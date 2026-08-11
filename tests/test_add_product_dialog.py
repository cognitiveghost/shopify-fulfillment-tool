"""Regression test: Add Product to Order dialog drops the static info box
and consolidates its three QGroupBox sections into one QFormLayout (Phase 5
Item 3) -- the live status labels and stock-warning box keep working
unchanged since the backend behavior they describe wasn't touched.
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from gui.add_product_dialog import AddProductDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog():
    analysis_df = pd.DataFrame([
        {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"},
    ])
    stock_df = pd.DataFrame([
        {"SKU": "SKU-A", "Product_Name": "Widget A"},
    ])
    live_stock = {"SKU-A": 2}
    dlg = AddProductDialog(None, analysis_df, stock_df, live_stock)
    # isVisible() on a child only reflects reality once the top-level widget
    # itself has been shown -- otherwise it's always False regardless of
    # setVisible() calls on the child.
    dlg.show()
    return dlg


def test_info_box_and_group_boxes_are_gone(dialog):
    assert not hasattr(dialog, "info_box")
    assert dialog.findChildren(QGroupBox) == []


def test_order_status_label_still_updates(dialog):
    dialog.order_input.setText("1001")
    assert "Order found" in dialog.order_status_label.text()


def test_low_stock_warning_still_shows(dialog):
    dialog.sku_input.setText("SKU-A")
    assert dialog.warning_box.isVisible()
    assert "low stock" in dialog.warning_box.text().lower()
