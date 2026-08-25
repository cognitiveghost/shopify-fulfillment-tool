"""Packing column + archived visibility in the Session Browser."""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.session_browser_widget import SessionBrowserWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(qapp):
    w = SessionBrowserWidget(Mock(), parent=None)
    w.current_client_id = "M"
    return w


def _session(name, status="active", lists=(), progress=None):
    return {
        "session_name": name,
        "status": status,
        "created_at": "",
        "statistics": {"packing_lists": list(lists)},
        "packing_progress": progress or {},
    }


def _column_text(widget, header):
    col = next(
        c for c in range(widget.sessions_table.columnCount())
        if widget.sessions_table.horizontalHeaderItem(c).text() == header
    )
    return [widget.sessions_table.item(r, col).text() for r in range(widget.sessions_table.rowCount())]


def _names(widget):
    return [widget.sessions_table.item(r, 0).text() for r in range(widget.sessions_table.rowCount())]


class TestPackingColumn:
    def test_shows_packed_over_total(self, widget):
        widget.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"a": {"status": "completed"}})
        ]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["1/2"]

    def test_session_with_no_packing_lists_shows_a_dash(self, widget):
        widget.sessions_data = [_session("s1")]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["—"]

    def test_full_session_key_reads_as_complete(self, widget):
        widget.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"full_session": {"status": "completed"}})
        ]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["2/2"]


class TestArchivedVisibility:
    def test_archived_sessions_are_hidden_by_default(self, widget):
        widget.sessions_data = [_session("keep"), _session("gone", status="archived")]
        widget._populate_table()
        assert _names(widget) == ["keep"]

    def test_show_archived_toggle_reveals_them(self, widget):
        widget.sessions_data = [_session("keep"), _session("gone", status="archived")]
        widget.show_archived_btn.setChecked(True)
        assert sorted(_names(widget)) == ["gone", "keep"]

    def test_explicit_archived_status_filter_shows_them_with_toggle_off(self, widget):
        # The status filter is server-side: that path returns only archived
        # rows, so hiding them would leave the user staring at an empty table.
        # Signal blocked: setCurrentText alone would fire currentTextChanged
        # -> _apply_filter -> a real background refresh against this test's
        # unconfigured Mock session_manager, which is not what this test
        # means to exercise.
        widget.status_filter.blockSignals(True)
        widget.status_filter.setCurrentText("Archived")
        widget.status_filter.blockSignals(False)
        widget.sessions_data = [_session("gone", status="archived")]
        widget._populate_table()
        assert _names(widget) == ["gone"]


def test_manual_status_edit_is_recorded_as_manual(widget):
    widget._on_status_changed("/some/session", "Abandoned")
    widget.session_manager.update_session_status.assert_called_once_with(
        "/some/session", "abandoned", manual=True
    )
