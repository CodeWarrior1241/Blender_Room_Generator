---
name: room-qc
description: Compare the reconstruction with the photo (overlay and preview) and fix what is visibly wrong through annotations or a room.json merge patch. Use after a build; at most two rounds.
argument-hint: [world-slug] [round 1|2]
allowed-tools: Read Write Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-qc
---

Quality-check world `$0`.

1. Read `worlds/$0/output/world/overlay.png` (photo + reconstruction drawn on it) and the
   latest `worlds/$0/output/world/<N>-world-room-preview.png` (N from `room_gen project`).
2. List concrete discrepancies only: a wall line off the real wall/floor boundary, a missing
   or misplaced door/window, an object box not on the object, wrong archetype, a missing
   object, a clearly wrong colour.
3. Fix each at the right level:
   - geometry of the room or objects → annotations (floor_corners, openings, object boxes,
     reference) with `provenance.by = "model"`, then `uv run room_gen auto --world "$0"`;
   - type/style/colour of one object → edit its recipe like `room-recipe`;
   - lighting, exposure or a material → a JSON merge patch file applied with
     `uv run room_gen patch --room worlds/$0/room.json --ops <patch.json>`, setting the
     patched block's `provenance.by` to "model".
4. `uv run room_gen build --world "$0"` and report before/after paths. Stop after round 2 and
   list what remains for the user.
