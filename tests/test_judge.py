import unittest

from server.executor import ExecResult
from server.judge import compare_output, run_tests

PROBLEM = {"time_limit_ms": 1000}


class FakeExecutor:
    """Maps stripped stdin -> ExecResult. Thread-safe and order-independent,
    matching the parallel judge."""

    def __init__(self, mapping, default=None):
        self.mapping = mapping
        self.default = default or ExecResult(stdout="")

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        return self.mapping.get((stdin or "").strip(), self.default)


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

    def test_case_insensitive_like_codeforces(self):
        self.assertTrue(compare_output("YES\nNO", "yes\nno"))
        self.assertTrue(compare_output("Yes", "yEs"))
        self.assertTrue(compare_output("IMPOSSIBLE", "impossible"))
        self.assertFalse(compare_output("YES", "NO"))

    def test_lowercase_output_gets_ok_verdict(self):
        ex = FakeExecutor({"2": ExecResult(stdout="yes\n"), "3": ExecResult(stdout="no\n")})
        r = run_tests(ex, PROBLEM, "python", "x",
                      [{"input": "2", "expected": "YES"}, {"input": "3", "expected": "NO"}])
        self.assertEqual((r["verdict"], r["passed"]), ("OK", 2))


class TestVerdicts(unittest.TestCase):
    def test_all_ok(self):
        ex = FakeExecutor({"8": ExecResult(stdout="YES"), "5": ExecResult(stdout="NO")})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "8", "expected": "YES"}, {"input": "5", "expected": "NO"}])
        self.assertEqual((r["verdict"], r["passed"], r["total"]), ("OK", 2, 2))

    def test_wa(self):
        ex = FakeExecutor({"8": ExecResult(stdout="NO"), "5": ExecResult(stdout="NO")})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "8", "expected": "YES"}, {"input": "5", "expected": "NO"}])
        self.assertEqual((r["verdict"], r["passed"]), ("WA", 1))
        self.assertEqual(r["results"][0]["verdict"], "WA")

    def test_tle(self):
        ex = FakeExecutor({"1": ExecResult(signal="SIGKILL", time_ms=1000)})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "TLE")

    def test_re(self):
        ex = FakeExecutor({"1": ExecResult(exit_code=1, stderr="boom")})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "RE")

    def test_ce_short_circuits_before_parallel_batch(self):
        ex = FakeExecutor({}, default=ExecResult(compile_output="error: x", compile_code=1))
        r = run_tests(ex, PROBLEM, "cpp", "x", [{"input": "1", "expected": "1"}, {"input": "2", "expected": "2"}])
        self.assertEqual(r["verdict"], "CE")
        self.assertEqual(len(r["results"]), 1)

    def test_run_only_without_expected(self):
        ex = FakeExecutor({"1": ExecResult(stdout="whatever")})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1"}])
        self.assertEqual(r["verdict"], "OK")
        self.assertEqual(r["results"][0]["verdict"], "RUN")

    def test_judge_error(self):
        ex = FakeExecutor({"1": ExecResult(error="judge unreachable")})
        r = run_tests(ex, PROBLEM, "python", "x", [{"input": "1", "expected": "1"}])
        self.assertEqual(r["verdict"], "JUDGE_ERROR")

    def test_parallel_results_keep_input_order(self):
        mapping = {str(i): ExecResult(stdout=str(i * 10)) for i in range(1, 8)}
        mapping["4"] = ExecResult(stdout="wrong")
        tests = [{"input": str(i), "expected": str(i * 10)} for i in range(1, 8)]
        r = run_tests(FakeExecutor(mapping), PROBLEM, "python", "x", tests)
        self.assertEqual([e["i"] for e in r["results"]], list(range(7)))  # ordered despite threads
        self.assertEqual(r["results"][3]["verdict"], "WA")
        self.assertEqual((r["verdict"], r["passed"]), ("WA", 6))


if __name__ == "__main__":
    unittest.main()
