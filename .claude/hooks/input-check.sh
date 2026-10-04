#!/bin/bash
# UserPromptSubmit: list photos waiting in input/.
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || cd "$(dirname "$0")/../.."
FILES=$(ls input/ 2>/dev/null | grep -v -E '^\.|^$' | tr '\n' ' ')
[ -n "$FILES" ] && echo "Staged in input/: $FILES"
exit 0
