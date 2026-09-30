"""The three status channels resolve in one place, for both renderers.

Spec: shopify-fulfillment-tool
docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §3.2
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, status_style

ROLES = [
    "status_info", "status_success", "status_warning",
    "status_danger", "text_secondary",
]


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize("role", ROLES)
def test_four_combinations_are_four_distinguishable_renderings(theme, role):
    seen = {
        status_style(role, theme, live=live, manual=manual)
        for live in (True, False)
        for manual in (True, False)
    }
    assert len(seen) == 4


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_resting_has_no_fill_and_live_has_the_roles_tint(theme):
    live = status_style("status_warning", theme, live=True)
    resting = status_style("status_warning", theme, live=False)
    assert live.fill == theme.status_warning_bg
    assert resting.fill is None
    assert live.fg == resting.fg == theme.status_warning


def test_mark_is_solid_for_a_person_and_hollow_for_the_system():
    assert status_style("status_info", LIGHT_THEME, manual=True).mark_filled
    assert not status_style("status_info", LIGHT_THEME, manual=False).mark_filled


def test_a_role_with_no_bg_partner_falls_back_to_surface_sunken():
    # text_secondary is the "Not Started" / "Archived" role and has no _bg.
    style = status_style("text_secondary", DARK_THEME, live=True)
    assert style.fill == DARK_THEME.surface_sunken


def test_a_typo_in_the_role_raises_where_it_is_written():
    with pytest.raises(AttributeError):
        status_style("status_sucess", LIGHT_THEME)
