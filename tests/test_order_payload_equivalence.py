import json

import numpy as np
import pandas as pd
import pytest
from test_order_payload import _analysis_frame

from gui.orders_view import (
    _STOCK_CODES,
    FULFILLABLE,
    NOT_FULFILLABLE,
    ORDER_KEY,
    _iso_or_none,
    _json_value,
    _per_order_any,
    classify_columns,
    order_payload,
    order_verdict,
    orders_frame,
    parse_tags,
    stock_ledger,
)


def _reference(df: pd.DataFrame) -> list[dict]:
    """The pre-#365 body of order_payload, kept to pin its output."""
    orders = orders_frame(df)
    if orders.empty:
        return []
    _, line_level = classify_columns(df)
    lines, verdicts = {}, {}
    ready = stock_ledger.fulfillable_orders(df)
    for key, group in df.groupby(ORDER_KEY, sort=False):
        lines[key] = [
            dict(zip(line_level, map(_json_value, row)))
            for row in group[line_level].itertuples(index=False, name=None)
        ]
        if "Order_Fulfillment_Status" in group:
            status = FULFILLABLE if str(key).strip() in ready else NOT_FULFILLABLE
        else:
            status = ""
        verdicts[key] = order_verdict(
            status,
            group["System_note"].tolist() if "System_note" in group else [],
            group["SKU"].tolist() if "SKU" in group else [],
            group["Has_SKU"].tolist() if "Has_SKU" in group else [],
        )
    columns = [ORDER_KEY] + [c for c in orders.columns if c != ORDER_KEY]
    by_order = df[ORDER_KEY]
    units = (
        pd.to_numeric(df["Quantity"], errors="coerce")
        .fillna(0)
        .groupby(by_order, sort=False)
        .sum()
        if "Quantity" in df.columns
        else pd.Series(dtype=float)
    )
    unknown_sku = (
        _per_order_any(df, df["Has_SKU"].eq(False))
        if "Has_SKU" in df.columns
        else pd.Series(dtype=bool)
    )
    low_stock = (
        _per_order_any(df, df["Stock_Alert"].fillna("").astype(str).str.strip().ne(""))
        if "Stock_Alert" in df.columns
        else pd.Series(dtype=bool)
    )

    payload = []
    for row in orders[columns].itertuples(index=False, name=None):
        key = row[0]
        entry = dict(zip(columns, map(_json_value, row)))
        entry["lines"] = lines.get(key, [])
        verdict = verdicts.get(
            key, {"state": "review", "by_hand": True, "problems": []}
        )
        entry["Verdict"] = _json_value(verdict)
        short = {p["sku"] for p in verdict["problems"] if p["code"] in _STOCK_CODES}
        for line in entry["lines"]:
            line["Short"] = line.get("SKU") is not None and str(line["SKU"]) in short
        entry["Units"] = int(units.get(key, 0))
        entry["Created_At"] = _iso_or_none(entry.get("Created_At"))
        entry["Tag_List"] = parse_tags(entry.get("Internal_Tags"))
        entry["Unknown_SKU"] = bool(unknown_sku.get(key, False))
        entry["Low_Stock"] = bool(low_stock.get(key, False))
        payload.append(entry)
    return payload


def _random_frame(seed: int, with_optional: bool) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    n = 300
    keys = [f"#{1000 + k}" for k in rng.randint(0, 80, size=n)]  # orders interleaved
    df = pd.DataFrame(
        {
            "Order_Number": keys,
            "Order_Fulfillment_Status": rng.choice(["Fulfillable", "Not Fulfillable"], size=n),
            "SKU": rng.choice(["A", "B", "C", "TS-1"], size=n),
            "Quantity": rng.randint(1, 5, size=n),
            "Stock": rng.choice([0.0, 1.0, 5.0, np.nan], size=n),
            "System_note": rng.choice(["", "Cannot fulfill: B short"], size=n),
            "Notes": rng.choice(["", "call", np.nan], size=n),
            "Total_Price": rng.choice([10.5, np.nan, 3.0], size=n),
        }
    )
    if with_optional:
        df["Has_SKU"] = rng.choice([True, False], size=n, p=[0.9, 0.1])
        df["Stock_Alert"] = rng.choice(["", "Low"], size=n)
        df["Internal_Tags"] = rng.choice(["", "VIP", "VIP, Gift"], size=n)
    return df


FRAMES = [
    lambda: _analysis_frame(),
    lambda: _random_frame(1, True),
    lambda: _random_frame(2, False),
]


@pytest.mark.parametrize("make", FRAMES)
def test_the_one_pass_payload_matches_the_groupby_one(make):
    df = make()
    expected = json.dumps(_reference(df.copy()), sort_keys=False, default=str)
    actual = json.dumps(order_payload(df.copy()), sort_keys=False, default=str)
    assert actual == expected
