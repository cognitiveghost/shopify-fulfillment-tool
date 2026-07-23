"""Packing list export accuracy: output must exactly reflect the analysis
DataFrame (priority: packing list / export generation accuracy)."""
import pandas as pd

from shopify_tool.packing_lists import create_packing_list


def _analysis_df(rows):
    """Build a final_df-shaped DataFrame with sane defaults for every row."""
    defaults = {
        "Order_Number": "#1", "SKU": "A1", "Product_Name": "Widget",
        "Warehouse_Name": "Widget WH", "Quantity": 1, "Stock": 10, "Final_Stock": 9,
        "Order_Fulfillment_Status": "Fulfillable", "Shipping_Provider": "DHL",
        "Destination_Country": "DE", "Lot_Details": None,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _read_output(path):
    return pd.read_excel(path)


class TestFilteringAndExclusion:
    def test_only_fulfillable_rows_included(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Order_Fulfillment_Status": "Fulfillable"},
            {"Order_Number": "#2", "SKU": "A2", "Order_Fulfillment_Status": "Not Fulfillable"},
        ])
        out = tmp_path / "list.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        assert list(result["Order_Number"]) == ["#1"]

    def test_custom_filter_by_provider(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Shipping_Provider": "DHL"},
            {"Order_Number": "#2", "SKU": "A2", "Shipping_Provider": "DPD"},
        ])
        out = tmp_path / "dhl_only.xlsx"
        create_packing_list(df, str(out), filters=[{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}])
        result = _read_output(out)
        assert list(result["Order_Number"]) == ["#1"]

    def test_exclude_skus_matches_leading_zero_variants(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "07"},
            {"Order_Number": "#1", "SKU": "A2"},
        ])
        out = tmp_path / "excl.xlsx"
        create_packing_list(df, str(out), exclude_skus=["7"])  # "7" should match SKU "07"
        result = _read_output(out)
        assert list(result["SKU"]) == ["A2"]

    def test_no_matching_rows_does_not_create_file(self, tmp_path):
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Order_Fulfillment_Status": "Not Fulfillable"}])
        out = tmp_path / "empty.xlsx"
        create_packing_list(df, str(out))
        assert not out.exists()


class TestSortOrder:
    def test_sorted_by_provider_priority_then_numeric_order_then_sku(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#10", "SKU": "Z", "Shipping_Provider": "DPD"},
            {"Order_Number": "#9", "SKU": "A", "Shipping_Provider": "DHL"},
            {"Order_Number": "#9", "SKU": "B", "Shipping_Provider": "DHL"},
            {"Order_Number": "#1", "SKU": "Y", "Shipping_Provider": "PostOne"},
        ])
        out = tmp_path / "sorted.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        # DHL (priority 0) rows first, sorted by numeric order# then SKU;
        # then PostOne (1); DPD (2) last -- NOT insertion order, NOT lexicographic "#10" < "#9".
        assert list(zip(result["Order_Number"].astype(str), result["SKU"])) == [
            ("#9", "A"), ("#9", "B"), ("#1", "Y"), ("#10", "Z"),
        ]


class TestDestinationCountryDedup:
    def test_country_shown_only_on_first_row_of_order(self, tmp_path):
        df = _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Destination_Country": "DE"},
            {"Order_Number": "#1", "SKU": "A2", "Destination_Country": "DE"},
        ])
        out = tmp_path / "dedup.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        country_col = result.columns[0]  # first column = Destination_Country (renamed header)
        values = result[country_col].fillna("").tolist()
        assert values[0] == "DE"
        assert values[1] == ""


class TestWarehouseNameFallback:
    def test_falls_back_to_product_name_when_warehouse_name_missing(self, tmp_path):
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Product_Name": "Fallback Name"}])
        df = df.drop(columns=["Warehouse_Name"])
        out = tmp_path / "fallback.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        # Warehouse_Name column header is renamed to the output filename per the
        # export's metadata-embedding scheme -- assert by position instead.
        warehouse_col_idx = 3  # Destination_Country, Order_Number, SKU, Warehouse_Name, ...
        assert result.iloc[0, warehouse_col_idx] == "Fallback Name"


class TestLotExpansion:
    def test_multi_lot_row_expands_and_quantities_sum_to_original(self, tmp_path):
        lot_details = [
            {"expiry": "260601", "batch": None, "qty_allocated": 3},
            {"expiry": "270101", "batch": None, "qty_allocated": 2},
        ]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 5, "Lot_Details": lot_details}])
        out = tmp_path / "lots.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        assert len(result) == 2
        assert result["Quantity"].sum() == 5
        assert set(result["Lot_Expiry"].astype(str)) == {"260601", "270101"}

    def test_lot_sentinel_expiry_one_renders_as_blank(self, tmp_path):
        lot_details = [{"expiry": "1", "batch": "1", "qty_allocated": 4}]
        df = _analysis_df([{"Order_Number": "#1", "SKU": "A1", "Quantity": 4, "Lot_Details": lot_details}])
        out = tmp_path / "sentinel.xlsx"
        create_packing_list(df, str(out))
        result = _read_output(out)
        assert result.iloc[0]["Lot_Expiry"] in ("", None) or pd.isna(result.iloc[0]["Lot_Expiry"])
        assert result.iloc[0]["Lot_Batch"] in ("", None) or pd.isna(result.iloc[0]["Lot_Batch"])
