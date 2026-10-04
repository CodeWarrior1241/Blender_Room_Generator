"""Project configuration: ``room_gen.config.json`` merged over built-in defaults."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from room_gen.jsonio import read_json

CONFIG_FILE = "room_gen.config.json"

DEFAULTS: dict[str, Any] = {
    "blender": None,
    "blender_timeout_s": 600,
    "worlds_dir": "worlds",
    "input_dir": "input",
    "working_long_side": 1024,
    "render": {
        "engine": "eevee",
        "width": 960,
        "samples": 32,
        "object_previews": True,
        "object_preview_size": 384,
    },
    "exports": ["glb"],
    "recipes": {"auto_fit": True, "allow_script_recipes": False},
    "fit": {"enabled": True, "max_evals": 400},
    "texture": {"enabled": True, "size": 2048, "min_coverage": 0.05},
    "defaults": {
        "camera_height_m": 1.5,
        "ceiling_height_m": 2.7,
        "wall_thickness_m": 0.12,
        "behind_camera_m": 1.0,
    },
    "ml": {
        "mode": "auto",
        "device": "auto",
        "depth_model": "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
        "detect_model": "google/owlv2-base-patch16-ensemble",
        "segment_model": "facebook/sam-vit-base",
        "caption_model": None,
        "detect_threshold": 0.25,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(root: str | Path = ".", path: str | Path | None = None) -> dict[str, Any]:
    """Return the effective configuration for a workspace root."""
    root = Path(root)
    candidate = Path(path) if path else root / CONFIG_FILE
    config = copy.deepcopy(DEFAULTS)
    if candidate.is_file():
        config = deep_merge(config, read_json(candidate))
    config["_root"] = str(root.resolve())
    return config
