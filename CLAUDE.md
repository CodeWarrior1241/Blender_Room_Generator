# Blender Room Generator — build specification

This file is the specification for what to build in this repository and the standing
instructions for any Claude session working here. Nothing below is implemented yet.
Sections marked **Spec** describe the target; **Rules** (§15) apply now.

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
  CLAUDE.md  README.md  LICENSE
  pyproject.toml  uv.lock             host package + deps; `uv sync` creates .venv
  room_gen.config.json                user defaults: blender path, render size, exports, fit budget
  schemas/                            JSON Schema exported from the pydantic models (docs + annotator types)
  room_gen/                           host package (Python ≥ 3.10)
    __init__.py  __main__.py  cli.py  (typer)
    models.py       pydantic models for every contract in §7; `schemas/` is generated from here
    project.py      envelope, staging, state report (parity with project-state.mjs)
    indexed.py      N-slug.ext / .N-slug-request.json helpers
    blender_exec.py find Blender, run headless, parse ROOM_GEN_RESULT, render-server client
    sidecar.py  coords.py  exif.py (Pillow)
    vision/         host-side CV
      imageio.py  lines.py  calib.py  layout.py  openings.py  objects.py  light.py  texture.py  fit.py
    ml/             optional local models (import-guarded; package extra `room_gen[ml]`)
      __init__.py  runtime.py (device pick, cache, budget)  depth.py  detect.py  segment.py  caption.py
    archetypes/     parametric furniture → DSL parts (pure Python)
      __init__.py  seating.py  tables.py  storage.py  beds.py  lighting.py  misc.py  sizes.py  synonyms.py
    server.py       FastAPI app for the annotator: serves the built UI, reads/writes world JSON, runs tools
    blender/        runs inside Blender only (bpy, numpy, mathutils, bmesh)
      entry.py  shim.py  shell.py  openings.py  recipes.py  materials.py  lighting.py
      camera.py  placement.py  exporters.py  preview.py  render.py  bridge.py
  annotator/        Vite + React + TypeScript + Three.js (ported from deps/image-blaster/app)
    package.json  vite.config.ts  src/  (calibrate, trace, openings, boxes, result viewer)
  .claude/
    settings.json  rules/project.md  hooks/setup-check.sh  hooks/input-check.sh
    skills/room-project  room-survey  room-boxes  room-recipe  room-build  room-qc  room-export  room-bridge
    agents/room-survey.md  room-boxes.md  room-recipe.md  room-build.md  room-qc.md  room-bridge.md
  worlds/.gitkeep  input/.gitkeep
  tests/
    unit/          pytest on host (vision on synthetic images, archetypes, models, coords, exif)
    blender/       `blender -b --python tests/blender/run_all.py`
    annotator/     vitest
    fixtures/      rooms/ recipes/ annotations/ synthetic photos rendered by the eval
    eval/          synthetic round-trip benchmark + REPORT.md
  .github/workflows/ci.yml   uv + pytest; downloads Blender LTS tarball for the Blender tests; npm test
  deps/image-blaster                  git submodule, read-only reference
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
`spz_urls: {}`, `metric_scale_factor: 1`) plus a `generator` block (`provider: "room-gen"`,
`room_json`, `calibration_json`, `blender_version`, `tiers_used`). Hidden sidecars record
inputs, file hashes, Blender binary/version, per-stage wall-clock, exporter results,
warnings, status.

```
output/world/   N-world.blend  N-world.glb  [N-world.fbx N-world.obj N-world.usdc]
                N-world-preview.png  N-world-plan.png  N-world-thumbnail.webp|png
                N-world-tex-floor.png  N-world-tex-wall-<i>.png
                N-world-overlay.png   (photo + reprojected wireframe, for humans and QC)
                N-world.json  .N-world-request.json
output/<obj>/   N-<obj>.glb  N-<obj>.blend  N-<obj>-preview.png  .N-<obj>-request.json
output/room/    N-room.blend  N-room.glb  N-room-preview.png     (furnished, appended)
scene.json      derived from placements, Three.js Y-up
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

`cv2.createLineSegmentDetector` (LSD, available again in OpenCV ≥ 4.5.1) as the primary
detector, `cv2.ximgproc.createFastLineDetector` (opencv-contrib) as the alternative, and
`cv2.Canny` + `cv2.HoughLinesP` as the fallback. Output: segments with endpoints, length,
mean gradient magnitude; debug overlay PNG with `--debug`.

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

### 8.4 Floor plane and room layout (`layout.py`)

- **Auto:** wall/floor boundary = long segments in the lower 60 % of the image pointing to
  one of the two horizontal VPs; chain left→right; corners where chains of different VP
  families meet near a vertical segment. Back-project the polyline to the floor plane and
  fit a Manhattan rectangle (edges parallel to the VP axes) by least squares; unseen edges
  become `guessed_edges` with defaults (room depth = 1.5 × visible width unless a wall is
  seen).
- **From clicks:** `floor_corners` back-projected directly; closed with Manhattan guesses.
- **Ceiling height:** from a wall corner whose top is visible, else `ceiling_height_m`,
  else 2.7 m with low confidence.

### 8.5 Openings (`openings.py`)

Auto candidates: quadrilaterals on a wall plane bounded by segments pointing to that
wall's VP and the vertical VP, brightness above the wall median (window) or tall-narrow
aspect reaching the floor (door); masks via `cv2.fillPoly`. Reported as candidates with
confidence, built only when confirmed by annotation or confidence ≥ 0.8. Confirmed quads
→ wall plane → `offset`, `width`, `sill`, `height`.

### 8.6 Objects from boxes (`objects.py`, `archetypes/`)

- **Mask from box:** `cv2.grabCut` initialised with the box (5 iterations) gives a
  foreground mask; its bottom contour is the floor-contact line, its extremal columns the
  width, its top the height. This is markedly better than the raw box when objects overlap.
- **Metric, no learning:** contact-line midpoint → floor point via the homography (or the
  support object's top plane); contact-line endpoints → width; mask top → height via the
  vertical through the floor point; depth from the archetype's default aspect unless a side
  face is visible; yaw from the dominant horizontal VP among segments inside the mask.
  Confidence drops when the mask touches the image border or another mask's floor region.
- **Archetype library** (`room_gen/archetypes/`, pure Python): sofa, loveseat, armchair,
  dining_chair, office_chair, stool, bench, bed, nightstand, dresser, wardrobe, bookshelf,
  cabinet, sideboard, desk, dining_table, coffee_table, side_table, tv_stand, tv, floor_lamp,
  table_lamp, pendant_lamp, rug, plant, radiator, fireplace, picture_frame, curtain,
  generic_box. Each: `sizes.py` defaults, named params with ranges, material slots,
  `expand(params) -> parts[]`. `generic_box` is the universal fallback so any labelled box
  becomes a correctly sized placeholder. `synonyms.py` maps labels (`couch` → sofa).
- **Colours:** `cv2.kmeans` (k = 3) on mask pixels after dropping the brightest 10 % and
  darkest 5 %; largest cluster → primary `base_color`, second → secondary slot.

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
blender --background --factory-startup --python room_gen/blender/entry.py -- \
  <command> --world <path> [--index N] [--json <path>] [--out <dir>] [--config room_gen.config.json] [--debug]
commands: probe | build | build-object | render | export | bridge
```

Last stdout line is `ROOM_GEN_RESULT {json}`; non-zero exit on failure. Modules: `shim.py`
(EEVEE id, OBJ operator, optional USD/WEBP, 4.2+ extensions), `shell.py` (floor, mitred
solid walls, ceiling, trim; one object per surface, metre-scaled UVs, collection `Shell`),
`openings.py`, `recipes.py` (`build_recipe(recipe) -> Object`, asserts `bbox_m` ±10 %,
`auto_fit`), `materials.py` (Principled only, glTF-safe; image textures from §8.8),
`lighting.py`, `camera.py`, `placement.py` (append/link, `support` by ray-cast,
wall-intersection nudge), `exporters.py` (GLB `export_yup=True`, FBX, OBJ, optional USD,
always `.blend`), `preview.py` (EEVEE 960×540, 64 samples, Filmic), `render.py` (render a
room spec from an arbitrary camera; used by the synthetic benchmark), `bridge.py`
(import image-blaster world: collider GLB, object GLBs, `scene.json` with `x,y,z → x,−z,y`,
`sun`, `metricScaleFactor`; save `N-room.blend`; re-export).

## 10. Host CLI (Spec)

Installed as `room_gen` (typer) by `uv sync`; `python -m room_gen` is equivalent.

```
room_gen project   --world <slug> [--stage-input] [--display-name ...]
room_gen probe                                     # Blender, OpenCV, Node, annotator build status
room_gen auto      --world <slug> [--ml auto|on|off] [--device cpu|cuda|mps]   # lines→calibrate→layout→objects→light→texture→room.json
room_gen calibrate --world <slug> [--manual]
room_gen layout    --world <slug>
room_gen objects   --world <slug> [--ids a,b]
room_gen light     --world <slug>
room_gen texture   --world <slug> [--surfaces floor,wall-0]
room_gen validate  --room <path> | --recipe <path> | --annotations <path>
room_gen build     --world <slug> [--objects a,b] [--skip-shell] [--regenerate]
room_gen assemble  --world <slug>
room_gen fit       --world <slug> [--max-evals N] [--params camera,shell,openings,placements]
room_gen preview   --world <slug> [--index N]
room_gen export    --world <slug> --formats glb,fbx,obj[,usd] [--index N]
room_gen bridge    --world <path-to-worlds/slug> [--out worlds/<slug>]
room_gen annotate  --world <slug> [--port 5174]    # serves the annotator, opens the browser
room_gen patch     --room <path> --ops <merge-patch.json>
room_gen path      --world <slug> --kind world|object --slug x --ext .glb [--next]
room_gen archetypes [list | show <name> | expand <recipe.json>]
room_gen models    [list | download | check]       # optional local models (§8.12)
```

Shared behaviour: synchronous, one JSON report on stdout, human log on stderr, exit 0/1,
`--regenerate` allocates a new index, otherwise repair-in-place. Blender discovery:
`--blender`, `ROOM_GEN_BLENDER`, `room_gen.config.json`, `PATH`, platform defaults
(`/Applications/Blender.app/Contents/MacOS/Blender`, `C:\Program Files\Blender Foundation\Blender*\blender.exe`,
`/usr/bin/blender`, `/snap/bin/blender`). Per-invocation timeout from config (600 s).
`auto` is the one-command model-free path.

## 11. Claude layer (Spec) — optional autofill

### 11.1 Model assignment

Subagent frontmatter `model:` decides; the main session's model is the user's `/model`
choice. Tier-0 work never depends on this table.

| Agent | Model | Writes | Notes |
|---|---|---|---|
| `room-survey` | `sonnet` | `image.json` text, `annotations.floor_corners`, `openings[]`, `reference`, `known_lengths` | the one vision step where judgment matters; asks for one known length when auto calibration confidence < 0.5 |
| `room-boxes` | `haiku` | `annotations.objects[]` (label, box, support, archetype, materials_hint) | escalate to `sonnet` if `objects` rejects > 30 % of boxes |
| `room-recipe` | `haiku` | `recipe.json` archetype + params (not parts) | only when archetype defaults look wrong |
| `room-build` | `haiku` | nothing; runs CLI, reads JSON reports | never Reads PNGs |
| `room-qc` | `sonnet` | merge patch to `room.json` / recipes | reads `N-world-overlay.png` and the photo; after `fit`; ≤ 2 rounds |
| `room-bridge` | `haiku` | nothing; mechanical | |

### 11.2 Skills, hooks, settings

Skills mirror image-blaster's shape (`name`, `description`, `argument-hint`, tight
`allowed-tools` limited to `room_gen *`, `ls`, Read, Write, Glob; `context: fork` + `agent:`
for generation skills; `model:` per §11.1). `room-survey` carries `ROOM-SURVEY.md`
(literal-language rules from `IMAGE-BLAST.md`, the pixel-box contract, scale anchors:
doors 2.0–2.1 m, counters 0.9 m, seats 0.45 m, ceilings 2.4–3.0 m, switch plates 1.2 m).
`room-recipe` carries `RECIPE-DSL.md` and the archetype table. Hooks: `SessionStart` runs
`room_gen probe` and lists worlds and staged input (no key checks); `UserPromptSubmit` lists
`input/`. `settings.json` allow-list: `Skill(room-*)`, `Bash(room_gen *)`,
`Bash(uv run room_gen *)`, `Bash(ls *)`, `Bash(mkdir *)`. Images are Read only in
`room-survey`, `room-boxes`, `room-qc`.

### 11.3 Order of operations (one-shot)

1. `room-project --stage-input`; 2. `room_gen auto` (always first, model-free);
3. `Agent(room-survey)` and `Agent(room-boxes)` in parallel, background, to fill what auto
left low-confidence or empty; 4. `objects`, `build`, `assemble`, `fit`; 5.
`Agent(room-qc)` ≤ 2 rounds; 6. report paths, confidences, which tier produced each block.
A user with no model runs steps 2 and 4 and, if needed, `annotate` instead of 3 and 5.

## 12. Quality bar and tests (Spec)

- **Unit (host pytest):** vision modules on synthetic images (rendered checkerboard rooms
  from the eval set and generated line images): LSD recovers known lines within 1 px, VP
  and focal recovery within 3 % and rotation within 1°, homography round-trip, grabcut
  mask → contact line on synthetic boxes; archetype expand at min/default/max params yields
  ≤ 64 parts and the declared bbox; pydantic models accept fixtures and reject documented
  bad cases; coords; EXIF reader on sample headers; merge-patch; Blender discovery with
  fake filesystems.
- **Blender integration:** every fixture room and recipe builds and exports (`FINISHED`),
  face caps, previews non-uniform, GLB re-import object counts, render-from-camera round-trip,
  annotator `annotations.json` ↔ headless equivalence.
- **Annotator (vitest):** reducers, coordinate mapping, schema-typed API client.
- **Synthetic round-trip benchmark (`tests/eval/`), model-free and CI-able:** build
  fixture rooms with known dimensions and furniture, render "photos" from known cameras
  (several heights, focal lengths, clutter on/off), run `auto` and `auto` + fixture
  annotations, and score focal error, camera-height error, floor-polygon IoU,
  ceiling-height error, opening count/position error, object position/size error, and
  `fit` residual before/after. `REPORT.md` is regenerated by the test and is the yardstick
  for every algorithm change, and for Haiku vs Sonnet when a person runs the Claude tier.
- **CI:** GitHub Actions: `uv sync`, pytest; download the Blender LTS tarball and run the
  Blender tests; `npm ci && npm test` for the annotator.
- **Acceptance (end of M5):** one real interior photo → `N-room.blend` + GLB + overlay +
  preview with no model and no network via `auto`, `build`, `fit`, `export` in under 3
  minutes on this host, the overlay visibly aligned to the walls; the same photo → the same
  files via Claude Code with at most one confirmation.

## 13. Milestones (Spec) — model-free first

- **M0 scaffold:** `pyproject.toml` + `uv`, package skeleton, pydantic models → schemas,
  `probe`, `project`, `validate`, config, hooks, `settings.json`, CI, unit tests green.
- **M1 bridge:** import a real image-blaster world → `N-room.blend` + exports.
- **M2 build core:** shell, openings, DSL, archetypes, materials, lighting, camera,
  placement, exporters, previews, assemble; fixture-driven.
- **M3 vision and calibration:** `imageio`, `exif`, `lines`, `calib` (auto + manual),
  `layout`, `objects` (grabcut), `light`, `auto`; benchmark v1 with hand-written
  annotation fixtures.
- **M3b local models:** `room_gen[ml]` with depth, detection, segmentation; `models`
  command; benchmark reports with and without models.
- **M4 annotator:** the web annotator end to end (port of image-blaster's `app/`);
  equivalence test.
- **M5 textures and fit:** rectified textures with inpainting,
  analytic wireframe fit with scipy, overlays; benchmark v2.
- **M6 Claude autofill:** skills, agents, hooks per §11; one-shot flow; Haiku vs Sonnet
  benchmark run; README quickstart for Pro/Max users and for model-free users.
- **M7 polish:** USD/WEBP when available, plan labels, Blender edit-in-place add-on,
  drop-in instructions for image-blaster checkouts, optional captioning model.

## 14. Non-goals

Gaussian splats, NeRFs, photogrammetry; learned models in the required path; models
beyond the §8.12 desktop budget; any hosted inference; audio;
image editing or clean plates; an Anthropic-API mode; non-Manhattan or multi-room
reconstruction in v1 (curved walls become polyline approximations, low confidence).

## 15. Rules for Claude sessions in this repo (apply now)

- **Git:** read-only git is fine. Do not commit, branch, push, tag or amend unless the user
  explicitly asks in that message. `deps/image-blaster` is a submodule; never edit inside it.
- **No code until the user asks to start M0.** Until then, changes are limited to this file
  and docs.
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

- "Claude Mac plan" in the original request is read as the Claude **Max** plan; the spec
  also covers Claude Code inside the Claude desktop app on macOS.
- **Local models (§8.12)** were approved by the user on 2026-10-04 for anything that runs
  on typical desktop/laptop CPU and GPU resources. The Depth Anything V2 metric-indoor Small
  card carries no licence field; the Apache-2.0 status rests on the upstream repository's
  statement that all Small checkpoints are Apache-2.0.
- Single-photo scale is ±15–25 % without a reference; `reference`, `known_lengths`, the
  EXIF focal prior, and `fit` are the mitigations.
- Auto layout assumes a Manhattan box room; the benchmark will show how often that holds.
- Whether Haiku writes acceptable boxes/archetypes is unproven; the benchmark decides.
- Node 18 on this host is below the Node 20 LTS the annotator docs will recommend; Vite 5
  still runs on 18, so this is a docs note, not a blocker.
- USD and WEBP availability vary by Blender build; both are optional outputs gated by
  `probe`. Cycles GPU availability is irrelevant to v1 (EEVEE/Workbench only).
