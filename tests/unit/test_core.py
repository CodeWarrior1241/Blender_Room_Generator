"""Indexed names, JSON I/O, merge patch, config, project envelope."""

from __future__ import annotations

import json
import os
import stat

import numpy as np
from PIL import Image

from room_gen.config import load_config
from room_gen.indexed import artifact_path, latest_indexed, next_index, parse_indexed_name, request_path, safe_file_name, slugify
from room_gen.jsonio import dumps, write_json
from room_gen.patch import merge_patch
from room_gen.project import Workspace


def test_parse_indexed_names():
    a = parse_indexed_name("3-world-full_res.spz")
    assert (a.index, a.slug, a.extension, a.hidden) == (3, "world-full_res", ".spz", False)
    r = parse_indexed_name(".2-chair__model-request.json")
    assert (r.index, r.slug, r.scope, r.hidden) == (2, "chair", "model", True)
    assert parse_indexed_name("recipe.json") is None


def test_slug_rules_match_image_blaster():
    assert slugify("Green Velvet Couch!") == "green-velvet-couch"
    assert slugify("--A__B--") == "a-b"
    assert safe_file_name("my file (1).png") == "my-file-1-.png"


def test_next_and_latest_index(tmp_path):
    assert next_index(tmp_path, "world") == 0
    for name in ("0-world.json", "1-world.json", "1-world.glb", ".2-world-request.json", "5-other.png"):
        (tmp_path / name).write_text("x")
    assert next_index(tmp_path, "world") == 3
    assert latest_indexed(tmp_path, "world", {".json"}).index == 1
    assert artifact_path(tmp_path, 4, "world", ".glb").name == "4-world.glb"
    assert request_path(tmp_path, 4, "chair", "model").name == ".4-chair__model-request.json"


def test_write_json_sorted_and_readable(tmp_path):
    p = write_json(tmp_path / "a.json", {"b": 1, "a": np.float64(0.1234567891), "c": [np.int64(2)]})
    text = p.read_text()
    assert text.index('"a"') < text.index('"b"')
    assert json.loads(text)["a"] == 0.123457
    mode = stat.S_IMODE(os.stat(p).st_mode)
    assert mode & stat.S_IRGRP, "JSON files must be group/world readable like normal files"
    assert dumps({"x": 1}).endswith("\n")


def test_merge_patch_rfc7386():
    target = {"a": "b", "c": {"d": "e", "f": "g"}}
    assert merge_patch(target, {"a": "z", "c": {"f": None}}) == {"a": "z", "c": {"d": "e"}}
    assert merge_patch({"a": [1, 2]}, {"a": [3]}) == {"a": [3]}
    assert merge_patch({"a": 1}, {"b": {"c": None}}) == {"a": 1, "b": {}}


def test_config_merges_over_defaults(tmp_path):
    (tmp_path / "room_gen.config.json").write_text(json.dumps({"render": {"width": 640}, "exports": ["glb", "fbx"]}))
    cfg = load_config(tmp_path)
    assert cfg["render"]["width"] == 640 and cfg["render"]["samples"] == 32
    assert cfg["exports"] == ["glb", "fbx"]


def test_project_staging_and_state(tmp_path):
    ws = Workspace.open(tmp_path)
    ws.input_dir.mkdir()
    Image.new("RGB", (64, 48), (200, 10, 10)).save(ws.input_dir / "My Room.JPG")
    Image.new("RGB", (64, 48), (10, 200, 10)).save(ws.input_dir / "0-already.png")
    (ws.input_dir / "notes.txt").write_text("ignored")
    w = ws.world("Test World")
    assert w.slug == "test-world"
    w.ensure()
    staged = w.stage_input()
    assert sorted(s["to"].split("/")[-1] for s in staged) == ["0-already.png", "0-my-room.jpg"]
    assert (ws.input_dir / "notes.txt").exists()
    st = w.state()["state"]
    assert st["source_image_count"] == 2 and st["has_room"] is False
    assert w.primary_image() is not None
    assert json.loads((w.dir / "project.json").read_text())["display_name"] == "Test World"
