"""JSON read/write with the project's formatting rules (sorted keys, 2-space indent)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert pydantic models, numpy scalars/arrays and Paths into plain JSON values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "tolist"):  # numpy arrays and scalars
        return to_jsonable(value.tolist())
    if isinstance(value, float):
        return round(value, 6)
    return value


def dumps(value: Any) -> str:
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: str | Path, value: Any) -> Path:
    """Atomically write ``value`` as formatted JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(dumps(value))
        os.replace(tmp, path)
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(path, 0o666 & ~umask)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_json_if_exists(path: str | Path) -> Any | None:
    path = Path(path)
    return read_json(path) if path.is_file() else None
