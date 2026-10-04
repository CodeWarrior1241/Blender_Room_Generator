"""Box-prompted segmentation (SAM)."""

from __future__ import annotations

import numpy as np

from room_gen.ml.runtime import load


def masks_for_boxes(rgb: np.ndarray, boxes: list, repo: str, device: str) -> list[np.ndarray]:
    """One boolean mask (image size) per box; the highest-IoU proposal is kept."""
    if not boxes:
        return []
    import torch
    from PIL import Image

    proc, model, dtype = load("segment", repo, device)
    img = Image.fromarray(rgb)
    with torch.no_grad():
        inputs = proc(images=img, input_boxes=[[list(map(float, b)) for b in boxes]], return_tensors="pt").to(device)
        inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
        out = model(**inputs, multimask_output=True)
    masks = proc.image_processor.post_process_masks(out.pred_masks.float().cpu(), inputs["original_sizes"].cpu(), inputs["reshaped_input_sizes"].cpu())[0]
    iou = out.iou_scores.float().cpu().numpy()[0]
    result = []
    for k in range(len(boxes)):
        best = int(np.argmax(iou[k]))
        result.append(masks[k, best].numpy().astype(bool))
    return result
