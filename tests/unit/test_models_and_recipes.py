"""Contracts, mesh generation and the archetype library."""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from room_gen import archetypes, meshgen
from room_gen.build import prepare_recipe, scene_json_from_room
from room_gen.models import SCHEMA_MODELS, Annotations, Recipe, Room
from tests.conftest import FIXTURES


def test_fixture_room_and_recipes_validate(fixture_room):
    Room.model_validate(fixture_room)
    for p in (FIXTURES / "recipes").glob("*.json"):
        rec, warnings = prepare_recipe(json.loads(p.read_text()))
        assert rec["parts"] and not warnings


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r["shell"].update(floor_polygon=list(reversed(r["shell"]["floor_polygon"]))), "counter-clockwise"),
    (lambda r: r["shell"]["walls"][1]["openings"][0].update(offset=5.5), "extends past the wall end"),
    (lambda r: r["shell"]["walls"][3]["openings"][0].update(height=2.9), "taller than the ceiling"),
    (lambda r: r["materials"].pop("oak_floor"), "not defined"),
    (lambda r: r.update(extra_field=1), "Extra inputs"),
])
def test_room_rejects(fixture_room, mutate, message):
    room = copy.deepcopy(fixture_room)
    mutate(room)
    with pytest.raises(ValidationError, match=message):
        Room.model_validate(room)


def test_recipe_and_annotation_rejects():
    with pytest.raises(ValidationError, match="needs"):
        Recipe.model_validate({"object": "x", "materials": {"m": {}}, "parts": [{"id": "a", "primitive": "cylinder", "material": "m"}]})
    with pytest.raises(ValidationError, match="undefined materials"):
        Recipe.model_validate({"object": "x", "parts": [{"id": "a", "primitive": "box", "size": [1, 1, 1], "material": "nope"}]})
    with pytest.raises(ValidationError, match="duplicate object ids"):
        Annotations.model_validate({"world": "w", "image": "i.png", "image_size": [10, 10],
                                    "objects": [{"id": "a", "label": "a", "box": [0, 0, 5, 5]}, {"id": "a", "label": "b", "box": [1, 1, 5, 5]}]})
    with pytest.raises(ValidationError, match="x1 > x0"):
        Annotations.model_validate({"world": "w", "image": "i.png", "image_size": [10, 10], "objects": [{"id": "a", "label": "a", "box": [5, 0, 1, 5]}]})


def test_schemas_generate():
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema()
        assert schema["type"] == "object", name


def test_primitives_closed_and_outward():
    for verts, faces in (meshgen.box(1, 2, 3), meshgen.cylinder(0.5, 1), meshgen.cone(0.5, 0, 1), meshgen.sphere(1),
                         meshgen.torus(1, 0.2), meshgen.tube(1, 0.8, 1), meshgen.prism([(0, 0), (1, 0), (0, 1)], 1),
                         meshgen.lathe([(0, 0), (0.3, 0), (0.2, 1), (0, 1)])):
        assert meshgen.signed_volume(verts, faces) > 0
        edges = {}
        for f in faces:
            for a, b in zip(f, f[1:] + f[:1]):
                edges[(a, b)] = edges.get((a, b), 0) + 1
        assert all((b, a) in edges for a, b in edges), "every edge must have an opposite half-edge (closed mesh)"


def test_part_instances_mirror_and_array():
    part = {"id": "leg", "primitive": "box", "size": [0.1, 0.1, 0.5], "position": [0.4, 0.3, 0.25], "material": "m",
            "mirror": "xy", "array": {"count": 2, "offset": [0, 0, 1]}}
    inst = meshgen.part_instances(part)
    assert len(inst) == 8
    lo, hi = meshgen.recipe_bbox({"parts": [part]})
    assert lo == pytest.approx((-0.45, -0.35, 0.0)) and hi == pytest.approx((0.45, 0.35, 1.5))


@pytest.mark.parametrize("name", archetypes.names())
@pytest.mark.parametrize("scale", [0.6, 1.0, 1.4])
def test_archetype_matches_its_bbox(name, scale):
    arch = archetypes.get(name)
    params = {k: (v * scale if k in ("width", "depth", "height") else v) for k, v in arch.defaults.items()}
    rec, _ = archetypes.expand({"object": name, "archetype": name, "params": params})
    Recipe.model_validate(rec)
    assert len(rec["parts"]) <= 64
    lo, hi = meshgen.recipe_bbox(rec)
    size = [hi[i] - lo[i] for i in range(3)]
    for got, want in zip(size, rec["bbox_m"]):
        assert got == pytest.approx(want, rel=0.03)
    assert abs((hi[0] + lo[0]) / 2) < 0.02 * max(rec["bbox_m"]) and abs((hi[1] + lo[1]) / 2) < 0.02 * max(rec["bbox_m"])
    assert lo[2] == pytest.approx(0.0, abs=1e-6)


def test_resolve_and_expand_rules():
    assert archetypes.resolve("green velvet couch") == ("sofa", True)
    assert archetypes.resolve("Bedside Tables") == ("nightstand", True)
    assert archetypes.resolve("coffee table") == ("coffee_table", True)
    assert archetypes.resolve("mysterious object") == ("generic_box", False)
    hand = {"object": "x", "archetype": "sofa", "parts": [{"id": "p", "primitive": "box", "size": [1, 1, 1], "material": "m"}],
            "materials": {"m": {}}, "provenance": {"parts_by": "human"}}
    out, _ = archetypes.expand(hand)
    assert len(out["parts"]) == 1, "hand-written parts are kept"
    out, warnings = archetypes.expand({"object": "x", "archetype": "sofa", "params": {"width": 9.0}})
    assert out["params"]["width"] == 4.0 and warnings


def test_prepare_recipe_auto_fit():
    rec = {"object": "x", "bbox_m": [2, 2, 2], "materials": {"m": {}}, "parts": [{"id": "a", "primitive": "box", "size": [1, 1, 1], "position": [0, 0, 0.5], "material": "m"}]}
    out, warnings = prepare_recipe(rec)
    lo, hi = meshgen.recipe_bbox(out)
    assert hi[2] - lo[2] == pytest.approx(2.0) and warnings


def test_scene_json_matches_viewer_conventions(fixture_room):
    scene = scene_json_from_room(fixture_room, {"sofa": "w/sofa/0"})
    sofa = next(i for i in scene["instances"] if i["objectId"] == "sofa")
    assert sofa["position"] == [0.0, 0.0, -2.45]  # Blender (0, 2.45, 0) -> Three (0, 0, -2.45)
    assert sofa["scale"] == [2.0, 2.0, 2.0]  # viewer renders objects at 0.5
    assert sofa["assetId"] == "w/sofa/0"
    from room_gen.coords import three_sun_direction, three_to_blender
    import math
    d = three_to_blender(three_sun_direction(scene["sun"]["rotation"]))
    az, el = math.radians(120), math.radians(30)
    assert d == pytest.approx((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)), abs=1e-6)
