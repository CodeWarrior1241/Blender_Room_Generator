"""Small helpers for the Blender side: result protocol, colours, collections."""

from __future__ import annotations

import json
import sys

import bpy

RESULT_PREFIX = "ROOM_GEN_RESULT "


def emit(result: dict) -> None:
    sys.stdout.write("\n" + RESULT_PREFIX + json.dumps(result, default=str) + "\n")
    sys.stdout.flush()


def log(*parts) -> None:
    print("[room_gen]", *parts, file=sys.stderr, flush=True)


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(value: str | None, alpha: float = 1.0, linear: bool = True) -> tuple[float, float, float, float]:
    value = (value or "#cccccc").lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    if linear:
        r, g, b = srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)
    return (r, g, b, alpha)


def ensure_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if coll.name not in parent.children:
        parent.children.link(coll)
    return coll


def link(obj: bpy.types.Object, coll: bpy.types.Collection) -> bpy.types.Object:
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    return obj


def all_objects(coll: bpy.types.Collection) -> list[bpy.types.Object]:
    return list(coll.all_objects)


def reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Room"
    scene.unit_settings.system = "METRIC"
    return scene
