#!/usr/bin/env python3
"""CF Studio — AI-first competitive programming workspace.

Run:  python main.py            (then open http://localhost:8000)
Env:  see .env.example / README.md
"""
import argparse
import os
import sys

if sys.version_info < (3, 8):
    sys.exit("CF Studio needs Python 3.8+")

# Load .env if present (no dependency needed)
def _load_env(path=".env"):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if not os.path.exists(p):
        return
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    _load_env()
    ap = argparse.ArgumentParser(description="CF Studio server")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    args = ap.parse_args()

    from server.app import create_server
    from server import ai

    srv, seeded = create_server(port=args.port, host=args.host)
    print("=" * 56)
    print("  CF Studio  ->  http://%s:%d" % ("localhost" if args.host in ("0.0.0.0", "127.0.0.1") else args.host, args.port))
    if seeded:
        print("  Seeded %d demo problems." % seeded)
    ex = os.environ.get("EXECUTOR", "auto")
    if ex == "auto":
        chain = (["piston"] if os.environ.get("PISTON_URL") else []) + ["wandbox", "local"]
        print("  Judge   : auto (%s)" % " -> ".join(chain))
    else:
        print("  Judge   : %s" % ex)
    provs = ai.providers()
    print("  AI      : %s" % (" -> ".join("%s (%s)" % (p["name"], p["model"]) for p in provs)
                              if provs else "NOT configured — put keys in .env (free: openrouter.ai/keys, console.groq.com/keys, build.nvidia.com)"))
    print("  Ctrl+C to stop.")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
