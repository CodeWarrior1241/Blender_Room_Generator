"""The only script Blender runs: ``blender -b --factory-startup --python entry.py -- <cmd> --job job.json``."""

from __future__ import annotations

import json
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from room_gen.blender.util import emit  # noqa: E402


def _args() -> tuple[str, dict]:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("usage: entry.py -- <probe|build|render|bridge> [--job job.json]")
    command, job = argv[0], {}
    if "--job" in argv:
        with open(argv[argv.index("--job") + 1], encoding="utf-8") as handle:
            job = json.load(handle)
    return command, job


def main() -> None:
    try:
        command, job = _args()
        if command == "probe":
            from room_gen.blender.shim import capabilities

            result = capabilities()
        elif command == "build":
            from room_gen.blender.build import run_build

            result = run_build(job)
        elif command == "render":
            from room_gen.blender.build import run_render

            result = run_render(job)
        elif command == "inspect":
            from room_gen.blender.inspect import run_inspect

            result = run_inspect(job)
        elif command == "bridge":
            from room_gen.blender.bridge import run_bridge

            result = run_bridge(job)
        else:
            raise ValueError(f"unknown command {command!r}")
        emit({"ok": True, "command": command, **result})
    except Exception as exc:  # noqa: BLE001 - report every failure through the result line
        emit({"ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        sys.stdout.flush()
        os._exit(1)


main()
