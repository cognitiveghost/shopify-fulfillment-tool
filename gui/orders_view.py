"""Fold the line-level analysis frame into one row per order.

``analysis_results_df`` stays the single source of truth for every report,
export, packing list and undo step. This module is a *projection* for display:
computed on demand, never persisted, never written back to. See
``docs/superpowers/specs/2026-08-30-analysis-results-1b-design.md`` section 3.
"""

import pandas as pd

from gui.pandas_model import REPEAT_COLUMN, cell_search_text, is_repeat

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

# Hidden column carrying the order's line text so a SKU search still finds the
# order that contains it. The view hides it; the filter proxy still scans it.
SEARCH_COLUMN = "_search_text"

# Derived, and hidden from every surface that walks the frame's columns: the
# table view, the column-config dialog, and the filter-scope dropdown.
HIDDEN_COLUMNS = (SEARCH_COLUMN, REPEAT_COLUMN)

ORDER_KEY = "Order_Number"


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


def _first_blocker(notes) -> str:
    """The reason out of the first System_note that carries one, else ""."""
    for note in notes:
        if note is None or (isinstance(note, float) and pd.isna(note)):
            continue
        _, sep, tail = str(note).partition(BLOCKER_PREFIX)
        if sep:
            return tail
    return ""


def orders_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Fold ``df`` to one row per ``Order_Number``, preserving row order.

    Adds three columns that exist only at the order level: ``Items`` (line
    count), ``Blocker`` (the reason, extracted) and ``SEARCH_COLUMN``.
    """
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return pd.DataFrame()

    order_level, line_level = classify_columns(df)
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
        out["Blocker"] = out[ORDER_KEY].map(grouped["System_note"].apply(_first_blocker))
    else:
        out["Blocker"] = ""

    if "System_note" in df.columns:
        out[REPEAT_COLUMN] = out[ORDER_KEY].map(
            grouped["System_note"].apply(lambda notes: any(is_repeat(n) for n in notes))
        )
    else:
        out[REPEAT_COLUMN] = False

    if line_level:
        # Series.map, not DataFrame.map: the latter only exists from pandas 2.1
        # and this stays readable either way.
        # cell_search_text, not cell_display_text: a Lot_Details cell displays
        # as "1 lot" but must stay findable by its batch number and expiry.
        parts = [df[col].map(cell_search_text) for col in line_level]
        line_text = parts[0]
        for part in parts[1:]:
            line_text = line_text.str.cat(part, sep=" ")
        out[SEARCH_COLUMN] = out[ORDER_KEY].map(
            line_text.groupby(df[ORDER_KEY], sort=False).agg(" ".join)
        )
    else:
        out[SEARCH_COLUMN] = ""

    return out


def order_lines(df: pd.DataFrame, order_number) -> pd.DataFrame:
    """The line-level columns of one order, in the frame's own row order."""
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return pd.DataFrame()
    _, line_level = classify_columns(df)
    return df.loc[df[ORDER_KEY] == order_number, line_level].copy()
