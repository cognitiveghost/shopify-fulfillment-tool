#!/usr/bin/env bash
# Creates .venv (if missing) and installs runtime + dev deps for running the test suite.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt -r requirements-dev.txt

.venv/bin/python -c "import pytest" && echo "venv ready: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest"
