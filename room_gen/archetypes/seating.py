"""Sofas, chairs, stools, benches, ottomans."""

from __future__ import annotations

import math

from room_gen.archetypes._dsl import Archetype, array, box, cyl, mats, sphere, torus

SIZE_RANGE = {"width": (0.3, 4.0), "depth": (0.3, 2.0), "height": (0.3, 1.6)}


def _sofa(p):
    w, d, h = p["width"], p["depth"], p["height"]
    leg = p["leg_height"]
    seat = min(p["seat_height"], h - 0.1)
    arm_w = p["arm_width"] if p["arms"] else 0.0
    arm_h = min(p["arm_height"], h)
    back_d = min(p["back_depth"], d * 0.4)
    cush_t = min(0.14, (seat - leg) * 0.5)
    base_top = seat - cush_t
    inner_w = w - 2 * arm_w
    n = max(1, int(p["cushions"]))
    cw, cd = inner_w / n, d - back_d
    parts = [
        box("base", (w, d, base_top - leg), (0, 0, leg + (base_top - leg) / 2), "upholstery", bevel=0.02),
        box("back", (inner_w, back_d, h - base_top), (0, d / 2 - back_d / 2, base_top + (h - base_top) / 2), "upholstery", bevel=0.04),
        box("cushion", (cw - 0.01, cd, cush_t), (-inner_w / 2 + cw / 2, -d / 2 + cd / 2, base_top + cush_t / 2), "upholstery", bevel=0.035, array=array(n, cw)),
        cyl("leg", 0.022, leg, (w / 2 - 0.06, d / 2 - 0.06, leg / 2), "legs", segments=12, mirror="xy"),
    ]
    if arm_w > 0:
        parts.append(box("arm", (arm_w, d, arm_h - leg), (w / 2 - arm_w / 2, 0, leg + (arm_h - leg) / 2), "upholstery", bevel=0.04, mirror="x"))
    return parts


def _dining_chair(p):
    w, d, h = p["width"], p["depth"], p["height"]
    seat_h, t, leg = min(p["seat_height"], h - 0.15), 0.04, 0.035
    back_h = h - seat_h
    return [
        box("seat", (w, d, t), (0, 0, seat_h - t / 2), "seat", bevel=0.008),
        box("front_leg", (leg, leg, seat_h - t), (w / 2 - leg / 2, -d / 2 + leg / 2, (seat_h - t) / 2), "frame", mirror="x"),
        box("back_post", (leg, leg, h), (w / 2 - leg / 2, d / 2 - leg / 2, h / 2), "frame", mirror="x"),
        box("back_rest", (w - 2 * leg, 0.022, back_h * 0.45), (0, d / 2 - leg / 2, h - back_h * 0.25), "seat", bevel=0.006),
        box("stretcher", (0.02, d - 2 * leg, 0.03), (w / 2 - leg / 2, 0, 0.15), "frame", mirror="x"),
    ]


def _office_chair(p):
    w, d, h = p["width"], p["depth"], p["height"]
    wheel = 0.03
    a, b = w / 2 - wheel, d / 2 - wheel
    length = math.hypot(a, b)
    angle = math.degrees(math.atan2(b, a))
    seat_h = min(p["seat_height"], h - 0.2)
    seat_w, seat_d = w * 0.75, d * 0.75
    back_h = h - seat_h
    return [
        box("arm", (length, 0.04, 0.035), (a / 2, b / 2, 0.075), "metal", rotation=(0, 0, angle), mirror="xy"),
        sphere("wheel", wheel, (a, b, wheel), "rubber", segments=10, mirror="xy"),
        cyl("column", 0.025, seat_h - 0.13, (0, 0, 0.09 + (seat_h - 0.13) / 2), "metal", segments=12),
        box("seat", (seat_w, seat_d, 0.08), (0, -0.02, seat_h - 0.04), "upholstery", bevel=0.03),
        box("back", (seat_w * 0.9, 0.07, back_h), (0, seat_d / 2 - 0.02, seat_h + back_h / 2), "upholstery", bevel=0.03),
    ]


def _stool(p):
    w, h = p["width"], p["height"]
    r = w / 2
    leg_r = 0.018
    return [
        cyl("seat", r, 0.04, (0, 0, h - 0.02), "seat", segments=32, bevel=0.01),
        cyl("leg", leg_r, h - 0.04, (r * 0.7 / math.sqrt(2), r * 0.7 / math.sqrt(2), (h - 0.04) / 2), "frame", segments=10, mirror="xy"),
        torus("footrest", r * 0.7, 0.01, (0, 0, h * 0.3), "frame", segments=32),
    ]


def _bench(p):
    w, d, h = p["width"], p["depth"], p["height"]
    t = 0.05
    return [
        box("top", (w, d, t), (0, 0, h - t / 2), "seat", bevel=0.01),
        box("slab", (0.05, d * 0.9, h - t), (w / 2 - 0.12, 0, (h - t) / 2), "frame", mirror="x"),
    ]


def _ottoman(p):
    w, d, h = p["width"], p["depth"], p["height"]
    leg = min(0.06, h * 0.2)
    return [
        box("body", (w, d, h - leg), (0, 0, leg + (h - leg) / 2), "upholstery", bevel=0.04),
        cyl("leg", 0.02, leg, (w / 2 - 0.05, d / 2 - 0.05, leg / 2), "legs", segments=10, mirror="xy"),
    ]


SOFA_DEFAULTS = {"leg_height": 0.1, "seat_height": 0.43, "arm_width": 0.18, "arm_height": 0.62, "back_depth": 0.22, "arms": True}

ARCHETYPES = [
    Archetype("sofa", "seating", _sofa, {"width": 2.0, "depth": 0.9, "height": 0.85, "cushions": 3, **SOFA_DEFAULTS},
              {**SIZE_RANGE, "cushions": (1, 5)}, mats(upholstery="fabric", legs="dark_wood"),
              ["couch", "settee", "sectional", "chesterfield", "davenport"], description="three-seat sofa with arms and seat cushions"),
    Archetype("loveseat", "seating", _sofa, {"width": 1.5, "depth": 0.88, "height": 0.85, "cushions": 2, **SOFA_DEFAULTS},
              {**SIZE_RANGE, "cushions": (1, 3)}, mats(upholstery="fabric", legs="dark_wood"), ["love seat", "two-seater", "small sofa"]),
    Archetype("armchair", "seating", _sofa, {"width": 0.85, "depth": 0.85, "height": 0.9, "cushions": 1, **SOFA_DEFAULTS, "arm_width": 0.15},
              {**SIZE_RANGE, "cushions": (1, 1)}, mats(upholstery="fabric", legs="dark_wood"),
              ["arm chair", "easy chair", "lounge chair", "club chair", "recliner", "accent chair", "wingback"], against_wall=False),
    Archetype("dining_chair", "seating", _dining_chair, {"width": 0.45, "depth": 0.5, "height": 0.9, "seat_height": 0.46},
              {**SIZE_RANGE}, mats(seat="wood", frame="wood"), ["chair", "side chair", "kitchen chair", "wooden chair"], against_wall=False),
    Archetype("office_chair", "seating", _office_chair, {"width": 0.65, "depth": 0.65, "height": 1.05, "seat_height": 0.48},
              {**SIZE_RANGE}, mats(upholstery="fabric", metal="metal", rubber="rubber"),
              ["desk chair", "swivel chair", "task chair", "computer chair", "gaming chair"], against_wall=False),
    Archetype("stool", "seating", _stool, {"width": 0.4, "depth": 0.4, "height": 0.65},
              {**SIZE_RANGE}, mats(seat="wood", frame="metal"), ["bar stool", "counter stool", "footstool"], against_wall=False),
    Archetype("bench", "seating", _bench, {"width": 1.2, "depth": 0.4, "height": 0.45},
              {**SIZE_RANGE}, mats(seat="wood", frame="wood"), ["entry bench", "piano bench"]),
    Archetype("ottoman", "seating", _ottoman, {"width": 0.7, "depth": 0.5, "height": 0.42},
              {**SIZE_RANGE}, mats(upholstery="fabric", legs="dark_wood"), ["pouf", "footrest", "hassock"], against_wall=False),
]
