#!/usr/bin/env bash
# Creates .venv (if missing) and installs runtime + dev deps for running the test suite.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -f .venv/bin/python ]; then
    python3 -m venv .venv
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt

.venv/bin/python -c "import pytest" && echo "venv ready: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest"
