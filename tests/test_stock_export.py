"""Stock write-off export accuracy (priority: export generation accuracy).

Output columns are positional (Артикул, blank spacer, Мярка, Брой, Годност,
Партида) -- the warehouse ERP auto-detects them by position, so tests read
back by column index rather than by header name.
"""
import pandas as pd

from shopify_tool.stock_export import (
    _finalize_export_df,
    _to_erp_quantity,
    create_stock_export,
    merge_session_stock_exports,
)

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

    def test_fractional_lot_quantity_rounds_instead_of_truncating(self, tmp_path):
        # The lot path built its rows with int(qty), which truncated BEFORE
        # _finalize_export_df could round -- the finalizer cannot recover a
        # fraction that was already thrown away.
        lot_details = [{"expiry": "260601", "batch": "B1", "qty_allocated": 1.5}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 1.5, "Lot_Details": lot_details}])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out))
        result = _read(out)
        assert result.iloc[0, COL_QTY] == 2


class TestConfirmedBugs:
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


class TestQuantityRounding:
    def test_rounds_half_up_not_half_to_even(self):
        # pandas/numpy .round() is banker's rounding: 0.5 -> 0 and 2.5 -> 2, which
        # leaves the exact bug this helper exists to fix. Half-up is required.
        result = _to_erp_quantity(pd.Series([0.5, 1.5, 2.5, 3.5]))
        assert list(result) == [1, 2, 3, 4]

    def test_rounds_down_below_the_half(self):
        result = _to_erp_quantity(pd.Series([0.4, 0.49, 1.2, 2.499]))
        assert list(result) == [0, 0, 1, 2]

    def test_whole_numbers_are_unchanged(self):
        result = _to_erp_quantity(pd.Series([0.0, 1.0, 7.0, 100.0]))
        assert list(result) == [0, 1, 7, 100]

    def test_non_numeric_and_missing_become_zero(self):
        result = _to_erp_quantity(pd.Series([1.6, None, "abc"]))
        assert list(result) == [2, 0, 0]

    def test_negative_quantities_clip_to_zero(self):
        result = _to_erp_quantity(pd.Series([-3.0, -0.4]))
        assert list(result) == [0, 0]

    def test_finalize_rounds_the_quantity_column(self):
        df = pd.DataFrame({"Артикул": ["A1", "A2"], "Брой": [1.5, 2.5]})
        result = _finalize_export_df(df)
        assert list(result["Брой"]) == [2, 3]

    def test_finalize_drops_rows_that_round_to_zero(self):
        df = pd.DataFrame({"Артикул": ["KEEP", "DROP"], "Брой": [1.0, 0.15]})
        result = _finalize_export_df(df)
        assert list(result["Артикул"]) == ["KEEP"]

    def test_finalize_logs_the_sku_it_dropped(self, caplog):
        df = pd.DataFrame({"Артикул": ["PKG-TAPE"], "Брой": [0.15]})
        with caplog.at_level("WARNING", logger="ShopifyToolLogger"):
            _finalize_export_df(df)
        assert "PKG-TAPE" in caplog.text

    def test_finalize_stays_idempotent(self):
        df = pd.DataFrame({"Артикул": ["A1"], "Брой": [2.5]})
        once = _finalize_export_df(df)
        twice = _finalize_export_df(once)
        assert list(twice["Брой"]) == [3]
        assert list(once.columns) == list(twice.columns)
        assert len(twice) == 1

    def test_finalize_handles_an_empty_frame(self):
        from shopify_tool.stock_export import _empty_export_df

        result = _finalize_export_df(_empty_export_df())
        assert result.empty
        assert list(result.columns) == list(_empty_export_df().columns)

    def test_fractional_writeoff_on_a_single_order_is_not_lost(self, tmp_path):
        # The headline bug: 0.5 boxes for one order truncated to 0 and the packaging
        # material vanished from the export entirely.
        config = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 0.5}]},
                    },
                }
            },
        }
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), apply_writeoff=True, tag_categories=config)
        result = _read(out)
        packaging = result[result.iloc[:, COL_SKU] == "PKG-BOX"]
        assert len(packaging) == 1
        assert packaging.iloc[0, COL_QTY] == 1

    def test_fractional_writeoff_across_three_orders_rounds_up(self, tmp_path):
        config = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 0.5}]},
                    },
                }
            },
        }
        # 3 orders x 0.5 = 1.5 -> 2. Truncation gave 1.
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
            {"Order_Number": "#2", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
            {"Order_Number": "#3", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), apply_writeoff=True, tag_categories=config)
        result = _read(out)
        packaging = result[result.iloc[:, COL_SKU] == "PKG-BOX"]
        assert packaging.iloc[0, COL_QTY] == 2

    def test_no_zero_quantity_cell_ever_reaches_the_file(self, tmp_path):
        # The warehouse ERP REJECTS a row whose quantity is 0, so this is a hard
        # requirement of the file format, not a tidiness rule. Before the rounding
        # fix a 0.5-per-order write-off truncated to 0 and was written as a 0 cell.
        # A 0.4 rate still rounds to 0 -- that row must be absent, not zeroed.
        config = {
            "version": 2,
            "categories": {
                "packaging": {
                    "tags": ["BOX"],
                    "sku_writeoff": {
                        "enabled": True,
                        "mappings": {"BOX": [{"sku": "PKG-TAPE", "quantity": 0.4}]},
                    },
                }
            },
        }
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 1, "Internal_Tags": '["BOX"]'},
        ])
        out = tmp_path / "export.xls"
        create_stock_export(df, str(out), apply_writeoff=True, tag_categories=config)
        result = _read(out)
        assert "PKG-TAPE" not in set(result.iloc[:, COL_SKU])
        assert (result.iloc[:, COL_QTY] > 0).all()


def test_not_in_filter_excludes_the_listed_skus(tmp_path):
    """stock_export.py carried a verbatim copy of the packing-list query
    builder, so it carried the same defect."""
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Final_Stock": [10, 20, 30],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })
    out = tmp_path / "notin.xls"

    create_stock_export(df, str(out),
                        filters=[{"field": "SKU", "operator": "not in", "value": "AB-01,CD-02"}])

    written = pd.read_excel(out)
    assert "AB-01" not in written.to_string()
    assert "CD-02" not in written.to_string()
    assert "EF-03" in written.to_string()
