"""The 8.6 shell contract: one command bar, a rail, no global header."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components import CommandBar


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
