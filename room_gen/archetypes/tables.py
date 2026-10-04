"""Tables and desks."""

from __future__ import annotations

from room_gen.archetypes._dsl import Archetype, box, cyl, mats

RANGE = {"width": (0.25, 4.0), "depth": (0.25, 2.5), "height": (0.2, 1.2)}


def _legged_table(p, apron=True, shelf=False):
    w, d, h = p["width"], p["depth"], p["height"]
    t, leg = p["top_thickness"], p["leg_size"]
    inset = p["leg_inset"]
    parts = [
        box("top", (w, d, t), (0, 0, h - t / 2), "top", bevel=0.006),
        box("leg", (leg, leg, h - t), (w / 2 - inset - leg / 2, d / 2 - inset - leg / 2, (h - t) / 2), "legs", mirror="xy"),
    ]
    if apron:
        ah = min(0.08, h * 0.15)
        parts.append(box("apron_x", (w - 2 * inset - 2 * leg, 0.02, ah), (0, d / 2 - inset - leg / 2, h - t - ah / 2), "legs", mirror="y"))
        parts.append(box("apron_y", (0.02, d - 2 * inset - 2 * leg, ah), (w / 2 - inset - leg / 2, 0, h - t - ah / 2), "legs", mirror="x"))
    if shelf:
        parts.append(box("shelf", (w - 2 * inset, d - 2 * inset, 0.02), (0, 0, h * 0.25), "top"))
    return parts


def _dining_table(p):
    return _legged_table(p, apron=True)


def _coffee_table(p):
    return _legged_table(p, apron=False, shelf=p.get("shelf", True))


def _desk(p):
    w, d, h = p["width"], p["depth"], p["height"]
    t = p["top_thickness"]
    parts = [
        box("top", (w, d, t), (0, 0, h - t / 2), "top", bevel=0.005),
        box("side", (0.04, d - 0.04, h - t), (w / 2 - 0.02, 0.02, (h - t) / 2), "legs", mirror="x"),
        box("modesty", (w - 0.08, 0.02, (h - t) * 0.5), (0, d / 2 - 0.01, h - t - (h - t) * 0.25), "legs"),
    ]
    if p.get("drawers", True) and w > 0.9:
        dw = 0.4
        parts.append(box("drawer_unit", (dw, d - 0.06, h - t - 0.02), (w / 2 - 0.04 - dw / 2, 0.03, (h - t - 0.02) / 2 + 0.02), "top"))
    return parts


def _side_table(p):
    w, d, h = p["width"], p["depth"], p["height"]
    if p.get("style", "round") == "round":
        r = min(w, d) / 2
        return [
            cyl("top", r, 0.03, (0, 0, h - 0.015), "top", segments=40, bevel=0.005),
            cyl("pedestal", 0.03, h - 0.05, (0, 0, (h - 0.05) / 2 + 0.02), "legs", segments=16),
            cyl("foot", r * 0.6, 0.02, (0, 0, 0.01), "legs", segments=32),
        ]
    return _legged_table({**p, "top_thickness": 0.03, "leg_size": 0.035, "leg_inset": 0.02}, apron=False, shelf=True)


TABLE_DEFAULTS = {"top_thickness": 0.04, "leg_size": 0.06, "leg_inset": 0.05}

ARCHETYPES = [
    Archetype("dining_table", "tables", _dining_table, {"width": 1.6, "depth": 0.9, "height": 0.75, **TABLE_DEFAULTS},
              RANGE, mats(top="wood", legs="wood"), ["table", "kitchen table", "dinner table", "conference table"], against_wall=False),
    Archetype("coffee_table", "tables", _coffee_table, {"width": 1.1, "depth": 0.6, "height": 0.42, "shelf": True, **TABLE_DEFAULTS, "leg_size": 0.045},
              RANGE, mats(top="wood", legs="wood"), ["cocktail table", "low table", "center table"], against_wall=False),
    Archetype("side_table", "tables", _side_table, {"width": 0.5, "depth": 0.5, "height": 0.55, "style": "round"},
              RANGE, mats(top="wood", legs="metal"), ["end table", "accent table", "lamp table", "occasional table"]),
    Archetype("desk", "tables", _desk, {"width": 1.2, "depth": 0.6, "height": 0.75, "top_thickness": 0.03, "drawers": True},
              RANGE, mats(top="laminate", legs="laminate"), ["writing desk", "computer desk", "work desk", "vanity", "secretary"]),
]
