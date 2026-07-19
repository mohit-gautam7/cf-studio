import os
import unittest

os.environ["AI_MOCK"] = "1"

from server import ai  # noqa: E402
from server.executor import LocalExecutor  # noqa: E402
from server.seed import PROBLEMS  # noqa: E402
from server.stress import run_stress  # noqa: E402

EVEN_SPLIT = dict(PROBLEMS[0], id=1)


class TestExtractJson(unittest.TestCase):
    def test_plain_array(self):
        self.assertEqual(ai.extract_json('[{"input": "1"}]'), [{"input": "1"}])

    def test_fenced_with_prose(self):
        text = 'Here are the tests:\n```json\n[{"input": "2", "expected": "YES"}]\n```\nEnjoy!'
        self.assertEqual(ai.extract_json(text), [{"input": "2", "expected": "YES"}])

    def test_object_with_nested_brackets(self):
        self.assertEqual(ai.extract_json('note [1] then {"a": [1, 2, {"b": "}"}]}'),
                         {"a": [1, 2, {"b": "}"}]})

    def test_no_json_raises(self):
        with self.assertRaises(ai.AIError):
            ai.extract_json("no json here")


class TestContextBundle(unittest.TestCase):
    def test_bundle_includes_everything(self):
        ctx = ai.build_context(EVEN_SPLIT, code="print(1)", language="python",
                              last_run={"verdict": "WA"})
        for piece in ("Even Split", "candies", "Sample 1", "print(1)", "WA", "Input", "Output"):
            self.assertIn(piece, ctx)

    def test_html_stripped(self):
        self.assertNotIn("<p>", ai.build_context(EVEN_SPLIT))


class TestMockedFeatures(unittest.TestCase):
    def test_generate_tests(self):
        tests = ai.generate_tests(EVEN_SPLIT, count=5)
        self.assertGreaterEqual(len(tests), 3)
        self.assertTrue(all(t["input"].strip() for t in tests))

    def test_hint_and_bug_and_complexity(self):
        self.assertTrue(ai.hint(EVEN_SPLIT, 2))
        self.assertTrue(ai.find_bug(EVEN_SPLIT, "code", "python", {"verdict": "WA"}))
        self.assertIn("Time", ai.complexity(EVEN_SPLIT, "code", "python"))

    def test_generator_and_brute_are_code(self):
        self.assertIn("random", ai.input_generator(EVEN_SPLIT))
        self.assertIn("input()", ai.brute_force(EVEN_SPLIT))


class TestStress(unittest.TestCase):
    """Real subprocess execution through LocalExecutor (python)."""

    def test_buggy_solution_caught(self):
        buggy = "n = int(input())\nprint('YES' if n % 4 == 0 else 'NO')\n"  # wrong: 2 -> NO
        res = run_stress(LocalExecutor(), EVEN_SPLIT, buggy, "python", iterations=15)
        self.assertEqual(res["status"], "mismatch")
        self.assertEqual(res["kind"], "WA")
        self.assertEqual(res["brute_source"], "reference")
        self.assertTrue(res["input"].strip())

    def test_correct_solution_passes(self):
        good = "n = int(input())\nprint('YES' if n % 2 == 0 else 'NO')\n"
        res = run_stress(LocalExecutor(), EVEN_SPLIT, good, "python", iterations=6)
        self.assertEqual(res["status"], "passed")

    def test_crashing_solution_reported(self):
        crash = "import sys\nn = int(input())\nsys.exit(3)\n"
        res = run_stress(LocalExecutor(), EVEN_SPLIT, crash, "python", iterations=3)
        self.assertEqual(res["status"], "mismatch")
        self.assertEqual(res["kind"], "RE")


class TestProviderChain(unittest.TestCase):
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

    def test_priority_order_and_defaults(self):
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        os.environ["GROQ_API_KEY"] = "groq-key"
        os.environ["NVIDIA_API_KEY"] = "nv-key"
        ps = ai.providers()
        self.assertEqual([p["name"] for p in ps], ["openrouter", "nvidia", "groq"])
        self.assertIn("nemotron-3-ultra", ps[0]["model"])
        self.assertTrue(ps[0]["model"].endswith(":free"))
        self.assertEqual(ps[2]["model"], "openai/gpt-oss-120b")

    def test_legacy_key_maps_to_openrouter(self):
        os.environ["AI_API_KEY"] = "sk-or-legacy"
        ps = ai.providers()
        self.assertEqual(ps[0]["name"], "openrouter")
        self.assertEqual(ps[0]["key"], "sk-or-legacy")

    def test_custom_base_used_first(self):
        os.environ["AI_BASE_URL"] = "http://localhost:11434/v1"
        os.environ["AI_MODEL"] = "qwen2.5-coder"
        os.environ["GROQ_API_KEY"] = "g"
        self.assertEqual([p["name"] for p in ai.providers()], ["custom", "groq"])

    def test_failover_and_cooldown(self):
        os.environ["OPENROUTER_API_KEY"] = "a"
        os.environ["GROQ_API_KEY"] = "b"
        calls = []

        def fake(p, messages, temperature, max_tokens):
            calls.append(p["name"])
            if p["name"] == "openrouter":
                raise ai.AIError("HTTP 429: rate limited")
            return "answer from " + p["name"]

        orig = ai._call_provider
        ai._call_provider = fake
        try:
            self.assertEqual(ai.chat([{"role": "user", "content": "hi"}]), "answer from groq")
            self.assertEqual(calls, ["openrouter", "groq"])
            calls.clear()  # openrouter is cooling down -> groq goes first now
            ai.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(calls[0], "groq")
        finally:
            ai._call_provider = orig

    def test_all_providers_failing_raises_combined_error(self):
        os.environ["GROQ_API_KEY"] = "b"

        def boom(p, messages, temperature, max_tokens):
            raise ai.AIError("down")

        orig = ai._call_provider
        ai._call_provider = boom
        try:
            with self.assertRaises(ai.AIError) as cm:
                ai.chat([{"role": "user", "content": "hi"}])
            self.assertIn("groq", str(cm.exception))
        finally:
            ai._call_provider = orig

    def test_no_keys_error_is_actionable(self):
        with self.assertRaises(ai.AIError) as cm:
            ai.chat([{"role": "user", "content": "hi"}])
        self.assertIn("OPENROUTER_API_KEY", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
