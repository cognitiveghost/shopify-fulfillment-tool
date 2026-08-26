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

from gui.theme_manager import (
    DEFAULT_DENSITY,
    DENSITY_PROFILES,
    TYPE_SCALE,
    apply_font,
    font_css,
    get_density,
    get_density_profile,
    set_density,
    type_style,
)
from shared.theme import build_stylesheet, get_theme


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_scale_has_exactly_the_six_documented_roles():
    assert set(TYPE_SCALE) == {
        "caption", "body", "label", "heading", "display", "display_xl",
    }


@pytest.mark.parametrize("role,size_pt,bold", [
    ("caption", 9, False),
    ("body", 10, False),
    ("label", 12, True),
    ("heading", 14, True),
    ("display", 17, True),
    ("display_xl", 28, True),
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


@pytest.fixture(autouse=True)
def reset_density():
    """Density is module-global state. A test that switches it must not leak
    into the next one, and the whole file assumes the desk baseline."""
    set_density(DEFAULT_DENSITY)
    yield
    set_density(DEFAULT_DENSITY)


def test_exactly_two_profiles_and_desk_is_the_default():
    assert set(DENSITY_PROFILES) == {"desk", "floor"}
    assert DEFAULT_DENSITY == "desk"
    assert get_density() == "desk"


@pytest.mark.parametrize("name,control,row,pad_v,pad_h", [
    ("desk", 32, 28, 4, 8),
    ("floor", 44, 40, 8, 12),
])
def test_profile_metrics_match_the_spec_table(name, control, row, pad_v, pad_h):
    profile = DENSITY_PROFILES[name]
    assert profile.control_height == control
    assert profile.row_height == row
    assert profile.padding_v == pad_v
    assert profile.padding_h == pad_h


def test_profile_padding_is_the_shared_spacing_scale():
    """Spec C3 names spacing tokens, not raw pixels. shared/theme.py is
    sync-owned by packing-tool, so if its spacing scale moves under us these
    profiles silently stop meaning what the spec says."""
    theme = get_theme("light")
    assert DENSITY_PROFILES["desk"].padding_v == theme.spacing_xs
    assert DENSITY_PROFILES["desk"].padding_h == theme.spacing_sm
    assert DENSITY_PROFILES["floor"].padding_v == theme.spacing_sm
    assert DENSITY_PROFILES["floor"].padding_h == theme.spacing_md


def test_desk_is_the_identity_profile():
    """TYPE_SCALE is the desk baseline, so desk overrides nothing."""
    assert DENSITY_PROFILES["desk"].type_overrides == {}


def test_floor_overrides_body_and_caption_and_nothing_else():
    """Spec C3 overrides Parcker's 'density never changes type size' in exactly
    one place. A third key here would be silent drift, which is the thing the
    spec explicitly said it did not want."""
    assert DENSITY_PROFILES["floor"].type_overrides == {"body": 12, "caption": 10}


@pytest.mark.parametrize("name,expected", [("desk", 22), ("floor", 26)])
def test_control_content_height_backs_out_padding_and_border(name, expected):
    assert DENSITY_PROFILES[name].control_content_height == expected


def test_set_density_switches_and_get_density_reports_it():
    set_density("floor")
    assert get_density() == "floor"
    assert get_density_profile() is DENSITY_PROFILES["floor"]


def test_unknown_density_raises_rather_than_falling_back():
    with pytest.raises(KeyError):
        set_density("comfortable")
    assert get_density() == "desk"


def test_type_style_is_the_baseline_at_desk():
    for role, style in TYPE_SCALE.items():
        assert type_style(role).size_pt == style.size_pt
        assert type_style(role).bold is style.bold


def test_floor_raises_body_and_caption():
    set_density("floor")
    assert type_style("body").size_pt == 12
    assert type_style("caption").size_pt == 10


def test_floor_leaves_every_other_rung_alone():
    set_density("floor")
    for role in ("label", "heading", "display", "display_xl"):
        assert type_style(role).size_pt == TYPE_SCALE[role].size_pt


def test_floor_never_changes_weight():
    set_density("floor")
    for role in TYPE_SCALE:
        assert type_style(role).bold is TYPE_SCALE[role].bold


def test_font_css_follows_the_density():
    assert font_css("body") == "font-size: 10pt; font-weight: normal;"
    set_density("floor")
    assert font_css("body") == "font-size: 12pt; font-weight: normal;"


def test_apply_font_follows_the_density():
    label = QLabel("x")
    set_density("floor")
    apply_font(label, "caption")
    assert label.font().pointSize() == 10


def test_type_style_rejects_an_unknown_role():
    with pytest.raises(KeyError):
        type_style("subheading")
