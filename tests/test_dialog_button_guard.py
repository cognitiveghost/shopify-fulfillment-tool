"""A guard, not a unit test.

Qt's QDialogButtonBox places commit buttons per platform (on Windows: grouped
bottom-right) and wires Esc->reject / Enter->default for free. Without this
guard the next dialog someone adds hand-rolls its own addStretch() + QPushButton
footer and the convention decays one widget at a time -- the same failure mode
tests/test_icon_usage_guard.py exists to prevent for iconography.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = REPO_ROOT / "gui"

_FOOTER_WIRE = re.compile(r"clicked\.connect\(\s*self\.(accept|reject)\s*\)")


def _dialog_files():
    return [p for p in sorted(GUI_DIR.rglob("*.py")) if "QDialog)" in p.read_text(encoding="utf-8")]


def test_no_dialog_hand_rolls_its_footer_buttons():
    offenders = []
    for path in _dialog_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _FOOTER_WIRE.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use QDialogButtonBox for dialog footers instead of wiring a QPushButton "
        "straight to accept/reject:\n" + "\n".join(offenders)
    )


def test_the_guard_scans_a_nonempty_set_of_dialogs():
    """A scan that finds no files to check passes vacuously forever."""
    assert len(_dialog_files()) >= 6


def test_the_guard_regex_matches_the_pattern_it_polices():
    """And a regex that matches nothing does too. These are the exact lines
    this task removed."""
    assert _FOOTER_WIRE.search("        close_btn.clicked.connect(self.accept)")
    assert _FOOTER_WIRE.search("        cancel_btn.clicked.connect(self.reject)")
    assert _FOOTER_WIRE.search("self.close_btn.clicked.connect( self.accept )")
    assert not _FOOTER_WIRE.search("self.panel.config_applied.connect(self._on_panel_applied)")
    assert not _FOOTER_WIRE.search("box.rejected.connect(self.accept)")
