"""The two Python seams behind the results document (Bundle 12 spec §4)."""

import json

import pandas as pd
import pytest

from gui.orders_view import order_payload, results_summary


@pytest.fixture
def lines():
    base = {"System_note": "", "Has_SKU": True, "Stock_Alert": ""}
    return pd.DataFrame(
        [
            {
                **base,
                "Order_Number": "#1",
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DHL",
                "SKU": "A",
                "Quantity": 2,
                "Total_Price": 10.0,
                "Created_At": "2026-09-02 09:00:00 +0200",
                "Internal_Tags": '["vip"]',
            },
            {
                **base,
                "Order_Number": "#1",
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DHL",
                "SKU": "B",
                "Quantity": 1,
                "Total_Price": 10.0,
                "Created_At": "2026-09-02 09:00:00 +0200",
                "Internal_Tags": '["vip"]',
                "Stock_Alert": "Low Stock",
            },
            {
                **base,
                "Order_Number": "#2",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "Shipping_Provider": "DPD",
                "SKU": "C",
                "Quantity": 4,
                "Total_Price": 25.5,
                "Created_At": "2026-09-01 08:00:00 +0200",
                "Internal_Tags": "[]",
                "Has_SKU": False,
            },
            {
                **base,
                "Order_Number": "#3",
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "",
                "SKU": "A",
                "Quantity": "x",
                "Total_Price": 5.0,
                "Created_At": "not a date",
                "Internal_Tags": "",
            },
        ]
    )


def _by_order(payload):
    return {entry["Order_Number"]: entry for entry in payload}


def test_the_payload_counts_units_and_coerces_junk_to_zero(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Units"] == 3
    assert orders["#2"]["Units"] == 4
    assert orders["#3"]["Units"] == 0


def test_the_payload_normalises_created_at_or_drops_it(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Created_At"] == "2026-09-02T07:00:00+00:00"
    assert orders["#3"]["Created_At"] is None


def test_the_payload_carries_tags_and_flags(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Tag_List"] == ["vip"]
    assert orders["#3"]["Tag_List"] == []
    assert (orders["#1"]["Low_Stock"], orders["#1"]["Unknown_SKU"]) == (True, False)
    assert (orders["#2"]["Low_Stock"], orders["#2"]["Unknown_SKU"]) == (False, True)


def test_the_payload_flags_default_off_without_their_columns():
    payload = order_payload(pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    assert payload[0]["Units"] == 0
    assert payload[0]["Created_At"] is None
    assert payload[0]["Tag_List"] == []
    assert payload[0]["Unknown_SKU"] is False
    assert payload[0]["Low_Stock"] is False


def test_the_summary_counts_the_session(lines):
    s = results_summary(lines)
    assert (s["orders"], s["lines"], s["skus"]) == (3, 4, 3)
    assert (s["fulfillable"], s["blocked"]) == (2, 1)
    assert (s["blocked_lines"], s["blocked_skus"]) == (1, 1)


def test_labels_are_fulfillable_orders_by_courier_blank_named(lines):
    # Equal counts fall back to name order.
    assert results_summary(lines)["labels_by_courier"] == [
        ["DHL", 1],
        ["No courier", 1],
    ]


def test_value_counts_each_order_once(lines):
    s = results_summary(lines)
    assert s["value_total"] == pytest.approx(40.5)
    assert s["value_ready"] == pytest.approx(15.0)


def test_value_is_none_without_a_price_column(lines):
    s = results_summary(lines.drop(columns=["Total_Price"]))
    assert s["value_total"] is None
    assert s["value_ready"] is None


def test_oldest_is_the_earliest_parseable_order(lines):
    assert results_summary(lines)["oldest"] == {
        "order_number": "#2",
        "created_at": "2026-09-01T06:00:00+00:00",
    }
    assert results_summary(lines.drop(columns=["Created_At"]))["oldest"] is None


def test_nothing_to_summarise_is_an_empty_dict():
    assert results_summary(None) == {}
    assert results_summary(pd.DataFrame()) == {}
    assert results_summary(pd.DataFrame({"SKU": ["A"]})) == {}


def test_both_survive_strict_json(lines):
    json.dumps(order_payload(lines), allow_nan=False)
    json.dumps(results_summary(lines), allow_nan=False)
