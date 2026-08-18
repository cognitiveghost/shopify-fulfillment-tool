"""core.py orchestration accuracy (priority: inventory memory accuracy)."""
import pandas as pd

from shopify_tool import core

_ORDERS_MAPPING = {
    "Name": "Order_Number", "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method",
}


class TestInventoryMemoryStockReconstruction:
    def test_reconstructed_stock_has_sku_product_name_and_stock_columns(self):
        orders_df = pd.DataFrame([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 2, "Shipping Method": "Standard"}])
        config = {
            "test_orders_df": orders_df,
            "_inventory_memory": {"enabled": True, "skus": {"A1": 8.0}},
            "column_mappings": {"orders": _ORDERS_MAPPING, "stock": {}},
        }
        _orders, stock_df = core._load_and_validate_files(
            None, None, ",", ",", config
        )
        assert list(stock_df.columns) == ["SKU", "Product_Name", "Stock"]
        assert stock_df.iloc[0]["SKU"] == "A1"
        assert stock_df.iloc[0]["Stock"] == 8.0

    def test_reconstructed_stock_preserves_warehouse_name(self):
        from shopify_tool import analysis

        orders_df = pd.DataFrame([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 2, "Shipping Method": "Standard"}])
        config = {
            "test_orders_df": orders_df,
            # A real inventory-memory snapshot should be able to carry the
            # last-known product name alongside the quantity.
            "_inventory_memory": {"enabled": True, "skus": {"A1": 8.0}, "names": {"A1": "Widget A1"}},
            "column_mappings": {"orders": _ORDERS_MAPPING, "stock": {}},
        }
        _orders_clean, stock_df = core._load_and_validate_files(None, None, ",", ",", config)
        history_df = pd.DataFrame({"Order_Number": [], "Execution_Date": []})
        final_df, *_ = analysis.run_analysis(stock_df, orders_df, history_df)
        assert final_df.iloc[0]["Warehouse_Name"] == "Widget A1"


class TestFulfillmentHistoryMerge:
    """The merge must preserve each order's ORIGINAL Execution_Date.

    fulfillment_history.csv is the only record of when an order was first
    fulfilled. Overwriting that date loses it permanently and silently
    clears the order's "Repeat" flag.
    """

    def test_reanalysis_preserves_original_execution_date(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame({
            "Order_Number": ["#11014590", "#11014599"],
            "Execution_Date": ["2025-11-27", "2025-11-27"],
        })
        # A re-analysis today finds #11014590 still Fulfillable.
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#11014590"],
            "Execution_Date": ["2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        dates = dict(zip(merged["Order_Number"], merged["Execution_Date"]))

        assert dates["#11014590"] == "2025-11-27", (
            "re-analysis overwrote the original fulfilment date"
        )
        assert dates["#11014599"] == "2025-11-27"

    def test_genuinely_new_order_is_added(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame({
            "Order_Number": ["#11014590"],
            "Execution_Date": ["2025-11-27"],
        })
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#99999"],
            "Execution_Date": ["2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        dates = dict(zip(merged["Order_Number"], merged["Execution_Date"]))

        assert dates["#99999"] == "2026-08-18"
        assert dates["#11014590"] == "2025-11-27"

    def test_empty_history_accepts_all_new_orders(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#1", "#2"],
            "Execution_Date": ["2026-08-18", "2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        assert set(merged["Order_Number"]) == {"#1", "#2"}



class TestPackedOrdersAreDetectionOnly:
    """The single most important line in Task 3: the packed-order union feeds
    repeat DETECTION only. It must never reach fulfillment_history.csv, which
    is this repo's own record of what it analyzed.

    Uses real CSV inputs on purpose -- passing None file paths puts
    _save_results_and_reports in "test mode", which skips the history
    write-back entirely and would make this test vacuous.
    """

    def _run(self, tmp_path, monkeypatch, packed_df):
        monkeypatch.setattr(core, "load_packed_orders", lambda _pm, _cid: packed_df)
        # Legacy mode writes history via get_persistent_data_path; keep it in
        # tmp_path so the test never touches the real app-data directory.
        history_path = tmp_path / "fulfillment_history.csv"
        monkeypatch.setattr(core, "get_persistent_data_path", lambda _name: history_path)

        orders_csv = tmp_path / "orders.csv"
        pd.DataFrame([
            {"Name": "#PACKED", "Lineitem sku": "A1", "Lineitem quantity": 1, "Shipping Method": "Standard"},
            {"Name": "#FRESH", "Lineitem sku": "A1", "Lineitem quantity": 1, "Shipping Method": "Standard"},
        ]).to_csv(orders_csv, index=False)

        stock_csv = tmp_path / "stock.csv"
        pd.DataFrame([
            {"Артикул": "A1", "Име": "Widget", "Наличност": 100},
        ]).to_csv(stock_csv, index=False)

        ok, _msg, final_df, _stats = core.run_full_analysis(
            str(stock_csv), str(orders_csv), str(tmp_path / "out"), ",", ",",
            {
                "analysis": {"repeat_detection_days": 1},
                "column_mappings": {
                    "orders": _ORDERS_MAPPING,
                    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
                },
            },
        )
        assert ok, _msg
        return final_df, history_path

    def test_packed_order_is_flagged_repeat_without_entering_history(
        self, tmp_path, monkeypatch
    ):
        import datetime

        yesterday = (
            datetime.datetime.now().astimezone() - datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        packed = pd.DataFrame(
            {"Order_Number": ["#PACKED"], "Execution_Date": [yesterday]}
        )

        final_df, history_path = self._run(tmp_path, monkeypatch, packed)

        # Detection saw the packed order...
        assert final_df[final_df["Order_Number"] == "#PACKED"].iloc[0]["System_note"] == "Repeat"
        assert final_df[final_df["Order_Number"] == "#FRESH"].iloc[0]["System_note"] != "Repeat"

        # ...but the written history carries TODAY's date for #PACKED, from
        # this run's own fulfilment -- not the packed frame's yesterday. If
        # the union had leaked into the write-back, yesterday would be here.
        written = pd.read_csv(history_path)
        today = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")
        assert set(written["Order_Number"]) == {"#PACKED", "#FRESH"}
        assert set(written["Execution_Date"].astype(str)) == {today}

    def test_packed_order_absent_from_this_run_never_reaches_history(
        self, tmp_path, monkeypatch
    ):
        """An order Packing Tool packed but that is not in today's export must
        not be written into this repo's history at all."""
        packed = pd.DataFrame(
            {"Order_Number": ["#LONG_GONE"], "Execution_Date": ["2026-01-01"]}
        )

        _final_df, history_path = self._run(tmp_path, monkeypatch, packed)

        written = pd.read_csv(history_path)
        assert "#LONG_GONE" not in set(written["Order_Number"])
