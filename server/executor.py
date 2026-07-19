"""Code execution backends with automatic failover (EXECUTOR=auto, default).

The public Piston API went whitelist-only in Feb 2026, so the chain is:

  1. Piston   — only when PISTON_URL is set (self-hosted or whitelisted)
  2. Wandbox  — free public compile/run API, no key (wandbox.org)
  3. Local    — your own toolchain via subprocess (python always; g++ if present)

A backend is only skipped on infrastructure errors (unreachable, HTTP error);
a compile error / wrong answer is a real result and never triggers failover.
Set EXECUTOR=piston|wandbox|local to pin a single backend.
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

PISTON_PUBLIC = "https://emkc.org/api/v2/piston"

# language key -> (piston language, piston fallback version, filename)
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

# language key -> (wandbox compiler, raw compiler options)  [verified Jul 2026]
WANDBOX_COMPILERS = {
    "cpp": ("gcc-13.2.0", "-O2\n-std=c++17"),
    "python": ("cpython-3.13.8", ""),
    "javascript": ("nodejs-20.17.0", ""),
    "rust": ("rust-1.82.0", ""),
    "go": ("go-1.23.2", ""),
    "java": ("openjdk-jdk-22+36", ""),
}


class ExecResult:
    def __init__(self, compile_output="", compile_code=0, stdout="", stderr="",
                 exit_code=0, signal=None, time_ms=None, error=None, backend=None):
        self.compile_output = compile_output
        self.compile_code = compile_code
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.signal = signal
        self.time_ms = time_ms
        self.error = error  # infrastructure error (network etc.), not user-code error
        self.backend = backend

    def to_dict(self):
        return {
            "compile_output": self.compile_output, "compile_code": self.compile_code,
            "stdout": self.stdout, "stderr": self.stderr, "exit_code": self.exit_code,
            "signal": self.signal, "time_ms": self.time_ms, "error": self.error,
            "backend": self.backend,
        }


def _post_json(url, payload, timeout=60, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=dict({"Content-Type": "application/json",
                                               "User-Agent": "cf-studio"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class _Throttled:
    def __init__(self, min_interval):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            delta = self._last + self.min_interval - time.time()
            if delta > 0:
                time.sleep(delta)
            self._last = time.time()


class PistonExecutor:
    name = "piston"

    def __init__(self, base_url=None):
        self.base_url = (base_url or os.environ.get("PISTON_URL") or PISTON_PUBLIC).rstrip("/")
        self._versions = {}
        self._throttle = _Throttled(float(os.environ.get("PISTON_MIN_INTERVAL", "0.25")))

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
            return ExecResult(error="unsupported language: %s" % language, backend=self.name)
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
        for attempt in range(2):
            self._throttle.wait()
            try:
                data = _post_json(self.base_url + "/execute", payload, timeout=40)
                comp = data.get("compile") or {}
                run = data.get("run") or {}
                return ExecResult(
                    compile_output=(comp.get("stdout", "") + comp.get("stderr", "")).strip(),
                    compile_code=comp.get("code") or 0,
                    stdout=run.get("stdout", ""),
                    stderr=run.get("stderr", ""),
                    exit_code=run.get("code") if run.get("code") is not None else 0,
                    signal=run.get("signal"), backend=self.name)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    time.sleep(1.5)
                    continue
                return ExecResult(error="piston HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:300]),
                                  backend=self.name)
            except Exception as e:
                return ExecResult(error="piston unreachable: %s" % e, backend=self.name)
        return ExecResult(error="piston unreachable", backend=self.name)


class WandboxExecutor:
    """Free public https://wandbox.org — no key. ~30s hard run limit upstream."""
    name = "wandbox"

    def __init__(self, base_url=None):
        self.base_url = (base_url or os.environ.get("WANDBOX_URL") or "https://wandbox.org").rstrip("/")
        self._throttle = _Throttled(float(os.environ.get("WANDBOX_MIN_INTERVAL", "0.5")))

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        if language not in WANDBOX_COMPILERS:
            return ExecResult(error="wandbox: unsupported language %s" % language, backend=self.name)
        compiler, raw_opts = WANDBOX_COMPILERS[language]
        payload = {"compiler": compiler, "code": code, "stdin": stdin or "",
                   "options": "", "compiler-option-raw": raw_opts}
        if args:
            payload["runtime-option-raw"] = "\n".join(str(a) for a in args)
        self._throttle.wait()
        try:
            data = _post_json(self.base_url + "/api/compile.json", payload, timeout=60)
        except urllib.error.HTTPError as e:
            return ExecResult(error="wandbox HTTP %d: %s" % (e.code, e.read().decode(errors="replace")[:300]),
                              backend=self.name)
        except Exception as e:
            return ExecResult(error="wandbox unreachable: %s" % e, backend=self.name)
        compiler_err = (data.get("compiler_error") or "") + (data.get("compiler_output") or "")
        program_ran = ("program_message" in data) or ("program_output" in data) or ("program_error" in data)
        status = str(data.get("status", ""))
        signal = data.get("signal") or None
        if compiler_err.strip() and not (data.get("program_output") or data.get("program_error")) and status != "0":
            return ExecResult(compile_output=compiler_err.strip()[:4000], compile_code=1, backend=self.name)
        if signal and "kill" in signal.lower():
            signal = "SIGKILL"  # upstream time/memory kill -> treated as TLE by the judge
        try:
            exit_code = int(status) if status not in ("", None) else 0
        except ValueError:
            exit_code = 1
        if not program_ran and status == "":
            return ExecResult(error="wandbox: empty response", backend=self.name)
        return ExecResult(stdout=data.get("program_output", ""),
                          stderr=(data.get("program_error", "") or "")[:4000],
                          exit_code=exit_code, signal=signal, backend=self.name)


class LocalExecutor:
    """python always; cpp when g++ is available. Unsandboxed — own machine only."""
    name = "local"

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
                    return ExecResult(compile_output=cp.stderr[-4000:], compile_code=cp.returncode, backend=self.name)
                cmd = [binp] + list(args or [])
            else:
                return ExecResult(error="local executor supports python (and cpp with g++); got %s" % language,
                                  backend=self.name)
            start = time.time()
            try:
                p = subprocess.run(cmd, input=stdin or "", capture_output=True, text=True,
                                   timeout=time_limit_ms / 1000.0, cwd=tmp)
                return ExecResult(stdout=p.stdout, stderr=p.stderr[-4000:], exit_code=p.returncode,
                                  time_ms=int((time.time() - start) * 1000), backend=self.name)
            except subprocess.TimeoutExpired:
                return ExecResult(signal="SIGKILL", time_ms=int(time_limit_ms), backend=self.name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AutoExecutor:
    """Failover chain. Infra errors advance to the next backend; real verdicts don't."""
    name = "auto"
    COOLDOWN = 120

    def __init__(self, backends=None):
        if backends is None:
            backends = []
            if os.environ.get("PISTON_URL"):  # public Piston is whitelist-only now
                backends.append(PistonExecutor())
            backends.append(WandboxExecutor())
            backends.append(LocalExecutor())
        self.backends = backends
        self._cooldown = {}

    def run(self, language, code, stdin="", args=None, time_limit_ms=5000):
        now = time.time()
        ordered = [b for b in self.backends if self._cooldown.get(b.name, 0) <= now] + \
                  [b for b in self.backends if self._cooldown.get(b.name, 0) > now]
        errors = []
        for b in ordered:
            res = b.run(language, code, stdin=stdin, args=args, time_limit_ms=time_limit_ms)
            if res.error is None:
                self._cooldown.pop(b.name, None)
                return res
            self._cooldown[b.name] = time.time() + self.COOLDOWN
            errors.append("%s: %s" % (b.name, res.error))
        return ExecResult(error="all judges failed — " + " | ".join(errors)[:600], backend=self.name)


def get_executor():
    kind = os.environ.get("EXECUTOR", "auto").lower()
    if kind == "local":
        return LocalExecutor()
    if kind == "piston":
        return PistonExecutor()
    if kind == "wandbox":
        return WandboxExecutor()
    return AutoExecutor()
