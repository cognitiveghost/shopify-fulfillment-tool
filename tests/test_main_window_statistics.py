"""Regression test: SKU Summary table search box filters by SKU or product
substring (Phase 5 Item 2's "add sort/filter to the SKU table" gap).
"""
import pytest
from PySide6.QtCore import Qt
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


class _FakeStatsWindow:
    """Minimal stand-in for update_statistics_tab: every other block in that
    method is hasattr/getattr-guarded, so only these three attrs are needed.
    """

    def __init__(self, table, sku_summary):
        self.sku_table = table
        self.analysis_stats = {"sku_summary": sku_summary}
        self.active_profile_config = None


def test_sku_quantity_columns_sort_numerically():
    """Quantities must be stored as ints, not strings -- a str-built
    QTableWidgetItem sorts lexicographically and puts 10 before 2.
    """
    table = QTableWidget()
    table.setColumnCount(6)
    sku_summary = [
        {"SKU": "SKU-A", "Product_Name": "A", "Total_Quantity": 2},
        {"SKU": "SKU-B", "Product_Name": "B", "Total_Quantity": 10},
        {"SKU": "SKU-C", "Product_Name": "C", "Total_Quantity": 9},
    ]

    MainWindow.update_statistics_tab(_FakeStatsWindow(table, sku_summary))
    table.sortItems(3)

    sorted_qtys = [table.item(r, 3).data(Qt.DisplayRole) for r in range(3)]
    assert sorted_qtys == [2, 9, 10]


def test_missing_quantity_falls_back_to_zero():
    table = QTableWidget()
    table.setColumnCount(6)
    sku_summary = [{"SKU": "SKU-A", "Product_Name": "A"}]

    MainWindow.update_statistics_tab(_FakeStatsWindow(table, sku_summary))

    assert table.item(0, 3).data(Qt.DisplayRole) == 0
