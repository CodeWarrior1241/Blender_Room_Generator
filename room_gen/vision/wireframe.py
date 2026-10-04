"""Score 3-D line sets against image evidence (shared by layout search and fitting)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from room_gen.geometry import PinholeCamera
from room_gen.vision.lines import OrientedEdges


@dataclass
class EdgeScore:
    supported: float  # image length (px) within tau of a same-orientation segment
    visible: float  # image length (px) inside the frame and in front of the camera
    per_segment: list[tuple[float, float]]

    def value(self, penalty: float = 0.15) -> float:
        return self.supported - penalty * (self.visible - self.supported)


def sample_segments(cam: PinholeCamera, segs3d, n: int = 120, margin: float = 1.0):
    """Project sampled 3-D segments; returns (midpoints, angles, weights, owner index)."""
    if not segs3d:
        return np.zeros((0, 2)), np.zeros(0), np.zeros(0), np.zeros(0, int)
    a = np.array([s[0] for s in segs3d], float)
    b = np.array([s[1] for s in segs3d], float)
    t = np.linspace(0.0, 1.0, n)
    pts = a[:, None, :] * (1 - t)[None, :, None] + b[:, None, :] * t[None, :, None]
    uv, z = cam.project(pts.reshape(-1, 3))
    uv = uv.reshape(len(segs3d), n, 2)
    z = z.reshape(len(segs3d), n)
    ok = (z > 0.05) & np.isfinite(uv).all(axis=2)
    ok &= (uv[..., 0] >= margin) & (uv[..., 0] < cam.width - margin) & (uv[..., 1] >= margin) & (uv[..., 1] < cam.height - margin)
    p0, p1 = uv[:, :-1], uv[:, 1:]
    pair_ok = ok[:, :-1] & ok[:, 1:]
    d = p1 - p0
    w = np.linalg.norm(d, axis=2)
    mid = (p0 + p1) / 2
    ang = np.arctan2(d[..., 1], d[..., 0])
    owner = np.broadcast_to(np.arange(len(segs3d))[:, None], pair_ok.shape)
    sel = pair_ok & (w < max(cam.width, cam.height) * 0.5)
    return mid[sel], ang[sel], w[sel], owner[sel]


def score(edges: OrientedEdges, cam: PinholeCamera, segs3d, tau: float = 2.5, n: int = 120) -> EdgeScore:
    mid, ang, w, owner = sample_segments(cam, segs3d, n)
    if len(w) == 0:
        return EdgeScore(0.0, 0.0, [(0.0, 0.0)] * len(segs3d))
    dist = edges.lookup(mid, ang)
    sup = dist < tau
    per = []
    for k in range(len(segs3d)):
        m = owner == k
        per.append((float(w[m & sup].sum()), float(w[m].sum())))
    return EdgeScore(float(w[sup].sum()), float(w.sum()), per)


def soft_value(edges: OrientedEdges, cam: PinholeCamera, segs3d, tau: float = 2.5, penalty: float = 0.15, n: int = 64) -> float:
    """Smooth version of ``score(...).value()``: Gaussian support instead of a hard threshold."""
    mid, ang, w, _ = sample_segments(cam, segs3d, n)
    if len(w) == 0:
        return 0.0
    dist = edges.lookup(mid, ang)
    sup = np.exp(-((dist / tau) ** 2))
    return float((w * sup).sum() - penalty * (w * (1 - sup)).sum())


def chamfer(edges: OrientedEdges, cam: PinholeCamera, segs3d, n: int = 120) -> tuple[float, float]:
    """Mean truncated oriented distance over visible model edges, and visible length."""
    mid, ang, w, _ = sample_segments(cam, segs3d, n)
    if len(w) == 0 or w.sum() < 1:
        return edges.trunc, 0.0
    dist = edges.lookup(mid, ang)
    return float((dist * w).sum() / w.sum()), float(w.sum())


def box_room_edges(x0: float, x1: float, y0: float, y1: float, h: float, tags: bool = False):
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    segs = []
    for i in range(4):
        a, b = c[i], c[(i + 1) % 4]
        segs.append(((a[0], a[1], 0.0), (b[0], b[1], 0.0), f"floor{i}"))
        segs.append(((a[0], a[1], h), (b[0], b[1], h), f"ceiling{i}"))
        segs.append(((a[0], a[1], 0.0), (a[0], a[1], h), f"corner{i}"))
    return segs if tags else [(s[0], s[1]) for s in segs]


# ----- orientation consistency (Hedau/Lee-style) -------------------------------------------

FACE_NORMAL_AXIS = np.array([1, 0, 1, 0, 2, 2])  # faces: y0, x1, y1, x0 walls, floor, ceiling


def box_faces_hit(cam: PinholeCamera, uv: np.ndarray, x0, x1, y0, y1, h) -> np.ndarray:
    """Index of the box-room face each pixel ray hits first (camera inside the box)."""
    d = cam.rays(uv)
    c = cam.C
    planes = [(1, y0), (0, x1), (1, y1), (0, x0), (2, 0.0), (2, h)]
    t = np.full((len(uv), 6), np.inf)
    with np.errstate(divide="ignore", invalid="ignore"):
        for k, (ax, val) in enumerate(planes):
            tk = (val - c[ax]) / d[:, ax]
            t[:, k] = np.where(tk > 1e-6, tk, np.inf)
    return np.argmin(t, axis=1)


class SegmentFamilies:
    """Line segments with their Manhattan family (0 x, 1 y, 2 z) for consistency checks."""

    def __init__(self, segs: np.ndarray, labels: np.ndarray):
        keep = labels >= 0
        self.mid = (segs[keep, :2] + segs[keep, 2:]) / 2
        self.family = labels[keep]
        self.length = np.hypot(segs[keep, 2] - segs[keep, 0], segs[keep, 3] - segs[keep, 1])

    def incompatible(self, cam: PinholeCamera, box) -> float:
        if len(self.mid) == 0:
            return 0.0
        faces = box_faces_hit(cam, self.mid, *box)
        bad = FACE_NORMAL_AXIS[faces] == self.family
        return float(self.length[bad].sum())


class RegionColors:
    """Appearance consistency: each face of a box-room hypothesis should look uniform.

    Colours are sampled on a coarse grid (CIE Lab); the energy is the mean squared distance
    of samples to their face's mean colour. Lower is better.
    """

    def __init__(self, rgb: np.ndarray, grid: tuple[int, int] = (64, 48)):
        import cv2

        h, w = rgb.shape[:2]
        gw, gh = grid if w >= h else (grid[1], grid[0])
        small = cv2.resize(rgb, (gw, gh), interpolation=cv2.INTER_AREA)
        lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float64).reshape(-1, 3)
        lab[:, 0] *= 100.0 / 255.0
        lab[:, 1:] -= 128.0
        self.lab = lab
        vs, us = np.mgrid[0:gh, 0:gw]
        self.uv = np.column_stack([(us.ravel() + 0.5) * w / gw, (vs.ravel() + 0.5) * h / gh])
        self._cam_key = None
        self._rays = None

    def energy(self, cam: PinholeCamera, box) -> float:
        key = (id(cam), cam.C.tobytes(), cam.R.tobytes(), cam.fx)
        if key != self._cam_key:
            self._rays = cam.rays(self.uv)
            self._cam_key = key
        d, c = self._rays, cam.C
        x0, x1, y0, y1, h = box
        planes = ((1, y0), (0, x1), (1, y1), (0, x0), (2, 0.0), (2, h))
        t = np.empty((len(d), 6))
        with np.errstate(divide="ignore", invalid="ignore"):
            for k, (ax, val) in enumerate(planes):
                tk = (val - c[ax]) / d[:, ax]
                t[:, k] = np.where(tk > 1e-6, tk, np.inf)
        faces = np.argmin(t, axis=1)
        total = 0.0
        for f in range(6):
            sel = faces == f
            n = int(sel.sum())
            if n > 1:
                col = self.lab[sel]
                total += float(((col - col.mean(axis=0)) ** 2).sum())
        return total / len(d)
