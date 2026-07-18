import unittest

from server.executor import ExecResult
from server.judge import compare_output, run_tests

PROBLEM = {"time_limit_ms": 1000}


class FakeExecutor:
    """Returns queued ExecResults in order."""

    def __init__(self, results):
        self.results = list(results)

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        return self.results.pop(0)


class TestCompare(unittest.TestCase):
    def test_whitespace_insensitive(self):
        self.assertTrue(compare_output("YES\n", "  YES  "))
        self.assertTrue(compare_output("1 2 3", "1\n2\n3\n"))

    def test_mismatch(self):
        self.assertFalse(compare_output("YES", "NO"))
        self.assertFalse(compare_output("1 2", "1 2 3"))

    def test_float_tolerance(self):
        self.assertTrue(compare_output("0.3333333", "0.333333333333"))
        self.assertFalse(compare_output("0.5", "0.6"))


class TestVerdicts(unittest.TestCase):
    def test_all_ok(self):
        ex = FakeExecutor([ExecResult(stdout="YES"), ExecResult(stdout="NO")])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "8", "expected": "YES"}, {"input": "5", "expected": "NO"}])
        self.assertEqual((r["verdict"], r["passed"], r["total"]), ("OK", 2, 2))

    def test_wa(self):
        ex = FakeExecutor([ExecResult(stdout="NO"), ExecResult(stdout="NO")])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "8", "expected": "YES"}, {"input": "5", "expected": "NO"}])
        self.assertEqual((r["verdict"], r["passed"]), ("WA", 1))
        self.assertEqual(r["results"][0]["verdict"], "WA")

    def test_tle(self):
        ex = FakeExecutor([ExecResult(signal="SIGKILL", time_ms=1000)])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "TLE")

    def test_re(self):
        ex = FakeExecutor([ExecResult(exit_code=1, stderr="boom")])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "RE")

    def test_ce_short_circuits(self):
        ex = FakeExecutor([ExecResult(compile_output="error: x", compile_code=1)])
        r = run_tests(ex, PROBLEM, "cpp", "x", [{"input": "1", "expected": "1"}, {"input": "2", "expected": "2"}])
        self.assertEqual(r["verdict"], "CE")
        self.assertEqual(len(r["results"]), 1)

    def test_run_only_without_expected(self):
        ex = FakeExecutor([ExecResult(stdout="whatever")])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1"}])
        self.assertEqual(r["verdict"], "OK")
        self.assertEqual(r["results"][0]["verdict"], "RUN")

    def test_judge_error(self):
        ex = FakeExecutor([ExecResult(error="judge unreachable")])
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "JUDGE_ERROR")


if __name__ == "__main__":
    unittest.main()
