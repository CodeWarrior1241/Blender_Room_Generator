"""Room-shell geometry shared by the host (textures, overlays, fitting) and Blender.

Pure Python (no numpy) so Blender's bundled interpreter can import it.

Wall frame for edge i of the CCW floor polygon P:
- ``start`` = P[i], ``u`` = unit direction to P[i+1], ``length`` = |P[i+1] - P[i]|
- ``v_in`` = left normal (points into the room); the wall slab occupies v in [-t, 0]
- local (s, v, z) -> world: start + s*u + v*v_in + z*Z

Photo-texture conventions (image row 0 is the top):
- walls: column c covers s = L * (1 - c / W) so the image reads left-to-right as seen
  from inside the room; UV = (1 - s/L, z/H)
- floor and ceiling: column -> x (min..max), row 0 -> max y; UV = ((x-x0)/sx, (y-y0)/sy)
"""

from __future__ import annotations

import math
from typing import Sequence

Vec2 = tuple[float, float]


def signed_area(poly: Sequence[Vec2]) -> float:
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))


def wall_frames(poly: Sequence[Vec2]) -> list[dict]:
    frames = []
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        ux, uy = (dx / length, dy / length) if length > 0 else (1.0, 0.0)
        frames.append(
            {
                "edge": i,
                "start": (x0, y0),
                "end": (x1, y1),
                "u": (ux, uy),
                "v_in": (-uy, ux),
                "length": length,
                "yaw_deg": math.degrees(math.atan2(uy, ux)),
            }
        )
    return frames


def local_to_world(frame: dict, s: float, v: float, z: float) -> tuple[float, float, float]:
    sx, sy = frame["start"]
    ux, uy = frame["u"]
    nx, ny = frame["v_in"]
    return (sx + s * ux + v * nx, sy + s * uy + v * ny, z)


def world_to_local(frame: dict, x: float, y: float, z: float) -> tuple[float, float, float]:
    sx, sy = frame["start"]
    ux, uy = frame["u"]
    nx, ny = frame["v_in"]
    dx, dy = x - sx, y - sy
    return (dx * ux + dy * uy, dx * nx + dy * ny, z)


def offset_polygon(poly: Sequence[Vec2], t: float) -> list[Vec2]:
    """Offset a CCW polygon outward by ``t`` with mitred corners."""
    n = len(poly)
    frames = wall_frames(poly)
    out = []
    for j in range(n):
        a, b = frames[j - 1], frames[j]
        # shifted lines: p = start + t * (-v_in) + s * u
        pa = (a["start"][0] - t * a["v_in"][0], a["start"][1] - t * a["v_in"][1])
        pb = (b["start"][0] - t * b["v_in"][0], b["start"][1] - t * b["v_in"][1])
        ua, ub = a["u"], b["u"]
        det = ua[0] * (-ub[1]) - ua[1] * (-ub[0])
        if abs(det) < 1e-9:
            out.append(pb)
            continue
        rx, ry = pb[0] - pa[0], pb[1] - pa[1]
        s = (rx * (-ub[1]) - ry * (-ub[0])) / det
        out.append((pa[0] + s * ua[0], pa[1] + s * ua[1]))
    return out


def bbox(poly: Sequence[Vec2]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def wall_uv(s: float, z: float, length: float, height: float) -> tuple[float, float]:
    return (1.0 - s / length if length > 0 else 0.0, z / height if height > 0 else 0.0)


def floor_uv(x: float, y: float, box: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = box
    return ((x - x0) / max(x1 - x0, 1e-9), (y - y0) / max(y1 - y0, 1e-9))


def free_intervals(length: float, blocked: Sequence[tuple[float, float]], min_len: float = 0.05) -> list[tuple[float, float]]:
    """Sub-intervals of [0, length] not covered by ``blocked`` (start, end) ranges."""
    cuts = sorted((max(0.0, a), min(length, b)) for a, b in blocked if b > 0 and a < length)
    out, cursor = [], 0.0
    for a, b in cuts:
        if a - cursor >= min_len:
            out.append((cursor, a))
        cursor = max(cursor, b)
    if length - cursor >= min_len:
        out.append((cursor, length))
    return out


def shell_edges_world(room_shell: dict) -> list[tuple[tuple[float, float, float], tuple[float, float, float], str]]:
    """3-D line segments of the shell (interior corners, floor/ceiling borders, openings).

    Used for overlays and wireframe fitting; tags: floor, ceiling, corner, opening.
    """
    poly = [tuple(p) for p in room_shell["floor_polygon"]]
    h = float(room_shell["ceiling_height"])
    segs = []
    frames = wall_frames(poly)
    for fr in frames:
        a, b = fr["start"], fr["end"]
        segs.append(((a[0], a[1], 0.0), (b[0], b[1], 0.0), "floor"))
        segs.append(((a[0], a[1], h), (b[0], b[1], h), "ceiling"))
        segs.append(((a[0], a[1], 0.0), (a[0], a[1], h), "corner"))
    walls = {w["edge"]: w for w in room_shell.get("walls", [])}
    for fr in frames:
        for op in walls.get(fr["edge"], {}).get("openings", []):
            s0, s1 = op["offset"], op["offset"] + op["width"]
            z0, z1 = op.get("sill", 0.0), op.get("sill", 0.0) + op["height"]
            c = [local_to_world(fr, s, 0.0, z) for s, z in ((s0, z0), (s1, z0), (s1, z1), (s0, z1))]
            for k in range(4):
                if k == 0 and z0 < 1e-3:
                    continue  # door threshold coincides with the floor line
                segs.append((c[k], c[(k + 1) % 4], "opening"))
    return segs
