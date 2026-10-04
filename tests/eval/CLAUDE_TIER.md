# Claude tier measurements (manual runs)

These runs used Claude subagents and are not part of the automated benchmark. They answer the
spec's open question of which Claude model should draw object boxes (`room-boxes`).

**Setup (2026-10-04).** The `dining` scene from `tests/eval/scenes.py` was rendered at
1200×1600. A subagent got the `room-boxes` instructions: run `room_gen grid`, read the
grid image, and write `annotations.objects` in native pixels. The pipeline then ran
`room_gen auto --ml off`, so no local models were used. Scores come from `tests/eval/benchmark.score`.

| Model | Objects boxed | Mean box IoU vs truth | Camera height err | Ceiling err | Visible wall err | Objects matched | Object position err (median) |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 | 6 of 8 | about 0.15 (boxes shifted about 120 px, undersized) | 5.5 % | 0.19 m | 0.25 m | 5/8 | 0.58 m |
| Sonnet | 8 of 8 | 0.77 | 0.9 % | 0.001 m | 0.003 m | 8/8 | 0.14 m |
| Ground-truth boxes (`annotated` mode) | 8 of 8 | 1.00 | 1.7 % | 0.08 m | 0.10 m | 8/8 | 0.06 m |

**Haiku before the robust scale estimate.** The first version applied the object-height
scale cue as a plain weighted mean. Haiku's misplaced boxes then drove a ×1.6 scale correction,
giving 45 % camera-height error and 1.7 m wall error. The robust median, outlier rejection
and cap in `room_gen/vision/scale.py` limit the damage. The Haiku row above was measured
after that fix.

**Decision.** `room-boxes` uses `sonnet`. Haiku stays on the text-only and mechanical agents:
`room-recipe`, `room-build` and `room-bridge`.
