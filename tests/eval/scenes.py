"""Benchmark scenes with known geometry (room spec + recipes + photo cameras)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _living() -> dict:
    room = json.loads((FIXTURES / "rooms" / "living_room.json").read_text())
    recipes = {p.stem: json.loads(p.read_text()) for p in (FIXTURES / "recipes").glob("*.json")}
    return {"room": room, "recipes": recipes}


def _box_room(world, w, d, h, walls, placements, recipes, floor="#a9805a", wall="#e8e4dc", accent=None):
    poly = [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]]
    mats = {"wall_paint": {"base_color": wall, "roughness": 0.9}, "floor_mat": {"base_color": floor, "roughness": 0.5, "procedural": "wood", "scale": 1.2},
            "ceiling_white": {"base_color": "#f4f4f2", "roughness": 0.95}}
    if accent:
        mats["accent"] = {"base_color": accent, "roughness": 0.9}
    room = {
        "schema_version": 1, "world": world, "shell": {
            "floor_polygon": poly, "ceiling_height": h, "wall_thickness": 0.12,
            "walls": [{"edge": i, "material": "accent" if accent and i == 2 else "wall_paint", "openings": walls.get(i, [])} for i in range(4)],
            "floor": {"material": "floor_mat"}, "ceiling": {"material": "ceiling_white"}},
        "materials": mats,
        "lighting": {"sun": {"azimuth": 30, "elevation": 35, "strength": 3.0}, "sky": {"strength": 0.7, "color": "#d4dce6"}},
        "placements": placements,
    }
    return {"room": room, "recipes": recipes}


def _bedroom() -> dict:
    recipes = {
        "bed": {"object": "bed", "archetype": "bed", "params": {"width": 1.6, "depth": 2.1, "height": 1.05}, "materials": {"duvet": {"base_color": "#8a9bb0"}}},
        "nightstand": {"object": "nightstand", "archetype": "nightstand", "params": {"width": 0.5, "depth": 0.4, "height": 0.55}},
        "wardrobe": {"object": "wardrobe", "archetype": "wardrobe", "params": {"width": 1.2, "depth": 0.6, "height": 2.0}},
        "table-lamp": {"object": "table-lamp", "archetype": "table_lamp", "params": {"width": 0.3, "depth": 0.3, "height": 0.5}},
    }
    placements = [
        {"object": "bed", "position": [0.2, 1.2, 0.0], "yaw": 0},
        {"object": "nightstand", "position": [-0.95, 2.05, 0.0], "yaw": 0},
        {"object": "table-lamp", "position": [-0.95, 2.05, 0.55], "yaw": 0, "support": "nightstand"},
        {"object": "wardrobe", "position": [1.69, -0.6, 0.0], "yaw": -90},
    ]
    walls = {2: [{"kind": "window", "offset": 1.4, "width": 1.2, "height": 1.3, "sill": 0.9}],
             3: [{"kind": "door", "offset": 0.4, "width": 0.85, "height": 2.05, "sill": 0.0}]}
    return _box_room("bedroom", 4.0, 4.5, 2.5, walls, placements, recipes, floor="#b08d68", accent="#c9b8a6")


def _dining() -> dict:
    recipes = {
        "dining-table": {"object": "dining-table", "archetype": "dining_table", "params": {"width": 1.8, "depth": 0.95, "height": 0.75}},
        "sideboard": {"object": "sideboard", "archetype": "sideboard", "params": {"width": 1.6, "depth": 0.45, "height": 0.8}},
        "pendant-lamp": {"object": "pendant-lamp", "archetype": "pendant_lamp", "params": {"width": 0.45, "depth": 0.45, "height": 0.9}},
        "plant": {"object": "plant", "archetype": "plant", "params": {"width": 0.55, "depth": 0.55, "height": 1.3}},
    }
    for i in range(4):
        recipes[f"chair-{i + 1}"] = {"object": f"chair-{i + 1}", "archetype": "dining_chair", "params": {"width": 0.46, "depth": 0.5, "height": 0.9}}
    placements = [
        {"object": "dining-table", "position": [0.0, 0.6, 0.0], "yaw": 0},
        {"object": "chair-1", "position": [-0.45, 0.0, 0.0], "yaw": 180},
        {"object": "chair-2", "position": [0.45, 0.0, 0.0], "yaw": 180},
        {"object": "chair-3", "position": [-0.45, 1.2, 0.0], "yaw": 0},
        {"object": "chair-4", "position": [0.45, 1.2, 0.0], "yaw": 0},
        {"object": "sideboard", "position": [0.0, 2.27, 0.0], "yaw": 0},
        {"object": "pendant-lamp", "position": [0.0, 0.6, 2.1], "yaw": 0, "support": "ceiling"},
        {"object": "plant", "position": [1.45, 2.1, 0.0], "yaw": 0},
    ]
    walls = {1: [{"kind": "window", "offset": 1.0, "width": 1.4, "height": 1.6, "sill": 0.8}, {"kind": "window", "offset": 3.0, "width": 1.0, "height": 1.6, "sill": 0.8}]}
    return _box_room("dining", 3.6, 5.0, 3.0, walls, placements, recipes, floor="#7a5a40", wall="#ece8df")


def _cam(pos, target, hfov, res=(1280, 960)):
    return {"position": pos, "target": target, "hfov": hfov, "resolution": list(res)}


SCENES = {
    "living-a": (_living, _cam((-1.6, -2.6, 1.45), (0.6, 1.2, 0.9), 70.9), {}),
    "living-b": (_living, _cam((0.9, -2.7, 1.6), (-0.3, 2.0, 0.8), 64.0, (1600, 1200)), {"exif_focal_35mm": True, "jpeg": True}),
    "bedroom": (_bedroom, _cam((1.5, -1.9, 1.5), (-0.6, 1.6, 0.8), 74.0), {}),
    "dining": (_dining, _cam((-1.4, -2.2, 1.65), (0.5, 1.8, 0.9), 68.0, (1200, 1600)), {}),
}


def scene(name: str) -> dict:
    make, cam, opts = SCENES[name]
    s = copy.deepcopy(make())
    s["camera"] = cam
    s["options"] = opts
    s["name"] = name
    return s
