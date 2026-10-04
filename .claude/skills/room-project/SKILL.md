---
name: room-project
description: Create or inspect a room world under worlds/<slug>, staging photos from input/. Use first, or whenever the user asks what state a room is in.
argument-hint: [world-slug or description] [optional instructions]
allowed-tools: Read Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
---

Create or inspect project `$0`.

1. Pick a slug: `$0` if it looks like one, else a short lowercase-hyphen slug from `$ARGUMENTS`.
2. Run (add `--stage-input` when `input/` has photos or the user asked to use them):

```bash
uv run room_gen project --world "<slug>" --stage-input
```

3. Report: slug, source image count and primary image, which of image.json /
   annotations.json / calibration.json / room.json exist, latest world and room build
   indexes, objects with built models.
4. Next step: no photo → ask the user to drop one in `input/`; photo but no room.json →
   `/room-auto <slug>`; room.json but no build → `Agent(room-build)`.
