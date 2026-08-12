#!/usr/bin/env bash
# One command to make a fresh clone OR a fresh worktree runnable from VS Code.
#
# Provides .venv (shared from the main checkout when we're in a worktree) and
# writes the gitignored .vscode/ config so F5 runs the app and the test
# explorer finds pytest. Safe to re-run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"

have_deps() { [ -x "$1/bin/python" ] && "$1/bin/python" -c "import PySide6, pytest" >/dev/null 2>&1; }

# --- 1. .venv ---------------------------------------------------------------
# A venv is ~400MB with PySide6 and every branch installs the same
# requirements.txt, so worktrees share the main checkout's venv by symlink
# instead of each downloading their own.
# ponytail: shared venv — a branch that adds a dependency installs it for every
# worktree too. Give this worktree its own with: rm .venv && python3 -m venv .venv
MAIN=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo)
MAIN=${MAIN%/.git}

if have_deps "$REPO/.venv"; then
    echo "venv: already good"
elif [ -n "$MAIN" ] && [ "$MAIN" != "$REPO" ] && have_deps "$MAIN/.venv"; then
    rm -rf "$REPO/.venv"
    ln -s "$MAIN/.venv" "$REPO/.venv"
    echo "venv: linked -> $MAIN/.venv"
else
    # Bare `python3` is NOT safe to trust here. On this machine
    # /usr/local/bin/python3 shadows the system one and its ensurepip fails, so
    # `python3 -m venv` leaves a directory behind with no pip in it — which is
    # exactly what made this script fail before. Probe for one that works.
    PY=""
    for c in /usr/bin/python3 python3 python3.14 python3.13 python3.12; do
        p=$(command -v "$c" 2>/dev/null) || continue
        probe=$(mktemp -d)
        if "$p" -m venv "$probe" >/dev/null 2>&1 && "$probe/bin/python" -m pip --version >/dev/null 2>&1; then
            rm -rf "$probe"; PY="$p"; break
        fi
        rm -rf "$probe"
    done
    if [ -z "$PY" ]; then
        echo "No python3 on this machine can create a venv with pip." >&2
        echo "Tried: /usr/bin/python3 python3 python3.14 python3.13 python3.12" >&2
        echo "On Debian/Ubuntu: sudo apt install python3-venv" >&2
        exit 1
    fi
    echo "venv: creating with $PY ($("$PY" -V))"
    rm -rf "$REPO/.venv"
    "$PY" -m venv "$REPO/.venv"
    "$REPO/.venv/bin/python" -m pip install -q --upgrade pip
    "$REPO/.venv/bin/python" -m pip install -q -r requirements.txt -r requirements-dev.txt
fi

have_deps "$REPO/.venv" || { echo "venv still missing PySide6/pytest — see errors above." >&2; exit 1; }

# --- 2. .vscode/ ------------------------------------------------------------
# Gitignored, so it does not exist in a fresh worktree and generating it here
# never dirties git status.
mkdir -p "$REPO/.vscode"
cat > "$REPO/.vscode/settings.json" <<'EOF'
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.unittestEnabled": false,
    "python.testing.pytestArgs": ["tests"],
    "python.envFile": "${workspaceFolder}/.vscode/.env"
}
EOF
# Qt needs a display for the app but must not have one for the test suite;
# VS Code's test runner reads this envFile, launch.json sets its own.
printf 'QT_QPA_PLATFORM=offscreen\n' > "$REPO/.vscode/.env"
cat > "$REPO/.vscode/launch.json" <<'EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run app (local dev-server)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/run_dev.py",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "env": {"QT_QPA_PLATFORM": ""}
        },
        {
            "name": "Run app (production server)",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/gui_main.py",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "env": {"QT_QPA_PLATFORM": ""}
        }
    ]
}
EOF

echo "vscode: .vscode/{settings,launch}.json written"
echo
echo "Ready. In VS Code: open $REPO, F5 -> 'Run app (local dev-server)'."
echo "Tests: scripts/run_tests.sh   (or the Testing panel)"
