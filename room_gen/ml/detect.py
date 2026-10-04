"""Open-vocabulary detection (OWLv2) of furniture, doors and windows.

Raw per-query scores are decoded so every box is judged separately as furniture and as an
opening (the library post-processor keeps only the single best label per box, which lets
"picture frame" hide "window").
"""

from __future__ import annotations

import numpy as np

from room_gen import archetypes
from room_gen.ml.runtime import load

OPENING_PROMPTS = {"a door": "door", "a window": "window"}
STORAGE = {"bookshelf", "cabinet", "wardrobe", "dresser", "sideboard", "tv_stand", "counter"}


def _prompts() -> dict[str, str]:
    prompts = {f"a {name.replace('_', ' ')}": name for name in archetypes.names() if name != archetypes.FALLBACK}
    prompts.update({"a couch": "sofa", "a chair": "dining_chair", "a television": "tv", "a table": "dining_table", "a lamp": "table_lamp", "a cupboard": "cabinet"})
    return prompts


def _area(b) -> float:
    return float(max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]))


def _iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return inter / (_area(a) + _area(b) - inter + 1e-9)


def _nms(boxes: np.ndarray, scores: np.ndarray, thr: float) -> list[int]:
    keep: list[int] = []
    for i in np.argsort(-scores):
        if all(_iou(boxes[i], boxes[j]) < thr for j in keep):
            keep.append(int(i))
    return keep


def _inside_storage(box, others) -> bool:
    for ob, arch in others:
        if arch in STORAGE and _area(ob) > _area(box):
            x0, y0, x1, y1 = max(box[0], ob[0]), max(box[1], ob[1]), min(box[2], ob[2]), min(box[3], ob[3])
            if max(0, x1 - x0) * max(0, y1 - y0) >= 0.8 * _area(box):
                return True
    return False


def detect(rgb: np.ndarray, repo: str, device: str, threshold: float = 0.2, threshold_objects: float = 0.3) -> tuple[list[dict], list[dict]]:
    """Return (objects, openings): dicts with box (native px), label, archetype/kind, score."""
    import torch
    from PIL import Image

    proc, model, dtype = load("detect", repo, device)
    prompts = _prompts()
    obj_texts, open_texts = list(prompts), list(OPENING_PROMPTS)
    with torch.no_grad():
        inputs = proc(text=[obj_texts + open_texts], images=Image.fromarray(rgb), return_tensors="pt").to(device)
        inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
        out = model(**inputs)
    probs = torch.sigmoid(out.logits.float())[0].cpu().numpy()  # (boxes, queries)
    cxcywh = out.pred_boxes.float()[0].cpu().numpy()
    side = max(rgb.shape[:2])  # OWLv2 pads to a square at the bottom/right
    boxes = np.column_stack([cxcywh[:, 0] - cxcywh[:, 2] / 2, cxcywh[:, 1] - cxcywh[:, 3] / 2,
                             cxcywh[:, 0] + cxcywh[:, 2] / 2, cxcywh[:, 1] + cxcywh[:, 3] / 2]) * side
    h, w = rgb.shape[:2]
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
    size_ok = ((boxes[:, 2] - boxes[:, 0]) > 0.02 * w) & ((boxes[:, 3] - boxes[:, 1]) > 0.02 * h)
    n_obj = len(obj_texts)
    obj_q = probs[:, :n_obj].argmax(axis=1)
    obj_p = probs[np.arange(len(probs)), obj_q]
    open_q = probs[:, n_obj:].argmax(axis=1)
    open_p = probs[np.arange(len(probs)), n_obj + open_q]

    openings: list[dict] = []
    cand = np.where(size_ok & (open_p >= threshold))[0]
    for k in _nms(boxes[cand], open_p[cand], 0.4) if len(cand) else []:
        i = int(cand[k])
        openings.append({"kind": OPENING_PROMPTS[open_texts[int(open_q[i])]], "box": [round(float(v), 1) for v in boxes[i]], "score": round(float(open_p[i]), 3)})

    cand = np.where(size_ok & (obj_p >= threshold_objects))[0]
    kept = [int(cand[k]) for k in _nms(boxes[cand], obj_p[cand], 0.5)] if len(cand) else []
    gray = rgb.mean(axis=2)
    median_lum = float(np.median(gray))
    objects: list[dict] = []
    counts: dict[str, int] = {}
    for i in kept:
        arch = prompts[obj_texts[int(obj_q[i])]]
        box, score = boxes[i], float(obj_p[i])
        if arch == "picture_frame":
            x0, y0, x1, y1 = (int(v) for v in box)
            inside = float(gray[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 0.0
            rivals = [o for o in openings if o["kind"] == "window" and _iou(o["box"], box) > 0.5 and o["score"] >= 0.6 * score]
            if rivals or inside > 1.15 * median_lum:
                if not rivals:
                    openings.append({"kind": "window", "box": [round(float(v), 1) for v in box], "score": round(score * 0.8, 3)})
                continue
        if archetypes.get(arch).support == "floor" and _inside_storage(box, [(boxes[j], prompts[obj_texts[int(obj_q[j])]]) for j in kept if j != i]):
            continue
        counts[arch] = counts.get(arch, 0) + 1
        oid = arch.replace("_", "-") + (f"-{counts[arch]}" if counts[arch] > 1 else "")
        objects.append({"id": oid, "label": obj_texts[int(obj_q[i])][2:], "archetype": arch, "box": [round(float(v), 1) for v in box], "score": round(score, 3)})
    # an opening fully covered by a confident piece of furniture is usually furniture
    openings = [o for o in openings if not any(_iou(o["box"], ob["box"]) > 0.7 and ob["score"] > 1.5 * o["score"] and ob["archetype"] != "picture_frame" for ob in objects)]
    return objects, openings
