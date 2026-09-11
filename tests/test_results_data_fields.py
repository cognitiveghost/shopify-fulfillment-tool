"""Customer and Created_At: two optional orders-file fields (Bundle 12 spec §3)."""

import pandas as pd

from gui.orders_view import ORDER_LEVEL_COLUMNS
from shopify_tool import analysis


def _orders(rows):
    defaults = {
        "Name": "",
        "Lineitem sku": "",
        "Lineitem quantity": 1,
        "Shipping Method": "Standard",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _stock():
    return pd.DataFrame(
        [
            {"Артикул": "A", "Име": "A", "Наличност": 50},
            {"Артикул": "B", "Име": "B", "Наличност": 50},
        ]
    )


def _run(orders):
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    final_df, *_ = analysis.run_analysis(_stock(), orders, history)
    return final_df


def test_customer_and_created_at_are_carried_and_filled_within_each_order():
    final_df = _run(
        _orders(
            [
                {
                    "Name": "#1",
                    "Lineitem sku": "A",
                    "Shipping Name": "B. Fischer",
                    "Created at": "2026-09-02 09:12:44 +0200",
                },
                {
                    "Name": "#1",
                    "Lineitem sku": "B",
                },  # Shopify leaves order fields blank on later lines
                {"Name": "#2", "Lineitem sku": "A"},  # an order with neither
            ]
        )
    )
    first = final_df[final_df["Order_Number"] == "#1"]
    assert first["Customer"].tolist() == ["B. Fischer", "B. Fischer"]
    assert first["Created_At"].tolist() == ["2026-09-02 09:12:44 +0200"] * 2
    second = final_df[final_df["Order_Number"] == "#2"]
    # Filled per order, never from the order above it.
    assert second["Customer"].isna().all()
    assert second["Created_At"].isna().all()


def test_absent_columns_are_not_invented():
    final_df = _run(_orders([{"Name": "#1", "Lineitem sku": "A"}]))
    assert "Customer" not in final_df.columns
    assert "Created_At" not in final_df.columns


def test_both_are_order_level():
    assert "Customer" in ORDER_LEVEL_COLUMNS
    assert "Created_At" in ORDER_LEVEL_COLUMNS


def test_the_mapping_page_offers_both():
    from gui.settings.mappings import OrdersMappingPage

    assert {"Customer", "Created_At"} <= set(OrdersMappingPage.OPTIONAL_FIELDS)


def test_new_profiles_map_shopifys_headers(profile_manager):
    profile_manager.create_client_profile("M", "Client")
    orders = profile_manager.load_shopify_config("M")["column_mappings"]["orders"]
    assert orders["Shipping Name"] == "Customer"
    assert orders["Created at"] == "Created_At"
