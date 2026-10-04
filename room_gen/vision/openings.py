"""Doors and windows: annotated (or detected) image quads -> wall openings (CLAUDE.md §8.5)."""

from __future__ import annotations

import numpy as np

from room_gen import shellgeom
from room_gen.geometry import PinholeCamera

HINTS = {"front": 0, "right": 1, "back": 2, "left": 3}


def _wall_hits(cam: PinholeCamera, uv: np.ndarray, frame: dict) -> np.ndarray:
    """Intersect pixel rays with a wall plane; returns local (s, v, z) or NaN."""
    nx, ny = frame["v_in"]
    sx, sy = frame["start"]
    offset = -(nx * sx + ny * sy)
    pts, ok = cam.intersect_plane(uv, (nx, ny, 0.0), offset)
    out = np.full((len(uv), 3), np.nan)
    for i, (p, good) in enumerate(zip(pts, ok)):
        if good:
            out[i] = shellgeom.world_to_local(frame, p[0], p[1], p[2])
    return out


def choose_wall(cam: PinholeCamera, polygon, height: float, uv_center, hint: str | int | None = None) -> int | None:
    frames = shellgeom.wall_frames(polygon)
    if isinstance(hint, int) or (isinstance(hint, str) and hint.isdigit()):
        return int(hint)
    if isinstance(hint, str) and hint.lower() in HINTS and len(frames) == 4:
        return HINTS[hint.lower()]
    best, best_t = None, np.inf
    ray = cam.rays([uv_center])[0]
    for fr in frames:
        loc = _wall_hits(cam, np.array([uv_center]), fr)[0]
        if np.isnan(loc).any():
            continue
        s, _, z = loc
        if -0.05 <= s <= fr["length"] + 0.05 and -0.05 <= z <= height + 0.05:
            world = np.array(shellgeom.local_to_world(fr, s, 0.0, z))
            t = float(np.dot(world - cam.C, ray))
            if 0 < t < best_t:
                best, best_t = fr["edge"], t
    return best


def opening_from_quad(cam: PinholeCamera, polygon, height: float, quad_uv, kind: str, hint=None) -> tuple[int, dict] | None:
    """Back-project an image quad onto its wall; returns (edge, opening dict) or None."""
    quad = np.asarray(quad_uv, float)
    edge = choose_wall(cam, polygon, height, quad.mean(axis=0), hint)
    if edge is None:
        return None
    frame = shellgeom.wall_frames(polygon)[edge]
    loc = _wall_hits(cam, quad, frame)
    if np.isnan(loc).any():
        return None
    s0, s1 = float(np.clip(loc[:, 0].min(), 0.0, frame["length"])), float(np.clip(loc[:, 0].max(), 0.0, frame["length"]))
    z0, z1 = float(np.clip(loc[:, 2].min(), 0.0, height)), float(np.clip(loc[:, 2].max(), 0.0, height))
    if kind == "door" or z0 < 0.12:
        z0 = 0.0 if kind != "window" else z0
    width, op_h = s1 - s0, z1 - z0
    if width < 0.2 or op_h < 0.2:
        return None
    op = {"kind": kind, "offset": round(s0, 3), "width": round(width, 3), "height": round(min(op_h, height - z0 - 0.01), 3), "sill": round(z0, 3)}
    if kind == "window":
        op["glazing"] = True
    return edge, op
