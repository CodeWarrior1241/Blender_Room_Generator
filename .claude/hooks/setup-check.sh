#!/bin/bash
# SessionStart: stdout is added to Claude's context. No API keys are ever needed here.
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/../.."

if [ -x .venv/bin/room_gen ]; then
  RG=".venv/bin/room_gen"
elif command -v uv >/dev/null 2>&1; then
  RG="uv run --quiet room_gen"
else
  echo "room_gen is not installed. Tell the user to run: uv sync   (or: python3 -m venv .venv && .venv/bin/pip install -e .)"
  exit 0
fi

PROBE=$($RG probe 2>/dev/null)
if [ -z "$PROBE" ]; then
  echo "room_gen probe failed; run '$RG probe' to see why."
  exit 0
fi
python3 - "$PROBE" "$RG" <<'PY'
import json, sys
p = json.loads(sys.argv[1]); rg = sys.argv[2]
b = p.get("blender") or {}
if b.get("path"):
    caps = b.get("capabilities") or {}
    usd = "yes" if caps.get("usd") else "no"
    print(f"Blender {b.get('version')} at {b['path']} (USD export: {usd}).")
else:
    print("Blender not found. Tell the user to install Blender 4.0+ from https://www.blender.org/download/ (or set ROOM_GEN_BLENDER).")
ml = p.get("ml") or {}
if ml.get("installed"):
    cached = all(m.get("cached") for m in (ml.get("models") or {}).values())
    print(f"Local vision models: installed on {ml.get('device')}" + ("" if cached else f"; weights not cached yet (run: {rg} models download)") + ".")
else:
    print("Local vision models: not installed (optional; uv sync --extra ml). The model-free pipeline still works.")
print("Annotator: " + ("built" if p.get("annotator_built") else "not built (cd annotator && npm install && npm run build)") + ".")
worlds = p.get("worlds") or []
print(f"Worlds: {', '.join(worlds)}" if worlds else "No worlds yet. Put a room photo in input/ and use /room-project.")
if p.get("staged_input"):
    print("Staged in input/: " + " ".join(p["staged_input"]))
print(f"Run the CLI as: {rg} <command>")
PY
exit 0
