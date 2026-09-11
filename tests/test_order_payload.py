"""order_payload: the order frame as the web tier receives it (roadmap 9.12)."""

import json

import numpy as np
import pandas as pd

from gui.orders_view import SEARCH_COLUMN, order_payload


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Order_Number": ["#1001", "#1002", "#1002", "#1003", "#1003", "#1003"],
            "Order_Fulfillment_Status": [
                "Fulfillable",
                "Not Fulfillable",
                "Not Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
            ],
            "Shipping_Provider": ["DHL"] * 6,
            "Notes": [np.nan, "call first", "call first", np.nan, np.nan, np.nan],
            "Total_Price": [10.5, 20.0, 20.0, np.nan, np.nan, np.nan],
            "SKU": ["A", "TS-4409-B", "C", "D", "E", "F"],
            "Quantity": np.array([1, 6, 2, 1, 1, 1], dtype="int64"),
            "Stock": [5.0, 4.0, np.inf, 1.0, 1.0, 1.0],
            "System_note": [
                "",
                "Cannot fulfill: TS-4409-B short",
                "Cannot fulfill: TS-4409-B short",
                "",
                "",
                "",
            ],
        }
    )


def test_one_entry_per_order_in_frame_order():
    payload = order_payload(_analysis_frame())
    assert [o["Order_Number"] for o in payload] == ["#1001", "#1002", "#1003"]


def test_lines_are_nested_with_only_the_line_level_columns():
    order = order_payload(_analysis_frame())[1]
    assert order["lines"] == [
        {
            "SKU": "TS-4409-B",
            "Quantity": 6,
            "Stock": 4.0,
            "System_note": "Cannot fulfill: TS-4409-B short",
        },
        {
            "SKU": "C",
            "Quantity": 2,
            "Stock": None,
            "System_note": "Cannot fulfill: TS-4409-B short",
        },
    ]


def test_order_level_columns_appear_once_with_the_derived_ones():
    order = order_payload(_analysis_frame())[1]
    assert order["Shipping_Provider"] == "DHL"
    assert order["Items"] == 2 and type(order["Items"]) is int
    assert order["Blocker"] == "TS-4409-B short"
    assert "SKU" not in order and SEARCH_COLUMN not in order


def test_every_value_is_json_native():
    payload = order_payload(_analysis_frame())
    json.dumps(payload, allow_nan=False)  # raises on NaN, inf or numpy types
    assert payload[0]["Notes"] is None
    assert payload[2]["Total_Price"] is None
    assert type(payload[0]["lines"][0]["Quantity"]) is int


def test_a_numpy_datetime_nested_in_a_list_cell_becomes_an_iso_string():
    # A top-level datetime64 cell already arrives as a pd.Timestamp; inside a
    # list pandas leaves it raw, and a nanosecond one's .item() is an int.
    df = _analysis_frame()
    df["Lot_Details"] = [[np.datetime64("2026-01-02T03:04:05", "ns")] for _ in range(6)]
    assert '"2026-01-02T03:04:05"' in json.dumps(order_payload(df))


def test_nothing_to_send_is_an_empty_list():
    assert order_payload(None) == []
    assert order_payload(pd.DataFrame()) == []
    assert order_payload(pd.DataFrame({"SKU": ["A"]})) == []
