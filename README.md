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

Add **any or all** of these free keys to `.env` — CF Studio always tries the strongest model first and automatically falls back to the next provider on any error (rate limit, retired model, outage):

```
OPENROUTER_API_KEY=sk-or-v1-...     # https://openrouter.ai/keys
GROQ_API_KEY=gsk_...                # https://console.groq.com/keys
NVIDIA_API_KEY=nvapi-...            # https://build.nvidia.com
```

Failover order (verified July 2026, all $0):

| Priority | Provider | Default model | Context |
|---|---|---|---|
| 1 | OpenRouter | `nvidia/nemotron-3-ultra-550b-a55b:free` — 550B frontier reasoning | 1M tokens |
| 2 | NVIDIA NIM | `nvidia/nemotron-3-ultra-550b-a55b` (same model, direct) | 1M tokens |
| 3 | Groq | `openai/gpt-oss-120b` — fastest (~500 tps) | 131K tokens |

Override any default with `OPENROUTER_MODEL` / `NVIDIA_MODEL` / `GROQ_MODEL`. A local Ollama (`AI_BASE_URL=http://localhost:11434/v1`, no key) is used first when set. A plain `AI_API_KEY` still works as the OpenRouter key. Free model names rotate over time — if a provider errors, the chain skips it; update the model name when convenient.

## What's inside

**LeetCode-style problem workspace** — statement with rendered LaTeX on the left; Monaco editor (C++, Python, Java, JS, Rust, Go, Kotlin, C#; themes; autosave) on the right; test panel below.

**Judge** — run against sample tests (verdicts: OK / WA / TLE / RE / CE), your own custom tests, or AI-generated tests. No compiler needed: execution uses a free-judge failover chain (`EXECUTOR=auto`): self-hosted Piston if you set `PISTON_URL` → the free public [Wandbox](https://wandbox.org) API → your local toolchain. (The public Piston API went whitelist-only in Feb 2026, so Wandbox is the default free path.)

**AI panel** (sees the full context: statement, constraints, your code, latest run results — never code alone):

- 💬 Chat about the problem or your approach
- 📖 Explain the problem
- 💡 Progressive hints, 5 levels: nudge → idea → algorithm → pseudocode → full solution
- 🧪 Generate hidden tests (boundary, overflow, corner, hack-style) — then **validate** their expected outputs against a correct brute force
- 🐞 Find bug: which input fails, why, where, suggested fix
- ⏱ Complexity estimate vs. what the constraints demand

**Stress testing** — one click: an AI-written brute force + AI-written random input generator run against your solution until a mismatch is found; the failing case is shown and can be added to your custom tests. (Seeded problems use their built-in reference solutions as the brute force.)

**Practice tracking** — per-problem markdown+LaTeX notes, bookmarks with labels, local run history, Codeforces verdict import by handle, dashboard with daily streak, solved/attempted counts, weak-topic accuracy bars and your CF rating graph.

## Browser extension — "Open in CF Studio"

The `extension/` folder is a tiny Chrome/Brave/Edge extension that does two things:

- **⚡ Open in CF Studio** button on every Codeforces problem page — one click imports the problem and opens your workspace.
- **Submit autofill** — when you press 🚀 Submit on CF in the workspace, the Codeforces submit page opens with your problem, code and language already filled. You review and click Submit yourself (auto-submitting is against CF rules, so that final click is always yours).

Install: open `chrome://extensions` (or `brave://extensions`) → enable *Developer mode* → *Load unpacked* → select the `extension/` folder. After pulling updates, hit ↻ on the extension card.

**Sharing with a friend:** they clone this repo and run their own CF Studio (`python main.py`) plus load the same extension — it points at `http://localhost:8000`, i.e. *their* server and *their* AI keys. If instead you host one instance (see *Going live*), they just edit the `CF_STUDIO` constant at the top of `extension/content.js` to your public URL and register an account there — but then everyone shares your AI quota. The autofill part works for anyone with the extension, either way.

No-install alternative — save this as a bookmarklet:

```
javascript:location='http://localhost:8000/import?url='+encodeURIComponent(location.href)
```

## Importing Codeforces problems

Paste any `codeforces.com/problemset/problem/...` or `/contest/.../problem/...` URL. The statement, samples, limits, tags and rating are parsed and cached locally. Be polite: problems are fetched once and cached; CF Studio never hammers Codeforces.

**No automated submissions.** Submitting through scripts violates Codeforces rules. Instead, **🚀 Submit on CF** copies your code to the clipboard and opens that exact problem's Codeforces submit page — you pick the language, paste (Ctrl+V) and click submit yourself. Then import your verdicts by handle (public API, read-only).

## Configuration (.env)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` / `GROQ_API_KEY` / `NVIDIA_API_KEY` | — | add any or all; automatic failover |
| `OPENROUTER_MODEL` / `GROQ_MODEL` / `NVIDIA_MODEL` | best free models | per-provider model override |
| `AI_BASE_URL` + `AI_MODEL` (+`AI_API_KEY`) | — | custom/local provider (Ollama), tried first |
| `PISTON_URL` | public Piston | point at a self-hosted Piston for speed |
| `EXECUTOR` | `piston` | `local` runs code with your local toolchain — **unsandboxed, your own code only** |
| `PORT` / `HOST` | 8000 / 127.0.0.1 | server bind |

The public Piston API is rate-limited (~5 req/s). For heavy stress-testing, self-host Piston with Docker and set `PISTON_URL`, or use `EXECUTOR=local`.

## Tests

```bash
python -m unittest discover -s tests
```

48 tests: statement parser (fixture), verdict engine, AI JSON extraction, stress loop (real subprocess execution), and a full-stack HTTP e2e (register → run → generate tests → validate → stress → chat → dashboard).

## Going live (free)

CF Studio is local-first, but you can put it on a public URL in ~5 minutes with Render's free tier (the included `render.yaml` does the setup):

1. Go to [render.com](https://render.com) → sign in with GitHub.
2. **New → Blueprint** → pick your `cf-studio` repository → Render reads `render.yaml` automatically.
3. When prompted for environment variables, paste your `OPENROUTER_API_KEY` (and optionally `GROQ_API_KEY` / `NVIDIA_API_KEY`).
4. Deploy — you get a URL like `https://cf-studio.onrender.com`.

Free-tier caveats: the instance sleeps when idle (first visit takes ~1 min to wake), and the disk is ephemeral — accounts, notes and imported problems reset whenever it redeploys or restarts. Anyone with the URL can register and use *your* AI keys, so share it with friends, not the world. For serious daily use, local (`python main.py`) is faster and keeps your data.

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
