"""Case goods: nightstands, dressers, cabinets, wardrobes, shelves, counters, appliances."""

from __future__ import annotations

from room_gen.archetypes._dsl import Archetype, array, box, cyl, mats

RANGE = {"width": (0.25, 4.0), "depth": (0.15, 1.2), "height": (0.2, 2.6)}


def _case(p, rows: int, cols: int, kind: str):
    """Carcass with a grid of drawer or door fronts; handles stay inside the depth."""
    w, d, h = p["width"], p["depth"], p["height"]
    leg_h = p.get("leg_height", 0.0)
    front_t, handle_d, gap = 0.018, 0.022, 0.004
    body_h = h - leg_h
    carcass_d = d - front_t - handle_d
    parts = [box("carcass", (w, carcass_d, body_h), (0, d / 2 - carcass_d / 2, leg_h + body_h / 2), "body")]
    fw = (w - gap * (cols + 1)) / cols
    fh = (body_h - gap * (rows + 1)) / rows
    y_front = -d / 2 + handle_d + front_t / 2
    x0 = -w / 2 + gap + fw / 2
    z0 = leg_h + gap + fh / 2
    parts.append(box("front", (fw, front_t, fh), (x0, y_front, z0), "front", bevel=0.003,
                     array=array(cols, fw + gap) if cols > 1 else None))
    if rows > 1:
        parts[-1]["id"] = "front_row0"
        for r in range(1, rows):
            parts.append(box(f"front_row{r}", (fw, front_t, fh), (x0, y_front, z0 + r * (fh + gap)), "front", bevel=0.003,
                             array=array(cols, fw + gap) if cols > 1 else None))
    y_handle = -d / 2 + handle_d / 2
    for r in range(rows):
        zc = z0 + r * (fh + gap)
        if kind == "drawer":
            hz = zc + fh * 0.2 if fh < 0.35 else zc + fh * 0.35
            parts.append(box(f"handle_{r}", (min(0.12, fw * 0.4), handle_d, 0.014), (x0, y_handle, min(hz, h - 0.03)), "handles",
                             array=array(cols, fw + gap) if cols > 1 else None))
        else:
            hl = min(0.18, fh * 0.3)
            for c in range(cols):
                side = 1 if c % 2 == 0 else -1
                hx = x0 + c * (fw + gap) + side * (fw / 2 - 0.04)
                parts.append(box(f"handle_{r}_{c}", (0.014, handle_d, hl), (hx, y_handle, zc + (fh * 0.25 if fh > 1.0 else 0)), "handles"))
    if leg_h > 0:
        parts.append(cyl("leg", 0.02, leg_h, (w / 2 - 0.05, d / 2 - 0.05, leg_h / 2), "handles", segments=10, mirror="xy"))
    return parts


def _nightstand(p):
    return _case(p, rows=int(p.get("drawers", 2)), cols=1, kind="drawer")


def _dresser(p):
    return _case(p, rows=int(p.get("rows", 3)), cols=int(p.get("cols", 2)), kind="drawer")


def _cabinet(p):
    return _case(p, rows=1, cols=int(p.get("doors", 2)), kind="door")


def _sideboard(p):
    return _case(p, rows=1, cols=int(p.get("doors", 3)), kind="door")


def _wardrobe(p):
    return _case(p, rows=1, cols=int(p.get("doors", 2)), kind="door")


def _bookshelf(p):
    w, d, h = p["width"], p["depth"], p["height"]
    t = 0.02
    n = max(1, int(p.get("shelves", 4)))
    inner_h = h - 2 * t
    pitch = inner_h / (n + 1)
    parts = [
        box("side", (t, d, h), (w / 2 - t / 2, 0, h / 2), "body", mirror="x"),
        box("top", (w - 2 * t, d, t), (0, 0, h - t / 2), "body"),
        box("bottom", (w - 2 * t, d, t), (0, 0, t / 2), "body"),
        box("back", (w - 2 * t, 0.008, inner_h), (0, d / 2 - 0.004, h / 2), "body"),
        box("shelf", (w - 2 * t, d - 0.01, t), (0, -0.005, t + pitch), "body", array=array(n, dz=pitch)),
    ]
    if p.get("books", True):
        inner_w = w - 2 * t
        for k in range(n + 1):
            frac_w = (0.45, 0.7, 0.55, 0.8, 0.6, 0.5, 0.75)[k % 7]
            frac_h = (0.78, 0.86, 0.7)[k % 3]
            surface = t if k == 0 else t + k * pitch + t / 2
            bh = (pitch - t) * frac_h
            bw = inner_w * frac_w
            x = -inner_w / 2 + 0.02 + bw / 2 if k % 2 == 0 else inner_w / 2 - 0.02 - bw / 2
            parts.append(box(f"books_{k}", (bw, d * 0.75, bh), (x, -d * 0.1, surface + bh / 2), "books"))
    return parts


def _counter(p):
    w, d, h = p["width"], p["depth"], p["height"]
    top_t, toe = 0.04, 0.1
    body_d = d - 0.03
    body_h = h - top_t - toe
    doors = max(1, int(round(w / 0.6)))
    parts = [
        box("toe", (w, body_d - 0.06, toe), (0, d / 2 - (body_d - 0.06) / 2, toe / 2), "front"),
        box("carcass", (w, body_d - 0.02, body_h), (0, d / 2 - (body_d - 0.02) / 2, toe + body_h / 2), "body"),
        box("door", ((w - 0.004 * (doors + 1)) / doors, 0.018, body_h - 0.01), (-w / 2 + 0.004 + (w - 0.004 * (doors + 1)) / doors / 2, d / 2 - body_d + 0.009, toe + body_h / 2), "front",
            array=array(doors, (w - 0.004 * (doors + 1)) / doors + 0.004)),
        box("countertop", (w, d, top_t), (0, 0, h - top_t / 2), "top", bevel=0.004),
    ]
    return parts


def _refrigerator(p):
    w, d, h = p["width"], p["depth"], p["height"]
    door_t, handle_d = 0.04, 0.04
    body_d = d - door_t - handle_d
    split = h * 0.62
    return [
        box("body", (w, body_d, h), (0, d / 2 - body_d / 2, h / 2), "body", bevel=0.01),
        box("door_low", (w, door_t, split - 0.01), (0, -d / 2 + handle_d + door_t / 2, split / 2), "body", bevel=0.01),
        box("door_high", (w, door_t, h - split - 0.01), (0, -d / 2 + handle_d + door_t / 2, split + (h - split) / 2), "body", bevel=0.01),
        box("handle", (0.025, handle_d, 0.35), (w / 2 - 0.06, -d / 2 + handle_d / 2, split + 0.25), "handles"),
        box("handle_low", (0.025, handle_d, 0.35), (w / 2 - 0.06, -d / 2 + handle_d / 2, split - 0.25), "handles"),
    ]


ARCHETYPES = [
    Archetype("nightstand", "storage", _nightstand, {"width": 0.5, "depth": 0.4, "height": 0.55, "leg_height": 0.08, "drawers": 2},
              RANGE, mats(body="wood", front="wood", handles="metal"), ["night stand", "bedside table", "bedside cabinet", "night table"]),
    Archetype("dresser", "storage", _dresser, {"width": 1.2, "depth": 0.5, "height": 0.85, "leg_height": 0.08, "rows": 3, "cols": 2},
              RANGE, mats(body="wood", front="wood", handles="metal"), ["chest of drawers", "drawers", "bureau", "commode", "drawer unit"]),
    Archetype("cabinet", "storage", _cabinet, {"width": 0.8, "depth": 0.45, "height": 0.9, "leg_height": 0.0, "doors": 2},
              RANGE, mats(body="laminate", front="laminate", handles="metal"), ["cupboard", "storage cabinet", "credenza", "hutch", "console"]),
    Archetype("sideboard", "storage", _sideboard, {"width": 1.6, "depth": 0.45, "height": 0.8, "leg_height": 0.12, "doors": 3},
              RANGE, mats(body="wood", front="wood", handles="metal"), ["buffet", "media console", "server"]),
    Archetype("wardrobe", "storage", _wardrobe, {"width": 1.0, "depth": 0.6, "height": 2.0, "leg_height": 0.0, "doors": 2},
              RANGE, mats(body="laminate", front="laminate", handles="metal"), ["armoire", "closet", "clothes cabinet", "tall cabinet"]),
    Archetype("bookshelf", "storage", _bookshelf, {"width": 0.9, "depth": 0.3, "height": 1.8, "shelves": 4, "books": True},
              {**RANGE, "shelves": (1, 10)}, mats(body="wood", books="books"), ["bookcase", "shelf", "shelving", "shelves", "shelving unit", "etagere"]),
    Archetype("counter", "storage", _counter, {"width": 2.4, "depth": 0.6, "height": 0.9},
              RANGE, mats(body="laminate", front="paint", top="stone"), ["kitchen counter", "base cabinets", "kitchen island", "island", "countertop"]),
    Archetype("refrigerator", "storage", _refrigerator, {"width": 0.7, "depth": 0.7, "height": 1.8},
              RANGE, mats(body="paint", handles="chrome"), ["fridge", "freezer"]),
]
