"""HTTP server + API router. Stdlib http.server; JSON API under /api/*."""
import json
import os
import re
import threading
import traceback
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import ai, auth, cfimport, db, seed, stress
from .executor import get_executor, LANGUAGES
from .judge import run_tests

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
_executor = None
_executor_lock = threading.Lock()


def executor():
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = get_executor()
        return _executor


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------- helpers ----------------

def _get_problem(pid, with_secret=False):
    with db.connect() as con:
        row = con.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    if not row:
        raise ApiError(404, "problem not found")
    d = db.row_to_dict(row)
    if not with_secret:
        d = db.problem_public(row, full=True)
    return d


def _record_run(user, pid, kind, language, code, result):
    with db.connect() as con:
        con.execute(
            "INSERT INTO runs (user_id, problem_id, kind, language, verdict, passed, total, detail, code, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user["id"], pid, kind, language, result["verdict"], result["passed"], result["total"],
             json.dumps(result["results"])[:200000], code[:100000], db.now()))


def _last_run(user, pid):
    with db.connect() as con:
        row = con.execute(
            "SELECT verdict, passed, total, detail, language FROM runs WHERE user_id=? AND problem_id=? ORDER BY id DESC LIMIT 1",
            (user["id"], pid)).fetchone()
    return db.row_to_dict(row)


# ---------------- handlers ----------------

def h_health(ctx):
    return {"ok": True, "ai_configured": ai.is_configured(),
            "ai_providers": [{"name": p["name"], "model": p["model"]} for p in ai.providers()],
            "executor": os.environ.get("EXECUTOR", "auto"),
            "languages": list(LANGUAGES.keys())}


def h_register(ctx):
    email = (ctx["body"].get("email") or "").strip().lower()
    password = ctx["body"].get("password") or ""
    handle = (ctx["body"].get("handle") or "").strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError(400, "valid email required")
    if len(password) < 6:
        raise ApiError(400, "password must be at least 6 characters")
    with db.connect() as con:
        try:
            cur = con.execute("INSERT INTO users (email, password_hash, handle, created_at) VALUES (?,?,?,?)",
                              (email, auth.hash_password(password), handle, db.now()))
        except Exception:
            raise ApiError(409, "an account with this email already exists")
        uid = cur.lastrowid
    return {"token": auth.make_token(uid), "user": {"id": uid, "email": email, "handle": handle}}


def h_login(ctx):
    email = (ctx["body"].get("email") or "").strip().lower()
    password = ctx["body"].get("password") or ""
    with db.connect() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row or not auth.verify_password(password, row["password_hash"]):
        raise ApiError(401, "wrong email or password")
    return {"token": auth.make_token(row["id"]),
            "user": {"id": row["id"], "email": row["email"], "handle": row["handle"]}}


def h_me(ctx):
    return {"user": ctx["user"]}


def h_update_me(ctx):
    handle = (ctx["body"].get("handle") or "").strip()
    with db.connect() as con:
        con.execute("UPDATE users SET handle=? WHERE id=?", (handle, ctx["user"]["id"]))
    return {"ok": True, "handle": handle}


def h_problems(ctx):
    uid = ctx["user"]["id"]
    with db.connect() as con:
        rows = con.execute("SELECT * FROM problems ORDER BY id").fetchall()
        runs = con.execute(
            "SELECT problem_id, MAX(CASE WHEN verdict='OK' AND total>0 THEN 1 ELSE 0 END) solved, COUNT(*) attempts FROM runs WHERE user_id=? GROUP BY problem_id",
            (uid,)).fetchall()
        marks = con.execute("SELECT problem_id, label FROM bookmarks WHERE user_id=?", (uid,)).fetchall()
        cfok = con.execute("SELECT DISTINCT problem_id FROM cf_verdicts WHERE user_id=? AND verdict='OK'", (uid,)).fetchall()
    status = {r["problem_id"]: {"solved": bool(r["solved"]), "attempts": r["attempts"]} for r in runs}
    for r in cfok:
        status.setdefault(r["problem_id"], {"solved": False, "attempts": 0})["solved"] = True
    bm = {r["problem_id"]: r["label"] for r in marks}
    out = []
    for row in rows:
        p = db.problem_public(row)
        p["status"] = status.get(p["id"], {"solved": False, "attempts": 0})
        p["bookmark"] = bm.get(p["id"])
        out.append(p)
    return {"problems": out}


def h_problem(ctx):
    pid = int(ctx["match"].group(1))
    p = _get_problem(pid)
    with db.connect() as con:
        raw = con.execute("SELECT reference_solution FROM problems WHERE id=?", (pid,)).fetchone()
        bm = con.execute("SELECT label FROM bookmarks WHERE user_id=? AND problem_id=?",
                         (ctx["user"]["id"], pid)).fetchone()
    p["has_reference"] = bool(raw and raw["reference_solution"])
    p["bookmark"] = bm["label"] if bm else None
    return {"problem": p}


def h_import(ctx):
    url = (ctx["body"].get("url") or "").strip()
    try:
        pid, created = cfimport.import_problem(url)
    except ValueError as e:
        raise ApiError(400, str(e))
    except Exception as e:
        raise ApiError(502, "could not fetch/parse that problem: %s" % e)
    return {"problem_id": pid, "created": created}


def h_run(ctx):
    b = ctx["body"]
    pid = int(b.get("problem_id") or 0)
    language = b.get("language") or "cpp"
    code = b.get("code") or ""
    kind = b.get("kind") or "samples"
    if language not in LANGUAGES:
        raise ApiError(400, "unsupported language")
    if not code.strip():
        raise ApiError(400, "empty code")
    p = _get_problem(pid)
    if kind == "samples":
        tests = [{"input": s["input"], "expected": s["output"]} for s in p.get("samples", [])]
    elif kind == "ai":
        with db.connect() as con:
            rows = con.execute("SELECT input, expected FROM ai_tests WHERE user_id=? AND problem_id=? ORDER BY id",
                               (ctx["user"]["id"], pid)).fetchall()
        tests = [{"input": r["input"], "expected": r["expected"]} for r in rows]
        if not tests:
            raise ApiError(400, "no AI tests yet — generate them first")
    else:
        tests = [{"input": t.get("input", ""), "expected": t.get("expected", "")}
                 for t in (b.get("tests") or []) if (t.get("input") or "").strip()]
        if not tests:
            raise ApiError(400, "no custom tests provided")
    result = run_tests(executor(), p, language, code, tests)
    _record_run(ctx["user"], pid, kind, language, code, result)
    return {"result": result}


def h_tests_list(ctx):
    pid = int(ctx["query"].get("problem_id", ["0"])[0])
    with db.connect() as con:
        rows = con.execute("SELECT * FROM ai_tests WHERE user_id=? AND problem_id=? ORDER BY id",
                           (ctx["user"]["id"], pid)).fetchall()
    return {"tests": [db.row_to_dict(r) for r in rows]}


def h_tests_generate(ctx):
    pid = int(ctx["body"].get("problem_id") or 0)
    count = int(ctx["body"].get("count") or 8)
    p = _get_problem(pid)
    try:
        tests = ai.generate_tests(p, ctx["body"].get("code"), ctx["body"].get("language"),
                                  count=max(3, min(count, 25)))
    except ai.AIError as e:
        raise ApiError(502, str(e))
    with db.connect() as con:
        con.execute("DELETE FROM ai_tests WHERE user_id=? AND problem_id=?", (ctx["user"]["id"], pid))
        for t in tests:
            con.execute("INSERT INTO ai_tests (user_id, problem_id, input, expected, reason, validated, created_at) VALUES (?,?,?,?,?,0,?)",
                        (ctx["user"]["id"], pid, t["input"], t["expected"], t["reason"], db.now()))
    return h_tests_list({**ctx, "query": {"problem_id": [str(pid)]}})


def h_tests_validate(ctx):
    """Recompute expected outputs with a trusted solution (reference or AI brute)."""
    pid = int(ctx["body"].get("problem_id") or 0)
    p_secret = _get_problem(pid, with_secret=True)
    brute = p_secret.get("reference_solution")
    brute_lang = p_secret.get("reference_language", "python")
    if not brute:
        try:
            brute, brute_lang = ai.brute_force(_get_problem(pid)), "python"
        except ai.AIError as e:
            raise ApiError(502, str(e))
    with db.connect() as con:
        rows = con.execute("SELECT * FROM ai_tests WHERE user_id=? AND problem_id=? ORDER BY id",
                           (ctx["user"]["id"], pid)).fetchall()
    if not rows:
        raise ApiError(400, "no AI tests to validate")
    validated, dropped = 0, 0
    for r in rows:
        res = executor().run(brute_lang, brute, stdin=r["input"], time_limit_ms=15000)
        with db.connect() as con:
            if res.error or res.compile_code or res.exit_code != 0 or res.signal:
                con.execute("DELETE FROM ai_tests WHERE id=?", (r["id"],))
                dropped += 1
            else:
                con.execute("UPDATE ai_tests SET expected=?, validated=1 WHERE id=?",
                            (res.stdout.strip() + "\n", r["id"]))
                validated += 1
    out = h_tests_list({**ctx, "query": {"problem_id": [str(pid)]}})
    out.update({"validated": validated, "dropped": dropped})
    return out


def h_chat(ctx):
    b = ctx["body"]
    pid = int(b.get("problem_id") or 0)
    message = (b.get("message") or "").strip()
    if not message:
        raise ApiError(400, "empty message")
    p = _get_problem(pid)
    last_run = _last_run(ctx["user"], pid) if b.get("include_run", True) else None
    context = ai.build_context(p, b.get("code"), b.get("language"), last_run)
    with db.connect() as con:
        prev = con.execute("SELECT role, content FROM ai_chats WHERE user_id=? AND problem_id=? ORDER BY id DESC LIMIT 10",
                           (ctx["user"]["id"], pid)).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(prev)]
    history.append({"role": "user", "content": message})
    try:
        reply = ai.ask(context, message, history=history)
    except ai.AIError as e:
        raise ApiError(502, str(e))
    with db.connect() as con:
        con.execute("INSERT INTO ai_chats (user_id, problem_id, role, content, created_at) VALUES (?,?,?,?,?)",
                    (ctx["user"]["id"], pid, "user", message, db.now()))
        con.execute("INSERT INTO ai_chats (user_id, problem_id, role, content, created_at) VALUES (?,?,?,?,?)",
                    (ctx["user"]["id"], pid, "assistant", reply, db.now()))
    return {"reply": reply}


def h_chat_history(ctx):
    pid = int(ctx["query"].get("problem_id", ["0"])[0])
    with db.connect() as con:
        rows = con.execute("SELECT role, content, created_at FROM ai_chats WHERE user_id=? AND problem_id=? ORDER BY id",
                           (ctx["user"]["id"], pid)).fetchall()
    return {"messages": [db.row_to_dict(r) for r in rows]}


def _ai_feature(ctx, fn):
    b = ctx["body"]
    p = _get_problem(int(b.get("problem_id") or 0))
    try:
        return fn(p, b)
    except ai.AIError as e:
        raise ApiError(502, str(e))


def h_hint(ctx):
    return {"hint": _ai_feature(ctx, lambda p, b: ai.hint(p, b.get("level", 1), b.get("code"), b.get("language"))),
            "level": int(ctx["body"].get("level", 1))}


def h_find_bug(ctx):
    def fn(p, b):
        last_run = _last_run(ctx["user"], p["id"])
        return ai.find_bug(p, b.get("code") or "", b.get("language") or "?", last_run)
    return {"analysis": _ai_feature(ctx, fn)}


def h_complexity(ctx):
    return {"analysis": _ai_feature(ctx, lambda p, b: ai.complexity(p, b.get("code") or "", b.get("language") or "?"))}


def h_explain(ctx):
    return {"explanation": _ai_feature(ctx, lambda p, b: ai.explain(p, b.get("audience") or "competitive programmer"))}


def h_stress(ctx):
    b = ctx["body"]
    pid = int(b.get("problem_id") or 0)
    p = _get_problem(pid, with_secret=True)
    code, language = b.get("code") or "", b.get("language") or "cpp"
    if not code.strip():
        raise ApiError(400, "empty code")
    try:
        result = stress.run_stress(executor(), p, code, language, b.get("iterations", 20))
    except ai.AIError as e:
        raise ApiError(502, str(e))
    if result.get("status") == "mismatch":
        _record_run(ctx["user"], pid, "stress", language,
                    code, {"verdict": "STRESS_" + result.get("kind", "WA"), "passed": result.get("iteration", 0) - 1,
                           "total": result.get("iteration", 0), "results": [result]})
    return {"stress": result}


def h_notes_get(ctx):
    pid = int(ctx["query"].get("problem_id", ["0"])[0])
    with db.connect() as con:
        row = con.execute("SELECT content, updated_at FROM notes WHERE user_id=? AND problem_id=?",
                          (ctx["user"]["id"], pid)).fetchone()
    return {"content": row["content"] if row else "", "updated_at": row["updated_at"] if row else None}


def h_notes_put(ctx):
    pid = int(ctx["body"].get("problem_id") or 0)
    content = ctx["body"].get("content") or ""
    with db.connect() as con:
        con.execute("INSERT INTO notes (user_id, problem_id, content, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(user_id, problem_id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                    (ctx["user"]["id"], pid, content[:100000], db.now()))
    return {"ok": True}


def h_bookmarks(ctx):
    with db.connect() as con:
        rows = con.execute(
            "SELECT b.problem_id, b.label, b.created_at, p.title, p.rating FROM bookmarks b JOIN problems p ON p.id=b.problem_id WHERE b.user_id=? ORDER BY b.created_at DESC",
            (ctx["user"]["id"],)).fetchall()
    return {"bookmarks": [db.row_to_dict(r) for r in rows]}


def h_bookmark_toggle(ctx):
    pid = int(ctx["body"].get("problem_id") or 0)
    label = (ctx["body"].get("label") or "favorite")[:30]
    _get_problem(pid)
    with db.connect() as con:
        row = con.execute("SELECT label FROM bookmarks WHERE user_id=? AND problem_id=?",
                          (ctx["user"]["id"], pid)).fetchone()
        if row and row["label"] == label:
            con.execute("DELETE FROM bookmarks WHERE user_id=? AND problem_id=?", (ctx["user"]["id"], pid))
            return {"bookmark": None}
        con.execute("INSERT INTO bookmarks (user_id, problem_id, label, created_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(user_id, problem_id) DO UPDATE SET label=excluded.label",
                    (ctx["user"]["id"], pid, label, db.now()))
        return {"bookmark": label}


def h_submissions(ctx):
    pid = int(ctx["query"].get("problem_id", ["0"])[0])
    uid = ctx["user"]["id"]
    with db.connect() as con:
        runs = con.execute("SELECT id, kind, language, verdict, passed, total, created_at FROM runs "
                           "WHERE user_id=? AND problem_id=? ORDER BY id DESC LIMIT 50", (uid, pid)).fetchall()
        cf = con.execute("SELECT cf_submission_id, verdict, language, submitted_at FROM cf_verdicts "
                         "WHERE user_id=? AND problem_id=? ORDER BY submitted_at DESC LIMIT 50", (uid, pid)).fetchall()
    return {"runs": [db.row_to_dict(r) for r in runs], "codeforces": [db.row_to_dict(r) for r in cf]}


def h_cf_verdicts(ctx):
    handle = (ctx["body"].get("handle") or ctx["user"].get("handle") or "").strip()
    if not handle:
        raise ApiError(400, "set your Codeforces handle first")
    try:
        n = cfimport.import_verdicts(ctx["user"]["id"], handle)
    except Exception as e:
        raise ApiError(502, "Codeforces API failed: %s" % e)
    return {"imported": n}


def h_cf_rating(ctx):
    handle = (ctx["query"].get("handle", [""])[0] or ctx["user"].get("handle") or "").strip()
    if not handle:
        return {"rating": []}
    try:
        return {"rating": cfimport.rating_history(handle)}
    except Exception as e:
        raise ApiError(502, "Codeforces API failed: %s" % e)


def h_dashboard(ctx):
    uid = ctx["user"]["id"]
    with db.connect() as con:
        solved_rows = con.execute(
            "SELECT DISTINCT problem_id FROM runs WHERE user_id=? AND verdict='OK' AND total>0", (uid,)).fetchall()
        cf_solved = con.execute("SELECT DISTINCT problem_id FROM cf_verdicts WHERE user_id=? AND verdict='OK'", (uid,)).fetchall()
        attempted_rows = con.execute("SELECT DISTINCT problem_id FROM runs WHERE user_id=?", (uid,)).fetchall()
        day_rows = con.execute("SELECT DISTINCT date(created_at,'unixepoch','localtime') d FROM runs WHERE user_id=? ORDER BY d DESC LIMIT 400", (uid,)).fetchall()
        recent = con.execute(
            "SELECT p.id, p.title, p.rating, MAX(r.created_at) last_at, "
            "MAX(CASE WHEN r.verdict='OK' AND r.total>0 THEN 1 ELSE 0 END) solved "
            "FROM runs r JOIN problems p ON p.id=r.problem_id WHERE r.user_id=? "
            "GROUP BY p.id ORDER BY last_at DESC LIMIT 8", (uid,)).fetchall()
        tag_rows = con.execute(
            "SELECT p.tags, MAX(CASE WHEN r.verdict='OK' AND r.total>0 THEN 1 ELSE 0 END) solved "
            "FROM runs r JOIN problems p ON p.id=r.problem_id WHERE r.user_id=? GROUP BY p.id", (uid,)).fetchall()
    solved = {r["problem_id"] for r in solved_rows} | {r["problem_id"] for r in cf_solved}
    days = [r["d"] for r in day_rows]
    streak = 0
    cur = date.today()
    dayset = set(days)
    if str(cur) not in dayset and str(cur - timedelta(days=1)) in dayset:
        cur = cur - timedelta(days=1)
    while str(cur) in dayset:
        streak += 1
        cur -= timedelta(days=1)
    topics = {}
    for r in tag_rows:
        try:
            tags = json.loads(r["tags"])
        except Exception:
            tags = []
        for t in tags:
            a, s = topics.get(t, (0, 0))
            topics[t] = (a + 1, s + (1 if r["solved"] else 0))
    topic_stats = sorted(
        [{"tag": t, "attempted": a, "solved": s, "rate": round(100.0 * s / a)} for t, (a, s) in topics.items()],
        key=lambda x: (x["rate"], -x["attempted"]))
    bm = h_bookmarks(ctx)["bookmarks"]
    return {"solved": len(solved), "attempted": len(attempted_rows), "streak": streak,
            "recent": [db.row_to_dict(r) for r in recent], "topics": topic_stats[:10], "bookmarks": bm[:10]}


ROUTES = [
    ("GET", r"^/api/health$", h_health, False),
    ("POST", r"^/api/register$", h_register, False),
    ("POST", r"^/api/login$", h_login, False),
    ("GET", r"^/api/me$", h_me, True),
    ("POST", r"^/api/me$", h_update_me, True),
    ("GET", r"^/api/problems$", h_problems, True),
    ("POST", r"^/api/problems/import$", h_import, True),
    ("GET", r"^/api/problems/(\d+)$", h_problem, True),
    ("POST", r"^/api/run$", h_run, True),
    ("GET", r"^/api/tests$", h_tests_list, True),
    ("POST", r"^/api/tests/generate$", h_tests_generate, True),
    ("POST", r"^/api/tests/validate$", h_tests_validate, True),
    ("POST", r"^/api/ai/chat$", h_chat, True),
    ("GET", r"^/api/ai/chat$", h_chat_history, True),
    ("POST", r"^/api/ai/hint$", h_hint, True),
    ("POST", r"^/api/ai/find_bug$", h_find_bug, True),
    ("POST", r"^/api/ai/complexity$", h_complexity, True),
    ("POST", r"^/api/ai/explain$", h_explain, True),
    ("POST", r"^/api/stress$", h_stress, True),
    ("GET", r"^/api/notes$", h_notes_get, True),
    ("POST", r"^/api/notes$", h_notes_put, True),
    ("GET", r"^/api/bookmarks$", h_bookmarks, True),
    ("POST", r"^/api/bookmarks/toggle$", h_bookmark_toggle, True),
    ("GET", r"^/api/submissions$", h_submissions, True),
    ("POST", r"^/api/cf/verdicts$", h_cf_verdicts, True),
    ("GET", r"^/api/cf/rating$", h_cf_rating, True),
    ("GET", r"^/api/dashboard$", h_dashboard, True),
]
_COMPILED = [(m, re.compile(p), h, a) for m, p, h, a in ROUTES]

PAGES = {"/": "index.html", "/login": "login.html", "/problems": "problems.html", "/import": "import.html"}
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "CFStudio/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("CFSTUDIO_QUIET") != "1":
            super().log_message(fmt, *args)

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        if path.startswith("/p/") and path[3:].isdigit():
            fname = "problem.html"
        else:
            fname = PAGES.get(path)
            if fname is None:
                if not path.startswith("/static/"):
                    self._send_json(404, {"error": "not found"})
                    return
                fname = path[len("/static/"):]
        full = os.path.normpath(os.path.join(STATIC_DIR, fname))
        if not full.startswith(os.path.normpath(STATIC_DIR)) or not os.path.isfile(full):
            self._send_json(404, {"error": "not found"})
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            if method == "GET":
                self._serve_static(path)
            else:
                self._send_json(405, {"error": "method not allowed"})
            return
        for m, rx, handler, needs_auth in _COMPILED:
            if m != method:
                continue
            match = rx.match(path)
            if not match:
                continue
            try:
                user = None
                if needs_auth:
                    tok = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                    user = auth.get_user_by_token(tok)
                    if user is None:
                        self._send_json(401, {"error": "login required"})
                        return
                body = {}
                if method == "POST":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > 2_000_000:
                        self._send_json(413, {"error": "request too large"})
                        return
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        body = json.loads(raw.decode() or "{}")
                    except ValueError:
                        self._send_json(400, {"error": "invalid JSON"})
                        return
                ctx = {"user": user, "body": body, "match": match, "query": parse_qs(parsed.query)}
                result = handler(ctx)
                self._send_json(200, result)
            except ApiError as e:
                self._send_json(e.status, {"error": e.message})
            except Exception:
                traceback.print_exc()
                self._send_json(500, {"error": "internal error — see server console"})
            return
        self._send_json(404, {"error": "no such API route"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def create_server(port=8000, host="127.0.0.1"):
    db.init_db()
    added = seed.seed_if_empty()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv, added
