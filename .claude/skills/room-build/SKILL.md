---
name: room-build
description: Build the room in Blender (shell, objects, lights, camera), export .blend/.glb (and fbx/obj on request) and render previews. Use after room-auto, or after any edit to room.json or a recipe.
argument-hint: [world-slug] [--formats glb,fbx,obj] [--force]
allowed-tools: Read Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-build
---

Build world `$0`.

```bash
uv run room_gen build --world "$0"                # --formats glb,fbx,obj  --force
```

Report from the JSON (do not open images): status (built / up-to-date), index, seconds,
`files.room_blend`, `files.room_glb`, `files.room_preview`, `files.room_plan`, `files.blend`
(empty shell), per-object faces and dimensions, `warnings`, `failed_outputs`. If it fails,
quote the error and the last lines of `log_tail`, then stop.
