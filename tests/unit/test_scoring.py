"""The benchmark scorer itself (tests/eval/scoring.py)."""

from __future__ import annotations

import numpy as np
import pytest

from room_gen.geometry import PinholeCamera
from tests.eval.scoring import Truth, layout_errors, layout_labels, polygon_iou, virtual_edges, visible_walls

SQUARE = np.array([[-2.0, -2.0], [2.0, -2.0], [2.0, 3.0], [-2.0, 3.0]])


def cam():
    return PinholeCamera.look_at((0.0, 0.0, 1.4), (0.3, 3.0, 1.0), 640, 480, hfov_deg=65)


def test_polygon_iou():
    assert polygon_iou(SQUARE, SQUARE) == pytest.approx(1.0, abs=1e-3)
    shifted = SQUARE + [2.0, 0.0]
    assert polygon_iou(SQUARE, shifted) == pytest.approx(2 * 5 / (4 * 5 + 2 * 5), abs=0.01)


def test_layout_labels_and_errors():
    c = cam()
    lab, depth = layout_labels(c, SQUARE, 2.6)
    assert set(np.unique(lab)) <= {0, 1, 2, 3, 4} and (lab == 3).mean() > 0.2  # the back wall is in front
    assert np.isfinite(depth).all()
    truth = Truth(c, SQUARE, 2.6)
    assert layout_errors(truth, c, SQUARE, 2.6) == {"layout_pixel_err_pct": 0.0, "layout_depth_err_pct": 0.0, "layout_depth_err_scaled_pct": 0.0}
    big = c.copy()
    big.C = big.C * 1.25
    err = layout_errors(truth, big, SQUARE * 1.25, 2.6 * 1.25)
    assert err["layout_pixel_err_pct"] == 0.0 and err["layout_depth_err_pct"] == pytest.approx(25.0, abs=0.5)
    assert err["layout_depth_err_scaled_pct"] == pytest.approx(0.0, abs=0.5)


def test_camera_fan_edges_are_view_boundaries():
    """SUN RGB-D style: the visible region fanned out from the camera."""
    c = cam()
    fan = np.array([[0.0, 0.0], [2.0, 2.0], [2.0, 3.0], [-1.5, 3.0], [-1.5, 1.5]])
    assert virtual_edges(fan, c) == {0, 4}
    lab, depth = layout_labels(c, fan, 2.6, skip_edges=virtual_edges(fan, c))
    assert np.nanmin(depth) > 0.5, "no ray may stop at the camera"
    assert not set(visible_walls(c, fan, 2.6)) & {0, 4}
