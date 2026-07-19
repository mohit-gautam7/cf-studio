"""Remote-DB adapter tests: a fake Turso server (stdlib http.server) speaking
the /v2/pipeline wire protocol, backed by real in-memory SQLite. The whole
app storage layer (schema, seed, upserts, lastrowid, typed rows) runs through
the HTTP adapter exactly as it would against real Turso."""
import json
import os
import sqlite3
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server import db, remote_db
from server.seed import seed_if_empty

_LOCK = threading.Lock()
_SQL = None  # shared in-memory sqlite behind the fake API
SEEN_AUTH = []


def _encode_cell(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


class FakeTurso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        SEEN_AUTH.append(self.headers.get("Authorization"))
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        results = []
        with _LOCK:
            for r in body.get("requests", []):
                if r.get("type") == "close":
                    results.append({"type": "ok", "response": {"type": "close"}})
                    continue
                stmt = r.get("stmt", {})
                args = [remote_db._from_cell(a) for a in stmt.get("args", [])]
                try:
                    cur = _SQL.execute(stmt.get("sql", ""), args)
                    cols = [d[0] for d in (cur.description or [])]
                    rows = [[_encode_cell(v) for v in row] for row in cur.fetchall()]
                    _SQL.commit()
                    results.append({"type": "ok", "response": {"type": "execute", "result": {
                        "cols": [{"name": c} for c in cols], "rows": rows,
                        "affected_row_count": max(cur.rowcount, 0),
                        "last_insert_rowid": str(cur.lastrowid) if cur.lastrowid else None}}})
                except sqlite3.Error as e:
                    results.append({"type": "error", "error": {"message": str(e)}})
                    break
        payload = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class TestRemoteDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _SQL
        _SQL = sqlite3.connect(":memory:", check_same_thread=False)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeTurso)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.saved = {k: os.environ.get(k) for k in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")}
        os.environ["TURSO_DATABASE_URL"] = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        os.environ["TURSO_AUTH_TOKEN"] = "test-token"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_01_mode_and_schema_and_seed(self):
        self.assertEqual(db.mode(), "turso")
        db.init_db()
        self.assertEqual(seed_if_empty(), 4)
        with db.connect() as con:
            rows = con.execute("SELECT * FROM problems ORDER BY id").fetchall()
        self.assertEqual(len(rows), 4)
        first = db.row_to_dict(rows[0])
        self.assertEqual(first["title"], "Even Split")
        self.assertEqual(first["tags"], ["math"])          # JSON round trip
        self.assertIsInstance(first["time_limit_ms"], int)  # typed cells decoded

    def test_02_params_lastrowid_and_null(self):
        with db.connect() as con:
            cur = con.execute("INSERT INTO users (email, password_hash, handle, created_at) VALUES (?,?,?,?)",
                              ("remote@test.dev", "hash", "", 123))
            uid = cur.lastrowid
            self.assertIsInstance(uid, int)
            row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        self.assertEqual(row["email"], "remote@test.dev")
        self.assertEqual(row["created_at"], 123)
        self.assertEqual(dict(row)["handle"], "")

    def test_03_upsert_and_or_ignore(self):
        with db.connect() as con:
            for content in ("v1", "v2"):
                con.execute("INSERT INTO notes (user_id, problem_id, content, updated_at) VALUES (?,?,?,?) "
                            "ON CONFLICT(user_id, problem_id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                            (1, 1, content, 5))
            note = con.execute("SELECT content FROM notes WHERE user_id=1 AND problem_id=1").fetchone()
            self.assertEqual(note["content"], "v2")
            for _ in range(2):
                con.execute("INSERT OR IGNORE INTO cf_verdicts (user_id, problem_id, cf_submission_id, verdict, language, submitted_at) VALUES (?,?,?,?,?,?)",
                            (1, 1, 777, "OK", "cpp", 1))
            n = con.execute("SELECT COUNT(*) c FROM cf_verdicts").fetchone()
        self.assertEqual(n["c"], 1)

    def test_04_bearer_token_sent(self):
        self.assertTrue(SEEN_AUTH)
        self.assertTrue(all(a == "Bearer test-token" for a in SEEN_AUTH))

    def test_05_problem_public_shape(self):
        with db.connect() as con:
            row = con.execute("SELECT * FROM problems WHERE id=1").fetchone()
        p = db.problem_public(row, full=True)
        self.assertNotIn("reference_solution", p)
        self.assertEqual(len(p["samples"]), 2)

    def test_06_sql_error_raises(self):
        with self.assertRaises(remote_db.RemoteError):
            with db.connect() as con:
                con.execute("SELECT * FROM no_such_table")


if __name__ == "__main__":
    unittest.main()
