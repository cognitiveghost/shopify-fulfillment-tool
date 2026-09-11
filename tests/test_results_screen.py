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
