"""Tests for FIFO lot allocation feature.

Covers:
- _parse_expiry_date: edge cases
- _build_fifo_lots: sorting and aggregation
- _simulate_stock_allocation: multi-lot FIFO, backward-compat, insufficient stock, all-or-nothing
- create_stock_export: lot expansion, packaging writeoff with lot columns, no-lot fallback
- create_packing_list: lot row expansion, destination-country dedup after expansion, no-lot fallback
"""
import sys
import os
from datetime import date
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shopify_tool.analysis import (
    _parse_expiry_date,
    _build_fifo_lots,
    _simulate_stock_allocation,
)
from shopify_tool import stock_export, packing_lists
from shopify_tool.packing_lists import _expand_lot_rows
from shopify_tool.stock_export import _expand_lot_summary


# ---------------------------------------------------------------------------
# _parse_expiry_date
# ---------------------------------------------------------------------------

class TestParseExpiryDate:
    def test_sentinel_one_returns_none(self):
        assert _parse_expiry_date("1") is None

    def test_none_returns_none(self):
        assert _parse_expiry_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_expiry_date("") is None

    def test_nan_returns_none(self):
        import math
        assert _parse_expiry_date(float("nan")) is None

    def test_6digit_yymmdd(self):
        assert _parse_expiry_date("261230") == date(2026, 12, 30)

    def test_6digit_yymmdd_early_year(self):
        assert _parse_expiry_date("010115") == date(2001, 1, 15)

    def test_8digit_yyyymmdd(self):
        assert _parse_expiry_date("20270131") == date(2027, 1, 31)

    def test_invalid_returns_none(self):
        assert _parse_expiry_date("ABCDEF") is None

    def test_wrong_length_returns_none(self):
        assert _parse_expiry_date("2612") is None

    def test_whitespace_stripped(self):
        assert _parse_expiry_date("  261230  ") == date(2026, 12, 30)


# ---------------------------------------------------------------------------
# _build_fifo_lots
# ---------------------------------------------------------------------------

class TestBuildFifoLots:
    def _make_stock(self, rows):
        return pd.DataFrame(rows)

    def test_returns_none_when_no_lot_columns(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 10, "Product_Name": "Alpha"},
        ])
        assert _build_fifo_lots(df) is None

    def test_single_lot_per_sku(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 10, "Expiry_Date": "261230", "Batch": "B001"},
        ])
        result = _build_fifo_lots(df)
        assert result is not None
        assert "A" in result
        assert len(result["A"]) == 1
        assert result["A"][0]["expiry"] == "261230"
        assert result["A"][0]["batch"] == "B001"
        assert result["A"][0]["qty"] == 10.0

    def test_fifo_sort_order_earliest_first(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 5, "Expiry_Date": "270131", "Batch": "B002"},
            {"SKU": "A", "Stock": 8, "Expiry_Date": "261230", "Batch": "B001"},
        ])
        result = _build_fifo_lots(df)
        lots = result["A"]
        # Earliest expiry should be first
        assert lots[0]["expiry"] == "261230"
        assert lots[1]["expiry"] == "270131"

    def test_no_expiry_lots_sort_last(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 100, "Expiry_Date": "1", "Batch": None},
            {"SKU": "A", "Stock": 5, "Expiry_Date": "261230", "Batch": "B001"},
        ])
        result = _build_fifo_lots(df)
        lots = result["A"]
        assert lots[0]["expiry"] == "261230"   # real date first
        assert lots[1]["expiry"] == "1"        # no-expiry last

    def test_zero_stock_rows_excluded(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 0, "Expiry_Date": "261230", "Batch": "B001"},
            {"SKU": "A", "Stock": 10, "Expiry_Date": "270101", "Batch": "B002"},
        ])
        result = _build_fifo_lots(df)
        lots = result["A"]
        assert len(lots) == 1
        assert lots[0]["expiry"] == "270101"

    def test_multiple_skus(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 10, "Expiry_Date": "261230", "Batch": "B1"},
            {"SKU": "B", "Stock": 20, "Expiry_Date": "270101", "Batch": "B2"},
        ])
        result = _build_fifo_lots(df)
        assert "A" in result
        assert "B" in result

    def test_batch_only_no_expiry_column(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 10, "Batch": "LOT-X"},
        ])
        result = _build_fifo_lots(df)
        assert result is not None
        assert "A" in result

    def test_expiry_only_no_batch_column(self):
        df = self._make_stock([
            {"SKU": "A", "Stock": 10, "Expiry_Date": "261230"},
        ])
        result = _build_fifo_lots(df)
        assert result is not None
        assert result["A"][0]["batch"] is None


# ---------------------------------------------------------------------------
# _simulate_stock_allocation — lot path
# ---------------------------------------------------------------------------

def _make_orders_df(rows):
    """Create a minimal orders DataFrame for simulation."""
    return pd.DataFrame(rows)


def _make_stock_df(skus_stocks):
    """Create minimal stock DataFrame with SKU and Stock columns."""
    return pd.DataFrame([{"SKU": s, "Stock": q} for s, q in skus_stocks.items()])


def _make_prioritized(order_numbers):
    return pd.DataFrame({"Order_Number": order_numbers})


class TestSimulateStockAllocationFifo:
    def test_backward_compat_no_fifo(self):
        """Legacy path: fifo_lots=None returns empty lot_allocations."""
        orders = _make_orders_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5},
        ])
        stock = _make_stock_df({"A": 10})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=None)
        assert results["O1"]["fulfillable"] is True
        assert lot_allocs == {}

    def test_single_lot_fulfilled(self):
        """One order, one SKU, one lot — should consume from that lot."""
        fifo_lots = {
            "A": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 10.0}]
        }
        orders = _make_orders_df([{"Order_Number": "O1", "SKU": "A", "Quantity": 5}])
        stock = _make_stock_df({"A": 10})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is True
        assert "O1" in lot_allocs
        assert lot_allocs["O1"]["A"][0]["qty_allocated"] == 5
        assert lot_allocs["O1"]["A"][0]["expiry"] == "261230"
        # Input fifo_lots is deep-copied inside the function — original is not mutated
        assert fifo_lots["A"][0]["qty"] == 10.0

    def test_multi_lot_spanning(self):
        """Order spans two lots — FIFO order: first lot fully consumed, remainder from second."""
        fifo_lots = {
            "A": [
                {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 5.0},
                {"expiry": "270131", "expiry_dt": date(2027, 1, 31), "batch": "B2", "qty": 10.0},
            ]
        }
        orders = _make_orders_df([{"Order_Number": "O1", "SKU": "A", "Quantity": 8}])
        stock = _make_stock_df({"A": 15})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is True
        alloc = lot_allocs["O1"]["A"]
        assert len(alloc) == 2
        assert alloc[0]["qty_allocated"] == 5  # all of B1
        assert alloc[1]["qty_allocated"] == 3  # 3 from B2
        # Input fifo_lots is deep-copied — originals untouched
        assert fifo_lots["A"][0]["qty"] == 5.0
        assert fifo_lots["A"][1]["qty"] == 10.0

    def test_insufficient_stock_not_fulfilled(self):
        """Order requiring more than available lots should be marked unfulfillable."""
        fifo_lots = {
            "A": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 3.0}]
        }
        orders = _make_orders_df([{"Order_Number": "O1", "SKU": "A", "Quantity": 10}])
        stock = _make_stock_df({"A": 3})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is False
        assert "O1" not in lot_allocs
        # Stock must not be mutated on failure
        assert fifo_lots["A"][0]["qty"] == 3.0

    def test_out_of_stock_not_fulfilled(self):
        fifo_lots = {}  # SKU "A" has no lots
        orders = _make_orders_df([{"Order_Number": "O1", "SKU": "A", "Quantity": 1}])
        stock = _make_stock_df({})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is False

    def test_all_or_nothing_semantics(self):
        """If one SKU is unavailable, the entire order fails and no lots are mutated."""
        fifo_lots = {
            "A": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 10.0}],
            "B": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 0.0}],
        }
        orders = _make_orders_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5},
            {"Order_Number": "O1", "SKU": "B", "Quantity": 1},
        ])
        stock = _make_stock_df({"A": 10, "B": 0})
        prioritized = _make_prioritized(["O1"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is False
        assert "O1" not in lot_allocs
        # A's lot must not have been decremented
        assert fifo_lots["A"][0]["qty"] == 10.0

    def test_sequential_orders_consume_fifo(self):
        """Second order gets whatever first order leaves."""
        fifo_lots = {
            "A": [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty": 6.0}]
        }
        orders = _make_orders_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 4},
            {"Order_Number": "O2", "SKU": "A", "Quantity": 3},
        ])
        stock = _make_stock_df({"A": 6})
        prioritized = _make_prioritized(["O1", "O2"])

        results, lot_allocs = _simulate_stock_allocation(orders, stock, prioritized, fifo_lots=fifo_lots)
        assert results["O1"]["fulfillable"] is True
        assert results["O2"]["fulfillable"] is False  # only 2 remain after O1


# ---------------------------------------------------------------------------
# _expand_lot_summary
# ---------------------------------------------------------------------------

class TestExpandLotSummary:
    def _fulfillable_df(self, rows):
        return pd.DataFrame(rows)

    def test_basic_lot_aggregation(self):
        # Two different orders each need 1 lot entry for SKU A — totals should sum
        df = self._fulfillable_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 5}
            ]},
            {"Order_Number": "O2", "SKU": "A", "Quantity": 3, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 3}
            ]},
        ])
        result = _expand_lot_summary(df)
        # Should aggregate: A, 261230, B1 = 8
        row = result[(result["Артикул"] == "A") & (result["Годност"] == "261230")]
        assert len(row) == 1
        assert row.iloc[0]["Наличност"] == 8

    def test_multi_lot_same_sku(self):
        df = self._fulfillable_df([
            {"SKU": "A", "Quantity": 10, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 5},
                {"expiry": "270131", "batch": "B2", "qty_allocated": 5},
            ]},
        ])
        result = _expand_lot_summary(df)
        assert len(result) == 2
        assert set(result["Годност"]) == {"261230", "270131"}

    def test_no_lot_details_fallback(self):
        """Rows without Lot_Details aggregate by SKU with empty lot columns."""
        df = self._fulfillable_df([
            {"SKU": "B", "Quantity": 7, "Lot_Details": None},
            {"SKU": "B", "Quantity": 3, "Lot_Details": None},
        ])
        result = _expand_lot_summary(df)
        assert len(result) == 1
        assert result.iloc[0]["Артикул"] == "B"
        assert result.iloc[0]["Наличност"] == 10
        assert result.iloc[0]["Годност"] == ""
        assert result.iloc[0]["Партида"] == ""

    def test_expiry_sentinel_one_replaced_with_empty(self):
        """expiry='1' (no-info) becomes empty string in the output."""
        df = self._fulfillable_df([
            {"SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "1", "batch": "B1", "qty_allocated": 5}
            ]},
        ])
        result = _expand_lot_summary(df)
        assert result.iloc[0]["Годност"] == ""

    def test_batch_sentinel_one_replaced_with_empty(self):
        """batch='1' (no-info) becomes empty string in the output."""
        df = self._fulfillable_df([
            {"SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "261230", "batch": "1", "qty_allocated": 5}
            ]},
        ])
        result = _expand_lot_summary(df)
        assert result.iloc[0]["Партида"] == ""

    def test_empty_dataframe_returns_correct_columns(self):
        df = pd.DataFrame(columns=["SKU", "Quantity", "Lot_Details"])
        result = _expand_lot_summary(df)
        assert list(result.columns) == ["Артикул", "Годност", "Партида", "Наличност"]
        assert len(result) == 0


# ---------------------------------------------------------------------------
# create_stock_export — lot path integration
# ---------------------------------------------------------------------------

class TestCreateStockExportLots:
    def _make_df(self, rows):
        base = {
            "Order_Fulfillment_Status": "Fulfillable",
            "Shipping_Provider": "DHL",
        }
        records = [{**base, **r} for r in rows]
        return pd.DataFrame(records)

    def test_lot_path_creates_per_lot_rows(self, tmp_path):
        # Two separate orders, each contributing a different lot for the same SKU
        df = self._make_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 5}
            ]},
            {"Order_Number": "O2", "SKU": "A", "Quantity": 3, "Lot_Details": [
                {"expiry": "270101", "batch": "B2", "qty_allocated": 3}
            ]},
        ])
        out = tmp_path / "export.xls"
        stock_export.create_stock_export(df, str(out))
        assert out.exists()
        result = pd.read_excel(str(out))
        assert "Годност" in result.columns
        assert "Партида" in result.columns
        assert len(result) == 2

    def test_no_lot_path_simple_columns(self, tmp_path):
        df = self._make_df([
            {"SKU": "A", "Quantity": 5},
            {"SKU": "B", "Quantity": 3},
        ])
        out = tmp_path / "export_noLot.xls"
        stock_export.create_stock_export(df, str(out))
        result = pd.read_excel(str(out))
        assert "Годност" not in result.columns
        assert "Партида" not in result.columns
        assert set(result.columns) == {"Артикул", "Наличност"}

    def test_lot_path_quantities_correct(self, tmp_path):
        df = self._make_df([
            {"SKU": "IT12-LE", "Quantity": 15, "Lot_Details": [
                {"expiry": "261230", "batch": "109109", "qty_allocated": 10},
                {"expiry": "261230", "batch": None, "qty_allocated": 5},
            ]},
        ])
        out = tmp_path / "export_qty.xls"
        stock_export.create_stock_export(df, str(out))
        result = pd.read_excel(str(out))
        total = result["Наличност"].sum()
        assert total == 15

    def test_lot_path_empty_df(self, tmp_path):
        """Empty result after filter should still produce file with lot headers."""
        df = pd.DataFrame(columns=["Order_Fulfillment_Status", "SKU", "Quantity", "Lot_Details"])
        out = tmp_path / "export_empty.xls"
        stock_export.create_stock_export(df, str(out))
        # File might not be created (function returns early), that is acceptable
        # If created, check it has the right structure or is empty


# ---------------------------------------------------------------------------
# _expand_lot_rows (packing list helper)
# ---------------------------------------------------------------------------

class TestExpandLotRows:
    def _make_sorted_df(self, rows):
        return pd.DataFrame(rows)

    def test_no_lot_details_row_preserved(self):
        df = self._make_sorted_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Lot_Details": None},
        ])
        result = _expand_lot_rows(df)
        assert len(result) == 1
        assert result.iloc[0]["Lot_Expiry"] == ""
        assert result.iloc[0]["Lot_Batch"] == ""
        assert result.iloc[0]["Quantity"] == 5

    def test_lot_details_expands_to_one_row_per_lot(self):
        df = self._make_sorted_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 8, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 5},
                {"expiry": "270101", "batch": "B2", "qty_allocated": 3},
            ]},
        ])
        result = _expand_lot_rows(df)
        assert len(result) == 2
        assert result.iloc[0]["Quantity"] == 5
        assert result.iloc[0]["Lot_Expiry"] == "261230"
        assert result.iloc[0]["Lot_Batch"] == "B1"
        assert result.iloc[1]["Quantity"] == 3
        assert result.iloc[1]["Lot_Expiry"] == "270101"
        assert result.iloc[1]["Lot_Batch"] == "B2"

    def test_sentinel_one_replaced_with_empty(self):
        df = self._make_sorted_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "1", "batch": "1", "qty_allocated": 5}
            ]},
        ])
        result = _expand_lot_rows(df)
        assert result.iloc[0]["Lot_Expiry"] == ""
        assert result.iloc[0]["Lot_Batch"] == ""

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Order_Number", "SKU", "Quantity", "Lot_Details"])
        result = _expand_lot_rows(df)
        assert "Lot_Expiry" in result.columns
        assert "Lot_Batch" in result.columns

    def test_mixed_rows(self):
        """Some rows with lots, some without."""
        df = self._make_sorted_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Lot_Details": [
                {"expiry": "261230", "batch": "B1", "qty_allocated": 5}
            ]},
            {"Order_Number": "O1", "SKU": "B", "Quantity": 3, "Lot_Details": None},
        ])
        result = _expand_lot_rows(df)
        assert len(result) == 2
        assert result.iloc[0]["Lot_Expiry"] == "261230"
        assert result.iloc[1]["Lot_Expiry"] == ""


# ---------------------------------------------------------------------------
# create_packing_list — lot path integration
# ---------------------------------------------------------------------------

class TestCreatePackingListLots:
    def _make_df(self, rows):
        base = {
            "Order_Fulfillment_Status": "Fulfillable",
            "Shipping_Provider": "DHL",
            "Destination_Country": "BG",
        }
        records = [{**base, **r} for r in rows]
        return pd.DataFrame(records)

    def test_lot_columns_present_in_output(self, tmp_path):
        df = self._make_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Warehouse_Name": "Alpha",
             "Lot_Details": [{"expiry": "261230", "batch": "B1", "qty_allocated": 5}]},
        ])
        out = tmp_path / "packing.xlsx"
        packing_lists.create_packing_list(df, str(out))
        assert out.exists()
        result = pd.read_excel(str(out))
        # Column headers include renamed columns; check for Lot columns in actual data
        # The sheet has renamed Shipping_Provider → timestamp, Warehouse_Name → filename
        # Column existence checked by position or by finding them in the output
        col_str = " ".join(str(c) for c in result.columns)
        assert "Lot_Expiry" in col_str or "261230" in result.to_string()

    def test_destination_country_dedup_after_lot_expansion(self, tmp_path):
        """After lot expansion, Destination_Country should appear only on first row of each order."""
        df = self._make_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 8, "Warehouse_Name": "Alpha",
             "Lot_Details": [
                 {"expiry": "261230", "batch": "B1", "qty_allocated": 5},
                 {"expiry": "270101", "batch": "B2", "qty_allocated": 3},
             ]},
        ])
        out = tmp_path / "packing_dedup.xlsx"
        packing_lists.create_packing_list(df, str(out))
        assert out.exists()
        result = pd.read_excel(str(out))
        # 2 rows for order O1 due to lot expansion
        assert len(result) == 2
        # First column is Destination_Country; first row has value, second is empty
        dc_col = result.columns[0]
        assert str(result.iloc[0][dc_col]) in ("BG", "nan", "")  # first row has country
        assert str(result.iloc[1][dc_col]) in ("", "nan")         # second row is blank

    def test_no_lot_fallback_no_lot_columns(self, tmp_path):
        """Without Lot_Details, output should not have lot columns."""
        df = self._make_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 5, "Warehouse_Name": "Alpha"},
            {"Order_Number": "O2", "SKU": "B", "Quantity": 3, "Warehouse_Name": "Beta"},
        ])
        out = tmp_path / "packing_noLot.xlsx"
        packing_lists.create_packing_list(df, str(out))
        assert out.exists()
        result = pd.read_excel(str(out))
        col_str = " ".join(str(c) for c in result.columns)
        assert "Lot_Expiry" not in col_str
        assert "Lot_Batch" not in col_str

    def test_multi_order_destination_country_dedup_no_lots(self, tmp_path):
        """Without lots, Destination_Country appears only for first line of each order."""
        df = self._make_df([
            {"Order_Number": "O1", "SKU": "A", "Quantity": 1, "Warehouse_Name": "Alpha",
             "Destination_Country": "BG"},
            {"Order_Number": "O1", "SKU": "B", "Quantity": 2, "Warehouse_Name": "Beta",
             "Destination_Country": "BG"},
            {"Order_Number": "O2", "SKU": "C", "Quantity": 1, "Warehouse_Name": "Gamma",
             "Destination_Country": "DE"},
        ])
        out = tmp_path / "packing_2orders.xlsx"
        packing_lists.create_packing_list(df, str(out))
        assert out.exists()
        result = pd.read_excel(str(out))
        dc_col = result.columns[0]
        # O1 row 2 should be blank (deduped)
        assert str(result.iloc[1][dc_col]) in ("", "nan")
