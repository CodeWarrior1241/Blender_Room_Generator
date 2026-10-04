# Blender_Room_Generator

Blender_Room_Generator turns a photo of a room into an editable, exportable Blender scene using deterministic Python and Blender tools, with Claude as an optional helper, so that no paid 3D-generation API is needed.

It extends [image-blaster](https://github.com/neilsonnn/image-blaster), which is vendored as a submodule in `deps/image-blaster`. Its worlds use the same folder layout, so either tool can read the other's output. Where image-blaster calls World Labs and FAL for the room and its objects, this project reconstructs both from the photo:

1. **Classical computer vision.** OpenCV and scipy find line segments and vanishing points, calibrate the camera, and fit a box-shaped room to the evidence. Furniture is then fitted from 2-D boxes, using parametric archetypes for sofas, beds, tables and so on.
2. **Optional small local vision models.** These run on your own CPU or GPU and never call a hosted service: metric depth, open-vocabulary detection and box-prompted segmentation.
3. **A person or Claude can correct it.** The local web annotator, or Claude Code skills on a Claude Pro/Max subscription, edit one file of pixel facts (`annotations.json`). The tools refit from it. No API key is involved anywhere.

The output is a Blender scene with the room shell, doors and windows, photo-textured walls and floor, and furniture. It also includes lights and the estimated photo camera. Everything exports to `.blend`, GLB, FBX and OBJ.

## Requirements

- Blender 4.0 or newer. It is found on `PATH`, at the platform default location, or via `ROOM_GEN_BLENDER`.
- Python 3.10+ and [uv](https://docs.astral.sh/uv/). `pip install -e .` also works.
- Optional:
  - NVIDIA CUDA or Apple MPS for the local models. CPU works too, just slower.
  - Node 18+ for the annotator.

## Install

```bash
git clone --recurse-submodules https://github.com/CodeWarrior1241/Blender_Room_Generator
cd Blender_Room_Generator
uv sync --extra dev                  # core + tests
uv sync --extra dev --extra ml       # + local models (PyTorch, transformers), optional
uv run room_gen models download      # one-time, about 1.05 GB of weights, optional
(cd annotator && npm install && npm run build)   # web annotator, optional
uv run room_gen probe                # shows what was found
```

## Quick start without any model

```bash
cp ~/Pictures/living-room.jpg input/
uv run room_gen project --world living --stage-input
uv run room_gen auto --world living --ml off --build
```

Look at `worlds/living/output/world/overlay.png`. It shows the photo with the reconstruction drawn on top: the room in yellow, openings in cyan, objects in magenta. The furnished scene is `worlds/living/output/world/0-world-room.blend` (and `.glb`).

If the overlay is off, open the annotator and add a few clicks:

```bash
uv run room_gen annotate --world living
```

These are the useful clicks, in the order they help most:
1. Floor corners.
2. A traced wall/floor line.
3. One known length, such as the door height.
4. Boxes around furniture the detector missed.

Then run `auto` again; the tools keep your edits and refit everything else.

## With the local models

`uv run room_gen auto --world living --build` (the default `--ml auto` uses the models when they are installed). Detection proposes the furniture, doors and windows, segmentation cuts them out, and metric depth gives a first scale. Standard furniture heights then correct that scale.

## With Claude Code (Pro or Max subscription, no API key)

Open the repository in Claude Code: the CLI, the VS Code extension, or the Code tab of the Claude desktop app. The session hook reports what is installed. Then ask, for example: *"put the photo in input/ through the whole pipeline and confirm each step with me"*.

The skills in `.claude/skills` run the tools first. They call on Claude only where the tools are unsure:

| Skill | Model | Job |
|---|---|---|
| `room-project`, `room-auto` | main session | run the tools, read the confidences |
| `room-survey` | Sonnet | floor corners, boundary lines, doors/windows, a reference length, literal `image.json` |
| `room-boxes` | Sonnet | labelled boxes around furniture (reads a labelled pixel-grid image) |
| `room-recipe` | Haiku | change one object's type, style or colours |
| `room-build`, `room-bridge` | Haiku | run the Blender build or the image-blaster import |
| `room-qc` | Sonnet | compare the result with the photo and fix it (two rounds at most) |

Haiku was measured too imprecise for drawing boxes, so the vision-with-coordinates jobs use Sonnet (see `tests/eval/CLAUDE_TIER.md`).

## Useful commands

```bash
uv run room_gen build --world living --formats glb,fbx,obj   # rebuild after editing room.json or a recipe
uv run room_gen grid --world living                          # photo with a labelled pixel grid
uv run room_gen archetypes list                              # 35 furniture types
uv run room_gen validate --annotations worlds/living/annotations.json
uv run room_gen bridge --world ../image-blaster/worlds/my-room   # image-blaster world -> .blend
uv run room_gen inspect worlds/living/output/world/0-world-room.glb
```

Every command prints one JSON report, which makes the tool easy to script and easy for Claude to read.

## Files

```
worlds/<slug>/source/0-photo.jpg         the photo
worlds/<slug>/annotations.json           pixel facts (tools, people and Claude all write here)
worlds/<slug>/calibration.json           camera (focal, rotation, height)
worlds/<slug>/room.json                  room in metres: walls, openings, materials, lights, camera, placements
worlds/<slug>/output/<object>/recipe.json  archetype + parameters of one object
worlds/<slug>/output/world/N-world-room.blend / .glb   the furnished scene
worlds/<slug>/output/world/N-world.blend / .glb        the empty room
worlds/<slug>/scene.json                 placements for image-blaster's viewer
```

Each block carries `provenance` (`auto`, `fit`, `human` or `model`). A re-run of `auto` replaces only `auto` and `fit` blocks.

## Quality and limits

`uv run python -m tests.eval.benchmark` renders four rooms with known geometry in Blender, runs the pipeline and writes `tests/eval/REPORT.md`. Here is what it found on the lines-only path:

- **Camera:** focal length within 0.6 % and rotation within 0.35°.
- **Room:** floor overlap 0.73–0.86 with the true room, and visible walls within 0.02–0.39 m.
- **Objects, given good boxes:** placed within 0.07–0.32 m.
- **With the local models:** camera height within 2–7 %, which is better than assuming an eye height.

Real photos are much harder. On 40 NYU Depth v2 frames with measured ground truth, about a third of the pixels get the wrong room surface, against under 1 % on the synthetic rooms. Renders of the same rooms score about the same, so the difficulty is the scenes themselves: close-up views of partly seen rooms. See `tests/realdata/REPORT.md`.

Tight close-ups, heavy clutter and curtains reaching the floor are the usual ways a photo misleads the automatic layout. A few annotator clicks or the `room-survey` skill are the fix. Without a known length, absolute scale is an estimate: give one length when it matters.

## Tests

```bash
uv run pytest tests/unit       # fast, no Blender needed
uv run pytest tests/blender    # needs Blender
uv run pytest tests/ml         # needs the ml extra and cached weights
uv run pytest tests/eval       # slow end-to-end quality gates
uv run pytest tests/realdata   # real photos with measured ground truth (needs the reference data)
(cd annotator && npm test)
```

The real-photo tests use 40 frames of NYU Depth v2 with SUN RGB-D's room-layout and object
labels. That data is licensed for research use only, so it is fetched into `deps/sunrgbd/`
and never committed (see `deps/sunrgbd/README.md`):

```bash
uv sync --extra realdata
uv run python -m tests.realdata.fetch --accept-license
uv run python -m tests.realdata.benchmark      # photo vs ground-truth twin render, tests/realdata/REPORT.md
```

## Licences

The code is MIT. The default local models are Apache-2.0: Depth Anything V2 Small (metric indoor), OWLv2 and SAM ViT-B. Their weights are downloaded to the Hugging Face cache and are not part of this repository. `CLAUDE.md` holds the full design specification.
