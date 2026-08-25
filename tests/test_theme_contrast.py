"""shared/theme.py is synced from packing-tool and can change without warning.

Its unit tests live there. What this repo needs is proof that whatever
arrived still satisfies the design-system contract, because a broken sync
would otherwise surface as unreadable badges on a warehouse screen rather
than as a red test. Same guard role as
test_type_scale.py::test_body_role_matches_shared_button_size.
"""
import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, contrast_ratio, validate_theme


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
