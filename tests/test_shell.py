"""The 8.6 shell contract: one command bar, a rail, no global header."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

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
    main_window.session_info_label.setText("SESSION_7")
    assert main_window.command_bar.session_label.text() == "SESSION_7"


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
    "Information",
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
    assert labels == ["Setup", "Results", "Browse", "Info", "Tools"]


def test_the_full_destination_name_survives_in_the_tooltip(main_window):
    """The rail label is abbreviated, so hover is the only place the full name
    still appears -- and _TAB_TOOLTIPS holds descriptions, not names."""
    for index, full_name in enumerate(DESTINATIONS):
        assert full_name in main_window.nav_rail.button(index).toolTip()


@pytest.mark.parametrize("index", range(5))
def test_clicking_the_rail_moves_the_page(main_window, index):
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
    row = next(i for i in range(model.rowCount())
               if model.item(i).data(Qt.UserRole) == ROW_CLIENT)

    view = bar.client_selector.view()
    bar._on_row_context_menu(view.visualRect(model.index(row, 0)).center())

    assert seen == ["M"]
