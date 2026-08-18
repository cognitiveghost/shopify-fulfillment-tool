"""Packing list export accuracy: output must exactly reflect the analysis
DataFrame (priority: packing list / export generation accuracy)."""
import zipfile

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


def test_not_in_filter_excludes_the_listed_skus(tmp_path):
    """Regression: the old .query() builder wrote every row here.

    "SKU not in AB-01,CD-02" against three rows must leave exactly EF-03.
    Before the shared evaluator this produced a 3-row file -- a picking list
    containing both SKUs the config excluded, reported as "Report saved".
    """
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Warehouse_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        "Destination_Country": ["DE", "FR", "DE"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })
    out = tmp_path / "notin.xlsx"

    create_packing_list(df, str(out), "notin",
                        filters=[{"field": "SKU", "operator": "not in", "value": "AB-01,CD-02"}])

    written = pd.read_excel(out)
    assert written["SKU"].tolist() == ["EF-03"]


def test_contains_filter_writes_the_matching_row(tmp_path):
    """"contains" used to raise SyntaxError -- it is not valid pandas query
    syntax -- so the report failed outright."""
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002"],
        "SKU": ["AB-01", "CD-02"],
        "Product_Name": ["Widget", "Gadget"],
        "Warehouse_Name": ["Widget", "Gadget"],
        "Quantity": [1, 2],
        "Shipping_Provider": ["DHL", "DPD"],
        "Destination_Country": ["DE", "FR"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 2,
    })
    out = tmp_path / "contains.xlsx"

    create_packing_list(df, str(out), "contains",
                        filters=[{"field": "SKU", "operator": "contains", "value": "AB"}])

    assert pd.read_excel(out)["SKU"].tolist() == ["AB-01"]


def _three_row_df():
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1001", "#1002"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Warehouse_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DHL", "DPD"],
        "Destination_Country": ["DE", "DE", "FR"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })


def test_columns_none_reproduces_the_default_layout(tmp_path):
    """The guard against regressing every existing packing list."""
    out = tmp_path / "default.xlsx"
    create_packing_list(_three_row_df(), str(out), "default")

    written = pd.read_excel(out)
    # Shipping_Provider and Warehouse_Name are renamed to carry the timestamp
    # and the filename; the other four keep their names and order.
    assert list(written.columns)[:3] == ["Destination_Country", "Order_Number", "SKU"]
    assert len(written.columns) == 6


def test_chosen_columns_appear_in_the_chosen_order(tmp_path):
    out = tmp_path / "custom.xlsx"
    create_packing_list(_three_row_df(), str(out), "custom",
                        columns=["SKU", "Quantity", "Order_Number"])

    written = pd.read_excel(out)
    assert list(written.columns) == ["SKU", "Quantity", "Order_Number"]
    assert written["SKU"].tolist() == ["AB-01", "CD-02", "EF-03"]


def test_column_set_without_order_number_still_writes(tmp_path):
    """Order boundaries drive the row borders and used to be read off the
    printed frame, so deselecting Order_Number raised KeyError."""
    out = tmp_path / "no_order_col.xlsx"
    create_packing_list(_three_row_df(), str(out), "no_order_col",
                        columns=["SKU", "Quantity"])

    written = pd.read_excel(out)
    assert list(written.columns) == ["SKU", "Quantity"]
    assert len(written) == 3


def test_metadata_survives_a_column_set_that_drops_the_carrier_columns(tmp_path):
    """The timestamp and filename used to ride on Shipping_Provider and
    Warehouse_Name. With neither selected they must still reach the sheet --
    they move to the Excel print header."""
    out = tmp_path / "no_carriers.xlsx"
    create_packing_list(_three_row_df(), str(out), "no_carriers",
                        columns=["SKU", "Quantity"])

    written = pd.read_excel(out)
    # No metadata smuggled into a column name...
    assert list(written.columns) == ["SKU", "Quantity"]

    # ...and it actually reached the sheet, in the print header. Read from the
    # xlsx itself: xlsxwriter exposes no way to read a header back, and
    # asserting only on the column names is what the assertion above already
    # does -- it would pass with the header dropped entirely.
    with zipfile.ZipFile(out) as book:
        sheet = book.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "oddHeader" in sheet
    assert "no_carriers" in sheet
