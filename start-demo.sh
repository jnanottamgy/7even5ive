#!/usr/bin/env bash
# 7even5ive demo on macOS/Linux: every server the phone needs, in this one terminal.
set -euo pipefail
cd "$(dirname "$0")/core"
PY=$(command -v python3 || command -v python)
[ -x .venv/bin/python ] || "$PY" -m venv .venv
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install -q -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
mkdir -p data
exec .venv/bin/python -m seventy5.serve_all
