"""Talk to codeforces.com from the user's machine: import problems by URL,
pull verdicts and rating history by handle (public API, no login, read-only)."""
import gzip
import json
import urllib.request

from . import cfparse, db

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) CF-Studio/1.0 (personal practice tool)",
      "Accept-Encoding": "gzip"}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")


def _api(method, **params):
    qs = "&".join("%s=%s" % (k, v) for k, v in params.items())
    data = json.loads(_get("https://codeforces.com/api/%s?%s" % (method, qs)))
    if data.get("status") != "OK":
        raise RuntimeError("Codeforces API error: %s" % data.get("comment", "unknown"))
    return data["result"]


def import_problem(url):
    """Fetch + parse a CF problem page; upsert into DB; return problem id."""
    ids = cfparse.parse_problem_url(url)
    if not ids:
        raise ValueError("not a recognizable Codeforces problem URL")
    contest_id, index = ids
    canonical = "https://codeforces.com/problemset/problem/%d/%s" % (contest_id, index)
    with db.connect() as con:
        row = con.execute("SELECT id FROM problems WHERE cf_contest_id=? AND cf_index=?",
                          (contest_id, index)).fetchone()
        if row:
            return row["id"], False
    html = _get(canonical)
    if "problem-statement" not in html:  # problemset page missing (old/gym) -> contest URL
        html = _get("https://codeforces.com/contest/%d/problem/%s" % (contest_id, index))
    p = cfparse.parse_problem(html)
    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO problems (source, cf_contest_id, cf_index, url, title, rating, tags,
               time_limit_ms, memory_limit_mb, statement_html, input_spec_html, output_spec_html,
               note_html, samples, created_at)
               VALUES ('cf',?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (contest_id, index, canonical, p["title"], p["rating"], json.dumps(p["tags"]),
             p["time_limit_ms"], p["memory_limit_mb"], p["statement_html"], p["input_spec_html"],
             p["output_spec_html"], p["note_html"], json.dumps(p["samples"]), db.now()))
        return cur.lastrowid, True


def import_verdicts(user_id, handle, count=200):
    """Match the user's recent CF submissions to imported problems."""
    subs = _api("user.status", handle=handle, count=count)
    with db.connect() as con:
        known = {(r["cf_contest_id"], r["cf_index"]): r["id"] for r in
                 con.execute("SELECT id, cf_contest_id, cf_index FROM problems WHERE source='cf'")}
        imported = 0
        for s in subs:
            prob = s.get("problem", {})
            key = (prob.get("contestId"), prob.get("index"))
            pid = known.get(key)
            if not pid:
                continue
            try:
                con.execute(
                    "INSERT OR IGNORE INTO cf_verdicts (user_id, problem_id, cf_submission_id, verdict, language, submitted_at) VALUES (?,?,?,?,?,?)",
                    (user_id, pid, s["id"], s.get("verdict", "?"),
                     s.get("programmingLanguage", ""), s.get("creationTimeSeconds", 0)))
                imported += 1
            except Exception:
                pass
    return imported


def rating_history(handle):
    res = _api("user.rating", handle=handle)
    return [{"contest": r.get("contestName", ""), "at": r.get("ratingUpdateTimeSeconds", 0),
             "old": r.get("oldRating"), "new": r.get("newRating")} for r in res]
