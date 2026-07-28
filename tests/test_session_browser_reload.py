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
    assert widget.sessions_table.rowCount() == 0


def test_becoming_visible_again_retries_the_load(widget, monkeypatch):
    monkeypatch.setattr(widget, "isVisible", lambda: False)
    widget._on_sessions_loaded([{"session_name": "s1", "created_at": ""}])

    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)
    monkeypatch.setattr(widget, "isVisible", lambda: True)
    widget.showEvent(QShowEvent())

    refreshed.assert_called_once()
