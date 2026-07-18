"""Full-stack e2e: boots the real HTTP server (local executor + mock AI) and
drives the API the same way the frontend does."""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

os.environ["EXECUTOR"] = "local"
os.environ["AI_MOCK"] = "1"
os.environ["CFSTUDIO_QUIET"] = "1"

from server import db  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="cfstudio_test_")
db.DATA_DIR = _TMP
db.DB_PATH = os.path.join(_TMP, "test.db")

from server.app import create_server  # noqa: E402

GOOD = "n = int(input())\nprint('YES' if n % 2 == 0 else 'NO')\n"
WRONG = "n = int(input())\nprint('NO')\n"
BUGGY = "n = int(input())\nprint('YES' if n % 4 == 0 else 'NO')\n"


class TestApiE2E(unittest.TestCase):
    token = None
    base = None

    @classmethod
    def setUpClass(cls):
        cls.srv, _ = create_server(port=0)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(_TMP, ignore_errors=True)

    @classmethod
    def api(cls, method, path, body=None, token="default"):
        headers = {"Content-Type": "application/json"}
        tok = cls.token if token == "default" else token
        if tok:
            headers["Authorization"] = "Bearer " + tok
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(cls.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_01_health_public(self):
        s, d = self.api("GET", "/api/health", token=None)
        self.assertEqual(s, 200)
        self.assertIn("cpp", d["languages"])

    def test_02_register_and_me(self):
        s, d = self.api("POST", "/api/register",
                        {"email": "mohit@test.dev", "password": "secret1", "handle": "tourist_fan"}, token=None)
        self.assertEqual(s, 200, d)
        type(self).token = d["token"]
        s, d = self.api("GET", "/api/me")
        self.assertEqual(d["user"]["email"], "mohit@test.dev")

    def test_03_auth_rejections(self):
        s, _ = self.api("POST", "/api/login", {"email": "mohit@test.dev", "password": "nope"}, token=None)
        self.assertEqual(s, 401)
        s, _ = self.api("GET", "/api/problems", token=None)
        self.assertEqual(s, 401)
        s, _ = self.api("GET", "/api/problems", token="broken.token")
        self.assertEqual(s, 401)

    def test_04_seeded_problems(self):
        s, d = self.api("GET", "/api/problems")
        self.assertEqual(s, 200)
        self.assertEqual(len(d["problems"]), 4)
        self.assertEqual(d["problems"][0]["title"], "Even Split")

    def test_05_problem_detail(self):
        s, d = self.api("GET", "/api/problems/1")
        p = d["problem"]
        self.assertEqual(len(p["samples"]), 2)
        self.assertIn("$$$n$$$", p["input_spec_html"])
        self.assertTrue(p["has_reference"])
        self.assertNotIn("reference_solution", p)

    def test_06_run_samples_ok(self):
        s, d = self.api("POST", "/api/run", {"problem_id": 1, "language": "python", "code": GOOD, "kind": "samples"})
        self.assertEqual(s, 200, d)
        self.assertEqual(d["result"]["verdict"], "OK")
        self.assertEqual(d["result"]["passed"], 2)

    def test_07_run_samples_wa(self):
        s, d = self.api("POST", "/api/run", {"problem_id": 1, "language": "python", "code": WRONG, "kind": "samples"})
        self.assertEqual(d["result"]["verdict"], "WA")

    def test_08_run_custom(self):
        s, d = self.api("POST", "/api/run", {
            "problem_id": 1, "language": "python", "code": GOOD, "kind": "custom",
            "tests": [{"input": "10", "expected": "YES"}, {"input": "3", "expected": ""}]})
        self.assertEqual(d["result"]["verdict"], "OK")
        self.assertEqual(d["result"]["results"][1]["verdict"], "RUN")

    def test_09_ai_tests_generate_validate_run(self):
        s, d = self.api("POST", "/api/tests/generate", {"problem_id": 1, "count": 8})
        self.assertEqual(s, 200, d)
        self.assertGreaterEqual(len(d["tests"]), 3)
        self.assertFalse(d["tests"][0]["validated"])
        s, d = self.api("POST", "/api/tests/validate", {"problem_id": 1})
        self.assertEqual(s, 200, d)
        self.assertGreaterEqual(d["validated"], 3)
        self.assertTrue(all(t["validated"] for t in d["tests"]))
        self.assertEqual(d["tests"][0]["expected"].strip(), "NO")  # input 1 -> NO
        s, d = self.api("POST", "/api/run", {"problem_id": 1, "language": "python", "code": GOOD, "kind": "ai"})
        self.assertEqual(d["result"]["verdict"], "OK")

    def test_10_notes(self):
        self.api("POST", "/api/notes", {"problem_id": 1, "content": "parity! $$$O(1)$$$"})
        s, d = self.api("GET", "/api/notes?problem_id=1")
        self.assertIn("parity", d["content"])

    def test_11_bookmarks(self):
        s, d = self.api("POST", "/api/bookmarks/toggle", {"problem_id": 2, "label": "redo"})
        self.assertEqual(d["bookmark"], "redo")
        s, d = self.api("GET", "/api/bookmarks")
        self.assertEqual(d["bookmarks"][0]["title"], "Largest Gap")
        s, d = self.api("POST", "/api/bookmarks/toggle", {"problem_id": 2, "label": "redo"})
        self.assertIsNone(d["bookmark"])

    def test_12_submissions_history(self):
        s, d = self.api("GET", "/api/submissions?problem_id=1")
        self.assertGreaterEqual(len(d["runs"]), 3)
        self.assertIn(d["runs"][0]["verdict"], ("OK", "WA"))

    def test_13_dashboard(self):
        s, d = self.api("GET", "/api/dashboard")
        self.assertGreaterEqual(d["solved"], 1)
        self.assertGreaterEqual(d["attempted"], 1)
        self.assertGreaterEqual(d["streak"], 1)
        self.assertTrue(any(t["tag"] == "math" for t in d["topics"]))

    def test_14_stress_catches_bug(self):
        s, d = self.api("POST", "/api/stress", {"problem_id": 1, "language": "python", "code": BUGGY, "iterations": 15})
        self.assertEqual(s, 200, d)
        self.assertEqual(d["stress"]["status"], "mismatch")
        self.assertEqual(d["stress"]["kind"], "WA")

    def test_15_ai_endpoints(self):
        s, d = self.api("POST", "/api/ai/chat", {"problem_id": 1, "message": "how to approach?", "code": GOOD, "language": "python"})
        self.assertEqual(s, 200, d)
        self.assertTrue(d["reply"])
        s, d = self.api("GET", "/api/ai/chat?problem_id=1")
        self.assertEqual(len(d["messages"]), 2)
        s, d = self.api("POST", "/api/ai/hint", {"problem_id": 1, "level": 2})
        self.assertTrue(d["hint"])
        s, d = self.api("POST", "/api/ai/find_bug", {"problem_id": 1, "code": BUGGY, "language": "python"})
        self.assertIn("Fix", d["analysis"])
        s, d = self.api("POST", "/api/ai/complexity", {"problem_id": 1, "code": GOOD, "language": "python"})
        self.assertIn("Time", d["analysis"])

    def test_16_bad_import_url(self):
        s, d = self.api("POST", "/api/problems/import", {"url": "https://example.com/nope"})
        self.assertEqual(s, 400)

    def test_17_static_pages_served(self):
        for path in ("/", "/login", "/problems", "/p/1", "/static/js/workspace.js"):
            req = urllib.request.Request(self.base + path)
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(r.status, 200, path)


if __name__ == "__main__":
    unittest.main()
