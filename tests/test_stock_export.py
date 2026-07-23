"""Stock write-off export accuracy (priority: export generation accuracy).

Output columns are positional (Артикул, blank spacer, Мярка, Брой, Годност,
Партида) -- the warehouse ERP auto-detects them by position, so tests read
back by column index rather than by header name.
"""
import pandas as pd
import pytest

from shopify_tool.stock_export import create_stock_export, merge_session_stock_exports

COL_SKU, COL_BLANK, COL_UNIT, COL_QTY, COL_EXPIRY, COL_BATCH = range(6)


def _analysis_df(rows):
    defaults = {
        "Order_Number": "#1", "SKU": "A1", "Quantity": 1,
        "Order_Fulfillment_Status": "Fulfillable", "Lot_Details": None,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _read(path):
    return pd.read_excel(path, header=0, engine="xlrd")


class TestBasicExport:
    def test_only_fulfillable_rows_summed_by_sku(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 3, "Order_Fulfillment_Status": "Fulfillable"},
            {"Order_Number": "#2", "SKU": "A1", "Quantity": 2, "Order_Fulfillment_Status": "Fulfillable"},
            {"Order_Number": "#3", "SKU": "A1", "Quantity": 100, "Order_Fulfillment_Status": "Not Fulfillable"},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert len(result) == 1
        assert result.iloc[0, COL_SKU] == "A1"
        assert result.iloc[0, COL_QTY] == 5

    def test_canonical_column_layout(self, tmp_path):
        df = _analysis_df([{"SKU": "A1", "Quantity": 1}])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert result.iloc[0, COL_UNIT] == "брой"

    def test_multiple_skus_each_get_own_row(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 3},
            {"Order_Number": "#1", "SKU": "A2", "Quantity": 5},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        totals = dict(zip(result.iloc[:, COL_SKU], result.iloc[:, COL_QTY]))
        assert totals == {"A1": 3, "A2": 5}

    def test_custom_filter_applied(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 3, "Shipping_Provider": "DHL"},
            {"Order_Number": "#2", "SKU": "A2", "Quantity": 5, "Shipping_Provider": "DPD"},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), filters=[{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}])
        result = _read(out)
        assert list(result.iloc[:, COL_SKU]) == ["A1"]

    def test_empty_result_still_writes_canonical_headers(self, tmp_path):
        df = _analysis_df([{"Order_Fulfillment_Status": "Not Fulfillable"}])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert result.empty
        assert list(result.columns)[COL_UNIT] == "Мярка"


class TestLotAggregation:
    def test_lot_details_aggregated_per_expiry_batch(self, tmp_path):
        lot_details = [
            {"expiry": "260601", "batch": "B1", "qty_allocated": 3},
            {"expiry": "270101", "batch": "B2", "qty_allocated": 2},
        ]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 5, "Lot_Details": lot_details}])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert len(result) == 2
        assert result.iloc[:, COL_QTY].sum() == 5
        assert set(result.iloc[:, COL_EXPIRY].astype(str)) == {"260601", "270101"}

    def test_lot_sentinel_one_renders_blank(self, tmp_path):
        lot_details = [{"expiry": "1", "batch": "1", "qty_allocated": 4}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 4, "Lot_Details": lot_details}])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        expiry_val = result.iloc[0, COL_EXPIRY]
        assert expiry_val == "" or pd.isna(expiry_val)


class TestConfirmedBugs:
    @pytest.mark.xfail(
        strict=True,
        reason="BUG: _expand_lot_summary dedupes per-(order,SKU) allocations "
               "using key (Order_Number, SKU) to avoid double-counting a "
               "duplicated DataFrame row. When Order_Number is blank/missing "
               "for more than one Fulfillable row sharing a SKU, they all "
               "collapse to the same ('', SKU) key -- every allocation after "
               "the first is silently dropped from the write-off export, "
               "understating the real quantity to deduct from the ERP.",
    )
    def test_missing_order_number_does_not_drop_distinct_lot_allocations(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "", "SKU": "A1", "Quantity": 3,
             "Lot_Details": [{"expiry": "260601", "batch": None, "qty_allocated": 3}]},
            {"Order_Number": "", "SKU": "A1", "Quantity": 2,
             "Lot_Details": [{"expiry": "270101", "batch": None, "qty_allocated": 2}]},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert result.iloc[:, COL_QTY].sum() == 5  # currently only 3 (first row wins)


class TestMergeSessionStockExportsBug:
    """User-reported, fixed: merging stock exports from multiple sessions
    (session browser's "merge stock exports" action) used to not sum matching
    SKUs into one row -- the same SKU could appear on several rows."""

    def _write_session(self, session_dir, rows):
        analysis_dir = session_dir / "analysis"
        analysis_dir.mkdir(parents=True)
        df = pd.DataFrame([{
            "Order_Number": "#1", "SKU": "A1", "Quantity": 1,
            "Order_Fulfillment_Status": "Fulfillable", "Lot_Details": None,
            **row,
        } for row in rows])
        df.to_pickle(analysis_dir / "current_state.pkl")

    def test_same_sku_without_lot_tracking_sums_into_one_row(self, tmp_path):
        s1, s2 = tmp_path / "s1", tmp_path / "s2"
        self._write_session(s1, [{"SKU": "A1", "Quantity": 3}])
        self._write_session(s2, [{"SKU": "A1", "Quantity": 2}])
        result = merge_session_stock_exports([s1, s2], client_id="TEST")
        assert len(result[result.iloc[:, COL_SKU] == "A1"]) == 1
        assert result.iloc[0, COL_QTY] == 5

    def test_same_sku_from_different_lots_across_sessions_still_summed(self, tmp_path):
        s1, s2 = tmp_path / "s1", tmp_path / "s2"
        self._write_session(s1, [{
            "SKU": "A1", "Quantity": 3,
            "Lot_Details": [{"expiry": "260601", "batch": "B1", "qty_allocated": 3}],
        }])
        self._write_session(s2, [{
            "SKU": "A1", "Quantity": 2,
            "Lot_Details": [{"expiry": "270101", "batch": "B2", "qty_allocated": 2}],
        }])
        result = merge_session_stock_exports([s1, s2], client_id="TEST")
        a1_rows = result[result.iloc[:, COL_SKU] == "A1"]
        assert len(a1_rows) == 1
        assert a1_rows.iloc[0, COL_QTY] == 5
