"""Hidden request sidecars (``.N-slug-request.json``) recording how an artifact was made."""

from __future__ import annotations

import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from room_gen import __version__
from room_gen.jsonio import write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: str | Path) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: str | Path, root: str | Path) -> str:
    path, root = Path(path).resolve(), Path(root).resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def write_request(
    path: str | Path,
    *,
    kind: str,
    root: str | Path,
    inputs: list[str | Path] | None = None,
    outputs: list[str | Path] | None = None,
    status: str = "completed",
    started_at: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a request sidecar with input hashes and output listing."""
    record: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "provider": "room-gen",
        "room_gen_version": __version__,
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "status": "failed" if error else status,
        "submitted_at": started_at or now_iso(),
        "completed_at": now_iso(),
        "input_files": [{"path": rel(p, root), "sha256": sha256_file(p)} for p in inputs or []],
        "output_files": [rel(p, root) for p in outputs or [] if Path(p).exists()],
        "error": error,
    }
    if extra:
        record.update(extra)
    return write_json(path, record)
