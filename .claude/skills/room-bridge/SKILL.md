---
name: room-bridge
description: Import an existing image-blaster world (World Labs collider, object GLBs, scene.json placements and sun) into Blender and export it. Use when the user has worlds made by image-blaster.
argument-hint: [path to image-blaster worlds/<slug>] [optional output slug]
allowed-tools: Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-bridge
---

```bash
uv run room_gen bridge --world "$0" --formats glb,fbx
```

Report the `.blend` and export paths, the number of instances placed, the collider transform
used (flip_y, scale, offset), and every warning (missing model files are common when an
image-blaster object never finished generating).
