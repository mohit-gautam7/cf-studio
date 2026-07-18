"""Code execution backends.

- PistonExecutor: free public Piston API (default), or any self-hosted Piston
  via PISTON_URL. No key required.
- LocalExecutor: runs code with the local toolchain via subprocess. Used for
  the test suite and available for advanced users (EXECUTOR=local). Runs code
  unsandboxed — only use it for your own code.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

PISTON_URL = os.environ.get("PISTON_URL", "https://emkc.org/api/v2/piston")

# language key -> (piston language, fallback version, filename)
LANGUAGES = {
    "cpp": ("c++", "10.2.0", "main.cpp"),
    "python": ("python", "3.10.0", "main.py"),
    "java": ("java", "15.0.2", "Main.java"),
    "javascript": ("javascript", "18.15.0", "main.js"),
    "rust": ("rust", "1.68.2", "main.rs"),
    "go": ("go", "1.16.2", "main.go"),
    "kotlin": ("kotlin", "1.8.20", "Main.kt"),
    "csharp": ("csharp", "6.12.0", "Main.cs"),
}


class ExecResult:
    def __init__(self, compile_output="", compile_code=0, stdout="", stderr="",
                 exit_code=0, signal=None, time_ms=None, error=None):
        self.compile_output = compile_output
        self.compile_code = compile_code
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.signal = signal
        self.time_ms = time_ms
        self.error = error  # infrastructure error (network etc.), not user-code error

    def to_dict(self):
        return {
            "compile_output": self.compile_output, "compile_code": self.compile_code,
            "stdout": self.stdout, "stderr": self.stderr, "exit_code": self.exit_code,
            "signal": self.signal, "time_ms": self.time_ms, "error": self.error,
        }


class PistonExecutor:
    def __init__(self, base_url=None):
        self.base_url = (base_url or PISTON_URL).rstrip("/")
        self._versions = {}
        self._lock = threading.Lock()
        self._last_call = 0.0
        self.min_interval = float(os.environ.get("PISTON_MIN_INTERVAL", "0.25"))

    def _throttle(self):
        with self._lock:
            wait = self._last_call + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _resolve_version(self, piston_lang, fallback):
        if self._versions:
            return self._versions.get(piston_lang, fallback)
        try:
            req = urllib.request.Request(self.base_url + "/runtimes", headers={"User-Agent": "cf-studio"})
            with urllib.request.urlopen(req, timeout=10) as r:
                for rt in json.loads(r.read().decode()):
                    self._versions.setdefault(rt["language"], rt["version"])
                    for alias in rt.get("aliases", []):
                        self._versions.setdefault(alias, rt["version"])
        except Exception:
            pass
        return self._versions.get(piston_lang, fallback)

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        if language not in LANGUAGES:
            return ExecResult(error="unsupported language: %s" % language)
        piston_lang, fallback, filename = LANGUAGES[language]
        payload = {
            "language": piston_lang,
            "version": self._resolve_version(piston_lang, fallback),
            "files": [{"name": filename, "content": code}],
            "stdin": stdin or "",
            "args": args or [],
            "compile_timeout": 15000,
            "run_timeout": max(1000, min(int(time_limit_ms) + 500, 20000)),
        }
        body = json.dumps(payload).encode()
        for attempt in range(3):
            self._throttle()
            try:
                req = urllib.request.Request(
                    self.base_url + "/execute", data=body,
                    headers={"Content-Type": "application/json", "User-Agent": "cf-studio"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = json.loads(r.read().decode())
                comp = data.get("compile") or {}
                run = data.get("run") or {}
                return ExecResult(
                    compile_output=(comp.get("stdout", "") + comp.get("stderr", "")).strip(),
                    compile_code=comp.get("code") or 0,
                    stdout=run.get("stdout", ""),
                    stderr=run.get("stderr", ""),
                    exit_code=run.get("code") if run.get("code") is not None else 0,
                    signal=run.get("signal"),
                )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return ExecResult(error="judge HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:300]))
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.0)
                    continue
                return ExecResult(error="judge unreachable: %s" % e)
        return ExecResult(error="judge unreachable")


class LocalExecutor:
    """python always; cpp when g++ is available. Unsandboxed — own machine only."""

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        tmp = tempfile.mkdtemp(prefix="cfstudio_")
        try:
            if language == "python":
                path = os.path.join(tmp, "main.py")
                with open(path, "w") as f:
                    f.write(code)
                cmd = [sys.executable, path] + list(args or [])
            elif language == "cpp" and shutil.which("g++"):
                src, binp = os.path.join(tmp, "main.cpp"), os.path.join(tmp, "main.bin")
                with open(src, "w") as f:
                    f.write(code)
                cp = subprocess.run(["g++", "-O2", "-std=c++17", "-o", binp, src],
                                    capture_output=True, text=True, timeout=30)
                if cp.returncode != 0:
                    return ExecResult(compile_output=cp.stderr[-4000:], compile_code=cp.returncode)
                cmd = [binp] + list(args or [])
            else:
                return ExecResult(error="local executor supports python (and cpp with g++); got %s" % language)
            start = time.time()
            try:
                p = subprocess.run(cmd, input=stdin or "", capture_output=True, text=True,
                                   timeout=time_limit_ms / 1000.0, cwd=tmp)
                return ExecResult(stdout=p.stdout, stderr=p.stderr[-4000:], exit_code=p.returncode,
                                  time_ms=int((time.time() - start) * 1000))
            except subprocess.TimeoutExpired:
                return ExecResult(signal="SIGKILL", time_ms=int(time_limit_ms))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def get_executor():
    kind = os.environ.get("EXECUTOR", "piston").lower()
    if kind == "local":
        return LocalExecutor()
    return PistonExecutor()
