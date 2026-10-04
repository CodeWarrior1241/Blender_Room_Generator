"""Room layout: an axis-aligned box room explained by line evidence (CLAUDE.md §8.4).

Works in the calibration frame (camera above the origin). Edge index convention of the
resulting CCW polygon: 0 = front wall (y_min), 1 = right (x_max), 2 = back (y_max),
3 = left (x_min).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from room_gen.geometry import PinholeCamera
from room_gen.vision.lines import OrientedEdges
from scipy.optimize import differential_evolution

from room_gen.vision.wireframe import RegionColors, SegmentFamilies, box_room_edges, score, soft_value

PARAMS = ("x0", "x1", "y0", "y1", "h")
WALL_OF_PARAM = {"y0": 0, "x1": 1, "y1": 2, "x0": 3}


@dataclass
class Layout:
    x0: float
    x1: float
    y0: float
    y1: float
    h: float
    wall_support: list[float] = field(default_factory=lambda: [0.0] * 4)
    visible: list[bool] = field(default_factory=lambda: [False] * 4)
    ceiling_visible: bool = False
    confidence: float = 0.3
    sources: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_tuple(self) -> tuple[float, float, float, float, float]:
        return (self.x0, self.x1, self.y0, self.y1, self.h)

    def polygon(self) -> list[tuple[float, float]]:
        return [(self.x0, self.y0), (self.x1, self.y0), (self.x1, self.y1), (self.x0, self.y1)]


def _value(edges, cam, p, penalty=0.15) -> float:
    return score(edges, cam, box_room_edges(*p)).value(penalty)


def contain_camera(lay: "Layout", cam: PinholeCamera, margin: float = 0.3) -> bool:
    """Make sure the room contains the camera (and its height). Returns True if anything moved."""
    cx, cy = float(cam.C[0]), float(cam.C[1])
    before = lay.as_tuple()
    lay.x0, lay.x1 = min(lay.x0, cx - margin), max(lay.x1, cx + margin)
    lay.y0, lay.y1 = min(lay.y0, cy - margin), max(lay.y1, cy + margin)
    lay.h = max(lay.h, float(cam.C[2]) + 0.1)
    moved = lay.as_tuple() != before
    if moved:
        lay.notes.append("walls moved so the room contains the camera")
    return moved


def visible_floor_extent(cam: PinholeCamera, bounds: dict[str, float] | None = None) -> tuple[float, float, float, float] | None:
    """Bounding box of floor points seen along the image border (below the horizon),
    clipped at walls that are already known (``bounds`` holds any of x0, x1, y0, y1)."""
    w, h = cam.width, cam.height
    border = np.concatenate([
        np.column_stack([np.zeros(60) + 1, np.linspace(1, h - 1, 60)]),
        np.column_stack([np.zeros(60) + w - 1, np.linspace(1, h - 1, 60)]),
        np.column_stack([np.linspace(1, w - 1, 60), np.zeros(60) + h - 1]),
    ])
    pts, ok = cam.floor_point(border)
    pts = pts[ok]
    bounds = bounds or {}
    keep = np.linalg.norm(pts[:, :2] - cam.C[:2], axis=1) < 15
    if "x0" in bounds:
        keep &= pts[:, 0] >= bounds["x0"]
    if "x1" in bounds:
        keep &= pts[:, 0] <= bounds["x1"]
    if "y0" in bounds:
        keep &= pts[:, 1] >= bounds["y0"]
    if "y1" in bounds:
        keep &= pts[:, 1] <= bounds["y1"]
    pts = pts[keep]
    if len(pts) == 0:
        return None
    return float(pts[:, 0].min()), float(pts[:, 0].max()), float(pts[:, 1].min()), float(pts[:, 1].max())


def _corner_constraints(cam: PinholeCamera, corners_uv) -> dict[str, float]:
    fixed: dict[str, float] = {}
    if not corners_uv:
        return fixed
    pts, ok = cam.floor_point(corners_uv)
    for p, good in zip(pts, ok):
        if not good:
            continue
        x, y = float(p[0]), float(p[1])
        if y > cam.C[1]:
            fixed["y1"] = max(fixed.get("y1", -np.inf), y)
        else:
            fixed["y0"] = min(fixed.get("y0", np.inf), y)
        if x < cam.C[0]:
            fixed["x0"] = min(fixed.get("x0", np.inf), x)
        else:
            fixed["x1"] = max(fixed.get("x1", -np.inf), x)
    return fixed


def estimate_layout(
    edges: OrientedEdges,
    cam: PinholeCamera,
    *,
    corners_uv=None,
    ceiling_height: float | None = None,
    prior: dict[str, float] | None = None,
    defaults: dict | None = None,
    cycles: int = 2,
    seed: int = 0,
    restarts: int = 2,
    tau: float = 4.0,
    families: SegmentFamilies | None = None,
    orient_weight: float = 0.5,
    regions: RegionColors | None = None,
    region_weight: float | None = None,
    h_soft_min: float = 2.4,
    max_unseen: float = 4.0,
    hints: dict[str, OrientedEdges] | None = None,
    hint_weight: float = 3.0,
) -> Layout:
    """Coordinate search over the five box parameters, then visibility bookkeeping."""
    defaults = defaults or {}
    h_default = float(defaults.get("ceiling_height_m", 2.7))
    behind = float(defaults.get("behind_camera_m", 1.0))
    cxy = cam.C[:2]
    fixed = _corner_constraints(cam, corners_uv)
    if ceiling_height:
        fixed["h"] = float(ceiling_height)
    p = {"x0": cxy[0] - 2.0, "x1": cxy[0] + 2.0, "y0": cxy[1] - behind, "y1": cxy[1] + 4.0, "h": h_default}
    if prior:
        p.update({k: v for k, v in prior.items() if v is not None})
    p.update(fixed)
    h_lo = max(2.1, float(cam.C[2]) + 0.15)
    bounds = {
        "x0": (cxy[0] - 9.0, cxy[0] - 0.3),
        "x1": (cxy[0] + 0.3, cxy[0] + 9.0),
        "y0": (cxy[1] - 6.0, cxy[1] - 0.2),
        "y1": (cxy[1] + 0.6, cxy[1] + 14.0),
        "h": (max(h_lo, 2.2), max(h_lo, 2.2) + 2.0),
    }
    free = [k for k in PARAMS if k not in fixed]
    region_w = region_weight if region_weight is not None else 0.02 * cam.width

    def full(x):
        q = dict(p)
        q.update(dict(zip(free, x)))
        return tuple(q[k] for k in PARAMS)

    def objective(x, t=None):
        box = full(x)
        val = soft_value(edges, cam, box_room_edges(*box), tau=t or tau)
        if families is not None:
            val -= orient_weight * families.incompatible(cam, box)
        if regions is not None:
            val -= region_w * regions.energy(cam, box)
        if hints:
            tagged = box_room_edges(*box, tags=True)
            for kind, hedges in hints.items():
                prefix = {"wall_floor": "floor", "wall_ceiling": "ceiling", "wall_wall": "corner"}[kind]
                segs_k = [(a, b) for a, b, tag in tagged if tag.startswith(prefix)]
                val += hint_weight * soft_value(hedges, cam, segs_k, tau=t or tau, penalty=0.0)
        if "h" in free and box[4] < h_soft_min:
            val -= 400.0 * (h_soft_min - box[4])
        return -val

    start = dict(p)
    best_run: tuple[float, dict] | None = None
    for run_seed in range(seed, seed + max(1, restarts)):
        p = dict(start)
        if free:
            coarse = 2.0 * tau  # wider support band: broader peaks for the global stages
            res = differential_evolution(lambda x: objective(x, coarse), [bounds[k] for k in free], seed=run_seed, popsize=10, maxiter=40,
                                         tol=1e-7, init="sobol", polish=False, updating="deferred")
            p.update(dict(zip(free, (float(v) for v in res.x))))
            full_grid = {
                "x0": cxy[0] - np.geomspace(0.3, 9.0, 120), "x1": cxy[0] + np.geomspace(0.3, 9.0, 120),
                "y0": cxy[1] - np.geomspace(0.2, 6.0, 80), "y1": cxy[1] + np.geomspace(0.6, 14.0, 140),
                "h": np.linspace(bounds["h"][0], bounds["h"][1], 80),
            }

            def value(name, v, t=None):
                return -objective([float(v) if k == name else p[k] for k in free], t)

            def refine(name, centre, half, n=21):
                lo, hi = bounds[name]
                grid = np.clip(centre + np.linspace(-half, half, n), lo, hi)
                vals = [value(name, v) for v in grid]
                j = int(np.argmax(vals))
                return float(grid[j]), vals[j]

            def scale_ray(t=None) -> None:
                """Scan solutions scaled about the camera for every subset of walls together with the
                ceiling: a wall/ceiling line pair projects the same at (d, h) and (k d, k h); only the
                wall's floor line (camera height is fixed) tells them apart."""
                import itertools

                walls = [k for k in ("x0", "x1", "y0", "y1") if k in free]
                subsets = [c for r in range(1, len(walls) + 1) for c in itertools.combinations(walls, r)]
                base = dict(p)
                best_q, best_v = None, -objective([p[k] for k in free], t)
                for subset in subsets:
                    for lam in np.geomspace(0.35, 2.8, 48):
                        q = dict(base)
                        for k in subset:
                            c0 = cxy[0] if k[0] == "x" else cxy[1]
                            q[k] = c0 + lam * (base[k] - c0)
                        if "h" in free:
                            q["h"] = float(cam.C[2]) + lam * (base["h"] - float(cam.C[2]))
                        if any(not (bounds[k][0] <= q[k] <= bounds[k][1]) for k in free):
                            continue
                        v = -objective([q[k] for k in free], t)
                        if v > best_v + 1e-6:
                            best_q, best_v = q, v
                if best_q is not None:
                    p.update(best_q)

            scale_ray(coarse)
            scale_ray()
            current = -objective([p[k] for k in free])
            for _ in range(2):
                improved = False
                for name in free:
                    grid = full_grid[name]
                    vals = np.array([value(name, v, coarse) for v in grid])
                    peaks = [j for j in range(len(vals)) if (j == 0 or vals[j] >= vals[j - 1]) and (j == len(vals) - 1 or vals[j] >= vals[j + 1])]
                    peaks = sorted(peaks, key=lambda j: -vals[j])[:3]
                    for j in peaks:
                        step = abs(grid[min(j + 1, len(grid) - 1)] - grid[max(j - 1, 0)])
                        v, val = refine(name, float(grid[j]), step)
                        if val > current + 1e-6:
                            p[name], current, improved = v, val, True
                if not improved:
                    break
            scale_ray()
            current = -objective([p[k] for k in free])
            for _ in range(cycles):
                for name in free:
                    v, val = refine(name, p[name], 0.2, 41)
                    if val >= current:
                        p[name], current = v, val
        final = -objective([p[k] for k in free]) if free else 0.0
        if best_run is None or final > best_run[0]:
            best_run = (final, dict(p))
        if not free:
            break
    p = best_run[1]
    lay = Layout(**p)
    sc = score(edges, cam, box_room_edges(*lay.as_tuple(), tags=True), tau=tau)
    segs = box_room_edges(*lay.as_tuple(), tags=True)
    # wall support: floor + ceiling + corner edges belonging to each wall
    for wall in range(4):
        idx = [k for k, s in enumerate(segs) if s[2] in (f"floor{wall}", f"ceiling{wall}", f"corner{wall}", f"corner{(wall + 1) % 4}")]
        sup = sum(sc.per_segment[k][0] for k in idx)
        vis = sum(sc.per_segment[k][1] for k in idx)
        lay.wall_support[wall] = sup / vis if vis > 1 else 0.0
        lay.visible[wall] = vis > 0.04 * cam.width and lay.wall_support[wall] > 0.12
        if hints and not lay.visible[wall]:
            for kind, hedges in hints.items():
                prefix = {"wall_floor": "floor", "wall_ceiling": "ceiling", "wall_wall": "corner"}[kind]
                hs = score(hedges, cam, [(a, b) for k, (a, b, tag) in enumerate(segs) if k in idx and tag.startswith(prefix)], tau=tau)
                if hs.supported > 0.03 * cam.width:
                    lay.visible[wall] = True
                    lay.wall_support[wall] = max(lay.wall_support[wall], 0.5)
    ceil_idx = [k for k, s in enumerate(segs) if s[2].startswith("ceiling")]
    lay.ceiling_visible = sum(sc.per_segment[k][1] for k in ceil_idx) > 0.05 * cam.width and "h" not in fixed
    # unseen walls: just beyond the visible floor (clipped at the walls that are seen)
    known = {name: getattr(lay, name) for name, wall in WALL_OF_PARAM.items() if lay.visible[wall] or name in fixed}
    ext = visible_floor_extent(cam, known)
    if ext:
        fx0, fx1, fy0, fy1 = ext
        for name, wall in WALL_OF_PARAM.items():
            if lay.visible[wall] or name in fixed:
                continue
            # never further than max_unseen metres from the camera: a long floor ray along the
            # image border usually ends at furniture or a wall the lines did not pick up
            # the camera is inside the room, so an unseen wall is also at least half the
            # behind-camera distance past it (a sideways view can show floor on one side only)
            if name == "x0":
                lay.x0 = min(max(fx0 - 0.3, cxy[0] - max_unseen), cxy[0] - 0.5 * behind)
            elif name == "x1":
                lay.x1 = max(min(fx1 + 0.3, cxy[0] + max_unseen), cxy[0] + 0.5 * behind)
            elif name == "y1":
                lay.y1 = max(min(fy1 + 0.3, cxy[1] + max_unseen), cxy[1] + 0.5 * behind)
            elif name == "y0":
                lay.y0 = max(min(cxy[1] - behind, fy0 - 0.3), cxy[1] - max_unseen)
            lay.notes.append(f"wall {wall} ({name}) not visible; placed just beyond the visible floor")
    if not lay.ceiling_visible and "h" not in fixed and not (prior and prior.get("h")):
        lay.h = h_default
        lay.notes.append(f"ceiling not visible; assumed {h_default} m")
    contain_camera(lay, cam)
    lay.sources = {k: ("annotation" if k in fixed else "prior" if prior and k in prior else "lines") for k in PARAMS}
    seen = [lay.wall_support[w] for w in range(4) if lay.visible[w]]
    lay.confidence = round(float(min(1.0, (np.mean(seen) if seen else 0.0) * 1.2) * (0.5 + 0.125 * len(seen))), 3)
    return lay
