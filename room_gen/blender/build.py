"""Execute a build job prepared by the host (``room_gen.build``).

The job is fully resolved: absolute paths, expanded recipes, final placements, Blender
camera parameters. This module only builds, renders and exports.
"""

from __future__ import annotations

import os
import time

import bpy
from mathutils import Matrix

from room_gen.blender import exporters, preview, shim
from room_gen.blender.materials import make_material, make_palette
from room_gen.blender.meshbuild import build_recipe_object, face_count, object_dimensions
from room_gen.blender.shell import build_shell, look_from_corner, shell_extent
from room_gen.blender.staging import add_camera, add_fill_light, add_fixture, add_sun, look_at_camera, place, plan_camera, setup_world
from room_gen.blender.util import ensure_collection, log, reset_scene

INTERNAL_MATERIALS = {
    "wall_paint": {"base_color": "#e6e2da", "roughness": 0.9},
    "floor": {"base_color": "#a37a52", "roughness": 0.55},
    "ceiling": {"base_color": "#f3f2ef", "roughness": 0.95},
    "trim": {"base_color": "#f4f3f0", "roughness": 0.45},
    "frame": {"base_color": "#f2f1ee", "roughness": 0.45},
    "door": {"base_color": "#ece9e2", "roughness": 0.5},
    "glass": {"base_color": "#dfe9ee", "roughness": 0.05, "transmission": 0.9, "alpha": 0.25},
    "exterior": {"base_color": "#cfdbe8", "roughness": 1.0, "emission": "#dfe8f2", "emission_strength": 1.2},
}


def _build_scene(job: dict) -> dict:
    scene = reset_scene()
    room = job["room"]
    colls = {name: ensure_collection(name) for name in ("Shell", "Fixed", "Objects", "Lights", "Cameras", "Backdrop")}
    palette = {**INTERNAL_MATERIALS, **job.get("materials", {})}
    mats = {name: make_material(name, spec) for name, spec in palette.items()}
    shell = build_shell(room, mats, colls["Shell"])
    for bd in shell["backdrops"]:
        colls["Shell"].objects.unlink(bd)
        colls["Backdrop"].objects.link(bd)
    objects: dict[str, bpy.types.Object] = {}
    reports = []
    for kind, items in (("fixed", job.get("fixed", [])), ("object", job.get("objects", []))):
        for item in items:
            oid = item["id"]
            palette_o = make_palette(f"{oid}:", item["recipe"].get("materials", {}))
            coll = colls["Fixed"] if kind == "fixed" else colls["Objects"]
            obj = build_recipe_object(oid, item["recipe"], palette_o, coll)
            obj["room_gen_id"] = oid
            dims = object_dimensions(obj)
            report = {"id": oid, "kind": kind, "faces": face_count(obj), "dimensions": [round(d, 4) for d in dims], "warnings": []}
            expected = item["recipe"].get("bbox_m")
            if expected:
                err = max(abs(d - e) / max(e, 1e-6) for d, e in zip(dims, expected))
                if err > 0.10:
                    report["warnings"].append(f"built size {dims} differs from bbox_m {expected} by {err:.0%}")
            if item.get("placement"):
                place(obj, item["placement"])
            else:
                obj.hide_render = True
                obj["room_gen_unplaced"] = True
            objects[oid] = obj
            reports.append(report)
    lighting = room.get("lighting", {})
    setup_world(scene, lighting.get("sky", {}))
    if lighting.get("sun"):
        add_sun(lighting["sun"], colls["Lights"])
    for i, fx in enumerate(lighting.get("fixtures", [])):
        add_fixture(fx, colls["Lights"], i)
    extent = shell_extent(room)
    if not lighting.get("fixtures"):
        add_fill_light(extent, colls["Lights"])
    shim.set_view_transform(scene, float(lighting.get("exposure", 0.0)))
    if job.get("camera"):
        cam = add_camera(job["camera"], colls["Cameras"])
    else:
        pos, tgt = look_from_corner(room)
        cam = look_at_camera(pos, tgt, 18.0, colls["Cameras"], "PhotoCamera")
    scene.camera = cam
    return {"scene": scene, "colls": colls, "shell": shell, "objects": objects, "reports": reports, "camera": cam, "extent": extent}


def _shell_objects(ctx) -> list:
    return [o for o in ctx["colls"]["Shell"].all_objects] + [o for o in ctx["colls"]["Fixed"].all_objects]


def _preview_size(job: dict) -> tuple[int, int]:
    cam = job.get("camera") or {}
    w0, h0 = cam.get("resolution", (16, 9))
    width = int(job.get("render", {}).get("width", 960))
    return width, max(1, int(round(width * h0 / w0)))


def _labels(ctx) -> list:
    made = []
    mat = bpy.data.materials.new("LabelInk")
    mat.diffuse_color = (0.05, 0.05, 0.06, 1.0)
    for oid, obj in ctx["objects"].items():
        if obj.get("room_gen_unplaced"):
            continue
        curve = bpy.data.curves.new(f"Label_{oid}", "FONT")
        curve.body = oid
        curve.size = 0.16
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.materials.append(mat)
        text = bpy.data.objects.new(f"Label_{oid}", curve)
        text.location = (obj.location.x, obj.location.y, ctx["extent"][4] + 0.5)
        ctx["scene"].collection.objects.link(text)
        made.append(text)
    return made


def run_build(job: dict) -> dict:
    t0 = time.time()
    ctx = _build_scene(job)
    scene, colls, objects = ctx["scene"], ctx["colls"], ctx["objects"]
    outputs = []
    render_cfg = job.get("render", {})
    samples = int(render_cfg.get("samples", 32))
    formats = job.get("formats", ["glb"])

    # ---- per-object files (object space, bottom-centre origin) --------------------
    for item in job.get("objects", []) + job.get("fixed", []):
        out = item.get("outputs") or {}
        if not out:
            continue
        obj = objects[item["id"]]
        saved = obj.matrix_world.copy()
        obj.matrix_world = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for fmt in formats:
            if out.get(fmt):
                outputs.append({"id": item["id"], **exporters.export([obj], out[fmt], fmt)})
        if out.get("blend"):
            dup = obj.copy()
            outputs.append({"id": item["id"], **exporters.write_partial_blend(out["blend"], f"object_{item['id']}", objects=[dup])})
            bpy.data.objects.remove(dup, do_unlink=True)
        obj.matrix_world = saved
        bpy.context.view_layer.update()
        if out.get("preview") and render_cfg.get("object_previews", True):
            outputs.append({"id": item["id"], **preview.object_studio_render(obj, out["preview"], int(render_cfg.get("object_preview_size", 384)), samples=16)})

    # ---- world: shell + fixed features ---------------------------------------------
    wout = job.get("outputs", {}).get("world", {})
    shell_objs = _shell_objects(ctx)
    for fmt in formats:
        if wout.get(fmt):
            outputs.append({"id": "world", **exporters.export(shell_objs, wout[fmt], fmt)})
    width, height = _preview_size(job)
    if wout.get("preview"):
        colls["Objects"].hide_render = True
        outputs.append({"id": "world", **preview.render(scene, ctx["camera"], wout["preview"], width, height, samples=samples)})
        colls["Objects"].hide_render = False
    if wout.get("blend"):
        outputs.append({"id": "world", **exporters.write_partial_blend(
            wout["blend"], "World", collections=[colls["Shell"], colls["Fixed"], colls["Lights"], colls["Cameras"], colls["Backdrop"]],
            world=scene.world, camera=ctx["camera"])})

    # ---- furnished room ----------------------------------------------------------------
    rout = job.get("outputs", {}).get("room", {})
    placed = [o for o in objects.values() if not o.get("room_gen_unplaced")]
    if rout.get("preview"):
        outputs.append({"id": "room", **preview.render(scene, ctx["camera"], rout["preview"], width, height, samples=samples)})
    if rout.get("plan"):
        cam = plan_camera(ctx["extent"], colls["Cameras"])
        labels = _labels(ctx)
        hidden = [o for o in colls["Shell"].all_objects if o.get("room_gen_kind") == "ceiling"]
        for o in hidden:
            o.hide_render = True
        colls["Backdrop"].hide_render = True
        outputs.append({"id": "room", **preview.render(scene, cam, rout["plan"], 900, 900, engine="workbench")})
        for o in hidden:
            o.hide_render = False
        colls["Backdrop"].hide_render = False
        for t in labels:
            curve = t.data
            bpy.data.objects.remove(t, do_unlink=True)
            bpy.data.curves.remove(curve)
        bpy.data.objects.remove(cam, do_unlink=True)
        scene.camera = ctx["camera"]
    if rout.get("thumbnail_stem") and rout.get("preview"):
        thumb = preview.thumbnail(rout["preview"], rout["thumbnail_stem"], webp=shim.capabilities()["webp"])
        if thumb:
            outputs.append({"id": "room", "format": "thumbnail", "path": thumb, "ok": True})
    for fmt in formats:
        if rout.get(fmt):
            outputs.append({"id": "room", **exporters.export(shell_objs + placed + [ctx["camera"]], rout[fmt], fmt, cameras=True)})
    if rout.get("blend"):
        for s in list(bpy.data.scenes):
            if s != scene:
                bpy.data.scenes.remove(s)
        exporters.pack_images()
        os.makedirs(os.path.dirname(rout["blend"]), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=rout["blend"], compress=True)
        outputs.append({"id": "room", "format": "blend", "path": rout["blend"], "ok": os.path.isfile(rout["blend"])})
    log(f"build finished in {time.time() - t0:.1f}s")
    return {"outputs": outputs, "objects": ctx["reports"], "seconds": round(time.time() - t0, 2), "capabilities": shim.capabilities()}


def run_render(job: dict) -> dict:
    """Render a room spec from the job camera (used for synthetic benchmark photos)."""
    ctx = _build_scene(job)
    out = job["output"]
    cam = job.get("camera") or {}
    w, h = cam.get("resolution", (1280, 960))
    engine = job.get("engine", "eevee")
    if job.get("hide_ceiling_lights", False):
        pass
    res = preview.render(ctx["scene"], ctx["camera"], out, int(w), int(h), engine=engine, samples=int(job.get("samples", 64)))
    return {"outputs": [res], "objects": ctx["reports"]}
