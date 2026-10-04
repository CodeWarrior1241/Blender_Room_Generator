"""Re-import an exported file and report what it contains (used by tests and `room_gen inspect`)."""

from __future__ import annotations

import os

import bpy
from mathutils import Vector

from room_gen.blender.util import reset_scene


def run_inspect(job: dict) -> dict:
    reset_scene()
    path = job["path"]
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        raise ValueError(f"cannot inspect {ext}")
    bpy.context.view_layer.update()
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    objects = []
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for o in meshes:
        olo = Vector((float("inf"),) * 3)
        ohi = Vector((float("-inf"),) * 3)
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            for i in range(3):
                olo[i], ohi[i] = min(olo[i], w[i]), max(ohi[i], w[i])
        for i in range(3):
            lo[i], hi[i] = min(lo[i], olo[i]), max(hi[i], ohi[i])
        objects.append({"name": o.name, "faces": len(o.data.polygons), "materials": [m.name for m in o.data.materials if m],
                        "min": list(olo), "max": list(ohi)})
    return {"path": path, "mesh_count": len(meshes), "objects": objects,
            "cameras": [o.name for o in bpy.context.scene.objects if o.type == "CAMERA"],
            "bounds": {"min": list(lo), "max": list(hi)} if meshes else None}
