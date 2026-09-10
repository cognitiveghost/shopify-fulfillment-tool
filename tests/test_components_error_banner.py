"""9.25: a failure persists until dismissed and says what to do.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.3
"""

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget

from gui.components.error_banner import ErrorBanner, show_error
from shared.theme import current_tokens


@pytest.fixture
def dialog(qapp):
    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("existing content"))
    yield dlg
    dlg.close()


def test_a_dialog_gets_its_banner_at_the_top(dialog):
    banner = show_error(
        dialog,
        "Tag categories weren't saved",
        "Check that the server share is reachable, then save again.",
    )
    assert dialog.layout().indexOf(banner) == 0
    assert ErrorBanner.for_window(dialog) is banner
    assert not banner.isHidden()
    assert banner.headline() == "Tag categories weren't saved"
    assert (
        banner.what_to_do()
        == "Check that the server share is reachable, then save again."
    )


def test_a_dialog_banner_has_no_logs_button(dialog):
    assert show_error(dialog, "h", "w").logs_button is None


def test_a_second_error_replaces_the_first(dialog):
    first = show_error(dialog, "First", "w")
    second = show_error(dialog, "Second", "w")
    assert first is second
    assert second.headline() == "Second"
    assert dialog.layout().count() == 2


def test_it_persists_until_dismissed(dialog):
    banner = show_error(dialog, "h", "w")
    assert not banner.findChildren(QTimer)
    banner.dismiss_button.click()
    assert banner.isHidden()


def test_a_window_without_a_box_layout_is_refused(qapp):
    bare = QWidget()
    with pytest.raises(TypeError):
        show_error(bare, "h", "w")


def test_a_non_widget_source_is_refused(qapp):
    with pytest.raises(TypeError):
        show_error(object(), "h", "w")


def test_the_ground_is_the_danger_background(dialog):
    assert (
        current_tokens().status_danger_bg in show_error(dialog, "h", "w").styleSheet()
    )


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """A real MainWindow rooted at a throwaway server path (tests/test_shell.py)."""
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_main_window_holds_a_hidden_banner(main_window):
    assert isinstance(main_window.error_banner, ErrorBanner)
    assert main_window.error_banner.isHidden()


def test_open_logs_moves_the_main_window_to_logs(main_window):
    from gui.ui_manager import UIManager

    banner = show_error(
        main_window.command_bar, "The analysis didn't finish", "Details are in Logs."
    )
    assert banner is main_window.error_banner
    banner.logs_button.click()
    assert main_window.main_tabs.currentIndex() == UIManager._RAIL_LABELS.index("Logs")
