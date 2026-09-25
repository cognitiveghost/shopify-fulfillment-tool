"""stock_ledger: the order-status rule (R1) and Stock left (R2).

Spec: docs/superpowers/specs/2026-09-25-phase14-bundle1-stock-ledger-design.md §2-3.
"""

import pandas as pd
import pytest

from shopify_tool.analysis import run_analysis
from shopify_tool.stock_ledger import (
    FULFILLABLE as FF,
)
from shopify_tool.stock_ledger import (
    NOT_FULFILLABLE as NF,
)
from shopify_tool.stock_ledger import (
    claim,
    fulfillable_orders,
    is_fulfillable,
    shortfall,
    stock_left,
    with_stock_left,
)


def frame(rows):
    """(order, sku, qty, status, stock, final_stock); sku None = no-SKU line."""
    df = pd.DataFrame(
        rows,
        columns=["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status",
                 "Stock", "Final_Stock"],
    )
    df["Has_SKU"] = df["SKU"].notna()
    df.loc[~df["Has_SKU"], "SKU"] = "NO_SKU"
    return df


def test_one_blocked_sku_line_blocks_the_order():
    df = frame([("#1", "A", 1, FF, 5, 4), ("#1", "GIFT", 1, NF, 0, 0)])
    assert fulfillable_orders(df) == set()


def test_no_sku_line_does_not_block_and_first_row_does_not_decide():
    df = frame([("#1", None, 1, NF, 0, None), ("#1", "A", 2, FF, 5, 3)])
    assert is_fulfillable(df, "#1")
    assert is_fulfillable(df, " #1 ")


def test_order_with_only_no_sku_lines_follows_its_lines():
    df = frame([("#1", None, 1, NF, 0, None)])
    assert not is_fulfillable(df, "#1")
    df["Order_Fulfillment_Status"] = FF
    assert is_fulfillable(df, "#1")


def test_frame_without_has_sku_uses_the_sku_column():
    df = frame([("#1", None, 1, NF, 0, None), ("#1", "A", 2, FF, 5, 3)])
    df = df.drop(columns=["Has_SKU"])
    assert is_fulfillable(df, "#1")


def test_stock_left_is_opening_minus_fulfillable_orders():
    df = frame([
        ("#1", "A", 2, FF, 5, 999),   # stale Final_Stock is ignored
        ("#2", "A", 1, NF, 5, 999),
        ("#3", "A", 1, FF, 5, 999),
        ("#3", "B", 1, NF, 4, 999),   # mixed: #3 is blocked, draws nothing
    ])
    assert stock_left(df) == {"A": 3.0, "B": 4.0}
    assert stock_left(df, excluding="#1") == {"A": 5.0, "B": 4.0}


def test_unlisted_sku_stays_null_and_counts_as_covered():
    df = frame([("#1", "X", 3, NF, 0, None), ("#2", "A", 1, FF, 2, 1)])
    assert "X" not in stock_left(df)
    assert shortfall(df, "#1") == []
    out = with_stock_left(df)
    assert out.loc[out["SKU"] == "X", "Final_Stock"].isna().all()
    assert out.loc[out["SKU"] == "A", "Final_Stock"].tolist() == [1.0]


def test_shortfall_sums_repeated_lines_and_releases_own_draw():
    df = frame([("#1", "A", 2, NF, 3, 3), ("#1", "A", 2, NF, 3, 3)])
    assert shortfall(df, "#1") == ["A"]           # needs 4, has 3
    df2 = frame([("#1", "A", 2, FF, 3, 1), ("#1", "B", 1, FF, 1, 0)])
    assert shortfall(df2, "#1") == []             # its own 2 A are released


def test_claim_takes_orders_in_the_given_order_without_double_promising():
    df = frame([("#1", "A", 2, NF, 3, 3), ("#2", "A", 2, NF, 3, 3),
                ("#3", "A", 1, FF, 3, 3)])
    # #3 already holds 1, so 2 are left: #1 fits, then #2 does not.
    assert claim(df, ["#1", "#2", "#3"]) == (["#1"], ["#2"])


def test_frame_without_ledger_columns_is_a_no_op():
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
                       "Order_Fulfillment_Status": [NF]})
    assert stock_left(df) == {}
    assert shortfall(df, "#1") == []
    assert claim(df, ["#1"]) == (["#1"], [])
    assert with_stock_left(df) is df
    assert "Final_Stock" not in df.columns


def _stock(rows, lots=False):
    cols = ["Артикул", "Наличност", "Годност", "Партида"] if lots else ["Артикул", "Наличност"]
    df = pd.DataFrame(rows, columns=cols)
    df["Име"] = df["Артикул"] + " name"
    return df


def _orders(rows):
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


@pytest.mark.parametrize("lots", [False, True])
def test_derived_stock_left_equals_the_runs_final_stock(lots):
    """The invariant ADR 0010 rests on: re-deriving a fresh run changes nothing."""
    stock = (
        _stock([("A", 3, "261230", "B1"), ("A", 2, "270101", "B2"), ("B", 1, "261230", "B3")], lots=True)
        if lots
        else _stock([("A", 5), ("B", 1)])
    )
    orders = _orders([("#1", "A", 2), ("#1", "B", 1), ("#2", "A", 4),
                      ("#3", "A", 1), ("#3", None, 1), ("#4", "Z", 1)])
    df, *_ = run_analysis(stock, orders, pd.DataFrame({"Order_Number": []}))
    before = df["Final_Stock"].copy()
    after = with_stock_left(df.copy())["Final_Stock"]
    pd.testing.assert_series_equal(before.astype(float), after.astype(float), check_names=False)
