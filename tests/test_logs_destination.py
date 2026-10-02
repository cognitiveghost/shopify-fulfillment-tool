import logging

import pytest

from gui import logs_widget
from gui.logs_bridge import LogsBridge
from gui.logs_widget import LogsWidget
from gui.main_window_pyside import MainWindow
from gui.ui_manager import UIManager


def test_the_rail_reads_logs():
    assert UIManager._RAIL_LABELS[3] == "Logs"
    assert UIManager._TAB_LABELS[3] == "Logs"
    assert "Statistics" not in UIManager._TAB_TOOLTIPS[3]


def test_no_statistics_page_is_reachable():
    for gone in (
        "_create_statistics_subtab",
        "_create_activity_log_subtab",
        "_create_execution_log_subtab",
        "_make_stat_card",
        "_make_courier_card",
        "_make_tag_card",
    ):
        assert not hasattr(UIManager, gone), f"{gone} should be deleted"


def test_the_statistics_update_methods_are_gone():
    for gone in (
        "update_statistics_tab",
        "_clear_statistics_view",
        "_on_sku_search_changed",
    ):
        assert not hasattr(MainWindow, gone), f"{gone} should be deleted"


def test_the_qt_log_viewer_is_gone():
    """Phase 6 spec section 7: the page replaced the widget, its model, proxy and follow state."""
    import importlib.util

    for gone in ("gui.log_viewer", "gui.log_model", "gui.log_filter", "gui.log_follow"):
        assert importlib.util.find_spec(gone) is None, f"{gone} should be deleted"
    assert not hasattr(UIManager, "_apply_page_inset")


class _JustTheLogging:
    """A MainWindow reduced to the methods that route into the Logs widget.

    Building a real MainWindow drags in the profile manager, the server path
    and a full UI; these methods only ever touch `self.logs_widget`, so
    binding them to a stub tests the routing and nothing else.
    """

    log_activity = MainWindow.log_activity
    _on_log_entry = MainWindow._on_log_entry
    setup_logging = MainWindow.setup_logging

    def __init__(self, widget):
        self.logs_widget = widget


@pytest.fixture
def logs(qtbot, monkeypatch):
    """A LogsWidget with no page loaded: these tests read its buffer."""
    monkeypatch.setattr(
        logs_widget,
        "mount_logs_page",
        lambda view, wrap=False: LogsBridge(view, wrap=wrap),
    )
    widget = LogsWidget(None)
    qtbot.addWidget(widget)
    return widget


def test_log_activity_appends_to_the_activity_stream(logs):
    _JustTheLogging(logs).log_activity("Report", "Generated: picklist")

    rows = logs.buffer.rows()
    assert [(row["stream"], row["source"], row["message"]) for row in rows] == [
        ("Activity", "Report", "Generated: picklist")
    ]


def test_a_root_logger_record_reaches_the_execution_stream(logs):
    """The whole wiring, end to end: logging call -> handler -> buffer.

    test_log_handler covers emit() in isolation and this file covers
    log_activity, but nothing proved the signal is actually connected -- the
    one edge where a rename would fail silently, because a log line that
    never arrives looks exactly like a quiet program.
    """
    window = _JustTheLogging(logs)
    window.setup_logging()
    try:
        try:
            raise FileNotFoundError("inventory.csv")
        except FileNotFoundError:
            logging.getLogger("shopify_tool.engine").exception("stock file vanished")

        row = logs.buffer.rows()[-1]
        assert row["stream"] == "Execution"
        assert row["level"] == "Error"
        assert row["source"] == "shopify_tool.engine"
        assert (
            row["message"] == "stock file vanished — FileNotFoundError: inventory.csv"
        )
        assert row["traceback"].startswith("Traceback (most recent call last):")
        assert row["traceback"].endswith("FileNotFoundError: inventory.csv")
    finally:
        logging.getLogger().removeHandler(window.log_handler)
