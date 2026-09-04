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
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
)

from gui.theme_manager import get_theme_manager
from gui.ui_manager import (
    _RECENT_PANEL_MAX_WIDTH,
    _RECENT_SESSIONS_ROWS,
    UIManager,
    _recent_list_height,
)
from shared.theme import build_stylesheet


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mw(qapp):
    window = QMainWindow()
    # _create_tab1_session_setup wraps page 0 in a StatePanel.failed() that
    # names profile_manager.base_path (Bundle 4) -- this fixture predates
    # that and builds a bare QMainWindow with no ProfileManager at all.
    window.profile_manager = SimpleNamespace(base_path=Path("/fake/server"))
    # Degraded, so _refresh_setup_panel's StatePanel.failed() branch runs and
    # never reaches into a command_bar this bare fixture does not build.
    window.is_connected = lambda: False
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
    # The app's own default (main_window_pyside.py:76). Qt clamps it up to the
    # window's real minimum, so these tests measure the narrowest window a user
    # can actually produce -- which is the case that matters.
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    win.main_tabs.setCurrentIndex(0)
    # This file measures the form's own layout (page 1), not page 0's empty
    # state -- and a QStackedWidget page that has never been current is
    # never laid out, so every button in it would read back as (0, 0).
    win.setup_stack.setCurrentIndex(1)
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
    tab = main_window.setup_stack.widget(1)
    assert _clipped_buttons(tab) == []


def test_setup_column_never_scrolls_horizontally(main_window):
    tab = main_window.setup_stack.widget(1)
    scroll = tab.findChild(QScrollArea)
    assert not scroll.horizontalScrollBar().isVisible()


def test_recent_sessions_panel_stays_compact(main_window):
    tab = main_window.setup_stack.widget(1)
    card = tab.findChild(QSplitter).widget(1)
    assert card.width() <= _RECENT_PANEL_MAX_WIDTH
    assert main_window.recent_sessions_list.height() <= 200

    # The stretch factors alone already keep the card at the cap, so the above
    # would pass with setMaximumWidth removed. Simulate a user dragging the
    # splitter open -- that is the only thing the cap actually resists.
    main_window.resize(1920, 1080)
    QApplication.processEvents()
    tab.findChild(QSplitter).setSizes([200, 1500])
    QApplication.processEvents()
    assert card.width() <= _RECENT_PANEL_MAX_WIDTH


def test_setup_column_does_not_dramatically_outgrow_the_rest_of_the_app(main_window):
    """Pinning Tab 1's minimum to its content is what stops buttons hiding --
    but it also means anything added to that column widens that minimum.

    Phase 8.2's `desk` density profile tightens QPushButton/QComboBox/etc.
    padding app-wide (spec S2/C3: 4px 8px vs the old 6px 12px). Tab 2
    (Analysis Results) carries far more of those controls than Tab 1, so it
    now shrinks more -- Tab 1 (~1022px) has overtaken Tab 2 (~989px) as the
    tab that sets the app's minimum width. That flip is an accepted,
    deliberate side effect of the density change (see the 8.2 plan's Stage C
    notes), not a regression by itself: the actual failure modes -- clipped
    buttons, forced horizontal scroll -- are covered directly by
    test_no_action_button_is_clipped_at_default_window_size and
    test_setup_column_never_scrolls_horizontally. This test keeps a loose
    ceiling so a *dramatic* future blowup still gets caught, without pinning
    to the pre-8.2 ordering.

    2026-08-29: Tab 1's own primary (Run Analysis) and Tab 2's own primary
    (Generate Reports) both moved into the CommandBar and hid their in-page
    copies (see _SCREEN_ACTIONS in ui_manager.py). Tab 2 carried more of the
    controls that shrank, so it dropped further -- 989px to ~857px -- widening
    the gap past the old +100 ceiling even though Tab 1 itself (~1022px) did
    not move. Widened to +200; still loose, not a pin to today's numbers.

    2026-08-30: Phase 8.8a deleted Tab 2's "Tags Manager" and "Bulk
    Operations" toggle buttons (the checkbox column and bulk-mode workarounds
    they drove are gone -- selection is order-level now, see the 8.8a plan).
    Tab 2 dropped further still -- ~857px to ~583px -- again without Tab 1
    itself moving. Widened to +450; still loose, not a pin to today's numbers.
    """
    tabs = main_window.main_tabs
    widths = [tabs.widget(i).minimumSizeHint().width() for i in range(tabs.count())]
    setup, others = widths[0], max(widths[1:])
    assert setup <= others + 450, (
        f"Tab 1 now sets the app's minimum window width ({setup}px vs {others}px "
        f"for the next widest tab) -- the whole app got harder to fit on screen."
    )


def test_the_fifth_recent_session_row_fits_whole(qapp):
    """_recent_list_height() derives a fixed height from font metrics, so any
    change to what a QListWidget::item costs vertically silently clips a row.

    The selection ring did exactly that: items carry a transparent 2px
    top/bottom border so selecting one does not shift its text, which put the
    viewport at 4.24 rows until the helper accounted for it.
    """
    widget = QListWidget()
    widget.setStyleSheet(build_stylesheet(get_theme_manager().get_current_theme()))
    for i in range(_RECENT_SESSIONS_ROWS):
        widget.addItem(f"session {i}")
    widget.setFixedHeight(_recent_list_height(widget))
    widget.show()
    QApplication.processEvents()

    row = widget.sizeHintForRow(0)
    assert widget.viewport().height() >= row * _RECENT_SESSIONS_ROWS, (
        f"{widget.viewport().height() / row:.2f} rows fit, need "
        f"{_RECENT_SESSIONS_ROWS}"
    )
