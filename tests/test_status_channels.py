"""The status roles the shared chip resolves (shared/theme.py).

The session row's eight states are pinned in tests/test_browse_state.py: the
Browse page draws them as a badge with a dot (phase 4 spec section 4.2), and
the Qt delegate with its STATE_STYLES table is gone.
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, status_style


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_a_role_with_no_bg_partner_falls_back_to_surface_sunken(theme):
    # text_secondary has no _bg partner. Force live=True, or the one tolerated
    # missing token in the theme goes untested.
    assert status_style("text_secondary", theme, live=True).fill == theme.surface_sunken
