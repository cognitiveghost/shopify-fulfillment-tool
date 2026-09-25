"""Order status and Stock left, derived from the analysis frame.

The only place two rules live (spec 2026-09-25 bundle 1 §2, ADR 0010):

R1  An order is fulfillable when every one of its SKU lines is Fulfillable.
    An order with no SKU lines follows all of its lines.
R2  Stock left = opening Stock - the SKU lines of fulfillable orders, per
    listed SKU. A SKU whose Final_Stock is null on every row is unlisted
    (missing from the stock file): it stays null and never blocks.

Edit verbs write rows and statuses, then call with_stock_left. They never
adjust Final_Stock themselves.
"""

import pandas as pd

FULFILLABLE = "Fulfillable"
NOT_FULFILLABLE = "Not Fulfillable"

_LEDGER_COLUMNS = {"SKU", "Stock", "Final_Stock"}


def _key(value) -> str:
    return str(value).strip()


def _keys(df: pd.DataFrame) -> pd.Series:
    return df["Order_Number"].astype(str).str.strip()


def _sku_lines(df: pd.DataFrame) -> pd.Series:
    if "Has_SKU" in df.columns:
        return df["Has_SKU"].fillna(False).astype(bool)
    if "SKU" in df.columns:
        return df["SKU"].notna() & (df["SKU"].astype(str) != "NO_SKU")
    return pd.Series(True, index=df.index)


def _has_ledger(df) -> bool:
    return df is not None and not df.empty and _LEDGER_COLUMNS <= set(df.columns)


def fulfillable_orders(df) -> set:
    """R1: the order numbers (str, stripped) of the fulfillable orders."""
    if df is None or df.empty or "Order_Fulfillment_Status" not in df.columns:
        return set()
    keys = _keys(df)
    sku = _sku_lines(df)
    deciding = sku | ~sku.groupby(keys).transform("any")
    blocked = (deciding & df["Order_Fulfillment_Status"].ne(FULFILLABLE)).groupby(keys).any()
    return set(blocked.index[~blocked])


def is_fulfillable(df, order_number) -> bool:
    return _key(order_number) in fulfillable_orders(df)


def stock_left(df, excluding=None) -> dict:
    """R2 per listed SKU. `excluding`: an order whose own draw is released."""
    if not _has_ledger(df):
        return {}
    rows = df[_sku_lines(df)]
    by_sku = rows["SKU"]
    listed = rows["Final_Stock"].notna().groupby(by_sku).any()
    opening = pd.to_numeric(rows.groupby("SKU")["Stock"].first(), errors="coerce").fillna(0)
    drawing = _keys(rows).isin(fulfillable_orders(df))
    if excluding is not None:
        drawing &= _keys(rows) != _key(excluding)
    qty = pd.to_numeric(rows["Quantity"], errors="coerce").fillna(0).where(drawing, 0)
    left = (opening - qty.groupby(by_sku).sum())[listed]
    return {sku: float(v) for sku, v in left.items()}


def _needs(df, order_number) -> dict:
    rows = df[(_keys(df) == _key(order_number)) & _sku_lines(df)]
    qty = pd.to_numeric(rows["Quantity"], errors="coerce").fillna(0)
    return qty.groupby(rows["SKU"], sort=False).sum().to_dict()


def _short(needs: dict, left: dict) -> list:
    return [sku for sku, need in needs.items() if sku in left and need > left[sku]]


def shortfall(df, order_number) -> list:
    """SKUs Stock left can't cover for this order, its own draw released."""
    if not _has_ledger(df):
        return []
    return _short(_needs(df, order_number), stock_left(df, excluding=order_number))


def claim(df, order_numbers) -> tuple:
    """Which of these orders Stock left covers, taken in the order given.

    Each covered order draws before the next is checked. Orders that are
    already fulfillable are in neither list. Returns (covered, skipped) with
    the order numbers as the caller passed them.
    """
    already = fulfillable_orders(df)
    left = stock_left(df)
    covered, skipped = [], []
    for number in order_numbers:
        if _key(number) in already:
            continue
        needs = _needs(df, number) if _has_ledger(df) else {}
        if _short(needs, left):
            skipped.append(number)
            continue
        for sku, need in needs.items():
            if sku in left:
                left[sku] -= need
        covered.append(number)
    return covered, skipped


def with_stock_left(df):
    """Rewrite Final_Stock on every row of a listed SKU. Returns df."""
    left = stock_left(df)
    if left:
        derived = df["SKU"].map(left)
        df["Final_Stock"] = derived.where(derived.notna(), df["Final_Stock"])
    return df
