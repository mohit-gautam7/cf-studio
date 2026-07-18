"""Verdict computation: run code against tests, compare outputs token-wise."""


def compare_output(expected, actual):
    """Codeforces-style tolerant compare: token-wise, whitespace-insensitive."""
    et = (expected or "").split()
    at = (actual or "").split()
    if len(et) != len(at):
        return False
    for e, a in zip(et, at):
        if e == a:
            continue
        try:  # float tolerance 1e-6 when both parse as numbers
            if abs(float(e) - float(a)) <= 1e-6 * max(1.0, abs(float(e))):
                continue
        except ValueError:
            pass
        return False
    return True


def _clip(s, n=4000):
    s = s or ""
    return s if len(s) <= n else s[:n] + "\n...[truncated]"


def run_tests(executor, problem, language, code, tests):
    """tests: [{input, expected?}] -> {verdict, passed, total, results:[...]}.

    Stops early on compile error; runs all tests otherwise.
    """
    results = []
    passed = 0
    overall = "OK"
    for i, t in enumerate(tests):
        r = executor.run(language, code, stdin=t.get("input", ""),
                         time_limit_ms=problem.get("time_limit_ms", 2000))
        if r.error:
            results.append({"i": i, "verdict": "JUDGE_ERROR", "message": r.error})
            overall = "JUDGE_ERROR"
            break
        if r.compile_code:
            results.append({"i": i, "verdict": "CE", "message": _clip(r.compile_output)})
            overall = "CE"
            break
        if r.signal == "SIGKILL":
            v = "TLE"
        elif r.exit_code != 0:
            v = "RE"
        else:
            expected = t.get("expected")
            if expected is None or expected == "":
                v = "RUN"  # no expected output: just show what the code printed
            else:
                v = "OK" if compare_output(expected, r.stdout) else "WA"
        if v in ("OK", "RUN"):
            passed += 1
        entry = {
            "i": i, "verdict": v,
            "input": _clip(t.get("input", ""), 1500),
            "expected": _clip(t.get("expected", "") or "", 1500),
            "stdout": _clip(r.stdout, 1500),
            "stderr": _clip(r.stderr, 1000),
            "time_ms": r.time_ms,
        }
        results.append(entry)
        if v not in ("OK", "RUN") and overall == "OK":
            overall = v
    total = len(tests)
    if overall == "OK" and passed < total:
        overall = "WA"
    return {"verdict": overall, "passed": passed, "total": total, "results": results}
