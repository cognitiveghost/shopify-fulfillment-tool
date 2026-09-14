"""order_verdict and the payload's Verdict/Short (Bundle 13 spec §3.1)."""

import json

import pandas as pd
import pytest

from gui.orders_view import order_payload, order_verdict

SHORT = "Cannot fulfill: A: Insufficient stock (need 6, have 4); B: Out of stock"


def test_a_fulfillable_order_with_no_note_is_ready():
    assert order_verdict("Fulfillable", ["", ""], ["A", "B"], [True, True]) == {
        "state": "ready",
        "by_hand": False,
        "problems": [],
    }


def test_stock_reasons_parse_with_their_numbers():
    v = order_verdict("Not Fulfillable", [SHORT, SHORT], ["A", "B"], [True, True])
    assert v["state"] == "short"
    assert v["by_hand"] is False
    assert v["problems"] == [
        {"code": "short", "sku": "A", "need": 6, "have": 4},
        {"code": "out_of_stock", "sku": "B"},
    ]


def test_a_repeat_prefix_and_a_no_sku_suffix_are_tolerated():
    note = "Repeat; Cannot fulfill: A: Out of stock [NO_SKU]"
    v = order_verdict("Not Fulfillable", [note], ["A"], [True])
    assert v["problems"] == [{"code": "out_of_stock", "sku": "A"}]


def test_lines_without_a_sku_are_a_data_problem():
    v = order_verdict("Not Fulfillable", ["[NO_SKU]", ""], [None, "A"], [False, True])
    assert v == {
        "state": "review",
        "by_hand": False,
        "problems": [{"code": "no_sku", "lines": 1}],
    }


def test_an_invalid_quantity_is_a_data_problem():
    v = order_verdict(
        "Not Fulfillable",
        ["Cannot fulfill: A: Missing/invalid quantity"],
        ["A"],
        [True],
    )
    assert v["state"] == "review"
    assert v["problems"] == [{"code": "invalid_quantity", "sku": "A"}]


def test_an_unrecognised_reason_is_kept_as_text():
    v = order_verdict(
        "Not Fulfillable", ["Cannot fulfill: Unknown reason"], ["A"], [True]
    )
    assert v["state"] == "review"
    assert v["problems"] == [{"code": "other", "text": "Unknown reason"}]


def test_forcing_a_blocked_order_fulfillable_reads_as_by_hand():
    v = order_verdict("Fulfillable", [SHORT], ["A", "B"], [True, True])
    assert (v["state"], v["by_hand"]) == ("review", True)


def test_holding_an_order_the_run_could_ship_reads_as_by_hand():
    v = order_verdict("Not Fulfillable", [""], ["A"], [True])
    assert v == {"state": "review", "by_hand": True, "problems": []}


def test_a_reason_for_a_removed_line_is_dropped():
    v = order_verdict("Not Fulfillable", [SHORT], ["B"], [True])
    assert v["problems"] == [{"code": "out_of_stock", "sku": "B"}]


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_blank_notes_are_skipped(missing):
    assert order_verdict("Fulfillable", [missing], ["A"], [True])["state"] == "ready"


def test_the_payload_carries_the_verdict_and_edges_short_lines():
    df = pd.DataFrame(
        [
            {
                "Order_Number": "1",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "SKU": "A",
                "Quantity": 6,
                "System_note": SHORT,
                "Has_SKU": True,
            },
            {
                "Order_Number": "1",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "SKU": "B",
                "Quantity": 1,
                "System_note": SHORT,
                "Has_SKU": True,
            },
            {
                "Order_Number": "1",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "SKU": "C",
                "Quantity": 1,
                "System_note": SHORT,
                "Has_SKU": True,
            },
        ]
    )
    (entry,) = order_payload(df)
    assert entry["Verdict"]["state"] == "short"
    assert [line["Short"] for line in entry["lines"]] == [True, True, False]
    json.dumps(order_payload(df), allow_nan=False)


def test_the_payload_verdict_survives_missing_columns():
    df = pd.DataFrame([{"Order_Number": "1", "SKU": "A"}])
    (entry,) = order_payload(df)
    assert entry["Verdict"] == {"state": "review", "by_hand": True, "problems": []}
