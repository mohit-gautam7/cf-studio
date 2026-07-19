# ⚡ CF Studio

**An AI-first competitive programming workspace for Codeforces.** One place to read, code, test, stress-test, debug and learn — then copy your code and submit on Codeforces.

Replaces this stack: `Codeforces + VS Code + ChatGPT + custom test generator + stress-testing scripts + local compiler`.

**Zero dependencies.** Backend is pure Python standard library, frontend is static HTML/JS (Monaco + KaTeX from CDN). Judging runs on the free public [Piston](https://github.com/engineer-man/piston) API, AI runs on any free OpenAI-compatible provider.

## Quick start

Requirements: Python 3.8+ and an internet connection. Nothing to install.

```bash
git clone <your-repo-url> && cd cf-studio
copy .env.example .env     # Windows   (mac/linux: cp .env.example .env)
# put your free AI key into .env (see below) — optional but recommended
python main.py             # Windows may prefer: py main.py
```

Open **http://localhost:8000**, register an account (stored locally in SQLite) and you're in. Four demo problems are pre-seeded; import any real Codeforces problem by pasting its URL.

## Free AI setup (2 minutes)

Grab a free key from **[openrouter.ai/keys](https://openrouter.ai/keys)** and put it in `.env`:

```
AI_API_KEY=sk-or-v1-...
```

That's it — the default model (`nvidia/nemotron-3-ultra-550b-a55b:free`, a 550B frontier-reasoning model, $0 on OpenRouter) is already set. Any OpenAI-compatible provider works:

| Provider | AI_BASE_URL | Example model (free tier, verified Jul 2026) |
|---|---|---|
| OpenRouter (default) | `https://openrouter.ai/api/v1` | `nvidia/nemotron-3-ultra-550b-a55b:free` (best), `nvidia/nemotron-3-super-120b-a12b:free` (faster), `google/gemma-4-31b-it:free` |
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` |
| NVIDIA NIM | `https://integrate.api.nvidia.com/v1` | key at build.nvidia.com; model id from the model page |
| Ollama (fully local) | `http://localhost:11434/v1` | `qwen2.5-coder` — no key needed |

Free model names change over time — check your provider's list and set `AI_MODEL` accordingly.

## What's inside

**LeetCode-style problem workspace** — statement with rendered LaTeX on the left; Monaco editor (C++, Python, Java, JS, Rust, Go, Kotlin, C#; themes; autosave) on the right; test panel below.

**Judge** — run against sample tests (verdicts: OK / WA / TLE / RE / CE), your own custom tests, or AI-generated tests. Executed via Piston's free public API — no compiler needed on your machine.

**AI panel** (sees the full context: statement, constraints, your code, latest run results — never code alone):

- 💬 Chat about the problem or your approach
- 📖 Explain the problem
- 💡 Progressive hints, 5 levels: nudge → idea → algorithm → pseudocode → full solution
- 🧪 Generate hidden tests (boundary, overflow, corner, hack-style) — then **validate** their expected outputs against a correct brute force
- 🐞 Find bug: which input fails, why, where, suggested fix
- ⏱ Complexity estimate vs. what the constraints demand

**Stress testing** — one click: an AI-written brute force + AI-written random input generator run against your solution until a mismatch is found; the failing case is shown and can be added to your custom tests. (Seeded problems use their built-in reference solutions as the brute force.)

**Practice tracking** — per-problem markdown+LaTeX notes, bookmarks with labels, local run history, Codeforces verdict import by handle, dashboard with daily streak, solved/attempted counts, weak-topic accuracy bars and your CF rating graph.

## Importing Codeforces problems

Paste any `codeforces.com/problemset/problem/...` or `/contest/.../problem/...` URL. The statement, samples, limits, tags and rating are parsed and cached locally. Be polite: problems are fetched once and cached; CF Studio never hammers Codeforces.

**No automated submissions.** Submitting through scripts violates Codeforces rules, so the flow is: 📋 Copy code → submit on Codeforces yourself → import your verdicts by handle (public API, read-only).

## Configuration (.env)

| Variable | Default | Purpose |
|---|---|---|
| `AI_API_KEY` | — | key for your AI provider |
| `AI_BASE_URL` | OpenRouter | any OpenAI-compatible endpoint |
| `AI_MODEL` | Nemotron 3 Ultra (free) | model name at that provider |
| `PISTON_URL` | public Piston | point at a self-hosted Piston for speed |
| `EXECUTOR` | `piston` | `local` runs code with your local toolchain — **unsandboxed, your own code only** |
| `PORT` / `HOST` | 8000 / 127.0.0.1 | server bind |

The public Piston API is rate-limited (~5 req/s). For heavy stress-testing, self-host Piston with Docker and set `PISTON_URL`, or use `EXECUTOR=local`.

## Tests

```bash
python -m unittest discover -s tests
```

48 tests: statement parser (fixture), verdict engine, AI JSON extraction, stress loop (real subprocess execution), and a full-stack HTTP e2e (register → run → generate tests → validate → stress → chat → dashboard).

## Deploying (optional)

CF Studio is local-first. A `render.yaml` is included for a free Render.com web service (note: free-tier disk is ephemeral — your SQLite data resets on redeploys; fine for demos, keep real practice data local).

## Architecture

```
main.py                 entry point (.env loader, banner)
server/
  app.py                stdlib HTTP server + API router (~30 endpoints)
  db.py     schema      SQLite (users, problems, runs, ai_tests, notes,
                        bookmarks, cf_verdicts, ai_chats)
  auth.py               PBKDF2 passwords, HMAC session tokens
  cfparse.py            Codeforces HTML parser (stdlib html.parser DOM)
  cfimport.py           CF problem import + verdict/rating API
  executor.py           Piston client / local subprocess runner
  judge.py              verdict computation (token compare, float tolerance)
  ai.py                 provider-agnostic AI client + feature prompts
  stress.py             brute-force comparison loop
  seed.py               4 original demo problems
static/                 dashboard, problem list, workspace (Monaco, KaTeX, marked via CDN)
tests/                  unit + e2e suite
```

Want the full Next.js + FastAPI + Judge0 version? `cf-studio-fable5-prompt.md` (one folder up) is a ready-to-run Claude prompt that rebuilds this product on that stack, feature-parity and beyond.

## License

MIT — see [LICENSE](LICENSE).
