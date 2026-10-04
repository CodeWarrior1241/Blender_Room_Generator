"""Find Blender and run ``room_gen/blender/entry.py`` headless."""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ENTRY = Path(__file__).resolve().parent / "blender" / "entry.py"
RESULT_PREFIX = "ROOM_GEN_RESULT "


class BlenderError(RuntimeError):
    def __init__(self, message: str, log_tail: str = "", result: dict | None = None):
        super().__init__(message)
        self.log_tail = log_tail
        self.result = result or {}


def _platform_candidates() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return ["/Applications/Blender.app/Contents/MacOS/Blender", os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender")]
    if system == "Windows":
        return sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    return ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender", os.path.expanduser("~/blender/blender")]


def find_blender(config: dict | None = None, explicit: str | None = None) -> str | None:
    """Discovery order: explicit, ROOM_GEN_BLENDER, config, PATH, platform defaults."""
    candidates = [explicit, os.environ.get("ROOM_GEN_BLENDER"), (config or {}).get("blender"), shutil.which("blender")]
    candidates += _platform_candidates()
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return str(Path(c))
    return None


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP"):
        env.pop(key, None)
    return env


def blender_version(path: str) -> str | None:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60, env=_clean_env()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines():
        if line.startswith("Blender "):
            return line.split()[1]
    return None


def parse_result(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(RESULT_PREFIX):
            return json.loads(line[len(RESULT_PREFIX) :])
    return None


def run_blender(
    command: str,
    job: dict[str, Any] | None = None,
    *,
    config: dict | None = None,
    blender: str | None = None,
    timeout: float | None = None,
    log_path: str | Path | None = None,
) -> dict:
    exe = find_blender(config, blender)
    if not exe:
        raise BlenderError("Blender not found. Install Blender 4.0+ from https://www.blender.org/download/ or set ROOM_GEN_BLENDER.")
    timeout = timeout or float((config or {}).get("blender_timeout_s", 600))
    with tempfile.TemporaryDirectory(prefix="room_gen_") as tmp:
        cmd = [exe, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(ENTRY), "--", command]
        if job is not None:
            job_path = Path(tmp) / "job.json"
            job_path.write_text(json.dumps(job), encoding="utf-8")
            cmd += ["--job", str(job_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_clean_env())
        except subprocess.TimeoutExpired as exc:
            raise BlenderError(f"Blender timed out after {timeout:.0f}s running {command}", str(exc.stdout or "")[-4000:]) from exc
    log = (proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(log, encoding="utf-8")
    result = parse_result(proc.stdout or "")
    if result is None:
        raise BlenderError(f"Blender exited with code {proc.returncode} without a result", log[-4000:])
    if not result.get("ok"):
        raise BlenderError(result.get("error", "Blender reported a failure"), (result.get("traceback") or "") + log[-2000:], result)
    result["blender"] = exe
    return result
