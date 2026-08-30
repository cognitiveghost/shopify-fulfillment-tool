"""Spec §9 tests 10-14: the restyled Analysis Results screen."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.orders_view import HIDDEN_COLUMNS
from gui.status_edge_delegate import StatusEdgeDelegate


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lines_df():
    """3 orders / 4 lines / 8 items. 1 fulfillable, 2 blocked, 1003 a repeat."""
    return pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "AAA", "Quantity": 2,
             "System_note": "", "Internal_Tags": "[]"},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "BBB", "Quantity": 1,
             "System_note": "", "Internal_Tags": "[]"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "SKU": "CCC", "Quantity": 4,
             "System_note": "Cannot fulfill: insufficient stock for CCC",
             "Internal_Tags": "[]"},
            {"Order_Number": "1003", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "DDD", "Quantity": 1,
             "System_note": "Repeat customer; Cannot fulfill: out of stock",
             "Internal_Tags": "[]"},
        ]
    )


@pytest.fixture
def main_window(app):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


@pytest.fixture
def loaded(main_window, lines_df):
    """The window with the frame loaded, exactly as _update_all_views does it."""
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)
    main_window.ui_manager.update_kpi_strip()
    return main_window


def test_both_tables_paint_the_status_edge(loaded):
    assert isinstance(loaded.tableView.itemDelegate(), StatusEdgeDelegate)
    lines = loaded.order_detail_pane.lines_table
    assert isinstance(lines.itemDelegate(), StatusEdgeDelegate)


def test_the_derived_columns_are_hidden_from_the_table(loaded):
    orders_df = loaded.orders_df
    for name in HIDDEN_COLUMNS:
        assert name in orders_df.columns
        column = orders_df.columns.get_loc(name)
        assert loaded.tableView.isColumnHidden(column)


def test_the_derived_columns_are_not_offered_as_filter_scopes(loaded):
    selector = loaded.filter_column_selector
    offered = {selector.itemData(i) for i in range(selector.count())}
    for name in HIDDEN_COLUMNS:
        assert name not in offered
