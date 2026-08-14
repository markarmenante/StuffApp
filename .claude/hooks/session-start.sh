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

# Same layout the README prescribes for local dev. A venv sidesteps the
# container's debian-managed site-packages, which pip can't upgrade.
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt

# Pre-fetch the rembg background-removal model (~176MB) that the
# note-trim suite needs, in the background so session start isn't
# blocked — otherwise the first test run stalls ~70s downloading it.
if [ ! -s "$HOME/.u2net/u2net.onnx" ]; then
  mkdir -p "$HOME/.u2net"
  ( curl -fsSL -o "$HOME/.u2net/u2net.onnx.part" \
      "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx" \
    && mv "$HOME/.u2net/u2net.onnx.part" "$HOME/.u2net/u2net.onnx" ) \
    >/dev/null 2>&1 &
fi

# CLAUDE_ENV_FILE only exists when the harness provides one.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
