"""Metric monocular depth (Depth Anything V2, metric indoor) and what it tells the layout."""

from __future__ import annotations

import numpy as np

from room_gen.geometry import PinholeCamera
from room_gen.ml.runtime import load


def estimate_depth(rgb: np.ndarray, repo: str, device: str) -> np.ndarray:
    """Per-pixel metric depth (metres along the optical axis), same size as ``rgb``."""
    import torch
    from PIL import Image

    proc, model, dtype = load("depth", repo, device)
    img = Image.fromarray(rgb)
    with torch.no_grad():
        inputs = proc(images=img, return_tensors="pt").to(device)
        inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
        out = model(**inputs)
    post = proc.post_process_depth_estimation(out, target_sizes=[(rgb.shape[0], rgb.shape[1])])
    depth = post[0]["predicted_depth"].float().cpu().numpy()
    return np.where(np.isfinite(depth) & (depth > 0), depth, np.nan).astype(np.float32)


def world_points(depth: np.ndarray, cam: PinholeCamera, step: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Back-project every ``step``-th pixel into the camera-centred, gravity-aligned frame.

    Returns (points Nx3 relative to the camera centre, pixel uv Nx2).
    """
    h, w = depth.shape
    vs, us = np.mgrid[step // 2 : h : step, step // 2 : w : step]
    uv = np.column_stack([us.ravel() + 0.5, vs.ravel() + 0.5])
    z = depth[vs.ravel(), us.ravel()]
    ok = np.isfinite(z) & (z > 0.1) & (z < 30)
    uv, z = uv[ok], z[ok]
    xc = np.column_stack([(uv[:, 0] - cam.cx) / cam.fx * z, (uv[:, 1] - cam.cy) / cam.fy * z, z])
    return xc @ cam.R, uv  # R^T applied: camera -> world axes


def camera_height(points: np.ndarray) -> float | None:
    """Height of the camera above the floor: the LOWEST horizontal plane with real support.

    Big furniture tops (sofa seats, beds, tables) form horizontal planes too and can hold
    more points than a barely visible floor, so the dominant plane is not used.
    """
    zs = points[:, 2]
    below = zs[zs < -0.25]
    if len(below) < 200:
        return None
    hist, edges = np.histogram(below, bins=np.arange(below.min(), below.max() + 0.03, 0.03))
    smooth = np.convolve(hist, [1, 2, 1], mode="same")
    need = max(0.02 * len(points), 0.15 * smooth.max())
    for k in range(len(smooth)):
        left = smooth[k - 1] if k > 0 else -1
        right = smooth[k + 1] if k + 1 < len(smooth) else -1
        if smooth[k] >= need and smooth[k] >= left and smooth[k] >= right:
            z0 = 0.5 * (edges[k] + edges[k + 1])
            sel = below[np.abs(below - z0) < 0.06]
            return float(-np.median(sel)) if len(sel) else float(-z0)
    return None


def layout_prior(points: np.ndarray, cam_height: float) -> dict[str, float]:
    """Wall and ceiling positions from the extremes of the point cloud (camera-centred frame,
    shifted so the camera is at height ``cam_height`` above the floor)."""
    p = points.copy()
    p[:, 2] += cam_height
    mid = p[(p[:, 2] > 0.25) & (p[:, 2] < 2.0)]
    prior: dict[str, float] = {}
    if len(mid) > 500:
        prior["x0"] = float(np.percentile(mid[:, 0], 1.0))
        prior["x1"] = float(np.percentile(mid[:, 0], 99.0))
        prior["y1"] = float(np.percentile(mid[:, 1], 99.0))
    high = p[p[:, 2] > cam_height + 0.3]
    if len(high) > 300:
        prior["h"] = float(np.percentile(high[:, 2], 97.0))
    return prior
