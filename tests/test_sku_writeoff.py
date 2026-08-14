import pandas as pd
import pytest

from shopify_tool.sku_writeoff import calculate_writeoff_quantities


def _config(mappings, enabled=True):
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "tags": list(mappings),
                "sku_writeoff": {"enabled": enabled, "mappings": mappings},
            }
        },
    }


BOX_ONLY = _config({"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]})


def test_tag_counts_once_per_order_not_once_per_line_item():
    df = pd.DataFrame({
        "Order_Number": [1001, 1001, 1001, 1002],
        "SKU": ["A", "B", "C", "A"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 4,
        "Internal_Tags": ['["BOX"]'] * 4,
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    row = result[result["SKU"] == "PKG-BOX"].iloc[0]
    assert row["Writeoff_Quantity"] == 2.0
    assert row["Order_Count"] == 2


def test_two_tags_mapping_to_same_sku_each_count_once():
    cfg = _config({
        "BOX": [{"sku": "PKG-SEAL", "quantity": 1.0}],
        "BAG": [{"sku": "PKG-SEAL", "quantity": 1.0}],
    })
    df = pd.DataFrame({
        "Order_Number": [1001, 1001, 1001],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        "Internal_Tags": ['["BOX", "BAG"]'] * 3,
    })
    result = calculate_writeoff_quantities(df, cfg)
    assert result[result["SKU"] == "PKG-SEAL"].iloc[0]["Writeoff_Quantity"] == 2.0


def test_non_fulfillable_orders_are_excluded():
    df = pd.DataFrame({
        "Order_Number": [1001, 1002],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable"],
        "Internal_Tags": ['["BOX"]'] * 2,
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result[result["SKU"] == "PKG-BOX"].iloc[0]["Writeoff_Quantity"] == 1.0


def test_multiple_skus_per_tag_all_applied_once():
    cfg = _config({"BOX": [
        {"sku": "PKG-BOX", "quantity": 1.0},
        {"sku": "PKG-TAPE", "quantity": 2.0},
    ]})
    df = pd.DataFrame({
        "Order_Number": [1001, 1001],
        "Order_Fulfillment_Status": ["Fulfillable"] * 2,
        "Internal_Tags": ['["BOX"]'] * 2,
    })
    result = calculate_writeoff_quantities(df, cfg).set_index("SKU")
    assert result.loc["PKG-BOX", "Writeoff_Quantity"] == 1.0
    assert result.loc["PKG-TAPE", "Writeoff_Quantity"] == 2.0


def test_disabled_category_produces_no_writeoff():
    df = pd.DataFrame({
        "Order_Number": [1001],
        "Order_Fulfillment_Status": ["Fulfillable"],
        "Internal_Tags": ['["BOX"]'],
    })
    cfg = _config({"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]}, enabled=False)
    assert calculate_writeoff_quantities(df, cfg).empty


@pytest.mark.parametrize("df", [
    pd.DataFrame(),
    pd.DataFrame({"Order_Number": [1], "Order_Fulfillment_Status": ["Fulfillable"]}),
])
def test_degenerate_inputs_return_empty_with_correct_columns(df):
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result.empty
    assert list(result.columns) == [
        "SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count",
    ]
