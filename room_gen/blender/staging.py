"""Lights, world background, cameras and object placement."""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Vector

from room_gen.blender.util import hex_rgba


def setup_world(scene, sky: dict) -> None:
    world = bpy.data.worlds.get("RoomWorld") or bpy.data.worlds.new("RoomWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = hex_rgba(sky.get("color", "#d0d8e4"))
    bg.inputs[1].default_value = float(sky.get("strength", 0.8))
    scene.world = world


def add_sun(sun: dict, coll) -> bpy.types.Object:
    data = bpy.data.lights.new("Sun", "SUN")
    data.energy = float(sun.get("strength", 3.0))
    data.color = hex_rgba(sun.get("color", "#fff1dc"))[:3]
    data.angle = math.radians(1.5)
    obj = bpy.data.objects.new("Sun", data)
    az, el = math.radians(sun.get("azimuth", 215.0)), math.radians(sun.get("elevation", 35.0))
    d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    coll.objects.link(obj)
    return obj


def add_fixture(fx: dict, coll, index: int) -> bpy.types.Object:
    kind = fx.get("kind", "area").upper()
    data = bpy.data.lights.new(f"Fixture_{index}", kind)
    data.energy = float(fx.get("power_w", 60.0))
    data.color = hex_rgba(fx.get("color", "#fff4e6"))[:3]
    if kind == "AREA":
        size = fx.get("size") or (0.5, 0.5)
        data.shape = "RECTANGLE"
        data.size, data.size_y = float(size[0]), float(size[1])
    obj = bpy.data.objects.new(f"Fixture_{index}", data)
    obj.location = tuple(fx["position"])
    coll.objects.link(obj)
    return obj


def add_fill_light(extent, coll) -> bpy.types.Object:
    """Soft ceiling panel so interiors read even without explicit fixtures."""
    x0, y0, x1, y1, h = extent
    area = max((x1 - x0) * (y1 - y0), 1.0)
    data = bpy.data.lights.new("CeilingFill", "AREA")
    data.shape = "RECTANGLE"
    data.size, data.size_y = (x1 - x0) * 0.6, (y1 - y0) * 0.6
    data.energy = min(max(28.0 * area, 200.0), 2500.0)
    data.color = (1.0, 0.96, 0.9)
    obj = bpy.data.objects.new("CeilingFill", data)
    obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, h - 0.02)
    coll.objects.link(obj)
    return obj


def add_camera(params: dict, coll, name: str = "PhotoCamera") -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.sensor_fit = "AUTO"
    data.sensor_width = float(params.get("sensor_mm", 36.0))
    data.lens = float(params["lens_mm"])
    data.shift_x = float(params.get("shift_x", 0.0))
    data.shift_y = float(params.get("shift_y", 0.0))
    data.clip_start, data.clip_end = 0.02, 200.0
    obj = bpy.data.objects.new(name, data)
    obj.matrix_world = Matrix(params["matrix_world"])
    coll.objects.link(obj)
    return obj


def look_at_camera(position, target, lens_mm: float, coll, name: str) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = lens_mm
    data.sensor_fit = "AUTO"
    data.sensor_width = 36.0
    data.clip_start, data.clip_end = 0.02, 200.0
    obj = bpy.data.objects.new(name, data)
    obj.location = Vector(position)
    direction = Vector(target) - Vector(position)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(obj)
    return obj


def plan_camera(extent, coll) -> bpy.types.Object:
    x0, y0, x1, y1, h = extent
    data = bpy.data.cameras.new("PlanCamera")
    data.type = "ORTHO"
    data.ortho_scale = max(x1 - x0, y1 - y0) * 1.15 + 0.5
    data.clip_start, data.clip_end = 0.05, h + 50
    obj = bpy.data.objects.new("PlanCamera", data)
    obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, h + 20.0)
    coll.objects.link(obj)
    return obj


def place(obj, placement: dict) -> None:
    obj.location = tuple(placement["position"])
    obj.rotation_euler = (0.0, 0.0, math.radians(float(placement.get("yaw", 0.0))))
    s = float(placement.get("scale", 1.0))
    obj.scale = (s, s, s)
