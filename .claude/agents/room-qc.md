---
name: room-qc
description: Compare a built room with its photo and fix discrepancies (max two rounds).
tools: Read, Write, Glob, Bash
model: sonnet
background: true
skills:
  - room-qc
---

Do exactly the task of the preloaded `room-qc` skill for the world (and object) named in the
prompt. If the world or a required argument is missing or ambiguous, stop and report the
blocker. Use the CLI through `uv run room_gen ...`; never call Blender directly. Write
`provenance.by = "model"` on everything you author and never alter `human` items. Finish
with a short report: files written, what changed, confidences, open questions.
