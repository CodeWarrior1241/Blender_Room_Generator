"""Blender integration: probe, builds, exports, projection round trip, bridge."""

from __future__ import annotations

import json
import math
import shutil

import cv2
import numpy as np
import pytest

from room_gen import archetypes
from room_gen.blender_exec import run_blender
from room_gen.build import build, bridge, render_room
from room_gen.config import load_config
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json, write_json
from room_gen.project import Workspace
from tests.conftest import FIXTURES

pytestmark = pytest.mark.blender


def test_probe_capabilities():
    caps = run_blender("probe", None, config={}, timeout=120)
    assert caps["gltf"] and caps["obj"] and caps["fbx"]
    assert caps["blender_version"] >= "4.0"


def test_build_fixture_room(fixture_world):
    root, slug = fixture_world
    w = Workspace.open(root).world(slug)
    res = build(w, formats=["glb", "fbx", "obj"])
    assert res["status"] == "built" and not res["failed_outputs"], res
    files = res["files"]
    for key in ("glb", "fbx", "obj", "blend", "preview", "room_blend", "room_glb", "room_preview", "room_plan"):
        assert (root / files[key]).is_file(), key
    for obj in res["objects"]:
        recipe = read_json(w.object_dir(obj["id"]) / "recipe.json")
        want = [recipe["params"][k] for k in ("width", "depth", "height")]
        assert obj["dimensions"] == pytest.approx(want, rel=0.1), obj["id"]
        assert obj["faces"] < 50_000
    preview = cv2.imread(str(root / files["room_preview"]))
    assert preview.std() > 10, "preview should not be blank"
    manifest = read_json(root / res["manifest"])
    assert manifest["assets"]["mesh"]["collider_mesh_url"].endswith("0-world.glb")
    assert manifest["assets"]["splats"]["semantics_metadata"]["flip_y"] is False
    scene = read_json(w.scene_path)
    assert len(scene["instances"]) == 7
    # exported room re-imports with the shell, seven objects and the camera
    info = run_blender("inspect", {"path": str(root / files["room_glb"])}, config={})
    assert info["cameras"] and info["bounds"]["max"][2] == pytest.approx(2.7 + 0.12, abs=0.02)
    assert res == res and build(w)["status"] == "up-to-date"


def test_every_archetype_builds(tmp_path):
    w = Workspace.open(tmp_path).world("all")
    w.ensure()
    room = json.loads((FIXTURES / "rooms" / "living_room.json").read_text())
    room["placements"] = []
    write_json(w.room_path, room)
    for name in archetypes.names():
        d = w.object_dir(name.replace("_", "-"))
        d.mkdir(parents=True)
        write_json(d / "recipe.json", {"object": name.replace("_", "-"), "archetype": name, "params": {}})
    cfg_path = tmp_path / "room_gen.config.json"
    cfg_path.write_text(json.dumps({"render": {"object_previews": False}}))
    w = Workspace.open(tmp_path).world("all")
    res = build(w, previews=False)
    assert len(res["objects"]) == len(archetypes.names())
    for obj in res["objects"]:
        arch = archetypes.get(obj["id"].replace("-", "_"))
        want = [arch.defaults[k] for k in ("width", "depth", "height")]
        assert obj["dimensions"] == pytest.approx(want, rel=0.1), obj["id"]


def test_projection_matches_blender_render(tmp_path):
    """Emissive markers rendered by Blender land where PinholeCamera projects them."""
    room = json.loads((FIXTURES / "rooms" / "living_room.json").read_text())
    for m in room["materials"].values():
        m.pop("procedural", None)
        m["base_color"] = "#000000"
    room["lighting"] = {"sun": None, "sky": {"strength": 0.0, "color": "#000000"}, "fixtures": [{"kind": "point", "position": [0, 0, 2.5], "power_w": 0.0}]}
    for wall in room["shell"]["walls"]:
        wall["openings"] = []
    cam = PinholeCamera.look_at((-1.6, -2.6, 1.45), (0.6, 1.2, 0.9), 640, 480, f=450.0)
    cam.cx += 13.0  # exercise lens shift
    pts = [(2.3, 2.8, 2.5), (-1.0, 2.0, 0.3), (1.0, 0.5, 1.0), (0.0, 2.9, 2.6)]
    objs = [{"id": f"m{i}", "recipe": {"object": f"m{i}", "materials": {"e": {"base_color": "#ffffff", "emission": "#ffffff", "emission_strength": 50.0}},
                                       "parts": [{"id": "s", "primitive": "sphere", "radius": 0.03, "segments": 16, "material": "e"}]},
             "placement": {"object": f"m{i}", "position": list(p), "yaw": 0}} for i, p in enumerate(pts)]
    out = tmp_path / "markers.png"
    render_room(room, cam, out, objects=objs, samples=8, config=load_config("."))
    img = cv2.imread(str(out), cv2.IMREAD_GRAYSCALE)
    _, _, _, cents = cv2.connectedComponentsWithStats((img > 128).astype(np.uint8))
    uv, _ = cam.project(np.array(pts))
    for p in uv:
        d = np.linalg.norm(cents[1:] + 0.5 - p, axis=1)
        assert d.min() < 0.6, f"marker off by {d.min():.2f}px"


def test_bridge_image_blaster_world(tmp_path, fixture_world):
    """Synthesise an image-blaster world (flipped collider, scaled objects) and import it."""
    root, slug = fixture_world
    w = Workspace.open(root).world(slug)
    res = build(w, formats=["glb"], previews=False)
    ib = tmp_path / "ib" / "worlds" / "demo"
    (ib / "output" / "world").mkdir(parents=True)
    (ib / "output" / "chair").mkdir(parents=True)
    shutil.copy(root / res["files"]["glb"], ib / "output" / "world" / "0-world.glb")
    write_json(ib / "output" / "world" / "0-world.json", {"assets": {"splats": {"semantics_metadata": {"flip_y": False, "metric_scale_factor": 1.0, "ground_plane_offset": 0.0}}}})
    chair_glb = sorted((root / "worlds" / slug / "output" / "armchair").glob("*-armchair.glb"))[-1]
    shutil.copy(chair_glb, ib / "output" / "chair" / "0-chair.glb")
    write_json(ib / "scene.json", {"version": 1, "instances": [
        {"instanceId": "c1", "objectId": "chair", "position": [1.0, 0.0, -2.0], "rotation": [0.0, math.pi / 2, 0.0], "scale": [2.0, 2.0, 2.0]}]})
    out = Workspace.open(tmp_path / "out").world("demo")
    rep = bridge(ib, out, formats=["glb"])
    inst = rep["instances"][0]
    lo, hi = np.array(inst["min"]), np.array(inst["max"])
    # Three (1, 0, -2) -> Blender (1, 2, 0); 0.5 * 2 scale keeps the 0.85 m armchair at full size; 90 deg yaw swaps x/y extents
    assert ((lo + hi) / 2)[:2] == pytest.approx((1.0, 2.0), abs=0.02)
    assert lo[2] == pytest.approx(0.0, abs=0.01)
    assert (hi - lo) == pytest.approx((0.85, 0.85, 0.9), abs=0.02)
    assert rep["world"]["objects"] > 5
    assert (tmp_path / "out" / rep["files"]["blend"]).is_file()
