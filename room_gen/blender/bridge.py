"""Import an image-blaster world into Blender, reproducing its viewer transforms.

Viewer facts (deps/image-blaster/app): the collider GLB is rotated by pi about X when
``flip_y`` (default true), lifted by ``groundPlaneOffset`` and scaled by
``metricScaleFactor``; each object GLB is re-centred to its bottom centre, scaled by 0.5
(OBJECT_SCALE) and then placed with the instance's Three.js position/rotation/scale.
"""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix, Vector

from room_gen.blender import exporters, preview, shim
from room_gen.blender.staging import look_at_camera
from room_gen.blender.util import ensure_collection, log, reset_scene

OBJECT_SCALE = 0.5
THREE_TO_BLENDER = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def _import_glb(path: str, coll) -> list:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    return new


def _bounds(objs) -> tuple[Vector, Vector]:
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    bpy.context.view_layer.update()
    for o in objs:
        if o.type != "MESH":
            continue
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
    if lo.x == math.inf:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    return lo, hi


def _roots(objs) -> list:
    return [o for o in objs if o.parent is None or o.parent not in objs]


def _three_matrix(position, rotation, scale) -> Matrix:
    t = Matrix.Translation(Vector(position))
    # Three.js Euler 'XYZ' is Rx @ Ry @ Rz (Blender's 'XYZ' is Rz @ Ry @ Rx), so build it explicitly
    rx, ry, rz = (Matrix.Rotation(a, 4, ax) for a, ax in zip(rotation, "XYZ"))
    s = Matrix.Diagonal((*scale, 1.0))
    return t @ (rx @ ry @ rz) @ s


def run_bridge(job: dict) -> dict:
    scene = reset_scene()
    world_coll = ensure_collection("ImageBlasterWorld")
    obj_coll = ensure_collection("ImageBlasterObjects")
    light_coll = ensure_collection("Lights")
    report = {"world": None, "instances": [], "warnings": []}
    scene_json = job.get("scene") or {}
    sem = job.get("semantics") or {}
    flip = sem.get("flip_y", True)
    scale = scene_json.get("metricScaleFactor", sem.get("metric_scale_factor", 1.0)) or 1.0
    offset = scene_json.get("groundPlaneOffset", sem.get("ground_plane_offset", 0.0)) or 0.0
    if job.get("collider"):
        objs = _import_glb(job["collider"], world_coll)
        # viewer transform in Three space -> Blender space (conjugate by the axis change)
        m_three = Matrix.Translation((0, offset, 0)) @ Matrix.Rotation(math.pi if flip else 0.0, 4, "X") @ Matrix.Scale(scale, 4)
        m = THREE_TO_BLENDER @ m_three @ THREE_TO_BLENDER.inverted()
        for root in _roots(objs):
            root.matrix_world = m @ root.matrix_world
        report["world"] = {"path": job["collider"], "objects": len(objs), "flip_y": flip, "scale": scale, "offset": offset}
    assets = job.get("assets", {})
    imported: dict[str, list] = {}
    for inst in scene_json.get("instances", []):
        key = inst.get("assetId") or inst.get("objectId")
        path = assets.get(key) or assets.get(inst.get("objectId"))
        if not path:
            report["warnings"].append(f"no model file for instance {inst.get('instanceId')} ({key})")
            continue
        holder = bpy.data.objects.new(f"inst_{inst.get('instanceId')}", None)
        obj_coll.objects.link(holder)
        if key not in imported:
            objs = _import_glb(path, obj_coll)
            lo, hi = _bounds(objs)
            centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
            fix = Matrix.Scale(OBJECT_SCALE, 4) @ Matrix.Translation(-centre)
            for root in _roots(objs):
                root.matrix_world = fix @ root.matrix_world
            imported[key] = objs
            sources = _roots(objs)
        else:
            sources = []
            for o in _roots(imported[key]):
                dup = o.copy()
                obj_coll.objects.link(dup)
                sources.append(dup)
        m_three = _three_matrix(inst["position"], inst["rotation"], inst["scale"])
        holder.matrix_world = THREE_TO_BLENDER @ m_three @ THREE_TO_BLENDER.inverted()
        for o in sources:
            local = o.matrix_world.copy()
            o.parent = holder
            o.matrix_parent_inverse = Matrix.Identity(4)
            o.matrix_basis = local
        bpy.context.view_layer.update()
        ilo, ihi = _bounds([c for c in holder.children_recursive])
        report["instances"].append({"instance": inst.get("instanceId"), "object": inst.get("objectId"), "path": path,
                                    "min": list(ilo), "max": list(ihi)})
    sun = scene_json.get("sun")
    if sun:
        x, y, z = 0.0, 10.0, 0.0
        rx, ry, rz = sun.get("rotation", (0, 0, 0))
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        d = Vector((x, -z, y)).normalized()
        data = bpy.data.lights.new("Sun", "SUN")
        data.energy = 2.5 * float(sun.get("intensity", 1.0))
        lamp = bpy.data.objects.new("Sun", data)
        lamp.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        light_coll.objects.link(lamp)
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = world
    outputs = []
    meshes = [o for o in scene.objects if o.type == "MESH"]
    lo, hi = _bounds(meshes)
    centre = (lo + hi) / 2
    span = max((hi - lo).length, 1.0)
    cam = look_at_camera(centre + Vector((0.6, -1.0, 0.55)).normalized() * span * 0.9, centre, 24.0, scene.collection, "OverviewCamera")
    scene.camera = cam
    shim.set_view_transform(scene)
    out = job.get("outputs", {})
    for fmt in job.get("formats", ["glb"]):
        if out.get(fmt):
            outputs.append(exporters.export(meshes, out[fmt], fmt))
    if out.get("preview"):
        outputs.append(preview.render(scene, cam, out["preview"], 960, 540, samples=16))
    if out.get("blend"):
        exporters.pack_images()
        bpy.ops.wm.save_as_mainfile(filepath=out["blend"], compress=True)
        outputs.append({"format": "blend", "path": out["blend"], "ok": os.path.isfile(out["blend"])})
    log("bridge done")
    report["outputs"] = outputs
    report["bounds"] = {"min": list(lo), "max": list(hi)}
    return report
