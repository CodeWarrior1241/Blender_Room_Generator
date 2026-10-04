"""Lamps. Shade materials are emissive so previews read as lit lamps."""

from __future__ import annotations

from room_gen.archetypes._dsl import Archetype, cone, cyl, lathe, mats


def _floor_lamp(p):
    w, h = min(p["width"], p["depth"]), p["height"]
    shade_h = min(0.3, h * 0.2)
    r = w / 2
    return [
        cyl("base", min(0.15, r * 0.8), 0.03, (0, 0, 0.015), "metal", segments=32),
        cyl("pole", 0.012, h - shade_h * 0.6, (0, 0, 0.03 + (h - shade_h * 0.6 - 0.03) / 2), "metal", segments=12),
        cone("shade", r, r * 0.75, shade_h, (0, 0, h - shade_h / 2), "shade", segments=32),
    ]


def _table_lamp(p):
    w, h = min(p["width"], p["depth"]), p["height"]
    r = w / 2
    shade_h = h * 0.4
    base_h = h - shade_h * 0.85
    rb = min(r * 0.55, 0.09)
    return [
        lathe("base", [(0.0, 0.0), (rb, 0.0), (rb * 1.15, base_h * 0.35), (rb * 0.5, base_h * 0.8), (0.02, base_h), (0.0, base_h)], (0, 0, 0), "body", segments=28),
        cone("shade", r, r * 0.7, shade_h, (0, 0, h - shade_h / 2), "shade", segments=32),
    ]


def _pendant(p):
    w, h = min(p["width"], p["depth"]), p["height"]
    r = w / 2
    shade_h = min(0.25, h * 0.5)
    return [
        cyl("cord", 0.004, h - shade_h, (0, 0, shade_h + (h - shade_h) / 2), "metal", segments=8),
        cone("shade", r, r * 0.25, shade_h, (0, 0, shade_h / 2), "shade", segments=32),
    ]


ARCHETYPES = [
    Archetype("floor_lamp", "lighting", _floor_lamp, {"width": 0.4, "depth": 0.4, "height": 1.6},
              {"width": (0.15, 1.0), "depth": (0.15, 1.0), "height": (0.8, 2.2)}, mats(metal="metal", shade="shade"),
              ["standing lamp", "torchiere", "arc lamp"], against_wall=False),
    Archetype("table_lamp", "lighting", _table_lamp, {"width": 0.32, "depth": 0.32, "height": 0.55},
              {"width": (0.1, 0.8), "depth": (0.1, 0.8), "height": (0.15, 1.0)}, mats(body="ceramic", shade="shade"),
              ["lamp", "desk lamp", "bedside lamp", "reading lamp"], support="surface", against_wall=False),
    Archetype("pendant_lamp", "lighting", _pendant, {"width": 0.4, "depth": 0.4, "height": 0.8},
              {"width": (0.1, 1.5), "depth": (0.1, 1.5), "height": (0.2, 2.0)}, mats(metal="metal", shade="shade"),
              ["pendant", "hanging lamp", "ceiling lamp", "chandelier", "ceiling light", "light fixture"], support="ceiling", against_wall=False),
]
