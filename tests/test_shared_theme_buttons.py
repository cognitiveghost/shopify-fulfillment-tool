"""The four-role button hierarchy lives in shared/, so both apps get one copy."""
import pytest
from conftest import _rule_block
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QCheckBox, QPushButton, QRadioButton

from shared.theme import (
    BUTTON_ROLES,
    DARK_THEME,
    LIGHT_THEME,
    build_stylesheet,
    set_button_role,
)


def test_the_four_roles_are_the_contract():
    assert BUTTON_ROLES == ("primary", "secondary", "ghost", "danger")


@pytest.mark.parametrize("theme", [DARK_THEME, LIGHT_THEME])
@pytest.mark.parametrize("role", ["primary", "secondary", "ghost", "danger"])
def test_build_stylesheet_emits_every_role_block(theme, role):
    assert f'QPushButton[role="{role}"]' in build_stylesheet(theme)


def test_the_unmarked_button_rule_is_secondary():
    # 2026-08-29: the default flipped from accent-filled to secondary -- primary
    # is now something a screen declares, not what every unmarked button gets.
    sheet = build_stylesheet(DARK_THEME)
    plain = sheet.split('QPushButton[role=')[0]
    assert DARK_THEME.accent_fill not in plain


def test_danger_is_an_outline_not_a_fill():
    sheet = build_stylesheet(DARK_THEME)
    block = sheet.split('QPushButton[role="danger"] {')[1].split('}')[0]
    assert "transparent" in block
    assert DARK_THEME.status_danger in block


def test_ghost_has_no_border():
    sheet = build_stylesheet(DARK_THEME)
    block = sheet.split('QPushButton[role="ghost"] {')[1].split('}')[0]
    assert "border: none" in block


def test_set_button_role_marks_the_widget(qapp):
    button = QPushButton("Start Packing")
    set_button_role(button, "primary")
    assert button.property("role") == "primary"


def test_set_button_role_rejects_an_unknown_role(qapp):
    button = QPushButton("Cancel")
    with pytest.raises(ValueError):
        set_button_role(button, "tertiary")


def _default_button_block(sheet: str) -> str:
    """The body of the bare `QPushButton {` rule.

    `QPushButton[role="primary"] {` and `QPushButton:hover {` do not match the
    split token, so this finds the unqualified selector and only that one.
    """
    return sheet.split("QPushButton {", 1)[1].split("}", 1)[0]


def test_an_unmarked_button_is_not_primary():
    """The whole point: primary is declared, never defaulted into."""
    for theme in (DARK_THEME, LIGHT_THEME):
        block = _default_button_block(build_stylesheet(theme))
        assert theme.surface_raised in block
        assert theme.accent_fill not in block


def test_marking_a_button_primary_still_fills_it_with_the_accent():
    for theme in (DARK_THEME, LIGHT_THEME):
        sheet = build_stylesheet(theme)
        primary = sheet.split('QPushButton[role="primary"] {', 1)[1].split("}", 1)[0]
        assert theme.accent_fill in primary


def test_a_button_grows_with_its_density_rung():
    """build_stylesheet hardcoded font-size: 10pt, so a floor-density button
    stayed at the desk size."""
    from shared.theme import set_density

    try:
        set_density("floor")
        assert "font-size: 12pt" in _rule_block(build_stylesheet(LIGHT_THEME), "QPushButton")
    finally:
        set_density("desk")


def test_primary_focuses_against_its_own_fill():
    """A focus_ring border on an accent fill is invisible. One exception,
    written down once."""
    sheet = build_stylesheet(LIGHT_THEME)
    primary_focus = _rule_block(sheet, 'QPushButton[role="primary"]:focus')
    assert f"2px solid {LIGHT_THEME.border_strong}" in primary_focus
    assert LIGHT_THEME.focus_ring not in primary_focus


def test_the_spin_box_is_specified_as_it_renders():
    """Qt adds room for the up/down buttons after min-height applies, so a
    'desk' spin box comes out 35px, not 32."""
    from shared.theme import get_density_profile

    profile = get_density_profile()
    assert profile.control_height + 3 == 35


def _render(widget) -> QImage:
    """One control, styled by the real sheet, drawn offscreen."""
    widget.setStyleSheet(build_stylesheet(LIGHT_THEME))
    widget.resize(widget.sizeHint())
    widget.show()
    image = widget.grab().toImage()
    widget.hide()
    return image


def test_the_toggle_indicator_is_the_drawn_size(qapp):
    """Rendered, not asserted against the QSS text. QSS resolves equal
    specificity by source order but only per property, so without an explicit
    border the toggle keeps QCheckBox::indicator's 2px frame and comes out
    24px tall -- which a substring test on its own rule cannot see."""
    toggle = QCheckBox()
    toggle.setProperty("role", "toggle")
    assert _render(toggle).height() == 20


def test_a_checked_box_draws_a_tick(qapp):
    """spec 5.2: the tick is the vendored `check` glyph. Without the image
    declaration the indicator is a solid accent_fill square with no mark, and
    only pixels show that."""
    box = QCheckBox()
    box.setChecked(True)
    image = _render(box)
    tick = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).lightness() > 160
    )
    assert tick > 10, f"only {tick} light pixels on the accent fill"


def test_checking_a_radio_does_not_resize_it(qapp):
    """width/height are the *content* box in QSS, so a thicker border on
    :checked grows the control and shifts the row it sits in."""
    radio = QRadioButton()
    unchecked = _render(radio).size()
    radio.setChecked(True)
    assert _render(radio).size() == unchecked
