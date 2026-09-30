"""The rail owns selection state and emits an index. It knows nothing about
tabs, stacks or pages -- main_window connects it to whatever it drives.
"""
import pytest
from PySide6.QtGui import QIcon

from shared import theme as shared_theme
from shared.navrail import RAIL_WIDTH, NavRail
from shared.theme import THEME_DARK, THEME_LIGHT, current_tokens, set_current


@pytest.fixture(autouse=True)
def _restore_applied_theme():
    """The theme test below ends on dark. Here the suite's reset fixture only
    resets ThemeManager, so a stale shared.theme._current would make a later
    set_theme('dark') a no-op that never notifies listeners."""
    before = shared_theme._current
    yield
    shared_theme._current = before


@pytest.fixture
def rail(qapp):
    widget = NavRail()
    yield widget
    widget.deleteLater()


def test_the_default_width_is_the_depot_56(rail):
    assert RAIL_WIDTH == 56
    assert rail.width() == RAIL_WIDTH


def test_the_width_is_a_constructor_argument(qapp):
    """packing-tool passes 76: every one of its labels elides at 56."""
    wide = NavRail(width=76)
    try:
        assert wide.width() == 76
        index = wide.add_item(QIcon(), "Statistics")
        assert wide.button(index).width() == 76
    finally:
        wide.deleteLater()


def test_the_first_item_added_is_checked(rail):
    index = rail.add_item(QIcon(), "Packing")
    assert index == 0
    assert rail.button(0).isChecked()
    assert rail.current_index() == 0


def test_set_current_emits_once_per_real_change(rail):
    rail.add_item(QIcon(), "Packing")
    rail.add_item(QIcon(), "Statistics")
    seen = []
    rail.currentChanged.connect(seen.append)

    rail.set_current(1)
    rail.set_current(1)          # re-selecting the live page is not a change
    assert seen == [1]
    assert rail.button(1).isChecked()


def test_set_current_rejects_an_index_that_has_no_item(rail):
    rail.add_item(QIcon(), "Packing")
    with pytest.raises(IndexError):
        rail.set_current(3)


def test_the_rail_repaints_on_a_theme_change(rail):
    """The regression the missing signal would have caused: a widget sheet
    outranks the app's, so a rail styled once stays light over dark pages."""
    set_current(THEME_DARK)
    dark_plane = current_tokens().surface_sunken
    assert dark_plane in rail.styleSheet()

    set_current(THEME_LIGHT)
    try:
        light_plane = current_tokens().surface_sunken
        assert light_plane in rail.styleSheet()
        assert dark_plane not in rail.styleSheet()
    finally:
        set_current(THEME_DARK)
