"""AI features over any OpenAI-compatible API (OpenRouter, Groq, NVIDIA NIM,
DeepSeek, Ollama, ...). Configured entirely by env:

  AI_BASE_URL  default https://openrouter.ai/api/v1
  AI_API_KEY   your key (free keys: openrouter.ai, console.groq.com, build.nvidia.com)
  AI_MODEL     default nvidia/nemotron-3-ultra-550b-a55b:free
  AI_MOCK=1    canned offline responses (used by the test suite)

Every feature sends the full context bundle: statement, constraints, current
code, compiler output, failing tests — never the code alone.
"""
import json
import os
import re
import urllib.error
import urllib.request

DEFAULT_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

HINT_LEVELS = {
    1: "a tiny nudge (one sentence, no algorithm names, no spoilers)",
    2: "the key idea or observation (2-3 sentences, still no full algorithm)",
    3: "the algorithm to use and why it fits the constraints",
    4: "step-by-step pseudocode",
    5: "a complete, correct solution with explanation",
}


class AIError(Exception):
    pass


def is_configured():
    return bool(os.environ.get("AI_API_KEY")) or os.environ.get("AI_MOCK") == "1"


def chat(messages, temperature=0.4, max_tokens=3000):
    if os.environ.get("AI_MOCK") == "1":
        return _mock_reply(messages)
    key = os.environ.get("AI_API_KEY")
    if not key:
        raise AIError("AI is not configured. Set AI_API_KEY (free keys: https://openrouter.ai/keys or https://console.groq.com/keys) and restart.")
    base = os.environ.get("AI_BASE_URL", DEFAULT_BASE).rstrip("/")
    model = os.environ.get("AI_MODEL", DEFAULT_MODEL)
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
            "HTTP-Referer": "https://github.com/cf-studio",
            "X-Title": "CF Studio",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise AIError("AI provider HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:400]))
    except Exception as e:
        raise AIError("AI provider unreachable: %s" % e)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise AIError("unexpected AI response: %s" % json.dumps(data)[:400])
    # reasoning models may inline their thinking; keep only the final answer
    return re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()


def _balanced_parse(text, start):
    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


def extract_json(text):
    """Pull the first JSON array/object (in text order) out of a model reply.
    Handles ``` fences and surrounding prose; prefers structures over scalars."""
    text = re.sub(r"```(?:json)?", "", text or "")
    results = []
    for m in re.finditer(r"[\[{]", text):
        parsed = _balanced_parse(text, m.start())
        if parsed is not None:
            results.append(parsed)
    if not results:
        raise AIError("model reply contained no valid JSON")
    for r in results:  # prefer a dict, or a list of dicts, over stray scalars
        if isinstance(r, dict) or (isinstance(r, list) and r and all(isinstance(x, dict) for x in r)):
            return r
    return results[0]


def _html_to_text(html):
    t = re.sub(r"<br\s*/?>", "\n", html or "")
    t = re.sub(r"</(p|div|li)>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def build_context(problem, code=None, language=None, last_run=None, ai_tests=None):
    """The full context bundle every AI feature receives."""
    p = problem
    parts = [
        "## Problem: %s" % p.get("title", ""),
        "Time limit: %s ms | Memory limit: %s MB | Rating: %s | Tags: %s"
        % (p.get("time_limit_ms"), p.get("memory_limit_mb"), p.get("rating") or "?",
           ", ".join(p.get("tags") or []) or "-"),
        "### Statement\n" + _html_to_text(p.get("statement_html", "")),
        "### Input\n" + _html_to_text(p.get("input_spec_html", "")),
        "### Output\n" + _html_to_text(p.get("output_spec_html", "")),
    ]
    samples = p.get("samples") or []
    if samples:
        s = "\n\n".join("Sample %d\nInput:\n%s\nOutput:\n%s" % (i + 1, x["input"], x["output"])
                        for i, x in enumerate(samples))
        parts.append("### Samples\n" + s)
    if p.get("note_html"):
        parts.append("### Note\n" + _html_to_text(p["note_html"]))
    if code:
        parts.append("### User's current code (%s)\n```\n%s\n```" % (language or "?", code[:12000]))
    if last_run:
        parts.append("### Latest run results\n" + json.dumps(last_run, indent=1)[:4000])
    if ai_tests:
        parts.append("### Existing generated tests\n" + json.dumps(ai_tests, indent=1)[:2000])
    return "\n\n".join(parts)


SYSTEM = ("You are the AI assistant inside CF Studio, a competitive programming workspace. "
          "Be precise and concise. Use the provided problem context; do not invent constraints. "
          "When asked for code, produce complete compilable code.")


def ask(context, instruction, temperature=0.4, max_tokens=3000, history=None):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": context + "\n\n---\n\n" + instruction}]
    if history:
        msgs = [{"role": "system", "content": SYSTEM + "\n\nContext:\n" + context}] + history
    return chat(msgs, temperature=temperature, max_tokens=max_tokens)


# ---------------- feature prompts ----------------

def generate_tests(problem, code=None, language=None, count=12):
    ctx = build_context(problem, code, language)
    instruction = (
        "Generate %d diverse hidden test cases for this problem: boundary/minimum values, maximum "
        "constraint sizes (keep inputs under 20 lines by using patterns only if the format allows, "
        "otherwise moderate sizes), corner cases, duplicates, negatives if allowed, adversarial/hack-style cases, "
        "and cases that break common wrong approaches (overflow, off-by-one, greedy failures). "
        "Respect the input format EXACTLY. Reply with ONLY a JSON array like: "
        '[{"input": "...", "expected": "...", "reason": "..."}] '
        "where expected is your best computation of the correct output. If you cannot be certain of an "
        "expected output, still include the test with your best attempt." % count
    )
    reply = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": ctx + "\n\n" + instruction}],
                 temperature=0.7, max_tokens=4000)
    tests = extract_json(reply)
    out = []
    for t in tests if isinstance(tests, list) else []:
        if isinstance(t, dict) and t.get("input"):
            out.append({"input": str(t["input"]).strip() + "\n",
                        "expected": str(t.get("expected", "")).strip(),
                        "reason": str(t.get("reason", ""))[:300]})
    if not out:
        raise AIError("model returned no usable tests")
    return out


def find_bug(problem, code, language, last_run):
    ctx = build_context(problem, code, language, last_run)
    return ask(ctx, "The code fails (see run results). Identify the bug: which input fails, why, and where "
                    "in the code (quote the line). Then give a minimal suggested fix. "
                    "Format: **Failing case** / **Why it fails** / **Where** / **Fix**.")


def complexity(problem, code, language):
    ctx = build_context(problem, code, language)
    return ask(ctx, "Estimate this code's time and space complexity. Given the constraints, state the roughly "
                    "required complexity, whether this code risks TLE (and at what n), and memory risk vs the limit. "
                    "Format: **Time** / **Space** / **Required** / **TLE risk** / **Memory risk**.")


def hint(problem, level, code=None, language=None):
    lvl = max(1, min(5, int(level)))
    ctx = build_context(problem, code, language)
    return ask(ctx, "Give hint level %d of 5: %s. Do not reveal more than this level allows." % (lvl, HINT_LEVELS[lvl]),
               temperature=0.5)


def explain(problem, audience):
    ctx = build_context(problem)
    return ask(ctx, "Explain what this problem is actually asking, for this audience: %s. "
                    "Do not give the solution approach." % audience)


def brute_force(problem):
    ctx = build_context(problem)
    reply = ask(ctx, "Write a CORRECT brute-force solution in Python 3 (clarity over speed; assume small inputs). "
                     "Read from stdin, write to stdout. Reply with ONLY the code in a single ``` block.")
    return _extract_code(reply)


def input_generator(problem, max_n=None):
    ctx = build_context(problem)
    size_note = " Keep sizes small (n <= %s) so brute force stays fast." % (max_n or 8)
    reply = ask(ctx, "Write a Python 3 RANDOM INPUT GENERATOR for this problem. It receives a seed as its first "
                     "command line argument (sys.argv[1]); use random.seed(that). Print ONLY a valid input for the "
                     "problem, matching the input format exactly." + size_note +
                     " Reply with ONLY the code in a single ``` block.")
    return _extract_code(reply)


def _extract_code(reply):
    m = re.search(r"```[a-zA-Z0-9+]*\n(.*?)```", reply or "", re.DOTALL)
    code = (m.group(1) if m else reply or "").strip()
    if not code:
        raise AIError("model returned no code")
    return code


# ---------------- offline mock (test suite) ----------------

def _mock_reply(messages):
    last = messages[-1]["content"] if messages else ""
    if "JSON array" in last and "test cases" in last:
        return json.dumps([
            {"input": "1\n", "expected": "", "reason": "minimum n"},
            {"input": "1000000000000000000\n", "expected": "", "reason": "maximum n, 64-bit"},
            {"input": "7\n", "expected": "", "reason": "odd value"},
        ])
    if "INPUT GENERATOR" in last:
        return "```python\nimport random, sys\nrandom.seed(sys.argv[1])\nprint(random.randint(1, 20))\n```"
    if "brute-force" in last:
        return "```python\nn = int(input())\nprint('YES' if n % 2 == 0 else 'NO')\n```"
    if "hint level" in last:
        return "Mock hint: think about parity."
    if "time and space complexity" in last:
        return "**Time** O(1) / **Space** O(1) / **Required** O(1) / **TLE risk** none / **Memory risk** none"
    if "Identify the bug" in last:
        return "**Failing case** n=1 **Why it fails** ... **Where** line 1 **Fix** handle odd n."
    return "Mock AI reply."
