"""Regression test for the Session Browser getting permanently stuck on
'Loading...' -- gui.session_browser_widget.SessionBrowserWidget.

Root cause: refresh_sessions() clears _is_dirty synchronously the moment the
background load *starts*, not when it finishes. If the widget becomes hidden
before the async worker's result arrives (e.g. the user switches to another
tab while the file-server load is in flight), _on_sessions_loaded's
isVisible() guard discarded the result -- but left _is_dirty False. Since
showEvent() only reloads when _is_dirty is True, the widget never recovered:
switching back showed an empty table with the button stuck on "Loading...".
"""
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication

from gui.session_browser_widget import SessionBrowserWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget(qapp):
    w = SessionBrowserWidget(Mock(), parent=None)
    w.current_client_id = "CLIENT_1"
    w._is_dirty = False  # mimics state right after refresh_sessions() started a load
    return w


def test_dropped_result_while_hidden_marks_dirty_for_retry(widget, monkeypatch):
    monkeypatch.setattr(widget, "isVisible", lambda: False)

    widget._on_sessions_loaded([{"session_name": "s1", "created_at": ""}])

    assert widget._is_dirty is True
    assert widget.sessions_tree.topLevelItemCount() == 0


def test_becoming_visible_again_retries_the_load(widget, monkeypatch):
    monkeypatch.setattr(widget, "isVisible", lambda: False)
    widget._on_sessions_loaded([{"session_name": "s1", "created_at": ""}])

    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)
    monkeypatch.setattr(widget, "isVisible", lambda: True)
    widget.showEvent(QShowEvent())

    refreshed.assert_called_once()


def test_client_switch_refreshes_immediately_when_tab_already_visible(qapp, monkeypatch):
    """set_client(..., auto_refresh=False) is called on every client switch
    (gui/main_window_pyside.py) on the assumption that the next showEvent()
    will pick up the resulting dirty flag. But if the Session Browser tab is
    already the active/visible tab -- e.g. the user switches clients from the
    sidebar while already browsing sessions -- no showEvent() fires, since
    visibility never changes. Without this, the table would keep showing the
    previous client's sessions until some unrelated action (Refresh click, or
    a tab switch away and back) happened to trigger a reload.
    """
    widget = SessionBrowserWidget(Mock(), parent=None)
    widget.current_client_id = "CLIENT_1"
    monkeypatch.setattr(widget, "isVisible", lambda: True)
    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)

    widget.set_client("CLIENT_2", auto_refresh=False)

    refreshed.assert_called_once()


def test_client_switch_defers_to_showevent_when_tab_hidden(qapp, monkeypatch):
    """Unchanged behavior: when the widget isn't visible, auto_refresh=False
    still defers the reload to the next showEvent() instead of doing a
    network round trip for a tab nobody is looking at."""
    widget = SessionBrowserWidget(Mock(), parent=None)
    widget.current_client_id = "CLIENT_1"
    monkeypatch.setattr(widget, "isVisible", lambda: False)
    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)

    widget.set_client("CLIENT_2", auto_refresh=False)

    refreshed.assert_not_called()
    assert widget._is_dirty is True
