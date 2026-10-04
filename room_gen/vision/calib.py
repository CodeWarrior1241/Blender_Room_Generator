"""Camera calibration from vanishing points (CLAUDE.md §8.3).

Manhattan-world assumption: walls, floor and most furniture align with three orthogonal
directions. Each image segment defines an interpretation plane through the camera
centre; a world direction ``d`` is consistent with a segment when ``n . d = 0``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from room_gen.geometry import PinholeCamera, orthonormalize
from room_gen.vision.lines import lengths

SIN_INLIER = math.sin(math.radians(1.5))
SIN_ASSIGN = math.sin(math.radians(3.0))
AXES = ("x", "y", "z")


@dataclass
class CalibResult:
    f: float
    cx: float
    cy: float
    R: np.ndarray  # world -> camera
    width: int
    height: int
    labels: np.ndarray  # per segment: 0/1/2 world axis, -1 none
    residual_deg: float
    inlier_fraction: float
    finite_vps: int
    confidence: float
    method: str
    focal_source: str
    notes: list[str] = field(default_factory=list)

    def camera(self, height_m: float = 1.0) -> PinholeCamera:
        return PinholeCamera(self.f, self.f, self.cx, self.cy, self.width, self.height, self.R, (0.0, 0.0, height_m))

    def vanishing_points(self) -> list[dict]:
        k = np.array([[self.f, 0, self.cx], [0, self.f, self.cy], [0, 0, 1.0]])
        out = []
        for i, axis in enumerate(AXES):
            d = self.R[:, i]
            v = k @ d
            out.append({"axis": axis, "point": (v / v[2]).tolist() if abs(v[2]) > 1e-9 else v.tolist(),
                        "direction_cam": d.tolist(), "inliers": int(np.sum(self.labels == i))})
        return out

    def scaled(self, s: float) -> "CalibResult":
        """The same calibration for an image resized by ``s``."""
        return CalibResult(self.f * s, self.cx * s, self.cy * s, self.R.copy(), int(round(self.width * s)), int(round(self.height * s)),
                           self.labels.copy(), self.residual_deg, self.inlier_fraction, self.finite_vps, self.confidence,
                           self.method, self.focal_source, list(self.notes))


def interpretation_normals(segs: np.ndarray, f: float, cx: float, cy: float) -> np.ndarray:
    ones = np.ones(len(segs))
    r1 = np.column_stack([(segs[:, 0] - cx) / f, (segs[:, 1] - cy) / f, ones])
    r2 = np.column_stack([(segs[:, 2] - cx) / f, (segs[:, 3] - cy) / f, ones])
    n = np.cross(r1, r2)
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def _scores(normals: np.ndarray, weights: np.ndarray, frames: np.ndarray, thr: float, chunk: int = 512) -> np.ndarray:
    out = np.empty(len(frames))
    for s in range(0, len(frames), chunk):
        res = np.abs(np.einsum("nk,mkj->mnj", normals, frames[s : s + chunk]))
        best = res.min(axis=2)
        out[s : s + chunk] = ((best < thr) * weights[None, :]).sum(axis=1)
    return out


def ransac_frames(normals: np.ndarray, weights: np.ndarray, rng: np.random.Generator, iters: int = 2500, top: int = 3):
    n = len(normals)
    p = weights / weights.sum()
    a, b, c = (rng.choice(n, iters, p=p) for _ in range(3))
    d1 = np.cross(normals[a], normals[b])
    n1 = np.linalg.norm(d1, axis=1)
    d1 = d1 / np.maximum(n1, 1e-12)[:, None]
    d2 = np.cross(d1, normals[c])
    n2 = np.linalg.norm(d2, axis=1)
    d2 = d2 / np.maximum(n2, 1e-12)[:, None]
    d3 = np.cross(d1, d2)
    ok = (n1 > 1e-4) & (n2 > 1e-4)
    frames = np.stack([d1, d2, d3], axis=2)[ok]
    if len(frames) == 0:
        return [], []
    scores = _scores(normals, weights, frames, SIN_INLIER)
    order = np.argsort(-scores)[:top]
    return [frames[i] for i in order], [float(scores[i]) for i in order]


def assign(normals: np.ndarray, frame: np.ndarray, thr: float = SIN_ASSIGN) -> np.ndarray:
    res = np.abs(normals @ frame)
    lab = res.argmin(axis=1)
    lab[res.min(axis=1) >= thr] = -1
    return lab


def refine(segs, weights, frame0, f0, cx, cy, *, optimize_f=True, f_prior=None, f_sigma=0.3, rounds=3):
    """Jointly refine rotation (and focal) from segment-to-axis consistency."""
    frame, f = frame0.copy(), f0
    labels = assign(interpretation_normals(segs, f, cx, cy), frame)
    for _ in range(rounds):
        idx = np.where(labels >= 0)[0]
        if len(idx) < 4:
            break
        sw = np.sqrt(weights[idx])
        lab = labels[idx]
        scale = SIN_INLIER

        def fun(x, idx=idx, sw=sw, lab=lab, frame=frame, f=f):
            ff = f * math.exp(x[3]) if optimize_f else f
            n = interpretation_normals(segs[idx], ff, cx, cy)
            fr = Rotation.from_rotvec(x[:3]).as_matrix() @ frame
            r = np.einsum("nk,kn->n", n, fr[:, lab]) * sw
            if optimize_f and f_prior:
                r = np.append(r, (math.log(ff) - math.log(f_prior)) / f_sigma * scale * math.sqrt(3.0))
            return r

        x0 = np.zeros(4 if optimize_f else 3)
        sol = least_squares(fun, x0, loss="soft_l1", f_scale=scale, max_nfev=200)
        frame = Rotation.from_rotvec(sol.x[:3]).as_matrix() @ frame
        if optimize_f:
            f = f * math.exp(sol.x[3])
        labels = assign(interpretation_normals(segs, f, cx, cy), frame)
    return orthonormalize(frame), f, labels


def world_axes(frame: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Order/sign a Manhattan frame as world X (rightish), Y (forward), Z (up)."""
    cols = [frame[:, i] for i in range(3)]
    kz = int(np.argmax([abs(c[1]) for c in cols]))
    z = cols[kz] * (-np.sign(cols[kz][1]) or 1.0)
    rest = [i for i in range(3) if i != kz]
    kx = max(rest, key=lambda i: abs(cols[i][0]))
    x = cols[kx] * (np.sign(cols[kx][0]) or 1.0)
    y = np.cross(z, x)
    ky = [i for i in rest if i != kx][0]
    return np.column_stack([x, y, z]), [kx, ky, kz]


def _finite_count(R: np.ndarray, thr: float = 0.06) -> int:
    return int(sum(abs(R[2, i]) > thr for i in range(3)))


def _summarise(segs, weights, R, f, cx, cy, w, h, method, focal_source, notes, prior_ratio=None) -> CalibResult:
    normals = interpretation_normals(segs, f, cx, cy)
    labels = assign(normals, R)
    res = np.abs(normals @ R)
    inl = labels >= 0
    frac = float(weights[inl].sum() / max(weights.sum(), 1e-9))
    resid = float(np.degrees(np.arcsin(np.median(res.min(axis=1)[inl])))) if inl.any() else 90.0
    finite = _finite_count(R)
    conf = min(1.0, frac * 1.3) * (1.0 if finite >= 2 else 0.6)
    if prior_ratio is not None and abs(math.log(prior_ratio)) > math.log(1.15):
        conf *= 0.75
        notes.append(f"focal differs from the EXIF prior by {abs(prior_ratio - 1):.0%}")
    if finite < 2:
        notes.append("fewer than two finite vanishing points: focal length taken from the prior")
    return CalibResult(f, cx, cy, R, w, h, labels, resid, frac, finite, round(conf, 3), method, focal_source, notes)


def calibrate_auto(segs: np.ndarray, width: int, height: int, *, focal_prior: float | None = None, seed: int = 0) -> CalibResult:
    """Manhattan frame and focal length from line segments (working-resolution pixels)."""
    if len(segs) < 5:
        raise ValueError(f"only {len(segs)} line segments; cannot calibrate")
    rng = np.random.default_rng(seed)
    cx, cy = width / 2.0, height / 2.0
    weights = lengths(segs)
    weights = weights / np.median(weights)
    if focal_prior:
        f_candidates = [focal_prior * k for k in (0.8, 0.9, 1.0, 1.12, 1.25)]
        prior, sigma, source = focal_prior, 0.1, "exif+vanishing-points"
    else:
        f_candidates = [(width / 2) / math.tan(math.radians(fov) / 2) for fov in range(40, 106, 6)]
        prior, sigma, source = (width / 2) / math.tan(math.radians(60) / 2), 0.6, "vanishing-points"
    hyps = []
    for f in f_candidates:
        normals = interpretation_normals(segs, f, cx, cy)
        frames, scores = ransac_frames(normals, weights, rng)
        hyps += [(s, f, fr) for fr, s in zip(frames, scores)]
    hyps.sort(key=lambda t: -t[0])
    best = None
    for _, f0, fr0 in hyps[:6]:
        fr, f, labels = refine(segs, weights, fr0, f0, cx, cy, optimize_f=True, f_prior=prior, f_sigma=sigma)
        normals = interpretation_normals(segs, f, cx, cy)
        score = float(_scores(normals, weights, fr[None], SIN_INLIER)[0])
        if best is None or score > best[0]:
            best = (score, f, fr)
    _, f, fr = best
    R, _ = world_axes(fr)
    if _finite_count(R) < 2:
        f = focal_prior or prior
        fr2, _, _ = refine(segs, weights, R, f, cx, cy, optimize_f=False)
        R, _ = world_axes(fr2)
        source = "exif" if focal_prior else "default-60deg"
    return _summarise(segs, weights, R, f, cx, cy, width, height, "auto-vp", source, [],
                      prior_ratio=(f / focal_prior) if focal_prior else None)


def vp_from_lines(lines) -> np.ndarray:
    hom = []
    for (x1, y1), (x2, y2) in lines:
        l = np.cross([x1, y1, 1.0], [x2, y2, 1.0])
        hom.append(l / np.linalg.norm(l[:2]))
    _, _, vt = np.linalg.svd(np.array(hom))
    return vt[-1]


def calibrate_manual(hints: dict, width: int, height: int, *, segs: np.ndarray | None = None, scale: float = 1.0,
                     focal_prior: float | None = None) -> CalibResult:
    """fSpy-style calibration from annotated parallel line pairs (native pixels * scale)."""
    cx, cy = (np.array(hints["principal_point"]) * scale) if hints.get("principal_point") else (width / 2.0, height / 2.0)
    vps: dict[str, np.ndarray] = {}
    for pair in hints.get("parallel_pairs", []):
        vps[pair["axis"]] = vp_from_lines([[(x * scale, y * scale) for x, y in line] for line in pair["lines"]])
    if hints.get("vertical_lines") and "z" not in vps and len(hints["vertical_lines"]) >= 2:
        vps["z"] = vp_from_lines([[(x * scale, y * scale) for x, y in line] for line in hints["vertical_lines"]])
    if len(vps) < 2:
        raise ValueError("manual calibration needs vanishing points for at least two axes")
    c = np.array([cx, cy])
    f_est = []
    keys = list(vps)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = vps[keys[i]], vps[keys[j]]
            if abs(a[2]) < 1e-9 or abs(b[2]) < 1e-9:
                continue
            f2 = -float(np.dot(a[:2] / a[2] - c, b[:2] / b[2] - c))
            if f2 > 0:
                f_est.append(math.sqrt(f2))
    if hints.get("focal_px"):
        f, source = float(hints["focal_px"]) * scale, "annotation"
    elif f_est:
        f, source = float(np.median(f_est)), "manual-vanishing-points"
    elif focal_prior:
        f, source = focal_prior, "exif"
    else:
        f, source = (width / 2) / math.tan(math.radians(30)), "default-60deg"
    kinv = np.linalg.inv(np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]]))
    dirs = {k: (kinv @ v) / np.linalg.norm(kinv @ v) for k, v in vps.items()}
    if "z" in dirs:
        dirs["z"] = dirs["z"] * (-np.sign(dirs["z"][1]) or 1.0)
    if "x" in dirs:
        dirs["x"] = dirs["x"] * (np.sign(dirs["x"][0]) or 1.0)
    if "y" in dirs:
        dirs["y"] = dirs["y"] * (np.sign(dirs["y"][2]) or 1.0)
    if "x" in dirs and "y" in dirs:
        z = np.cross(dirs["x"], dirs["y"])
        m = np.column_stack([dirs["x"], dirs["y"], z * (-np.sign(z[1]) or 1.0)])
    elif "x" in dirs and "z" in dirs:
        m = np.column_stack([dirs["x"], np.cross(dirs["z"], dirs["x"]), dirs["z"]])
    else:
        x = np.cross(dirs["y"], dirs["z"])
        m = np.column_stack([x, dirs["y"], dirs["z"]])
    R, _ = world_axes(orthonormalize(m))
    method, notes = "manual-vp", []
    weights = lengths(segs) / max(np.median(lengths(segs)), 1e-9) if segs is not None and len(segs) else None
    if segs is not None and len(segs) >= 8:
        fr, f2, _ = refine(segs, weights, R, f, cx, cy, optimize_f=not hints.get("focal_px"), f_prior=f, f_sigma=0.05)
        if rotation_delta(R, fr) < 5.0:
            R, _ = world_axes(fr)
            f = f2
            method = "manual-vp+auto-refine"
    if weights is None:
        weights = np.ones(0)
        segs = np.zeros((0, 4))
    if len(segs) == 0:
        return CalibResult(f, cx, cy, R, width, height, np.zeros(0, int), 0.0, 1.0, _finite_count(R), 0.85, method, source, notes)
    return _summarise(segs, weights, R, f, cx, cy, width, height, method, source, notes)


def rotation_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Smallest rotation angle (deg) between two Manhattan frames, ignoring axis order/sign."""
    m = np.abs(a.T @ b)
    return float(np.degrees(np.arccos(np.clip(m.max(axis=1).min(), -1, 1))))


# ----- metric scale ----------------------------------------------------------------------


def height_from_reference(cam: PinholeCamera, bottom_uv, top_uv, metres: float) -> float | None:
    """Camera height from a vertical of known length standing on the floor (cam at height 1)."""
    pb, ok = cam.floor_point([bottom_uv])
    if not ok[0]:
        return None
    pb = pb[0]
    d = cam.rays([top_uv])[0]
    # closest point between ray C + t d and vertical line pb + s e_z
    e = np.array([0.0, 0.0, 1.0])
    w0 = cam.C - pb
    a, b, c = d @ d, d @ e, e @ e
    dd, ee = d @ w0, e @ w0
    den = a * c - b * b
    if abs(den) < 1e-9:
        return None
    s = (a * ee - b * dd) / den
    if s <= 1e-6:
        return None
    return metres / s * cam.C[2]


def height_from_floor_length(cam: PinholeCamera, uv_a, uv_b, metres: float) -> float | None:
    pts, ok = cam.floor_point([uv_a, uv_b])
    if not ok.all():
        return None
    dist = float(np.linalg.norm(pts[0, :2] - pts[1, :2]))
    return metres / dist * cam.C[2] if dist > 1e-9 else None
