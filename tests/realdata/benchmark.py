"""Real-photo benchmark on SUN RGB-D's NYU frames, with paired 'twin' renders.

For every frame in tests/realdata/nyu_subset.json:

  photo-auto       the real photo, lines only (no models, no annotations)
  photo-annotated  the real photo plus SUN RGB-D's 2-D object boxes (stand-in for a person / Claude)
  photo-ml         the real photo with the local models
  twin-auto        a Blender render of the frame's ground truth (same camera, room and objects as
  twin-annotated   archetype furniture), scored against the same truth: the photo/twin gap
                   is how much harder real imagery is

Usage: uv run python -m tests.realdata.benchmark [--frames N] [--modes photo-auto,twin-auto,...]
Writes tests/realdata/REPORT.md and tests/realdata/out/realdata.json.
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

from room_gen.build import render_room
from room_gen.config import load_config
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json, write_json
from room_gen.project import Workspace
from room_gen.vision.objects import box_corners
from tests.eval.scoring import Truth, score
from tests.realdata import sunrgbd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "deps" / "sunrgbd" / "nyu"
MODES = ["photo-auto", "photo-annotated", "photo-ml", "twin-auto", "twin-annotated"]


def available_frames() -> list[str]:
    subset = json.loads((HERE / "nyu_subset.json").read_text())
    return [f["id"] for f in subset["frames"] if (DATA / f["id"] / "truth.json").is_file() and (DATA / f["id"] / "image.jpg").is_file()]


def load_truth(frame: str) -> tuple[dict, Truth]:
    t = read_json(DATA / frame / "truth.json")
    return t, Truth(PinholeCamera.from_dict(t["camera"]), np.array(t["floor_polygon"], float), float(t["ceiling_height"]), t["objects"])


def twin_boxes(t: dict) -> list[dict]:
    """2-D boxes of the twin's objects (projected 3-D boxes; the twin has no other source)."""
    cam = PinholeCamera.from_dict(t["camera"])
    out = []
    for o in t["objects"]:
        if not o["matched"]:
            continue
        c = box_corners(o["position"][0], o["position"][1], o["position"][2], *o["size"], o["yaw"])
        uv, z = cam.project(c)
        if (z <= 0.05).any():
            continue
        x0, y0 = np.clip(uv.min(axis=0), 0, [cam.width, cam.height])
        x1, y1 = np.clip(uv.max(axis=0), 0, [cam.width, cam.height])
        if (x1 - x0) * (y1 - y0) < 0.002 * cam.width * cam.height:
            continue
        out.append({**o, "box2d": [round(float(v), 1) for v in (x0, y0, x1, y1)]})
    return out


def _with_exif(src: Path, dst: Path, cam: PinholeCamera) -> None:
    """Save as JPEG with the 35 mm-equivalent focal length a phone would record (photo and twin alike)."""
    from PIL import Image

    img = Image.open(src).convert("RGB")
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0xA405] = int(round(cam.fx * 36.0 / max(cam.width, cam.height)))
    img.save(dst, quality=95, exif=exif)


def run_frame(frame: str, mode: str, out: Path) -> dict:
    from room_gen.pipeline import run_auto

    t, truth = load_truth(frame)
    kind, how = mode.split("-", 1)
    root = out / f"ws-{frame}-{mode}"
    shutil.rmtree(root, ignore_errors=True)
    (root / "input").mkdir(parents=True)
    if kind == "photo":
        _with_exif(DATA / frame / "image.jpg", root / "input" / f"{frame}.jpg", truth.camera)
    else:
        twin_png = out / "twins" / f"{frame}.png"
        if not twin_png.is_file():
            room, objects = sunrgbd.twin_scene(t)
            render_room(room, truth.camera, twin_png, objects=objects, samples=32, config=load_config(ROOT))
        _with_exif(twin_png, root / "input" / f"{frame}.jpg", truth.camera)
    ws = Workspace.open(root)
    world = ws.world(frame)
    world.ensure()
    world.stage_input()
    if how == "annotated":
        source = t if kind == "photo" else {**t, "objects": twin_boxes(t)}
        write_json(world.annotations_path, sunrgbd.annotations_from_truth(source, world.slug, world.rel(world.primary_image())))
    started = time.time()
    try:
        summary = run_auto(world, ml_mode="on" if how == "ml" else "off")
    except (ValueError, RuntimeError) as exc:
        return {"frame": frame, "mode": mode, "error": str(exc)}
    row = {"frame": frame, "scene": t.get("scene"), "mode": mode, "seconds": round(time.time() - started, 1),
           **score(truth, read_json(world.room_path), world.dir), "scale_source": summary["scale"]["source"]}
    return row


def rescore_frame(frame: str, mode: str, out: Path) -> dict | None:
    """Score a saved workspace again (after a scorer change) without re-running the pipeline."""
    old = {}
    saved = out / "realdata.json"
    if saved.is_file():
        old = {(r["frame"], r["mode"]): r for r in read_json(saved)["rows"]}
    world = Workspace.open(out / f"ws-{frame}-{mode}").world(frame)
    if not world.room_path.is_file():
        return old.get((frame, mode))
    t, truth = load_truth(frame)
    prev = old.get((frame, mode), {})
    return {"frame": frame, "scene": t.get("scene"), "mode": mode, "seconds": prev.get("seconds"),
            **score(truth, read_json(world.room_path), world.dir), "scale_source": prev.get("scale_source")}


def summarise(rows: list[dict]) -> dict[str, dict]:
    keys = ["focal_err_pct", "gravity_err_deg", "yaw_err_deg", "camera_height_err_pct", "ceiling_err_m", "layout_pixel_err_pct",
            "layout_depth_err_pct", "layout_depth_err_scaled_pct", "floor_iou", "visible_wall_err_m", "object_pos_err_m", "object_size_err_pct", "seconds"]
    out: dict[str, dict] = {}
    for mode in MODES:
        rs = [r for r in rows if r["mode"] == mode and "error" not in r]
        if not rs:
            continue
        agg = {"frames": len(rs), "failed": sum(1 for r in rows if r["mode"] == mode and "error" in r)}
        for k in keys:
            vals = [float(r[k]) for r in rs if r.get(k) is not None]
            agg[k] = round(float(np.median(vals)), 3) if vals else None
        m = [tuple(int(v) for v in r["objects_matched"].split("/")) for r in rs]
        agg["objects_matched"] = f"{sum(a for a, _ in m)}/{sum(b for _, b in m)}"
        out[mode] = agg
    return out


def report(rows: list[dict], out: Path) -> None:
    summary = summarise(rows)
    cols = ["frames", "layout_pixel_err_pct", "layout_depth_err_pct", "layout_depth_err_scaled_pct", "focal_err_pct", "gravity_err_deg",
            "camera_height_err_pct", "ceiling_err_m", "visible_wall_err_m", "objects_matched", "object_pos_err_m", "object_size_err_pct", "seconds"]
    lines = [
        "# Real-photo benchmark (SUN RGB-D, NYU Depth v2 frames)",
        "",
        "Regenerated by `uv run python -m tests.realdata.benchmark`. Data: deps/sunrgbd (research use only, not in git).",
        "Ground truth: SUN RGB-D camera intrinsics, gravity, room-layout polygon and 3-D object boxes (human labels,",
        "roughly 5-20 cm accurate). `twin-*` rows render each frame's ground truth in Blender from the true camera, so",
        "photo and twin share one truth: the difference between them is what real imagery costs. Both carry the EXIF",
        "35 mm-equivalent focal length a phone would record. `layout_pixel_err_pct` is the LSUN-style share of pixels",
        "whose surface (floor, ceiling, left/front/right wall) is wrong; `layout_depth_err*` is the median relative",
        "error of the depth to the room surfaces, raw and after correcting the overall scale by the true camera height.",
        "",
        f"Host: {platform.platform()}, Python {platform.python_version()}. Values are medians over frames.",
        "",
        "| mode | " + " | ".join(cols) + " |",
        "| --- | " + " | ".join("---" for _ in cols) + " |",
    ]
    for mode, agg in summary.items():
        lines.append(f"| {mode} | " + " | ".join(str(agg.get(c, "")) for c in cols) + " |")
    lines += ["", "## Per frame", "", "| frame | scene | mode | layout_pixel_err_pct | layout_depth_err_scaled_pct | camera_height_err_pct | ceiling_err_m | focal_err_pct | objects |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(rows, key=lambda r: (r["frame"], MODES.index(r["mode"]))):
        if "error" in r:
            lines.append(f"| {r['frame']} | | {r['mode']} | failed: {r['error'][:60]} | | | | | |")
            continue
        lines.append(f"| {r['frame']} | {r['scene']} | {r['mode']} | {r.get('layout_pixel_err_pct')} | {r.get('layout_depth_err_scaled_pct')} | {r['camera_height_err_pct']} | "
                     f"{r['ceiling_err_m']} | {r['focal_err_pct']} | {r['objects_matched']} |")
    (HERE / "REPORT.md").write_text("\n".join(lines) + "\n")
    write_json(out / "realdata.json", {"summary": summary, "rows": rows})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=0, help="first N frames of the subset (0 = all)")
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--rescore", action="store_true", help="re-score saved workspaces instead of running the pipeline")
    a = ap.parse_args()
    frames = available_frames()
    if not frames:
        raise SystemExit("no SUN RGB-D frames found: run `uv run python -m tests.realdata.fetch --accept-license` first")
    if a.frames:
        frames = frames[: a.frames]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for frame in frames:
        for mode in a.modes.split(","):
            row = rescore_frame(frame, mode, out) if a.rescore else run_frame(frame, mode, out)
            if row is None:
                continue
            rows.append(row)
            print(json.dumps(row, default=float), flush=True)
    report(rows, out)


if __name__ == "__main__":
    main()
