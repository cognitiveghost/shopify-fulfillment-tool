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


def _dialog(live_stock, low_stock_threshold):
    analysis_df = pd.DataFrame([
        {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"},
    ])
    stock_df = pd.DataFrame([
        {"SKU": "SKU-1", "Product_Name": "Widget"},
    ])
    dlg = AddProductDialog(
        None, analysis_df, stock_df, live_stock,
        low_stock_threshold=low_stock_threshold,
    )
    dlg.show()
    return dlg


def test_the_low_stock_warning_follows_the_client_threshold(qapp):
    """The bug: the dialog hard-coded 5, so a client who set 12 saw no
    warning at 11 units."""
    dlg = _dialog({"SKU-1": 11}, low_stock_threshold=12)
    dlg.sku_input.setText("SKU-1")
    assert dlg.warning_box.isVisible()
    assert "low stock" in dlg.warning_box.text().lower()


def test_stock_at_the_threshold_is_not_low(qapp):
    dlg = _dialog({"SKU-1": 12}, low_stock_threshold=12)
    dlg.sku_input.setText("SKU-1")
    assert not dlg.warning_box.isVisible()


def test_zero_stock_still_warns_when_the_threshold_is_zero(qapp):
    """Zero stock and low stock are different sentences."""
    dlg = _dialog({"SKU-1": 0}, low_stock_threshold=0)
    dlg.sku_input.setText("SKU-1")
    assert dlg.warning_box.isVisible()
    assert "0 stock" in dlg.warning_box.text()
