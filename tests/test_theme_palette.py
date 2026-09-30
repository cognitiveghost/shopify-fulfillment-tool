"""Phase 1 palette: the mockup's values, fitted to the contrast floors.

Spec docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md
section 3; ADR 0018 says why four of them are darker than the mockup.
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, build_stylesheet, validate_theme

PALETTE = {
    "surface_sunken": ("#F1F1F1", "#0F1012"),
    "surface": ("#FFFFFF", "#1A1B1E"),
    "surface_raised": ("#F7F7F7", "#232428"),
    "surface_overlay": ("#FFFFFF", "#2A2B30"),
    "text": ("#303030", "#E3E3E3"),
    "text_secondary": ("#616161", "#A3A3A8"),
    "text_disabled": ("#888888", "#767676"),
    "text_placeholder": ("#6C6C6C", "#949494"),
    "border": ("#888888", "#767676"),
    "border_subtle": ("#E3E3E3", "#34353A"),
    "border_strong": ("#888888", "#767676"),
    "status_info": ("#00527C", "#7CC4F8"),
    "status_info_bg": ("#E0F0FF", "#0B2A40"),
    "status_success": ("#0C5132", "#6ED3A0"),
    "status_success_bg": ("#CDFEE1", "#0E3222"),
    "status_warning": ("#5E4200", "#F5C451"),
    "status_warning_bg": ("#FFEF9D", "#3A2C05"),
    "status_danger": ("#8E0B21", "#FF9A9A"),
    "status_danger_bg": ("#FEE9E8", "#43141A"),
    "accent_fill": ("#303030", "#E3E3E3"),
    "accent_fill_hover": ("#1A1A1A", "#FFFFFF"),
    "accent_fill_active": ("#000000", "#C4C4C8"),
    "on_accent": ("#FFFFFF", "#1A1B1E"),
    "selection_border": ("#005BD3", "#4A9CFF"),
    "selection_bg": ("#EAF4FF", "#12243B"),
    "focus_ring": ("#005BD3", "#4A9CFF"),
    "hover": ("#F7F7F7", "#232428"),
    # New in phase 1 (spec section 3.2).
    "status_success_dot": ("#29845A", "#6ED3A0"),
    "status_danger_dot": ("#E51C00", "#FF9A9A"),
    "status_danger_border": ("#FDB5B4", "#6B2029"),
    "control_disabled_bg": ("#F1F1F1", "#141518"),
}

THEMES = pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])


@pytest.mark.parametrize("token", sorted(PALETTE))
def test_the_palette_is_the_mockups_fitted_to_the_floors(token):
    light, dark = PALETTE[token]
    assert getattr(LIGHT_THEME, token) == light
    assert getattr(DARK_THEME, token) == dark


@THEMES
def test_both_themes_still_validate(theme):
    validate_theme(theme)


@THEMES
@pytest.mark.parametrize(
    "selector", ["QPushButton:disabled {", 'QPushButton[role="danger"]:disabled {']
)
def test_a_disabled_button_drops_its_fill_and_dashes_its_edge(qapp, theme, selector):
    """Audit A6: a disabled button used to differ only by a lighter label."""
    block = build_stylesheet(theme).split(selector, 1)[1].split("}", 1)[0]
    assert f"background-color: {theme.control_disabled_bg};" in block
    assert f"border: 1px dashed {theme.border_strong};" in block
    assert f"color: {theme.text_disabled};" in block
