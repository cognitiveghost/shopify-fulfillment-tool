"""9.3: one silhouette, and live-ness rides with the role.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §3
"""

import pytest

from gui.session_row_delegates import STATUS_ROLES
from shared.theme import DARK_THEME, LIGHT_THEME, status_style


def test_every_shopify_status_names_a_role_and_its_liveness():
    assert STATUS_ROLES == {
        "active": ("status_info", True),
        "completed": ("status_success", False),
        "abandoned": ("status_danger", False),
        "archived": ("text_secondary", False),
    }


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize("status", sorted(STATUS_ROLES))
def test_every_status_resolves_in_both_themes(theme, status):
    role, live = STATUS_ROLES[status]
    style = status_style(role, theme, live=live)
    assert style.fg
    assert (style.fill is not None) is live


def test_the_delegate_no_longer_chooses_between_two_silhouettes():
    from gui import session_row_delegates

    assert not hasattr(session_row_delegates.SessionStatusDelegate, "form")
    assert not hasattr(session_row_delegates, "chip_colors")
