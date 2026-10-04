"""Pure-Python mesh generation for the recipe DSL primitives.

Shared by the host (bounding boxes, face counts, tests) and Blender (actual meshes), so
it must not import numpy or bpy. Every primitive is centred on its local origin except
``lathe``, whose profile carries explicit z values. Faces are wound counter-clockwise
seen from outside.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Vec3 = tuple[float, float, float]
Face = tuple[int, ...]
Mesh = tuple[list[Vec3], list[Face]]


def box(sx: float, sy: float, sz: float) -> Mesh:
    x, y, z = sx / 2, sy / 2, sz / 2
    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5)]
    return verts, faces


def plane(sx: float, sy: float) -> Mesh:
    x, y = sx / 2, sy / 2
    return [(-x, -y, 0.0), (x, -y, 0.0), (x, y, 0.0), (-x, y, 0.0)], [(0, 1, 2, 3)]


def _ring(radius: float, z: float, n: int) -> list[Vec3]:
    return [(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def cone(r1: float, r2: float, height: float, n: int = 24) -> Mesh:
    """Frustum from radius r1 at z=-h/2 to r2 at z=+h/2; either radius may be 0."""
    h = height / 2
    verts: list[Vec3] = []
    faces: list[Face] = []
    if r1 > 0:
        bottom = list(range(len(verts), len(verts) + n))
        verts += _ring(r1, -h, n)
    else:
        bottom = [len(verts)] * n
        verts.append((0.0, 0.0, -h))
    if r2 > 0:
        top = list(range(len(verts), len(verts) + n))
        verts += _ring(r2, h, n)
    else:
        top = [len(verts)] * n
        verts.append((0.0, 0.0, h))
    for i in range(n):
        j = (i + 1) % n
        quad = [bottom[i], bottom[j], top[j], top[i]]
        dedup = [v for k, v in enumerate(quad) if v not in quad[:k]]
        if len(dedup) >= 3:
            faces.append(tuple(dedup))
    if r1 > 0:
        faces.append(tuple(reversed(bottom)))
    if r2 > 0:
        faces.append(tuple(top))
    return verts, faces


def cylinder(radius: float, height: float, n: int = 24) -> Mesh:
    return cone(radius, radius, height, n)


def sphere(radius: float, n: int = 24) -> Mesh:
    rings = max(4, n // 2)
    verts: list[Vec3] = [(0.0, 0.0, -radius)]
    for k in range(1, rings):
        phi = -math.pi / 2 + math.pi * k / rings
        verts += _ring(radius * math.cos(phi), radius * math.sin(phi), n)
    verts.append((0.0, 0.0, radius))
    top = len(verts) - 1
    faces: list[Face] = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((0, 1 + j, 1 + i))
    for k in range(rings - 2):
        a, b = 1 + k * n, 1 + (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a + i, a + j, b + j, b + i))
    last = 1 + (rings - 2) * n
    for i in range(n):
        j = (i + 1) % n
        faces.append((last + i, last + j, top))
    return verts, faces


def torus(major: float, minor: float, n: int = 24) -> Mesh:
    m = max(8, n // 2)
    verts = []
    for i in range(n):
        u = 2 * math.pi * i / n
        for j in range(m):
            v = 2 * math.pi * j / m
            r = major + minor * math.cos(v)
            verts.append((r * math.cos(u), r * math.sin(u), minor * math.sin(v)))
    faces = []
    for i in range(n):
        for j in range(m):
            a = i * m + j
            b = ((i + 1) % n) * m + j
            c = ((i + 1) % n) * m + (j + 1) % m
            d = i * m + (j + 1) % m
            faces.append((a, b, c, d))
    return verts, faces


def tube(outer: float, inner: float, height: float, n: int = 24) -> Mesh:
    h = height / 2
    verts = _ring(outer, -h, n) + _ring(outer, h, n) + _ring(inner, -h, n) + _ring(inner, h, n)
    ob, ot, ib, it = 0, n, 2 * n, 3 * n
    faces: list[Face] = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((ob + i, ob + j, ot + j, ot + i))
        faces.append((ib + j, ib + i, it + i, it + j))
        faces.append((ot + i, ot + j, it + j, it + i))
        faces.append((ob + j, ob + i, ib + i, ib + j))
    return verts, faces


def signed_area_2d(poly: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))


def prism(polygon: Sequence[tuple[float, float]], height: float) -> Mesh:
    poly = list(polygon)
    if signed_area_2d(poly) < 0:
        poly.reverse()
    n, h = len(poly), height / 2
    verts = [(x, y, -h) for x, y in poly] + [(x, y, h) for x, y in poly]
    faces: list[Face] = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    return verts, faces


def lathe(profile: Sequence[tuple[float, float]], n: int = 24) -> Mesh:
    """Revolve (r, z) profile points around local Z; r == 0 points become poles."""
    verts: list[Vec3] = []
    rings: list[list[int]] = []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([len(verts)] * n)
            verts.append((0.0, 0.0, z))
        else:
            rings.append(list(range(len(verts), len(verts) + n)))
            verts += _ring(r, z, n)
    faces: list[Face] = []
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            quad = [a[i], a[j], b[j], b[i]]
            dedup = [v for k, v in enumerate(quad) if v not in quad[:k]]
            if len(dedup) >= 3:
                faces.append(tuple(dedup))
    if profile[0][0] > 1e-9:
        faces.append(tuple(reversed(rings[0])))
    if profile[-1][0] > 1e-9:
        faces.append(tuple(rings[-1]))
    return orient_outward(verts, faces)


def signed_volume(verts: Sequence[Vec3], faces: Iterable[Face]) -> float:
    vol = 0.0
    for f in faces:
        a = verts[f[0]]
        for k in range(1, len(f) - 1):
            b, c = verts[f[k]], verts[f[k + 1]]
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return vol


def orient_outward(verts: list[Vec3], faces: list[Face]) -> Mesh:
    if signed_volume(verts, faces) < 0:
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces


# ----- transforms -------------------------------------------------------------------------


def euler_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> list[list[float]]:
    """Blender 'XYZ' Euler: R = Rz @ Ry @ Rx."""
    ax, ay, az = (math.radians(a) for a in (rx_deg, ry_deg, rz_deg))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]


def transform(verts: Sequence[Vec3], position=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1)) -> list[Vec3]:
    m = euler_matrix(*rotation)
    out = []
    for x, y, z in verts:
        x, y, z = x * scale[0], y * scale[1], z * scale[2]
        out.append(
            (
                m[0][0] * x + m[0][1] * y + m[0][2] * z + position[0],
                m[1][0] * x + m[1][1] * y + m[1][2] * z + position[1],
                m[2][0] * x + m[2][1] * y + m[2][2] * z + position[2],
            )
        )
    return out


def primitive_mesh(part: dict) -> Mesh:
    p = part["primitive"]
    n = int(part.get("segments", 24))
    if p == "box":
        return box(*part["size"])
    if p == "plane":
        return plane(part["size"][0], part["size"][1])
    if p == "cylinder":
        return cylinder(part["radius"], part["height"], n)
    if p == "cone":
        return cone(part["radius"], part.get("radius2") or 0.0, part["height"], n)
    if p == "sphere":
        return sphere(part["radius"], n)
    if p == "torus":
        return torus(part["radius"], part["radius2"], n)
    if p == "tube":
        return tube(part["radius"], part["radius2"], part["height"], n)
    if p == "prism":
        return prism([tuple(q) for q in part["polygon"]], part["height"])
    if p == "lathe":
        return lathe([tuple(q) for q in part["profile"]], n)
    raise ValueError(f"unknown primitive {p!r}")


def part_instances(part: dict) -> list[Mesh]:
    """All copies of a part (array then mirror), transformed into object space."""
    verts, faces = primitive_mesh(part)
    base = transform(verts, part.get("position", (0, 0, 0)), part.get("rotation", (0, 0, 0)), part.get("scale", (1, 1, 1)))
    copies: list[list[Vec3]] = []
    arr = part.get("array")
    count = int(arr["count"]) if arr else 1
    off = arr["offset"] if arr else (0, 0, 0)
    for k in range(count):
        copies.append([(x + k * off[0], y + k * off[1], z + k * off[2]) for x, y, z in base])
    out: list[Mesh] = [(c, list(faces)) for c in copies]
    mirror = part.get("mirror")
    if mirror:
        flips = {"x": [(-1, 1)], "y": [(1, -1)], "xy": [(-1, 1), (1, -1), (-1, -1)]}[mirror]
        mirrored: list[Mesh] = []
        for fx, fy in flips:
            for c in copies:
                v = [(x * fx, y * fy, z) for x, y, z in c]
                f = list(faces) if fx * fy > 0 else [tuple(reversed(face)) for face in faces]
                mirrored.append((v, f))
        out += mirrored
    return out


def recipe_meshes(recipe: dict) -> list[tuple[dict, Mesh]]:
    """(part, mesh) for every non-cutter part instance of an expanded recipe."""
    cutters = set()
    for mod in recipe.get("modifiers", []):
        if isinstance(mod, dict):
            cutters |= set(mod.get("boolean_difference", []))
    result = []
    for part in recipe.get("parts", []):
        if part["id"] in cutters:
            continue
        for mesh in part_instances(part):
            result.append((part, mesh))
    return result


def recipe_bbox(recipe: dict) -> tuple[Vec3, Vec3]:
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for _, (verts, _) in recipe_meshes(recipe):
        for v in verts:
            for k in range(3):
                lo[k] = min(lo[k], v[k])
                hi[k] = max(hi[k], v[k])
    if lo[0] == math.inf:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return tuple(lo), tuple(hi)  # type: ignore[return-value]


def recipe_face_count(recipe: dict) -> int:
    faces = sum(len(f) for _, (_, f) in recipe_meshes(recipe))
    for mod in recipe.get("modifiers", []):
        if isinstance(mod, dict) and mod.get("subdivide"):
            faces *= 4 ** int(mod["subdivide"])
    return faces
