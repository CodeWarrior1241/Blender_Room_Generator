"""Calibration, layout, openings, objects, scale, texture and lighting on synthetic rooms."""

from __future__ import annotations


import numpy as np
import pytest

from room_gen.geometry import PinholeCamera
from room_gen.vision import scale as vscale
from room_gen.vision.calib import calibrate_auto, calibrate_manual, height_from_floor_length, height_from_reference, rotation_delta
from room_gen.vision.imageio import to_gray
from room_gen.vision.layout import estimate_layout
from room_gen.vision.light import estimate_lighting
from room_gen.vision.lines import OrientedEdges, detect_segments, side_contrast
from room_gen.vision.objects import box_corners, dominant_colors, fit_box, grabcut_mask
from room_gen.vision.openings import opening_from_quad
from room_gen.vision.texture import rectify_shell
from room_gen.vision.wireframe import SegmentFamilies
from tests.unit.synth import render_box_room

ROOM = (-2.0, 3.0, -1.0, 4.5, 2.6)  # camera-centred: x0, x1, y0, y1, h
VIEWS = [((0.0, 0.0, 1.5), (1.2, 4.0, 1.1), 72), ((0.0, 0.0, 1.3), (-1.0, 4.0, 0.9), 60)]


def _cam(view, w=960, h=720):
    pos, tgt, fov = view
    return PinholeCamera.look_at(pos, tgt, w, h, hfov_deg=fov)


@pytest.mark.parametrize("view", VIEWS)
def test_auto_calibration_recovers_focal_and_rotation(view):
    cam = _cam(view)
    img = render_box_room(cam, ROOM, boxes3d=[((0.2, 2.5, 0.0), (1.4, 3.3, 0.8), (90, 110, 140))])
    segs = detect_segments(to_gray(img))
    cal = calibrate_auto(segs, cam.width, cam.height)
    assert cal.finite_vps >= 2
    assert cal.f == pytest.approx(cam.fx, rel=0.02)
    assert rotation_delta(cal.R, cam.R) < 0.5


def test_manual_calibration_from_exact_lines():
    cam = _cam(VIEWS[0])

    def line(a, b):
        uv, _ = cam.project([a, b])
        return [tuple(uv[0]), tuple(uv[1])]

    hints = {
        "parallel_pairs": [
            {"axis": "x", "lines": [line((-1, 4.5, 0), (2, 4.5, 0)), line((-1, 4.5, 2.6), (2, 4.5, 2.6))]},
            {"axis": "y", "lines": [line((3, 1, 0), (3, 4, 0)), line((3, 1, 2.6), (3, 4, 2.6))]},
        ],
        "vertical_lines": [line((3, 4.5, 0.2), (3, 4.5, 2.4)), line((-2, 4.5, 0.2), (-2, 4.5, 2.4))],
    }
    cal = calibrate_manual(hints, cam.width, cam.height)
    assert cal.f == pytest.approx(cam.fx, rel=1e-3)
    assert rotation_delta(cal.R, cam.R) < 0.05


def test_metric_scale_from_reference_and_length():
    cam = _cam(VIEWS[0])
    unit = PinholeCamera(cam.fx, cam.fy, cam.cx, cam.cy, cam.width, cam.height, cam.R, (0, 0, 1.0))
    uv, _ = cam.project([[0.8, 3.0, 0.0], [0.8, 3.0, 2.03]])
    assert height_from_reference(unit, uv[0], uv[1], 2.03) == pytest.approx(1.5, rel=1e-6)
    uv, _ = cam.project([[-0.5, 2.0, 0.0], [0.7, 2.0, 0.0]])
    assert height_from_floor_length(unit, uv[0], uv[1], 1.2) == pytest.approx(1.5, rel=1e-6)


def test_layout_recovers_box_room():
    cam = _cam(VIEWS[0])
    img = render_box_room(cam, ROOM)
    segs = detect_segments(to_gray(img))
    cal = calibrate_auto(segs, cam.width, cam.height)
    est_cam = cal.camera(1.5)
    keep = side_contrast(img, segs) >= 4
    lay = estimate_layout(OrientedEdges(segs[keep], img.shape[:2]), est_cam, families=SegmentFamilies(segs, cal.labels))
    got = dict(zip(("x0", "x1", "y0", "y1", "h"), lay.as_tuple()))
    for k, want in zip(("x1", "y1", "h"), ROOM[1:2] + ROOM[3:]):
        if k == "x1" and not lay.visible[1]:
            continue
        assert got[k] == pytest.approx(want, abs=0.12), k
    assert lay.visible[2]


def test_opening_back_projection():
    cam = _cam(VIEWS[0])
    poly = [(ROOM[0], ROOM[2]), (ROOM[1], ROOM[2]), (ROOM[1], ROOM[3]), (ROOM[0], ROOM[3])]
    # window on the back wall (edge 2 runs from x1 to x0): offset measured from (x1, y1)
    corners = [(1.8, 4.5, 0.9), (0.6, 4.5, 0.9), (0.6, 4.5, 2.1), (1.8, 4.5, 2.1)]
    uv, _ = cam.project(corners)
    edge, op = opening_from_quad(cam, poly, ROOM[4], uv, "window")
    assert edge == 2
    assert op["offset"] == pytest.approx(3.0 - 1.8, abs=0.01)
    assert op["width"] == pytest.approx(1.2, abs=0.01)
    assert op["sill"] == pytest.approx(0.9, abs=0.01) and op["height"] == pytest.approx(1.2, abs=0.01)


def test_fit_box_recovers_size_and_position():
    cam = _cam(VIEWS[0])
    truth = dict(x=0.8, y=3.0, w=1.8, d=0.9, h=0.85)
    pts = box_corners(truth["x"], truth["y"], 0.0, truth["w"], truth["d"], truth["h"], 0.0)
    uv, _ = cam.project(pts)
    obs = (uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max())
    sol, cost = fit_box(cam, obs, [False] * 4, 0.0, (2.0, 0.9, 0.85), 0.0)
    x, y = sol[:2]
    w, d, h = np.exp(sol[2:5])
    assert cost < 1.0
    assert (x, y) == pytest.approx((truth["x"], truth["y"]), abs=0.08)
    assert w == pytest.approx(truth["w"], rel=0.06) and h == pytest.approx(truth["h"], rel=0.06)


def test_masks_and_colours():
    img = np.full((120, 160, 3), 230, np.uint8)
    img[40:90, 50:120] = (40, 90, 160)
    m = grabcut_mask(img, (45, 35, 125, 95))
    assert m[60, 80] and not m[5, 5]
    cols = dominant_colors(img, m)
    r, g, b = (int(cols[0][i : i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 40) < 12 and abs(b - 160) < 12


def test_scale_from_object_heights():
    k, sigma, n = vscale.estimate([{"archetype": "dining_table", "height": 0.75 * 1.2, "confidence": 0.8},
                                   {"archetype": "sofa", "height": 0.84 * 1.2, "confidence": 0.8},
                                   {"archetype": "plant", "height": 3.0, "confidence": 0.8}], [])
    assert n == 2 and k == pytest.approx(1 / 1.2, rel=1e-6)
    k2, _ = vscale.combine("assumed", k, sigma)
    assert 1 / 1.2 < k2 < 1.0
    assert vscale.estimate([], [2.03 * 0.9])[0] == pytest.approx(1 / 0.9)


def test_texture_rectification_recovers_surface_colours(tmp_path):
    cam = _cam(VIEWS[0], 640, 480)
    img = render_box_room(cam, ROOM, noise=0)
    cx, cy = (ROOM[0] + ROOM[1]) / 2, (ROOM[2] + ROOM[3]) / 2
    room_cam = PinholeCamera(cam.fx, cam.fy, cam.cx, cam.cy, cam.width, cam.height, cam.R, cam.C - (cx, cy, 0))
    hx, hy = (ROOM[1] - ROOM[0]) / 2, (ROOM[3] - ROOM[2]) / 2
    shell = {"floor_polygon": [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)], "ceiling_height": ROOM[4], "walls": []}
    res = rectify_shell(img, room_cam, shell, tmp_path, 0, size=256)
    def rgb(hexcol):
        return np.array([int(hexcol[i : i + 2], 16) for i in (1, 3, 5)])

    assert res["floor"]["coverage"] > 0.2
    assert np.abs(rgb(res["floor"]["mean_color"]) - (168, 128, 92)).max() <= 3
    assert np.abs(rgb(res["wall-2"]["mean_color"]) - (158, 178, 162)).max() <= 3
    assert res["wall-0"]["coverage"] == 0.0  # behind the camera


def test_lighting_estimate_is_valid():
    img = np.full((60, 80, 3), (180, 170, 150), np.uint8)
    shell = {"floor_polygon": [(-2, -2), (2, -2), (2, 2), (-2, 2)], "ceiling_height": 2.5,
             "walls": [{"edge": 2, "openings": [{"kind": "window", "offset": 1, "width": 1, "height": 1, "sill": 1}]}]}
    light = estimate_lighting(img, shell)
    assert light["sun"]["azimuth"] == pytest.approx(0.0)  # back wall faces +Y: the sun is out there
    from room_gen.models import Lighting

    Lighting.model_validate(light)


def test_boundary_hints_alone_recover_walls():
    """With no image evidence at all, traced boundary lines must still pin the walls."""
    from room_gen.vision.wireframe import box_room_edges

    cam = _cam(VIEWS[0])
    hints_by_kind: dict = {}
    for a, b, tag in box_room_edges(*ROOM, tags=True):
        kind = {"floor": "wall_floor", "ceiling": "wall_ceiling", "corner": "wall_wall"}[tag.rstrip("0123")]
        t = np.linspace(0, 1, 30)[:, None]
        uv, z = cam.project(np.array(a) * (1 - t) + np.array(b) * t)
        ok = (z > 0.05) & (uv[:, 0] > 0) & (uv[:, 0] < cam.width) & (uv[:, 1] > 0) & (uv[:, 1] < cam.height)
        pts = uv[ok]
        if len(pts) >= 2:
            hints_by_kind.setdefault(kind, []).append([*pts[0], *pts[-1]])
    hints = {k: OrientedEdges(np.array(v), (cam.height, cam.width)) for k, v in hints_by_kind.items()}
    empty = OrientedEdges(np.zeros((0, 4)), (cam.height, cam.width))
    lay = estimate_layout(empty, cam, hints=hints, restarts=1)
    got = dict(zip(("x0", "x1", "y0", "y1", "h"), lay.as_tuple()))
    assert got["y1"] == pytest.approx(ROOM[3], abs=0.1) and got["h"] == pytest.approx(ROOM[4], abs=0.1)
    assert got["x1"] == pytest.approx(ROOM[1], abs=0.15)
