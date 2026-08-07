#!/usr/bin/env bash
# Runs the test suite against THIS worktree's .venv, ignoring whatever
# python/pytest is on PATH (avoids picking up the main repo's .venv).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -x .venv/bin/python ]; then
    echo "No .venv here — run scripts/setup_venv.sh first." >&2
    exit 1
fi

QT_QPA_PLATFORM=offscreen exec .venv/bin/python -m pytest "$@"
