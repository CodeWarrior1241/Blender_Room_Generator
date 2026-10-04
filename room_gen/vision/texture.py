"""Photo textures for shell surfaces by planar rectification (CLAUDE.md §8.8).

UV conventions come from :mod:`room_gen.shellgeom` so Blender maps them identically.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from room_gen import shellgeom
from room_gen.geometry import PinholeCamera, point_in_polygon


def _sample(rgb: np.ndarray, cam: PinholeCamera, world: np.ndarray, occluder: np.ndarray | None):
    """Sample the photo at world points; returns (colours HxWx3 uint8, valid HxW)."""
    shp = world.shape[:2]
    uv, z = cam.project(world.reshape(-1, 3))
    h, w = rgb.shape[:2]
    valid = (z > 0.05) & np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < w - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < h - 1)
    mx = np.where(valid, uv[:, 0] - 0.5, -1).astype(np.float32).reshape(shp)
    my = np.where(valid, uv[:, 1] - 0.5, -1).astype(np.float32).reshape(shp)
    img = cv2.remap(rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    valid = valid.reshape(shp)
    if occluder is not None:
        xi = np.clip(mx.astype(int), 0, w - 1)
        yi = np.clip(my.astype(int), 0, h - 1)
        valid &= ~occluder[yi, xi]
    return img, valid


def _fill(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Fill invalid texels: inpaint at low resolution, upsample into the holes."""
    if valid.all():
        return img
    h, w = valid.shape
    s = 256 / max(h, w)
    small = cv2.resize(img, (max(2, int(w * s)), max(2, int(h * s))), interpolation=cv2.INTER_AREA)
    vs = cv2.resize(valid.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    if vs.sum() == 0:
        mean = img[valid].mean(axis=0) if valid.any() else np.array([200, 200, 200])
        return np.broadcast_to(mean.astype(np.uint8), img.shape).copy()
    filled = cv2.inpaint(small, (1 - vs).astype(np.uint8) * 255, 7, cv2.INPAINT_TELEA)
    up = cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC)
    out = img.copy()
    out[~valid] = up[~valid]
    return out


def _texel_grid(span_a: float, span_b: float, max_px: int, px_per_m: float = 350.0) -> tuple[int, int]:
    a = max(16, int(round(span_a * px_per_m)))
    b = max(16, int(round(span_b * px_per_m)))
    k = min(1.0, max_px / max(a, b))
    return max(16, int(a * k)), max(16, int(b * k))


def rectify_shell(rgb: np.ndarray, cam: PinholeCamera, shell: dict, out_dir: str | Path, index: int, *,
                  occluder: np.ndarray | None = None, size: int = 2048, min_coverage: float = 0.05) -> dict:
    """Write photo textures for floor, ceiling and walls. Returns {surface: info}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    poly = [tuple(p) for p in shell["floor_polygon"]]
    height = float(shell["ceiling_height"])
    x0, y0, x1, y1 = shellgeom.bbox(poly)
    results: dict = {}

    def save(name, img, valid, inside):
        cov = float(valid[inside].mean()) if inside.any() else 0.0
        mean = img[valid].mean(axis=0) if valid.any() else None
        info = {"coverage": round(cov, 3), "mean_color": "#%02x%02x%02x" % tuple(int(c) for c in mean) if mean is not None else None}
        if cov >= min_coverage:
            filled = _fill(img, valid & inside)
            path = out_dir / f"{index}-world-tex-{name}.png"
            cv2.imwrite(str(path), cv2.cvtColor(filled, cv2.COLOR_RGB2BGR))
            info["path"] = str(path)
        results[name] = info

    # floor and ceiling: column -> x, row 0 -> max y
    tw, th = _texel_grid(x1 - x0, y1 - y0, size)
    xs = x0 + (np.arange(tw) + 0.5) / tw * (x1 - x0)
    ys = y1 - (np.arange(th) + 0.5) / th * (y1 - y0)
    gx, gy = np.meshgrid(xs, ys)
    inside = point_in_polygon(np.column_stack([gx.ravel(), gy.ravel()]), np.array(poly)).reshape(gx.shape)
    for name, z in (("floor", 0.0), ("ceiling", height)):
        world = np.dstack([gx, gy, np.full_like(gx, z)])
        img, valid = _sample(rgb, cam, world, occluder if name == "floor" else None)
        save(name, img, valid & inside, inside)
    # walls: column c -> s = L * (1 - (c + 0.5) / W), row 0 -> z = H
    for fr in shellgeom.wall_frames(poly):
        L = fr["length"]
        tw, th = _texel_grid(L, height, size)
        s = L * (1 - (np.arange(tw) + 0.5) / tw)
        z = height - (np.arange(th) + 0.5) / th * height
        gs, gz = np.meshgrid(s, z)
        sx, sy = fr["start"]
        ux, uy = fr["u"]
        world = np.dstack([sx + gs * ux, sy + gs * uy, gz])
        img, valid = _sample(rgb, cam, world, occluder)
        # the wall's front face must face the camera
        facing = (cam.C[0] - sx) * fr["v_in"][0] + (cam.C[1] - sy) * fr["v_in"][1] > 0
        if not facing:
            valid[:] = False
        save(f"wall-{fr['edge']}", img, valid, np.ones_like(valid))
    return results
