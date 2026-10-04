"""Lighting from image statistics (CLAUDE.md §8.7). Deliberately low confidence."""

from __future__ import annotations

import math

import numpy as np

from room_gen import shellgeom


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(np.clip(round(c), 0, 255)) for c in rgb)


def _tint(rgb, keep: float = 0.35) -> np.ndarray:
    """Normalise a colour to white-ish keeping a fraction of its chroma."""
    rgb = np.asarray(rgb, float)
    rgb = rgb / max(rgb.max(), 1e-6) * 255.0
    return 255.0 * (1 - keep) + rgb * keep


def estimate_lighting(rgb: np.ndarray, shell: dict) -> dict:
    px = rgb.reshape(-1, 3).astype(np.float64)
    lum = px @ np.array([0.2126, 0.7152, 0.0722])
    mean_rgb = px.mean(axis=0)
    bright = px[lum >= np.percentile(lum, 99)]
    sun_rgb = bright.mean(axis=0) if len(bright) else mean_rgb
    log_mean = float(np.exp(np.mean(np.log(lum / 255.0 + 1e-4))))
    exposure = float(np.clip(math.log2(0.18 / max(log_mean, 1e-4)) * 0.35, -1.0, 1.0))
    windows = []
    frames = {f["edge"]: f for f in shellgeom.wall_frames([tuple(p) for p in shell["floor_polygon"]])}
    for wall in shell.get("walls", []):
        for op in wall.get("openings", []):
            if op["kind"] == "window":
                windows.append((frames[wall["edge"]], op))
    lighting: dict = {
        "sky": {"strength": round(0.5 + 0.6 * min(1.0, log_mean * 3), 3), "color": _hex(_tint(mean_rgb, 0.25))},
        "exposure": round(exposure, 3),
        "fixtures": [],
        "provenance": {"by": "auto", "tool": "light", "confidence": 0.3 if windows else 0.2},
    }
    if windows:
        fr, _ = windows[0]
        out = (-fr["v_in"][0], -fr["v_in"][1])  # outward normal of the window wall
        az = math.degrees(math.atan2(out[0], out[1]))
        lighting["sun"] = {"azimuth": round(az % 360.0, 1), "elevation": 30.0, "strength": 3.0, "color": _hex(_tint(sun_rgb, 0.3))}
    else:
        lighting["sun"] = {"azimuth": 215.0, "elevation": 40.0, "strength": 2.0, "color": _hex(_tint(sun_rgb, 0.3))}
    return lighting
