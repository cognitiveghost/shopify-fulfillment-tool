from gui.log_model import LogBufferModel
from gui.log_viewer import LogViewer
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


def test_log_activity_appends_to_the_activity_source(qapp):
    viewer = LogViewer()

    class Stub:
        log_viewer = viewer
        log_activity = __import__(
            "gui.main_window_pyside", fromlist=["MainWindow"]
        ).MainWindow.log_activity

    Stub().log_activity("Report", "Generated: picklist")

    viewer.set_source(LogBufferModel.ACTIVITY)
    assert viewer.proxy.rowCount() == 1
    from PySide6.QtCore import Qt

    assert viewer.proxy.index(0, 2).data(Qt.DisplayRole) == "Report"
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "Generated: picklist"
