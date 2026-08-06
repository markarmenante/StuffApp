#!/bin/bash
set -euo pipefail

# Web sessions only — local dev manages its own .venv (see README).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Same layout the README prescribes for local dev. A venv sidesteps the
# container's debian-managed site-packages, which pip can't upgrade.
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
