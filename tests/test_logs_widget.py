"""The Logs screen's widget: the buffer, the batches, save and copy (phase 6 spec 6).

The page itself is tested in test_logs_page.py. Here the widget is tested
against a bare bridge with no page loaded, so nothing calls start() but the
test. The last test loads the real page once, end to end.
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog
from test_results_bridge import _eval, _until_js

from gui import logs_widget
from gui.log_buffer import ACTIVITY, EXECUTION
from gui.log_entry import LogEntry
from gui.logs_bridge import LogsBridge
from gui.logs_widget import BATCH_MS, LogsWidget

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_000, tzinfo=UTC)
TRACE = "Traceback (most recent call last):\nPermissionError: share is read-only"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path, monkeypatch):
    """This PC's settings, in a file under tmp_path."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(
        logs_widget, "_settings", lambda: QSettings(path, QSettings.IniFormat)
    )
    return logs_widget._settings


@pytest.fixture
def window():
    """What LogsWidget reads from the main window."""
    return SimpleNamespace(current_client_id="ACME")


@pytest.fixture
def bare(monkeypatch):
    """No page: the bridge alone, so only the test calls start()."""
    monkeypatch.setattr(
        logs_widget,
        "mount_logs_page",
        lambda view, wrap=False: LogsBridge(view, wrap=wrap),
    )


@pytest.fixture
def logs(qtbot, window, store, bare):
    widget = LogsWidget(window)
    qtbot.addWidget(widget)
    return widget


def entry(message, level=logging.INFO, source="shopify_tool.core", trace=""):
    return LogEntry(STAMP, level, source, message, trace)


def _batches(bridge):
    seen = []
    bridge.entriesAdded.connect(
        lambda rows: seen.append([row["message"] for row in rows])
    )
    return seen


def _toasts(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, _flag: seen.append(text))
    return seen


def _save_to(monkeypatch, path):
    asked = []

    def dialog(parent, title, name, filters):
        asked.append((title, name, filters))
        return str(path) if path else "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", dialog)
    return asked


# --- batches ------------------------------------------------------------------


def test_it_hosts_one_web_view_with_no_margins(logs):
    assert logs.findChildren(QWebEngineView) == [logs.view]
    margins = logs.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )


def test_entries_before_the_page_starts_leave_as_one_backlog_batch(qtbot, logs):
    seen = _batches(logs.bridge)
    logs.append(entry("one"), EXECUTION)
    logs.append(entry("two"), ACTIVITY)
    qtbot.wait(BATCH_MS * 2)
    assert seen == []
    logs.bridge.start()
    assert seen == [["one", "two"]]


def test_entries_after_the_start_leave_together_on_the_timer(qtbot, logs):
    logs.bridge.start()
    seen = _batches(logs.bridge)
    for message in ("one", "two", "three"):
        logs.append(entry(message), EXECUTION)
    assert seen == []
    qtbot.waitUntil(lambda: seen == [["one", "two", "three"]], timeout=2000)
    logs.append(entry("four"), EXECUTION)
    qtbot.waitUntil(lambda: seen == [["one", "two", "three"], ["four"]], timeout=2000)


def test_a_second_start_resends_the_whole_backlog(qtbot, logs):
    logs.append(entry("one"), EXECUTION)
    logs.bridge.start()
    logs.append(entry("two"), EXECUTION)
    seen = _batches(logs.bridge)
    logs.bridge.start()
    assert seen == [["one", "two"]]
    qtbot.wait(BATCH_MS * 2)
    assert seen == [["one", "two"]]  # nothing was left pending


def test_append_does_not_log(logs, caplog):
    """The root logger's handler calls append(): a log call here would recurse."""
    logs.bridge.start()
    with caplog.at_level(logging.DEBUG):
        logs.append(entry("one"), EXECUTION)
        logs._flush()
    assert caplog.records == []


# --- save ---------------------------------------------------------------------


def test_save_writes_the_picked_rows_and_toasts_the_file_name(
    logs, tmp_path, monkeypatch
):
    logs.append(entry("New session created", source="Session"), ACTIVITY)
    logs.append(
        entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
    )
    logs.append(entry("not shown"), EXECUTION)
    target = tmp_path / "out.txt"
    asked = _save_to(monkeypatch, target)
    toasts = _toasts(logs.bridge)

    logs.bridge.saveShown([0, 1])

    assert asked == [
        (
            "Save log as text",
            f"logs_ACME_{datetime.now().astimezone():%Y-%m-%d}.txt",
            "Text files (*.txt);;All files (*)",
        )
    ]
    assert target.read_text(encoding="utf-8") == (
        "2026-09-30 14:00:53.508  INFO      Activity   Session  New session created\n"
        "2026-09-30 14:00:53.508  ERROR     Execution  gui.tools_widget  Save failed\n"
        "    Traceback (most recent call last):\n"
        "    PermissionError: share is read-only\n"
    )
    assert toasts == ["Saved 2 entries to out.txt"]


def test_saving_one_entry_says_one_entry(logs, tmp_path, monkeypatch):
    logs.append(entry("only"), EXECUTION)
    _save_to(monkeypatch, tmp_path / "one.txt")
    toasts = _toasts(logs.bridge)
    logs.bridge.saveShown([0])
    assert toasts == ["Saved 1 entry to one.txt"]


def test_a_cancelled_dialog_writes_nothing(logs, tmp_path, monkeypatch):
    logs.append(entry("only"), EXECUTION)
    _save_to(monkeypatch, None)
    toasts = _toasts(logs.bridge)
    logs.bridge.saveShown([0])
    assert toasts == []
    assert list(tmp_path.glob("*.txt")) == []


def test_save_with_no_row_left_opens_no_dialog(logs, monkeypatch):
    asked = _save_to(monkeypatch, None)
    logs.bridge.saveShown([5, 6])
    assert asked == []


def test_a_file_that_cannot_be_written_shows_the_dialog_and_no_toast(
    logs, tmp_path, monkeypatch
):
    logs.append(entry("only"), EXECUTION)
    target = tmp_path / "missing_folder" / "out.txt"
    _save_to(monkeypatch, target)
    shown = []
    monkeypatch.setattr(
        logs_widget,
        "show_error",
        lambda parent, title, text: shown.append((title, text)),
    )
    toasts = _toasts(logs.bridge)

    logs.bridge.saveShown([0])

    assert shown == [
        (
            "The log wasn't saved",
            f"{target} couldn't be written. Choose another folder and save again.",
        )
    ]
    assert toasts == []


def test_with_no_client_the_file_name_has_only_the_day(
    logs, window, tmp_path, monkeypatch
):
    window.current_client_id = None
    logs.append(entry("only"), EXECUTION)
    asked = _save_to(monkeypatch, tmp_path / "x.txt")
    logs.bridge.saveShown([0])
    assert asked[0][1] == f"logs_{datetime.now().astimezone():%Y-%m-%d}.txt"


# --- copy and wrap ------------------------------------------------------------


def test_copy_puts_the_traceback_on_the_clipboard(logs):
    logs.append(entry("Save failed", logging.ERROR, trace=TRACE), EXECUTION)
    QGuiApplication.clipboard().setText("before")
    toasts = _toasts(logs.bridge)
    logs.bridge.copyTraceback(0)
    assert QGuiApplication.clipboard().text() == TRACE
    assert toasts == ["Traceback copied"]


def test_copy_does_nothing_for_a_row_without_a_traceback_or_an_unknown_id(logs):
    logs.append(entry("plain"), EXECUTION)
    QGuiApplication.clipboard().setText("before")
    toasts = _toasts(logs.bridge)
    logs.bridge.copyTraceback(0)
    logs.bridge.copyTraceback(99)
    assert QGuiApplication.clipboard().text() == "before"
    assert toasts == []


def test_wrap_is_read_from_this_pc_and_written_back(qtbot, window, store, bare):
    first = LogsWidget(window)
    qtbot.addWidget(first)
    assert first.bridge.wrap is False
    first.bridge.setWrap(True)
    assert store().value("logs/wrap", False, type=bool) is True

    second = LogsWidget(window)
    qtbot.addWidget(second)
    assert second.bridge.wrap is True


# --- end to end ---------------------------------------------------------------


def test_the_real_page_draws_the_backlog_and_then_each_batch(qtbot, window, store):
    widget = LogsWidget(window)
    qtbot.addWidget(widget)
    widget.append(entry("before the page was ready"), EXECUTION)
    widget.resize(1166, 720)
    widget.show()
    view = widget.view
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    _until_js(qtbot, view, "document.querySelectorAll('#list .row').length === 1")

    widget.append(entry("after"), ACTIVITY)
    _until_js(qtbot, view, "document.querySelectorAll('#list .row').length === 2")
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#list .row:last-child .cell-message').textContent",
        )
        == "after"
    )


def test_text_outside_ascii_is_saved_as_utf8(logs, tmp_path, monkeypatch):
    logs.append(entry("Oberländer-Schwarz — bitte zweimal klingeln ✓"), EXECUTION)
    target = tmp_path / "utf8.txt"
    _save_to(monkeypatch, target)
    logs.bridge.saveShown([0])
    assert (
        target.read_bytes()
        .decode("utf-8")
        .endswith("Oberländer-Schwarz — bitte zweimal klingeln ✓\n")
    )
