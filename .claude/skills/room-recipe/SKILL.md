---
name: room-recipe
description: Adjust one object's archetype, parameters or materials in output/<object>/recipe.json when the fitted model looks wrong (wrong type, wrong style, wrong colours). One object per invocation.
argument-hint: [world-slug] [object-id] [what is wrong]
allowed-tools: Read Write Glob Bash(uv run room_gen *) Bash(.venv/bin/room_gen *) Bash(ls *)
context: fork
agent: room-recipe
---

Fix the recipe of object `$1` in world `$0`. Read `RECIPE-DSL.md` in this skill directory.

1. Read `worlds/$0/output/$1/recipe.json` and `uv run room_gen archetypes show <archetype>`.
2. Change only what is wrong: `archetype` (pick from `archetypes list`), style params
   (e.g. `cushions`, `arms`, `doors`, `shelves`, `style`), material colours per slot.
   Do not change `width`/`depth`/`height` unless the user gave sizes: the tools measured them.
3. Set `provenance.archetype_by`/`params_by`/`colors_by` to `"model"` for what you changed,
   and delete `parts` so the archetype is expanded again.
4. `uv run room_gen validate --recipe worlds/$0/output/$1/recipe.json`; fix until ok.
5. Report the change. The main session rebuilds.
