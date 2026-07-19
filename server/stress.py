"""Stress testing: user's solution vs a correct brute force on random inputs.

Brute force comes from the problem's stored reference solution when present,
otherwise the AI writes one. The AI always writes the input generator.
Iterations run in parallel batches (each iteration is three network-bound
executions: generator -> brute -> user), stopping at the first mismatch.
"""
import concurrent.futures

from . import ai
from .judge import compare_output

BATCH = 3


def _one_iteration(executor, problem, code, language, brute, brute_lang, gen, it, tl):
    g = executor.run("python", gen, args=[str(it)], time_limit_ms=8000)
    if g.error or g.exit_code != 0 or g.compile_code:
        return {"status": "generator_error", "iteration": it,
                "message": (g.error or g.stderr or g.compile_output or "generator failed")[:1200],
                "generator": gen}
    test_input = g.stdout
    if not test_input.strip():
        return {"status": "generator_error", "iteration": it,
                "message": "generator printed empty input", "generator": gen}

    b = executor.run(brute_lang, brute, stdin=test_input, time_limit_ms=15000)
    if b.error or b.compile_code or b.exit_code != 0 or b.signal:
        return {"status": "brute_error", "iteration": it,
                "message": (b.error or b.compile_output or b.stderr or "brute force failed")[:1200],
                "input": test_input[:2000], "brute": brute}

    u = executor.run(language, code, stdin=test_input, time_limit_ms=tl)
    if u.error:
        return {"status": "judge_error", "iteration": it, "message": u.error}
    if u.compile_code:
        return {"status": "compile_error", "iteration": it, "message": u.compile_output[:2000]}
    if u.signal == "SIGKILL":
        return {"status": "mismatch", "iteration": it, "kind": "TLE",
                "input": test_input[:2000], "expected": b.stdout[:2000], "got": "(time limit exceeded)"}
    if u.exit_code != 0:
        return {"status": "mismatch", "iteration": it, "kind": "RE",
                "input": test_input[:2000], "expected": b.stdout[:2000],
                "got": "(runtime error)\n" + (u.stderr or "")[:800]}
    if not compare_output(b.stdout, u.stdout):
        return {"status": "mismatch", "iteration": it, "kind": "WA",
                "input": test_input[:2000], "expected": b.stdout[:2000], "got": u.stdout[:2000]}
    return {"status": "ok", "iteration": it}


def run_stress(executor, problem, code, language, iterations=20, max_n=None):
    iterations = max(1, min(int(iterations or 20), 60))
    if problem.get("reference_solution"):
        brute, brute_lang = problem["reference_solution"], problem.get("reference_language", "python")
        brute_source = "reference"
    else:
        brute, brute_lang = ai.brute_force(problem), "python"
        brute_source = "ai"
    gen = ai.input_generator(problem, max_n=max_n)
    tl = max(4000, problem.get("time_limit_ms", 2000))

    for start in range(1, iterations + 1, BATCH):
        seeds = list(range(start, min(start + BATCH, iterations + 1)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH) as pool:
            outcomes = list(pool.map(
                lambda it: _one_iteration(executor, problem, code, language, brute, brute_lang, gen, it, tl),
                seeds))
        for out in outcomes:  # report the earliest problem in seed order
            if out["status"] != "ok":
                out["brute_source"] = brute_source
                return out
    return {"status": "passed", "iterations": iterations, "brute_source": brute_source}
