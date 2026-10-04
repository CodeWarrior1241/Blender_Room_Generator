"""Real photos with measured ground truth (SUN RGB-D / NYU Depth v2; research use only).

Skipped unless the data is in deps/sunrgbd (`uv run python -m tests.realdata.fetch --accept-license`).
The fast tests check the converted ground truth; the slow ones are regression gates whose
thresholds come from the baseline in tests/realdata/REPORT.md, with a margin.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from room_gen.geometry import PinholeCamera
from room_gen.meshgen import signed_area_2d
from room_gen.vision.objects import box_corners

pytestmark = pytest.mark.realdata

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "deps" / "sunrgbd" / "nyu"
FRAMES = [f["id"] for f in json.loads((HERE / "nyu_subset.json").read_text())["frames"]] if (HERE / "nyu_subset.json").is_file() else []


def _truth(frame: str) -> dict:
    return json.loads((DATA / frame / "truth.json").read_text())


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


@pytest.mark.parametrize("frame", FRAMES)
def test_ground_truth_is_consistent(frame):
    """Conventions check: Kinect intrinsics, CCW layout, the photo crop size, and 3-D boxes
    that project onto their own 2-D boxes."""
    t = _truth(frame)
    from PIL import Image

    assert Image.open(DATA / frame / "image.jpg").size == (561, 427)
    cam = PinholeCamera.from_dict(t["camera"])
    assert cam.fx == pytest.approx(518.86, abs=1.0) and cam.fy == pytest.approx(519.47, abs=1.0)
    assert signed_area_2d([tuple(p) for p in t["floor_polygon"]]) > 0
    assert 0.6 <= t["camera_height"] <= 2.0 and 2.2 <= t["ceiling_height"] <= 3.6
    assert len(t["visible_walls"]) >= 2
    ious = []
    for o in t["objects"]:
        if not o["box2d"]:
            continue
        uv, z = cam.project(box_corners(*o["position"], *o["size"], o["yaw"]))
        if (z <= 0.05).any():
            continue
        x0, y0 = np.clip(uv.min(axis=0), 0, [cam.width, cam.height])
        x1, y1 = np.clip(uv.max(axis=0), 0, [cam.width, cam.height])
        ious.append(_iou((x0, y0, x1, y1), o["box2d"]))
    assert ious and float(np.median(ious)) > 0.4, f"projected 3-D boxes do not match the 2-D boxes (median IoU {np.median(ious):.2f})"


GATE_FRAMES = FRAMES[:4]


@pytest.mark.slow
@pytest.mark.blender
def test_twin_and_photo_gates(tmp_path):
    """Regression gates on a few frames (thresholds: baseline medians plus margin)."""
    from tests.realdata.benchmark import run_frame, summarise

    rows = [run_frame(f, m, tmp_path) for f in GATE_FRAMES for m in ("photo-auto", "twin-auto")]
    assert not [r for r in rows if "error" in r]
    agg = summarise(rows)
    assert agg["twin-auto"]["layout_pixel_err_pct"] <= GATES["twin_pixel"]
    assert agg["photo-auto"]["layout_pixel_err_pct"] <= GATES["photo_pixel"]
    assert agg["twin-auto"]["focal_err_pct"] <= GATES["twin_focal"]
    assert agg["photo-auto"]["focal_err_pct"] <= GATES["photo_focal"]


# baseline 2026-10-04 on GATE_FRAMES (medians): photo pixel 39.8 %, twin pixel 41.0 %, photo focal 6.4 %, twin focal 1.35 %
GATES = {"photo_pixel": 50.0, "twin_pixel": 52.0, "photo_focal": 9.0, "twin_focal": 3.0}
