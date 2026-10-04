"""Tileable procedural textures (wood, tile, fabric, noise, brick) generated on the host.

They are ordinary PNGs so the glTF exporter carries them; Blender maps them with
world-scale UVs (one tile per ``material.scale`` metres).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

SIZE = 512


def _hex(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _periodic_noise(rng: np.random.Generator, size: int, freqs=(1, 2, 4, 8, 16), falloff: float = 0.6) -> np.ndarray:
    """Sum of random integer-frequency sinusoids: seamless when tiled."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / size
    out = np.zeros((size, size), np.float32)
    amp = 1.0
    for f in freqs:
        for _ in range(3):
            fx, fy = rng.integers(-f, f + 1, size=2)
            if fx == 0 and fy == 0:
                fx = f
            phase = rng.uniform(0, 2 * np.pi)
            out += amp * np.sin(2 * np.pi * (fx * x + fy * y) + phase)
        amp *= falloff
    out -= out.min()
    return out / max(out.max(), 1e-6)


def _wood(rng, size, planks: int = 4):
    """Planks along x: straight grain, gentle waviness, per-plank tone, dark seams."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / size
    plank = np.floor(y * planks)
    wobble = 0.015 * (_periodic_noise(rng, size, (1, 2), 0.5) - 0.5)
    grain = 0.5 + 0.5 * np.sin(2 * np.pi * (planks * 9 * (y + wobble) + 0.35 * np.sin(2 * np.pi * x * 2 + plank)))
    streak = _periodic_noise(rng, size, (24, 48, 64), 0.8)
    tone = np.vectorize(lambda k: ((int(k) * 7919) % 97) / 97.0)(plank).astype(np.float32)
    fy = y * planks - plank
    seam = (fy < 0.012) | (fy > 0.988)
    end_joint = ((x * 2 + 0.5 * (plank % 2)) % 1.0) < 0.004
    val = 0.88 + 0.07 * grain + 0.05 * streak + 0.12 * (tone - 0.5)
    return np.where(seam | end_joint, 0.55, val)


def _tile(rng, size, tiles=4, grout=0.035, brick=False):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32) / size
    rows = tiles * (2 if brick else 1)
    ty = y * rows
    tx = x * tiles + (0.5 * (np.floor(ty) % 2) if brick else 0.0)
    fx, fy = tx - np.floor(tx), ty - np.floor(ty)
    g = grout * (1 if not brick else 2.0)
    is_grout = (fx < g) | (fy < g * (tiles / rows) * (2 if brick else 1))
    ids = (np.floor(tx) % tiles) * 31 + np.floor(ty) % rows
    jitter = np.vectorize(lambda k: (hash(int(k)) % 1000) / 1000.0)(ids).astype(np.float32)
    val = 0.92 + 0.12 * jitter + 0.05 * _periodic_noise(rng, size, (8, 16), 0.7)
    return np.where(is_grout, 0.62 if brick else 1.12, val)


def _fabric(rng, size):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    weave = 0.5 + 0.25 * np.sin(2 * np.pi * x / 8) * np.sin(2 * np.pi * y / 8)
    return 0.9 + 0.12 * weave + 0.06 * _periodic_noise(rng, size, (4, 8, 16), 0.7)


def _noise(rng, size):
    return 0.9 + 0.2 * _periodic_noise(rng, size, (2, 4, 8, 16, 32), 0.65)


def generate(kind: str, base_color: str, size: int = SIZE, seed: int = 7) -> np.ndarray:
    """RGB uint8 image whose average colour stays close to ``base_color``."""
    rng = np.random.default_rng(seed)
    pattern = {
        "wood": lambda: _wood(rng, size),
        "tile": lambda: _tile(rng, size),
        "brick": lambda: _tile(rng, size, tiles=4, brick=True),
        "fabric": lambda: _fabric(rng, size),
        "noise": lambda: _noise(rng, size),
    }[kind]()
    pattern = pattern / max(float(pattern.mean()), 1e-6)
    rgb = np.clip(_hex(base_color)[None, None, :] * pattern[..., None], 0, 255)
    return rgb.astype(np.uint8)


def ensure_texture(directory: str | Path, kind: str, base_color: str, size: int = SIZE) -> Path:
    """Write (once) and return the texture for (kind, colour)."""
    key = hashlib.sha1(f"{kind}:{base_color.lower()}:{size}:v2".encode()).hexdigest()[:10]
    path = Path(directory) / f"{kind}-{base_color.lstrip('#').lower()}-{key}.png"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        rgb = generate(kind, base_color, size)
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return path
