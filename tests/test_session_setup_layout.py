"""Regression test for the Session Setup window resizing/shifting when the
user switches Orders 'Load Mode' to Folder -- gui.ui_manager.UIManager.

Root cause: _create_session_setup_panel() (Tab 1's left panel) laid its
sections directly in a QVBoxLayout with no QScrollArea. Switching to Folder
mode reveals extra widgets (file list, count label, options checkboxes) that
were previously hidden (and so contributed zero height). With no scroll area
to absorb the growth, the panel's increased minimum height forces the whole
top-level window to resize -- exactly the pattern this codebase already
avoids elsewhere (see _create_statistics_subtab's QScrollArea wrapping).
"""
import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.ui_manager import UIManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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
