"""Round-trip quality gates on rendered rooms (slow: renders and runs the full pipeline)."""

from __future__ import annotations

import pytest

from tests.conftest import ML_READY

pytestmark = [pytest.mark.slow, pytest.mark.blender]


@pytest.mark.parametrize("scene_name", ["living-a", "bedroom"])
def test_lines_only_reconstruction(tmp_path, scene_name):
    from tests.eval.benchmark import run

    (row,) = run([scene_name], ["auto"], tmp_path, write_report=False)
    assert row["focal_err_pct"] < 2.0
    assert row["rotation_err_deg"] < 0.6
    assert row["floor_iou"] > 0.7
    assert row["visible_wall_err_m"] < 0.3
    assert row["ceiling_err_m"] < 0.25


def test_annotated_objects(tmp_path):
    from tests.eval.benchmark import run

    (row,) = run(["living-a"], ["annotated"], tmp_path, write_report=False)
    matched, total = (int(v) for v in row["objects_matched"].split("/"))
    assert matched == total
    assert row["object_pos_err_m"] < 0.25 and row["object_size_err_pct"] < 10


@pytest.mark.ml
@pytest.mark.skipif(not ML_READY, reason="room_gen[ml] not installed or weights not cached")
def test_models_detect_and_scale(tmp_path):
    from tests.eval.benchmark import run

    (row,) = run(["living-b"], ["ml"], tmp_path, write_report=False)
    matched, total = (int(v) for v in row["objects_matched"].split("/"))
    assert matched >= total - 2
    assert row["camera_height_err_pct"] < 15
    assert row["floor_iou"] > 0.7
