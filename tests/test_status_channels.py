"""9.19: the fourth channel -- shape names the state, eight of them.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle6-session-browser-design.md §5
"""

import pytest

from gui.session_row_delegates import STATE_STYLES
from shared.theme import DARK_THEME, LIGHT_THEME, SHAPES, status_style
from shopify_tool.session_lifecycle import DISPLAY_STATUSES


def test_every_display_status_has_a_style():
    assert tuple(STATE_STYLES) == DISPLAY_STATUSES


def test_the_table_is_exactly_the_spec_table():
    assert STATE_STYLES == {
        "not_started": ("text_secondary", False, "ring"),
        "in_progress": ("status_info", True, "half"),
        "paused": ("status_warning", True, "pause"),
        "stale": ("status_warning", True, "clock"),
        "completed": ("status_success", False, "check"),
        "incomplete": ("status_warning", True, "bang"),
        "abandoned": ("status_danger", False, "slash"),
        "archived": ("text_secondary", False, "tray"),
    }


@pytest.mark.parametrize("state", DISPLAY_STATUSES)
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_every_role_resolves_in_both_themes(state, theme):
    role, live, _shape = STATE_STYLES[state]
    style = status_style(role, theme, live=live)
    assert style.fg
    assert (style.fill is not None) is live


@pytest.mark.parametrize("state", DISPLAY_STATUSES)
def test_every_shape_is_one_shared_knows(state):
    assert STATE_STYLES[state][2] in SHAPES


def test_the_two_hard_pairs_differ_on_more_than_hue():
    # Active vs Completed: the common terminal state recedes.
    assert STATE_STYLES["in_progress"][1] is True
    assert STATE_STYLES["completed"][1] is False
    # Incomplete vs Abandoned: different role, different shape, and only one
    # of them is still live.
    assert STATE_STYLES["incomplete"][0] != STATE_STYLES["abandoned"][0]
    assert STATE_STYLES["incomplete"][2] != STATE_STYLES["abandoned"][2]
    assert STATE_STYLES["incomplete"][1] != STATE_STYLES["abandoned"][1]


def test_no_two_states_share_a_shape():
    shapes = [shape for _role, _live, shape in STATE_STYLES.values()]
    assert len(set(shapes)) == len(shapes)


def test_role_manual_is_gone():
    # Shape carries the state; authorship is constant per state and rides in
    # the table above. status_manually_set keeps its real job of stopping
    # session_lifecycle, and is no longer drawn.
    import gui.session_row_delegates as delegates

    assert not hasattr(delegates, "ROLE_MANUAL")
