"""Verdict computation. The first test runs alone (cheap compile-error probe),
the rest run in parallel worker threads — remote judges are network-bound, so
this cuts a full run from N round trips to roughly N/3."""
import concurrent.futures

MAX_WORKERS = 3


def compare_output(expected, actual):
    """Codeforces-style tolerant compare: token-wise, whitespace-insensitive,
    CASE-insensitive (CF accepts "yEs"/"YES"/"no" interchangeably), with 1e-6
    relative tolerance for numeric tokens."""
    et = (expected or "").split()
    at = (actual or "").split()
    if len(et) != len(at):
        return False
    for e, a in zip(et, at):
        if e == a or e.lower() == a.lower():
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


def _run_one(executor, problem, language, code, t, i):
    r = executor.run(language, code, stdin=t.get("input", ""),
                     time_limit_ms=problem.get("time_limit_ms", 2000))
    if r.error:
        return {"i": i, "verdict": "JUDGE_ERROR", "message": r.error}
    if r.compile_code:
        return {"i": i, "verdict": "CE", "message": _clip(r.compile_output)}
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
    return {"i": i, "verdict": v,
            "input": _clip(t.get("input", ""), 1500),
            "expected": _clip(t.get("expected", "") or "", 1500),
            "stdout": _clip(r.stdout, 1500),
            "stderr": _clip(r.stderr, 1000),
            "time_ms": r.time_ms}


def _summarize(results, total):
    passed = sum(1 for r in results if r["verdict"] in ("OK", "RUN"))
    overall = "OK"
    for r in results:
        if r["verdict"] == "JUDGE_ERROR":
            overall = "JUDGE_ERROR"
            break
        if r["verdict"] not in ("OK", "RUN") and overall == "OK":
            overall = r["verdict"]
    if overall == "OK" and passed < total:
        overall = "WA"
    return {"verdict": overall, "passed": passed, "total": total, "results": results}


def run_tests(executor, problem, language, code, tests):
    """tests: [{input, expected?}] -> {verdict, passed, total, results:[...]}."""
    if not tests:
        return {"verdict": "OK", "passed": 0, "total": 0, "results": []}
    first = _run_one(executor, problem, language, code, tests[0], 0)
    if first["verdict"] in ("CE", "JUDGE_ERROR"):
        return _summarize([first], len(tests))
    results = {0: first}
    rest = list(enumerate(tests))[1:]
    if rest:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(_run_one, executor, problem, language, code, t, i) for i, t in rest]
            for f in concurrent.futures.as_completed(futures):
                r = f.result()
                results[r["i"]] = r
    ordered = [results[i] for i in range(len(tests))]
    return _summarize(ordered, len(tests))
