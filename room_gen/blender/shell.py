"""Room shell: floor and ceiling slabs, mitred solid walls with openings, trim."""

from __future__ import annotations

import math

import bmesh

from room_gen import meshgen, shellgeom
from room_gen.blender.meshbuild import boolean_difference, finish_shading, mesh_object

CASING = 0.07


def _prism_object(name, polygon, z0, z1, material, collection):
    verts, faces = meshgen.prism(polygon, z1 - z0)
    verts = [(x, y, z + (z0 + z1) / 2) for x, y, z in verts]
    return mesh_object(name, [(verts, faces, 0, None)], [material], collection=collection)


def _local_box(frame, s_center, v_center, z_center, size_s, size_v, size_z):
    verts, faces = meshgen.box(size_s, size_v, size_z)
    yaw = frame["yaw_deg"]
    # box local x along u, y along v_in (u rotated +90 deg about Z)
    cx, cy, cz = shellgeom.local_to_world(frame, s_center, v_center, z_center)
    return meshgen.transform(verts, (cx, cy, cz), (0, 0, yaw)), faces


def _set_photo_uvs(obj, mapper) -> None:
    """Replace UVs with ``mapper(co, normal) -> (u, v) | None`` (None keeps the box UVs)."""
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        for loop in f.loops:
            res = mapper(loop.vert.co, f.normal)
            if res is not None:
                loop[uv].uv = res
    finish_shading(bm, mesh)
    bm.to_mesh(mesh)
    bm.free()


def build_shell(room: dict, mats: dict, coll) -> dict:
    shell = room["shell"]
    poly = [tuple(p) for p in shell["floor_polygon"]]
    t = float(shell.get("wall_thickness", 0.12))
    h = float(shell["ceiling_height"])
    frames = shellgeom.wall_frames(poly)
    outer = shellgeom.offset_polygon(poly, t)
    inner_box = shellgeom.bbox(poly)
    walls = {w["edge"]: w for w in shell.get("walls", [])}
    made = {"walls": [], "floor": None, "ceiling": None, "trim": [], "openings": [], "backdrops": []}

    def mat(name, fallback):
        return mats.get(name) or mats[fallback]

    floor_mat = mat(shell.get("floor", {}).get("material", "floor"), "floor")
    ceil_mat = mat(shell.get("ceiling", {}).get("material", "ceiling"), "ceiling")
    floor = _prism_object("Floor", outer, -t, 0.0, floor_mat, coll)
    ceiling = _prism_object("Ceiling", outer, h, h + t, ceil_mat, coll)
    for obj, top in ((floor, True), (ceiling, False)):
        m = obj.data.materials[0]
        if m.get("room_gen_photo"):
            target_n = 1.0 if top else -1.0
            _set_photo_uvs(obj, lambda co, n, tn=target_n: shellgeom.floor_uv(co.x, co.y, inner_box) if n.z * tn > 0.9 else None)
    floor["room_gen_kind"] = "floor"
    ceiling["room_gen_kind"] = "ceiling"
    made["floor"], made["ceiling"] = floor, ceiling

    for fr in frames:
        i = fr["edge"]
        wall_spec = walls.get(i, {"edge": i})
        wmat = mat(wall_spec.get("material", "wall_paint"), "wall_paint")
        quad = [fr["start"], fr["end"], outer[(i + 1) % len(poly)], outer[i]]
        wall = _prism_object(f"Wall_{i:02d}", quad, 0.0, h, wmat, coll)
        wall["room_gen_kind"] = "wall"
        wall["room_gen_edge"] = i
        openings = wall_spec.get("openings", [])
        cutters = []
        for k, op in enumerate(openings):
            s_c = op["offset"] + op["width"] / 2
            z_c = op.get("sill", 0.0) + op["height"] / 2
            verts, faces = _local_box(fr, s_c, -t / 2, z_c, op["width"], t + 0.2, op["height"])
            cutters.append(mesh_object(f"Cut_{i:02d}_{k}", [(verts, faces, 0, None)], [wmat], collection=coll))
        boolean_difference(wall, cutters)
        L = fr["length"]
        if wmat.get("room_gen_photo"):
            _set_photo_uvs(wall, lambda co, n, fr=fr, L=L: (
                shellgeom.wall_uv(shellgeom.world_to_local(fr, co.x, co.y, co.z)[0], co.z, L, h)
                if (n.x * fr["v_in"][0] + n.y * fr["v_in"][1]) > 0.9 else None))
        made["walls"].append(wall)

        # trim: baseboards between floor-level openings
        trim = shell.get("trim", {})
        bh, bd = float(trim.get("baseboard_height", 0.1)), float(trim.get("baseboard_depth", 0.015))
        blocked = [(op["offset"], op["offset"] + op["width"]) for op in openings if op.get("sill", 0.0) < 0.05]
        pieces = []
        if bh > 0 and bd > 0:
            for a, b in shellgeom.free_intervals(L, blocked):
                pieces.append((*_local_box(fr, (a + b) / 2, bd / 2, bh / 2, b - a, bd, bh), 0, None))
        if trim.get("crown"):
            pieces.append((*_local_box(fr, L / 2, 0.03, h - 0.04, L, 0.06, 0.08), 0, None))

        # opening dressing: casings, glass, sill, door leaf
        op_pieces = []
        glass_pieces = []
        door_pieces = []
        for op in openings:
            s0, s1 = op["offset"], op["offset"] + op["width"]
            z0, z1 = op.get("sill", 0.0), op.get("sill", 0.0) + op["height"]
            jamb_h = z1 - z0 + CASING + (CASING if z0 > 0.05 else 0.0)
            jamb_z = (z0 - (CASING if z0 > 0.05 else 0.0) + z1 + CASING) / 2
            if s0 - CASING >= 0:
                op_pieces.append((*_local_box(fr, s0 - CASING / 2, 0.01, jamb_z, CASING, 0.02, jamb_h), 0, None))
            if s1 + CASING <= L:
                op_pieces.append((*_local_box(fr, s1 + CASING / 2, 0.01, jamb_z, CASING, 0.02, jamb_h), 0, None))
            if z1 + CASING <= h:
                op_pieces.append((*_local_box(fr, (s0 + s1) / 2, 0.01, z1 + CASING / 2, s1 - s0 + 2 * CASING, 0.02, CASING), 0, None))
            if op["kind"] == "window":
                op_pieces.append((*_local_box(fr, (s0 + s1) / 2, 0.02, z0 - 0.015, s1 - s0 + 0.1, 0.04 + t * 0.5, 0.03), 0, None))
                if op.get("glazing", True) is not False:
                    glass_pieces.append((*_local_box(fr, (s0 + s1) / 2, -t / 2, (z0 + z1) / 2, s1 - s0, 0.01, z1 - z0), 0, None))
                # exterior backdrop plane, facing into the room
                vb = -t - 1.5
                c = [shellgeom.local_to_world(fr, s, vb, z) for s, z in ((s1 + 1.5, z0 - 1.5), (s0 - 1.5, z0 - 1.5), (s0 - 1.5, z1 + 1.5), (s1 + 1.5, z1 + 1.5))]
                bd_obj = mesh_object(f"Backdrop_{i:02d}", [(c, [(0, 1, 2, 3)], 0, None)], [mat("exterior", "wall_paint")], collection=coll)
                made["backdrops"].append(bd_obj)
            elif op["kind"] == "door":
                door_pieces.append((*_local_box(fr, (s0 + s1) / 2, -0.04, (z0 + z1 - 0.01) / 2, s1 - s0 - 0.01, 0.04, z1 - z0 - 0.01), 0, None))
                hs = s1 - 0.08
                door_pieces.append((*_local_box(fr, hs, -0.005, z0 + 1.0, 0.12, 0.03, 0.02), 0, None))
        if pieces:
            trim_obj = mesh_object(f"Trim_{i:02d}", pieces, [mat("trim", "wall_paint")], collection=coll)
            trim_obj["room_gen_kind"] = "trim"
            made["trim"].append(trim_obj)
        if op_pieces:
            o = mesh_object(f"Casing_{i:02d}", op_pieces, [mat("frame", "wall_paint")], collection=coll)
            made["openings"].append(o)
        if glass_pieces:
            o = mesh_object(f"Glass_{i:02d}", glass_pieces, [mat("glass", "wall_paint")], collection=coll)
            made["openings"].append(o)
        if door_pieces:
            o = mesh_object(f"Door_{i:02d}", door_pieces, [mat("door", "wall_paint")], collection=coll)
            made["openings"].append(o)
    return made


def shell_extent(room: dict) -> tuple[float, float, float, float, float]:
    x0, y0, x1, y1 = shellgeom.bbox([tuple(p) for p in room["shell"]["floor_polygon"]])
    return x0, y0, x1, y1, float(room["shell"]["ceiling_height"])


def look_from_corner(room: dict) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Fallback preview camera: from a front corner, looking at the far corner."""
    x0, y0, x1, y1, h = shell_extent(room)
    pos = (x0 + 0.35, y0 + 0.35, min(1.6, h - 0.3))
    tgt = (x1 - 0.2, y1 - 0.2, h * 0.35)
    return pos, tgt


def yaw_rad(deg: float) -> float:
    return math.radians(deg)
