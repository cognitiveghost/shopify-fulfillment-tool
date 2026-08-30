"""Widget-level tests for Analysis Results 1b (spec §10 tests 9-11)."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.order_detail_pane import OrderDetailPane
from gui.orders_view import order_lines, orders_frame


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lines_df():
    return pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "Destination_Country": "DE",
             "SKU": "AAA", "Product_Name": "Widget", "Quantity": 2,
             "System_note": "", "Notes": "leave at door", "Internal_Tags": "[]"},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "Destination_Country": "DE",
             "SKU": "BBB", "Product_Name": "Gadget", "Quantity": 1,
             "System_note": "", "Notes": "leave at door", "Internal_Tags": "[]"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "Destination_Country": "FR",
             "SKU": "CCC", "Product_Name": "Doohickey", "Quantity": 4,
             "System_note": "Cannot fulfill: insufficient stock for CCC",
             "Notes": "", "Internal_Tags": "[]"},
        ]
    )


def test_pane_shows_the_orders_lines(app, lines_df):
    """Spec §10 test 11."""
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)

    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))

    assert "1001" in pane.header_label.text()
    assert pane.lines_table.model().rowCount() == 2
    assert pane.tag_panel.selected_order == "1001"


def test_pane_shows_the_blocker_only_when_there_is_one(app, lines_df):
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)

    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))
    assert not pane.blocker_label.isVisible() or pane.blocker_label.text() == ""

    pane.set_order("1002", orders.loc["1002"], order_lines(lines_df, "1002"))
    assert "insufficient stock for CCC" in pane.blocker_label.text()


def test_pane_clear_empties_everything(app, lines_df):
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)
    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))

    pane.clear()

    assert pane.lines_table.model() is None or pane.lines_table.model().rowCount() == 0
    assert pane.tag_panel.selected_order is None
