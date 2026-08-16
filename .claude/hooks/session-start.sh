#!/bin/bash
set -euo pipefail

# Web sessions only — local dev manages its own .venv (see README).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# CLAUDE_PROJECT_DIR is set by the hook harness; fall back to the repo
# root relative to this script so the hook also works run by hand.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR"

# Print Mark's standing instructions into the session's opening context
# — they must be READ FIRST, not just sit in CLAUDE.md. Prints from the
# standing-instructions heading up to the next '## ' section, so edits
# to that section flow through with no second copy to maintain.
awk '/^## /{on = ($0 ~ /^## Standing instructions/)} on' CLAUDE.md

# Same layout the README prescribes for local dev. A venv sidesteps the
# container's debian-managed site-packages, which pip can't upgrade.
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

# CLAUDE_ENV_FILE only exists when the harness provides one.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
