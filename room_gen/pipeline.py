"""``room_gen auto``: photo -> annotations, calibration, room.json, recipes (model-free core).

Blocks written by a person or by Claude (``provenance.by`` in {human, model}) are kept;
only ``auto``/``fit`` blocks are regenerated.
"""

from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from room_gen import archetypes
from room_gen.exif import focal_px_from_exif
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json_if_exists, write_json
from room_gen.models import Annotations, Calibration, Room
from room_gen.project import World
from room_gen.sidecar import now_iso
from room_gen.vision import calib as vcalib
from room_gen.vision.fit import draw_overlay, fit_camera_and_room
from room_gen.vision.imageio import load_photo, to_gray
from room_gen.vision.layout import estimate_layout
from room_gen.vision.light import estimate_lighting
from room_gen.vision.lines import OrientedEdges, detect_segments, enhance, side_contrast
from room_gen.vision.objects import fit_object, grabcut_mask
from room_gen.vision.wireframe import RegionColors, SegmentFamilies
from room_gen.vision.openings import opening_from_quad
from room_gen.vision.texture import rectify_shell

LOCKED = ("human", "model")


def _locked(block: dict | None) -> bool:
    return bool(block) and (block.get("provenance") or {}).get("by") in LOCKED


class Timer:
    def __init__(self):
        self.t = time.time()
        self.steps: dict[str, float] = {}

    def mark(self, name: str) -> None:
        now = time.time()
        self.steps[name] = round(now - self.t, 2)
        self.t = now


def _load_annotations(world: World, photo_rel: str, size: tuple[int, int], exif: dict) -> dict:
    data = read_json_if_exists(world.annotations_path)
    if data:
        ann = Annotations.model_validate(data).model_dump(mode="json", exclude_none=True)
        if ann.get("image") != photo_rel:
            ann["notes"] = ann.get("notes", []) + [f"image changed from {ann.get('image')} to {photo_rel}; auto items reset"]
            ann["objects"] = [o for o in ann.get("objects", []) if (o.get("provenance") or {}).get("by") in LOCKED]
            ann["openings"] = [o for o in ann.get("openings", []) if (o.get("provenance") or {}).get("by") in LOCKED]
            ann["image"] = photo_rel
            ann["image_size"] = list(size)
    else:
        ann = {"schema_version": 1, "world": world.slug, "image": photo_rel, "image_size": list(size),
               "calibration": {}, "objects": [], "openings": [], "provenance": {"by": "auto", "tool": "room_gen auto", "confidence": 0.5}}
    if exif:
        ann.setdefault("calibration", {})["exif"] = {k: v for k, v in exif.items() if k in ("focal_mm", "focal_35mm", "make", "model", "orientation")}
    return ann


def _scale(ann: dict, cal, s: float, depth_pts, notes: list[str]) -> tuple[float, str, float]:
    """Camera height in metres and where it came from."""
    hints = ann.get("calibration", {})
    cam1 = cal.camera(1.0)
    if hints.get("camera_height_m"):
        return float(hints["camera_height_m"]), "annotation: camera height", 0.9
    ref = hints.get("reference")
    if ref:
        (bu, bv), (tu, tv) = ref["pixels"]
        h = vcalib.height_from_reference(cam1, (bu * s, bv * s), (tu * s, tv * s), ref["metres"])
        if h and 0.3 < h < 4.0:
            return h, f"reference: {ref.get('label') or 'vertical'} {ref['metres']} m", 0.85
        notes.append("reference could not be used (bottom pixel above the horizon?)")
    vals = []
    for kl in ann.get("known_lengths", []):
        (au, av), (bu, bv) = kl["pixels"]
        h = vcalib.height_from_floor_length(cam1, (au * s, av * s), (bu * s, bv * s), kl["metres"])
        if h and 0.3 < h < 4.0:
            vals.append(h)
    if vals:
        return float(np.median(vals)), f"known floor lengths ({len(vals)})", 0.8
    if depth_pts is not None:
        from room_gen.ml.depth import camera_height

        h = camera_height(depth_pts)
        if h and 0.8 <= h <= 2.2:
            return h, "metric depth model (floor plane)", 0.65
        if h:
            notes.append(f"depth model floor gives an implausible camera height ({h:.2f} m); ignored")
    return 1.5, "assumed eye height 1.5 m", 0.3


def run_auto(world: World, *, ml_mode: str | None = None, device: str | None = None, fit: bool | None = None,
             textures: bool | None = None, detect_objects: bool = True) -> dict[str, Any]:
    cfg = world.ws.config
    timer = Timer()
    world.ensure()
    photo_path = world.primary_image()
    if photo_path is None:
        raise FileNotFoundError(f"no source image in {world.workspace_rel(world.path('source'))}; put a photo in input/ and run `room_gen project --stage-input`")
    photo = load_photo(photo_path)
    W, H = photo.size
    small, s = photo.working(int(cfg.get("working_long_side", 1024)))
    gray = to_gray(small)
    photo_rel = world.rel(photo_path)
    ann = _load_annotations(world, photo_rel, (W, H), photo.exif)
    notes: list[str] = []
    timer.mark("load")

    # ---- optional local models ---------------------------------------------------------
    from room_gen.ml import runtime

    use_ml = runtime.enabled(cfg, ml_mode)
    ml_cfg = cfg.get("ml", {})
    dev = runtime.pick_device(device or ml_cfg.get("device", "auto")) if use_ml else None
    depth_small = None
    models_used: dict[str, str] = {}
    if use_ml:
        from room_gen.ml.depth import estimate_depth
        from room_gen.ml.detect import detect

        locked_objects = [o for o in ann["objects"] if (o.get("provenance") or {}).get("by") in LOCKED]
        if detect_objects and not locked_objects:
            dets, ops = detect(photo.rgb, ml_cfg["detect_model"], dev, float(ml_cfg.get("opening_threshold", 0.2)), float(ml_cfg.get("detect_threshold", 0.3)))
            ann["objects"] = [{**d, "support": "floor", "provenance": {"by": "auto", "tool": ml_cfg["detect_model"], "confidence": d["score"]}} for d in dets]
            if not [o for o in ann["openings"] if (o.get("provenance") or {}).get("by") in LOCKED]:
                ann["openings"] = [{"kind": o["kind"], "quad": [[o["box"][0], o["box"][1]], [o["box"][2], o["box"][1]], [o["box"][2], o["box"][3]], [o["box"][0], o["box"][3]]],
                                    "provenance": {"by": "auto", "tool": ml_cfg["detect_model"], "confidence": o["score"]}} for o in ops]
            models_used["detect"] = ml_cfg["detect_model"]
        depth_native = estimate_depth(photo.rgb, ml_cfg["depth_model"], dev)
        depth_small = cv2.resize(depth_native, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        models_used["depth"] = ml_cfg["depth_model"]
        timer.mark("models")

    # ---- calibration ---------------------------------------------------------------------
    segs = detect_segments(enhance(small))
    hints = ann.get("calibration", {})
    focal_prior = focal_px_from_exif(hints.get("exif") or {}, W, H)
    if hints.get("parallel_pairs") and len({p["axis"] for p in hints["parallel_pairs"]}) + (1 if len(hints.get("vertical_lines", [])) >= 2 else 0) >= 2:
        cal = vcalib.calibrate_manual(hints, small.shape[1], small.shape[0], segs=segs, scale=s, focal_prior=focal_prior * s if focal_prior else None)
    else:
        cal = vcalib.calibrate_auto(segs, small.shape[1], small.shape[0], focal_prior=focal_prior * s if focal_prior else None)
    timer.mark("calibrate")
    depth_pts = None
    if depth_small is not None:
        from room_gen.ml.depth import world_points

        depth_pts, _ = world_points(depth_small, cal.camera(1.0))
    cam_h, scale_source, scale_conf = _scale(ann, cal, s, depth_pts, notes)
    cam = cal.camera(cam_h)

    # ---- layout + fit (skipped when the shell is locked) ---------------------------------------
    existing_room = read_json_if_exists(world.room_path)
    shell_locked = _locked((existing_room or {}).get("shell"))
    contrast = side_contrast(small, segs)
    edges = OrientedEdges(segs[contrast >= 4.0], gray.shape)
    fit_report = None
    masks_pre: dict[str, np.ndarray] = {}
    if shell_locked:
        room_shell = existing_room["shell"]
        notes.append("shell is locked (human/model); layout and fit skipped")
        cam_room = PinholeCamera.from_dict(existing_room["camera"]).scaled(s) if existing_room.get("camera") else None
        poly = room_shell["floor_polygon"]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        lay_box = (min(xs), max(xs), min(ys), max(ys))
        ceiling_h = room_shell["ceiling_height"]
        lay_conf = room_shell.get("provenance", {}).get("confidence", 0.9)
        offset = np.zeros(2)
        lay = None
    else:
        prior = None
        if depth_pts is not None:
            from room_gen.ml.depth import layout_prior

            prior = layout_prior(depth_pts * (1.0), cam_h)
        corners = [(u * s, v * s) for u, v in ann.get("floor_corners", [])]
        families = SegmentFamilies(segs, cal.labels)
        regions = RegionColors(small)
        hints = _boundary_hints(ann, s, small.shape[:2])
        lay = estimate_layout(edges, cam, corners_uv=corners, ceiling_height=ann.get("ceiling_height_m"), prior=None, defaults=cfg.get("defaults"),
                              families=families, regions=regions, hints=hints)
        if prior:
            notes.append("depth model layout prior: " + ", ".join(f"{k}={v:.2f}" for k, v in prior.items()))
            lay = _reconcile(lay, prior, edges, cam, corners, ann, cfg, notes, families)
        timer.mark("layout")
        do_fit = cfg.get("fit", {}).get("enabled", True) if fit is None else fit
        if do_fit:
            free = {"y0": lay.visible[0], "x1": lay.visible[1], "y1": lay.visible[2], "x0": lay.visible[3]}
            fit_report = fit_camera_and_room(edges, cam, dict(zip(("x0", "x1", "y0", "y1", "h"), lay.as_tuple())), free_walls=free,
                                             fit_h=lay.ceiling_visible and not ann.get("ceiling_height_m"),
                                             max_evals=int(cfg.get("fit", {}).get("max_evals", 400)), fit_focal=cal.finite_vps >= 2)
            cam = fit_report.pop("camera")
            for k, v in fit_report["layout"].items():
                setattr(lay, k, v)
            timer.mark("fit")
        # scale correction from standard object heights (needs boxes: annotated or detected)
        k_scale = _object_scale(ann, small, s, cam, lay, masks_pre, depth_small, use_ml, ml_cfg, dev, photo, scale_source, notes)
        if abs(k_scale - 1.0) > 0.01:
            cam_h *= k_scale
            cam = PinholeCamera(cam.fx, cam.fy, cam.cx, cam.cy, cam.width, cam.height, cam.R, cam.C * k_scale)
            for key in ("x0", "x1", "y0", "y1", "h"):
                setattr(lay, key, getattr(lay, key) * k_scale)
            scale_source = f"{scale_source}; corrected x{k_scale:.3f} by standard object heights"
            scale_conf = min(0.8, scale_conf + 0.15)
        from room_gen.vision.layout import contain_camera

        contain_camera(lay, cam)
        offset = np.array([(lay.x0 + lay.x1) / 2, (lay.y0 + lay.y1) / 2])
        cam_room = PinholeCamera(cam.fx, cam.fy, cam.cx, cam.cy, cam.width, cam.height, cam.R, cam.C - np.array([offset[0], offset[1], 0.0]))
        hx, hy = (lay.x1 - lay.x0) / 2, (lay.y1 - lay.y0) / 2
        lay_box = (-hx, hx, -hy, hy)
        ceiling_h = lay.h
        lay_conf = lay.confidence
        room_shell = None

    # ---- openings -----------------------------------------------------------------------------
    poly = [(lay_box[0], lay_box[2]), (lay_box[1], lay_box[2]), (lay_box[1], lay_box[3]), (lay_box[0], lay_box[3])]
    if room_shell is None:
        walls = {i: {"edge": i, "material": f"wall_{i}", "openings": []} for i in range(4)}
        for op in ann.get("openings", []):
            quad = [(u * s, v * s) for u, v in op["quad"]]
            got = opening_from_quad(cam_room, poly, ceiling_h, quad, op["kind"], op.get("wall_hint"))
            if got is None:
                notes.append(f"{op['kind']} at {op['quad'][0]} could not be placed on a wall")
                continue
            edge, spec = got
            conf = (op.get("provenance") or {}).get("confidence", 0.5)
            by = (op.get("provenance") or {}).get("by", "auto")
            if by == "auto" and conf < 0.2:
                continue
            spec["provenance"] = {"by": by, "tool": "openings", "confidence": round(float(conf), 3)}
            if not any(abs(o["offset"] - spec["offset"]) < 0.2 and abs(o["sill"] - spec["sill"]) < 0.3 for o in walls[edge]["openings"]):
                walls[edge]["openings"].append(spec)
        L = [lay_box[1] - lay_box[0], lay_box[3] - lay_box[2]] * 2
        for edge, wall in walls.items():
            wall["openings"].sort(key=lambda o: o["offset"])
            kept = []
            for o in wall["openings"]:
                o["width"] = min(o["width"], [L[0], L[1], L[0], L[1]][edge] - o["offset"] - 0.01)
                if kept and o["offset"] < kept[-1]["offset"] + kept[-1]["width"] + 0.05:
                    continue
                if o["width"] > 0.2:
                    kept.append(o)
            wall["openings"] = kept
        room_shell = {
            "floor_polygon": [list(p) for p in poly],
            "ceiling_height": round(float(ceiling_h), 4),
            "wall_thickness": float(cfg.get("defaults", {}).get("wall_thickness_m", 0.12)),
            "walls": list(walls.values()),
            "floor": {"material": "floor"},
            "ceiling": {"material": "ceiling"},
            "visible_edges": [i for i in range(4) if lay.visible[i]],
            "guessed_edges": [i for i in range(4) if not lay.visible[i]],
            "provenance": {"by": "fit" if fit_report else "auto", "tool": "layout+fit" if fit_report else "layout", "confidence": lay_conf},
        }
    timer.mark("openings")

    # ---- objects ------------------------------------------------------------------------------
    masks: dict[str, np.ndarray] = dict(masks_pre)
    objs = ann.get("objects", [])
    if use_ml and objs and not masks:
        from room_gen.ml.segment import masks_for_boxes

        for o, m in zip(objs, masks_for_boxes(photo.rgb, [o["box"] for o in objs], ml_cfg["segment_model"], dev)):
            masks[o["id"]] = cv2.resize(m.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
        models_used["segment"] = ml_cfg["segment_model"]
    order = sorted(objs, key=lambda o: archetypes.get(o.get("archetype") or archetypes.resolve(o["label"])[0]).support == "surface")
    fits = {}
    supports: dict[str, dict] = {}
    for o in order:
        box_small = [v * s for v in o["box"]]
        m = masks.get(o["id"])
        if m is None:
            m = grabcut_mask(small, box_small)
            masks[o["id"]] = m
        f = fit_object(cam_room, small, {**o, "box": box_small}, room_box=lay_box, ceiling_h=ceiling_h, mask=m, supports=supports, depth=depth_small)
        fits[o["id"]] = (o, f)
        supports[o["id"]] = {"box": box_small, "top": f.position[2] + f.size[2]}
    timer.mark("objects")

    # ---- lighting -----------------------------------------------------------------------------
    lighting = (existing_room or {}).get("lighting")
    if not _locked(lighting):
        lighting = estimate_lighting(small, room_shell)

    # ---- materials and photo textures -----------------------------------------------------------
    materials = dict((existing_room or {}).get("materials") or {})
    tex_info = {}
    do_tex = cfg.get("texture", {}).get("enabled", True) if textures is None else textures
    if do_tex:
        occ = np.zeros(small.shape[:2], bool)
        for m in masks.values():
            occ |= m
        occ_native = cv2.resize(occ.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(bool)
        occ_native = cv2.dilate(occ_native.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        key = hashlib.sha1(photo_path.read_bytes()).hexdigest()[:8]
        tex_info = rectify_shell(photo.rgb, cam_room.scaled(1.0 / s), room_shell, world.path("output", "world", "textures"), 0,
                                 occluder=occ_native, size=int(cfg.get("texture", {}).get("size", 2048)),
                                 min_coverage=float(cfg.get("texture", {}).get("min_coverage", 0.05)))
        for name, info in tex_info.items():
            if info.get("path"):
                p = Path(info["path"])
                final = p.with_name(f"photo-{key}-{name}.png")
                p.replace(final)
                info["path"] = str(final)
        timer.mark("textures")
    def surface_material(name: str, fallback: str, roughness: float) -> dict:
        info = tex_info.get(name, {})
        mat = {"base_color": info.get("mean_color") or fallback, "roughness": roughness}
        if info.get("path"):
            mat["image"] = world.rel(info["path"])
        return mat
    if not _locked((existing_room or {}).get("shell")):
        materials["floor"] = surface_material("floor", "#a37a52", 0.55)
        materials["ceiling"] = surface_material("ceiling", "#f3f2ef", 0.95)
        for i in range(4):
            materials[f"wall_{i}"] = surface_material(f"wall-{i}", "#e6e2da", 0.9)

    # ---- placements and recipes ------------------------------------------------------------------
    old_pl = {p["object"]: p for p in (existing_room or {}).get("placements", [])}
    placements = []
    object_boxes = []
    for oid, (o, f) in fits.items():
        if oid in old_pl and _locked(old_pl[oid]):
            placements.append(old_pl[oid])
            continue
        pl = {"object": oid, "position": [round(v, 4) for v in f.position], "yaw": round(f.yaw, 2), "scale": 1.0,
              "support": f.support, "size_m": [round(v, 4) for v in f.size],
              "provenance": {"by": "auto", "tool": "objects", "confidence": f.confidence}}
        placements.append(pl)
        object_boxes.append({"id": oid, "position": f.position, "size": f.size, "yaw": f.yaw})
        _write_recipe(world, o, f)
        _write_object_json(world, o, f, photo_rel)
    for oid, pl in old_pl.items():
        if oid not in fits and _locked(pl):
            placements.append(pl)

    # ---- assemble -----------------------------------------------------------------------------
    camera_block = {**cam_room.scaled(1.0 / s).to_dict(), "provenance": {"by": "fit" if fit_report else "auto", "tool": "calib", "confidence": cal.confidence}}
    if existing_room and _locked(existing_room.get("camera")):
        camera_block = existing_room["camera"]
    room = {
        "schema_version": 1,
        "world": world.slug,
        "source_images": [photo_rel],
        "calibration": "calibration.json",
        "scale": {"reference": scale_source, "confidence": scale_conf},
        "shell": room_shell,
        "fixed_features": (existing_room or {}).get("fixed_features", []),
        "materials": materials,
        "lighting": lighting,
        "camera": camera_block,
        "placements": placements,
        "notes": notes + (lay.notes if lay else []),
        "updated_at": now_iso(),
    }
    room = Room.model_validate(room).model_dump(mode="json", exclude_none=True)
    write_json(world.room_path, room)
    calib_doc = Calibration.model_validate({
        "world": world.slug, "image": photo_rel, "image_size": [W, H],
        "fx": cal.f / s, "fy": cal.f / s, "cx": cal.cx / s, "cy": cal.cy / s,
        "R": cam.R.tolist(), "camera_position": [0.0, 0.0, cam_h], "camera_height_m": cam_h,
        "vanishing_points": [{**vp, "point": vp["point"], "support_px": 0.0} for vp in cal.scaled(1.0 / s).vanishing_points()],
        "method": cal.method, "focal_source": cal.focal_source, "scale_source": scale_source,
        "residual_deg": round(cal.residual_deg, 4), "hfov_deg": round(math.degrees(2 * math.atan(W / (2 * cal.f / s))), 3),
        "notes": cal.notes, "provenance": {"by": "auto", "tool": "calib", "confidence": cal.confidence},
    })
    write_json(world.calibration_path, calib_doc)
    write_json(world.annotations_path, Annotations.model_validate(ann))
    overlay = draw_overlay(photo.rgb, cam_room.scaled(1.0 / s), room, world.path("output", "world", "overlay.png"),
                           [{**b, "position": b["position"]} for b in object_boxes])
    timer.mark("write")
    return {
        "world": world.slug,
        "image": photo_rel,
        "models": models_used or None,
        "calibration": {"method": cal.method, "focal_px": round(cal.f / s, 2), "hfov_deg": calib_doc.hfov_deg, "confidence": cal.confidence,
                        "finite_vanishing_points": cal.finite_vps, "residual_deg": round(cal.residual_deg, 3)},
        "scale": {"camera_height_m": round(cam_h, 3), "source": scale_source, "confidence": scale_conf},
        "shell": {"size_m": [round(lay_box[1] - lay_box[0], 3), round(lay_box[3] - lay_box[2], 3)], "ceiling_height": round(float(ceiling_h), 3),
                  "visible_edges": room_shell.get("visible_edges"), "openings": sum(len(w["openings"]) for w in room_shell["walls"]),
                  "confidence": room_shell.get("provenance", {}).get("confidence")},
        "fit": fit_report,
        "objects": [{"id": oid, "archetype": f.archetype, "size_m": [round(v, 3) for v in f.size], "position": [round(v, 3) for v in f.position],
                     "yaw": f.yaw, "confidence": f.confidence, "notes": f.notes} for oid, (o, f) in fits.items()],
        "textures": {k: v.get("coverage") for k, v in tex_info.items()},
        "overlay": world.workspace_rel(overlay),
        "notes": room["notes"],
        "seconds": timer.steps,
    }


def _boundary_hints(ann: dict, s: float, shape) -> dict | None:
    """Annotated boundary polylines -> one OrientedEdges per boundary kind (working pixels)."""
    by_kind: dict[str, list] = {}
    for bl in ann.get("boundary_lines", []):
        pts = [(u * s, v * s) for u, v in bl["pixels"]]
        for a, b in zip(pts, pts[1:]):
            by_kind.setdefault(bl["kind"], []).append([a[0], a[1], b[0], b[1]])
    if not by_kind:
        return None
    return {k: OrientedEdges(np.array(v, float), shape) for k, v in by_kind.items()}


def _reconcile(lay, prior, edges, cam, corners, ann, cfg, notes, families=None):
    """Combine the line layout with the depth model's extents.

    Seen walls with weak line support move toward the depth estimate; unseen walls only
    have to contain the depth points; an unseen ceiling is at least as high as them.
    """
    for wall, k, outward in ((1, "x1", 1), (2, "y1", 1), (3, "x0", -1)):
        if k not in prior:
            continue
        cur = getattr(lay, k)
        if lay.visible[wall] and lay.wall_support[wall] < 0.3:
            setattr(lay, k, 0.5 * cur + 0.5 * prior[k])
            notes.append(f"wall {wall} ({k}) blended with metric depth (weak line support)")
        elif not lay.visible[wall] and outward * (prior[k] + outward * 0.1 - cur) > 0:
            setattr(lay, k, prior[k] + outward * 0.1)
            notes.append(f"wall {wall} ({k}) pushed out to contain the depth points")
    if "h" in prior and not lay.ceiling_visible and not ann.get("ceiling_height_m") and prior["h"] > lay.h:
        lay.h = prior["h"]
        notes.append("ceiling raised to contain the depth points")
    return lay


def _object_scale(ann, small, s, cam, lay, masks_out, depth_small, use_ml, ml_cfg, dev, photo, scale_source, notes) -> float:
    """Fit annotated objects at the current scale and compare their heights to typical ones."""
    from room_gen.vision import scale as vscale

    objs = ann.get("objects", [])
    if not objs:
        return 1.0
    if use_ml:
        from room_gen.ml.segment import masks_for_boxes

        for o, m in zip(objs, masks_for_boxes(photo.rgb, [o["box"] for o in objs], ml_cfg["segment_model"], dev)):
            masks_out[o["id"]] = cv2.resize(m.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
    box = (lay.x0, lay.x1, lay.y0, lay.y1)
    hidden = vscale.occluded_ids(objs)
    measured = []
    for o in objs:
        box_small = [v * s for v in o["box"]]
        m = masks_out.get(o["id"])
        if m is None:
            m = grabcut_mask(small, box_small)
            masks_out[o["id"]] = m
        f = fit_object(cam, small, {**o, "box": box_small}, room_box=box, ceiling_h=lay.h, mask=m, depth=None)
        ys = np.nonzero(m)[0]
        truncated = len(ys) == 0 or ys.min() <= 2 or ys.max() >= m.shape[0] - 3 or o["id"] in hidden
        if f.support == "floor":
            measured.append({"archetype": f.archetype, "height": f.size[2], "confidence": f.confidence, "truncated": truncated})
    doors = []
    for op in ann.get("openings", []):
        if op["kind"] == "door":
            got = opening_from_quad(cam, [(lay.x0, lay.y0), (lay.x1, lay.y0), (lay.x1, lay.y1), (lay.x0, lay.y1)], lay.h, [(u * s, v * s) for u, v in op["quad"]], "door")
            if got and got[1]["sill"] < 0.05:
                doors.append(got[1]["height"])
    k_obj, sig_obj, n = vscale.estimate(measured, doors)
    kind = "annotation" if scale_source.startswith("annotation") else "reference" if scale_source.startswith("reference") else \
        "known" if scale_source.startswith("known") else "depth" if "depth" in scale_source else "assumed"
    k, _ = vscale.combine(kind, k_obj, sig_obj)
    if n:
        notes.append(f"object heights suggest scale x{k_obj:.3f} from {n} items; applied x{k:.3f}")
    return k


def _write_recipe(world: World, ann_obj: dict, f) -> None:
    path = world.object_dir(f.id) / "recipe.json"
    existing = read_json_if_exists(path)
    if existing and (existing.get("provenance") or {}).get("params_by") in LOCKED:
        return
    arch = archetypes.get(f.archetype)
    slots = arch.slots
    mats: dict[str, dict] = {}
    for slot, color in zip(slots, f.colors):
        mats[slot] = {"base_color": color}
    recipe = {
        "schema_version": 1, "world": world.slug, "object": f.id, "archetype": f.archetype,
        "params": {"width": round(f.size[0], 4), "depth": round(f.size[1], 4), "height": round(f.size[2], 4)},
        "materials": mats,
        "provenance": {"archetype_by": (ann_obj.get("provenance") or {}).get("by", "auto"), "params_by": "auto", "colors_by": "auto"},
        "notes": "; ".join(f.notes),
    }
    write_json(path, recipe)


def _write_object_json(world: World, ann_obj: dict, f, photo_rel: str) -> None:
    path = world.object_dir(f.id) / "object.json"
    if path.is_file():
        return
    write_json(path, {
        "schema_version": 1, "world": world.slug,
        "object": {"id": f.id, "name": f.label, "description": f"{f.label} ({f.archetype})", "materials": list(ann_obj.get("materials_hint", [])),
                   "source_images": [photo_rel], "evidence": [{"image": photo_rel, "box": ann_obj["box"]}],
                   "generate_as_3d_object": True, "working_dir": world.workspace_rel(world.object_dir(f.id))},
        "updated_at": now_iso(),
    })
