"""Regression tests for Tab 1's layout -- gui.ui_manager.

Two unrelated regressions pinned in one file (same area of the codebase):

1. Switching Orders 'Load Mode' to Folder must not grow the panel's minimum
   height and resize the whole window (root cause: no QScrollArea absorbing
   the newly-revealed widgets -- fixed by wrapping the setup column in one).
2. That same QScrollArea is always willing to scroll rather than ask the
   splitter for room, so a fixed 60/40 splitter squeezed it below the 706px
   its content needs: a horizontal scrollbar appeared and five action
   buttons -- including "Generate Reports" -- fell off the right edge at the
   app's own default 1100x900 geometry. See
   docs/superpowers/specs/2026-08-23-session-setup-layout-design.md.
"""
import pytest
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
)

from gui.ui_manager import UIManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mw(qapp):
    window = QMainWindow()
    ui = UIManager(window)
    window.setCentralWidget(ui._create_tab1_session_setup())
    window.setGeometry(100, 100, 1100, 900)
    window.ui_manager = ui
    window.show()
    qapp.processEvents()
    yield window
    window.close()


def test_switching_orders_to_folder_mode_does_not_grow_minimum_height(mw, qapp):
    """The offscreen QPA platform doesn't propagate size-hint changes into an
    actual window resize (Qt prints "This plugin does not support
    propagateSizeHints()"), so this checks the underlying cause directly:
    the panel's minimumSizeHint must not grow when Folder mode is toggled --
    that growth is exactly what forces a real on-screen window to resize.
    """
    central = mw.centralWidget()
    height_before = central.minimumSizeHint().height()

    mw.orders_folder_radio.setChecked(True)
    mw.ui_manager.on_orders_mode_changed(True)
    qapp.processEvents()

    height_after = central.minimumSizeHint().height()
    assert height_after == height_before


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow
    win = MainWindow()
    win.resize(1100, 900)  # the app's own default, main_window_pyside.py:76
    win.show()
    QApplication.processEvents()
    win.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    yield win
    win.close()


def _clipped_buttons(tab):
    """Buttons whose right edge falls outside the setup column's viewport."""
    scroll = tab.findChild(QScrollArea)
    inner = scroll.widget()
    limit = scroll.viewport().width()
    return [b.text() for b in inner.findChildren(QPushButton)
            if b.mapTo(inner, b.rect().topRight()).x() > limit]


def test_no_action_button_is_clipped_at_default_window_size(main_window):
    tab = main_window.main_tabs.widget(0)
    assert _clipped_buttons(tab) == []


def test_setup_column_never_scrolls_horizontally(main_window):
    tab = main_window.main_tabs.widget(0)
    scroll = tab.findChild(QScrollArea)
    assert not scroll.horizontalScrollBar().isVisible()


def test_recent_sessions_panel_stays_compact(main_window):
    tab = main_window.main_tabs.widget(0)
    card = tab.findChild(QSplitter).widget(1)
    assert card.width() <= 320
    assert main_window.recent_sessions_list.height() <= 200
