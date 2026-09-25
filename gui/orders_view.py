"""Fold the line-level analysis frame into one row per order.

``analysis_results_df`` stays the single source of truth for every report,
export, packing list and undo step. This module is a *projection* for display:
computed on demand, never persisted, never written back to. See
``docs/superpowers/specs/2026-08-30-analysis-results-1b-design.md`` section 3.
"""

import datetime
import math
import re

import numpy as np
import pandas as pd

from gui.pandas_model import REPEAT_COLUMN, is_repeat
from shopify_tool import stock_ledger
from shopify_tool.stock_ledger import FULFILLABLE, NOT_FULFILLABLE
from shopify_tool.tag_manager import parse_tags

# Constant across every line of an order, by construction in analysis.py's
# output_columns (analysis.py:1119).
ORDER_LEVEL_COLUMNS = (
    "Order_Number",
    "Order_Type",
    "Order_Fulfillment_Status",
    "Shipping_Provider",
    "Destination_Country",
    "Shipping_Method",
    "Tags",
    "Notes",
    "Status_Note",
    "Internal_Tags",
    "Total_Price",
    "Subtotal",
    "Customer",
    "Created_At",
)

# Varies line by line; these live in the detail pane, not on the order row.
LINE_LEVEL_COLUMNS = (
    "SKU",
    "Has_SKU",
    "Product_Name",
    "Warehouse_Name",
    "Quantity",
    "Stock",
    "Final_Stock",
    "Source",
    "Stock_Alert",
    "System_note",
    "Lot_Details",
)

# analysis.py:1072 writes exactly this prefix into System_note, for every line
# of the order. The reason is the analysis's to compute; this module only reads.
BLOCKER_PREFIX = "Cannot fulfill: "

NO_SKU_SUFFIX = " [NO_SKU]"
# The allocation's own reason strings (analysis.py, legacy and FIFO paths).
_SHORT = re.compile(
    r"^(?P<sku>.+): Insufficient stock \(need (?P<need>\d+), have (?P<have>\d+)\)$"
)
_OUT_OF_STOCK = re.compile(r"^(?P<sku>.+): Out of stock$")
_INVALID_QTY = re.compile(r"^(?P<sku>.+): Missing/invalid quantity$")
_DATA_CODES = {"invalid_quantity", "no_sku", "other"}
_STOCK_CODES = {"short", "out_of_stock"}

ORDER_KEY = "Order_Number"

NO_COURIER = "No courier"


def _order_level_extras(df: pd.DataFrame, unknown: list[str]) -> set[str]:
    """Decide the level of client-configured additional columns from the data.

    Only over orders that actually have more than one line: in a session where
    every order has a single line, every column tests as constant -- SKU
    included -- and the table would grow a column that means nothing at the
    order level. That is why the declared lists are consulted first and this
    only ever sees columns in neither of them.
    """
    if not unknown:
        return set()
    multi = df[df.duplicated(ORDER_KEY, keep=False)]
    if multi.empty:
        return set()  # cannot tell -- leave them line-level, the safe side

    extras = set()
    for col in unknown:
        try:
            constant = multi.groupby(ORDER_KEY)[col].nunique(dropna=False).le(1).all()
        except TypeError:
            # Unhashable cell (a list, as Lot_Details holds). Not aggregatable,
            # so it cannot be an order attribute.
            continue
        if constant:
            extras.add(col)
    return extras


def classify_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Split ``df``'s columns into ``(order_level, line_level)``.

    Both lists preserve the frame's own column order, so a saved column
    configuration keeps its ordering on whichever surface it lands.
    """
    unknown = [
        col
        for col in df.columns
        if col not in ORDER_LEVEL_COLUMNS and col not in LINE_LEVEL_COLUMNS
    ]
    extras = _order_level_extras(df, unknown)

    order_level, line_level = [], []
    for col in df.columns:
        if col in ORDER_LEVEL_COLUMNS or col in extras:
            order_level.append(col)
        else:
            line_level.append(col)
    return order_level, line_level


def _blank(value) -> bool:
    """Missing in the sense the notes column means: no note at all."""
    return (
        value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value))
    )


def _first_blocker(notes) -> str:
    """The reason out of the first System_note that carries one, else ""."""
    for note in notes:
        if _blank(note):
            continue
        _, sep, tail = str(note).partition(BLOCKER_PREFIX)
        if sep:
            return tail
    return ""


def _reason_problems(notes) -> list[dict]:
    """The problems in the first note carrying a blocker, in the run's order."""
    for note in notes:
        if _blank(note):
            continue
        text = str(note)
        text = text.removesuffix(NO_SKU_SUFFIX)
        _, sep, tail = text.partition(BLOCKER_PREFIX)
        if not sep:
            continue
        problems = []
        for part in (p.strip() for p in tail.split("; ")):
            if not part:
                continue
            if m := _SHORT.match(part):
                problems.append(
                    {
                        "code": "short",
                        "sku": m["sku"],
                        "need": int(m["need"]),
                        "have": int(m["have"]),
                    }
                )
            elif m := _OUT_OF_STOCK.match(part):
                problems.append({"code": "out_of_stock", "sku": m["sku"]})
            elif m := _INVALID_QTY.match(part):
                problems.append({"code": "invalid_quantity", "sku": m["sku"]})
            else:
                problems.append({"code": "other", "text": part})
        return problems
    return []


def order_verdict(status, notes, line_skus, has_sku) -> dict:
    """Whether the order ships and why not, from the run's reason codes (§3.1).

    `by_hand` is true when the status disagrees with the run: a manual toggle
    rewrites Order_Fulfillment_Status and never System_note.
    """
    skus = {str(s) for s in line_skus if not _blank(s)}
    problems, seen = [], set()
    for p in _reason_problems(notes):
        if "sku" in p and p["sku"] not in skus:
            continue  # its line was removed after the run
        key = (p["code"], p.get("sku"), p.get("text"))
        if key not in seen:
            seen.add(key)
            problems.append(p)
    missing = sum(1 for h in has_sku if isinstance(h, (bool, np.bool_)) and not h)
    if missing:
        problems.append({"code": "no_sku", "lines": missing})

    fulfillable = status == FULFILLABLE
    by_hand = fulfillable == bool(problems)
    if by_hand or any(p["code"] in _DATA_CODES for p in problems):
        state = "review"
    elif not fulfillable:
        state = "short"
    else:
        state = "ready"
    return {"state": state, "by_hand": by_hand, "problems": problems}


def orders_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Fold ``df`` to one row per ``Order_Number``, preserving row order.

    Adds three columns that exist only at the order level: ``Items`` (line
    count), ``Blocker`` (the reason, extracted) and ``REPEAT_COLUMN``.
    """
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return pd.DataFrame()

    order_level, _line_level = classify_columns(df)
    carried = [col for col in order_level if col != ORDER_KEY]

    # groupby drops null keys. analysis.py writes Order_Number for every line,
    # so there are none; carrying them would mean a null-keyed order row whose
    # Items count cannot be mapped back, which is worse than the status quo.
    grouped = df.groupby(ORDER_KEY, sort=False)
    if carried:
        out = grouped[carried].first().reset_index()
    else:
        out = grouped.size().reset_index()[[ORDER_KEY]]

    out["Items"] = out[ORDER_KEY].map(grouped.size()).astype(int)

    if "System_note" in df.columns:
        out["Blocker"] = out[ORDER_KEY].map(
            grouped["System_note"].apply(_first_blocker)
        )
    else:
        out["Blocker"] = ""

    if "System_note" in df.columns:
        out[REPEAT_COLUMN] = out[ORDER_KEY].map(
            grouped["System_note"].apply(lambda notes: any(is_repeat(n) for n in notes))
        )
    else:
        out[REPEAT_COLUMN] = False

    if "Order_Fulfillment_Status" in out.columns:
        ready = stock_ledger.fulfillable_orders(df)
        out["Order_Fulfillment_Status"] = [
            FULFILLABLE if str(k).strip() in ready else NOT_FULFILLABLE
            for k in out[ORDER_KEY]
        ]

    return out


def order_lines(df: pd.DataFrame, order_number) -> pd.DataFrame:
    """The line-level columns of one order, in the frame's own row order."""
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return pd.DataFrame()
    _, line_level = classify_columns(df)
    return df.loc[df[ORDER_KEY] == order_number, line_level].copy()


def _json_value(value):
    """One cell as the web tier can receive it: JSON-native, never NaN."""
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, np.datetime64):  # a nanosecond one's .item() is an int
        value = pd.Timestamp(value)
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, float):  # numpy.float64 included
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime)):  # pd.Timestamp included
        return value.isoformat()
    if hasattr(value, "item"):  # numpy int, bool, ...
        return _json_value(value.item())
    return str(value)


def _iso_or_none(value):
    """An orders-file timestamp as ISO 8601 in UTC, or None if it isn't one."""
    if isinstance(value, (list, dict)):
        return None
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(stamp) else stamp.isoformat()


def _per_order_any(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    return mask.groupby(df[ORDER_KEY], sort=False).any()


def order_payload(df: pd.DataFrame) -> list[dict]:
    """The order frame with each order's lines nested -- what the bridge sends.

    One entry per order in the frame's row order: the order-level columns once,
    under their own names, and ``lines``, the line-level columns one dict per
    line. The page builds its own search text from these (9.13).
    """
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
        # Derived per order, for the results document (Bundle 12 spec §4.1).
        entry["Units"] = int(units.get(key, 0))
        entry["Created_At"] = _iso_or_none(entry.get("Created_At"))
        entry["Tag_List"] = parse_tags(entry.get("Internal_Tags"))
        entry["Unknown_SKU"] = bool(unknown_sku.get(key, False))
        entry["Low_Stock"] = bool(low_stock.get(key, False))
        payload.append(entry)
    return payload


def _order_values(df: pd.DataFrame) -> pd.Series:
    """Each order's Total_Price, once: the column repeats on every line."""
    firsts = df.groupby(ORDER_KEY, sort=False)["Total_Price"].first()
    return pd.to_numeric(firsts, errors="coerce").fillna(0.0)


def _labels_by_courier(df: pd.DataFrame, fulfillable_orders: set) -> list:
    """One label per fulfillable order, counted per courier, biggest first."""
    if not fulfillable_orders:
        return []
    ready = df[df[ORDER_KEY].isin(fulfillable_orders)].drop_duplicates(ORDER_KEY)
    if "Shipping_Provider" in ready.columns:
        couriers = ready["Shipping_Provider"].fillna("").astype(str).str.strip()
        couriers = couriers.mask(couriers.eq(""), NO_COURIER)
    else:
        couriers = pd.Series(NO_COURIER, index=ready.index)
    pairs = [[str(name), int(count)] for name, count in couriers.value_counts().items()]
    return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))


def _oldest(df: pd.DataFrame):
    """The order created longest ago, among those with a readable Created_At."""
    if "Created_At" not in df.columns:
        return None
    firsts = df.groupby(ORDER_KEY, sort=False)["Created_At"].first()
    iso = firsts.map(_iso_or_none).dropna()
    if iso.empty:
        return None
    stamps = pd.to_datetime(iso, utc=True)
    key = stamps.idxmin()
    return {"order_number": _json_value(key), "created_at": stamps[key].isoformat()}


def results_summary(df: pd.DataFrame) -> dict:
    """The KPI strip's numbers, over the whole session (Bundle 12 spec §4.2).

    Computed from the line frame, as the Qt strip was: quantities, SKUs and
    lines only exist there. Never narrowed by the page's filters.
    """
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return {}

    ready_mask = stock_ledger.in_fulfillable_order(df)
    fulfillable_orders = set(df.loc[ready_mask, ORDER_KEY])
    blocked_rows = df[~df[ORDER_KEY].isin(fulfillable_orders)]
    has_sku = "SKU" in df.columns
    orders = int(df[ORDER_KEY].nunique())

    summary = {
        "orders": orders,
        "lines": len(df),
        "skus": int(df["SKU"].nunique()) if has_sku else 0,
        "fulfillable": len(fulfillable_orders),
        "blocked": orders - len(fulfillable_orders),
        "blocked_lines": len(blocked_rows),
        "blocked_skus": int(blocked_rows["SKU"].nunique()) if has_sku else 0,
        "labels_by_courier": _labels_by_courier(df, fulfillable_orders),
        "value_ready": None,
        "value_total": None,
        "oldest": _oldest(df),
    }
    if "Total_Price" in df.columns:
        values = _order_values(df)
        summary["value_total"] = float(values.sum())
        summary["value_ready"] = float(
            values[values.index.isin(fulfillable_orders)].sum()
        )
    return summary
