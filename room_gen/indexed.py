"""Indexed file naming shared with image-blaster.

``N-slug.ext`` is a visible artifact of generation ``N``; ``.N-slug[__scope]-request.json``
is the hidden request sidecar beside it. Index 0 is the source/original.
Ported from image-blaster's ``request-metadata.mjs`` and ``fal-queue.mjs``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_REQUEST_RE = re.compile(r"^\.(\d+)-(.+?)(?:__([a-z0-9._-]+))?-request\.json$", re.IGNORECASE)
_ARTIFACT_RE = re.compile(r"^(\d+)-(.+?)(\.[^.]+)$")


@dataclass(frozen=True)
class IndexedName:
    index: int
    slug: str
    extension: str
    hidden: bool
    scope: str | None
    name: str


def parse_indexed_name(value: str | Path) -> IndexedName | None:
    name = Path(value).name
    match = _REQUEST_RE.match(name)
    if match:
        return IndexedName(int(match.group(1)), match.group(2), ".json", True, match.group(3), name)
    match = _ARTIFACT_RE.match(name)
    if match:
        return IndexedName(int(match.group(1)), match.group(2), match.group(3), False, None, name)
    return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower())
    return slug.strip("-")[:80]


def safe_file_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value))
    return safe.strip("-")[:120]


def is_visible(path: str | Path) -> bool:
    return not Path(path).name.startswith(".")


def indexed_entries(directory: str | Path) -> list[IndexedName]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    entries = []
    for child in directory.iterdir():
        if child.is_file():
            parsed = parse_indexed_name(child.name)
            if parsed:
                entries.append(parsed)
    return entries


def next_index(directory: str | Path, slug: str | None = None) -> int:
    indexes = [e.index for e in indexed_entries(directory) if slug is None or e.slug == slug]
    return max(indexes, default=-1) + 1


def latest_indexed(
    directory: str | Path,
    slug: str | None = None,
    extensions: Iterable[str] | None = None,
) -> IndexedName | None:
    exts = {e.lower() for e in extensions} if extensions else None
    artifacts = [
        e
        for e in indexed_entries(directory)
        if not e.hidden
        and (slug is None or e.slug == slug)
        and (exts is None or e.extension.lower() in exts)
    ]
    return max(artifacts, key=lambda e: e.index, default=None)


def artifact_path(directory: str | Path, index: int, slug: str, extension: str) -> Path:
    return Path(directory) / f"{index}-{safe_file_name(slug)}{extension}"


def request_path(directory: str | Path, index: int, slug: str, scope: str | None = None) -> Path:
    scope_part = f"__{safe_file_name(scope)}" if scope else ""
    return Path(directory) / f".{index}-{safe_file_name(slug)}{scope_part}-request.json"
