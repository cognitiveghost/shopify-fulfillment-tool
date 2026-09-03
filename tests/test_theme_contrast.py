"""shared/theme.py is synced from packing-tool and can change without warning.

Its unit tests live there. What this repo needs is proof that whatever
arrived still satisfies the design-system contract, because a broken sync
would otherwise surface as unreadable badges on a warehouse screen rather
than as a red test. Same guard role as
test_type_scale.py::test_body_role_matches_shared_button_size.
"""
import pytest

from shared.theme import (
    _MIN_CONTRAST_ON_PLANES,
    _SURFACE_PLANES,
    DARK_THEME,
    LIGHT_THEME,
    contrast_ratio,
    validate_theme,
)


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_synced_theme_satisfies_the_design_system_contract(theme):
    validate_theme(theme)


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_accent_blue_is_still_the_fill_that_carries_white_text(theme):
    """gui/*.py and shared/theme.py paint white on accent_blue. If a future
    sync re-points it at status_info, every primary button and selected row
    drops below AA -- silently, because nothing else checks this pairing.
    """
    assert theme.accent_blue == theme.accent_fill
    assert contrast_ratio(theme.on_accent, theme.accent_blue) >= 4.5


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("fill", ["accent_fill", "accent_fill_hover", "accent_fill_active"])
def test_white_still_clears_aa_on_every_button_fill(theme, fill):
    """spec 7 test 2. gui/*.py paints white on the accent fill and Qt swaps
    the hover and pressed fills in behind the same label. A sync that
    re-pointed any of the three would drop a primary button below AA
    silently -- 2.90:1 is exactly what shipped before 8.1."""
    assert contrast_ratio(theme.on_accent, getattr(theme, fill)) >= 4.5


def test_the_sync_brought_the_fourth_plane_with_it():
    """spec 7 test 1. surface_sunken has no call site in this repo until 8.6,
    so nothing else here would notice if a sync dropped it -- and the
    four-plane contrast sweep inside validate_theme silently narrows back to
    three when it goes."""
    assert len(_SURFACE_PLANES) == 4
    assert "surface_sunken" in _SURFACE_PLANES
    for theme in (LIGHT_THEME, DARK_THEME):
        assert theme.surface_sunken != theme.surface


def test_the_hover_aliases_carry_an_aa_safe_fill():
    """Two gui/*.py files still read button_hover_light/dark by name
    (theme_manager, report_selection_dialog -- frozen until 8.3).
    Whatever they resolve to has to carry white text, because that is
    what QPushButton paints on them."""
    for theme in (LIGHT_THEME, DARK_THEME):
        assert contrast_ratio(theme.on_accent, theme.button_hover_light) >= 4.5
        assert contrast_ratio(theme.on_accent, theme.button_hover_dark) >= 4.5


def test_the_tokens_gui_reads_by_name_all_still_exist():
    """Phase 8.2 is additive; 8.3 is what migrates call sites. If any of
    these vanished, ~180 reads in gui/*.py would start raising AttributeError
    at paint time rather than failing here.
    """
    legacy = (
        "background", "background_elevated", "text", "text_secondary",
        "text_disabled", "text_placeholder", "border", "border_subtle",
        "hover", "active_background", "active_border", "button_hover_light",
        "button_hover_dark", "accent_blue", "accent_green", "accent_orange",
        "accent_red", "radius",
    )
    for field in legacy:
        assert hasattr(LIGHT_THEME, field), field
        assert hasattr(DARK_THEME, field), field


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_no_foreground_sits_within_a_tenth_of_its_floor(theme):
    """9.1's completion criterion. A sync that re-tightened a token would
    otherwise surface as an unreadable badge on a warehouse screen."""
    for token, floor in _MIN_CONTRAST_ON_PLANES.items():
        for plane in _SURFACE_PLANES:
            ratio = contrast_ratio(getattr(theme, token), getattr(theme, plane))
            assert ratio >= floor + 0.1, f"{theme.name}.{token} on {plane}: {ratio:.2f}"
