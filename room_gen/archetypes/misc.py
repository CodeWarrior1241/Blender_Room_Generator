"""Electronics, decor, plants, wall items, built-ins, and the generic fallback."""

from __future__ import annotations


from room_gen.archetypes._dsl import Archetype, array, box, cyl, lathe, mats, prism, sphere


def _tv(p):
    w, d, h = p["width"], p["depth"], p["height"]
    if not p.get("stand", True):
        return [
            box("panel", (w, d, h), (0, 0, h / 2), "body", bevel=0.004),
            box("screen", (w - 0.02, 0.004, h - 0.02), (0, -d / 2 + 0.002, h / 2), "screen"),
        ]
    stand_h = min(0.08, h * 0.12)
    panel_d = min(d, 0.06)
    panel_h = h - stand_h
    return [
        box("foot", (w * 0.4, d, 0.015), (0, 0, 0.0075), "body"),
        box("neck", (0.06, 0.03, stand_h), (0, panel_d / 4, stand_h / 2), "body"),
        box("panel", (w, panel_d, panel_h), (0, 0, stand_h + panel_h / 2), "body", bevel=0.004),
        box("screen", (w - 0.02, 0.004, panel_h - 0.02), (0, -panel_d / 2 + 0.002, stand_h + panel_h / 2), "screen"),
    ]


def _tv_stand(p):
    w, d, h = p["width"], p["depth"], p["height"]
    leg_h, t = p.get("leg_height", 0.1), 0.025
    body_h = h - leg_h
    return [
        box("top", (w, d, t), (0, 0, h - t / 2), "body"),
        box("bottom", (w, d, t), (0, 0, leg_h + t / 2), "body"),
        box("side", (t, d, body_h - 2 * t), (w / 2 - t / 2, 0, leg_h + body_h / 2), "body", mirror="x"),
        box("divider", (t, d - 0.02, body_h - 2 * t), (0, 0.01, leg_h + body_h / 2), "body"),
        box("back", (w - 2 * t, 0.008, body_h - 2 * t), (0, d / 2 - 0.004, leg_h + body_h / 2), "body"),
        box("door", (w / 2 - t * 1.5, 0.018, body_h - 2 * t - 0.01), (-w / 4, -d / 2 + 0.009, leg_h + body_h / 2), "front"),
        cyl("leg", 0.02, leg_h, (w / 2 - 0.06, d / 2 - 0.06, leg_h / 2), "legs", segments=10, mirror="xy"),
    ]


def _monitor(p):
    w, d, h = p["width"], p["depth"], p["height"]
    panel_h = h * 0.72
    return [
        box("foot", (w * 0.35, d, 0.015), (0, 0, 0.0075), "body"),
        box("neck", (0.05, 0.03, h - panel_h * 0.6), (0, d / 2 - 0.03, (h - panel_h * 0.6) / 2), "body"),
        box("panel", (w, 0.03, panel_h), (0, -d / 2 + 0.015, h - panel_h / 2), "body", bevel=0.003),
        box("screen", (w - 0.016, 0.003, panel_h - 0.016), (0, -d / 2 + 0.0015, h - panel_h / 2), "screen"),
    ]


def _rug(p):
    w, d, h = p["width"], p["depth"], p["height"]
    return [box("rug", (w, d, h), (0, 0, h / 2), "rug", bevel=min(0.004, h * 0.3))]


def _plant(p):
    w, d, h = p["width"], p["depth"], p["height"]
    r = min(w, d) / 2
    pot_h = h * 0.32
    pot_r = min(r * 0.6, 0.22)
    crown_z = max(h - r, pot_h)
    small = r * 0.5
    parts = [
        lathe("pot", [(0.0, 0.0), (pot_r * 0.75, 0.0), (pot_r, pot_h), (pot_r * 0.92, pot_h), (0.0, pot_h * 0.9)], (0, 0, 0), "pot", segments=24),
        cyl("stem", 0.015, max(crown_z - pot_h, 0.02), (0, 0, pot_h + max(crown_z - pot_h, 0.02) / 2), "foliage", segments=8),
        sphere("crown", r, (0, 0, crown_z), "foliage", segments=16, scale=(w / (2 * r), d / (2 * r), 1.0)),
    ]
    for k, (fx, fy, fz) in enumerate([(0.42, 0.3, -0.45), (-0.4, 0.35, -0.3), (0.1, -0.45, -0.55), (-0.3, -0.3, -0.15)]):
        z = max(crown_z + fz * r, pot_h + small)
        parts.append(sphere(f"leaves_{k}", small, (fx * r, fy * r, min(z, h - small)), "foliage", segments=12))
    return parts


def _vase(p):
    w, h = min(p["width"], p["depth"]), p["height"]
    r = w / 2
    return [lathe("vase", [(0.0, 0.0), (r * 0.6, 0.0), (r, h * 0.35), (r * 0.45, h * 0.85), (r * 0.55, h), (0.0, h * 0.95)], (0, 0, 0), "body", segments=28)]


def _radiator(p):
    w, d, h = p["width"], p["depth"], p["height"]
    fin_pitch = 0.06
    n = max(2, min(60, int(w / fin_pitch)))
    pitch = (w - 0.03) / (n - 1)
    leg = 0.1
    rr = min(d * 0.18, (h - leg) / 4)
    return [
        box("fin", (0.03, d * 0.8, h - leg), (-w / 2 + 0.015, 0, leg + (h - leg) / 2), "body", array=array(n, pitch)),
        cyl("header", rr, w, (0, 0, h - rr), "body", segments=12, rotation=(0, 90, 0)),
        cyl("footer", rr, w, (0, 0, leg + rr), "body", segments=12, rotation=(0, 90, 0)),
        box("foot", (0.04, d, leg), (w / 2 - 0.1, 0, leg / 2), "body", mirror="x"),
    ]


def _fireplace(p):
    w, d, h = p["width"], p["depth"], p["height"]
    open_w, open_h = w * 0.55, h * 0.55
    pillar_w = (w - open_w) / 2
    mantel_t = 0.06
    hearth_d = min(0.3, d * 0.5)
    body_d = d - hearth_d
    yb = d / 2 - body_d / 2
    return [
        box("pillar", (pillar_w, body_d, h - mantel_t), (w / 2 - pillar_w / 2, yb, (h - mantel_t) / 2), "surround", mirror="x"),
        box("lintel", (open_w, body_d, h - mantel_t - open_h), (0, yb, open_h + (h - mantel_t - open_h) / 2), "surround"),
        box("firebox", (open_w, body_d * 0.4, open_h), (0, d / 2 - body_d * 0.2, open_h / 2), "soot"),
        box("mantel", (w, body_d + 0.04 if body_d + 0.04 <= d else body_d, mantel_t), (0, yb - 0.02 if body_d + 0.04 <= d else yb, h - mantel_t / 2), "mantel"),
        box("hearth", (w, hearth_d, 0.04), (0, -d / 2 + hearth_d / 2, 0.02), "surround"),
    ]


def _picture(p):
    w, d, h = p["width"], p["depth"], p["height"]
    f = min(0.04, w * 0.08, h * 0.08)
    return [
        box("frame_tb", (w, d, f), (0, 0, f / 2), "frame", mirror=None),
        box("frame_top", (w, d, f), (0, 0, h - f / 2), "frame"),
        box("frame_side", (f, d, h - 2 * f), (w / 2 - f / 2, 0, h / 2), "frame", mirror="x"),
        box("canvas", (w - 2 * f, d * 0.4, h - 2 * f), (0, d * 0.2, h / 2), "canvas"),
    ]


def _curtain(p):
    w, d, h = p["width"], p["depth"], p["height"]
    folds = max(3, int(w / 0.12))
    t = min(0.01, d * 0.2)
    amp = d / 2
    front = [(-w / 2 + w * k / folds, -amp if k % 2 else amp - t) for k in range(folds + 1)]
    back = [(x, y + t) for x, y in reversed(front)]
    rod_r = min(0.012, d / 2)
    return [
        prism("panel", front + back, h - 2 * rod_r, (0, 0, (h - 2 * rod_r) / 2), "fabric"),
        cyl("rod", rod_r, w, (0, 0, h - rod_r), "metal", segments=12, rotation=(0, 90, 0)),
    ]


def _generic(p):
    w, d, h = p["width"], p["depth"], p["height"]
    return [box("body", (w, d, h), (0, 0, h / 2), "body", bevel=min(w, d, h) * 0.05)]


ANY = {"width": (0.02, 6.0), "depth": (0.005, 6.0), "height": (0.005, 3.5)}

ARCHETYPES = [
    Archetype("tv", "electronics", _tv, {"width": 1.2, "depth": 0.25, "height": 0.78, "stand": True},
              ANY, mats(body="metal", screen="screen"), ["television", "tv set", "flat screen", "flatscreen"], support="surface"),
    Archetype("tv_stand", "storage", _tv_stand, {"width": 1.6, "depth": 0.4, "height": 0.5, "leg_height": 0.1},
              ANY, mats(body="wood", front="wood", legs="metal"), ["tv console", "entertainment center", "media unit", "tv cabinet", "tv unit"]),
    Archetype("monitor", "electronics", _monitor, {"width": 0.6, "depth": 0.2, "height": 0.48},
              ANY, mats(body="metal", screen="screen"), ["computer monitor", "computer screen", "display", "screen", "imac", "laptop"], support="surface"),
    Archetype("rug", "decor", _rug, {"width": 2.0, "depth": 1.4, "height": 0.012},
              ANY, mats(rug="fabric"), ["carpet", "area rug", "mat", "runner"], against_wall=False),
    Archetype("plant", "decor", _plant, {"width": 0.55, "depth": 0.55, "height": 1.1},
              ANY, mats(pot="terracotta", foliage="foliage"), ["potted plant", "houseplant", "fern", "ficus", "palm", "monstera", "succulent", "flower pot", "planter"], against_wall=False),
    Archetype("vase", "decor", _vase, {"width": 0.18, "depth": 0.18, "height": 0.3},
              ANY, mats(body="ceramic"), ["jar", "urn", "pot", "bottle", "amphora", "jug"], support="surface", against_wall=False),
    Archetype("radiator", "built_in", _radiator, {"width": 0.8, "depth": 0.1, "height": 0.6},
              ANY, mats(body="paint"), ["heater", "heating radiator", "baseboard heater"]),
    Archetype("fireplace", "built_in", _fireplace, {"width": 1.4, "depth": 0.45, "height": 1.15},
              ANY, mats(surround="stone", soot="soot", mantel="wood"), ["hearth", "fire place", "mantel", "mantelpiece", "wood stove"]),
    Archetype("picture_frame", "wall", _picture, {"width": 0.6, "depth": 0.03, "height": 0.45},
              ANY, mats(frame="dark_wood", canvas="canvas"), ["picture", "painting", "artwork", "frame", "poster", "mirror", "photo", "print", "canvas"], support="wall"),
    Archetype("curtain", "wall", _curtain, {"width": 1.4, "depth": 0.1, "height": 2.4},
              ANY, mats(fabric="linen", metal="metal"), ["curtains", "drapes", "drape", "blind", "blinds"], support="wall"),
    Archetype("generic_box", "generic", _generic, {"width": 0.5, "depth": 0.5, "height": 0.5},
              ANY, mats(body="laminate"), ["box", "object", "item", "crate", "storage box", "basket", "trunk", "chest", "suitcase"], against_wall=False),
]
