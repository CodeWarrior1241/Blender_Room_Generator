# Blender Room Generator — build specification

This file is the specification for this repository and the standing instructions for any
Claude session working here. The plan in §1–§16 is implemented (see §17 for status,
measured quality and known limits); sections marked **Spec** describe the design as built.
**Rules** (§15) apply to every change.

## 0. One sentence

Blender_Room_Generator turns a photo of a room into an editable, exportable Blender scene
using deterministic Python and Blender tools, with Claude as an optional helper, so that no
paid 3D-generation API is needed.

## 1. Purpose

Extend [image-blaster](https://github.com/neilsonnn/image-blaster) (vendored read-only at
`deps/image-blaster`) in three directions, in this priority order:

1. **Export to Blender.** Any image-blaster world (`worlds/<slug>/`) becomes a `.blend`
   file plus Blender-side re-exports (GLB, FBX, OBJ): environment mesh, every object model,
   and the viewer's `scene.json` placements, converted into Blender's coordinate system.
2. **A model-free toolchain.** Calibration, layout, placement, materials, lighting and
   textures are computed by classical computer vision and geometry (OpenCV, scipy, numpy
   on the host; bpy inside Blender) from the photo and, where the photo is ambiguous, from a
   handful of human clicks in a small local web annotator. When installed, small local
   open-weight vision models (metric depth, open-vocabulary detection, segmentation) sharpen
   the same steps (§8.12). This path needs no language model and, once model weights are
   cached, no network. It is the backbone of the project and gets the most engineering
   effort.
3. **Claude as optional autofill.** Where image-blaster calls World Labs, FAL/Hunyuan,
   Meshy, nano-banana and ElevenLabs, this project lets Claude (inside Claude Code under a
   Claude Pro or Max subscription, no API key) fill in the *same JSON* a person would
   produce in the annotator: object labels and 2-D boxes, archetype choices, material
   names, a literal scene description. Claude never computes a metre; the tools do. Cheap
   models (Haiku, Sonnet) are the default for this layer.

Design principle that follows from 2 and 3: **every JSON file the pipeline consumes can be
produced by a deterministic tool, by a person, or by Claude, and the build cannot tell
which.** Claude is a convenience over the tools, never a requirement of them.

## 2. Hard constraints and preferences

- **No external inference, no API keys.** No World Labs, FAL, Meshy, ElevenLabs, OpenAI,
  Google, and no Anthropic API key either. The only language model ever involved is Claude
  inside Claude Code under the user's subscription, and the whole pipeline must run with it
  absent. There is no `--model` flag anywhere: Python cannot call Claude under a
  subscription.
- **Direction of control is Claude → tools, never tools → Claude.** Skills call
  `room_gen ...`; no code imports an Anthropic SDK or shells out to `claude`.
- **Languages and libraries.** Python is preferred for business logic (the user knows it
  well) and is the default for everything in `room_gen/`. Any language or framework is
  acceptable where it clearly improves the result; say why in the commit message. Third-party
  packages are encouraged: OpenCV (contrib), scipy, numpy, Pillow, pydantic, typer,
  FastAPI/uvicorn on the Python side; Node/npm with Vite, React, TypeScript and Three.js
  for the annotator, matching image-blaster's stack so code can be ported both ways.
- **Blender side is bundled-Python only.** Official blender.org builds ship their own
  Python (3.10 on 4.0, 3.11 on 4.2+) with numpy, mathutils and bmesh. Code under
  `room_gen/blender/` must run with those alone; host-side packages are never imported
  there. Optional accelerations are guarded by try-import. (Installing packages into
  Blender's Python is possible but fragile across platforms, so it is never required.)
- **Blender 4.0 or newer**, headless for everything except opening results for editing.
- **Classical vision in the core, small local models as an extra.** The required path
  uses no learned weights and must always work. Small open-weight vision models that run
  locally on a typical desktop or laptop (CPU, or a GPU with ≤ 4 GB free VRAM) are allowed
  as the optional `room_gen[ml]` extra (§8.12): used automatically when installed, never
  required, weights downloaded once to the Hugging Face cache and never committed. These are
  vision models, not language models; they do not change the "no LLM outside Claude Code"
  rule.
- **image-blaster conventions.** Same `worlds/<slug>/` layout, indexed names
  (`N-slug.ext`, hidden `.N-slug-request.json`), same `project.json` / `image.json` /
  `object.json` / `scene.json` contracts, so either project can read the other's worlds.
- **Additive.** `deps/image-blaster` is never modified. Skills, agents and scripts here use
  the `room-` prefix so the `.claude/` tree can be merged into an image-blaster checkout.

## 3. Verified environment (this host, 2026-10-04)

| Item | Finding |
|---|---|
| Blender | 4.0.2 at `/usr/bin/blender` (Ubuntu package, uses system Python 3.12; site-packages are the system dist-packages) |
| Exporters | GLB, FBX, OBJ (`wm.obj_export`), `.blend` — verified headless |
| Importers | GLB, FBX, OBJ — verified headless |
| USD | `wm.usd_export` absent in this build → optional, detected at runtime |
| Render | `BLENDER_EEVEE` (legacy) renders headless; Cycles CPU only; NVIDIA T1000 present but no CUDA device exposed to Cycles here |
| Blender image I/O | PNG/JPEG/WEBP decode to numpy via `pixels.foreach_get`; JPEG/WEBP write via `save_render` |
| Blender geometry helpers | `mathutils.geometry.intersect_line_plane`, `intersect_line_line`, `intersect_plane_plane` |
| Host Python | 3.12.3; pip 24.0; `uv` at `~/.local/bin/uv`; venv works; numpy 1.26.4, scipy 1.11.4, Pillow 10.2.0 present system-wide; OpenCV and pydantic not installed (project venv will add them) |
| Node | 18.19.1, npm 9.2.0; no bun or pnpm. Vite 5 supports Node 18; prefer Node 20+ LTS in docs |
| numpy baseline | Sobel + Hough on 1 MP: 0.72 s (OpenCV will be faster; this is the fallback) |
| GPU / compute | NVIDIA T1000 8 GB (Turing, sm_75), driver 595.91, CUDA 13.2 runtime support; 92 GB RAM; 52 CPU threads; 8 TB free on the work disk |
| Network | PyPI, download.pytorch.org, Hugging Face and the npm registry all reachable |
| Claude Code facts (verified against code.claude.com docs) | Pro includes Claude Code with no API key, metered on the shared claude.ai usage pool. Subagent `model:` accepts `haiku`, `sonnet`, `opus`, `fable`, `inherit`, or a full id. SKILL.md may set `model`, `context: fork`, `agent`, `background`. Read handles PNG/JPG/WEBP/GIF multimodally. SessionStart and UserPromptSubmit hooks inject stdout into context. The desktop app's Code tab runs the same `.claude` tree as the CLI |

Target matrix: Blender 4.0.2 on this host, latest Blender LTS (4.2+: `BLENDER_EEVEE_NEXT`),
and the current blender.org macOS build. Version differences live in one shim module.

## 4. What is kept, replaced, or dropped from image-blaster

| image-blaster piece | Provider today | Here |
|---|---|---|
| Project envelope, `input/` staging, indexed files | Node scripts | Kept, re-implemented in Python (the Node originals stay usable on the same dirs) |
| Image analysis (`image-blast-uncover`, flat `IMAGE-BLAST.md` schema) | Claude | Kept; text fields are Claude-or-human; geometric fields move to the tools |
| World / environment | World Labs Marble (splat, collider, pano) | **Replaced** by calibration + layout → `room.json` → Blender shell mesh, photo-textured by rectification |
| Object 3-D models | FAL Hunyuan / Meshy | **Replaced** by an archetype library and a primitive DSL built in Blender; sizes and positions computed from 2-D boxes and the calibrated camera |
| Clean plate / image edit | nano-banana / gpt-image | **Dropped**; the shell is built from the survey, not from a cleaned photo (OpenCV inpainting fills texture holes) |
| Placement (`scene.json`) | manual in the viewer | Computed from boxes; written as `scene.json` for viewer compatibility |
| SFX | ElevenLabs via FAL | **Dropped** in v1 |
| Wildcard FAL | FAL | **Dropped** |
| React/Three viewer (`app/`) | Bun/Vite | Reused as the starting point for the annotator and result viewer (§8.10); world dirs stay index-compatible |

## 5. Architecture (Spec)

Three tiers write and read the same files. A build only ever reads tier-0 outputs.

```
tier 2  Claude autofill (optional)      .claude/ skills + subagents (Haiku/Sonnet)
        labels, boxes, archetypes,      writes: annotations.json, image.json text,
        descriptions, material names    recipe archetype/params
                      │ same JSON
tier 1  Human-in-the-loop (optional)    local web annotator (TS/React/Three, served by
        ~10 clicks when the photo is    the Python CLI): calibrate, trace floor, mark
        ambiguous                       openings, box objects, pick archetypes, view result
                      │ same JSON       writes: annotations.json
tier 0  Deterministic tools (required)  room_gen (host: OpenCV/scipy/numpy) +
                                        room_gen.blender (bpy, numpy, mathutils)
        + optional local models         room_gen.ml (depth, detection, segmentation)
        vision → calibration → layout → objects → lighting → textures → build → fit → export
        reads: photo, annotations.json   writes: calibration.json, room.json, recipes,
                                                 .blend/.glb/.fbx/.obj, previews, sidecars
```

Host/Blender split: everything that looks at pixels runs on the host (OpenCV, scipy, the
optional models); everything that makes geometry, materials, renders and exports runs
inside Blender. They exchange JSON and image files only.

```
input/photo.jpg ─ stage ─► source/0-photo.jpg
                              │
   host: vision.lines ────────┤ (auto)            annotations.json (human or Claude)
   host: calib.vps ───────────┼──────────────────────────┐
                              ▼                          ▼
                     calibration.json  (K, R, camera height, floor homography, confidence)
                              │
   host: layout ───────────────────────► room.json.shell (+ openings)
   host: objects (boxes, grabcut) ─────► room.json.placements + output/<obj>/recipe.json
   host: light ────────────────────────► room.json.lighting
   host: texture (warp + inpaint) ─────► output/world/N-world-tex-*.png
                              │
                 blender: build ─► shell, objects, lights, camera, exports, previews
                              │
                 host: fit ─► render-and-compare refinement (analytic wireframe
                              │   projection vs. photo edges, scipy optimiser)
                           export / bridge
```

## 6. Repository layout (Spec)

```
Blender_Room_Generator/
  CLAUDE.md  README.md  LICENSE  pyproject.toml  uv.lock
  room_gen.config.example.json   copy to room_gen.config.json to override defaults (room_gen/config.py)
  .github/workflows/ci.yml       unit + Blender LTS integration tests, annotator checks
  schemas/                       JSON Schema generated from room_gen/models.py (`room_gen schemas`)
  room_gen/                      host package (Python >= 3.10)
    cli.py  cli_vision.py        typer CLI (`room_gen ...`); every command prints one JSON report
    config.py  jsonio.py  indexed.py  sidecar.py  patch.py  project.py
    models.py                    pydantic contracts (§7)
    geometry.py                  PinholeCamera, rotations, polygons (shared conventions)
    coords.py                    Three.js Y-up <-> Blender Z-up; image-blaster viewer constants
    meshgen.py                   pure-Python primitive meshes (host bbox/face counts and Blender)
    shellgeom.py                 pure-Python wall frames, offsets, UV conventions, shell edges
    textures.py                  tileable procedural PNGs (wood/tile/brick/fabric/noise)
    exif.py                      focal length / orientation (Pillow)
    build.py                     prepares Blender jobs, manifests, scene.json, sidecars; bridge; render
    pipeline.py                  `room_gen auto`: photo -> annotations, calibration, room.json, recipes
    server.py                    FastAPI backend of the annotator
    blender_exec.py              find Blender, run entry.py headless, parse ROOM_GEN_RESULT
    vision/                      imageio lines calib layout wireframe openings objects scale light texture fit
    ml/                          runtime depth detect segment   (optional extra `room_gen[ml]`)
    archetypes/                  _dsl seating tables storage beds lighting misc (35 archetypes)
    blender/                     entry util shim materials meshbuild shell staging exporters preview build bridge inspect
  annotator/                     Vite + React 18 + TypeScript + three.js web annotator (vitest tests in src/)
  .claude/                       settings.json, hooks/, rules/project.md, skills/room-*, agents/room-*
  tests/
    unit/                        pytest, host only (synthetic flat-shaded rooms in tests/unit/synth.py)
    blender/                     builds, exports, projection round trip, bridge (marker `blender`)
    ml/                          local models on a rendered room (markers `ml`, `blender`)
    eval/                        scenes.py, benchmark.py, diagnose.py, REPORT.md, CLAUDE_TIER.md (marker `slow`)
    fixtures/                    rooms/living_room.json, recipes/*.json
  worlds/  input/                user data (gitignored)
  deps/image-blaster             read-only submodule
```

## 7. Data contracts (Spec)

All contracts are pydantic models in `room_gen/models.py`; JSON Schema is generated from
them into `schemas/` and TypeScript types for the annotator are generated from that
(`json-schema-to-typescript`). All JSON: UTF-8, 2-space indent, sorted keys,
`schema_version: 1`, metres and degrees. Blender space is right-handed Z-up; room origin is
the floor at the floor-polygon centroid. Pixel coordinates are `[u, v]`, origin top-left,
in the source image's native resolution.

Every block that a tool, a person or Claude may write carries
`"provenance": {"by": "auto|human|model|fit", "tool": "...", "confidence": 0..1}`.

### 7.1 Reused unchanged from image-blaster

`project.json`; per-image `source/<image>.json` and merged `image.json` (flat
`IMAGE-BLAST.md` schema, literal language, single-liftable-item object rule, no
`images[]`); `output/<object>/object.json` (identity and provenance only); `scene.json`
(`WorldSceneProject`: `instances[]` in Three.js Y-up, `sun`); indexed naming and hidden
request sidecars exactly as image-blaster's `.claude/rules/project.md`.

### 7.2 New: `worlds/<slug>/annotations.json` (pixel-space facts)

The only hand-made or model-made input the geometry tools need: pixel coordinates,
labels, and known lengths.

```jsonc
{
  "schema_version": 1, "world": "<slug>", "image": "worlds/<slug>/source/0-photo.jpg",
  "image_size": [4032, 3024],
  "calibration": {                           // optional; auto VPs are used when absent
    "parallel_pairs": [                      // fSpy style: two pairs of lines per axis
      { "axis": "x", "lines": [[[120,2200],[1800,1900]], [[150,2900],[1900,2500]]] },
      { "axis": "y", "lines": [[[2300,1900],[3900,2250]], [[2200,2500],[3950,2950]]] }
    ],
    "vertical_lines": [[[2010,400],[2000,2600]]],
    "principal_point": null,                 // null = image centre
    "reference": { "kind": "vertical", "pixels": [[2000,2600],[2000,760]], "metres": 2.03, "label": "door" },
    "camera_height_m": null,                 // null = derived from reference, else assumed 1.5
    "exif": { "focal_mm": 4.2, "focal_35mm": 26 }   // filled by room_gen.exif when present
  },
  "floor_corners": [[120,2200],[2010,2600],[3900,2250]],   // visible floor/wall corners, left→right
  "boundary_lines": [                        // traced visible stretches when corner feet are hidden
    { "kind": "wall_wall",  "pixels": [[1370,420],[1366,1240]], "provenance": { "by": "model", "tool": "room-survey", "confidence": 0.6 } },
    { "kind": "wall_floor", "pixels": [[757,1422],[1307,1425]], "provenance": { "by": "human", "tool": "annotator", "confidence": 0.9 } }
  ],
  "ceiling_height_m": null,
  "openings": [
    { "kind": "door",   "wall_hint": "left", "quad": [[300,700],[700,650],[700,2500],[300,2600]], "label": "door to hallway" },
    { "kind": "window", "wall_hint": "back", "quad": [[2300,700],[3300,700],[3300,1700],[2300,1700]] }
  ],
  "objects": [
    { "id": "armchair", "label": "armchair", "box": [1500,1500,2300,2500], "support": "floor",
      "archetype": "armchair", "params": {}, "materials_hint": ["green fabric","oak"] },
    { "id": "table-lamp", "label": "table lamp", "box": [3100,1200,3400,1700], "support": "side-table", "archetype": "table_lamp" }
  ],
  "known_lengths": [ { "pixels": [[2300,1700],[3300,1700]], "metres": 1.2, "label": "window width" } ],
  "notes": [],
  "provenance": { "by": "human", "tool": "annotator 0.1", "confidence": 0.9 }
}
```

### 7.3 New: `worlds/<slug>/calibration.json`

Output of `calibrate`: `intrinsics.K` (3×3), `vanishing_points` (three, homogeneous, with
inlier counts), `rotation` (3×3, camera→room), `camera_position`, `floor_homography`
(room XY → pixels), `method` (`auto-vp | manual-vp | manual-vp+auto-refine`),
`residuals`, `confidence`, `notes`. Downstream code uses two functions on it:
`pixel_to_plane(uv, plane)` and `point_to_pixel(xyz)`.

### 7.4 New: `worlds/<slug>/room.json` (room spec)

Produced by `layout` + `objects` + `light`, patched by `fit` and `room-qc`, consumed by
`build`:

```jsonc
{
  "schema_version": 1, "world": "<slug>", "source_images": ["worlds/<slug>/source/0-photo.jpg"],
  "calibration": "worlds/<slug>/calibration.json",
  "scale": { "reference": "door 2.03 m (annotations.reference)", "confidence": 0.8 },
  "shell": {
    "floor_polygon": [[-2.5,-3.0],[2.5,-3.0],[2.5,3.0],[-2.5,3.0]],   // XY, CCW
    "ceiling_height": 2.7, "wall_thickness": 0.12, "origin": "floor_centroid",
    "walls": [ { "edge": 0, "material": "wall_paint", "openings": [
        { "kind": "door", "offset": 1.1, "width": 0.9, "height": 2.03, "sill": 0.0 } ] } ],
    "floor": { "material": "floor_tex" }, "ceiling": { "material": "ceiling_white" },
    "trim": { "baseboard_height": 0.1, "crown": false },
    "visible_edges": [0, 1, 2], "guessed_edges": [3],
    "provenance": { "by": "auto", "tool": "layout", "confidence": 0.55 }
  },
  "fixed_features": [ { "id": "radiator", "recipe": "worlds/<slug>/output/radiator/recipe.json", "position": [2.3,0.0,0.0], "yaw": 90 } ],
  "materials": {
    "wall_paint":    { "base_color": "#e8e4dc", "roughness": 0.9 },
    "floor_tex":     { "image": "output/world/0-world-tex-floor.png", "roughness": 0.55, "uv_scale_m": [4.0,6.0] },
    "ceiling_white": { "base_color": "#f4f4f2", "roughness": 0.95 }
  },
  "lighting": { "sun": { "azimuth": 215, "elevation": 32, "strength": 4.0, "color": "#fff1dc" },
                "sky": { "strength": 1.0, "color": "#cfd9e6" }, "fixtures": [],
                "provenance": { "by": "auto", "tool": "light", "confidence": 0.3 } },
  "camera": { "position": [0.4,-2.9,1.45], "rotation": [84.0,0.0,-12.0], "focal_mm": 24.0, "sensor_mm": 36.0,
              "resolution": [4032,3024], "provenance": { "by": "auto", "tool": "calib", "confidence": 0.7 } },
  "placements": [ { "object": "armchair", "position": [-1.2,0.8,0.0], "yaw": 35, "scale": 1.0, "support": "floor",
                    "size_m": [0.85,0.9,0.95], "provenance": { "by": "auto", "tool": "objects", "confidence": 0.6 } } ],
  "notes": [], "updated_at": "..."
}
```

### 7.5 New: `worlds/<slug>/output/<object>/recipe.json` (object recipe)

Two levels. **Archetype level** is what humans and Claude write; **parts level** is what the
builder executes. `room_gen.archetypes.expand()` turns the first into the second
deterministically and records both.

```jsonc
{
  "schema_version": 1, "world": "<slug>", "object": "armchair",
  "archetype": "armchair",
  "params": { "width": 0.85, "depth": 0.9, "height": 0.95, "seat_height": 0.45, "arm_style": "boxy", "leg_style": "tapered", "cushion": true },
  "materials": { "fabric": { "base_color": "#6b7a4a", "roughness": 0.85 }, "oak": { "base_color": "#8a6a46", "roughness": 0.5 } },
  "bbox_m": [0.85, 0.9, 0.95], "origin": "bottom_center", "collision": "box",
  "parts": [ /* generated: box/cylinder/cone/sphere/torus/plane/prism/lathe/tube with position/rotation/scale/mirror/array/bevel/material */ ],
  "modifiers": ["join", { "subdivide": 1, "smooth": true }],
  "provenance": { "archetype_by": "human", "params_by": "auto", "colors_by": "auto" }
}
```

DSL scope: 9 primitives, per-part transforms, `mirror`, `array`, `bevel`, mesh-level
`join | subdivide | smooth | boolean_difference | shade_smooth_angle`, 64 parts and 50 k
faces max, Principled-BSDF materials with `procedural` hints `wood | tile | fabric | noise |
brick`. The `"script": "path.py"` escape hatch exists, is off unless
`allow_script_recipes: true`, and is shown to the user before it runs.

### 7.6 World manifest, sidecars, generated files

`output/world/N-world.json` is shaped like the World Labs manifest the viewer parses
(`assets.mesh.collider_mesh_url` → local `N-world.glb`, `thumbnail_url` → local thumbnail,
`spz_urls: {}`, `metric_scale_factor: 1`, `flip_y: false` so the viewer does not flip our
Y-up GLB) plus a `generator` block (`provider: "room-gen"`, files, `tiers_used`). Hidden
sidecars record inputs with sha256, Blender binary/version, seconds, warnings, failed
outputs, status; a build is skipped as `up-to-date` when the input digest is unchanged.

Furnished-room files live in `output/world/` under the `world-room` slug because the
image-blaster viewer would list any other `output/<dir>` holding a model as a placeable object.

```
output/world/   N-world.blend  N-world.glb  [N-world.fbx N-world.obj N-world.usd]   shell + fixed features
                N-world-preview.png                       empty room from the photo camera
                N-world-room.blend  N-world-room.glb [...] furnished room (+ photo camera)
                N-world-room-preview.png  N-world-plan.png  N-world-thumbnail.webp
                N-world.json  .N-world-request.json  .N-world-blender.log
                overlay.png      photo + reprojected shell (yellow), openings (cyan), objects (magenta)
                grid.png         photo + labelled native-pixel grid (`room_gen grid`, for Claude)
                textures/        procedural tiles and photo-*-<surface>.png rectified photo textures
output/<obj>/   N-<obj>.glb  N-<obj>.blend  [fbx obj]  N-<obj>-preview.png  .N-<obj>__model-request.json
                recipe.json  object.json
scene.json      placements in Three.js Y-up for the viewer (scale = 2 x ours: the viewer draws objects at 0.5)
```

## 8. Model-free toolchain (Spec) — the core of the project

Host-side modules live in `room_gen/vision/`, are pure functions over numpy arrays and
pydantic models, carry unit tests on synthetic images, and report a confidence. Budget: the
whole `auto` pass (lines → calibration → layout → objects → light → texture) under 10 s on
a 12 MP photo on this CPU; work at long-side 1024 px internally, textures at full res.

### 8.1 Image I/O and EXIF (`imageio.py`, `exif.py`)

OpenCV for decode/encode (`cv2.imread` with `IMREAD_COLOR`, HEIC via Pillow +
`pillow-heif` when installed), Pillow for EXIF (`Image.getexif()`: `FocalLength`,
`FocalLengthIn35mmFilm`, `Orientation`, `Make/Model`). Orientation is applied before any
pixel coordinate is recorded. The 35 mm-equivalent focal length is the calibration prior.

### 8.2 Line segments (`lines.py`)

`cv2.createLineSegmentDetector` (LSD) on a CLAHE-enhanced CIE-L image (`lines.enhance`),
FastLineDetector and Canny+HoughLinesP as fallbacks. Contrast enhancement matters: soft
wall/ceiling boundaries (white wall, grey ceiling) are otherwise below LSD's gradient
threshold, and losing them cost up to 1.3 m of wall error in the benchmark. Each segment also
gets a cross-line colour contrast (`side_contrast`, ΔE between thin strips on both sides);
layout evidence keeps segments with ΔE ≥ 4, which drops texture lines such as floor-plank
seams that have the same colour on both sides. `OrientedEdges` rasterises segments into 12
orientation bins with a distance transform each (oriented chamfer).

### 8.3 Vanishing points and camera (`calib.py`)

- **Auto:** RANSAC over segment pairs (a VP is the cross product of two homogeneous lines;
  inliers within 2° of the direction to the VP), greedy extraction of up to three VPs, then
  a joint nonlinear refinement of (f, R) with `scipy.optimize.least_squares` minimising
  angular residuals under the Manhattan constraint. With the principal point at the image
  centre and two finite orthogonal VPs, `f² = −(v1−c)·(v2−c)`. The VP nearest the image
  vertical is Z. Confidence from inlier fraction and orthogonality residual; non-Manhattan
  rooms get low confidence and the annotator is suggested.
- **Manual (fSpy math):** from `annotations.calibration` (`parallel_pairs`,
  `vertical_lines`, `principal_point`, `reference`). `manual-vp+auto-refine` snaps the
  user's lines to nearby detected segments before solving.
- **Scale and height:** camera height from `reference` (known vertical on the floor
  plane), else `known_lengths`, else `exif` focal + an assumed 1.5 m eye height with
  confidence 0.3 and a note. Floor homography `H = K [r1 r2 t]` for z = 0.
- **EXIF prior:** `FocalLengthIn35mmFilm` seeds `f`; a disagreement > 15 % with the VP
  estimate lowers confidence and is reported.

### 8.4 Floor plane and room layout (`layout.py`, `wireframe.py`)

The room is an axis-aligned box (x0, x1, y0, y1, h) in the calibration frame (camera above
the origin; polygon edges 0 front, 1 right, 2 back, 3 left). Objective, all in pixel units:

- **line support**: Gaussian-weighted length of projected box edges near same-orientation
  segments (τ = 4 px at 1024 px working width), minus 0.15 × unsupported visible length;
- **orientation consistency** (Hedau/Lee): a segment lying on a face cannot run parallel to
  that face's normal (e.g. plank end-joints on a hypothesised wall); −0.5 × such length;
- **face uniformity**: mean squared CIE-Lab deviation of a 64×48 colour grid from its
  face's mean, weight 0.02 × image width; separates a white wall from a beige one when the
  floor line is hidden behind a bed;
- **ceiling prior**: soft penalty below 2.4 m; search bound 2.2 m.

Search: differential evolution on a 2τ-smoothed objective, then **scale-ray scans** — for
every subset of walls together with the ceiling, solutions scaled about the camera (a
wall/ceiling line pair projects identically at (d, h) and (k·d, k·h); only floor lines break
the tie) — then full-range per-parameter rescans refining the top three peaks, then a local
polish; two restarts with different seeds, best objective wins. About 10 s on this CPU.

Annotated `floor_corners` fix the walls they touch; `ceiling_height_m` fixes h;
`boundary_lines` add strong, kind-specific line evidence (wall_floor lines only support model
floor edges, wall_ceiling ceiling edges, wall_wall vertical corners; weight 3, no penalty) and
mark the walls they touch as seen. Walls with
too little evidence are marked unseen and placed just beyond the visible floor (border rays
clipped at seen walls) but never more than 4 m from the camera. With the depth model, seen
walls with weak support are blended with the point-cloud extents and unseen walls/ceiling
only grow to contain the points. The joint camera + shell refinement is §8.9.

### 8.5 Openings (`openings.py`)

Auto candidates: quadrilaterals on a wall plane bounded by segments pointing to that
wall's VP and the vertical VP, brightness above the wall median (window) or tall-narrow
aspect reaching the floor (door); masks via `cv2.fillPoly`. Reported as candidates with
confidence, built only when confirmed by annotation or confidence ≥ 0.8. Confirmed quads
→ wall plane → `offset`, `width`, `sill`, `height`.

### 8.6 Objects from boxes (`objects.py`, `scale.py`, `archetypes/`)

- **Mask**: SAM when the extra is installed, else `cv2.grabCut` from the box (falls back to the
  box when the mask covers < 15 %).
- **3-D fit**: least squares over (x, y, log w, log d, log h) so the projected box matches the
  mask's bounding box; truncated sides are ignored; weak log-normal priors on the archetype's
  default size and aspect; optional depth term. Yaw is Manhattan: objects whose archetype is
  `against_wall` face away from the nearest wall, others face the camera's quadrant (both 0°
  and 90° variants are tried). Footprints are clamped inside the room. Wall items back-project
  onto the nearest wall plane and fall back to a free-standing fit when they do not land on it.
  Items on other items get `z` from the supporter's top; pendant lamps hang from the ceiling.
- **Scale from object heights** (`vision/scale.py`): typical heights with relative spread per
  archetype (dining table 0.75 m ± 5 %, counter 0.90 ± 4 %, sofa 0.84 ± 12 %, ...; doors
  2.03 m ± 4 %). Objects cut by the image top/bottom or covered by a box in front of them are
  excluded; weighted median, outliers beyond 2.5 MAD dropped, uncertainty inflated by spread
  and for single items, correction capped at ×1.5; blended with the current scale source
  (σ: reference 3 %, known length 4 %, assumed eye height 13 %, depth model 25 %).
- **Archetypes**: 35 parametric generators (`room_gen archetypes list`), each with defaults,
  ranges, material slots and synonyms; `generic_box` is the fallback. Every archetype matches
  its declared bbox within 3 % at 0.6×, 1× and 1.4× size (unit-tested).
- **Colours**: k-means (k = 3) on mask pixels → slot base colours in archetype slot order.

### 8.7 Lighting from image statistics (`light.py`)

Gray-world and bright-patch white balance → sun/sky colour; mean log-luminance →
exposure and sun strength; with a window opening, the brightest floor patch's centroid
relative to the window's floor projection gives sun azimuth and elevation; otherwise an
overhead fixture. Confidence ≤ 0.4 by design; this block is the first thing `fit` and
`room-qc` may change.

### 8.8 Photo textures by rectification (`texture.py`)

For each shell surface visible in the photo: plane→image homography from
`calibration.json`; `cv2.warpPerspective(..., WARP_INVERSE_MAP)` onto a 2048² texel grid
clipped to the surface polygon; mask texels covered by object masks (§8.6) and openings;
`cv2.inpaint` (Telea) fills holes, mean colour as last resort; write
`N-world-tex-<surface>.png`; the material uses the image with `uv_scale_m` equal to the
surface's metric size. The build also offers `camera_projection: true` (UVProject modifier
from the estimated camera) as a quick alternative.

### 8.9 Render-and-compare fitting (`fit.py`)

Deterministic replacement for a vision model judging the result. The camera sits inside a
convex room, so every shell edge in view is visible from the inside except where furniture
covers it; the shell's wireframe can therefore be projected analytically on the host
(milliseconds per evaluation) instead of rendered.

- Photo edges: `cv2.Canny` plus gradient orientation, split into 6 orientation bins, one
  `cv2.distanceTransform` per bin (oriented chamfer).
- Parameter vector `p`: camera height, pitch, roll, yaw, focal; room width, depth, ceiling
  height, room offset; per confirmed opening offset/width/sill/height.
- Model edges: the shell's edges (floor, ceiling, vertical corners, opening frames) are
  clipped against the near plane and image, sampled every 4 px, each sample scored by the
  distance in the bin matching its projected direction, truncated at 25 px, minus a
  reward for coverage; plus a prior term pulling `p` to its initial value weighted by each
  block's confidence.
- `scipy.optimize.minimize` (Nelder–Mead, then Powell) on a bounded transform of `p`,
  `fit.max_evals` default 400. Writes the patched `room.json` with
  `provenance.by = "fit"`, residual before/after, and `N-world-overlay.png` (photo +
  reprojected wireframe, drawn with OpenCV).
- Placements are refit separately (§8.6 box fit against masks) after the shell moves.

### 8.10 Human-in-the-loop annotator (`annotator/`, `room_gen/server.py`)

A small local web app, ported from `deps/image-blaster/app` (Vite + React + TypeScript +
Three.js) so the existing world-directory indexing and GLB viewing carry over. Started by
`room_gen annotate --world <slug>` (FastAPI serves the built UI and JSON endpoints, opens the
browser). It writes `annotations.json` and nothing else; the headless CLI with the same
file produces the identical build (tested).

Screens, each a thin UI over a backend call:

1. **Calibrate** — "Auto" shows detected segments and the three VP axes; "Manual" gives
   fSpy-style draggable line pairs and a reference length. The backend returns the
   homography; the client draws the floor grid on the photo live so the user sees it land.
2. **Trace floor** — clicks on the photo are back-projected on the server and drawn as the
   plan polygon beside the image.
3. **Openings** — two clicks on a wall → quad snapped to that wall's VP axes.
4. **Objects** — drag a box, type a label, pick an archetype (synonym search), see the
   grabcut mask and colour swatches, adjust params.
5. **Result** — overlay, plan, preview PNGs and the GLB in Three.js; buttons for build,
   fit, export, open folder.

A Blender add-on for editing in place is a later nicety (M7), not the annotator.

### 8.11 What is left for a model, and how it plugs in

Everything metric, geometric, photometric and file-related is tier 0. What remains is
semantic: which pixels are an object and what it is called, which archetype and params fit,
material names, the literal `image.json` prose, and resolving ambiguity. Those are exactly
the fields in `annotations.json` (`objects[].label/box/archetype/params/materials_hint`,
`openings[].kind`, `floor_corners`, `reference`) and the text fields of `image.json`.
Claude fills them by Reading the photo (§11); a person fills them in §8.10; the auto pass
fills what it can with low confidence. Nothing in `room_gen` branches on which it was.

### 8.12 Optional local models (`room_gen/ml/`, extra `room_gen[ml]`)

Allowed and encouraged within a desktop/laptop budget: total cached weights ≤ 1.5 GB,
peak VRAM ≤ 4 GB at fp16, every model also runnable on CPU, and each step ≤ 30 s on a
modern laptop CPU at the working resolution. Runtime is PyTorch + Hugging Face
`transformers`; `runtime.py` picks CUDA, then Apple MPS, then CPU (`--device` overrides),
uses fp16 on GPU, loads lazily, and records model id, revision and device in the request
sidecar. All models are Apache-2.0 or MIT.

| Role | Default model (HF id) | Params | Licence | Replaces / improves |
|---|---|---|---|---|
| Metric depth, indoor | `depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf` | 25 M | Apache-2.0 (upstream licence statement for Small; card has no licence field) | scale and camera height without a reference; floor/wall/ceiling plane fitting in `layout`; object distance prior in `objects`; ceiling height |
| Open-vocabulary detection | `google/owlv2-base-patch16-ensemble` (alt. `IDEA-Research/grounding-dino-tiny`) | 155 M / 172 M | Apache-2.0 | proposes `annotations.objects[]` boxes + labels from the archetype vocabulary; door/window candidates |
| Segmentation from boxes | `facebook/sam-vit-base` (light alt. `Zigeng/SlimSAM-uniform-77`) | 94 M / 10 M | Apache-2.0 | replaces grabCut masks in `objects` and `texture` |
| Captioning (optional) | `microsoft/Florence-2-base` or `HuggingFaceTB/SmolVLM-256M-Instruct` | 230 M / 256 M | MIT / Apache-2.0 | literal `image.json` prose when neither Claude nor a person writes it |

How they plug in, without changing any contract:

- `depth`: per-pixel metric depth → back-projected point cloud in the calibrated camera →
  RANSAC planes aligned with the Manhattan axes (floor, ceiling, up to four walls). Floor
  plane distance gives camera height (scale) when no `reference` exists; wall planes give
  room extents that are cross-checked against the line-based layout; disagreements lower
  confidence. Provenance `tool: "depth-anything-v2-metric-indoor-small"`.
- `detect`: prompts are the archetype names plus synonyms; boxes above a score threshold,
  after per-class NMS and a minimum-size filter, become `annotations.objects[]` with
  `provenance.by = "auto"`. Existing human/model entries are never overwritten.
- `segment`: box-prompted masks for every annotated object; falls back to grabCut.
- `caption`: fills empty `image.json` text fields only.
- `room_gen models list|download|check` manages the cache; `auto --ml auto|on|off`
  (default `auto` = use what is installed).
- Tests marked `ml` run only when the extra is installed; the synthetic benchmark reports
  with and without models.

## 9. Blender build engine (Spec)

`room_gen/blender/entry.py` is the only script Blender runs:

```
blender --background --factory-startup --python-exit-code 1 --python room_gen/blender/entry.py -- \
  <probe | build | render | bridge | inspect> --job job.json
```

The host (`room_gen/build.py`) writes a fully resolved job (absolute paths, expanded
recipes, final placements, Blender camera parameters from `PinholeCamera.blender_params`);
Blender only executes. The last stdout line is `ROOM_GEN_RESULT {json}`.

- `shell.py`: floor and ceiling slabs over the mitred outer polygon, one solid slab per wall,
  openings cut with EXACT booleans applied through the depsgraph, baseboards between
  floor-level openings, casings, window glass, door leaves, emissive exterior backdrops
  (rendered, never exported); photo-texture UVs follow `shellgeom`.
- `meshbuild.py`: recipe parts from `meshgen` into one bmesh per object, per-part bevel on
  sharp edges, boolean cutters, box-projected world-scale UVs, sharp-edge shading.
- `materials.py`: Principled BSDF only (glTF-safe); procedural looks are host-generated PNG tiles.
- `staging.py`: sun (azimuth clockwise from +Y), sky colour, fixtures, a ceiling fill light when
  no fixtures exist, photo camera, plan camera, placements.
- `exporters.py`: GLB (Y-up, modifiers applied), FBX, OBJ, USD when the build has it; partial
  `.blend` files through `bpy.data.libraries.write` of a temporary scene.
- `preview.py`: EEVEE previews (AgX when available), Workbench plan with labels, studio shots
  per object, WEBP/PNG thumbnails. `bridge.py` reproduces image-blaster's viewer transforms.
- Measured: a 7-object living room builds with all exports and previews in about 3 s (9 s with
  per-object studio renders on first run); projection matches Blender within 0.6 px.

## 10. Host CLI (Spec)

`uv sync` installs `room_gen`; `uv run room_gen ...` or `.venv/bin/room_gen ...`. Global options:
`--root <workspace>`, `--config <file>`, `--blender <exe>`.

```
room_gen project   --world <slug> [--stage-input] [--display-name ...]
room_gen probe                                  # Blender + capabilities, OpenCV, models, annotator, worlds
room_gen auto      --world <slug> [--ml auto|on|off] [--device cpu|cuda|mps] [--no-fit] [--no-textures] [--build]
room_gen grid      --world <slug>               # labelled native-pixel grid image for Claude
room_gen validate  --room | --recipe | --annotations | --calibration | --image <file>
room_gen schemas   [--out schemas]
room_gen build     --world <slug> [--formats glb,fbx,obj,usd] [--objects a,b] [--force] [--no-previews]
room_gen export    --world <slug> --formats glb,fbx,obj
room_gen bridge    --world <image-blaster worlds/slug> [--out <slug>] [--formats ...]
room_gen inspect   <file.glb|.fbx|.obj|.blend>   # re-import in Blender, report meshes/bounds
room_gen patch     --room <room.json> --ops <merge-patch.json>   # validated before writing
room_gen path      --world <slug> --kind world|object [--slug x] [--ext .glb] [--next]
room_gen annotate  --world <slug> [--port 5174]   # serves annotator/dist + API
room_gen archetypes list | show <name> | resolve "<label>" | expand <recipe.json> [--write]
room_gen models    list | check | download
room_gen version
```

The individual stages (calibrate, layout, objects, light, texture, fit) run inside `auto`;
`--no-fit` / `--no-textures` skip stages. All commands are synchronous and print one JSON
object; exit code 0/1. Blender discovery: `--blender`, `ROOM_GEN_BLENDER`, config `blender`,
`PATH`, platform defaults.

## 11. Claude layer (Spec) — optional autofill

### 11.1 Model assignment

Subagent frontmatter `model:` decides; tier-0 work never depends on it. Measured on the
dining benchmark scene (tests/eval/CLAUDE_TIER.md): Sonnet's boxes averaged IoU 0.77 with the
truth and reproduced the room as well as ground-truth boxes; Haiku's averaged about 0.15
(shifted ~120 px) and are not usable for pixel work. Vision-with-coordinates therefore uses Sonnet.

| Agent | Model | Writes | Notes |
|---|---|---|---|
| `room-survey` | `sonnet` | `image.json`, `annotations.floor_corners`, `boundary_lines`, `openings[]`, `reference`, `known_lengths` | reads grid.png and overlay.png |
| `room-boxes` | `sonnet` | `annotations.objects[]` | Haiku measured too imprecise |
| `room-recipe` | `haiku` | one `recipe.json` (archetype, style params, colours) | text-only edits |
| `room-build` | `haiku` | nothing; runs `build`, reports | never reads images |
| `room-qc` | `sonnet` | annotations / recipe / merge patch, then rebuild | ≤ 2 rounds |
| `room-bridge` | `haiku` | nothing; runs `bridge` | |

### 11.2 Skills, hooks, settings

Skills: `room-project`, `room-auto` (orchestration in the main session), `room-survey`
(+ `ROOM-SURVEY.md` contract), `room-boxes`, `room-recipe` (+ `RECIPE-DSL.md`), `room-build`,
`room-qc`, `room-export`, `room-bridge`; the generation skills fork into the agent of the same
name. `allowed-tools` are limited to Read/Write/Glob, `ls` and `room_gen`. Everything Claude
writes carries `provenance.by = "model"`; `auto` never overwrites `human` or `model` blocks.
Hooks: `SessionStart` runs `room_gen probe` and prints Blender/model/annotator status, worlds
and staged input (no key checks); `UserPromptSubmit` lists `input/`. Rules for sessions in
this repo that *use* the tool are in `.claude/rules/project.md`.

### 11.3 Order of operations (one-shot)

1. `room-project --stage-input`; 2. `room_gen auto` (always first, model-free);
3. `Agent(room-survey)` and `Agent(room-boxes)` in parallel, background, to fill what auto
left low-confidence or empty; 4. `objects`, `build`, `assemble`, `fit`; 5.
`Agent(room-qc)` ≤ 2 rounds; 6. report paths, confidences, which tier produced each block.
A user with no model runs steps 2 and 4 and, if needed, `annotate` instead of 3 and 5.

## 12. Quality bar and tests (Spec)

```
uv run pytest tests/unit                 # 150+ host tests, ~10 s, no Blender needed
uv run pytest tests/blender              # needs Blender: builds, exports, projection, bridge
uv run pytest tests/ml                   # needs room_gen[ml] + cached weights (and Blender)
uv run pytest tests/eval                 # slow quality gates on rendered rooms
uv run python -m tests.eval.benchmark    # regenerates tests/eval/REPORT.md (4 scenes x 3 modes)
cd annotator && npm test && npm run build
```

- **Unit**: indexed names, JSON I/O, merge patch, config, staging, camera model, coordinate
  conversions, shell geometry, contracts (valid and invalid), primitives closed/outward,
  every archetype at three sizes, recipe auto-fit, scene.json conventions, calibration on
  synthetic rooms (focal < 2 %, rotation < 0.5°), manual calibration, metric scale cues,
  layout, openings, box fit, masks/colours, texture rectification, lighting, CLI and API.
- **Blender**: probe, fixture build with every export re-imported, all 35 archetypes built
  within 10 % of their bbox, emissive markers land within 0.6 px of `PinholeCamera` (with lens
  shift), bridge reproduces image-blaster's transforms.
- **Benchmark** (`tests/eval/REPORT.md`): Blender renders of four rooms with known geometry,
  three modes (`auto` lines only, `annotated` with ground-truth boxes standing in for a person
  or Claude, `ml`). Quality gates in `tests/eval/test_benchmark.py`.
- **Annotator**: 89 vitest tests (transforms, reducer/undo, box normalisation, API errors,
  schema/type consistency); `npm run gen:types -- --check` fails when schemas change.

## 13. Milestones (Spec) — model-free first

| Milestone | Status (2026-10-04) |
|---|---|
| M0 scaffold: package, contracts, schemas, probe, project, validate, hooks, tests | done |
| M1 bridge from image-blaster worlds | done (tested on synthesised image-blaster worlds; no real World Labs output available) |
| M2 build core: shell, openings, DSL, archetypes, materials, lighting, exports, previews | done |
| M3 vision: calibration, layout, objects, scale, lighting, `auto` | done |
| M3b local models: depth, detection, segmentation, `models` command | done |
| M4 annotator | done (openings are axis-aligned rectangles, not VP-snapped; no mask/swatch preview) |
| M5 photo textures and analytic fit | done |
| M6 Claude layer: skills, agents, hooks; Haiku vs Sonnet measured | done |
| M7 polish | partial: USD/WEBP gated by probe, plan labels, drop-in notes in README; captioning model and Blender edit-in-place add-on not done; CI workflow written but not yet run on GitHub |

## 14. Non-goals

Gaussian splats, NeRFs, photogrammetry; learned models in the required path; models
beyond the §8.12 desktop budget; any hosted inference; audio;
image editing or clean plates; an Anthropic-API mode; non-Manhattan or multi-room
reconstruction in v1 (curved walls become polyline approximations, low confidence).

## 15. Rules for Claude sessions in this repo (apply now)

- **Git:** read-only git is fine. Do not commit, branch, push, tag or amend unless the user
  explicitly asks in that message. `deps/image-blaster` is a submodule; never edit inside it.
- **Keep the suites green**: `uv run pytest tests/unit tests/blender` and the annotator's
  `npm test` before proposing a commit; regenerate `schemas/` (`room_gen schemas`) and the
  annotator types (`npm run gen:types`) whenever `room_gen/models.py` changes.
- **Measure, don't guess**: changes to vision code must be checked with
  `python -m tests.eval.benchmark` (and `tests/eval/diagnose.py` for layout failures).
- **Python preferred for business logic.** Use another language or framework only where
  it clearly improves the result (the annotator UI is the expected case) and say why in
  the commit message.
- **Blender-side code uses only Blender's bundled modules.**
- **Never add external inference or an API-key flow.** If something cannot be done by
  deterministic code, a person in the annotator, or Claude Code, write it under §14.
- **Local models** are allowed within the §8.12 budget and licence rules (Apache-2.0,
  MIT, or similarly permissive). Weights live in the Hugging Face cache, never in git. A
  new model or a bigger one needs a line in the §8.12 table first.
- **Model-optional by construction.** Any new feature must work without Claude first; the
  skill for it comes second and only fills JSON.
- **Images:** Read a PNG/JPG into context only when multimodal analysis is the task
  (`room-survey`, `room-boxes`, `room-qc`). Report generated images by path.
- **Blender** is invoked only through `room_gen ...`.
- **Verify before claiming:** every exporter, engine, decoder or package assumption must be
  checked with `room_gen probe` or §3 on the host in question.
- **Keep this file current** when any decision in §5–§13 changes.

## 16. Open questions and assumptions

- "Claude Mac plan" in the original request is read as the Claude **Max** plan; the spec also
  covers Claude Code inside the Claude desktop app on macOS.
- **Real photos are harder than the benchmark.** On two public-domain photos the automatic
  path was poor: a tight sofa close-up with almost no floor or ceiling, and a cluttered room
  where curtain hems were taken for the wall/floor line. Tier 1/2 (annotator clicks or the
  `room-survey` agent marking floor corners and a reference length) is the intended remedy;
  a curated set of real photos with measured ground truth would make this quantitative.
- **The depth model's metric scale** was 25–70 % off on renders and real photos; it is
  guarded (implausible heights rejected, σ 25 %) and object heights correct it, but a known
  length or reference from the user remains the most reliable scale source.
- Auto layout assumes a Manhattan box room; L-shaped rooms need annotated corners and are
  approximated by their bounding box.
- USD export is missing from the Ubuntu Blender 4.0 build; it is reported, not faked.


## 17. Implementation status and measured quality (2026-10-04)

Benchmark (`tests/eval/REPORT.md`, final run 2026-10-04, four rendered rooms):

| Mode | Focal err | Rotation err | Camera height err | Floor IoU | Visible-wall err | Objects |
|---|---|---|---|---|---|---|
| `auto` (lines only, height assumed 1.5 m) | ≤ 0.55 % | ≤ 0.33° | 0–9 % | 0.73–0.86 | 0.02–0.39 m | none (no boxes) |
| `annotated` (ground-truth boxes) | ≤ 0.55 % | ≤ 0.33° | 0–6 % | 0.77–0.89 | 0.02–0.28 m | 24/26 matched, 0.07–0.32 m |
| `ml` (local models) | ≤ 0.83 % | ≤ 0.47° | 2–7 % | 0.77–0.85 | 0.03–0.37 m | 19/26 matched, 0.18–0.57 m |

With Sonnet-drawn boxes the dining room matched the ground-truth result
(tests/eval/CLAUDE_TIER.md). Typical run times on this host: `auto` 14–30 s (layout ≈ 10 s,
models ≈ 10 s), `build` 3–10 s. Suites: 150 unit, 5 Blender, 4 model, 4 slow end-to-end
tests (Python) and 106 annotator tests pass.

Real-photo check (public-domain Wikimedia photos, no ground truth): on a cluttered living
room the automatic layout took a curtain hem for the wall/floor line (room 12.9 m deep). A
Sonnet `room-survey` run traced the hidden back/right corner as a `wall_wall` boundary line
and a weak floor-line proxy; re-running `auto` moved the back wall onto the window wall and
gave a 3.6 × 7.3 m room with the bookshelf against it, which is closer to the photo but not exact.

Known limits: real photos (§16); doors/windows are only found by the detector or by
annotation (no classical opening detector yet); the front wall behind the camera is always
a guess; photo textures are re-lit in Blender, so textured surfaces render brighter than the
photo.
