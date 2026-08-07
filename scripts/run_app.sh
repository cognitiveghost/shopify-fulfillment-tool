#!/usr/bin/env bash
# Runs the app via this worktree's own .venv, bypassing whatever "python" is on PATH.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python gui_main.py "$@"
