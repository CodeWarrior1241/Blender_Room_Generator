from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def _blender():
    from room_gen.blender_exec import find_blender

    return find_blender({})


def _ml_ready() -> bool:
    try:
        from room_gen.config import DEFAULTS
        from room_gen.ml import runtime

        if not runtime.installed():
            return False
        st = runtime.status(DEFAULTS)
        return all(m["cached"] for m in st["models"].values())
    except Exception:  # noqa: BLE001
        return False


def _realdata_ready() -> bool:
    subset = ROOT / "tests" / "realdata" / "nyu_subset.json"
    if not subset.is_file():
        return False
    frames = json.loads(subset.read_text())["frames"]
    return all((ROOT / "deps" / "sunrgbd" / "nyu" / f["id"] / "truth.json").is_file() for f in frames)


BLENDER = _blender()
ML_READY = _ml_ready()
REALDATA_READY = _realdata_ready()
requires_blender = pytest.mark.skipif(BLENDER is None, reason="Blender not installed")
requires_ml = pytest.mark.skipif(not ML_READY, reason="room_gen[ml] not installed or weights not cached")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "blender" in item.keywords and BLENDER is None:
            item.add_marker(pytest.mark.skip(reason="Blender not installed"))
        if "ml" in item.keywords and not ML_READY:
            item.add_marker(pytest.mark.skip(reason="room_gen[ml] not installed or weights not cached"))
        if "realdata" in item.keywords and not REALDATA_READY:
            item.add_marker(pytest.mark.skip(reason="SUN RGB-D data missing: uv run python -m tests.realdata.fetch --accept-license"))


@pytest.fixture
def fixture_room() -> dict:
    return json.loads((FIXTURES / "rooms" / "living_room.json").read_text())


@pytest.fixture
def fixture_world(tmp_path) -> tuple[Path, str]:
    """A workspace holding the living-room fixture as world 'fixture'."""
    world = tmp_path / "worlds" / "fixture"
    world.mkdir(parents=True)
    shutil.copy(FIXTURES / "rooms" / "living_room.json", world / "room.json")
    for recipe in (FIXTURES / "recipes").glob("*.json"):
        d = world / "output" / recipe.stem
        d.mkdir(parents=True)
        shutil.copy(recipe, d / "recipe.json")
    return tmp_path, "fixture"
