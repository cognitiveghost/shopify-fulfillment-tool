"""scripts/setup_venv.sh refuses a Python older than 3.12 (AUDIT-08-T1).

numpy>=2.5.3 needs Python 3.12 or newer, so an older interpreter that can
make a venv still can't install requirements.txt.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_a_python_older_than_3_12_is_refused(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "setup_venv.sh", repo / "scripts")
    old = tmp_path / "python3"
    old.write_text('#!/bin/sh\n[ "$1" = -c ] && exit 1\nexit 0\n')
    old.chmod(0o755)
    run = subprocess.run(
        ["bash", str(repo / "scripts" / "setup_venv.sh")], capture_output=True, text=True, timeout=120, check=False,
        env={**os.environ, "SETUP_VENV_PYTHONS": str(old), "PIP_NO_INDEX": "1"}, cwd=repo,
    )
    assert run.returncode == 1
    assert "No Python 3.12 or newer on this machine can create a venv with pip." in run.stderr
    assert str(old) in run.stderr
    assert not (repo / ".venv").exists()
