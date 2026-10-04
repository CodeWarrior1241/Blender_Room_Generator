---
name: room-auto
description: Run the model-free reconstruction (lines, calibration, layout, objects, lighting, photo textures; local vision models when installed) and judge whether Claude needs to help. Use after room-project and after any annotation change.
argument-hint: [world-slug] [--ml on|off]
allowed-tools: Read Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
---

Run the deterministic pipeline for `$0` and decide what is missing.

```bash
uv run room_gen auto --world "$0"            # add --ml off to force the lines-only path
```

The JSON report has: calibration (focal, hfov, confidence, finite vanishing points), scale
(camera height and its source), shell (size, ceiling, visible walls, openings, confidence),
fit (wireframe residual before/after), objects (archetype, size, position, confidence),
textures (coverage per surface), notes, overlay path, seconds.

Decide, and say why in one line each:
- `scale.source` is "assumed eye height" and no objects were found → ask the user for one
  known length (door height, window width), or run `Agent(room-survey)` to find a reference.
- `shell.confidence` < 0.5, or fewer than 2 visible walls, or ceiling assumed → `Agent(room-survey)`.
- `objects` empty or obviously incomplete versus what the user described → `Agent(room-boxes)`.
- otherwise → `Agent(room-build)`.

After a survey or boxes agent finishes, run `room_gen auto` again: the tools refit using the
new annotations. Do not Read the overlay yourself here; `room-qc` does that after a build.
