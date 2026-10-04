"""Synthetic round-trip benchmark (CLAUDE.md §12). Model-free and CI-able.

For each scene: render a photo in Blender from a known camera, run ``room_gen auto`` in
up to three modes, and score the result against the ground truth.

  auto        lines only: no models, no annotations (shell and camera only)
  annotated   object boxes from the ground truth (what a person or Claude provides)
  ml          local models (detection, segmentation, metric depth)

Usage: python -m tests.eval.benchmark [--scenes a,b] [--modes auto,annotated,ml] [--out tests/eval/out]
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from room_gen import archetypes
from room_gen.build import render_room
from room_gen.config import load_config
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json, write_json
from room_gen.project import Workspace
from room_gen.vision.objects import box_corners
from tests.eval.scenes import SCENES, scene

ROOT = Path(__file__).resolve().parents[2]


def truth_camera(sc: dict) -> PinholeCamera:
    c = sc["camera"]
    w, h = c["resolution"]
    return PinholeCamera.look_at(c["position"], c["target"], w, h, hfov_deg=c["hfov"])


def render_scene(sc: dict, out_dir: Path) -> Path:
    cam = truth_camera(sc)
    objs = []
    for pl in sc["room"]["placements"]:
        objs.append({"id": pl["object"], "recipe": sc["recipes"][pl["object"]], "placement": pl})
    png = out_dir / f"{sc['name']}.png"
    render_room(sc["room"], cam, png, objects=objs, samples=48, config=load_config(ROOT))
    if not sc["options"].get("jpeg"):
        return png
    jpg = out_dir / f"{sc['name']}.jpg"
    img = Image.open(png).convert("RGB")
    exif = Image.Exif()
    if sc["options"].get("exif_focal_35mm"):
        f35 = cam.fx * 36.0 / max(cam.width, cam.height)
        exif.get_ifd(0x8769)[0xA405] = int(round(f35))
        exif[0x010F] = "Synthetic"
    img.save(jpg, quality=93, exif=exif)
    return jpg


def truth_boxes(sc: dict) -> list[dict]:
    """2-D boxes of every placed object as a careful annotator would draw them."""
    from room_gen.build import prepare_recipe
    from room_gen.meshgen import recipe_bbox

    cam = truth_camera(sc)
    out = []
    for pl in sc["room"]["placements"]:
        rec, _ = prepare_recipe(sc["recipes"][pl["object"]])
        lo, hi = recipe_bbox(rec)
        w, d, h = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
        corners = box_corners(pl["position"][0], pl["position"][1], pl["position"][2], w, d, h, pl.get("yaw", 0.0))
        uv, z = cam.project(corners)
        if (z <= 0).any():
            continue
        x0, y0 = np.clip(uv.min(axis=0), 0, [cam.width, cam.height])
        x1, y1 = np.clip(uv.max(axis=0), 0, [cam.width, cam.height])
        if (x1 - x0) * (y1 - y0) < 0.002 * cam.width * cam.height:
            continue
        support = pl.get("support", "floor")
        out.append({"id": pl["object"], "label": rec["archetype"].replace("_", " "), "archetype": rec["archetype"],
                    "box": [round(float(v), 1) for v in (x0, y0, x1, y1)], "support": support,
                    "provenance": {"by": "human", "tool": "benchmark-truth", "confidence": 1.0}})
    return out


def _manhattan_align(r_true: np.ndarray, r_est: np.ndarray) -> np.ndarray:
    """Rotation about Z (multiple of 90 deg) mapping the estimated room frame to the truth frame."""
    q = r_true.T @ r_est
    best, best_err = None, 1e9
    for k in range(4):
        a = math.radians(90 * k)
        cand = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        err = np.linalg.norm(cand - q)
        if err < best_err:
            best, best_err = cand, err
    return best


def score(sc: dict, room: dict, summary: dict) -> dict:
    cam_t = truth_camera(sc)
    cam_e = PinholeCamera.from_dict(room["camera"])
    from room_gen.vision.calib import rotation_delta

    q = _manhattan_align(cam_t.R, cam_e.R)
    b = cam_t.C - q @ cam_e.C  # truth = q @ est + b (b uses the estimated scale)
    est_poly = np.array([q[:2, :2] @ p + b[:2] for p in np.array(room["shell"]["floor_polygon"])])
    tp = np.array(sc["room"]["shell"]["floor_polygon"])
    t_box = (tp[:, 0].min(), tp[:, 0].max(), tp[:, 1].min(), tp[:, 1].max())
    e_box = (est_poly[:, 0].min(), est_poly[:, 0].max(), est_poly[:, 1].min(), est_poly[:, 1].max())
    ix = max(0.0, min(t_box[1], e_box[1]) - max(t_box[0], e_box[0]))
    iy = max(0.0, min(t_box[3], e_box[3]) - max(t_box[2], e_box[2]))
    inter = ix * iy
    union = (t_box[1] - t_box[0]) * (t_box[3] - t_box[2]) + (e_box[1] - e_box[0]) * (e_box[3] - e_box[2]) - inter
    # wall-position error for walls the camera can see (truth edges in front of the camera)
    wall_err = []
    for name, ti, ei in (("x0", 0, 0), ("x1", 1, 1), ("y0", 2, 2), ("y1", 3, 3)):
        t_val, e_val = t_box[ti], e_box[ei]
        normal = np.array([1.0, 0, 0]) if name.startswith("x") else np.array([0, 1.0, 0])
        if (cam_t.R @ (normal * (1 if name.endswith("1") else -1)))[2] > 0.15:
            wall_err.append(abs(t_val - e_val))
    res = {
        "focal_err_pct": round(100 * abs(cam_e.fx - cam_t.fx) / cam_t.fx, 2),
        "rotation_err_deg": round(rotation_delta(cam_e.R, cam_t.R), 3),
        "camera_height_err_pct": round(100 * abs(cam_e.C[2] - cam_t.C[2]) / cam_t.C[2], 1),
        "ceiling_err_m": round(abs(room["shell"]["ceiling_height"] - sc["room"]["shell"]["ceiling_height"]), 3),
        "floor_iou": round(inter / union, 3) if union > 0 else 0.0,
        "visible_wall_err_m": round(float(np.mean(wall_err)), 3) if wall_err else None,
        "openings": f"{sum(len(w['openings']) for w in room['shell']['walls'])}/{sum(len(w.get('openings', [])) for w in sc['room']['shell']['walls'])}",
    }
    # objects: match by archetype, nearest in the truth frame
    truth = {pl["object"]: pl for pl in sc["room"]["placements"]}
    matched, pos_err, size_err = 0, [], []
    used = set()
    for pl in room.get("placements", []):
        rec = read_json(Path(summary["_world_dir"]) / "output" / pl["object"] / "recipe.json")
        arch = rec.get("archetype")
        p = q @ np.array(pl["position"]) + b
        cands = [(np.linalg.norm(np.array(t["position"][:2]) - p[:2]), k) for k, t in truth.items()
                 if k not in used and archetypes.resolve(sc["recipes"][k]["archetype"])[0] == arch]
        if not cands:
            continue
        dist, k = min(cands)
        if dist > 1.0:
            continue
        used.add(k)
        matched += 1
        pos_err.append(dist)
        want = [sc["recipes"][k]["params"][key] for key in ("width", "depth", "height")]
        got = pl.get("size_m") or want
        size_err.append(float(np.mean([abs(g - w_) / w_ for g, w_ in zip(got, want)])))
    res["objects_matched"] = f"{matched}/{len(truth)}"
    res["object_pos_err_m"] = round(float(np.median(pos_err)), 3) if pos_err else None
    res["object_size_err_pct"] = round(100 * float(np.median(size_err)), 1) if size_err else None
    return res


def run(scenes: list[str], modes: list[str], out: Path, write_report: bool = True) -> list[dict]:
    from room_gen.ml import runtime
    from room_gen.pipeline import run_auto

    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in scenes:
        sc = scene(name)
        photo = render_scene(sc, out)
        for mode in modes:
            if mode == "ml" and not runtime.installed():
                continue
            root = out / f"ws-{name}-{mode}"
            shutil.rmtree(root, ignore_errors=True)
            (root / "input").mkdir(parents=True)
            shutil.copy(photo, root / "input" / photo.name)
            ws = Workspace.open(root)
            world = ws.world(name)
            world.ensure()
            world.stage_input()
            if mode == "annotated":
                img = Image.open(world.primary_image())
                write_json(world.annotations_path, {"world": world.slug, "image": world.rel(world.primary_image()), "image_size": list(img.size),
                                                    "objects": truth_boxes(sc), "provenance": {"by": "human", "tool": "benchmark", "confidence": 1.0}})
            t = time.time()
            summary = run_auto(world, ml_mode="on" if mode == "ml" else "off")
            seconds = time.time() - t
            summary["_world_dir"] = str(world.dir)
            room = read_json(world.room_path)
            row = {"scene": name, "mode": mode, "seconds": round(seconds, 1), **score(sc, room, summary),
                   "scale_source": summary["scale"]["source"]}
            rows.append(row)
            print(json.dumps(row), flush=True)
    if write_report:
        _report(rows, out)
    return rows


def _report(rows: list[dict], out: Path) -> None:
    cols = ["scene", "mode", "focal_err_pct", "rotation_err_deg", "camera_height_err_pct", "ceiling_err_m", "floor_iou",
            "visible_wall_err_m", "openings", "objects_matched", "object_pos_err_m", "object_size_err_pct", "seconds"]
    lines = [
        "# Synthetic round-trip benchmark",
        "",
        "Regenerated by `python -m tests.eval.benchmark`. Photos are Blender renders of rooms with known geometry",
        "(`tests/eval/scenes.py`); every number compares the reconstruction with that ground truth.",
        "",
        "Modes: `auto` uses lines only (no models, no annotations). `annotated` adds ground-truth object boxes, standing in",
        "for a person in the annotator or Claude. `ml` uses the local models (detection, segmentation, metric depth).",
        "Metric errors in `auto` and `annotated` include the unknown overall scale unless a cue fixes it.",
        "",
        f"Host: {platform.platform()}, Python {platform.python_version()}.",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    lines += ["", "Scale sources:", ""]
    lines += [f"- {r['scene']} / {r['mode']}: {r['scale_source']}" for r in rows]
    (Path(__file__).resolve().parent / "REPORT.md").write_text("\n".join(lines) + "\n")
    write_json(out / "benchmark.json", rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default=",".join(SCENES))
    ap.add_argument("--modes", default="auto,annotated,ml")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    a = ap.parse_args()
    run(a.scenes.split(","), a.modes.split(","), Path(a.out))


if __name__ == "__main__":
    main()
