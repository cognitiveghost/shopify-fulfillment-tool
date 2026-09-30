"""The 8.6 shell contract: one command bar, a rail, no global header."""

from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.components import CommandBar
from gui.components.commandbar import ROW_CLIENT


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """A real MainWindow rooted at a throwaway server path.

    Same construction tests/test_session_setup_layout.py:64 uses -- there is
    no conftest fixture for this, and copying seven lines beats making one
    test file import another.
    """
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_command_bar_replaces_the_global_header(main_window):
    assert isinstance(main_window.command_bar, CommandBar)
    # The header's widgets are gone, not merely hidden.
    assert not hasattr(main_window, "current_client_label")
    assert not hasattr(main_window, "session_folder_icon_label")
    assert not hasattr(main_window, "sidebar_toggle_btn")


def test_session_label_keeps_its_name_so_its_writer_needs_no_edit(main_window):
    from gui.components import BarState

    main_window.command_bar.set_state(BarState.SESSION)
    main_window.session_info_label.setText("SESSION_7")
    assert main_window.command_bar.session_button.text() == "SESSION_7"


def test_choosing_a_client_in_the_dropdown_drives_on_client_changed(main_window):
    # Real profiles: clientChanged is wired to the real on_client_changed,
    # which loads config for whatever id it's given -- a fake id would hit
    # the "Configuration Error" QMessageBox and hang the test on its exec().
    main_window.profile_manager.create_client_profile("alpha", "Client alpha")
    main_window.profile_manager.create_client_profile("beta", "Client beta")
    seen = []
    main_window.command_bar.clientChanged.connect(seen.append)
    main_window.command_bar.set_clients(["alpha", "beta"])

    main_window.command_bar.set_current_client("beta")

    # set_clients suppresses its own churn; only the change gets through.
    assert seen == ["beta"]


def test_the_bar_asks_its_owner_for_the_context_menu(main_window):
    """CommandBar owns no ProfileManager: the menu comes from the directory."""
    main_window.profile_manager.create_client_profile("M", "Client M")
    menu = main_window.client_directory.menu_for("M", main_window)
    assert menu.actions()


DESTINATIONS = (
    "Session Setup",
    "Analysis Results",
    "Session Browser",
    "Logs",
    "Tools",
)


def test_the_tab_bar_is_gone_and_the_rail_took_its_place(main_window):
    assert not main_window.main_tabs.tabBar().isVisible()
    assert main_window.nav_rail.button(4) is not None
    with pytest.raises(IndexError):
        main_window.nav_rail.set_current(5)


def test_the_pages_keep_the_old_tab_titles(main_window):
    """Guardrail 2 governs the destinations, and they have not moved again."""
    assert [main_window.main_tabs.tabText(i) for i in range(5)] == list(DESTINATIONS)


def test_the_rail_shows_short_labels_not_the_full_titles(main_window):
    """8.6 put the full titles on a 56px rail and Qt elided five of six.

    Guardrail 2 forbids renaming a destination and moving it in the *same*
    release; the move shipped in 8.6, so the rename is allowed now. See
    tests/test_navrail_labels_fit.py for the width check that forced it.
    """
    labels = [main_window.nav_rail.button(i).text() for i in range(5)]
    assert labels == ["Setup", "Results", "Browse", "Logs", "Tools"]


def test_the_full_destination_name_survives_in_the_tooltip(main_window):
    """The rail label is abbreviated, so hover is the only place the full name
    still appears -- and _TAB_TOOLTIPS holds descriptions, not names."""
    for index, full_name in enumerate(DESTINATIONS):
        assert full_name in main_window.nav_rail.button(index).toolTip()


@pytest.mark.parametrize("index", range(5))
def test_clicking_the_rail_moves_the_page(main_window, index):
    # The binding, not the gate: the gate has its own tests below.
    main_window.nav_rail.button(index).setEnabled(True)
    main_window.nav_rail.button(index).click()
    assert main_window.main_tabs.currentIndex() == index


def test_a_programmatic_jump_moves_the_rail_back(main_window):
    """actions_handler jumps to Analysis Results after a run; the rail follows."""
    main_window.main_tabs.setCurrentIndex(1)
    assert main_window.nav_rail.current_index() == 1


def test_the_two_way_binding_does_not_recurse(main_window):
    seen = []
    main_window.nav_rail.currentChanged.connect(seen.append)

    main_window.main_tabs.setCurrentIndex(3)

    assert seen == [3]
    assert main_window.nav_rail.current_index() == 3


def test_rail_buttons_carry_the_old_tab_tooltips(main_window):
    assert "Ctrl+1" in main_window.nav_rail.button(0).toolTip()
    assert main_window.main_tabs.tabToolTip(0) == ""


def test_refresh_icons_reaches_the_rail(main_window):
    main_window.ui_manager._refresh_icons()
    for index in range(5):
        assert not main_window.nav_rail.button(index).icon().isNull()


def test_right_clicking_a_client_row_asks_the_directory_for_a_menu(main_window):
    # connect_signals() (Task 4) already wired this signal to the real
    # MainWindow._on_client_menu_requested, which calls menu.exec() -- a
    # blocking call with nothing around to dismiss it headless. Disconnected
    # for this one assertion: what's under test is the signal itself
    # carrying the right client id, not the production dialog.
    main_window.command_bar.clientMenuRequested.disconnect(
        main_window._on_client_menu_requested
    )

    main_window.profile_manager.create_client_profile("M", "Client M")
    main_window.command_bar.set_clients_from(main_window.client_directory.gather())

    seen = []
    main_window.command_bar.clientMenuRequested.connect(
        lambda client_id, _pos: seen.append(client_id)
    )
    bar = main_window.command_bar
    model = bar.client_selector.model()
    row = next(
        i
        for i in range(model.rowCount())
        if model.item(i).data(Qt.UserRole) == ROW_CLIENT
    )

    view = bar.client_selector.view()
    bar._on_row_context_menu(view.visualRect(model.index(row, 0)).center())

    assert seen == ["M"]


def test_the_shell_leaves_the_page_the_size_later_screens_assume(main_window):
    """1366x768 minus the 200px sidebar and the 48px command bar; no status bar.

    main_tabs keeps the 5px inset every Qt page was laid out against (phase 1
    spec section 5.1), so the page is 1366 - 200 - 10 wide.
    """
    from PySide6.QtWidgets import QStatusBar

    main_window.resize(1366, 768)
    QApplication.processEvents()

    assert main_window.sidebar.width() == 200
    assert main_window.nav_rail is main_window.sidebar.rail
    assert main_window.command_bar.height() == 48
    assert main_window.findChild(QStatusBar) is None
    assert main_window.main_tabs.width() == 1156


def test_the_sidebar_footer_names_the_server(main_window, tmp_path):
    assert main_window.sidebar.connection_label.text() == "Server connected"
    assert main_window.sidebar.path_label.toolTip() == str(tmp_path)


def test_retry_rechecks_the_connection(main_window):
    """Retry is the Server Connection dialog's own recheck: it re-emits."""
    seen = []
    main_window.connectionChanged.connect(seen.append)
    main_window.sidebar.retryRequested.emit()
    assert seen == [True]


def test_the_sidebar_asks_for_client_settings(main_window):
    calls = []
    main_window.actions_handler.open_settings_window = lambda: calls.append(1)
    main_window.sidebar.settings_button.setEnabled(True)
    main_window.sidebar.settings_button.click()
    assert calls == [1]


def test_the_command_bar_sits_on_the_sunken_plane(main_window):
    from shared.theme import current_tokens

    # Painted, not just in the sheet: a QWidget subclass ignores its QSS
    # background unless it opts in with WA_StyledBackground.
    image = main_window.command_bar.grab().toImage()
    assert image.pixelColor(2, 2).name() == current_tokens().surface_sunken.lower()
    edge = image.pixelColor(2, image.height() - 1).name()
    assert edge == current_tokens().border_subtle.lower()
    assert main_window.command_bar.client_selector.placeholderText() == "Choose a client"


def test_resuming_a_past_session_reaches_the_session_state(main_window, tmp_path):
    """The second way into SESSION, and the one the wiring first missed.

    Creating a session says so; loading an existing one has to say so too,
    or the bar offers New Session while a session is open. Spec 3.1.
    """
    from gui.components.commandbar import BarState

    session = tmp_path / "Sessions" / "SESSION_OLD"
    session.mkdir(parents=True)
    main_window.load_existing_session(str(session))

    assert main_window.command_bar._state is BarState.SESSION
    assert main_window.command_bar.open_folder_button.isVisible()


def test_new_session_is_reachable_from_the_overflow_with_a_session_open(main_window):
    """The bar's own New Session button is state-owned (BarState.NO_SESSION
    only). PR #317 review: with a session already open, the only way back to
    it was switching clients first -- the overflow is the fix.
    """
    from gui.components.commandbar import BarState

    main_window.profile_manager.create_client_profile("M", "Client M")
    main_window.command_bar.set_clients(["M"])
    main_window.command_bar.set_current_client("M")
    main_window.command_bar.set_state(BarState.SESSION)

    menu = main_window.command_bar.overflow
    item = next(a for a in menu.actions() if a.text() == "New session…")
    assert item.isEnabled()

    calls = []
    main_window.actions_handler.create_new_session = lambda: calls.append(1)
    item.trigger()
    assert calls == [1]


def test_undo_with_nothing_to_undo_says_nothing(main_window, monkeypatch):
    toasts = Mock()
    monkeypatch.setattr("gui.main_window_pyside.toast", toasts)
    monkeypatch.setattr(
        QMessageBox, "information", Mock(side_effect=AssertionError("no message box"))
    )

    main_window.undo_last_operation()

    toasts.assert_not_called()
    assert main_window.error_banner.isHidden()


class _OneShotUndo:
    """An undo manager with exactly one operation left in it."""

    def __init__(self):
        self.done = False

    def can_undo(self):
        return not self.done

    def undo(self):
        self.done = True
        return True, "Undid the last thing"

    def get_undo_description(self):
        return None


@pytest.fixture
def one_shot_undo(main_window, monkeypatch):
    main_window.undo_manager = _OneShotUndo()
    monkeypatch.setattr(main_window, "_update_all_views", Mock())
    monkeypatch.setattr(main_window, "save_session_state", Mock())
    monkeypatch.setattr(main_window, "log_activity", Mock())
    return main_window


def test_undo_tells_the_results_page_there_is_nothing_left_to_undo(
    one_shot_undo, monkeypatch
):
    """Spec section 6: a toast whose operation has already been undone must
    stop offering Undo. That only holds if undo_last_operation pushes the new
    undoAvailable across the bridge, not just repaints the Qt button.
    """
    monkeypatch.setattr("gui.main_window_pyside.toast", Mock())
    one_shot_undo.results_bridge.set_undo_available(True)

    one_shot_undo.undo_last_operation()

    assert one_shot_undo.results_bridge.undoAvailable is False


def test_undo_toasts_into_the_document_while_the_results_screen_shows(
    one_shot_undo, monkeypatch
):
    """ADR 0007: a Qt toast raised over the results view lands behind it."""
    qt_toast = Mock()
    monkeypatch.setattr("gui.main_window_pyside.toast", qt_toast)
    monkeypatch.setattr(one_shot_undo.results_view, "isVisible", lambda: True)
    raised = Mock()
    monkeypatch.setattr(one_shot_undo.results_bridge, "raise_toast", raised)

    one_shot_undo.undo_last_operation()

    raised.assert_called_once_with("Undid the last thing")
    qt_toast.assert_not_called()


def test_undo_keeps_the_qt_toast_when_another_screen_shows(one_shot_undo, monkeypatch):
    """The other side of the same branch: off the Results screen the Qt toast
    is the visible one, so rerouting everything would lose the message."""
    qt_toast = Mock()
    monkeypatch.setattr("gui.main_window_pyside.toast", qt_toast)
    monkeypatch.setattr(one_shot_undo.results_view, "isVisible", lambda: False)
    raised = Mock()
    monkeypatch.setattr(one_shot_undo.results_bridge, "raise_toast", raised)

    one_shot_undo.undo_last_operation()

    qt_toast.assert_called_once()
    raised.assert_not_called()


def _enabled(window):
    return [i for i in range(5) if window.nav_rail.button(i).isEnabled()]


def _pick_client(window, client_id="M"):
    window.profile_manager.create_client_profile(client_id, f"Client {client_id}")
    window.command_bar.set_clients([client_id])
    window.command_bar.set_current_client(client_id)
    QApplication.processEvents()
    # The client's config may finish loading after this returns; the rule is
    # what is under test, so run the refresh the load would end with.
    window.update_ui_state()


def _go_offline(window):
    # _refresh_nav asks is_connected(), exactly as the real emitter does.
    window.profile_manager.is_network_available = False
    window.connectionChanged.emit(False)


def test_with_no_client_only_setup_and_logs_are_offered(main_window):
    assert main_window.current_client_id is None
    assert _enabled(main_window) == [0, 3]


def test_results_waits_for_an_analysis(main_window):
    import pandas as pd

    _pick_client(main_window)
    assert _enabled(main_window) == [0, 2, 3, 4]
    assert "available after Run analysis" in main_window.nav_rail.button(1).toolTip()
    assert "Analysis Results" in main_window.nav_rail.button(1).toolTip()

    main_window.analysis_results_df = pd.DataFrame({"Order_Number": ["1"]})
    main_window.update_ui_state()
    assert _enabled(main_window) == [0, 1, 2, 3, 4]
    assert "available after" not in main_window.nav_rail.button(1).toolTip()


def test_the_jump_to_results_after_a_run_survives_the_rule(main_window):
    """actions_handler (after a run) and load_existing_session (a past session
    with an analysis) both set the frame, jump to Results, then refresh. The
    rule must not bounce that jump back to Setup."""
    import pandas as pd

    _pick_client(main_window)
    main_window.analysis_results_df = pd.DataFrame({"Order_Number": ["1"]})
    main_window.main_tabs.setCurrentIndex(1)
    main_window.update_ui_state()
    assert main_window.main_tabs.currentIndex() == 1
    assert main_window.nav_rail.button(1).isEnabled()


def test_going_offline_on_browse_returns_to_setup(main_window):
    _pick_client(main_window)
    main_window.main_tabs.setCurrentIndex(2)
    _go_offline(main_window)
    assert main_window.main_tabs.currentIndex() == 0


def test_going_offline_on_logs_stays_on_logs(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    _go_offline(main_window)
    assert main_window.main_tabs.currentIndex() == 3


def test_ctrl_f_does_not_open_a_results_page_that_is_not_offered(main_window):
    assert not main_window.nav_rail.button(1).isEnabled()
    main_window._focus_results_search()
    assert main_window.main_tabs.currentIndex() == 0


def test_client_settings_needs_a_client(main_window):
    assert not main_window.sidebar.settings_button.isEnabled()
    _pick_client(main_window)
    assert main_window.sidebar.settings_button.isEnabled()


def test_the_overflow_keeps_only_what_the_sidebar_does_not(main_window):
    menu = main_window.command_bar.overflow
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == [
        "No client",
        "New session…",
        "THIS PC",
        "Server connection…",
        "Keyboard shortcuts…",
    ]
    assert not any(a.isCheckable() for a in menu.actions())


def test_collapsing_is_remembered_on_this_pc(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    import gui.ui_manager as ui

    ini = str(tmp_path / "shell.ini")
    monkeypatch.setattr(ui, "_shell_settings", lambda: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    first = MainWindow()
    first.show()
    QApplication.processEvents()
    first.sidebar.collapse_button.click()
    assert QSettings(ini, QSettings.IniFormat).value(ui._COLLAPSED_KEY, type=bool) is True
    first.close()

    second = MainWindow()
    second.show()
    QApplication.processEvents()
    try:
        assert not second.sidebar.is_expanded()
        assert second.sidebar.width() == 56
        # Collapsed, the tooltip is the only place a destination is named.
        assert "Session Setup" in second.nav_rail.button(0).toolTip()
    finally:
        second.close()
