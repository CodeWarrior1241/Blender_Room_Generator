---
name: room-export
description: Re-export the latest room to other formats (glb, fbx, obj, usd when Blender supports it).
argument-hint: [world-slug] [formats]
allowed-tools: Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
---

```bash
uv run room_gen export --world "$0" --formats "${1:-glb,fbx,obj}"
```

Report the written files (`files.*`) and any `failed_outputs` (USD is missing on some
Blender builds; say so plainly).
