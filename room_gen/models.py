"""Data contracts (CLAUDE.md §7) as pydantic models.

Every JSON file the pipeline consumes is validated against these models; ``schemas/`` is
generated from them with ``room_gen schemas``. Units are metres and degrees; pixel
coordinates are ``[u, v]`` in the source image's native resolution, origin top-left.
"""

from __future__ import annotations

import math
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]
Line2 = tuple[Vec2, Vec2]
Box2 = tuple[float, float, float, float]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
Positive = Annotated[float, Field(gt=0.0)]
NonNeg = Annotated[float, Field(ge=0.0)]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Provenance(Strict):
    by: Literal["auto", "human", "model", "fit"] = "auto"
    tool: str = ""
    confidence: Unit = 0.5


# --------------------------------------------------------------------------------------
# annotations.json — pixel-space facts written by tools, people, or Claude
# --------------------------------------------------------------------------------------


class ParallelPair(Strict):
    axis: Literal["x", "y", "z"]
    lines: list[Line2] = Field(min_length=2)


class Reference(Strict):
    """A vertical segment standing on the floor (bottom pixel first) of known length."""

    kind: Literal["vertical"] = "vertical"
    pixels: Line2
    metres: Positive
    label: str = ""


class ExifInfo(Strict):
    focal_mm: float | None = None
    focal_35mm: float | None = None
    make: str | None = None
    model: str | None = None
    orientation: int | None = None


class CalibrationHints(Strict):
    parallel_pairs: list[ParallelPair] = Field(default_factory=list)
    vertical_lines: list[Line2] = Field(default_factory=list)
    principal_point: Vec2 | None = None
    focal_px: Positive | None = None
    reference: Reference | None = None
    camera_height_m: Positive | None = None
    exif: ExifInfo | None = None


class OpeningAnnotation(Strict):
    kind: Literal["door", "window", "opening"]
    quad: list[Vec2] = Field(min_length=4, max_length=4)
    wall_hint: Literal["left", "right", "back", "front", "0", "1", "2", "3"] | None = None  # box-room edge names or indices
    label: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class ObjectAnnotation(Strict):
    id: Slug
    label: str
    box: Box2
    support: str = "floor"
    archetype: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    materials_hint: list[str] = Field(default_factory=list)
    mask: str | None = None
    score: float | None = None
    provenance: Provenance = Field(default_factory=Provenance)

    @field_validator("box")
    @classmethod
    def _box_order(cls, box: Box2) -> Box2:
        x0, y0, x1, y1 = box
        if x1 <= x0 or y1 <= y0:
            raise ValueError("box must be [x0, y0, x1, y1] with x1 > x0 and y1 > y0")
        return box


class BoundaryLine(Strict):
    """A traced stretch of a room boundary: wall/floor, wall/ceiling, or a vertical wall/wall corner.

    Use when a corner's foot is hidden but the boundary itself is visible.
    """

    kind: Literal["wall_floor", "wall_ceiling", "wall_wall"]
    pixels: list[Vec2] = Field(min_length=2)
    provenance: Provenance = Field(default_factory=Provenance)


class KnownLength(Strict):
    """Two pixels on the floor plane a known distance apart."""

    pixels: Line2
    metres: Positive
    label: str = ""


class Annotations(Strict):
    schema_version: Literal[1] = 1
    world: str
    image: str
    image_size: tuple[int, int]
    calibration: CalibrationHints = Field(default_factory=CalibrationHints)
    floor_corners: list[Vec2] = Field(default_factory=list)
    boundary_lines: list[BoundaryLine] = Field(default_factory=list)
    ceiling_height_m: Positive | None = None
    openings: list[OpeningAnnotation] = Field(default_factory=list)
    objects: list[ObjectAnnotation] = Field(default_factory=list)
    known_lengths: list[KnownLength] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def _unique_ids(self) -> "Annotations":
        ids = [o.id for o in self.objects]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate object ids: {sorted(dupes)}")
        return self


# --------------------------------------------------------------------------------------
# calibration.json
# --------------------------------------------------------------------------------------


class VanishingPoint(Strict):
    axis: Literal["x", "y", "z"]
    point: Vec3  # homogeneous image coordinates
    direction_cam: Vec3
    inliers: int = 0
    support_px: float = 0.0


class Calibration(Strict):
    schema_version: Literal[1] = 1
    world: str
    image: str
    image_size: tuple[int, int]
    fx: Positive
    fy: Positive
    cx: float
    cy: float
    R: Mat3  # world -> camera (OpenCV camera axes)
    camera_position: Vec3  # world frame with the origin on the floor below the camera
    camera_height_m: Positive
    vanishing_points: list[VanishingPoint] = Field(default_factory=list)
    method: Literal["auto-vp", "manual-vp", "manual-vp+auto-refine", "prior"] = "auto-vp"
    focal_source: str = ""
    scale_source: str = ""
    residual_deg: float = 0.0
    hfov_deg: float = 0.0
    notes: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)

    def camera_dict(self) -> dict:
        w, h = self.image_size
        return {
            "fx": self.fx,
            "fy": self.fy,
            "cx": self.cx,
            "cy": self.cy,
            "width": w,
            "height": h,
            "R": [list(r) for r in self.R],
            "position": list(self.camera_position),
        }


# --------------------------------------------------------------------------------------
# room.json
# --------------------------------------------------------------------------------------


class Material(Strict):
    base_color: HexColor = "#cccccc"
    roughness: Unit = 0.6
    metallic: Unit = 0.0
    emission: HexColor | None = None
    emission_strength: NonNeg = 0.0
    alpha: Unit = 1.0
    transmission: Unit = 0.0
    procedural: Literal["wood", "tile", "fabric", "noise", "brick"] | None = None
    scale: Positive = 1.0  # metres per texture tile for procedural materials
    image: str | None = None  # world-relative path of a photo texture covering one surface


class Opening(Strict):
    kind: Literal["door", "window", "opening"]
    offset: NonNeg  # along the wall from its start vertex, metres
    width: Positive
    height: Positive
    sill: NonNeg = 0.0
    glazing: bool | None = None
    frame_depth: NonNeg = 0.05
    label: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class Wall(Strict):
    edge: Annotated[int, Field(ge=0)]
    material: str = "wall_paint"
    openings: list[Opening] = Field(default_factory=list)


class Surface(Strict):
    material: str


class Trim(Strict):
    baseboard_height: NonNeg = 0.1
    baseboard_depth: NonNeg = 0.015
    crown: bool = False


class Shell(Strict):
    floor_polygon: list[Vec2] = Field(min_length=3)
    ceiling_height: Positive
    wall_thickness: Positive = 0.12
    origin: Literal["floor_centroid"] = "floor_centroid"
    walls: list[Wall] = Field(default_factory=list)
    floor: Surface = Field(default_factory=lambda: Surface(material="floor"))
    ceiling: Surface = Field(default_factory=lambda: Surface(material="ceiling"))
    trim: Trim = Field(default_factory=Trim)
    visible_edges: list[int] = Field(default_factory=list)
    guessed_edges: list[int] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def _check(self) -> "Shell":
        poly = self.floor_polygon
        area = 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
        if area <= 0:
            raise ValueError("floor_polygon must be counter-clockwise with positive area")
        n = len(poly)
        for wall in self.walls:
            if wall.edge >= n:
                raise ValueError(f"wall edge {wall.edge} does not exist (polygon has {n} edges)")
            a, b = poly[wall.edge], poly[(wall.edge + 1) % n]
            length = math.dist(a, b)
            for op in wall.openings:
                if op.offset + op.width > length + 1e-6:
                    raise ValueError(f"opening on edge {wall.edge} extends past the wall end ({op.offset}+{op.width} > {length:.3f})")
                if op.sill + op.height > self.ceiling_height + 1e-6:
                    raise ValueError(f"opening on edge {wall.edge} is taller than the ceiling")
        return self

    def wall_for_edge(self, edge: int) -> Wall:
        for wall in self.walls:
            if wall.edge == edge:
                return wall
        return Wall(edge=edge)


class Sun(Strict):
    azimuth: float = 215.0  # degrees, clockwise from +Y (room "north")
    elevation: float = 35.0
    strength: NonNeg = 3.0
    color: HexColor = "#fff1dc"


class Sky(Strict):
    strength: NonNeg = 0.8
    color: HexColor = "#d0d8e4"


class Fixture(Strict):
    kind: Literal["area", "point", "spot"] = "area"
    position: Vec3
    size: Vec2 | None = None
    power_w: NonNeg = 60.0
    color: HexColor = "#fff4e6"


class Lighting(Strict):
    sun: Sun | None = Field(default_factory=Sun)
    sky: Sky = Field(default_factory=Sky)
    fixtures: list[Fixture] = Field(default_factory=list)
    exposure: float = 0.0
    provenance: Provenance = Field(default_factory=Provenance)


class CameraSpec(Strict):
    """The estimated camera of the source photo, in the room frame."""

    position: Vec3
    R: Mat3  # world -> camera (OpenCV axes)
    fx: Positive
    fy: Positive
    cx: float
    cy: float
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    provenance: Provenance = Field(default_factory=Provenance)


class Placement(Strict):
    object: Slug
    position: Vec3  # bottom centre of the object, room frame
    yaw: float = 0.0  # degrees about +Z; 0 means the object's front faces -Y
    scale: Positive = 1.0
    support: str = "floor"
    size_m: Vec3 | None = None
    recipe: str | None = None  # world-relative path; default output/<object>/recipe.json
    provenance: Provenance = Field(default_factory=Provenance)


class FixedFeature(Strict):
    id: Slug
    recipe: str
    position: Vec3
    yaw: float = 0.0


class Scale(Strict):
    reference: str = "assumed camera height"
    confidence: Unit = 0.3


class Room(Strict):
    schema_version: Literal[1] = 1
    world: str
    source_images: list[str] = Field(default_factory=list)
    calibration: str | None = None
    scale: Scale = Field(default_factory=Scale)
    shell: Shell
    fixed_features: list[FixedFeature] = Field(default_factory=list)
    materials: dict[str, Material] = Field(default_factory=dict)
    lighting: Lighting = Field(default_factory=Lighting)
    camera: CameraSpec | None = None
    placements: list[Placement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    updated_at: str | None = None

    @model_validator(mode="after")
    def _materials_exist(self) -> "Room":
        used = {self.shell.floor.material, self.shell.ceiling.material}
        used |= {w.material for w in self.shell.walls}
        missing = sorted(m for m in used if m not in self.materials)
        if missing:
            raise ValueError(f"materials used by the shell are not defined: {missing}")
        return self


# --------------------------------------------------------------------------------------
# recipe.json — object recipe DSL
# --------------------------------------------------------------------------------------

PRIMITIVES = ("box", "cylinder", "cone", "sphere", "torus", "plane", "prism", "lathe", "tube")
MAX_PARTS = 64
MAX_FACES = 50_000


class ArraySpec(Strict):
    count: Annotated[int, Field(ge=1, le=64)]
    offset: Vec3


class BevelSpec(Strict):
    width: Positive
    segments: Annotated[int, Field(ge=1, le=8)] = 2


class Part(Strict):
    id: str
    primitive: Literal["box", "cylinder", "cone", "sphere", "torus", "plane", "prism", "lathe", "tube"]
    size: Vec3 | None = None
    radius: Positive | None = None
    radius2: NonNeg | None = None
    height: Positive | None = None
    segments: Annotated[int, Field(ge=3, le=128)] = 24
    polygon: list[Vec2] | None = None
    profile: list[Vec2] | None = None  # (r, z) pairs for lathe
    position: Vec3 = (0.0, 0.0, 0.0)
    rotation: Vec3 = (0.0, 0.0, 0.0)  # degrees, Blender XYZ Euler
    scale: Vec3 = (1.0, 1.0, 1.0)
    material: str
    mirror: Literal["x", "y", "xy"] | None = None
    array: ArraySpec | None = None
    bevel: BevelSpec | None = None

    @model_validator(mode="after")
    def _required_fields(self) -> "Part":
        need: dict[str, tuple[str, ...]] = {
            "box": ("size",),
            "plane": ("size",),
            "cylinder": ("radius", "height"),
            "cone": ("radius", "height"),
            "sphere": ("radius",),
            "torus": ("radius", "radius2"),
            "tube": ("radius", "radius2", "height"),
            "prism": ("polygon", "height"),
            "lathe": ("profile",),
        }
        missing = [f for f in need[self.primitive] if getattr(self, f) is None]
        if missing:
            raise ValueError(f"part {self.id!r} ({self.primitive}) needs {missing}")
        if self.primitive == "tube" and self.radius2 is not None and self.radius is not None and self.radius2 >= self.radius:
            raise ValueError(f"part {self.id!r}: tube radius2 (inner) must be smaller than radius")
        if self.primitive == "prism" and len(self.polygon or []) < 3:
            raise ValueError(f"part {self.id!r}: prism polygon needs at least 3 points")
        if self.primitive == "lathe" and len(self.profile or []) < 2:
            raise ValueError(f"part {self.id!r}: lathe profile needs at least 2 points")
        if self.size is not None and min(self.size[:2] if self.primitive == "plane" else self.size) <= 0:
            raise ValueError(f"part {self.id!r}: size components must be positive")
        return self


class Recipe(Strict):
    schema_version: Literal[1] = 1
    world: str = ""
    object: str
    archetype: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    materials: dict[str, Material] = Field(default_factory=dict)
    bbox_m: Vec3 | None = None
    origin: Literal["bottom_center", "center"] = "bottom_center"
    collision: Literal["box", "convex", "mesh"] = "box"
    parts: list[Part] = Field(default_factory=list)
    modifiers: list[str | dict[str, Any]] = Field(default_factory=list)
    script: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)
    notes: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Recipe":
        if not self.parts and not self.script and not self.archetype:
            raise ValueError("recipe needs parts, an archetype to expand, or a script")
        if len(self.parts) > MAX_PARTS:
            raise ValueError(f"recipe has {len(self.parts)} parts; the limit is {MAX_PARTS}")
        ids = [p.id for p in self.parts]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate part ids: {sorted(dupes)}")
        missing = sorted({p.material for p in self.parts} - set(self.materials))
        if missing:
            raise ValueError(f"parts use undefined materials: {missing}")
        for mod in self.modifiers:
            if isinstance(mod, str):
                if mod != "join":
                    raise ValueError(f"unknown modifier {mod!r}")
                continue
            unknown = set(mod) - {"subdivide", "smooth", "boolean_difference", "shade_smooth_angle"}
            if unknown:
                raise ValueError(f"unknown modifier keys {sorted(unknown)}")
            for pid in mod.get("boolean_difference", []):
                if pid not in ids:
                    raise ValueError(f"boolean_difference references unknown part {pid!r}")
        return self


# --------------------------------------------------------------------------------------
# image-blaster contracts (mirrored, permissive)
# --------------------------------------------------------------------------------------


class ImageObject(Loose):
    id: str
    name: str
    description: str = ""
    count_estimate: int | None = None
    materials: list[str] = Field(default_factory=list)
    source_images: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    generate_as_3d_object: bool = True


class ImageAnalysis(Loose):
    schema_version: int = 1
    world: str
    source_images: list[str] = Field(default_factory=list)
    scene_name: str = ""
    short_caption: str = ""
    literal_description: str = ""
    environment: str = ""
    visual_style: str = ""
    lighting: str = ""
    atmosphere: str = ""
    ambient_sound: str = ""
    objects: list[ImageObject] = Field(default_factory=list)


class ObjectIdentity(Loose):
    id: str
    name: str
    description: str = ""
    materials: list[str] = Field(default_factory=list)
    source_images: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    generate_as_3d_object: bool = True
    working_dir: str = ""


class ObjectFile(Loose):
    schema_version: int = 1
    world: str
    object: ObjectIdentity
    updated_at: str | None = None


class ScenePlacement(Loose):
    instanceId: str
    objectId: str
    assetId: str | None = None
    physics: Literal["rigidbody", "static", "ghost"] | None = None
    position: Vec3
    rotation: Vec3
    scale: Vec3


class SceneSun(Loose):
    intensity: float
    rotation: Vec3
    environmentIntensity: float | None = None


class SceneProject(Loose):
    version: Literal[1] = 1
    instances: list[ScenePlacement] = Field(default_factory=list)
    sun: SceneSun | None = None
    metricScaleFactor: float | None = None
    groundPlaneOffset: float | None = None
    groundPlaneColliderEnabled: bool | None = None
    shadowCatcherOpacity: float | None = None
    shadowCatcherColor: str | None = None


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "annotations": Annotations,
    "calibration": Calibration,
    "room": Room,
    "recipe": Recipe,
    "image": ImageAnalysis,
    "object": ObjectFile,
    "scene": SceneProject,
}
