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


if __name__ == "__main__":
    unittest.main()
