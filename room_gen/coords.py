"""Conversions between image-blaster's Three.js frame (Y up) and Blender's (Z up).

Three.js -> Blender: (x, y, z) -> (x, -z, y). The mapping is a proper rotation, so
rotations conjugate cleanly and scales permute.
"""

from __future__ import annotations

import math

import numpy as np

from room_gen.geometry import euler_xyz_from_matrix, rot_x, rot_y, rot_z

# image-blaster's viewer renders every object GLB at this scale (SceneObject.tsx)
IMAGE_BLASTER_OBJECT_SCALE = 0.5

THREE_TO_BLENDER = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def three_to_blender(v) -> tuple[float, float, float]:
    x, y, z = (float(a) for a in v)
    return (x, -z, y)


def blender_to_three(v) -> tuple[float, float, float]:
    x, y, z = (float(a) for a in v)
    return (x, z, -y)


def three_euler_to_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """Three.js Euler order 'XYZ' (radians): R = Rx @ Ry @ Rz."""
    return rot_x(rx) @ rot_y(ry) @ rot_z(rz)


def three_rotation_to_blender_matrix(rotation) -> np.ndarray:
    r_three = three_euler_to_matrix(*rotation)
    return THREE_TO_BLENDER @ r_three @ THREE_TO_BLENDER.T


def three_rotation_to_blender_euler(rotation) -> tuple[float, float, float]:
    return euler_xyz_from_matrix(three_rotation_to_blender_matrix(rotation))


def three_scale_to_blender(scale) -> tuple[float, float, float]:
    sx, sy, sz = (float(a) for a in scale)
    return (sx, sz, sy)


def yaw_deg_to_three_rotation(yaw_deg: float) -> tuple[float, float, float]:
    """A rotation about Blender +Z is a rotation about Three.js +Y by the same angle."""
    return (0.0, math.radians(yaw_deg), 0.0)


def three_sun_direction(rotation) -> np.ndarray:
    """Unit vector from the scene origin toward image-blaster's sun (Three.js frame).

    Mirrors ``sunPositionFromRotation`` in WorldViewer.tsx (start at (0, 10, 0)).
    """
    x, y, z = 0.0, 10.0, 0.0
    rx, ry, rz = (float(a) for a in rotation)
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    v = np.array([x, y, z])
    return v / np.linalg.norm(v)
