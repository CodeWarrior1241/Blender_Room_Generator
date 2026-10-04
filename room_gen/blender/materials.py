"""Principled-BSDF materials from the room/recipe material contract (glTF-safe)."""

from __future__ import annotations

import os

import bpy

from room_gen.blender import shim
from room_gen.blender.util import hex_rgba


def _image(path: str):
    path = os.path.abspath(path)
    for img in bpy.data.images:
        if img.filepath and os.path.abspath(bpy.path.abspath(img.filepath)) == path:
            return img
    return bpy.data.images.load(path, check_existing=True)


def make_material(name: str, spec: dict) -> bpy.types.Material:
    """Create (or reuse) a material. ``spec`` may carry ``texture_abs`` (tiling texture)
    or ``image_abs`` (photo texture for one surface); both feed Base Color."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    alpha = float(spec.get("alpha", 1.0))
    bsdf.inputs["Base Color"].default_value = hex_rgba(spec.get("base_color"))
    bsdf.inputs["Roughness"].default_value = float(spec.get("roughness", 0.6))
    bsdf.inputs["Metallic"].default_value = float(spec.get("metallic", 0.0))
    shim.set_input(bsdf, "Alpha", alpha)
    shim.set_input(bsdf, shim.TRANSMISSION, float(spec.get("transmission", 0.0)))
    if spec.get("emission") and float(spec.get("emission_strength", 0.0)) > 0:
        shim.set_input(bsdf, shim.EMISSION, hex_rgba(spec["emission"]))
        shim.set_input(bsdf, "Emission Strength", float(spec["emission_strength"]))
    tex_path = spec.get("image_abs") or spec.get("texture_abs")
    if tex_path and os.path.isfile(tex_path):
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = _image(tex_path)
        tex.extension = "EXTEND" if spec.get("image_abs") else "REPEAT"
        tex.location = (-400, 250)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    shim.material_blend_alpha(mat, alpha)
    mat.diffuse_color = hex_rgba(spec.get("base_color"), alpha)
    mat["room_gen_scale"] = float(spec.get("scale", 1.0))
    mat["room_gen_photo"] = bool(spec.get("image_abs"))
    return mat


def make_palette(prefix: str, specs: dict) -> dict[str, bpy.types.Material]:
    return {slot: make_material(f"{prefix}{slot}", spec) for slot, spec in specs.items()}
