"""Camera model, coordinate conversions, shell geometry."""

from __future__ import annotations

import math

import numpy as np
import pytest

from room_gen import shellgeom
from room_gen.coords import (THREE_TO_BLENDER, blender_to_three, three_euler_to_matrix, three_rotation_to_blender_matrix,
                             three_sun_direction, three_to_blender, yaw_deg_to_three_rotation)
from room_gen.geometry import (PinholeCamera, euler_xyz_from_matrix, matrix_from_euler_xyz, point_in_polygon, polygon_area,
                               polygon_centroid, rot_z, rotation_angle_deg)


def cam():
    return PinholeCamera.look_at((-1.0, -2.0, 1.4), (0.5, 1.5, 1.0), 1280, 960, hfov_deg=68)


def test_project_and_ray_round_trip():
    c = cam()
    pts = np.array([[0.3, 1.0, 0.0], [1.5, 2.5, 2.0], [-0.5, 0.0, 0.7]])
    uv, z = c.project(pts)
    assert (z > 0).all()
    rays = c.rays(uv)
    back = c.C + rays * (np.linalg.norm(pts - c.C, axis=1))[:, None]
    np.testing.assert_allclose(back, pts, atol=1e-9)


def test_floor_intersection_and_horizon():
    c = cam()
    p, ok = c.floor_point([(640, 900)])
    assert ok[0] and abs(p[0, 2]) < 1e-9
    v = c.horizon_v()
    _, ok_above = c.floor_point([(640, v - 5)])
    assert not ok_above[0]


def test_look_at_axes_and_scaling():
    c = PinholeCamera.look_at((0, 0, 1.5), (0, 5, 1.5), 1000, 800, f=800)
    np.testing.assert_allclose(c.R, [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-12)
    s = c.scaled(0.5)
    uv, _ = c.project([[1, 4, 1]])
    uv2, _ = s.project([[1, 4, 1]])
    np.testing.assert_allclose(uv2, uv * 0.5, atol=1e-9)
    assert math.isclose(c.hfov_deg, 2 * math.degrees(math.atan(500 / 800)))


def test_blender_params():
    c = PinholeCamera(900, 900, 640, 480, 1280, 960)
    bp = c.blender_params()
    assert math.isclose(bp["lens_mm"], 900 * 36 / 1280)
    assert bp["shift_x"] == 0 and bp["shift_y"] == 0
    m = np.array(bp["matrix_world"])
    # Blender cameras look down their local -Z: world look direction equals OpenCV +z
    np.testing.assert_allclose(-m[:3, 2], c.R[2], atol=1e-12)


def test_euler_round_trip():
    for angles in [(0.1, -0.4, 2.0), (1.2, 0.3, -0.7)]:
        r = matrix_from_euler_xyz(*angles)
        np.testing.assert_allclose(euler_xyz_from_matrix(r), angles, atol=1e-9)
    assert rotation_angle_deg(rot_z(0.1), rot_z(0.3)) == pytest.approx(math.degrees(0.2))


def test_three_blender_conversions():
    v = (1.0, 2.0, 3.0)
    assert three_to_blender(v) == (1.0, -3.0, 2.0)
    assert blender_to_three(three_to_blender(v)) == v
    r_three = three_euler_to_matrix(0.3, -0.5, 1.1)
    r_b = three_rotation_to_blender_matrix((0.3, -0.5, 1.1))
    p = np.array([0.2, 0.7, -1.3])
    np.testing.assert_allclose(r_b @ (THREE_TO_BLENDER @ p), THREE_TO_BLENDER @ (r_three @ p), atol=1e-12)
    # yaw about Blender +Z == rotation about Three +Y
    r_yaw = three_rotation_to_blender_matrix(yaw_deg_to_three_rotation(90))
    np.testing.assert_allclose(r_yaw @ [1, 0, 0], [0, 1, 0], atol=1e-12)
    np.testing.assert_allclose(three_sun_direction((0, 0, 0)), [0, 1, 0], atol=1e-12)


def test_polygon_helpers():
    sq = np.array([[0, 0], [2, 0], [2, 1], [0, 1]], float)
    assert polygon_area(sq) == 2.0
    np.testing.assert_allclose(polygon_centroid(sq), [1, 0.5])
    np.testing.assert_array_equal(point_in_polygon(np.array([[1, 0.5], [3, 0.5]]), sq), [True, False])


def test_shell_frames_offset_and_intervals():
    poly = [(-2, -3), (2, -3), (2, 3), (-2, 3)]
    frames = shellgeom.wall_frames(poly)
    assert [round(f["length"], 6) for f in frames] == [4, 6, 4, 6]
    assert frames[0]["v_in"] == pytest.approx((0, 1))
    outer = shellgeom.offset_polygon(poly, 0.1)
    assert outer[0] == pytest.approx((-2.1, -3.1))
    s, v, z = shellgeom.world_to_local(frames[1], *shellgeom.local_to_world(frames[1], 1.5, -0.05, 0.7))
    assert (s, v, z) == pytest.approx((1.5, -0.05, 0.7))
    assert shellgeom.free_intervals(4.0, [(1.0, 1.9)]) == [(0.0, 1.0), (1.9, 4.0)]
    assert shellgeom.wall_uv(0.0, 0.0, 4.0, 2.5) == (1.0, 0.0)
    shell = {"floor_polygon": poly, "ceiling_height": 2.5, "walls": [{"edge": 1, "openings": [{"kind": "window", "offset": 1, "width": 1, "height": 1, "sill": 1}]}]}
    tags = [t for *_, t in shellgeom.shell_edges_world(shell)]
    assert tags.count("corner") == 4 and tags.count("opening") == 4
