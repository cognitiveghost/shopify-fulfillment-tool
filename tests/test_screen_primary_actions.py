"""The CommandBar's one primary follows the current screen.

Before 2026-08-29 nothing called CommandBar.set_action, so the bar's right-hand
side was empty on all five screens while each screen kept its primary in the page
body -- next to an unmarked Settings button that the theme was painting primary
blue. See docs/superpowers/specs/2026-08-29-commandbar-primary-action-design.md.
"""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_each_screen_puts_its_own_primary_in_the_bar(main_window, qapp):
    expected = {
        0: "▶ Run Analysis",
        1: "Generate Reports",
        2: "Create New Session",
    }
    for index, label in expected.items():
        main_window.main_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert main_window.command_bar.action_button.text() == label
        assert not main_window.command_bar.action_button.isHidden()


def test_a_screen_with_no_primary_hides_the_slot(main_window, qapp):
    for index in (3, 4):
        main_window.main_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert main_window.command_bar.action_button.isHidden()


def test_the_bar_mirrors_the_bound_buttons_enabled_state(main_window, qapp):
    """Run Analysis is disabled until the files load; the bar must agree."""
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    bar_button = main_window.command_bar.action_button
    assert bar_button.isEnabled() == main_window.run_analysis_button.isEnabled()

    main_window.run_analysis_button.setEnabled(True)
    assert bar_button.isEnabled()
    main_window.run_analysis_button.setEnabled(False)
    assert not bar_button.isEnabled()


def test_the_moved_buttons_stop_rendering_in_the_page(main_window, qapp):
    assert main_window.run_analysis_button.isHidden()
    assert main_window.generate_reports_button_tab2.isHidden()


def test_session_setups_new_session_button_keeps_rendering(main_window, qapp):
    """SessionBrowserWidget has no New Session control, so screen 2 borrows Session
    Setup's -- where it is not the primary and must stay visible."""
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert not main_window.new_session_btn.isHidden()
