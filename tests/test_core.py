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
