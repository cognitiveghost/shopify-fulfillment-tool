"""The command bar's four states: exactly one primary, and it moves."""

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from gui.components.commandbar import BarState, CommandBar


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    widget.resize(1310, 48)
    # isVisible() reflects the whole ancestor chain, not just a widget's own
    # setVisible() flag -- an unshown top-level always reports False.
    widget.show()
    yield widget
    widget.deleteLater()


def test_no_client_has_no_primary_anywhere(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.NO_CLIENT)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()


def test_no_session_puts_the_primary_beside_the_selector(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.NO_SESSION)
    assert bar.new_session_button.isVisible()
    # The screen still has a bound button; the state says there is no
    # right-hand primary yet, and the state wins.
    assert not bar.action_button.isVisible()


def test_session_puts_the_screens_own_button_on_the_right(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.SESSION)
    assert bar.action_button.isVisible()
    assert bar.action_button.text() == "Run Analysis"
    assert not bar.new_session_button.isVisible()


def test_session_with_no_bound_button_still_has_no_primary(bar):
    bar.bind_action(None)
    bar.set_state(BarState.SESSION)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()


def test_running_has_no_primary_and_cancel_takes_the_danger_role(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.RUNNING)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()
    assert bar.cancel_button.isVisible()
    assert bar.cancel_button.property("role") == "danger"


def test_binding_after_the_state_is_set_still_resolves(bar):
    # Order must not matter: ui_manager sets the state on a connection change
    # and binds on a screen change, and neither knows which ran last.
    bar.set_state(BarState.SESSION)
    bar.bind_action(QPushButton("Generate Reports"))
    assert bar.action_button.isVisible()
    assert bar.action_button.text() == "Generate Reports"


def test_open_folder_appears_only_once_a_session_exists(bar):
    bar.set_state(BarState.NO_SESSION)
    assert not bar.open_folder_button.isVisible()
    bar.set_state(BarState.SESSION)
    assert bar.open_folder_button.isVisible()


def test_the_bar_is_the_height_every_later_screen_assumes(bar):
    assert bar.height() == 48
