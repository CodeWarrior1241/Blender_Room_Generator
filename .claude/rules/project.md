# Blender Room Generator — working rules for Claude

You turn a photo of a room into an editable Blender scene. The deterministic tools in
`room_gen` do every metric, geometric and file operation; you only supply semantic facts
(what objects are, where they are in the image, which archetype fits, literal prose) and
judge results. No API keys, no hosted models: everything runs locally.

## How to run things

- Run the CLI as `uv run room_gen <command>` (or `.venv/bin/room_gen`). Every command prints
  one JSON report. Never call `blender` directly.
- Key commands: `project --world <slug> --stage-input`, `auto --world <slug> [--ml on|off]`,
  `grid --world <slug>`, `validate --annotations|--room|--recipe <file>`, `build --world <slug>`,
  `export --world <slug> --formats glb,fbx,obj`, `bridge --world <path>`, `archetypes list`,
  `archetypes resolve "<label>"`, `patch --room <file> --ops <merge-patch.json>`, `inspect <file>`.

## Files (per world: `worlds/<slug>/`)

```
source/0-<photo>.jpg      the input photo (index 0)
annotations.json          pixel facts: objects (boxes), openings (quads), floor corners, calibration hints
calibration.json          camera intrinsics, rotation, height (written by auto)
room.json                 room spec in metres: shell, materials, lighting, camera, placements
image.json                literal scene description (image-blaster's IMAGE-BLAST schema)
output/<object>/recipe.json  object archetype + params (+ generated parts)
output/<object>/object.json  identity/provenance (image-blaster)
output/world/N-world*.*    builds: shell .glb/.blend, furnished N-world-room.blend/.glb, previews, plan
output/world/overlay.png  photo with the reconstruction drawn on it (yellow shell, cyan openings, magenta objects)
output/world/grid.png     photo with a labelled native-pixel grid (from `room_gen grid`)
```

## Provenance — the rule that keeps tools and people in charge

Every block you write carries `"provenance": {"by": "model", "tool": "<skill name>", "confidence": 0..1}`.
`auto` regenerates only `auto`/`fit` blocks; `human` and `model` blocks are kept. Never
overwrite a `human` block. If a person edited something in the annotator, ask before changing it.

## Images

Read an image into context only when visual analysis is the task (`room-survey`,
`room-boxes`, `room-qc`). Prefer `output/world/grid.png` for reading pixel positions, and
always write coordinates in native pixels (the grid labels are native). Report generated
images by path; do not open previews just to check that they exist.

## Order of operations (one-shot)

1. `/room-project` with `--stage-input`.
2. `/room-auto` (always first; model-free, uses local models when installed).
3. If auto reports low confidence or missing objects: `Agent(room-survey)` and/or
   `Agent(room-boxes)` in the background, then `/room-auto` again so the tools refit.
4. `Agent(room-build)`.
5. `Agent(room-qc)`: at most 2 rounds of fixes.
6. Report the .blend/.glb paths, the overlay and preview paths, and which tier produced each block.

Generation-type work (survey, boxes, recipe, build, qc) runs through `Agent(...)` with
`run_in_background: true`; the CLI commands themselves are synchronous — never background them.

## Style

Literal and concrete. Say what was measured and how confident the tools are. Do not invent
dimensions: if a number matters and the photo cannot give it, ask the user for one known length.
