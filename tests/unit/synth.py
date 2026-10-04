"""Synthetic flat-shaded box rooms for vision tests (no Blender needed)."""

from __future__ import annotations

import numpy as np

from room_gen.geometry import PinholeCamera
from room_gen.vision.wireframe import box_faces_hit

FACE_COLORS = np.array([[200, 196, 188], [214, 210, 204], [158, 178, 162], [222, 218, 210], [168, 128, 92], [236, 236, 233]], np.uint8)


def render_box_room(cam: PinholeCamera, box, *, boxes3d=(), noise: float = 2.0, seed: int = 0) -> np.ndarray:
    """RGB image of a box room (x0, x1, y0, y1, h) seen by ``cam``; optional solid furniture boxes."""
    h, w = cam.height, cam.width
    vs, us = np.mgrid[0:h, 0:w]
    uv = np.column_stack([us.ravel() + 0.5, vs.ravel() + 0.5])
    faces = box_faces_hit(cam, uv, *box)
    img = FACE_COLORS[faces].reshape(h, w, 3).astype(np.float32)
    if boxes3d:
        rays = cam.rays(uv)
        depth_room = np.full(len(uv), np.inf)
        best = np.full(len(uv), -1)
        for k, (lo, hi, color) in enumerate(boxes3d):
            lo, hi = np.asarray(lo, float), np.asarray(hi, float)
            with np.errstate(divide="ignore", invalid="ignore"):
                t1 = (lo - cam.C) / rays
                t2 = (hi - cam.C) / rays
            tmin = np.nanmax(np.minimum(t1, t2), axis=1)
            tmax = np.nanmin(np.maximum(t1, t2), axis=1)
            hit = (tmax >= tmin) & (tmin > 0) & (tmin < depth_room)
            depth_room[hit] = tmin[hit]
            best[hit] = k
        flat = img.reshape(-1, 3)
        for k, (_, _, color) in enumerate(boxes3d):
            flat[best == k] = color
        img = flat.reshape(h, w, 3)
    rng = np.random.default_rng(seed)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)
