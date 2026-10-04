"""Quickfix: the page area meets the chrome with no frame (spec §4.2)."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStackedWidget

from gui.components.commandbar import BAR_HEIGHT
from gui.theme_manager import get_theme_manager


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1280, 860)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_page_stack_has_no_pane_frame(main_window):
    tabs = main_window.main_tabs
    stack = tabs.findChild(QStackedWidget)
    assert stack.mapTo(tabs, QPoint(0, 0)) == QPoint(0, 0)
    assert stack.size() == tabs.size()


def test_the_sidebar_header_rule_meets_the_bar_rule(main_window):
    assert main_window.sidebar.header.height() == BAR_HEIGHT
    assert main_window.command_bar.height() == BAR_HEIGHT


def test_the_header_meets_the_bar_collapsed_too(main_window):
    main_window.sidebar.set_expanded(False)
    QApplication.processEvents()
    assert main_window.sidebar.header.height() == BAR_HEIGHT
    assert main_window.sidebar.expand_button.height() <= BAR_HEIGHT


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_open_recent_sits_on_the_bar_plane(main_window, theme):
    get_theme_manager().set_theme(theme)
    QApplication.processEvents()
    bar = main_window.command_bar
    button = bar.session_button
    # The bar's own grab: a transparent button has no pixels of its own.
    image = bar.grab().toImage()
    plane = QColor(get_theme_manager().get_current_theme().surface_sunken)
    centre = button.mapTo(bar, QPoint(0, 0)).y() + button.height() // 2
    # Just inside the button's left edge: background, never text.
    assert image.pixelColor(button.mapTo(bar, QPoint(2, 0)).x(), centre) == plane
