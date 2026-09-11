"""The Analysis Results screen is the results document (Bundle 12 spec §7)."""

import re
from pathlib import Path

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QTableView


@pytest.fixture
def main_window(qapp):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


@pytest.fixture
def lines_df():
    return pd.DataFrame(
        [
            {
                "Order_Number": "1001",
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DHL",
                "SKU": "AAA",
                "Quantity": 2,
                "System_note": "",
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "1001",
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DHL",
                "SKU": "BBB",
                "Quantity": 1,
                "System_note": "",
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "1002",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "Shipping_Provider": "DPD",
                "SKU": "CCC",
                "Quantity": 4,
                "System_note": "Cannot fulfill: insufficient stock for CCC",
                "Internal_Tags": "[]",
            },
        ]
    )


def test_the_results_page_is_one_web_view(main_window):
    page = main_window.main_tabs.widget(1)
    assert isinstance(main_window.results_view, QWebEngineView)
    assert main_window.results_view.parent() is page
    assert page.findChildren(QTableView) == []


def test_update_all_views_pushes_orders_and_summary(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window._update_all_views()
    assert [o["Order_Number"] for o in main_window.results_bridge.orders] == [
        "1001",
        "1002",
    ]
    assert main_window.results_bridge.summary["blocked"] == 1


def test_a_page_selection_reaches_the_selection_helper(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window.results_bridge.setSelection(["1002"])
    picked = main_window.selection_helper.get_selected_orders_data()
    assert picked["Order_Number"].unique().tolist() == ["1002"]


def test_export_clicks_generate_reports_only_while_enabled(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.actions_handler,
        "open_generate_reports_dialog",
        lambda: calls.append(1),
    )
    main_window.ui_manager.set_export_enabled(False)
    main_window.results_bridge.openExport()
    assert calls == []
    main_window.ui_manager.set_export_enabled(True)
    main_window.results_bridge.openExport()
    assert calls == [1]
    assert main_window.results_bridge.exportEnabled is True


def test_set_ui_busy_drives_the_pages_export(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.set_ui_busy(False)
    assert main_window.results_bridge.exportEnabled is True
    main_window.ui_manager.set_ui_busy(True)
    assert main_window.results_bridge.exportEnabled is False


def test_the_screen_menu_holds_add_product_and_undo(main_window):
    assert main_window.results_menu.actions() == [
        main_window.add_product_button_tab2,
        main_window.undo_button,
    ]


GUI = Path(__file__).resolve().parent.parent / "gui"
GONE = re.compile(
    r"tableView|proxy_model|order_detail_pane|tag_management_panel|filter_input"
    r"|filter_column_selector|case_sensitive_checkbox|tag_filter_combo|kpi_cards"
    r"|kpi_strip|update_results_table|update_kpi_strip|update_filter_count"
    r"|hidden_columns_indicator|configure_columns_button_tab2|_update_selection_bar_state"
)


def test_the_qt_results_screen_is_gone():
    hits = [
        f"{path.relative_to(GUI)}:{number}: {line.strip()}"
        for path in sorted(GUI.rglob("*.py"))
        if path.name != "session_browser_widget.py"  # its own filter_bar/selection_bar
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if GONE.search(line)
    ]
    assert hits == []


def test_results_binds_run_analysis_as_the_secondary_action(main_window):
    from PySide6.QtWidgets import QApplication

    bar = main_window.command_bar
    main_window.main_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert bar._bound_action is main_window.run_analysis_button
    assert bar.action_button.property("role") == "secondary"
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert bar.action_button.property("role") == "primary"


@pytest.mark.parametrize(
    "minutes, text",
    [
        (0, "0 min"),
        (59, "59 min"),
        (60, "1 h"),
        (47 * 60 + 59, "47 h"),
        (48 * 60, "2 d"),
    ],
)
def test_age_text(minutes, text):
    from datetime import timedelta

    from gui.ui_manager import age_text

    assert age_text(timedelta(minutes=minutes)) == text


def test_session_chips_read_the_analysis_and_the_stock_copy(
    main_window, tmp_path, monkeypatch
):
    import os
    from datetime import datetime, timedelta

    analysed = datetime(2026, 9, 2, 9, 33).astimezone()
    stock = tmp_path / "input" / "inventory.csv"
    stock.parent.mkdir()
    stock.write_text("sku\n", encoding="utf-8")
    stamp = (analysed - timedelta(hours=19)).timestamp()
    os.utime(stock, (stamp, stamp))
    manager = main_window.session_manager
    monkeypatch.setattr(
        manager,
        "get_session_info",
        lambda _path: {"analysis_completed_at": analysed.isoformat()},
    )
    monkeypatch.setattr(manager, "get_input_dir", lambda _path: tmp_path / "input")
    main_window.session_path = str(tmp_path)

    main_window.ui_manager.update_session_chips()

    assert main_window.command_bar.status_chip.text() == "Analysed 09:33"
    assert main_window.command_bar.stock_chip.text() == "Stock file 19 h old"


def test_session_chips_blank_without_an_analysis(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr(
        main_window.session_manager, "get_session_info", lambda _path: {}
    )
    main_window.session_path = str(tmp_path)
    main_window.ui_manager.update_session_chips()
    assert main_window.command_bar.status_chip.text() == ""
    assert main_window.command_bar.stock_chip.text() == ""
