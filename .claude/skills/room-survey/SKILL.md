---
name: room-survey
description: Look at the room photo and write the semantic facts the tools cannot see reliably — floor corners, doors and windows, a reference length, ceiling height when evident — plus the literal image.json description. Use when auto reports low shell or scale confidence.
argument-hint: [world-slug] [optional notes from the user]
allowed-tools: Read Write Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-survey
---

Survey world `$0`. Read `ROOM-SURVEY.md` in this skill directory first and follow it exactly.

1. `uv run room_gen grid --world "$0"` and Read the printed `grid_image` (labels are native pixels).
   Also Read `worlds/$0/output/world/overlay.png` if it exists: yellow is the current shell,
   cyan the openings, magenta the objects.
2. Read `worlds/$0/annotations.json` (create it from `uv run room_gen auto --world "$0" --no-textures`
   first if missing). Keep every existing item whose provenance is `human`.
3. Add or correct, with `provenance: {"by": "model", "tool": "room-survey", "confidence": c}`:
   floor_corners, boundary_lines (traced wall/floor, wall/ceiling and corner lines), openings (quads),
   calibration.reference or known_lengths, ceiling_height_m
   only when a strong cue exists. Write the file, then
   `uv run room_gen validate --annotations worlds/$0/annotations.json` and fix errors.
4. Write `worlds/$0/image.json` (literal description, IMAGE-BLAST schema in ROOM-SURVEY.md).
5. Report what you added, with confidences, and what you could not determine.
