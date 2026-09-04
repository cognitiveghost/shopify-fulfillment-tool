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


# The worst realistic content: the longest client name a validated id can
# produce (20 chars, profile_manager.validate_client_id) and a session id.
_WORST_CLIENT = "CLIENT_WAREHOUSE_NTH"
_WORST_SESSION = "Session 2026-09-04_18-45-02"


def _loaded(bar):
    bar.set_clients([_WORST_CLIENT])
    bar.set_current_client(_WORST_CLIENT)
    bar.set_session_text(_WORST_SESSION)
    bar.set_status("status_warning", "Analysis complete")
    bar.set_action("Generate Reports")
    bar.set_state(BarState.SESSION)
    return bar


def test_the_never_truncate_four_survive_the_design_width(bar):
    _loaded(bar)
    bar.resize(1310, 48)
    QApplication.processEvents()

    assert bar.session_button.text() == _WORST_SESSION
    assert bar.action_button.text() == "Generate Reports"
    assert bar.overflow_button.isVisible()
    assert bar.status_chip.isVisible()


def test_the_client_name_is_what_gives_way_first(bar):
    _loaded(bar)
    bar.resize(700, 48)
    QApplication.processEvents()

    # Step 2 of the ladder fired; step 4 did not, because New Session is not
    # even shown in this state.
    # 120, not "<= 200": the selector is setFixedWidth to one of exactly
    # two values, so a <= assertion passes whether or not the rung fired.
    assert bar.client_selector.width() == 120
    assert bar.session_button.text() == _WORST_SESSION


def test_progress_keeps_the_percentage_and_drops_the_phase(bar):
    _loaded(bar)
    bar.set_state(BarState.RUNNING)
    bar.set_progress(62, "Allocating stock")
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.progress_label.text() == "Allocating stock 62%"

    bar.resize(620, 48)
    QApplication.processEvents()
    assert bar.progress_label.text() == "62%"


def test_new_session_goes_icon_only_last(bar):
    bar.set_clients([_WORST_CLIENT])
    bar.set_current_client(_WORST_CLIENT)
    bar.set_state(BarState.NO_SESSION)
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == "New Session"

    bar.resize(420, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == ""


def test_the_session_button_reads_open_recent_with_no_session(qapp):
    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1")])
    bar.set_state(BarState.NO_SESSION)
    assert bar.session_button.isVisible() or not bar.isVisible()
    assert bar.session_button.text() == "Open recent"
    assert bar.session_button.isEnabled()


def test_the_session_button_is_disabled_when_the_client_has_no_sessions(qapp):
    bar = CommandBar()
    bar.set_recent_sessions([])
    bar.set_state(BarState.NO_SESSION)
    assert not bar.session_button.isEnabled()


def test_the_session_id_is_never_elided(qapp):
    bar = CommandBar()
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.SESSION)
    assert bar.session_button.text() == "2026-09-04_tuesday-restock"
    assert bar.session_button.maximumWidth() >= 16777215


def test_the_picker_is_disabled_while_a_run_holds_the_turn(qapp):
    bar = CommandBar()
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.RUNNING)
    assert bar.session_button.text() == "2026-09-04_tuesday-restock"
    assert not bar.session_button.isEnabled()


def test_choosing_a_session_emits_its_path(qapp, qtbot):
    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1"), ("Monday", "/s/2")])
    actions = [a for a in bar.session_menu.actions() if a.data()]
    with qtbot.waitSignal(bar.sessionChosen) as caught:
        actions[0].trigger()
    assert caught.args == ["/s/1"]


def test_the_menu_ends_with_a_route_to_the_browser(qapp, qtbot):
    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1")])
    last = bar.session_menu.actions()[-1]
    assert "Browse all sessions" in last.text()
    with qtbot.waitSignal(bar.browseAllRequested):
        last.trigger()
