"""Regression test: SKU Summary table search box filters by SKU or product
substring (Phase 5 Item 2's "add sort/filter to the SKU table" gap).
"""
import pytest
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from gui.main_window_pyside import MainWindow


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _make_sku_table(rows):
    table = QTableWidget()
    table.setColumnCount(3)
    for row_idx, (sku, product) in enumerate(rows):
        table.insertRow(row_idx)
        table.setItem(row_idx, 1, QTableWidgetItem(sku))
        table.setItem(row_idx, 2, QTableWidgetItem(product))
    return table


class _FakeMainWindow:
    def __init__(self, table):
        self.sku_table = table


def test_sku_search_hides_non_matching_rows():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "gadget")

    assert table.isRowHidden(0) is True
    assert table.isRowHidden(1) is False


def test_sku_search_matches_by_sku_too():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "sku-a")

    assert table.isRowHidden(0) is False
    assert table.isRowHidden(1) is True


def test_empty_search_shows_all_rows():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "")

    assert table.isRowHidden(0) is False
    assert table.isRowHidden(1) is False
