import pytest

from shared.icons import icon
from shared.navrail import RAIL_WIDTH, NavRail


def test_rail_is_the_spec_width(qapp):
    rail = NavRail()
    assert rail.width() == RAIL_WIDTH == 56


def test_add_item_returns_sequential_indices(qapp):
    rail = NavRail()
    assert rail.add_item(icon("package"), "Orders") == 0
    assert rail.add_item(icon("settings"), "Settings") == 1


def test_first_item_added_becomes_current(qapp):
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    assert rail.current_index() == 0


def test_set_current_emits_currentChanged_once(qapp):
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    rail.add_item(icon("settings"), "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.set_current(1)
    assert seen == [1]


def test_set_current_to_the_active_index_emits_nothing(qapp):
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    rail.add_item(icon("settings"), "Settings")
    rail.set_current(1)
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.set_current(1)
    assert seen == []


def test_clicking_an_item_emits_its_index(qapp):
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    rail.add_item(icon("settings"), "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.button(1).click()
    assert seen == [1]


def test_set_current_rejects_an_out_of_range_index(qapp):
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    with pytest.raises(IndexError):
        rail.set_current(3)


def test_an_unknown_icon_name_fails_at_add_time(qapp):
    with pytest.raises(KeyError):
        icon("no-such-glyph")


def test_clicking_the_current_item_again_emits_nothing(qapp):
    """The path self._current exists for: Qt has already flipped the group's
    checked state by the time clicked() runs, so checkedId() cannot see this."""
    rail = NavRail()
    rail.add_item(icon("package"), "Orders")
    rail.add_item(icon("settings"), "Settings")
    seen = []
    rail.currentChanged.connect(seen.append)
    rail.button(1).click()
    rail.button(1).click()
    assert seen == [1]


def test_a_theme_toggle_restyles_the_rail(qapp):
    """A widget sheet outranks the app's, so a rail that bakes its colours in
    once stays light over dark pages."""
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    rail = NavRail()
    before = rail.styleSheet()
    manager.toggle_theme()
    try:
        assert rail.styleSheet() != before
    finally:
        manager.toggle_theme()


def test_the_manager_seeds_shared_theme_at_construction(qapp):
    """Shared widgets read shared.theme.current_tokens(), so the manager must
    record the live theme when it is built, not at the first apply_theme():
    anything constructed in between would paint the unseeded fallback while
    the manager reports the saved theme."""
    import shared.theme as shared_theme
    from gui import theme_manager as tm

    saved_instance, saved_current = tm.ThemeManager._instance, shared_theme._current
    tm.ThemeManager._instance = None
    shared_theme._current = None
    try:
        manager = tm.ThemeManager()
        assert shared_theme.current_theme_name() == manager.get_current_theme_name()
    finally:
        tm.ThemeManager._instance = saved_instance
        shared_theme._current = saved_current
