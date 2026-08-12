"""The type scale is the single source of truth for font sizing in gui/*.py.

Two of these tests are guards rather than unit tests:
test_body_role_matches_shared_button_size catches shared/theme.py drifting
under us (it is sync-owned by packing-tool), and
test_no_hardcoded_font_sizes_outside_theme_manager stops future call sites
from bypassing the scale.
"""
import re
from pathlib import Path

import pytest
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QListWidgetItem

from gui.theme_manager import TYPE_SCALE, apply_font, font_css
from shared.theme import build_stylesheet, get_theme


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_scale_has_exactly_the_five_documented_roles():
    assert set(TYPE_SCALE) == {"caption", "body", "label", "heading", "display"}


@pytest.mark.parametrize("role,size_pt,bold", [
    ("caption", 9, False),
    ("body", 10, False),
    ("label", 12, True),
    ("heading", 14, True),
    ("display", 17, True),
])
def test_roles_resolve_to_expected_size_and_weight(role, size_pt, bold):
    assert TYPE_SCALE[role].size_pt == size_pt
    assert TYPE_SCALE[role].bold is bold


def test_font_css_emits_size_and_explicit_weight():
    assert font_css("caption") == "font-size: 9pt; font-weight: normal;"
    assert font_css("label") == "font-size: 12pt; font-weight: bold;"


def test_font_css_bold_override_wins_in_both_directions():
    assert font_css("caption", bold=True) == "font-size: 9pt; font-weight: bold;"
    assert font_css("label", bold=False) == "font-size: 12pt; font-weight: normal;"


def test_unknown_role_raises_rather_than_falling_back():
    with pytest.raises(KeyError):
        font_css("subheading")


def test_apply_font_sets_size_and_weight_on_a_widget():
    label = QLabel("x")
    apply_font(label, "heading")
    assert label.font().pointSize() == 14
    assert label.font().bold() is True


def test_apply_font_preserves_the_existing_family():
    label = QLabel("x")
    font = label.font()
    font.setFamily("Courier New")
    label.setFont(font)
    apply_font(label, "caption")
    assert label.font().family() == "Courier New"
    assert label.font().pointSize() == 9


def test_apply_font_works_on_a_list_item_and_a_painter():
    item = QListWidgetItem("x")
    apply_font(item, "caption", bold=True)
    assert item.font().pointSize() == 9
    assert item.font().bold() is True

    pixmap = QPixmap(10, 10)
    painter = QPainter(pixmap)
    try:
        apply_font(painter, "display")
        assert painter.font().pointSize() == 17
        assert painter.font().bold() is True
    finally:
        painter.end()


def test_body_role_matches_shared_button_size():
    """shared/theme.py is synced from packing-tool and can change without
    warning. If its QPushButton size stops matching the body role, buttons
    silently fall off the scale -- fail loudly instead."""
    sheet = build_stylesheet(get_theme("light"))
    match = re.search(r"QPushButton\s*\{[^}]*font-size:\s*(\d+)pt", sheet)
    assert match, "shared/theme.py no longer sets a pt font-size on QPushButton"
    assert int(match.group(1)) == TYPE_SCALE["body"].size_pt


GUI_DIR = Path(__file__).resolve().parent.parent / "gui"


def test_no_hardcoded_font_sizes_outside_theme_manager():
    """The scale is only worth having if it cannot be bypassed. A new dialog
    that hardcodes a size turns this red instead of quietly drifting."""
    offenders = []
    for path in sorted(GUI_DIR.rglob("*.py")):
        if path.name == "theme_manager.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "font-size:" in line or "setPointSize" in line or "setPixelSize" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use theme_manager.font_css()/apply_font() instead of hardcoding sizes:\n"
        + "\n".join(offenders)
    )
