"""The command bar's four states (phase 3 spec section 8).

New session and Open recent are always there. The session's name is a chip
on every screen but Setup, whose page head shows it. While a run is going the
bar names the step beside a disabled "Running…".
"""

import pytest
from PySide6.QtWidgets import QApplication

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


def _analysed(bar):
    bar.set_session_text("2026-09-30_1")
    bar.set_status("text_secondary", "Analysed 14:06")
    bar.set_stock_age("Stock file 19 h old")
    bar.set_state(BarState.SESSION)
    return bar


@pytest.mark.parametrize("state", list(BarState))
def test_new_session_and_open_recent_are_always_shown(bar, state):
    bar.set_state(state)
    assert bar.new_session_button.isVisible()
    assert bar.session_button.isVisible()
    assert bar.session_button.text() == "Open recent"


@pytest.mark.parametrize(
    ("state", "usable"),
    [
        (BarState.NO_CLIENT, False),
        (BarState.NO_SESSION, True),
        (BarState.SESSION, True),
        (BarState.RUNNING, False),
    ],
)
def test_they_are_usable_with_a_client_and_no_run(bar, state, usable):
    bar.set_state(state)
    assert bar.new_session_button.isEnabled() is usable
    assert bar.session_button.isEnabled() is usable


def test_new_session_is_a_secondary_button_that_asks_for_a_session(bar, qtbot):
    bar.set_state(BarState.NO_SESSION)
    assert bar.new_session_button.property("role") == "secondary"
    assert bar.new_session_button.text() == "New session"
    assert not bar.new_session_button.icon().isNull()
    with qtbot.waitSignal(bar.newSessionRequested):
        bar.new_session_button.click()


def test_the_bar_has_no_screen_action_cancel_or_folder_button(bar):
    for name in (
        "action_button",
        "cancel_button",
        "open_folder_button",
        "status_chip",
        "stock_chip",
        "progress_label",
    ):
        assert not hasattr(bar, name), name


def test_the_chip_shows_the_session_off_setup(bar):
    _analysed(bar).set_screen(chip=True, meta=False)
    assert bar.session_chip.isVisible()
    assert bar.session_chip.text() == "2026-09-30_1"
    assert "border-radius: 6px" in bar.session_chip.styleSheet()
    assert not bar.meta_label.isVisible()


def test_setup_shows_no_chip_because_its_page_head_does(bar):
    _analysed(bar).set_screen(chip=False, meta=False)
    assert not bar.session_chip.isVisible()
    assert not bar.meta_label.isVisible()


def test_results_adds_the_analysis_age_as_text(bar):
    _analysed(bar).set_screen(chip=True, meta=True)
    assert bar.session_chip.isVisible()
    assert bar.meta_label.isVisible()
    assert bar.meta_label.text() == "analysed 14:06 · stock file 19 h old"


def test_the_meta_text_follows_what_changes_under_it(bar):
    _analysed(bar).set_screen(chip=True, meta=True)
    bar.set_stock_age("")
    assert bar.meta_label.text() == "analysed 14:06"
    bar.set_status("text_secondary", "")
    assert not bar.meta_label.isVisible()


@pytest.mark.parametrize("state", [BarState.NO_CLIENT, BarState.NO_SESSION])
def test_with_no_session_there_is_no_chip_and_no_meta(bar, state):
    bar.set_session_text("No session")
    bar.set_state(state)
    bar.set_screen(chip=True, meta=True)
    assert not bar.session_chip.isVisible()
    assert not bar.meta_label.isVisible()


def test_the_session_id_is_never_elided(bar):
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.SESSION)
    bar.set_screen(chip=True, meta=False)
    assert bar.session_chip.text() == "2026-09-04_tuesday-restock"
    assert bar.session_chip.maximumWidth() >= 16777215


def test_running_names_the_step_beside_a_disabled_running_button(bar):
    _analysed(bar).set_screen(chip=False, meta=False)
    bar.set_state(BarState.RUNNING)
    bar.set_step(1, 4, "Checking fulfilment history")
    assert bar.step_count_label.isVisible()
    assert bar.step_count_label.text() == "Step 2 of 4"
    assert bar.step_name_label.isVisible()
    assert bar.step_name_label.text() == "Checking fulfilment history"
    assert bar.running_button.isVisible()
    assert bar.running_button.text() == "Running…"
    assert bar.running_button.property("role") == "primary"
    assert not bar.running_button.isEnabled()


@pytest.mark.parametrize(
    "state", [BarState.NO_CLIENT, BarState.NO_SESSION, BarState.SESSION]
)
def test_nothing_about_a_run_shows_when_none_is_going(bar, state):
    bar.set_step(2, 4, "Allocating stock")
    bar.set_state(state)
    assert not bar.step_count_label.isVisible()
    assert not bar.step_name_label.isVisible()
    assert not bar.running_button.isVisible()


def test_the_bar_is_the_height_every_later_screen_assumes(bar):
    assert bar.height() == 48


def test_the_client_name_is_what_gives_way_first(bar):
    bar.set_clients(["CLIENT_WAREHOUSE_NTH"])
    bar.set_current_client("CLIENT_WAREHOUSE_NTH")
    _analysed(bar).set_screen(chip=True, meta=False)
    bar.resize(700, 48)
    QApplication.processEvents()
    # 120, not "<= 200": the selector is setFixedWidth to one of exactly two
    # values, so a <= assertion passes whether or not the rung fired.
    assert bar.client_selector.width() == 120
    assert bar.session_chip.text() == "2026-09-30_1"


def test_a_narrow_bar_keeps_the_step_count_and_drops_its_name(bar):
    _analysed(bar)
    bar.set_state(BarState.RUNNING)
    bar.set_step(2, 4, "Allocating stock")
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.step_name_label.isVisible()

    bar.resize(620, 48)
    QApplication.processEvents()
    assert bar.step_count_label.text() == "Step 3 of 4"
    assert not bar.step_name_label.isVisible()


def test_new_session_goes_icon_only_last(bar):
    bar.set_state(BarState.NO_SESSION)
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == "New session"

    bar.resize(420, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == ""
    assert not bar.new_session_button.icon().isNull()


def test_open_recent_is_usable_even_with_no_recent_sessions(qapp):
    """Its menu always ends with the route to the browser."""
    bar = CommandBar()
    bar.set_recent_sessions([])
    bar.set_state(BarState.NO_SESSION)
    assert bar.session_button.isEnabled()
    assert "Browse all sessions" in bar.session_menu.actions()[-1].text()


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
