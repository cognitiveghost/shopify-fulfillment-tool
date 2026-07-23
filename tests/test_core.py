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
