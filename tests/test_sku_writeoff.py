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
    # Last three rows are the untagged shapes that reach explode(): NaN, an
    # empty array, and an array holding an empty string. None may contribute.
    df = pd.DataFrame({
        "Order_Number": [1001, 1001, 1001, 1002, 1003, 1004, 1005],
        "SKU": ["A", "B", "C", "A", "A", "A", "A"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 7,
        "Internal_Tags": ['["BOX"]'] * 4 + [None, "[]", '[""]'],
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    row = result[result["SKU"] == "PKG-BOX"].iloc[0]
    assert row["Writeoff_Quantity"] == 2.0
    assert row["Order_Count"] == 2
    assert row["Tags_Applied"] == ["BOX"]


def test_missing_order_number_falls_back_to_per_row_counting():
    # No Order_Number means per-order dedup is impossible; each row counts
    # separately (the pre-fix behaviour), and the caller is warned.
    df = pd.DataFrame({
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        "Internal_Tags": ['["BOX"]'] * 3,
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result[result["SKU"] == "PKG-BOX"].iloc[0]["Writeoff_Quantity"] == 3.0


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


def test_an_order_number_with_a_trailing_space_is_one_order():
    """AUDIT-09-O6: "1001" and "1001 " wrote the box off twice."""
    df = pd.DataFrame({
        "Order_Number": ["1001", "1001 "],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"],
        "Internal_Tags": ['["BOX"]', '["BOX"]'],
    })
    result = calculate_writeoff_quantities(df, BOX_ONLY)
    assert result.loc[result["SKU"] == "PKG-BOX", "Writeoff_Quantity"].sum() == 1.0


# --- config hygiene and accumulation (Audit 10, part A) ---------------------------------------


def _orders(*tags_per_order):
    return pd.DataFrame({
        "Order_Number": [f"#{i + 1}" for i in range(len(tags_per_order))],
        "Internal_Tags": [str(list(t)).replace("'", '"') for t in tags_per_order],
        "Order_Fulfillment_Status": ["Fulfillable"] * len(tags_per_order),
    })


def test_orders_with_the_same_tag_sum_their_quantities_and_count_orders():
    config = _config({"BOX": [{"sku": "PKG-BOX", "quantity": 1.5}]})
    result = calculate_writeoff_quantities(_orders(["BOX"], ["BOX"], ["OTHER"]), config)
    assert result.to_dict("records") == [
        {"SKU": "PKG-BOX", "Writeoff_Quantity": 3.0, "Tags_Applied": ["BOX"], "Order_Count": 2}
    ]


def test_a_tag_without_a_mapping_adds_nothing():
    result = calculate_writeoff_quantities(_orders(["OTHER"]), BOX_ONLY)
    assert result.empty
    assert list(result.columns) == ["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"]


def test_without_a_status_column_every_row_counts():
    frame = _orders(["BOX"]).drop(columns="Order_Fulfillment_Status")
    assert calculate_writeoff_quantities(frame, BOX_ONLY)["Writeoff_Quantity"].tolist() == [1.0]


def test_missing_tags_in_a_row_are_not_an_error():
    frame = _orders(["BOX"], ["BOX"])
    frame.loc[1, "Internal_Tags"] = None
    assert calculate_writeoff_quantities(frame, BOX_ONLY)["Order_Count"].tolist() == [1]


@pytest.mark.parametrize(
    "bad_mapping",
    [
        "PKG-BOX",                                              # not a list
        ["PKG-BOX"],                                            # item not a dict
        [{"sku": "PKG-BOX"}],                                   # no quantity
        [{"quantity": 1}],                                      # no sku
        [{"sku": "PKG-BOX", "quantity": "two"}],                # not a number
        [{"sku": "PKG-BOX", "quantity": 0}],                    # not positive
        [{"sku": "PKG-BOX", "quantity": -1}],
    ],
)
def test_an_invalid_mapping_is_skipped_and_the_rest_still_apply(bad_mapping):
    config = _config({"BAD": bad_mapping, "BOX": [{"sku": "PKG-OK", "quantity": 1}]})
    result = calculate_writeoff_quantities(_orders(["BAD", "BOX"]), config)
    assert result["SKU"].tolist() == ["PKG-OK"]


def test_a_quantity_written_as_text_is_read_as_a_number():
    config = _config({"BOX": [{"sku": "PKG-BOX", "quantity": "2"}]})
    assert calculate_writeoff_quantities(_orders(["BOX"]), config)["Writeoff_Quantity"].tolist() == [2.0]


def test_v1_shaped_categories_work_too():
    config = {"packaging": {"tags": ["BOX"], "sku_writeoff": {
        "enabled": True, "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 1}]}}}}
    assert calculate_writeoff_quantities(_orders(["BOX"]), config)["SKU"].tolist() == ["PKG-BOX"]
