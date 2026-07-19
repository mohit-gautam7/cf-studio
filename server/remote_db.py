"""Persistent remote database: Turso (hosted libSQL/SQLite) over plain HTTP.

Zero dependencies — stdlib urllib against Turso's /v2/pipeline API
(https://docs.turso.tech/sdk/http/reference). Activated when both
TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set; otherwise CF Studio keeps
using the local SQLite file. This is what makes accounts/notes survive
redeploys and restarts on ephemeral hosts like Render's free tier.

The classes below mimic the small slice of the sqlite3 API the app uses:
connection.execute(sql, params) -> cursor with fetchone/fetchall/lastrowid,
connection.executescript(sql), rows readable by index, name, or dict(row).
"""
import json
import os
import urllib.error
import urllib.request


def is_configured():
    return bool(os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"))


def _base_url():
    u = (os.environ.get("TURSO_DATABASE_URL") or "").strip().rstrip("/")
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://"):]
    return u


class RemoteError(Exception):
    pass


def _to_arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _from_cell(c):
    if not isinstance(c, dict):
        return c
    t = c.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(c["value"])
    if t == "float":
        return float(c["value"])
    return c.get("value")


def _pipeline(requests_):
    payload = {"requests": requests_ + [{"type": "close"}]}
    req = urllib.request.Request(
        _base_url() + "/v2/pipeline",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + (os.environ.get("TURSO_AUTH_TOKEN") or "")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RemoteError("Turso HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:300]))
    except Exception as e:
        raise RemoteError("Turso unreachable: %s" % e)
    out = []
    for res in data.get("results", []):
        if res.get("type") == "error":
            raise RemoteError(res.get("error", {}).get("message", "database error"))
        # tolerate both the nested wire shape and the flattened documented shape
        result = res.get("response", {}).get("result") if isinstance(res.get("response"), dict) else None
        if result is None:
            result = res.get("result") if isinstance(res.get("result"), dict) else res
        out.append(result or {})
    return out


class RemoteRow:
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals

    def keys(self):
        return list(self._cols)

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._vals[self._cols.index(k)]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class RemoteCursor:
    def __init__(self, rows, lastrowid, rowcount):
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


def _result_to_cursor(result):
    cols = [c.get("name") for c in result.get("cols", [])]
    rows = [RemoteRow(cols, [_from_cell(c) for c in r]) for r in result.get("rows", [])]
    lastrow = result.get("last_insert_rowid")
    try:
        lastrow = int(lastrow) if lastrow is not None else None
    except (TypeError, ValueError):
        lastrow = None
    return RemoteCursor(rows, lastrow, result.get("affected_row_count", 0))


class RemoteConnection:
    """One logical connection; each execute is its own atomic HTTP round trip."""

    def execute(self, sql, params=()):
        stmt = {"sql": sql}
        if params:
            stmt["args"] = [_to_arg(p) for p in params]
        result = _pipeline([{"type": "execute", "stmt": stmt}])[0]
        return _result_to_cursor(result)

    def executescript(self, script):
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        _pipeline([{"type": "execute", "stmt": {"sql": s}} for s in stmts])

    def commit(self):
        pass

    def close(self):
        pass
