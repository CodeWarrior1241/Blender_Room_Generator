# Recipe DSL

A recipe has two levels. The archetype level is what you edit:

```json
{"schema_version": 1, "object": "sofa", "archetype": "sofa",
 "params": {"width": 2.1, "depth": 0.92, "height": 0.85, "cushions": 3, "arms": true},
 "materials": {"upholstery": {"base_color": "#5f6f7a", "roughness": 0.9, "procedural": "fabric"},
               "legs": {"base_color": "#4e3626"}},
 "provenance": {"archetype_by": "model", "params_by": "auto", "colors_by": "model"}}
```

`room_gen` expands it into `parts` (boxes, cylinders, cones, spheres, tori, planes, prisms,
lathes, tubes with position/rotation/scale/mirror/array/bevel/material), origin at the bottom
centre, front facing -Y. Material fields: base_color (#rrggbb), roughness, metallic,
emission, emission_strength, alpha, transmission, procedural (wood | tile | fabric | noise |
brick), scale (metres per texture tile). Slot names come from `archetypes show <name>`.

Hand-written parts are allowed (set `provenance.parts_by` to "model" so they are kept) but
prefer archetypes: they are validated, sized and fast. Limits: 64 parts, 50 000 faces.
