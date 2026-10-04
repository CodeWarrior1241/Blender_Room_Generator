"""Beds."""

from __future__ import annotations

from room_gen.archetypes._dsl import Archetype, box, mats


def _bed(p):
    w, d, h = p["width"], p["depth"], p["height"]
    frame_h = p["frame_height"]
    mat_t = p["mattress_thickness"]
    limit = h - 0.13  # pillows (13 cm) must stay below the headboard top
    if frame_h + mat_t > limit:
        k = limit / (frame_h + mat_t)
        frame_h, mat_t = frame_h * k, mat_t * k
    head_t = 0.07
    body_d = d - head_t
    top = frame_h + mat_t
    head_h = h
    pillow_n = 2 if w >= 1.2 else 1
    pw = (w - 0.2) / pillow_n
    parts = [
        box("headboard", (w, head_t, head_h), (0, d / 2 - head_t / 2, head_h / 2), "frame", bevel=0.01),
        box("frame", (w, body_d, frame_h), (0, -head_t / 2, frame_h / 2), "frame", bevel=0.01),
        box("mattress", (w - 0.04, body_d - 0.04, mat_t), (0, -head_t / 2, frame_h + mat_t / 2), "linen", bevel=0.03),
        box("duvet", (w - 0.02, body_d * 0.72, 0.06), (0, -d / 2 + body_d * 0.36 + 0.005, top + 0.03 - 0.01), "duvet", bevel=0.025),
        box("pillow", (pw - 0.04, 0.4, 0.13), (-(w - 0.2) / 2 + pw / 2, d / 2 - head_t - 0.24, top + 0.06), "linen", bevel=0.05,
            array={"count": pillow_n, "offset": [pw, 0.0, 0.0]} if pillow_n > 1 else None),
    ]
    return parts


ARCHETYPES = [
    Archetype("bed", "beds", _bed, {"width": 1.6, "depth": 2.1, "height": 1.0, "frame_height": 0.3, "mattress_thickness": 0.24},
              {"width": (0.8, 2.4), "depth": (1.8, 2.4), "height": (0.4, 1.8)}, mats(frame="wood", linen="linen", duvet="fabric"),
              ["double bed", "queen bed", "king bed", "single bed", "twin bed", "daybed"]),
]
