"""Objects from 2-D boxes: mask, metric 3-D box fit, archetype recipe (CLAUDE.md §8.6).

Yaw convention: 0 means the object's front faces -Y; a front direction f has
yaw = atan2(f_x, -f_y) (degrees).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.optimize import least_squares

from room_gen import archetypes
from room_gen.geometry import PinholeCamera

WALL_YAW = {0: 180.0, 1: -90.0, 2: 0.0, 3: 90.0}  # facing away from wall edge i of a box room


@dataclass
class ObjectFit:
    id: str
    label: str
    archetype: str
    position: tuple[float, float, float]
    yaw: float
    size: tuple[float, float, float]
    support: str
    confidence: float
    colors: list[str] = field(default_factory=list)
    mask_area: int = 0
    notes: list[str] = field(default_factory=list)


def grabcut_mask(rgb: np.ndarray, box, iterations: int = 4) -> np.ndarray:
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    full = np.zeros((h, w), bool)
    if x1 - x0 < 4 or y1 - y0 < 4:
        full[y0 : y1 + 1, x0 : x1 + 1] = True
        return full
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, (x0, y0, x1 - x0, y1 - y0), bgd, fgd, iterations, cv2.GC_INIT_WITH_RECT)
        fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    except cv2.error:
        fg = np.zeros((h, w), bool)
    box_area = (x1 - x0 + 1) * (y1 - y0 + 1)
    if fg.sum() < 0.15 * box_area:
        fg = np.zeros((h, w), bool)
        fg[y0 : y1 + 1, x0 : x1 + 1] = True
    return fg


def dominant_colors(rgb: np.ndarray, mask: np.ndarray, k: int = 3) -> list[str]:
    px = rgb[mask].reshape(-1, 3).astype(np.float32)
    if len(px) < 20:
        return []
    lum = px.mean(axis=1)
    lo, hi = np.percentile(lum, [5, 90])
    px = px[(lum >= lo) & (lum <= hi)]
    if len(px) > 20000:
        px = px[np.random.default_rng(0).choice(len(px), 20000, replace=False)]
    k = min(k, max(1, len(px) // 50))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labels, centers = cv2.kmeans(px, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    return ["#%02x%02x%02x" % tuple(int(round(c)) for c in centers[i]) for i in order]


def box_corners(x, y, z0, w, d, h, yaw_deg) -> np.ndarray:
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    local = np.array([[sx * w / 2, sy * d / 2] for sx in (-1, 1) for sy in (-1, 1)])
    rot = local @ np.array([[c, s], [-s, c]])
    pts = []
    for z in (z0, z0 + h):
        for px, py in rot:
            pts.append((x + px, y + py, z))
    return np.array(pts)


def _bbox(cam: PinholeCamera, pts: np.ndarray) -> np.ndarray | None:
    uv, z = cam.project(pts)
    if (z <= 0.05).any():
        return None
    return np.array([uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()])


def fit_box(cam: PinholeCamera, obs_box, truncated, z0: float, size0, yaw_deg: float, *,
            depth_m: float | None = None, room=None) -> tuple[np.ndarray, float]:
    """Least-squares (x, y, w, d, h) so the projected box matches the mask's bounding box."""
    w0, d0, h0 = size0
    u0, v0, u1, v1 = obs_box
    base, ok = cam.intersect_plane([((u0 + u1) / 2, v1)], (0, 0, 1), -z0)
    if not ok[0]:
        base = cam.C + cam.rays([((u0 + u1) / 2, (v0 + v1) / 2)])[0] * 3.0
        base = np.array([[base[0], base[1], z0]])
    p = base[0][:2]
    away = p - cam.C[:2]
    away = away / max(np.linalg.norm(away), 1e-6)
    x_init = np.array([*(p + away * d0 / 2), math.log(w0), math.log(d0), math.log(h0)])
    sigma_px = max(2.0, 0.006 * cam.width)

    def fun(x):
        X, Y, lw, ld, lh = x
        w, d, h = math.exp(lw), math.exp(ld), math.exp(lh)
        bb = _bbox(cam, box_corners(X, Y, z0, w, d, h, yaw_deg))
        if bb is None:
            return np.full(9, 50.0)
        r = []
        for k in range(4):
            r.append(0.0 if truncated[k] else (bb[k] - obs_box[k]) / sigma_px)
        r += [(lw - math.log(w0)) / 0.45, (ld - math.log(d0)) / 0.45, (lh - math.log(h0)) / 0.45, ((ld - lw) - math.log(d0 / w0)) / 0.35]
        if depth_m is not None:
            front = np.array([X, Y, z0 + h / 2]) - cam.C
            r.append((np.linalg.norm(front) - d / 2 - depth_m) / (0.1 * depth_m))
        else:
            r.append(0.0)
        return np.array(r)

    lo = [-50, -50, math.log(0.02), math.log(0.005), math.log(0.005)]
    hi = [50, 50, math.log(6.0), math.log(6.0), math.log(3.5)]
    x0 = np.clip(x_init, lo, hi)
    sol = least_squares(fun, x0, bounds=(lo, hi), max_nfev=400)
    cost = float(np.sum(sol.fun[:4] ** 2))
    return sol.x, cost


def _nearest_wall(xy, room_box) -> tuple[int, float]:
    x0, x1, y0, y1 = room_box
    d = [xy[1] - y0, x1 - xy[0], y1 - xy[1], xy[0] - x0]
    i = int(np.argmin(d))
    return i, d[i]


def _toward(cam_xy, xy) -> float:
    f = np.asarray(cam_xy) - np.asarray(xy)
    yaw = math.degrees(math.atan2(f[0], -f[1]))
    return float(round(yaw / 90.0) * 90.0)


def fit_object(cam: PinholeCamera, rgb: np.ndarray, ann: dict, *, room_box, ceiling_h: float, mask: np.ndarray | None = None,
               supports: dict | None = None, depth: np.ndarray | None = None) -> ObjectFit:
    """Fit one annotated object (box in the working image's pixels)."""
    label = ann.get("label") or ann["id"]
    arch_name = ann.get("archetype")
    matched = True
    if not arch_name or arch_name not in archetypes.REGISTRY:
        arch_name, matched = archetypes.resolve(label)
    arch = archetypes.get(arch_name)
    notes = [] if matched else [f"label {label!r} matched no archetype; using {arch_name}"]
    if mask is None:
        mask = grabcut_mask(rgb, ann["box"])
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        x0b, y0b, x1b, y1b = ann["box"]
    else:
        x0b, y0b, x1b, y1b = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    h_img, w_img = mask.shape
    margin = 2
    truncated = [x0b <= margin, y0b <= margin, x1b >= w_img - margin, y1b >= h_img - margin]
    defaults = {**arch.defaults, **(ann.get("params") or {})}
    size0 = (float(defaults["width"]), float(defaults["depth"]), float(defaults["height"]))
    support = ann.get("support") or "floor"
    if support == "floor" and arch.support == "surface" and supports:
        for sid, sfit in supports.items():
            sb = sfit.get("box")
            if sb and sb[0] - 5 <= (x0b + x1b) / 2 <= sb[2] + 5 and sb[1] - 5 <= y1b <= sb[3] + 5:
                support = sid
                break
    z0 = 0.0
    if support not in ("floor", "wall", "ceiling") and supports and support in supports:
        z0 = float(supports[support]["top"])
    depth_m = None
    if depth is not None and mask.any():
        vals = depth[mask]
        vals = vals[np.isfinite(vals) & (vals > 0)]
        if len(vals) > 20:
            depth_m = float(np.percentile(vals, 30))
    obs = (float(x0b), float(y0b), float(x1b), float(y1b))
    base_pt, ok = cam.intersect_plane([((x0b + x1b) / 2, y1b)], (0, 0, 1), -z0)
    guess_xy = base_pt[0][:2] if ok[0] else cam.C[:2]
    candidates = []
    if arch.support == "ceiling" or support == "ceiling":
        z0 = max(0.0, ceiling_h - size0[2])
        support = "ceiling"
    if arch.against_wall or arch.support == "wall":
        wall, _ = _nearest_wall(guess_xy, room_box)
        candidates = [WALL_YAW[wall]]
    else:
        y_cam = _toward(cam.C[:2], guess_xy)
        candidates = [y_cam, y_cam + 90.0]
    best = None
    for yaw in candidates:
        sol = None
        if arch.support == "wall" or support == "wall":
            sol, cost = _fit_on_wall(cam, obs, truncated, size0, yaw, room_box)
            if cost >= 1e3:  # the box does not land on that wall: fit it as a free-standing item
                sol = None
                notes.append("could not place on a wall; fitted as a free-standing item")
        if sol is None:
            sol, cost = fit_box(cam, obs, truncated, z0, size0, yaw, depth_m=depth_m)
        if best is None or cost < best[1]:
            best = (sol, cost, yaw)
    sol, cost, yaw = best
    X, Y = float(sol[0]), float(sol[1])
    w, d, h = (float(math.exp(v)) for v in sol[2:5])
    rng = arch.ranges
    w = float(np.clip(w, *rng.get("width", (0.02, 6))))
    d = float(np.clip(d, *rng.get("depth", (0.005, 6))))
    h = float(np.clip(h, *rng.get("height", (0.005, 3.5))))
    zpos = z0 if len(sol) < 6 else float(sol[5])
    if arch.support == "ceiling":
        zpos = max(0.0, ceiling_h - h)
    # keep the footprint inside the room
    x0r, x1r, y0r, y1r = room_box
    odd = int(round(yaw / 90.0)) % 2 != 0
    half, half_y = ((d if odd else w) / 2, (w if odd else d) / 2)
    Xc = float(np.clip(X, x0r + half, x1r - half)) if x1r - x0r > 2 * half else (x0r + x1r) / 2
    Yc = float(np.clip(Y, y0r + half_y, y1r - half_y)) if y1r - y0r > 2 * half_y else (y0r + y1r) / 2
    if math.hypot(Xc - X, Yc - Y) > 0.05:
        notes.append(f"moved {math.hypot(Xc - X, Yc - Y):.2f} m to stay inside the room")
    conf = 0.75 if cost < 4 else 0.55 if cost < 25 else 0.35
    if any(truncated):
        conf *= 0.7
        notes.append("mask touches the image border; size partly from archetype defaults")
    if not matched:
        conf *= 0.8
    colors = dominant_colors(rgb, mask)
    return ObjectFit(ann["id"], label, arch_name, (Xc, Yc, zpos), float(yaw), (w, d, h), support, round(conf, 3), colors, int(mask.sum()), notes)


def _fit_on_wall(cam, obs, truncated, size0, yaw, room_box):
    """Wall-mounted items: back-project the box onto the nearest wall plane."""
    u0, v0, u1, v1 = obs
    x0r, x1r, y0r, y1r = room_box
    wall = {180.0: 0, -90.0: 1, 0.0: 2, 90.0: 3}.get(float(yaw), 2)
    normal, offset = {0: ((0, 1, 0), -y0r), 1: ((1, 0, 0), -x1r), 2: ((0, 1, 0), -y1r), 3: ((1, 0, 0), -x0r)}[wall]
    pts, ok = cam.intersect_plane([(u0, v1), (u1, v1), (u0, v0), ((u0 + u1) / 2, v1)], normal, offset)
    w0, d0, h0 = size0
    if not ok.all():
        return np.array([0, 0, math.log(w0), math.log(d0), math.log(h0)]), 1e3
    width = float(np.linalg.norm(pts[1, :2] - pts[0, :2]))
    height = float(abs(pts[2, 2] - pts[0, 2]))
    base = pts[3]
    inward = {0: (0, 1), 1: (-1, 0), 2: (0, -1), 3: (1, 0)}[wall]
    X, Y = base[0] + inward[0] * d0 / 2, base[1] + inward[1] * d0 / 2
    sol = np.array([X, Y, math.log(max(width, 0.02)), math.log(d0), math.log(max(height, 0.02)), float(base[2])])
    return sol, 1.0
