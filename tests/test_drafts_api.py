"""Draft sync + submission storage/restore endpoints, over a real server."""
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


class TestDraftsAndSubmissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cfstudio_drafts_")
        cls.saved_paths = (db.DATA_DIR, db.DB_PATH)
        db.DATA_DIR = cls.tmp
        db.DB_PATH = os.path.join(cls.tmp, "drafts_test.db")
        from server.app import create_server
        cls.srv, _ = create_server(port=0)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.token = cls.api("POST", "/api/register",
                            {"email": "draft@test.dev", "password": "secret1"}, token=None)[1]["token"]
        cls.other = cls.api("POST", "/api/register",
                            {"email": "other@test.dev", "password": "secret1"}, token=None)[1]["token"]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        db.DATA_DIR, db.DB_PATH = cls.saved_paths
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def api(cls, method, path, body=None, token="default"):
        headers = {"Content-Type": "application/json"}
        tok = cls.token if token == "default" else token
        if tok:
            headers["Authorization"] = "Bearer " + tok
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(cls.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_01_draft_roundtrip_per_language(self):
        s, d = self.api("GET", "/api/draft?problem_id=1&language=cpp")
        self.assertIsNone(d["code"])
        self.api("POST", "/api/draft", {"problem_id": 1, "language": "cpp", "code": "int main(){}"})
        self.api("POST", "/api/draft", {"problem_id": 1, "language": "python", "code": "print(1)"})
        s, d = self.api("GET", "/api/draft?problem_id=1&language=cpp")
        self.assertEqual(d["code"], "int main(){}")
        s, d = self.api("GET", "/api/draft?problem_id=1&language=python")
        self.assertEqual(d["code"], "print(1)")
        self.api("POST", "/api/draft", {"problem_id": 1, "language": "cpp", "code": "int main(){return 0;}"})
        s, d = self.api("GET", "/api/draft?problem_id=1&language=cpp")
        self.assertEqual(d["code"], "int main(){return 0;}")  # upsert, not duplicate

    def test_02_submitted_snapshot_and_restore(self):
        s, d = self.api("POST", "/api/submitted",
                        {"problem_id": 1, "language": "cpp", "code": "// submitted to CF"})
        self.assertEqual(s, 200)
        s, subs = self.api("GET", "/api/submissions?problem_id=1")
        submit_runs = [r for r in subs["runs"] if r["kind"] == "submit"]
        self.assertEqual(len(submit_runs), 1)
        self.assertEqual(submit_runs[0]["verdict"], "SUBMITTED")
        rid = submit_runs[0]["id"]
        s, code = self.api("GET", "/api/runs/%d/code" % rid)
        self.assertEqual(code["code"], "// submitted to CF")
        self.assertEqual(code["language"], "cpp")

    def test_03_run_code_stored_and_owned(self):
        good = "n = int(input())\nprint('YES' if n % 2 == 0 else 'NO')\n"
        s, d = self.api("POST", "/api/run", {"problem_id": 1, "language": "python", "code": good, "kind": "samples"})
        self.assertEqual(d["result"]["verdict"], "OK")
        s, subs = self.api("GET", "/api/submissions?problem_id=1")
        rid = subs["runs"][0]["id"]
        s, code = self.api("GET", "/api/runs/%d/code" % rid)
        self.assertEqual(code["code"], good)
        s, _ = self.api("GET", "/api/runs/%d/code" % rid, token=self.other)
        self.assertEqual(s, 404)  # other users can never read your code


if __name__ == "__main__":
    unittest.main()
