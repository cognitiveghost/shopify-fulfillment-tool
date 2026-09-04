"""The command-bar overflow: two scopes, one menu."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.overflow import OverflowMenu, overflow_button


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def menu(qapp):
    """Deleted after each test -- an unparented QMenu outlives the test."""
    widget = OverflowMenu()
    yield widget
    widget.deleteLater()


def test_a_section_header_is_a_disabled_action(menu):
    header = menu.add_section("THIS PC")
    assert header.text() == "THIS PC"
    # Disabled, so keyboard navigation steps over it and QSS can style it as
    # a header. addSection() would hand the drawing to Qt, which cannot carry
    # the type treatment the artboard pins.
    assert not header.isEnabled()


def test_an_item_runs_its_slot(menu):
    calls = []
    menu.add_item("Client settings…", lambda: calls.append(1)).trigger()
    assert calls == [1]


def test_a_choice_group_is_exclusive_and_starts_on_current(menu):
    picked = []
    group = menu.add_choice_group(["Light", "Dark"], "Dark", picked.append)

    checked = [a for a in group.actions() if a.isChecked()]
    assert [a.text() for a in checked] == ["Dark"]

    group.actions()[0].trigger()
    assert picked == ["Light"]
    # Exclusive: picking Light unchecks Dark without a second signal.
    assert [a.text() for a in group.actions() if a.isChecked()] == ["Light"]


def test_the_menu_is_the_width_the_artboard_specifies(menu):
    menu.add_section("THIS PC")
    menu.add_item("Server connection…", lambda: None)
    assert menu.minimumWidth() == 284


def test_the_button_opens_on_press_not_on_a_second_click(menu):
    from PySide6.QtWidgets import QToolButton

    button = overflow_button(menu)
    # InstantPopup: one press opens it. MenuButtonPopup would split the
    # button into an action half and an arrow half, and there is no action.
    assert button.popupMode() == QToolButton.InstantPopup
    assert button.menu() is menu


def test_repopulating_does_not_pile_up_action_groups(menu):
    """QMenu.clear() drops the actions but not a QActionGroup parented here.

    The menu is rebuilt on every client change, so a group left behind
    accumulates for the life of the process.
    """
    from PySide6.QtGui import QActionGroup

    for _ in range(5):
        menu.clear()
        menu.add_choice_group(["Light", "Dark"], "Light", lambda _n: None)

    assert len(menu.findChildren(QActionGroup)) == 1
