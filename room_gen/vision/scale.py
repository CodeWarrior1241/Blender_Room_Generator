"""Metric scale from standard object heights (CLAUDE.md §8.3 scale cues).

Every metric quantity of a single-photo reconstruction is proportional to the assumed
camera height, so a scale factor ``k`` rescales the whole scene. Typical heights and their
relative spread are conservative; only well-standardised items carry real weight.
"""

from __future__ import annotations

import math

# archetype -> (typical height m, relative sigma)
HEIGHTS = {
    "dining_table": (0.75, 0.05), "desk": (0.75, 0.05), "counter": (0.90, 0.04), "refrigerator": (1.78, 0.08),
    "dining_chair": (0.88, 0.08), "sofa": (0.84, 0.12), "loveseat": (0.84, 0.12), "armchair": (0.88, 0.13),
    "office_chair": (1.05, 0.12), "bench": (0.45, 0.12), "ottoman": (0.42, 0.15), "coffee_table": (0.43, 0.15),
    "side_table": (0.56, 0.15), "nightstand": (0.58, 0.15), "dresser": (0.85, 0.2), "sideboard": (0.80, 0.12),
    "wardrobe": (2.0, 0.1), "floor_lamp": (1.6, 0.15), "tv_stand": (0.5, 0.2), "bookshelf": (1.8, 0.3),
    "cabinet": (0.9, 0.25), "fireplace": (1.15, 0.2), "radiator": (0.6, 0.3), "bed": (1.0, 0.3), "stool": (0.65, 0.25),
}
DOOR = (2.03, 0.04)
SOURCE_SIGMA = {"annotation": 0.03, "reference": 0.03, "known": 0.04, "depth": 0.25, "assumed": 0.13}


def _wmedian(values, weights) -> float:
    order = sorted(range(len(values)), key=lambda i: values[i])
    total, acc = sum(weights), 0.0
    for i in order:
        acc += weights[i]
        if acc >= total / 2:
            return values[i]
    return values[order[-1]]


def estimate(objects: list[dict], doors: list[float], max_factor: float = 1.5) -> tuple[float, float, int]:
    """Return (k, sigma_log, n) where true = k * measured, from object and door heights.

    Robust: weighted median, outliers beyond 2.5 MAD (at least 8 %) dropped, uncertainty
    inflated by the spread of the survivors and for single items; |log k| capped.
    ``objects``: dicts with archetype, height (measured, m), confidence, truncated (bool).
    """
    logs, weights = [], []
    for o in objects:
        if o.get("truncated") or o.get("confidence", 0) < 0.5 or o["archetype"] not in HEIGHTS or o["height"] <= 0.05:
            continue
        typ, sig = HEIGHTS[o["archetype"]]
        logs.append(math.log(typ / o["height"]))
        weights.append(1.0 / sig**2)
    for h in doors:
        if h > 0.5:
            logs.append(math.log(DOOR[0] / h))
            weights.append(1.0 / DOOR[1] ** 2)
    if not logs:
        return 1.0, math.inf, 0
    med = _wmedian(logs, weights)
    mad = _wmedian([abs(v - med) for v in logs], weights)
    tol = max(2.5 * 1.4826 * mad, 0.08)
    keep = [i for i, v in enumerate(logs) if abs(v - med) <= tol]
    w = [weights[i] for i in keep]
    vals = [logs[i] for i in keep]
    mean = sum(wi * vi for wi, vi in zip(w, vals)) / sum(w)
    sigma = 1.0 / math.sqrt(sum(w))
    if len(vals) > 1:
        spread = math.sqrt(sum(wi * (vi - mean) ** 2 for wi, vi in zip(w, vals)) / sum(w))
        sigma = max(sigma, spread)
    else:
        sigma = max(sigma, 0.15)
    if len(keep) < len(logs) / 2:
        sigma = max(sigma, 0.3)  # most items disagree: barely trust the estimate
    cap = math.log(max_factor)
    mean = max(-cap, min(cap, mean))
    return math.exp(mean), sigma, len(vals)


def combine(source_kind: str, k_obj: float, sigma_obj: float) -> tuple[float, float]:
    """Blend the current scale (k = 1, sigma from its source) with the object estimate."""
    s0 = SOURCE_SIGMA.get(source_kind, 0.13)
    if not math.isfinite(sigma_obj):
        return 1.0, s0
    w0, w1 = 1 / s0**2, 1 / sigma_obj**2
    logk = (w1 * math.log(k_obj)) / (w0 + w1)
    return math.exp(logk), 1 / math.sqrt(w0 + w1)


def occluded_ids(objects: list[dict], threshold: float = 0.15) -> set[str]:
    """Ids whose box is covered by another box that sits lower in the image (in front of it)."""
    out: set[str] = set()
    for a in objects:
        ax0, ay0, ax1, ay1 = a["box"]
        area = max(1e-9, (ax1 - ax0) * (ay1 - ay0))
        for b in objects:
            if b is a:
                continue
            bx0, by0, bx1, by1 = b["box"]
            if by1 <= ay1:  # b ends higher: behind a, cannot hide a's base
                continue
            iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
            if iw * ih / area > threshold:
                out.add(a["id"])
                break
    return out
