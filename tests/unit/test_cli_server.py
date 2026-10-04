"""Command line and annotator API (no Blender needed)."""

from __future__ import annotations

import json
import warnings

from PIL import Image
from typer.testing import CliRunner

from room_gen.cli import app
from room_gen import cli_vision  # noqa: F401 - registers vision commands
from tests.conftest import FIXTURES

runner = CliRunner()


def run(*args, root=None):
    argv = (["--root", str(root)] if root else []) + list(args)
    res = runner.invoke(app, argv)
    return res.exit_code, json.loads(res.stdout) if res.stdout.strip().startswith("{") else res.stdout


def test_version_and_archetypes():
    code, out = run("version")
    assert code == 0 and out["room_gen"]
    code, out = run("archetypes", "list")
    assert code == 0 and any(a["name"] == "sofa" for a in out["archetypes"])
    code, out = run("archetypes", "resolve", "two-seater")
    assert out["archetype"] == "loveseat"
    code, out = run("archetypes", "show", "nope")
    assert code == 1 and "unknown archetype" in out["error"]


def test_validate_good_and_bad(tmp_path):
    code, out = run("validate", "--room", str(FIXTURES / "rooms" / "living_room.json"), "--recipe", str(FIXTURES / "recipes" / "sofa.json"))
    assert code == 0 and out["ok"] and out["results"][1]["parts"] > 3
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"object": "x", "parts": [{"id": "a", "primitive": "torus", "material": "m"}], "materials": {"m": {}}}))
    code, out = run("validate", "--recipe", str(bad))
    assert code == 1 and not out["ok"]


def test_schemas_project_path_patch(tmp_path):
    code, out = run("schemas", "--out", str(tmp_path / "schemas"))
    assert code == 0 and len(out["written"]) == 7
    (tmp_path / "input").mkdir()
    Image.new("RGB", (32, 24)).save(tmp_path / "input" / "kitchen.png")
    code, out = run("project", "--world", "Kitchen", "--stage-input", root=tmp_path)
    assert code == 0 and out["world"] == "kitchen" and out["state"]["source_image_count"] == 1
    code, out = run("path", "--world", "kitchen", "--kind", "world", "--next", root=tmp_path)
    assert out["path"].endswith("output/world/0-world.glb")
    room = tmp_path / "room.json"
    room.write_text((FIXTURES / "rooms" / "living_room.json").read_text())
    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps({"shell": {"ceiling_height": 2.9}}))
    code, out = run("patch", "--room", str(room), "--ops", str(ops))
    assert code == 0 and json.loads(room.read_text())["shell"]["ceiling_height"] == 2.9
    ops.write_text(json.dumps({"shell": {"ceiling_height": 1.5}}))  # door taller than ceiling -> rejected
    code, out = run("patch", "--room", str(room), "--ops", str(ops))
    assert code == 1 and json.loads(room.read_text())["shell"]["ceiling_height"] == 2.9


def test_auto_without_photo_fails_cleanly(tmp_path):
    code, out = run("auto", "--world", "empty", "--ml", "off", root=tmp_path)
    assert code == 1 and "no source image" in out["error"]


def test_server_api(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient
    from room_gen.server import create_app

    world = tmp_path / "worlds" / "demo" / "source"
    world.mkdir(parents=True)
    Image.new("RGB", (80, 60)).save(world / "0-demo.png")
    c = TestClient(create_app(tmp_path))
    assert c.get("/api/health").json()["ok"]
    assert [w["slug"] for w in c.get("/api/worlds").json()["worlds"]] == ["demo"]
    ann = c.get("/api/worlds/demo/annotations").json()
    assert ann["image_size"] == [80, 60] and ann["image"] == "source/0-demo.png"
    ann["objects"] = [{"id": "sofa", "label": "sofa", "box": [1, 2, 30, 40], "provenance": {"by": "human", "tool": "test", "confidence": 1}}]
    assert c.put("/api/worlds/demo/annotations", json=ann).json()["objects"] == 1
    ann["objects"][0]["id"] = "Bad Id"
    r = c.put("/api/worlds/demo/annotations", json=ann)
    assert r.status_code == 422 and r.json()["errors"][0]["loc"][:2] == ["objects", 0]
    ann["objects"][0]["id"] = "sofa"
    ann["objects"][0]["box"] = [30, 2, 1, 40]  # value_error with a ValueError in its context
    r = c.put("/api/worlds/demo/annotations", json=ann)
    assert r.status_code == 422 and "x1 > x0" in r.json()["errors"][0]["msg"]
    assert c.get("/api/worlds/demo/camera").status_code == 409
    assert c.get("/api/worlds/nope").status_code == 404
    assert c.get("/api/worlds/demo/files/../../etc/passwd").status_code == 404
    assert c.get("/api/archetypes/resolve", params={"label": "couch"}).json()["archetype"] == "sofa"
