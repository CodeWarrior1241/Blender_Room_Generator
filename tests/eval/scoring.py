"""Score a reconstruction (room.json + recipes) against ground truth.

Truth comes from the synthetic scenes (tests/eval/scenes.py) or from SUN RGB-D frames
(tests/realdata). Both truth frames are gravity-aligned with the floor at z = 0, but a real
room need not be aligned with the world axes, so rotation is scored as gravity (tilt/roll)
plus yaw relative to the walls, and the floor overlap uses polygon intersection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from room_gen import archetypes
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json_if_exists


@dataclass
class Truth:
    camera: PinholeCamera
    polygon: np.ndarray  # (N, 2) CCW, metres
    ceiling: float
    objects: list[dict] = field(default_factory=list)  # id, archetype, matched, position (bottom centre), size (w, d, h), yaw


def _rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def align(cam_t: PinholeCamera, cam_e: PinholeCamera) -> tuple[np.ndarray, np.ndarray]:
    """(Q, b) mapping the estimated world into the truth world: X_t = Q X_e + b (yaw only)."""
    rel = cam_t.R.T @ cam_e.R
    q = _rot_z(math.atan2(rel[1, 0], rel[0, 0]))
    return q, cam_t.C - q @ cam_e.C


def polygon_iou(a: np.ndarray, b: np.ndarray, res: float = 0.02) -> float:
    pts = np.vstack([a, b])
    lo = pts.min(axis=0) - 0.1
    hi = pts.max(axis=0) + 0.1
    w, h = (int(math.ceil(v)) for v in (hi - lo) / res)
    if w * h > 4e7:
        res *= math.sqrt(w * h / 4e7)
        w, h = (int(math.ceil(v)) for v in (hi - lo) / res)
    def mask(p):
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.round((p - lo) / res).astype(np.int32)], 1)
        return m.astype(bool)
    ma, mb = mask(a), mask(b)
    union = (ma | mb).sum()
    return float((ma & mb).sum() / union) if union else 0.0


def visible_walls(cam: PinholeCamera, polygon: np.ndarray, ceiling: float) -> list[int]:
    out = []
    skip = virtual_edges(polygon, cam)
    for i in range(len(polygon)):
        if i in skip:
            continue
        a, b = polygon[i], polygon[(i + 1) % len(polygon)]
        d = b - a
        n_in = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
        if np.dot(cam.C[:2] - a, n_in) <= 0:
            continue
        t = np.linspace(0.05, 0.95, 15)
        pts = np.concatenate([np.column_stack([a[0] + t * d[0], a[1] + t * d[1], np.full(15, z)]) for z in (0.3, ceiling / 2, ceiling - 0.3)])
        uv, z = cam.project(pts)
        ok = (z > 0.2) & (uv[:, 0] >= 0) & (uv[:, 0] < cam.width) & (uv[:, 1] >= 0) & (uv[:, 1] < cam.height)
        if ok.mean() > 0.2:
            out.append(i)
    return out


def _wall_error(truth_poly: np.ndarray, est_poly: np.ndarray, edges: list[int]) -> float | None:
    errs = []
    for i in edges:
        a, b = truth_poly[i], truth_poly[(i + 1) % len(truth_poly)]
        d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        mid = (a + b) / 2
        best = None
        for j in range(len(est_poly)):
            p, q = est_poly[j], est_poly[(j + 1) % len(est_poly)]
            e = (q - p) / max(np.linalg.norm(q - p), 1e-9)
            if abs(float(np.dot(d, e))) < 0.9:
                continue
            n = np.array([-e[1], e[0]])
            dist = abs(float(np.dot(mid - p, n)))
            best = dist if best is None else min(best, dist)
        if best is not None:
            errs.append(best)
    return float(np.mean(errs)) if errs else None


LABELS = ("floor", "ceiling", "left", "front", "right")


def virtual_edges(poly: np.ndarray, cam: PinholeCamera, radius: float = 0.3) -> set[int]:
    """Edges touching a vertex at the camera: SUN RGB-D draws partially seen rooms as the visible
    region fanned out from the camera, so those edges are view boundaries, not walls."""
    n = len(poly)
    near = [float(np.linalg.norm(poly[i] - cam.C[:2])) < radius for i in range(n)]
    return {i for i in range(n) if near[i] or near[(i + 1) % n]}


def layout_labels(cam: PinholeCamera, poly: np.ndarray, height: float, grid: tuple[int, int] = (80, 60), skip_edges: set[int] | None = None):
    """Per-pixel surface label (LSUN-style: floor, ceiling, left/front/right wall relative to the
    camera; -1 = ray leaves the room) and ray length to the layout surface, on a coarse grid."""
    gw, gh = grid
    vs, us = np.mgrid[0:gh, 0:gw]
    uv = np.column_stack([(us.ravel() + 0.5) * cam.width / gw, (vs.ravel() + 0.5) * cam.height / gh])
    d = cam.rays(uv)
    c = cam.C
    n = len(d)
    best_t = np.full(n, np.inf)
    label = np.full(n, -1)
    with np.errstate(divide="ignore", invalid="ignore"):
        for lab, z in ((0, 0.0), (1, height)):
            t = (z - c[2]) / d[:, 2]
            p = c + d * t[:, None]
            inside = _points_in_poly(p[:, :2], poly)
            ok = (t > 1e-6) & inside & (t < best_t)
            best_t[ok], label[ok] = t[ok], lab
        fwd = cam.R[2, :2] / max(np.linalg.norm(cam.R[2, :2]), 1e-9)
        right = cam.R[0, :2] / max(np.linalg.norm(cam.R[0, :2]), 1e-9)
        for i in range(len(poly)):
            if skip_edges and i in skip_edges:
                continue
            a, b = poly[i], poly[(i + 1) % len(poly)]
            e = b - a
            length = np.linalg.norm(e)
            if length < 1e-6:
                continue
            nrm = np.array([-e[1], e[0]]) / length  # inward for CCW
            denom = d[:, :2] @ nrm
            t = ((a - c[:2]) @ nrm) / denom
            p = c + d * t[:, None]
            s_ = ((p[:, :2] - a) @ e) / length**2
            ok = (t > 1e-6) & (s_ >= 0) & (s_ <= 1) & (p[:, 2] >= 0) & (p[:, 2] <= height) & (t < best_t)
            facing = -nrm  # direction the wall lies in, as seen from inside
            ang = math.degrees(math.atan2(float(facing @ right), float(facing @ fwd)))
            lab = 3 if abs(ang) < 45 else (4 if ang > 0 else 2)
            best_t[ok], label[ok] = t[ok], lab
    return label, np.where(np.isfinite(best_t), best_t, np.nan)


def _points_in_poly(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    from room_gen.geometry import point_in_polygon

    return point_in_polygon(pts, poly)


def layout_errors(truth: Truth, cam_e: PinholeCamera, poly_e: np.ndarray, height_e: float) -> dict:
    lt, dt = layout_labels(truth.camera, truth.polygon, truth.ceiling, skip_edges=virtual_edges(truth.polygon, truth.camera))
    le, de = layout_labels(cam_e, poly_e, height_e)
    valid = lt >= 0
    both = valid & (le >= 0) & np.isfinite(dt) & np.isfinite(de)
    k = truth.camera.C[2] / cam_e.C[2]
    out = {"layout_pixel_err_pct": round(100 * float((le[valid] != lt[valid]).mean()), 1) if valid.any() else None}
    if both.any():
        out["layout_depth_err_pct"] = round(100 * float(np.median(np.abs(de[both] - dt[both]) / dt[both])), 1)
        out["layout_depth_err_scaled_pct"] = round(100 * float(np.median(np.abs(k * de[both] - dt[both]) / dt[both])), 1)
    return out


def _dominant_angle(poly: np.ndarray) -> float:
    lens = [np.linalg.norm(poly[(i + 1) % len(poly)] - poly[i]) for i in range(len(poly))]
    i = int(np.argmax(lens))
    d = poly[(i + 1) % len(poly)] - poly[i]
    return math.degrees(math.atan2(d[1], d[0]))


def score(truth: Truth, room: dict, world_dir: str | Path) -> dict:
    cam_t = truth.camera
    cam_e = PinholeCamera.from_dict(room["camera"])
    q, b = align(cam_t, cam_e)
    est_poly = np.array([q[:2, :2] @ p + b[:2] for p in np.array(room["shell"]["floor_polygon"], float)])
    vis = visible_walls(cam_t, truth.polygon, truth.ceiling)
    up_t, up_e = cam_t.R[:, 2], cam_e.R[:, 2]
    gravity = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(up_t, up_e))))))
    yaw_t = _dominant_angle(truth.polygon) % 90.0
    yaw_e = math.degrees(math.atan2(q[1, 0], q[0, 0]) + math.atan2(*(np.array(room["shell"]["floor_polygon"][1]) - np.array(room["shell"]["floor_polygon"][0]))[::-1])) % 90.0
    dyaw = abs(yaw_t - yaw_e) % 90.0
    res = {
        "focal_err_pct": round(100 * abs(cam_e.fx - cam_t.fx) / cam_t.fx, 2),
        "gravity_err_deg": round(gravity, 3),
        "yaw_err_deg": round(min(dyaw, 90.0 - dyaw), 2),
        "camera_height_err_pct": round(100 * abs(cam_e.C[2] - cam_t.C[2]) / cam_t.C[2], 1),
        "ceiling_err_m": round(abs(room["shell"]["ceiling_height"] - truth.ceiling), 3),
        "floor_iou": round(polygon_iou(truth.polygon, est_poly), 3),
        **layout_errors(truth, cam_e, np.array(room["shell"]["floor_polygon"], float), float(room["shell"]["ceiling_height"])),
        "visible_walls": len(vis),
        "visible_wall_err_m": (lambda v: round(v, 3) if v is not None else None)(_wall_error(truth.polygon, est_poly, vis)),
    }
    # objects: same archetype, nearest within 1 m in the truth frame
    targets = [o for o in truth.objects if o.get("matched", True)]
    used: set[str] = set()
    pos_err, size_err = [], []
    for pl in room.get("placements", []):
        rec = read_json_if_exists(Path(world_dir) / "output" / pl["object"] / "recipe.json") or {}
        arch = rec.get("archetype")
        p = q @ np.array(pl["position"], float) + b
        cands = [(float(np.linalg.norm(np.array(t["position"][:2]) - p[:2])), t) for t in targets
                 if t["id"] not in used and archetypes.resolve(t["archetype"])[0] == arch]
        if not cands:
            continue
        dist, t = min(cands, key=lambda c: c[0])
        if dist > 1.0:
            continue
        used.add(t["id"])
        pos_err.append(dist)
        want = [*sorted(t["size"][:2]), t["size"][2]]
        got_raw = pl.get("size_m") or t["size"]
        got = [*sorted(got_raw[:2]), got_raw[2]]
        size_err.append(float(np.mean([abs(g - w) / max(w, 1e-3) for g, w in zip(got, want)])))
    res["objects_matched"] = f"{len(pos_err)}/{len(targets)}"
    res["object_pos_err_m"] = round(float(np.median(pos_err)), 3) if pos_err else None
    res["object_size_err_pct"] = round(100 * float(np.median(size_err)), 1) if size_err else None
    return res
