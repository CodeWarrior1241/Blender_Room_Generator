"""Exports (GLB/FBX/OBJ/USD) and partial .blend files."""

from __future__ import annotations

import os

import bpy

from room_gen.blender import shim


def select_only(objs) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        if o.name in bpy.context.view_layer.objects:
            o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def export(objs, path: str, fmt: str, *, cameras: bool = False) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    select_only(objs)
    try:
        if fmt == "glb":
            bpy.ops.export_scene.gltf(
                filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                export_yup=True, export_cameras=cameras, export_lights=False,
            )
        elif fmt == "fbx":
            types = {"MESH", "EMPTY"} | ({"CAMERA"} if cameras else set())
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types=types, use_mesh_modifiers=True,
                                     path_mode="COPY", embed_textures=True)
        elif fmt == "obj":
            kwargs = dict(filepath=path, export_selected_objects=True, apply_modifiers=True, export_materials=True)
            props = bpy.ops.wm.obj_export.get_rna_type().properties.keys()
            if "path_mode" in props:
                kwargs["path_mode"] = "COPY"
            bpy.ops.wm.obj_export(**kwargs)
        elif fmt == "usd":
            if not shim.has_operator("wm.usd_export"):
                return {"format": fmt, "path": path, "ok": False, "error": "USD export not available in this Blender build"}
            bpy.ops.wm.usd_export(filepath=path, selected_objects_only=True)
        else:
            return {"format": fmt, "path": path, "ok": False, "error": f"unknown format {fmt}"}
    except Exception as exc:  # noqa: BLE001 - report exporter failures, keep building
        return {"format": fmt, "path": path, "ok": False, "error": str(exc)}
    return {"format": fmt, "path": path, "ok": os.path.isfile(path)}


def pack_images() -> None:
    for img in bpy.data.images:
        if img.source == "FILE" and not img.packed_file and img.filepath:
            try:
                img.pack()
            except RuntimeError:
                pass


def write_partial_blend(path: str, name: str, collections=(), objects=(), world=None, camera=None) -> dict:
    """Write a .blend holding one scene with the given collections/objects."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene = bpy.data.scenes.new(name)
    for coll in collections:
        scene.collection.children.link(coll)
    for obj in objects:
        scene.collection.objects.link(obj)
    if world is not None:
        scene.world = world
    if camera is not None:
        scene.camera = camera
    pack_images()
    try:
        bpy.data.libraries.write(path, {scene}, fake_user=True, compress=True)
    finally:
        bpy.data.scenes.remove(scene)
    return {"format": "blend", "path": path, "ok": os.path.isfile(path)}
