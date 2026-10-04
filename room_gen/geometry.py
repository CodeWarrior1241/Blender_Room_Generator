"""Pinhole camera and small geometry helpers shared by every host-side tool.

Conventions
- World/room frame: Blender's, right-handed, Z up, metres.
- Camera frame: OpenCV's, x right, y down, z forward.
- ``R`` maps world to camera: ``X_cam = R @ (X_world - C)``; ``C`` is the camera centre.
- Pixel coordinates are continuous: the top-left pixel covers [0,1)x[0,1), so the image
  centre is (W/2, H/2) and scaling an image by ``s`` scales every coordinate by ``s``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

BLENDER_SENSOR_MM = 36.0
CV_TO_BLENDER_CAM = np.diag([1.0, -1.0, -1.0])


def normalize(v: np.ndarray, axis: int = -1) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def rotation_angle_deg(r1: np.ndarray, r2: np.ndarray) -> float:
    """Angle of the relative rotation between two rotation matrices, in degrees."""
    cos = (np.trace(np.asarray(r1).T @ np.asarray(r2)) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def orthonormalize(m: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(np.asarray(m, dtype=float))
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def euler_xyz_from_matrix(r: np.ndarray) -> tuple[float, float, float]:
    """Blender 'XYZ' Euler angles (radians) for R = Rz @ Ry @ Rx."""
    r = np.asarray(r, dtype=float)
    sy = -r[2, 0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.asin(sy)
    if abs(math.cos(ry)) > 1e-8:
        rx = math.atan2(r[2, 1], r[2, 2])
        rz = math.atan2(r[1, 0], r[0, 0])
    else:  # gimbal lock
        rx = math.atan2(-r[1, 2], r[1, 1])
        rz = 0.0
    return rx, ry, rz


def matrix_from_euler_xyz(rx: float, ry: float, rz: float) -> np.ndarray:
    """Inverse of :func:`euler_xyz_from_matrix` (Blender convention)."""
    return rot_z(rz) @ rot_y(ry) @ rot_x(rx)


@dataclass
class PinholeCamera:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    C: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self) -> None:
        self.R = np.asarray(self.R, dtype=float).reshape(3, 3)
        self.C = np.asarray(self.C, dtype=float).reshape(3)

    # ----- construction -------------------------------------------------------------
    @classmethod
    def look_at(
        cls,
        position,
        target,
        width: int,
        height: int,
        *,
        f: float | None = None,
        hfov_deg: float | None = None,
        up=(0.0, 0.0, 1.0),
        roll_deg: float = 0.0,
    ) -> "PinholeCamera":
        position = np.asarray(position, dtype=float)
        forward = normalize(np.asarray(target, dtype=float) - position)
        right = normalize(np.cross(forward, np.asarray(up, dtype=float)))
        down = np.cross(forward, right)
        r = np.stack([right, down, forward])
        if roll_deg:
            r = rot_z(math.radians(roll_deg)) @ r
        if f is None:
            hfov = math.radians(hfov_deg if hfov_deg is not None else 60.0)
            f = (width / 2.0) / math.tan(hfov / 2.0)
        return cls(f, f, width / 2.0, height / 2.0, width, height, r, position)

    @classmethod
    def from_dict(cls, d: dict) -> "PinholeCamera":
        return cls(
            float(d["fx"]),
            float(d["fy"]),
            float(d["cx"]),
            float(d["cy"]),
            int(d["width"]),
            int(d["height"]),
            np.asarray(d["R"], dtype=float),
            np.asarray(d["position"], dtype=float),
        )

    def to_dict(self) -> dict:
        return {
            "fx": float(self.fx),
            "fy": float(self.fy),
            "cx": float(self.cx),
            "cy": float(self.cy),
            "width": int(self.width),
            "height": int(self.height),
            "R": self.R.tolist(),
            "position": self.C.tolist(),
        }

    def copy(self) -> "PinholeCamera":
        return PinholeCamera(self.fx, self.fy, self.cx, self.cy, self.width, self.height, self.R.copy(), self.C.copy())

    # ----- intrinsics ---------------------------------------------------------------
    @property
    def K(self) -> np.ndarray:
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1]], dtype=float)

    @property
    def t(self) -> np.ndarray:
        return -self.R @ self.C

    @property
    def hfov_deg(self) -> float:
        return math.degrees(2 * math.atan(self.width / (2 * self.fx)))

    def scaled(self, s: float) -> "PinholeCamera":
        """Same camera for an image resized by factor ``s``."""
        return PinholeCamera(
            self.fx * s,
            self.fy * s,
            self.cx * s,
            self.cy * s,
            int(round(self.width * s)),
            int(round(self.height * s)),
            self.R.copy(),
            self.C.copy(),
        )

    # ----- projection ---------------------------------------------------------------
    def to_camera(self, points) -> np.ndarray:
        p = np.atleast_2d(np.asarray(points, dtype=float))
        return (p - self.C) @ self.R.T

    def project(self, points) -> tuple[np.ndarray, np.ndarray]:
        """Project world points; returns (uv Nx2, depth N). Points behind the camera get NaN uv."""
        pc = self.to_camera(points)
        z = pc[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            u = self.fx * pc[:, 0] / z + self.cx
            v = self.fy * pc[:, 1] / z + self.cy
        uv = np.stack([u, v], axis=1)
        uv[z <= 1e-9] = np.nan
        return uv, z

    def rays(self, uv) -> np.ndarray:
        """Unit world-space ray directions through pixels."""
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        dc = np.stack([(uv[:, 0] - self.cx) / self.fx, (uv[:, 1] - self.cy) / self.fy, np.ones(len(uv))], axis=1)
        return normalize(dc @ self.R)

    def intersect_plane(self, uv, normal, offset: float) -> tuple[np.ndarray, np.ndarray]:
        """Intersect pixel rays with the plane ``normal . X + offset = 0``.

        Returns (points Nx3, valid N) where valid means the hit is in front of the camera.
        """
        d = self.rays(uv)
        n = np.asarray(normal, dtype=float)
        denom = d @ n
        with np.errstate(divide="ignore", invalid="ignore"):
            t = -(n @ self.C + offset) / denom
        valid = np.isfinite(t) & (t > 1e-6)
        pts = self.C + d * t[:, None]
        pts[~valid] = np.nan
        return pts, valid

    def floor_point(self, uv, z: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        return self.intersect_plane(uv, (0.0, 0.0, 1.0), -z)

    def vanishing_point(self, direction) -> np.ndarray:
        """Homogeneous image vanishing point of a world direction."""
        return self.K @ self.R @ np.asarray(direction, dtype=float)

    def horizon_v(self, u: float | None = None) -> float:
        """Image row of the horizon (where rays are horizontal) at column ``u``."""
        u = self.width / 2 if u is None else u
        # rays with world z component 0: (R^T Kinv [u v 1])_z = 0 -> linear in v
        kinv = np.linalg.inv(self.K)
        rz = self.R.T[2]
        a = rz @ kinv @ np.array([u, 0.0, 1.0])
        b = rz @ kinv @ np.array([0.0, 1.0, 0.0])
        return float(-a / b) if abs(b) > 1e-12 else float("nan")

    # ----- Blender -----------------------------------------------------------------
    def blender_params(self) -> dict:
        """Camera data for Blender (sensor_fit AUTO, 36 mm sensor on the long side)."""
        long_side = float(max(self.width, self.height))
        m = np.eye(4)
        m[:3, :3] = self.R.T @ CV_TO_BLENDER_CAM
        m[:3, 3] = self.C
        return {
            "lens_mm": self.fx * BLENDER_SENSOR_MM / long_side,
            "sensor_mm": BLENDER_SENSOR_MM,
            "shift_x": (self.width / 2.0 - self.cx) / long_side,
            "shift_y": (self.cy - self.height / 2.0) / long_side,
            "matrix_world": m.tolist(),
            "resolution": [int(self.width), int(self.height)],
        }


def point_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Even-odd test for many 2-D points against one polygon."""
    pts = np.atleast_2d(points)
    poly = np.asarray(polygon, dtype=float)
    x, y = pts[:, 0][:, None], pts[:, 1][:, None]
    x1, y1 = poly[:, 0][None, :], poly[:, 1][None, :]
    x2, y2 = np.roll(poly[:, 0], -1)[None, :], np.roll(poly[:, 1], -1)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        cross = (y1 > y) != (y2 > y)
        xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    return (np.count_nonzero(cross & (x < xint), axis=1) % 2) == 1


def polygon_area(polygon) -> float:
    p = np.asarray(polygon, dtype=float)
    return 0.5 * float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(np.roll(p[:, 0], -1), p[:, 1]))


def polygon_centroid(polygon) -> np.ndarray:
    p = np.asarray(polygon, dtype=float)
    a = polygon_area(p)
    if abs(a) < 1e-12:
        return p.mean(axis=0)
    x, y = p[:, 0], p[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    return np.array([np.sum((x + xn) * cross), np.sum((y + yn) * cross)]) / (6.0 * a)
