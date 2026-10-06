"""stock_ledger: the order-status rule (R1) and Stock left (R2).

Spec: docs/superpowers/specs/2026-09-25-phase14-bundle1-stock-ledger-design.md §2-3.
"""

import pandas as pd
import pytest

from shopify_tool import stock_ledger
from shopify_tool.analysis import run_analysis
from shopify_tool.stock_ledger import (
    FULFILLABLE as FF,
)
from shopify_tool.stock_ledger import (
    NOT_FULFILLABLE as NF,
)
from shopify_tool.stock_ledger import (
    append_blocker,
    claim,
    claim_detail,
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


@pytest.mark.parametrize("note, expected", [
    ("", "Cannot fulfill: Held by rule: R"),
    (None, "Cannot fulfill: Held by rule: R"),
    ("Repeat order", "Repeat order; Cannot fulfill: Held by rule: R"),
    ("Cannot fulfill: A: Out of stock", "Cannot fulfill: A: Out of stock; Held by rule: R"),
    ("Cannot fulfill: Held by rule: R", "Cannot fulfill: Held by rule: R"),
    ("Cannot fulfill: A: Out of stock [NO_SKU]",
     "Cannot fulfill: A: Out of stock; Held by rule: R [NO_SKU]"),
    ("[NO_SKU]", "Cannot fulfill: Held by rule: R [NO_SKU]"),
])
def test_append_blocker(note, expected):
    assert append_blocker(note, "Held by rule: R") == expected


def test_claim_detail_reports_stock_at_each_orders_turn():
    df = frame([
        ("#1", "GIFT", 1, NF, 3, 3), ("#2", "GIFT", 2, NF, 3, 3), ("#3", "GIFT", 1, NF, 3, 3),
    ])
    covered, lacking = claim_detail(df, ["#1", "#2", "#3"])
    assert covered == ["#1", "#2"]
    assert lacking == {"#3": [("GIFT", 1.0, 0.0)]}
    assert claim(df, ["#1", "#2", "#3"]) == (["#1", "#2"], ["#3"])


# --- R3: lot labels follow Quantity (spec 2026-09-28 §3) --------------------

from shopify_tool.stock_ledger import lot_parts

L1 = {"expiry": "260601", "expiry_dt": None, "batch": "B1", "qty_allocated": 3}
L2 = {"expiry": "270101", "expiry_dt": None, "batch": "B2", "qty_allocated": 2}


def lines(rows):
    """(order, sku, qty, lot_details)"""
    return pd.DataFrame(rows, columns=["Order_Number", "SKU", "Quantity", "Lot_Details"])


def test_lots_are_clipped_to_a_lower_quantity():
    df = lines([("#1", "A", 4, [L1, L2])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 1, "270101", "B2")]


def test_quantity_above_the_lots_is_one_unlabelled_part():
    df = lines([("#1", "A", 7, [L1, L2])])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (0, 2, "270101", "B2"), (0, 2, "", "")]


def test_each_line_of_a_pair_reads_its_own_lots():
    # with_lots gives every line its own list (ADR 0015); none is shared.
    df = lines([("#1", "A", 2, [{**L1, "qty_allocated": 2}]), ("#1", "A", 3, [{**L1, "qty_allocated": 1}, L2])])
    assert lot_parts(df) == [(0, 2, "260601", "B1"), (1, 1, "260601", "B1"), (1, 2, "270101", "B2")]


def test_a_line_without_lots_stays_unlabelled_beside_one_with_lots():
    df = lines([("#1", "A", 3, [L1]), ("#1", "A", 1, None)])
    assert lot_parts(df) == [(0, 3, "260601", "B1"), (1, 1, "", "")]


def test_sentinel_one_is_blank():
    df = lines([("#1", "A", 4, [{"expiry": "1", "batch": "1", "qty_allocated": 4}])])
    assert lot_parts(df) == [(0, 4, "", "")]


@pytest.mark.parametrize("cell", [None, float("nan"), [], "[{'expiry': '1'}]"])
def test_a_cell_that_is_not_a_lot_list_means_no_lots(cell):
    df = lines([("#1", "A", 2, cell), ("#1", "A", 1, cell)])
    assert lot_parts(df) == [(0, 2, "", ""), (1, 1, "", "")]


def test_a_line_with_lots_and_no_quantity_yields_nothing():
    df = lines([("#1", "A", 0, [L1])])
    assert lot_parts(df) == []


def test_lines_come_out_in_row_order():
    df = lines([("#2", "B", 1, None), ("#1", "A", 1, [L1]), ("#2", "C", 1, None)])
    assert [p[0] for p in lot_parts(df)] == [0, 1, 2]


def test_no_lot_details_column_at_all():
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [2]})
    assert lot_parts(df) == [(0, 2, "", "")]


def test_unlisted_skus_names_skus_without_a_stock_row():
    df = pd.DataFrame({"Order_Number": ["#1", "#1", "#2"], "SKU": ["A", "X", "Y"], "Quantity": [1, 1, 1],
                       "Stock": [5, 0, 0], "Final_Stock": [5, None, None],
                       "Order_Fulfillment_Status": ["Not Fulfillable"] * 3})
    assert stock_ledger.unlisted_skus(df, ["#1"]) == ["X"]
    assert stock_ledger.unlisted_skus(df, ["#1", "#2"]) == ["X", "Y"]
    assert stock_ledger.unlisted_skus(df.drop(columns=["Final_Stock"]), ["#1"]) == []
