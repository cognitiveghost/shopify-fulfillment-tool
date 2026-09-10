import logging

from PySide6.QtCore import Qt

from gui.log_model import COL_LEVEL, COL_MESSAGE, COL_SOURCE, LogBufferModel
from gui.log_viewer import LogViewer
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
    from gui.main_window_pyside import MainWindow

    for gone in (
        "update_statistics_tab",
        "_clear_statistics_view",
        "_on_sku_search_changed",
    ):
        assert not hasattr(MainWindow, gone), f"{gone} should be deleted"


class _JustTheLogging:
    """A MainWindow reduced to the two methods that route into the viewer.

    Building a real MainWindow drags in the profile manager, the server path
    and a full UI; these two methods only ever touch `self.log_viewer`, so
    binding them to a stub tests the routing and nothing else.
    """

    log_activity = MainWindow.log_activity
    _on_log_entry = MainWindow._on_log_entry
    setup_logging = MainWindow.setup_logging

    def __init__(self, viewer):
        self.log_viewer = viewer


def test_log_activity_appends_to_the_activity_source(qapp):
    viewer = LogViewer()
    _JustTheLogging(viewer).log_activity("Report", "Generated: picklist")

    viewer.set_source(LogBufferModel.ACTIVITY)
    assert viewer.proxy.rowCount() == 1
    assert viewer.proxy.index(0, COL_SOURCE).data(Qt.DisplayRole) == "Report"
    assert viewer.proxy.index(0, COL_MESSAGE).data(Qt.DisplayRole) == (
        "Generated: picklist"
    )


def test_a_root_logger_record_reaches_the_execution_source(qapp):
    """The whole wiring, end to end: logging call -> handler -> viewer.

    test_log_handler covers emit() in isolation and this file covers
    log_activity, but nothing proved the signal is actually connected -- the
    one edge where a rename would fail silently, because a log line that
    never arrives looks exactly like a quiet program.
    """
    viewer = LogViewer()
    window = _JustTheLogging(viewer)
    window.setup_logging()
    try:
        logging.getLogger("shopify_tool.engine").error("stock file vanished")

        assert viewer.model.current_source() == LogBufferModel.EXECUTION
        assert viewer.proxy.rowCount() >= 1
        row = 0
        assert viewer.proxy.index(row, COL_LEVEL).data(Qt.DisplayRole) == "ERROR"
        assert (
            viewer.proxy.index(row, COL_SOURCE).data(Qt.DisplayRole)
            == "shopify_tool.engine"
        )
        assert viewer.proxy.index(row, COL_MESSAGE).data(Qt.DisplayRole) == (
            "stock file vanished"
        )
    finally:
        logging.getLogger().removeHandler(window.log_handler)
