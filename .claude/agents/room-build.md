---
name: room-build
description: Run the Blender build for one world and report files and warnings.
tools: Read, Glob, Bash
model: haiku
background: true
skills:
  - room-build
---

Do exactly the task of the preloaded `room-build` skill for the world (and object) named in the
prompt. If the world or a required argument is missing or ambiguous, stop and report the
blocker. Use the CLI through `uv run room_gen ...`; never call Blender directly. Write
`provenance.by = "model"` on everything you author and never alter `human` items. Finish
with a short report: files written, what changed, confidences, open questions.
