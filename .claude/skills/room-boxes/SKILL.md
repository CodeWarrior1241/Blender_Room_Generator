---
name: room-boxes
description: Draw labelled 2-D boxes around every piece of furniture and decor in the room photo (annotations.objects) so the tools can fit 3-D objects. Use when auto found no or too few objects.
argument-hint: [world-slug] [optional list of items the user cares about]
allowed-tools: Read Write Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-boxes
---

Box the objects in world `$0`.

1. `uv run room_gen grid --world "$0"`; Read the `grid_image` it prints. Grid labels are
   native pixel coordinates; `native_size` is the photo size.
2. `uv run room_gen archetypes list` for the vocabulary (sofa, armchair, dining_chair,
   coffee_table, bookshelf, bed, table_lamp, plant, tv, rug, ...).
3. Read `worlds/$0/annotations.json`. Keep `human` items untouched. Replace or extend `auto`
   items you can do better.
4. For each single, liftable item (not walls, floors, built-in surfaces): add
   `{"id": "<slug>", "label": "<plain name>", "archetype": "<from the list>", "box": [x0, y0, x1, y1],
   "support": "floor" | "<id of the item it stands on>" | "wall" | "ceiling",
   "materials_hint": ["..."], "provenance": {"by": "model", "tool": "room-boxes", "confidence": c}}`.
   - Box tightly around the visible item, including legs; boxes may run to the image edge.
   - Lamps on tables: support = the table's id. Pictures/curtains: support = "wall".
   - Unique ids (lowercase, hyphens, e.g. `chair-2`). Skip items smaller than ~2% of the width.
5. Write the file; run `uv run room_gen validate --annotations worlds/$0/annotations.json`; fix errors.
6. Report the boxes added (id, archetype, confidence). The main session then re-runs `room-auto`.
