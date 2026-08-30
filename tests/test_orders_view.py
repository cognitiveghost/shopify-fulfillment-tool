"""Spec §10 tests 1-6: the line frame folds to one row per order."""

import pandas as pd
import pytest

from gui.orders_view import (
    SEARCH_COLUMN,
    classify_columns,
    order_lines,
    orders_frame,
)


def _frame(rows):
    """Build a line frame with the columns orders_frame actually reads."""
    return pd.DataFrame(rows)


@pytest.fixture
def three_orders():
    """3 orders / 7 lines. #1002 is blocked; #1003 is a repeat AND blocked."""
    return _frame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "AAA", "Quantity": 2,
             "System_note": ""},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "BBB", "Quantity": 1,
             "System_note": ""},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "CCC", "Quantity": 1,
             "System_note": ""},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "SKU": "DDD", "Quantity": 5,
             "System_note": "Cannot fulfill: insufficient stock for DDD"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "SKU": "EEE", "Quantity": 1,
             "System_note": "Cannot fulfill: insufficient stock for DDD"},
            {"Order_Number": "1003", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "PostOne", "SKU": "FFF", "Quantity": 1,
             "System_note": "Repeat order (3 days); Cannot fulfill: no SKU match"},
            {"Order_Number": "1003", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "PostOne", "SKU": "GGG", "Quantity": 2,
             "System_note": "Repeat order (3 days); Cannot fulfill: no SKU match"},
        ]
    )


def test_folds_to_one_row_per_order_in_first_appearance_order(three_orders):
    out = orders_frame(three_orders)
    assert len(out) == 3
    assert list(out["Order_Number"]) == ["1001", "1002", "1003"]


def test_items_counts_lines_per_order(three_orders):
    out = orders_frame(three_orders)
    assert list(out["Items"]) == [3, 2, 2]


def test_blocker_extracts_reason_and_is_empty_when_fulfillable(three_orders):
    out = orders_frame(three_orders).set_index("Order_Number")
    assert out.loc["1001", "Blocker"] == ""
    assert out.loc["1002", "Blocker"] == "insufficient stock for DDD"
    # The compound "Repeat ...; Cannot fulfill: ..." form analysis.py:1071 writes.
    assert out.loc["1003", "Blocker"] == "no SKU match"


def test_search_text_carries_line_skus(three_orders):
    out = orders_frame(three_orders).set_index("Order_Number")
    assert "AAA" in out.loc["1001", SEARCH_COLUMN]
    assert "CCC" in out.loc["1001", SEARCH_COLUMN]
    assert "AAA" not in out.loc["1002", SEARCH_COLUMN]


def test_unknown_column_constant_within_orders_is_order_level(three_orders):
    df = three_orders.copy()
    df["Customer_Ref"] = df["Order_Number"].map(
        {"1001": "R-1", "1002": "R-2", "1003": "R-3"}
    )
    df["Line_Comment"] = ["a", "b", "c", "d", "e", "f", "g"]

    order_level, line_level = classify_columns(df)
    assert "Customer_Ref" in order_level
    assert "Line_Comment" in line_level
    assert "Customer_Ref" in orders_frame(df).columns


def test_declared_list_wins_when_every_order_has_one_line():
    df = _frame(
        [
            {"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable",
             "SKU": "AAA", "Quantity": 1, "System_note": ""},
            {"Order_Number": "2", "Order_Fulfillment_Status": "Fulfillable",
             "SKU": "BBB", "Quantity": 1, "System_note": ""},
        ]
    )
    _order_level, line_level = classify_columns(df)
    # Every column is trivially constant here; only the declared list stops SKU
    # from becoming an order-level column that means nothing.
    assert "SKU" in line_level
    assert "SKU" not in orders_frame(df).columns


def test_order_lines_returns_only_that_orders_lines(three_orders):
    lines = order_lines(three_orders, "1002")
    assert list(lines["SKU"]) == ["DDD", "EEE"]
    assert "Order_Fulfillment_Status" not in lines.columns


def test_empty_frame_gives_empty_frame():
    assert orders_frame(pd.DataFrame()).empty
