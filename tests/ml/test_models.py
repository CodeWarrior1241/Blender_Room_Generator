"""Optional local models on a Blender-rendered room (skipped unless room_gen[ml] and weights are present)."""

from __future__ import annotations


import numpy as np
import pytest

from room_gen.config import DEFAULTS
from room_gen.ml import runtime

pytestmark = [pytest.mark.ml, pytest.mark.blender]


@pytest.fixture(scope="module")
def photo(tmp_path_factory):
    from tests.eval.benchmark import render_scene
    from tests.eval.scenes import scene

    out = tmp_path_factory.mktemp("ml")
    sc = scene("living-a")
    path = render_scene(sc, out)
    from room_gen.vision.imageio import load_photo

    return sc, load_photo(path)


def test_detection_finds_furniture_and_window(photo):
    from room_gen.ml.detect import detect

    _, ph = photo
    objs, ops = detect(ph.rgb, DEFAULTS["ml"]["detect_model"], runtime.pick_device())
    found = {o["archetype"] for o in objs}
    assert {"sofa", "coffee_table", "bookshelf"} <= found, found
    assert any(o["kind"] == "window" for o in ops)
    assert "stool" not in found, "items inside the bookshelf must not become furniture"


def test_metric_depth_structure_and_height(photo):
    from room_gen.ml.depth import camera_height, estimate_depth, world_points
    from tests.eval.benchmark import truth_camera

    sc, ph = photo
    cam = truth_camera(sc)
    depth = estimate_depth(ph.rgb, DEFAULTS["ml"]["depth_model"], runtime.pick_device())
    assert depth.shape == (ph.height, ph.width) and np.isfinite(depth).mean() > 0.95
    near, far = depth[int(ph.height * 0.95), ph.width // 2], depth[int(ph.height * 0.2), int(ph.width * 0.35)]
    assert near < far
    h = camera_height(world_points(depth, _unit(cam))[0])
    assert h is not None and 0.6 * cam.C[2] < h < 1.6 * cam.C[2]


def _unit(cam):
    from room_gen.geometry import PinholeCamera

    return PinholeCamera(cam.fx, cam.fy, cam.cx, cam.cy, cam.width, cam.height, cam.R, (0, 0, 1.0))


def test_segmentation_masks_follow_boxes(photo):
    from room_gen.ml.segment import masks_for_boxes

    _, ph = photo
    box = [242, 457, 636, 650]  # the sofa
    (mask,) = masks_for_boxes(ph.rgb, [box], DEFAULTS["ml"]["segment_model"], runtime.pick_device())
    inside = mask[box[1] : box[3], box[0] : box[2]].mean()
    outside = mask.mean() - mask[box[1] : box[3], box[0] : box[2]].sum() / mask.size
    assert inside > 0.4 and outside < 0.01


def test_models_listed_and_cached():
    st = runtime.status(DEFAULTS)
    assert st["installed"] and all(m["cached"] for m in st["models"].values())
