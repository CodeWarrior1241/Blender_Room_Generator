"""Turn recipe parts (room_gen.meshgen geometry) into Blender mesh objects."""

from __future__ import annotations

import math

import bmesh
import bpy

from room_gen import meshgen

SHARP_ANGLE = math.radians(30.0)


def _add_piece(bm, verts, faces, mat_index: int):
    bverts = [bm.verts.new(v) for v in verts]
    new_faces = []
    for face in faces:
        try:
            f = bm.faces.new([bverts[i] for i in face])
        except ValueError:  # duplicate or degenerate face
            continue
        f.material_index = mat_index
        new_faces.append(f)
    return bverts, new_faces


def box_project_uvs(bm, scales: list[float]) -> None:
    """World-scale box projection: one UV unit per material tile size (metres)."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda k: abs(n[k]))
        a, b = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[ax]
        s = scales[f.material_index] if f.material_index < len(scales) else 1.0
        s = s if s > 1e-6 else 1.0
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co[a] / s, co[b] / s)


def finish_shading(bm, mesh) -> None:
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if e.is_manifold:
            e.smooth = e.calc_face_angle(0.0) < SHARP_ANGLE
        else:
            e.smooth = False
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = SHARP_ANGLE


def mesh_object(name: str, pieces, materials: list, *, uv_scales: list[float] | None = None, collection=None):
    """pieces: iterable of (verts, faces, material_index, bevel_dict_or_None)."""
    bm = bmesh.new()
    for verts, faces, mat_index, bevel in pieces:
        bverts, new_faces = _add_piece(bm, verts, faces, mat_index)
        if bevel and new_faces:
            for f in new_faces:
                f.normal_update()
            edges = {e for f in new_faces for e in f.edges}
            sharp = [e for e in edges if e.is_manifold and e.calc_face_angle(0.0) > SHARP_ANGLE]
            if sharp:
                bmesh.ops.bevel(
                    bm,
                    geom=sharp,
                    offset=float(bevel["width"]),
                    segments=int(bevel.get("segments", 2)),
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    box_project_uvs(bm, uv_scales or [m.get("room_gen_scale", 1.0) for m in materials])
    mesh = bpy.data.meshes.new(name)
    finish_shading(bm, mesh)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    if collection is not None:
        collection.objects.link(obj)
    return obj


def apply_modifiers(obj) -> None:
    """Bake the object's modifier stack into its mesh without operators."""
    if not obj.modifiers:
        return
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    new_mesh = bpy.data.meshes.new_from_object(evaluated)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_mesh
    new_mesh.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def boolean_difference(obj, cutters: list) -> None:
    """Subtract cutter objects (already linked to a scene) from ``obj`` and delete them."""
    if not cutters:
        return
    for cutter in cutters:
        mod = obj.modifiers.new(f"cut_{cutter.name}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
    apply_modifiers(obj)
    for cutter in cutters:
        mesh = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def build_recipe_object(name: str, recipe: dict, materials: dict, collection) -> bpy.types.Object:
    """Build one object from an expanded recipe. ``materials`` maps slot -> bpy material."""
    slots = list(materials)
    mats = [materials[s] for s in slots]
    cutter_ids: set[str] = set()
    subdivide = 0
    for mod in recipe.get("modifiers", []):
        if isinstance(mod, dict):
            cutter_ids |= set(mod.get("boolean_difference", []))
            subdivide = max(subdivide, int(mod.get("subdivide", 0) or 0))
    pieces, cutter_pieces = [], []
    for part in recipe.get("parts", []):
        idx = slots.index(part["material"]) if part["material"] in slots else 0
        for verts, faces in meshgen.part_instances(part):
            target = cutter_pieces if part["id"] in cutter_ids else pieces
            target.append((verts, faces, idx, part.get("bevel")))
    obj = mesh_object(name, pieces, mats, collection=collection)
    if cutter_pieces:
        cutter = mesh_object(f"{name}__cutter", [(v, f, 0, None) for v, f, _, _ in cutter_pieces], mats[:1], collection=collection)
        boolean_difference(obj, [cutter])
    if subdivide:
        mod = obj.modifiers.new("subdivide", "SUBSURF")
        mod.levels = mod.render_levels = min(subdivide, 2)
    obj["room_gen_kind"] = "object"
    obj["room_gen_archetype"] = recipe.get("archetype") or ""
    return obj


def object_dimensions(obj) -> list[float]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    xs = [v.co.x for v in ev.data.vertices] or [0.0]
    ys = [v.co.y for v in ev.data.vertices] or [0.0]
    zs = [v.co.z for v in ev.data.vertices] or [0.0]
    return [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]


def face_count(obj) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return len(obj.evaluated_get(depsgraph).data.polygons)
