---
name: room-bridge
description: Import one image-blaster world into Blender and export it.
tools: Read, Glob, Bash
model: haiku
background: true
skills:
  - room-bridge
---

Do exactly the task of the preloaded `room-bridge` skill for the world (and object) named in the
prompt. If the world or a required argument is missing or ambiguous, stop and report the
blocker. Use the CLI through `uv run room_gen ...`; never call Blender directly. Write
`provenance.by = "model"` on everything you author and never alter `human` items. Finish
with a short report: files written, what changed, confidences, open questions.
