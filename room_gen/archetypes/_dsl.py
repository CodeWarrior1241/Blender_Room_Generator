"""Helpers for writing archetype generators.

Object frame: origin at the bottom centre, +Z up, the object's front faces -Y, so a
generator must keep every part inside x in [-w/2, w/2], y in [-d/2, d/2], z in [0, h].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

Params = dict[str, Any]


def _bevel(size: tuple[float, ...] | None, width: float | None) -> dict | None:
    if not width:
        return None
    if size:
        width = min(width, 0.3 * min(s for s in size if s > 0))
    return {"width": round(width, 4), "segments": 2} if width > 0.002 else None


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def box(pid, size, pos, mat, *, bevel=None, **kw) -> dict:
    size = tuple(float(s) for s in size)
    return _clean({"id": pid, "primitive": "box", "size": list(size), "position": list(pos), "material": mat, "bevel": _bevel(size, bevel), **kw})


def cyl(pid, r, h, pos, mat, *, segments=24, bevel=None, **kw) -> dict:
    return _clean({"id": pid, "primitive": "cylinder", "radius": float(r), "height": float(h), "position": list(pos), "material": mat, "segments": segments, "bevel": _bevel((r, h), bevel), **kw})


def cone(pid, r1, r2, h, pos, mat, *, segments=24, **kw) -> dict:
    return _clean({"id": pid, "primitive": "cone", "radius": float(r1), "radius2": float(r2), "height": float(h), "position": list(pos), "material": mat, "segments": segments, **kw})


def sphere(pid, r, pos, mat, *, segments=16, **kw) -> dict:
    return _clean({"id": pid, "primitive": "sphere", "radius": float(r), "position": list(pos), "material": mat, "segments": segments, **kw})


def torus(pid, r_major, r_minor, pos, mat, *, segments=24, **kw) -> dict:
    return _clean({"id": pid, "primitive": "torus", "radius": float(r_major), "radius2": float(r_minor), "position": list(pos), "material": mat, "segments": segments, **kw})


def tube(pid, r_outer, r_inner, h, pos, mat, *, segments=24, **kw) -> dict:
    return _clean({"id": pid, "primitive": "tube", "radius": float(r_outer), "radius2": float(r_inner), "height": float(h), "position": list(pos), "material": mat, "segments": segments, **kw})


def lathe(pid, profile, pos, mat, *, segments=24, **kw) -> dict:
    return _clean({"id": pid, "primitive": "lathe", "profile": [list(p) for p in profile], "position": list(pos), "material": mat, "segments": segments, **kw})


def prism(pid, polygon, h, pos, mat, **kw) -> dict:
    return _clean({"id": pid, "primitive": "prism", "polygon": [list(p) for p in polygon], "height": float(h), "position": list(pos), "material": mat, **kw})


def array(count: int, dx=0.0, dy=0.0, dz=0.0) -> dict:
    return {"count": int(count), "offset": [float(dx), float(dy), float(dz)]}


# ----- materials --------------------------------------------------------------------

MAT = {
    "fabric": {"base_color": "#7d8088", "roughness": 0.92, "procedural": "fabric", "scale": 0.25},
    "leather": {"base_color": "#5a3b2a", "roughness": 0.45},
    "wood": {"base_color": "#9a7350", "roughness": 0.55, "procedural": "wood", "scale": 0.6},
    "dark_wood": {"base_color": "#4e3626", "roughness": 0.5, "procedural": "wood", "scale": 0.6},
    "laminate": {"base_color": "#e7e3dc", "roughness": 0.5},
    "metal": {"base_color": "#3a3b3e", "roughness": 0.35, "metallic": 0.85},
    "chrome": {"base_color": "#c8c8cc", "roughness": 0.15, "metallic": 1.0},
    "linen": {"base_color": "#efece6", "roughness": 0.9, "procedural": "fabric", "scale": 0.2},
    "glass": {"base_color": "#dfe9ee", "roughness": 0.05, "transmission": 0.9, "alpha": 0.35},
    "screen": {"base_color": "#0d0e10", "roughness": 0.18},
    "shade": {"base_color": "#f1e8d6", "roughness": 0.8, "emission": "#fff1d6", "emission_strength": 1.5},
    "ceramic": {"base_color": "#d9d4cb", "roughness": 0.35},
    "terracotta": {"base_color": "#b06a4a", "roughness": 0.8},
    "foliage": {"base_color": "#3e6a34", "roughness": 0.75, "procedural": "noise", "scale": 0.15},
    "stone": {"base_color": "#b9b4ab", "roughness": 0.7, "procedural": "noise", "scale": 0.5},
    "brick": {"base_color": "#9b5440", "roughness": 0.85, "procedural": "brick", "scale": 0.5},
    "soot": {"base_color": "#1d1b1a", "roughness": 0.95},
    "canvas": {"base_color": "#c9b79a", "roughness": 0.8},
    "books": {"base_color": "#7a5a48", "roughness": 0.8, "procedural": "noise", "scale": 0.08},
    "rubber": {"base_color": "#1f1f21", "roughness": 0.85},
    "paint": {"base_color": "#f0efeb", "roughness": 0.4},
}


def mats(**slots: str) -> dict[str, dict]:
    """Map slot name -> a copy of a library material."""
    return {slot: dict(MAT[name]) for slot, name in slots.items()}


@dataclass
class Archetype:
    name: str
    category: str
    build: Callable[[Params], list[dict]]
    defaults: Params
    ranges: dict[str, tuple[float, float]]
    materials: dict[str, dict]
    synonyms: list[str] = field(default_factory=list)
    support: str = "floor"  # floor | surface | wall | ceiling
    against_wall: bool = True
    description: str = ""

    @property
    def slots(self) -> list[str]:
        return list(self.materials)
