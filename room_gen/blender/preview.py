"""Preview renders: photo-camera view, top-down plan, object studio shots, thumbnails."""

from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

from room_gen.blender import shim
from room_gen.blender.staging import look_at_camera


def render(scene, camera, path: str, width: int, height: int, *, engine: str = "eevee", samples: int = 32) -> dict:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scene.camera = camera
    if engine == "workbench":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
    elif engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
    else:
        shim.configure_eevee(scene, samples)
    scene.render.resolution_x, scene.render.resolution_y = int(width), int(height)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=scene.name)
    return {"path": path, "ok": os.path.isfile(path)}


def thumbnail(src: str, dst_stem: str, width: int = 320, webp: bool = True) -> str | None:
    if not os.path.isfile(src):
        return None
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    img.scale(width, max(1, int(round(h * width / max(w, 1)))))
    scene = bpy.context.scene
    fmt = "WEBP" if webp else "PNG"
    ext = ".webp" if webp else ".png"
    settings = scene.render.image_settings
    old = settings.file_format
    settings.file_format = fmt
    path = dst_stem + ext
    img.save_render(path, scene=scene)
    settings.file_format = old
    bpy.data.images.remove(img)
    return path


def object_studio_render(obj, path: str, size: int, samples: int = 24) -> dict:
    """Three-quarter view of one object in a neutral studio scene."""
    studio = bpy.data.scenes.new("Studio")
    try:
        dup = obj.copy()
        dup.matrix_world = obj.matrix_basis.copy()
        dup.location = (0, 0, 0)
        dup.rotation_euler = (0, 0, 0)
        dup.scale = (1, 1, 1)
        studio.collection.objects.link(dup)
        world = bpy.data.worlds.new("StudioWorld")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.82, 1)
        world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
        studio.world = world
        dims = [max(d, 0.02) for d in dup.dimensions]
        radius = 0.5 * math.sqrt(sum(d * d for d in dims))
        center = Vector((0, 0, dims[2] / 2))
        lens = 50.0
        fov = 2 * math.atan(18.0 / lens)
        dist = radius / math.sin(fov / 2) * 1.05
        direction = Vector((0.55, -0.85, 0.45)).normalized()
        cam = look_at_camera(center + direction * dist, center, lens, studio.collection, "StudioCam")
        key = bpy.data.lights.new("Key", "SUN")
        key.energy = 3.0
        key_obj = bpy.data.objects.new("Key", key)
        key_obj.rotation_euler = Vector((0.4, -0.6, 0.7)).to_track_quat("Z", "Y").to_euler()
        studio.collection.objects.link(key_obj)
        floor_mesh = bpy.data.meshes.new("StudioFloor")
        s = radius * 6
        floor_mesh.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        floor = bpy.data.objects.new("StudioFloor", floor_mesh)
        fm = bpy.data.materials.new("StudioFloorMat")
        fm.diffuse_color = (0.75, 0.75, 0.77, 1)
        fm.use_nodes = True
        fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.6, 0.62, 1)
        floor_mesh.materials.append(fm)
        studio.collection.objects.link(floor)
        shim.set_view_transform(studio)
        return render(studio, cam, path, size, size, samples=samples)
    finally:
        for o in list(studio.collection.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.scenes.remove(studio)
