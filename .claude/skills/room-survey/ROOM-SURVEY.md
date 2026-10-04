# ROOM-SURVEY contract

You are giving the geometry tools pixel facts. They compute every metre themselves; your
job is to point at things precisely and say what they are. Coordinates are native pixels
`[u, v]`, origin top-left, read off the grid image (its labels are native pixels).

## What to write into annotations.json

- `floor_corners`: pixels where two walls meet the floor, left to right, only where the
  corner itself is visible (not occluded, not outside the frame). 0-3 points is normal.
- `boundary_lines[]`: `{kind: wall_floor | wall_ceiling | wall_wall, pixels: [[u,v], ...], provenance}`.
  Trace the VISIBLE stretches of room boundaries as polylines (2+ points each, follow the line
  exactly; one entry per straight stretch). `wall_floor` = where a wall meets the floor (top of
  the floor, bottom of the baseboard), `wall_ceiling` = where a wall meets the ceiling,
  `wall_wall` = a vertical corner line between two walls (top to bottom). Use these whenever
  a corner's foot is hidden: a few accurate boundary stretches are the strongest geometry you
  can give. Do not trace furniture edges, curtain hems, rugs or picture frames.
- `openings[]`: `{kind: door|window|opening, quad: [[u,v] x4], wall_hint: left|right|back|front, label}`.
  Quad = the inner edge of the frame, clockwise from top-left. Doors reach the floor.
  wall_hint is relative to the camera: the wall you look at is `back`.
- `calibration.reference`: one vertical object of known height standing on the floor,
  bottom pixel first: `{kind: vertical, pixels: [[u_bottom, v_bottom], [u_top, v_top]], metres, label}`.
  Anchors (use the most standard visible one): interior door leaf 2.03 m (2.00-2.10),
  kitchen counter top 0.90 m, dining table top 0.75 m, desk top 0.74 m, chair seat 0.45 m,
  sofa seat 0.42 m, light switch centre 1.20 m, standard brick course 0.075 m.
- `known_lengths[]`: two floor pixels and their distance, only if the user told you a length
  or a standard floor item gives it (e.g. a 60 cm floor tile).
- `ceiling_height_m`: only with a strong cue (user statement, visible full-height door + ceiling).
- Never remove or move items with `provenance.by == "human"`.

## image.json (image-blaster flat schema; literal language only)

```json
{"schema_version": 1, "world": "<slug>", "source_images": ["source/0-....jpg"],
 "scene_name": "...", "short_caption": "about 10 words", "literal_description": "...",
 "environment": "...", "visual_style": "...", "lighting": "...", "atmosphere": "...",
 "ambient_sound": "...", "objects": [{"id": "sofa", "name": "sofa", "description": "...",
 "materials": ["grey fabric"], "source_images": ["source/0-....jpg"], "evidence": [{"image": "...", "location_in_image": "..."}],
 "generate_as_3d_object": true}]}
```

Rules: describe like a technical survey; no "feels like", "suggests", narrative or mood words;
only what is visible; single liftable items as objects (no rugs-with-tables compounds); object
ids must match annotation object ids where both exist.
