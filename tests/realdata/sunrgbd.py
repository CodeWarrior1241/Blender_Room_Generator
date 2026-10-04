"""SUN RGB-D (NYU Depth v2 frames) -> this project's ground-truth conventions.

SUN RGB-D frame (see SUNRGBDtoolbox/read3dPoints.m): an OpenCV camera point (x right,
y down, z forward) maps to (x, z, -y) and is then rotated by ``Rtilt`` (gravity alignment),
giving a world frame with x right, y forward, z up and the camera at the origin. That is
already this project's calibration frame up to a vertical shift: we lift everything by
the camera height so the floor is z = 0.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.io as sio
from PIL import Image

from room_gen import archetypes
from room_gen.geometry import PinholeCamera
from room_gen.meshgen import signed_area_2d

M_CV_TO_SUN = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
NYU_SIZE = (561, 427)  # SUN RGB-D crop of the 640 x 480 Kinect frame
# frames per scene type in the committed subset (scaled when another size is requested)
ALLOCATION = {"living_room": 10, "bedroom": 10, "dining_room": 6, "kitchen": 6, "home_office": 4, "office": 4}
SKIP_CLASSES = {"door", "window", "wall", "floor", "ceiling", "blinds", "curtain_rod"}


def load_meta(path: str | Path) -> list:
    return list(sio.loadmat(str(path), squeeze_me=True, struct_as_record=False)["SUNRGBDMeta"])


def frame_record(meta: list, index: int) -> dict:
    e = meta[index]
    seq = str(e.sequenceName).rstrip("/")
    return {"index": int(index), "id": seq.split("/")[-1], "sequence": seq, "rgbname": str(e.rgbname), "depthname": str(e.depthname)}


def _boxes(e) -> list:
    bb = getattr(e, "groundtruth3DBB", None)
    if bb is None or (isinstance(bb, np.ndarray) and bb.size == 0):
        return []
    return list(np.atleast_1d(bb))


def has_layout(e) -> bool:
    g = getattr(e, "gtCorner3D", None)
    return g is not None and np.size(g) >= 6


def _object(bb, cam_h: float, cam: PinholeCamera) -> dict | None:
    cls = str(bb.classname)
    if cls in SKIP_CLASSES:
        return None
    basis = np.atleast_2d(np.asarray(bb.basis, float))
    coeffs = np.abs(np.asarray(bb.coeffs, float)).ravel()
    centroid = np.asarray(bb.centroid, float).ravel()
    if basis.shape != (3, 3) or coeffs.size != 3:
        return None
    kv = int(np.argmax(np.abs(basis[:, 2])))
    hz = [k for k in range(3) if k != kv]
    orient = np.asarray(bb.orientation, float).ravel()[:2]
    if np.linalg.norm(orient) < 1e-6:
        orient = basis[hz[0], :2]
    f = orient / np.linalg.norm(orient)
    kd = max(hz, key=lambda k: abs(float(np.dot(basis[k, :2] / max(np.linalg.norm(basis[k, :2]), 1e-9), f))))
    kw = [k for k in hz if k != kd][0]
    w, d, h = 2 * coeffs[kw], 2 * coeffs[kd], 2 * coeffs[kv]
    arch, matched = archetypes.resolve(cls.replace("_", " "))
    pos = [float(centroid[0]), float(centroid[1]), float(centroid[2] - h / 2 + cam_h)]
    box2d = None
    g = getattr(bb, "gtBb2D", None)
    if g is not None and np.size(g) == 4:
        x, y, bw, bh = (float(v) for v in np.ravel(g))
        x0, y0 = max(0.0, x - 1), max(0.0, y - 1)
        x1, y1 = min(cam.width, x0 + bw), min(cam.height, y0 + bh)
        if x1 - x0 > 4 and y1 - y0 > 4:
            box2d = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
    return {"class": cls, "archetype": arch, "matched": bool(matched), "position": [round(v, 4) for v in pos],
            "size": [round(float(w), 4), round(float(d), 4), round(float(h), 4)],
            "yaw": round(math.degrees(math.atan2(f[0], -f[1])), 2), "box2d": box2d}


def truth_from_entry(e, size: tuple[int, int] = NYU_SIZE) -> dict | None:
    if not has_layout(e):
        return None
    corners = np.asarray(e.gtCorner3D, float)
    n = corners.shape[1] // 2
    floor, ceil = corners[:, :n], corners[:, n:]
    floor_z, ceil_z = float(floor[2].mean()), float(ceil[2].mean())
    cam_h = -floor_z
    poly = [(float(x), float(y)) for x, y in floor[:2].T]
    if signed_area_2d(poly) < 0:
        poly.reverse()
    K = np.asarray(e.K, float)
    R = (np.asarray(e.Rtilt, float) @ M_CV_TO_SUN).T  # world -> OpenCV camera
    cam = PinholeCamera(K[0, 0], K[1, 1], K[0, 2], K[1, 2], size[0], size[1], R, (0.0, 0.0, cam_h))
    objects = []
    for k, bb in enumerate(_boxes(e)):
        o = _object(bb, cam_h, cam)
        if o:
            o["id"] = f"{o['class'].replace('_', '-')}-{k}"
            objects.append(o)
    return {"camera": cam.to_dict(), "camera_height": round(cam_h, 4), "ceiling_height": round(ceil_z - floor_z, 4),
            "floor_polygon": [[round(x, 4), round(y, 4)] for x, y in poly], "objects": objects}


def visible_walls(truth: dict) -> list[int]:
    """Visible real walls (edges touching the camera vertex are view boundaries, see scoring.virtual_edges)."""
    from tests.eval.scoring import virtual_edges

    cam = PinholeCamera.from_dict(truth["camera"])
    poly = np.array(truth["floor_polygon"])
    h = truth["ceiling_height"]
    skip = virtual_edges(poly, cam)
    out = []
    for i in range(len(poly)):
        if i in skip:
            continue
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = b - a
        n_in = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
        if np.dot(cam.C[:2] - a, n_in) <= 0:
            continue
        t = np.linspace(0.05, 0.95, 15)
        pts = np.concatenate([np.column_stack([a[0] + t * d[0], a[1] + t * d[1], np.full(15, z)]) for z in (0.3, h / 2, h - 0.3)])
        uv, z = cam.project(pts)
        ok = (z > 0.2) & (uv[:, 0] >= 0) & (uv[:, 0] < cam.width) & (uv[:, 1] >= 0) & (uv[:, 1] < cam.height)
        if ok.mean() > 0.2:
            out.append(i)
    return out


def write_truth(e, dest: Path) -> dict | None:
    img = dest / "image.jpg"
    size = Image.open(img).size if img.is_file() else NYU_SIZE
    t = truth_from_entry(e, size)
    if t is None:
        return None
    scene_file = dest / "scene.txt"
    t.update({"source": "SUN RGB-D (NYU Depth v2)", "frame": str(e.sequenceName).rstrip("/").split("/")[-1],
              "sequence": str(e.sequenceName).rstrip("/"), "scene": scene_file.read_text().strip() if scene_file.is_file() else None,
              "visible_walls": visible_walls(t)})
    (dest / "truth.json").write_text(json.dumps(t, indent=2, sort_keys=True) + "\n")
    return t


def select_subset(meta: list, nyu, n: int, out: Path) -> None:
    """Pick ``n`` NYU frames with a layout, two visible walls and two recognised objects."""
    cands = []
    for i, e in enumerate(meta):
        if "NYUdata" not in str(e.sequenceName) or not has_layout(e):
            continue
        t = truth_from_entry(e)
        poly = np.array(t["floor_polygon"])
        area = abs(signed_area_2d([tuple(p) for p in poly]))
        if not (5.0 <= area <= 60.0 and 2.2 <= t["ceiling_height"] <= 3.6 and 0.6 <= t["camera_height"] <= 2.0):
            continue
        walls = visible_walls(t)
        cam = PinholeCamera.from_dict(t["camera"])
        objs = [o for o in t["objects"] if o["matched"] and o["box2d"]]
        if len(walls) < 2 or len(objs) < 2:
            continue
        cands.append((i, t, len(walls), len(objs)))
    print(f"candidates after geometry filters: {len(cands)}", flush=True)
    picked: dict[str, list] = {}
    for i, t, nw, no in cands:
        rec = frame_record(meta, i)
        scene = nyu.scene(int(rec["id"].replace("NYU", "")))
        if scene in ALLOCATION:
            picked.setdefault(scene, []).append({"index": i, "id": rec["id"], "scene": scene, "walls_visible": nw, "objects_matched": no})
    counts = {k: len(v) for k, v in sorted(picked.items())}
    print("eligible by scene:", counts, flush=True)
    total = sum(ALLOCATION.values())
    chosen = []
    for scene, want in ALLOCATION.items():
        pool = sorted(picked.get(scene, []), key=lambda r: r["index"])
        k = min(len(pool), max(1, round(want * n / total)))
        # evenly spaced through the pool: different sequences, not neighbouring frames
        chosen += [pool[int(j * len(pool) / k)] for j in range(k)] if k else []
    chosen.sort(key=lambda r: r["index"])
    out.write_text(json.dumps({
        "source": "SUN RGB-D, NYU Depth v2 frames (research use only; data in deps/sunrgbd, never committed)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "criteria": "room layout annotated; floor 5-60 m2; ceiling 2.2-3.6 m; camera 0.6-2.0 m; >= 2 visible walls; "
                    ">= 2 objects with a recognised archetype and a 2-D box; scene allocation " + json.dumps(ALLOCATION) +
                    "; frames evenly spaced within each scene type",
        "eligible_by_scene": counts,
        "frames": chosen,
    }, indent=2) + "\n")
    print(f"wrote {len(chosen)} frames to {out}", flush=True)


def annotations_from_truth(truth: dict, world_slug: str, image_rel: str) -> dict:
    """What a careful annotator would provide: boxes and labels of the recognised objects."""
    objs = []
    for o in truth["objects"]:
        if not (o["matched"] and o["box2d"]):
            continue
        objs.append({"id": o["id"], "label": o["class"].replace("_", " "), "archetype": o["archetype"], "box": o["box2d"],
                     "support": "floor", "provenance": {"by": "human", "tool": "sunrgbd-truth", "confidence": 1.0}})
    cam = truth["camera"]
    return {"world": world_slug, "image": image_rel, "image_size": [cam["width"], cam["height"]], "objects": objs,
            "provenance": {"by": "human", "tool": "sunrgbd-truth", "confidence": 1.0}}


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(np.clip(round(float(c)), 0, 255)) for c in rgb)


def twin_polygon(truth: dict) -> list:
    """Layout polygon for rendering: the camera-fan vertex is pushed 0.5 m behind the camera
    (only unseen geometry changes) and a self-crossing layout falls back to its convex hull."""
    cam = PinholeCamera.from_dict(truth["camera"])
    poly = np.array(truth["floor_polygon"], float)
    back = -cam.R[2, :2] / max(np.linalg.norm(cam.R[2, :2]), 1e-9)
    for i in range(len(poly)):
        if np.linalg.norm(poly[i] - cam.C[:2]) < 0.3:
            poly[i] = cam.C[:2] + 0.5 * back
    if not _is_simple(poly) or signed_area_2d([tuple(p) for p in poly]) <= 0:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(poly)
        poly = poly[hull.vertices]  # scipy returns CCW order in 2-D
    return [[round(float(x), 4), round(float(y), 4)] for x, y in poly]


def _is_simple(poly: np.ndarray) -> bool:
    n = len(poly)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
                return False
    return True


def photo_colours(truth: dict, rgb: np.ndarray, poly: list) -> tuple[dict, dict]:
    """Median photo colour of each layout surface (floor, ceiling, wall i) and of each object's
    2-D box, so the twin keeps the photo's colour cues."""
    from tests.eval.scoring import layout_labels, virtual_edges

    cam = PinholeCamera.from_dict(truth["camera"])
    p = np.array(truth["floor_polygon"], float)
    _, _, surf, uv = layout_labels(cam, p, truth["ceiling_height"], grid=(140, 105), skip_edges=virtual_edges(p, cam), surfaces=True)
    h, w = rgb.shape[:2]
    xi = np.clip(uv[:, 0].astype(int), 0, w - 1)
    yi = np.clip(uv[:, 1].astype(int), 0, h - 1)
    colours = rgb[yi, xi].astype(float)
    in_box = np.zeros(len(uv), bool)
    for o in truth["objects"]:
        if o["box2d"]:
            x0, y0, x1, y1 = o["box2d"]
            in_box |= (uv[:, 0] >= x0) & (uv[:, 0] <= x1) & (uv[:, 1] >= y0) & (uv[:, 1] <= y1)
    surfaces = {}
    for sid in np.unique(surf[surf >= 0]):
        sel = (surf == sid) & ~in_box
        if sel.sum() < 15:
            sel = surf == sid
        surfaces[int(sid)] = _hex(np.median(colours[sel], axis=0))
    objects = {}
    for o in truth["objects"]:
        if o["box2d"]:
            x0, y0, x1, y1 = (int(v) for v in o["box2d"])
            patch = rgb[max(0, y0) : max(y0 + 1, y1), max(0, x0) : max(x0 + 1, x1)].reshape(-1, 3)
            if len(patch):
                objects[o["id"]] = _hex(np.median(patch, axis=0))
    return surfaces, objects


def twin_scene(truth: dict, rgb: np.ndarray | None = None) -> tuple[dict, list[dict]]:
    """Room spec and objects of the ground truth for rendering a 'twin' of the photo. With the
    photo given, surfaces and objects take its median colours."""
    poly = twin_polygon(truth)
    surf, obj_col = photo_colours(truth, rgb, poly) if rgb is not None else ({}, {})
    walls, mats = [], {
        "floor_mat": {"base_color": surf.get(0, "#9a7350"), "roughness": 0.55, "procedural": "wood", "scale": 1.2},
        "ceiling_white": {"base_color": surf.get(1, "#f2f2f0"), "roughness": 0.95},
        "wall_paint": {"base_color": "#dedad2", "roughness": 0.9},
    }
    n_truth = len(truth["floor_polygon"])
    for i in range(len(poly)):
        name = "wall_paint"
        if len(poly) == n_truth and (2 + i) in surf:
            name = f"wall_{i}"
            mats[name] = {"base_color": surf[2 + i], "roughness": 0.9}
        walls.append({"edge": i, "material": name})
    room = {
        "schema_version": 1, "world": "twin",
        "shell": {"floor_polygon": poly, "ceiling_height": truth["ceiling_height"], "wall_thickness": 0.12, "walls": walls,
                  "floor": {"material": "floor_mat"}, "ceiling": {"material": "ceiling_white"}},
        "materials": mats,
        "lighting": {"sun": {"azimuth": 215, "elevation": 40, "strength": 2.0}, "sky": {"strength": 0.8, "color": "#d6dde6"}},
        "placements": [],
    }
    from room_gen import archetypes as A

    objects = []
    for o in truth["objects"]:
        arch = o["archetype"] if o["matched"] else archetypes.FALLBACK
        w, d, h = (max(v, 0.02) for v in o["size"])
        recipe = {"object": o["id"], "archetype": arch, "params": {"width": w, "depth": d, "height": h}}
        if o["id"] in obj_col:
            recipe["materials"] = {A.get(arch).slots[0]: {"base_color": obj_col[o["id"]]}}
        objects.append({"id": o["id"], "recipe": recipe, "placement": {"object": o["id"], "position": o["position"], "yaw": o["yaw"]}})
    return room, objects
