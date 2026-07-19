import os
import unittest

from server import executor as ex
from server import ai
from server.executor import AutoExecutor, ExecResult, WandboxExecutor, get_executor


class FakeBackend:
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = 0

    def run(self, *a, **k):
        self.calls += 1
        return self.result


class TestAutoExecutor(unittest.TestCase):
    def test_infra_error_falls_through(self):
        dead = FakeBackend("dead", ExecResult(error="unreachable"))
        ok = FakeBackend("ok", ExecResult(stdout="42\n"))
        auto = AutoExecutor(backends=[dead, ok])
        r = auto.run("cpp", "code", stdin="1")
        self.assertIsNone(r.error)
        self.assertEqual(r.stdout, "42\n")
        # dead backend is now cooled down -> next call goes straight to ok
        auto.run("cpp", "code")
        self.assertEqual(dead.calls, 1)
        self.assertEqual(ok.calls, 2)

    def test_real_verdict_does_not_fall_through(self):
        ce = FakeBackend("ce", ExecResult(compile_output="error: x", compile_code=1))
        never = FakeBackend("never", ExecResult(stdout="should not run"))
        r = AutoExecutor(backends=[ce, never]).run("cpp", "bad code")
        self.assertEqual(r.compile_code, 1)
        self.assertEqual(never.calls, 0)

    def test_all_dead_reports_each(self):
        a = FakeBackend("a", ExecResult(error="down-a"))
        b = FakeBackend("b", ExecResult(error="down-b"))
        r = AutoExecutor(backends=[a, b]).run("python", "x")
        self.assertIn("down-a", r.error)
        self.assertIn("down-b", r.error)

    def test_default_executor_is_auto(self):
        saved = os.environ.pop("EXECUTOR", None)
        try:
            self.assertIsInstance(get_executor(), AutoExecutor)
        finally:
            if saved is not None:
                os.environ["EXECUTOR"] = saved


class TestWandboxMapping(unittest.TestCase):
    def _with_response(self, response):
        original = ex._post_json
        ex._post_json = lambda *a, **k: response
        self.addCleanup(lambda: setattr(ex, "_post_json", original))
        w = WandboxExecutor()
        w._throttle.min_interval = 0
        return w

    def test_ok_run(self):
        w = self._with_response({"status": "0", "signal": "", "compiler_error": "",
                                 "program_output": "42\n", "program_error": "", "program_message": "42\n"})
        r = w.run("cpp", "code", stdin="2 40")
        self.assertIsNone(r.error)
        self.assertEqual((r.stdout, r.exit_code, r.compile_code), ("42\n", 0, 0))

    def test_compile_error(self):
        w = self._with_response({"status": "1", "compiler_error": "main.cpp: error: expected ';'",
                                 "compiler_output": ""})
        r = w.run("cpp", "bad")
        self.assertEqual(r.compile_code, 1)
        self.assertIn("expected", r.compile_output)

    def test_killed_maps_to_sigkill(self):
        w = self._with_response({"status": "", "signal": "Killed", "compiler_error": "",
                                 "program_output": "", "program_error": "", "program_message": ""})
        r = w.run("python", "while True: pass")
        self.assertEqual(r.signal, "SIGKILL")

    def test_unsupported_language_is_infra_error(self):
        r = WandboxExecutor().run("kotlin", "code")
        self.assertIsNotNone(r.error)


class TestFastRouting(unittest.TestCase):
    KEYS = ("AI_MOCK", "AI_BASE_URL", "AI_MODEL", "AI_API_KEY",
            "OPENROUTER_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY")

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.KEYS}
        for k in self.KEYS:
            os.environ.pop(k, None)
        ai._cooldown.clear()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        ai._cooldown.clear()

    def test_prefer_fast_puts_groq_first(self):
        os.environ["OPENROUTER_API_KEY"] = "a"
        os.environ["GROQ_API_KEY"] = "b"
        order = []

        def fake(p, messages, temperature, max_tokens):
            order.append(p["name"])
            return "ok"

        orig = ai._call_provider
        ai._call_provider = fake
        try:
            ai.chat([{"role": "user", "content": "x"}], prefer="fast")
            self.assertEqual(order[0], "groq")
            order.clear()
            ai.chat([{"role": "user", "content": "x"}])  # smart default
            self.assertEqual(order[0], "openrouter")
        finally:
            ai._call_provider = orig


class TestImportPage(unittest.TestCase):
    def test_route_and_file_exist(self):
        from server.app import PAGES, STATIC_DIR
        self.assertEqual(PAGES.get("/import"), "import.html")
        self.assertTrue(os.path.isfile(os.path.join(STATIC_DIR, "import.html")))


if __name__ == "__main__":
    unittest.main()
