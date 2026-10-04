"""Blender version differences in one place (4.0 legacy EEVEE ... 4.2+ EEVEE Next)."""

from __future__ import annotations

import bpy

VERSION = bpy.app.version


def eevee_engine_id() -> str:
    items = {i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in items:
            return candidate
    return "BLENDER_WORKBENCH"


def set_input(node, names, value) -> bool:
    for name in names if isinstance(names, (list, tuple)) else [names]:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return True
    return False


def input_socket(node, names):
    for name in names if isinstance(names, (list, tuple)) else [names]:
        sock = node.inputs.get(name)
        if sock is not None:
            return sock
    return None


TRANSMISSION = ["Transmission Weight", "Transmission"]
EMISSION = ["Emission Color", "Emission"]


def configure_eevee(scene, samples: int = 32) -> None:
    scene.render.engine = eevee_engine_id()
    ee = scene.eevee
    for attr, value in (
        ("taa_render_samples", samples),
        ("use_gtao", True),
        ("gtao_distance", 0.6),
        ("use_soft_shadows", True),
        ("shadow_cube_size", "1024"),
        ("shadow_cascade_size", "2048"),
        ("use_ssr", True),
        ("use_bloom", False),
    ):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, value)
            except (TypeError, ValueError):
                pass


def set_view_transform(scene, exposure: float = 0.0) -> str:
    for name in ("AgX", "Filmic", "Standard"):
        try:
            scene.view_settings.view_transform = name
            break
        except TypeError:
            continue
    scene.view_settings.exposure = exposure
    return scene.view_settings.view_transform


def material_blend_alpha(mat, alpha: float) -> None:
    if alpha >= 0.999:
        return
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "HASHED"
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"


def has_operator(path: str) -> bool:
    mod, name = path.split(".")
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False


def capabilities() -> dict:
    caps = {
        "blender_version": bpy.app.version_string,
        "python": __import__("sys").version.split()[0],
        "eevee": eevee_engine_id(),
        "gltf": has_operator("export_scene.gltf"),
        "fbx": has_operator("export_scene.fbx"),
        "obj": has_operator("wm.obj_export"),
        "usd": has_operator("wm.usd_export"),
    }
    try:
        import numpy

        caps["numpy"] = numpy.__version__
    except ImportError:
        caps["numpy"] = None
    fmts = {i.identifier for i in bpy.types.ImageFormatSettings.bl_rna.properties["file_format"].enum_items}
    caps["webp"] = "WEBP" in fmts
    return caps
