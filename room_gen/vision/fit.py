"""Render-and-compare refinement of camera and shell (CLAUDE.md §8.9), and overlays."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from room_gen import shellgeom
from room_gen.geometry import PinholeCamera
from room_gen.vision.lines import OrientedEdges
from room_gen.vision.wireframe import box_room_edges, chamfer, soft_value

ROOM_KEYS = ("x0", "x1", "y0", "y1", "h")


def _camera(cam: PinholeCamera, x) -> PinholeCamera:
    r = Rotation.from_rotvec(np.radians(x[:3])).as_matrix() @ cam.R
    f = cam.fx * math.exp(x[3])
    return PinholeCamera(f, f, cam.cx, cam.cy, cam.width, cam.height, r, cam.C.copy())


def fit_camera_and_room(edges: OrientedEdges, cam: PinholeCamera, layout: dict, *, free_walls: dict[str, bool],
                        fit_h: bool, max_evals: int = 400, tau: float = 2.0, fit_focal: bool = True) -> dict:
    """Refine camera rotation/focal and the visible room parameters against line evidence."""
    keys = [k for k in ROOM_KEYS if (k == "h" and fit_h) or free_walls.get(k)]
    p0 = {k: float(layout[k]) for k in ROOM_KEYS}
    sig_cam = np.array([0.6, 0.6, 0.6, 0.04 if fit_focal else 1e-9])
    sig_room = np.array([0.25] * len(keys))
    x0 = np.zeros(4 + len(keys))
    x0[4:] = [p0[k] for k in keys]
    vis0 = max(1.0, chamfer(edges, cam, box_room_edges(*(p0[k] for k in ROOM_KEYS)))[1])

    def unpack(x):
        q = dict(p0)
        q.update(dict(zip(keys, x[4:])))
        return _camera(cam, x), tuple(q[k] for k in ROOM_KEYS)

    def objective(x):
        c, room = unpack(x)
        if (room[4] <= c.C[2] + 0.05 or room[0] >= c.C[0] - 0.2 or room[1] <= c.C[0] + 0.2
                or room[2] >= c.C[1] - 0.2 or room[3] <= c.C[1] + 0.2):
            return 10.0
        data = soft_value(edges, c, box_room_edges(*room), tau=tau) / vis0
        z = np.concatenate([(x[:4]) / sig_cam, (x[4:] - x0[4:]) / sig_room]) if keys else x[:4] / sig_cam
        return -data + 0.004 * float(np.sum(z**2))

    before_cam, before_room = unpack(x0)
    before = chamfer(edges, before_cam, box_room_edges(*before_room))[0]
    simplex_scale = np.concatenate([[0.25, 0.25, 0.25, 0.015 if fit_focal else 0.0], [0.15] * len(keys)])
    init = np.vstack([x0] + [x0 + np.eye(len(x0))[i] * simplex_scale[i] for i in range(len(x0))])
    res = minimize(objective, x0, method="Nelder-Mead", options={"maxfev": max_evals, "initial_simplex": init, "xatol": 1e-4, "fatol": 1e-7})
    res2 = minimize(objective, res.x, method="Powell", options={"maxfev": max_evals // 2, "xtol": 1e-4, "ftol": 1e-7})
    best = res2.x if res2.fun < res.fun else res.x
    cam2, room2 = unpack(best)
    after = chamfer(edges, cam2, box_room_edges(*room2))[0]
    if after > before:  # never make it worse
        cam2, room2, after = before_cam, before_room, before
    return {
        "camera": cam2,
        "layout": dict(zip(ROOM_KEYS, (float(v) for v in room2))),
        "chamfer_before_px": round(before, 3),
        "chamfer_after_px": round(after, 3),
        "rotation_change_deg": round(float(np.linalg.norm(best[:3])), 3),
        "focal_change": round(float(math.exp(best[3]) - 1), 4),
        "evaluations": int(res.nfev + res2.nfev),
        "fitted": keys + ["camera"],
    }


def _polyline(img, cam: PinholeCamera, a, b, color, thickness=2, n: int = 80):
    t = np.linspace(0, 1, n)[:, None]
    pts = np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t
    uv, z = cam.project(pts)
    ok = (z > 0.05) & np.isfinite(uv).all(axis=1)
    for i in range(n - 1):
        if ok[i] and ok[i + 1]:
            p, q = uv[i], uv[i + 1]
            if max(abs(p).max(), abs(q).max()) < 1e5:
                cv2.line(img, (int(p[0]), int(p[1])), (int(q[0]), int(q[1])), color, thickness, cv2.LINE_AA)


def draw_overlay(rgb: np.ndarray, cam: PinholeCamera, room: dict, out_path: str | Path, object_boxes: list[dict] | None = None) -> Path:
    """Photo with the reprojected shell wireframe (yellow), openings (cyan) and objects (magenta)."""
    from room_gen.vision.objects import box_corners

    img = (rgb.astype(np.float32) * 0.75).astype(np.uint8).copy()
    th = max(2, int(round(max(rgb.shape[:2]) / 600)))
    for a, b, tag in shellgeom.shell_edges_world(room["shell"]):
        _polyline(img, cam, a, b, (80, 230, 255) if tag == "opening" else (255, 225, 40), th)
    for ob in object_boxes or []:
        c = box_corners(ob["position"][0], ob["position"][1], ob["position"][2], *ob["size"], ob["yaw"])
        for i, j in ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)):
            _polyline(img, cam, c[i], c[j], (255, 80, 220), max(1, th - 1), 20)
        uv, z = cam.project([[ob["position"][0], ob["position"][1], ob["position"][2] + ob["size"][2] + 0.05]])
        if z[0] > 0 and np.isfinite(uv).all():
            cv2.putText(img, ob["id"], (int(uv[0, 0]), int(uv[0, 1])), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * th, (255, 255, 255), th, cv2.LINE_AA)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return out_path
