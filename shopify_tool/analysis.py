import copy
import logging
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from shopify_tool.csv_utils import normalize_sku, order_number_sort_key
from shopify_tool.stock_ledger import (
    FULFILLABLE,
    NOT_FULFILLABLE,
    drawing_rows,
    is_fulfillable,
    shortfall,
    unlisted_skus,
    with_stock_left,
)

NO_ORDER_NUMBER = "(no order number)"

logger = logging.getLogger(__name__)

# Bulgarian ERP CSV column names for lot tracking (Expiry_Date, Batch)
_LOT_COLUMN_DEFAULTS: dict[str, str] = {"Годност": "Expiry_Date", "Партида": "Batch"}


def _resolve_stock_mappings(stock_mappings: dict[str, str]) -> dict[str, str]:
    """Back-fill lot column defaults that the config does not already cover.

    Lot tracking works for clients whose configs pre-date the Stock mapping UI
    without a config migration. A default is skipped when its CSV header is
    already mapped, or when its *internal* name is -- otherwise a client who
    maps "Exp date" -> Expiry_Date also gets "Годност" -> Expiry_Date, i.e.
    two CSV headers claiming one internal field.

    ponytail: this back-fill is only needed until existing configs have been
    re-saved through the fixed Mappings UI -- drop it, and the constant, once
    that has happened.
    """
    mapped_internals = set(stock_mappings.values())
    missing = {
        csv_col: internal
        for csv_col, internal in _LOT_COLUMN_DEFAULTS.items()
        if csv_col not in stock_mappings and internal not in mapped_internals
    }
    return {**stock_mappings, **missing} if missing else stock_mappings


def stock_reason(sku, need, have) -> str:
    """The run's reason for one SKU the stock can't cover (orders_view parses it)."""
    if have == 0:
        return f"{sku}: Out of stock"
    return f"{sku}: Insufficient stock (need {int(need)}, have {int(have)})"


def stock_with_internal_columns(
    stock_df: pd.DataFrame, column_mappings: dict | None
) -> pd.DataFrame:
    """Return the stock frame with internal column names (SKU/Stock/...).

    A stock frame loaded from CSV carries the client's own headers ("Артикул",
    "Наличност"); one reconstructed from inventory memory already carries
    internal names. Renaming is a no-op for the second shape, so callers that
    need internal names can apply this to either without checking which they
    hold.
    """
    mappings = _resolve_stock_mappings((column_mappings or {}).get("stock", {}))
    # Only rename columns that exist in the DataFrame AND differ from the internal name
    rename_map = {
        csv_col: internal_col
        for csv_col, internal_col in mappings.items()
        if csv_col in stock_df.columns and csv_col != internal_col
    }
    return stock_df.rename(columns=rename_map) if rename_map else stock_df


def _parse_expiry_date(raw) -> date | None:
    """Parse a raw expiry string from the stock CSV to a comparable date object.

    Tries candidate formats in priority order, keeping the first
    calendar-valid one:
    - "1" or None or NaN or "" -> None  (sentinel for "no expiry info")
    - 6-digit: YYMM with day 00 -> the 1st; else YYMMDD, then DDMMYY
    - 8-digit: YYYYMMDD
    - 4-digit: MMYY, then YYMM (day defaults to 1)
    - No valid candidate -> None (logged as a warning)

    If more than one candidate format is calendar-valid for the same raw
    value (e.g. "261230" is valid as both YYMMDD and DDMMYY), this is logged
    as ambiguous and the higher-priority format's result is used.

    ponytail: format priority is a heuristic, not a guaranteed-correct
    disambiguation for 6-digit values valid under more than one format --
    add a per-client date-format setting if that turns out to be common in
    practice.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and math.isnan(raw):
            return None
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if not s or s == "1":
        return None

    if len(s) == 6 and s[4:6] == "00":
        # Day "00" means the month itself (WATERDROP "261200"); DDMMYY would
        # read it as 2000-12-26 and FIFO would draw it first (AUDIT-06-7).
        candidate_specs = [("YYMM00", s[0:2], s[2:4], "01")]
    elif len(s) == 6:
        candidate_specs = [
            ("YYMMDD", s[0:2], s[2:4], s[4:6]),
            ("DDMMYY", s[4:6], s[2:4], s[0:2]),
        ]
    elif len(s) == 8:
        candidate_specs = [("YYYYMMDD", s[0:4], s[4:6], s[6:8])]
    elif len(s) == 4:
        candidate_specs = [
            ("MMYY", s[2:4], s[0:2], "01"),
            ("YYMM", s[0:2], s[2:4], "01"),  # ALMADERM "2805" (AUDIT-06-7)
        ]
    else:
        candidate_specs = []

    valid: list[tuple[str, date]] = []
    for fmt, y_s, m_s, d_s in candidate_specs:
        try:
            year = int(y_s) if len(y_s) == 4 else 2000 + int(y_s)
            valid.append((fmt, date(year, int(m_s), int(d_s))))
        except (ValueError, OverflowError):
            continue

    if not valid:
        logger.warning(f"Could not parse expiry date: {s!r}")
        return None
    if len(valid) > 1:
        logger.warning(
            f"Ambiguous expiry {s!r}: valid as {[v[0] for v in valid]}, using {valid[0][0]}"
        )
    return valid[0][1]


def _normalized_stock(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Stock rows with normalised SKUs and numeric stock, blank or text read as 0.

    Normalize before any dedupe or aggregation: "501 " and "501.0" are one
    SKU, and deduping first let both through to double every order line
    the merge matched against them (F4). Blank SKUs stay blank so dropna
    still drops them -- normalize_sku(NaN) would return "".
    """
    stock_df = stock_df.copy()
    stock_df["SKU"] = stock_df["SKU"].astype(object)  # float SKUs take strings
    has_sku = stock_df["SKU"].notna()
    stock_df.loc[has_sku, "SKU"] = stock_df.loc[has_sku, "SKU"].map(normalize_sku)

    # A blank or non-numeric stock cell is no stock, never unlimited stock:
    # NaN fails both "== 0" and "required > available" (AUDIT-01-7).
    stock_numeric = pd.to_numeric(stock_df["Stock"], errors="coerce")
    bad = stock_numeric.isna() & has_sku
    if bad.any():
        logger.warning(
            f"{int(bad.sum())} stock rows have a blank or non-numeric stock cell, "
            f"read as 0: {stock_df.loc[bad, 'SKU'].tolist()[:10]}"
        )
    stock_df["Stock"] = stock_numeric.fillna(0)
    return stock_df


def lot_table(stock_df: pd.DataFrame) -> dict[str, list[dict]] | None:
    """The opening lots per SKU, in draw order, from a stock frame with internal
    column names. None without lot columns (R3, ADR 0015)."""
    return _build_fifo_lots(_normalized_stock(stock_df))


_NO_EXPIRY_SENTINEL = date(9999, 12, 31)  # sorts after all real dates


def _lot_fields(row, has_expiry: bool, has_batch: bool) -> tuple[str, date | None, str | None]:
    """(expiry, expiry_dt, batch) of one stock row; expiry "1" means none."""
    raw_e = row.Expiry_Date if has_expiry and pd.notna(row.Expiry_Date) else None
    if raw_e is None:
        expiry_raw = "1"
    elif isinstance(raw_e, float):
        expiry_raw = str(int(raw_e))
    else:
        expiry_raw = str(raw_e).strip()

    raw_b = row.Batch if has_batch and pd.notna(row.Batch) else None
    if raw_b is None:
        batch_raw = None
    elif isinstance(raw_b, float):
        batch_raw = str(int(raw_b))
    else:
        batch_raw = str(raw_b).strip()

    if batch_raw == "1":
        batch_raw = None
    return expiry_raw, _parse_expiry_date(expiry_raw), batch_raw


def _draw_key(lot: dict) -> tuple:
    """Draw order: undated, unbatched stock first, then the rest by expiry (ADR 0015)."""
    undated = lot["expiry"] == "1" and lot["batch"] is None
    return (0 if undated else 1, lot["expiry_dt"] or _NO_EXPIRY_SENTINEL, lot["batch"] or "")


def _build_fifo_lots(stock_df: pd.DataFrame) -> dict[str, list[dict]] | None:
    """Build the opening lots per SKU, in draw order, from a multi-row stock DataFrame.

    Returns None when neither Expiry_Date nor Batch column is present
    (backward-compatibility gate — no lot tracking needed).

    Each SKU maps to a list of lot dicts in the order orders draw them:
        {"expiry": str, "expiry_dt": Optional[date], "batch": Optional[str], "qty": float}

    Draw order: undated, unbatched lots first (expiry "1", no batch), then
    dated or batched lots, earliest expiry first (no expiry last), then by
    batch (ADR 0015).

    A negative stock row nets against the lot with the same expiry and batch
    first, and any remainder against the lots in draw order (AUDIT-07-M1).
    So a SKU's lots sum to its stock total, and a SKU whose total is 0 or
    less has no lots.

    Args:
        stock_df: Stock DataFrame with internal column names already applied.
                  Expected columns: SKU, Stock; optional: Expiry_Date, Batch.

    Returns:
        Dict mapping SKU → list of lot dicts in draw order, or None if no lot columns.
    """
    has_expiry = "Expiry_Date" in stock_df.columns
    has_batch = "Batch" in stock_df.columns
    if not has_expiry and not has_batch:
        return None

    fifo_lots: dict[str, list[dict]] = {}

    for sku, group in stock_df.groupby("SKU"):
        rows = [
            (_lot_fields(row, has_expiry, has_batch), float(row.Stock) if pd.notna(row.Stock) else 0.0)
            for row in group.itertuples(index=False)
        ]
        lots = sorted(
            (
                {"expiry": e, "expiry_dt": d, "batch": b, "qty": qty}
                for (e, d, b), qty in rows
                if qty > 0
            ),
            key=_draw_key,
        )
        for (e, _d, b), qty in rows:
            if qty >= 0:
                continue
            debt = -qty
            same = [lot for lot in lots if (lot["expiry"], lot["batch"]) == (e, b)]
            rest = [lot for lot in lots if all(lot is not s for s in same)]
            for lot in same + rest:  # its own lot first, then draw order
                take = min(lot["qty"], debt)
                lot["qty"] -= take
                debt -= take
                if debt <= 0:
                    break
        lots = [lot for lot in lots if lot["qty"] > 0]
        if lots:
            fifo_lots[str(sku)] = lots

    return fifo_lots if fifo_lots else {}


def _clean_and_prepare_data(
    orders_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    column_mappings: dict | None = None,
    additional_columns_config: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[dict]] | None]:
    """
    Clean and standardize input data for analysis.

    Performs:
    - Apply column mappings from external sources to internal standard names
    - Handle NaN values in critical columns (forward-fill order-level columns)
    - Normalize column names and data types
    - Convert numeric columns (Quantity, Stock)
    - Normalize SKU format for consistent matching
    - Remove duplicates from stock data
    - Validate required columns exist
    - Expand sets/bundles into component SKUs

    Args:
        orders_df: Raw orders DataFrame with external column names
        stock_df: Raw stock DataFrame with external column names
        column_mappings: Configuration dictionary with column mappings and set decoders.
            Format: {
                "orders": {"External_Col": "Internal_Col", ...},
                "stock": {"External_Col": "Internal_Col", ...},
                "set_decoders": {...}
            }
            If None, uses default Shopify/Bulgarian mappings for backward compatibility.

    Returns:
        Tuple of (cleaned_orders_df, cleaned_stock_df)

    Raises:
        ValueError: If required columns missing after mapping
    """
    logger.debug("Phase 1/7: Cleaning and preparing data...")

    # --- Step 0: Apply Column Mappings ---
    if column_mappings is None:
        column_mappings = {
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Lineitem name": "Product_Name",
                "Shipping Method": "Shipping_Method",
                "Shipping Country": "Shipping_Country",
                "Tags": "Tags",
                "Notes": "Notes",
                "Total": "Total_Price",
                "Subtotal": "Subtotal",
                "Shipping Name": "Customer",
                "Created at": "Created_At",
            },
            "stock": {
                "Артикул": "SKU",
                "Име": "Product_Name",
                "Наличност": "Stock",
                "Годност": "Expiry_Date",
                "Партида": "Batch",
            },
        }

    # Get mappings for orders and stock
    orders_mappings = column_mappings.get("orders", {})

    # Apply mappings to orders DataFrame
    # Only rename columns that exist in the DataFrame AND are different from internal names
    orders_rename_map = {
        csv_col: internal_col
        for csv_col, internal_col in orders_mappings.items()
        if csv_col in orders_df.columns and csv_col != internal_col
    }
    if orders_rename_map:
        orders_df = orders_df.rename(columns=orders_rename_map)

    # Apply mappings to stock DataFrame
    stock_df = stock_with_internal_columns(stock_df, column_mappings)

    # Rename additional columns from CSV names to internal names
    if additional_columns_config:
        logger.info(
            f"Processing {len(additional_columns_config)} additional columns config"
        )
        additional_rename_map = {
            col["csv_name"]: col["internal_name"]
            for col in additional_columns_config
            if col.get("enabled", True) and col["csv_name"] in orders_df.columns
        }
        if additional_rename_map:
            orders_df = orders_df.rename(columns=additional_rename_map)
            logger.info(
                f"Renamed {len(additional_rename_map)} additional columns: {list(additional_rename_map.values())}"
            )
        else:
            logger.info(
                "No additional columns to rename (none enabled or found in CSV)"
            )

    # --- Step 1: Data Cleaning (now using internal standard names) ---
    # Forward-fill order-level columns
    if "Order_Number" in orders_df.columns:
        orders_df["Order_Number"] = orders_df["Order_Number"].ffill()
        orphans = orders_df["Order_Number"].isna()
        if orphans.any():
            # Lines above the first order number stay visible as one blocked
            # order instead of vanishing in a groupby (AUDIT-01-9).
            logger.warning(f"{int(orphans.sum())} order lines have no order number")
            orders_df.loc[orphans, "Order_Number"] = NO_ORDER_NUMBER

    # Shopify writes order-level fields on an order's first line only. Fill
    # within the order, never from the one above it: an order with no tags or
    # no shipping method must not inherit the previous order's (F3).
    order_level = [
        "Shipping_Method",
        "Shipping_Country",
        "Total_Price",
        "Subtotal",
        "Tags",
        "Customer",
        "Created_At",
    ]
    if additional_columns_config:
        order_level += [
            col["internal_name"]
            for col in additional_columns_config
            if col.get("is_order_level", False) and col.get("enabled", True)
        ]
    for col in order_level:
        if col in orders_df.columns:
            orders_df[col] = orders_df.groupby("Order_Number")[col].ffill()

    # Keep only relevant columns (internal names)
    # Base columns (critical + standard optional)
    base_columns = [
        "Order_Number",
        "SKU",
        "Quantity",
        "Shipping_Method",
        "Shipping_Country",
        "Product_Name",
        "Tags",
        "Notes",
        "Total_Price",
        "Subtotal",
        "Customer",
        "Created_At",
    ]

    # Get enabled additional columns from config
    additional_columns = []
    if additional_columns_config:
        additional_columns = [
            col["internal_name"]
            for col in additional_columns_config
            if col.get("enabled", True) and col["internal_name"] in orders_df.columns
        ]

        logger.info(f"Additional columns to keep: {len(additional_columns)} columns")
        if additional_columns:
            logger.info(f"  Columns: {additional_columns}")

        # Log if configured columns are missing from CSV
        missing_cols = [
            col["csv_name"]
            for col in additional_columns_config
            if col.get("enabled", True)
            and col["internal_name"] not in orders_df.columns
        ]
        if missing_cols:
            logger.warning(
                f"Configured additional columns not found in CSV: {missing_cols}. "
                f"These columns will be skipped."
            )

    # Combine base + additional columns
    columns_to_keep = base_columns + additional_columns
    logger.info(
        f"Total columns to keep: {len(columns_to_keep)} ({len(base_columns)} base + {len(additional_columns)} additional)"
    )
    # Filter for existing columns only
    columns_to_keep_existing = [
        col for col in columns_to_keep if col in orders_df.columns
    ]
    logger.info(f"Columns existing in DataFrame: {len(columns_to_keep_existing)}")
    orders_clean_df = orders_df[columns_to_keep_existing].copy()

    # CRITICAL: Coerce Quantity to numeric. Without this, a single stray
    # non-numeric value (e.g. a data-entry typo) leaves the whole column
    # object-dtype, and a later "> " comparison in _simulate_stock_allocation
    # crashes with TypeError for the entire batch, not just the bad row.
    # Invalid/blank values become NaN so they can be explicitly flagged
    # instead of silently summing to a phantom zero.
    if "Quantity" in orders_clean_df.columns:
        orders_clean_df["Quantity"] = pd.to_numeric(
            orders_clean_df["Quantity"], errors="coerce"
        )

    # Mark rows without SKU but keep them (don't drop)
    orders_clean_df["Has_SKU"] = orders_clean_df["SKU"].notna()

    # Log warning about missing SKU rows
    missing_sku_mask = ~orders_clean_df["Has_SKU"]
    missing_sku_count = missing_sku_mask.sum()

    if missing_sku_count > 0:
        affected_orders = orders_clean_df.loc[missing_sku_mask, "Order_Number"].unique()
        logger.warning(
            f"Found {missing_sku_count} order rows without SKU "
            f"(typically shipping fees, discounts, or notes). "
            f"Affected orders: {affected_orders.tolist()[:10]}{'...' if len(affected_orders) > 10 else ''}"
        )

        # Fill missing SKU with placeholder
        orders_clean_df.loc[missing_sku_mask, "SKU"] = "NO_SKU"

        # Add descriptive product name if missing
        if "Product_Name" in orders_clean_df.columns:
            orders_clean_df.loc[missing_sku_mask, "Product_Name"] = orders_clean_df.loc[
                missing_sku_mask, "Product_Name"
            ].fillna("(No SKU - Shipping/Fee/Note)")

    # CRITICAL: Normalize SKU to standard format for consistent merging
    # This handles float artifacts (5170.0 → "5170"), whitespace, and leading zeros
    # Skip normalization for NO_SKU placeholder

    # First, ensure SKU column is string type to avoid dtype errors (pandas 2.x uses 'str')
    dtype_str = str(orders_clean_df["SKU"].dtype)
    if (
        orders_clean_df["SKU"].dtype != object
        and dtype_str != "str"
        and not dtype_str.startswith("string")
    ):
        orders_clean_df["SKU"] = orders_clean_df["SKU"].astype(str)
    orders_clean_df.loc[orders_clean_df["Has_SKU"], "SKU"] = orders_clean_df.loc[
        orders_clean_df["Has_SKU"], "SKU"
    ].apply(normalize_sku)

    # Clean stock DataFrame (internal names)
    required_stock_cols = ["SKU", "Stock"]

    # Verify required columns exist
    missing_stock_cols = [
        col for col in required_stock_cols if col not in stock_df.columns
    ]
    if missing_stock_cols:
        raise ValueError(
            f"Missing required columns in stock DataFrame after mapping: {missing_stock_cols}"
        )

    stock_df = _normalized_stock(stock_df)

    # Detect whether lot columns (Expiry_Date / Batch) are present after mapping
    stock_lot_cols = [c for c in ["Expiry_Date", "Batch"] if c in stock_df.columns]
    lot_columns_present = bool(stock_lot_cols)

    # One total per SKU, summed with or without lots (AUDIT-01-8, owner rule).
    agg_dict: dict = {"Stock": ("Stock", "sum")}
    if "Product_Name" in stock_df.columns:
        agg_dict["Product_Name"] = ("Product_Name", "first")

    if not lot_columns_present:
        fifo_lots = None
        stock_clean_df = stock_df.dropna(subset=["SKU"]).groupby("SKU", as_index=False).agg(**agg_dict)
    else:
        # Build the FIFO lot structure before aggregation, then aggregate
        # totals per SKU so downstream merge/display shows correct total stock
        fifo_lots = _build_fifo_lots(stock_df)
        stock_agg = stock_df.groupby("SKU", as_index=False).agg(**agg_dict)
        stock_clean_df = stock_agg.dropna(subset=["SKU"]).copy()

    # --- Set/Bundle Decoding ---
    # Expand sets into component SKUs before fulfillment simulation
    # Skip NO_SKU items (they don't participate in set expansion)
    from .set_decoder import decode_sets_in_orders

    set_decoders = column_mappings.get("set_decoders", {}) if column_mappings else {}
    if set_decoders:
        logger.info(f"Decoding sets: {len(set_decoders)} definitions")
        # Only expand sets for items with actual SKU (skip NO_SKU)
        items_with_sku = orders_clean_df[orders_clean_df["Has_SKU"] == True].copy()
        no_sku_items = orders_clean_df[orders_clean_df["Has_SKU"] == False].copy()

        expanded_items = decode_sets_in_orders(items_with_sku, set_decoders)

        # Add tracking columns to NO_SKU items for consistency
        if not no_sku_items.empty:
            no_sku_items["Original_SKU"] = no_sku_items["SKU"]
            no_sku_items["Original_Quantity"] = no_sku_items["Quantity"]
            no_sku_items["Is_Set_Component"] = False

        # Combine expanded items with NO_SKU items (unchanged)
        orders_clean_df = pd.concat([expanded_items, no_sku_items], ignore_index=True)
        logger.info(f"Orders after expansion: {len(orders_clean_df)} rows")
    else:
        # No sets defined - add tracking columns anyway for consistency
        orders_clean_df["Original_SKU"] = orders_clean_df["SKU"]
        orders_clean_df["Original_Quantity"] = orders_clean_df["Quantity"]
        orders_clean_df["Is_Set_Component"] = False

    logger.debug(
        f"Cleaned {len(orders_clean_df)} order rows, {len(stock_clean_df)} SKUs"
    )
    return orders_clean_df, stock_clean_df, fifo_lots


def _prioritize_orders(
    orders_df: pd.DataFrame, mode: str = "multi_first"
) -> pd.DataFrame:
    """
    Prioritize orders for stock allocation.

    Strategy (controlled by ``mode``):
    - ``"multi_first"`` (default): multi-item orders first, then by order number ASC.
      Maximizes the number of *complete* orders fulfilled.
    - ``"fifo"``: strictly oldest order first (order number ASC), regardless of item count.

    Uses VECTORIZED groupby operations instead of iterrows().

    Args:
        orders_df: Cleaned orders DataFrame
        mode: ``"multi_first"`` or ``"fifo"``

    Returns:
        DataFrame with columns ["Order_Number", "item_count"] in priority sequence
    """
    logger.debug(f"Phase 2/7: Prioritizing orders (mode={mode})...")

    # VECTORIZED: Count items per order using groupby
    order_item_counts = orders_df.groupby("Order_Number").size().rename("item_count")

    # Merge counts back to get unique orders with their counts
    orders_with_counts = pd.merge(orders_df, order_item_counts, on="Order_Number")

    # Using order_number_sort_key avoids lexicographic issues (e.g. "#9" vs "#10").
    unique_orders = (
        orders_with_counts[["Order_Number", "item_count"]].drop_duplicates().copy()
    )
    unique_orders["_order_sort"] = unique_orders["Order_Number"].apply(
        order_number_sort_key
    )

    if mode and mode.lower() == "fifo":
        prioritized_orders = unique_orders.sort_values(
            by=["_order_sort"], ascending=True
        ).drop(columns=["_order_sort"])
    else:  # multi_first (default, existing behavior)
        prioritized_orders = unique_orders.sort_values(
            by=["item_count", "_order_sort"], ascending=[False, True]
        ).drop(columns=["_order_sort"])

    logger.debug(f"Prioritized {len(prioritized_orders)} unique orders")
    return prioritized_orders


def _simulate_stock_allocation(
    orders_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    prioritized_orders: pd.DataFrame,
    fifo_lots: dict[str, list[dict]] | None = None,
) -> tuple[dict[str, dict], dict[str, dict[str, list[dict]]]]:
    """
    Simulate stock allocation across prioritized orders.

    Algorithm:
    1. Initialize stock availability dict from stock DataFrame (or FIFO lot structure)
    2. Process orders in priority sequence
    3. For each order, check if ALL items available (all-or-nothing)
    4. Mark order as fulfillable/not fulfillable
    5. Deduct stock for fulfillable orders

    Skips items without SKU (Has_SKU=False) as they don't consume stock.

    Args:
        orders_df: Cleaned orders DataFrame with item counts
        stock_df: Stock availability DataFrame (aggregated per SKU)
        prioritized_orders: DataFrame with ["Order_Number", "item_count"] in priority order
        fifo_lots: Optional lot structure from _build_fifo_lots(). When provided,
                   consumes lots in draw order (undated, unbatched stock first, then
                   earliest expiry first) and tracks which lots were allocated per order.

    Returns:
        Tuple of (fulfillment_results, lot_allocations, final_stock_dict):
        - fulfillment_results: {order_number: {"fulfillable": bool, "reason": str}}
        - lot_allocations: {order_number: {sku: [{expiry, batch, qty_allocated}]}}
                           Empty dict when fifo_lots is None.
        - final_stock_dict: {sku: remaining_qty} after all fulfillments applied.
                            No separate replay pass recomputes it.
    """
    logger.debug("Phase 3/7: Simulating stock allocation...")

    # Filter out NO_SKU items before simulation (they don't consume stock)
    if "Has_SKU" in orders_df.columns:
        orders_for_simulation = orders_df[orders_df["Has_SKU"] == True].copy()
        no_sku_count = (~orders_df["Has_SKU"]).sum()
        if no_sku_count > 0:
            logger.debug(f"Skipping {no_sku_count} NO_SKU items from stock simulation")
    else:
        orders_for_simulation = orders_df.copy()

    # Pre-group required quantities per order — single O(N) pass avoids O(N²) per-order scans
    order_required_quantities: dict[str, pd.Series] = {
        order_num: grp.groupby("SKU")["Quantity"].sum()
        for order_num, grp in orders_for_simulation.groupby("Order_Number")
    }

    # Orders with a NaN Quantity (blank cell or failed numeric coercion) must
    # not be silently treated as needing zero units -- groupby.sum() skips
    # NaN, so an order whose only line item is invalid would otherwise look
    # like a legitimate zero-quantity order and get marked Fulfillable.
    invalid_qty_rows = orders_for_simulation[orders_for_simulation["Quantity"].isna()]
    invalid_qty_by_order: dict[str, list[str]] = (
        invalid_qty_rows.groupby("Order_Number")["SKU"].apply(list).to_dict()
        if not invalid_qty_rows.empty
        else {}
    )

    fulfillment_results = {}

    if fifo_lots is None:
        # --- LEGACY PATH (no lot tracking) ---
        # Initialize stock tracking - VECTORIZED dict creation
        live_stock = pd.Series(stock_df.Stock.values, index=stock_df.SKU).to_dict()
        lot_allocations: dict[str, dict[str, list[dict]]] = {}

        for order_number in prioritized_orders["Order_Number"]:
            if order_number in invalid_qty_by_order:
                fulfillment_results[order_number] = {
                    "fulfillable": False,
                    "reason": "; ".join(
                        f"{sku}: Missing/invalid quantity"
                        for sku in invalid_qty_by_order[order_number]
                    ),
                }
                continue

            required_quantities = order_required_quantities.get(order_number)
            if required_quantities is None:
                continue

            can_fulfill_order = True
            unfulfillable_reasons = []

            for sku, required_qty in required_quantities.items():
                available = live_stock.get(sku, 0)
                if available == 0 or required_qty > available:
                    unfulfillable_reasons.append(stock_reason(sku, required_qty, available))
                    can_fulfill_order = False

            if can_fulfill_order:
                fulfillment_results[order_number] = {"fulfillable": True, "reason": ""}
                for sku, qty in required_quantities.items():
                    live_stock[sku] -= qty
            else:
                fulfillment_results[order_number] = {
                    "fulfillable": False,
                    "reason": "; ".join(unfulfillable_reasons),
                }

        final_stock_dict = live_stock

    else:
        # --- FIFO LOT PATH ---
        live_lots = copy.deepcopy(fifo_lots)
        lot_allocations = {}

        for order_number in prioritized_orders["Order_Number"]:
            if order_number in invalid_qty_by_order:
                fulfillment_results[order_number] = {
                    "fulfillable": False,
                    "reason": "; ".join(
                        f"{sku}: Missing/invalid quantity"
                        for sku in invalid_qty_by_order[order_number]
                    ),
                }
                continue

            required_quantities = order_required_quantities.get(order_number)
            if required_quantities is None:
                continue

            can_fulfill_order = True
            unfulfillable_reasons = []

            # CHECK PHASE (read-only — don't mutate lots yet)
            for sku, needed in required_quantities.items():
                available = sum(lot["qty"] for lot in live_lots.get(sku, []))
                if available == 0 or needed > available:
                    unfulfillable_reasons.append(stock_reason(sku, needed, available))
                    can_fulfill_order = False

            # COMMIT PHASE (mutate live_lots only if order is fulfillable)
            if can_fulfill_order:
                order_alloc: dict[str, list[dict]] = {}
                for sku, needed in required_quantities.items():
                    remaining = needed
                    sku_alloc: list[dict] = []
                    for lot in live_lots.get(sku, []):
                        if remaining <= 0:
                            break
                        take = min(lot["qty"], remaining)
                        if take > 0:
                            sku_alloc.append(
                                {
                                    "expiry": lot["expiry"],
                                    "expiry_dt": lot["expiry_dt"],
                                    "batch": lot["batch"],
                                    "qty_allocated": take,
                                }
                            )
                            lot["qty"] -= take
                            remaining -= take
                    order_alloc[sku] = sku_alloc
                lot_allocations[order_number] = order_alloc
                fulfillment_results[order_number] = {"fulfillable": True, "reason": ""}
            else:
                fulfillment_results[order_number] = {
                    "fulfillable": False,
                    "reason": "; ".join(unfulfillable_reasons),
                }

        # Derive final stock from remaining live_lots; seed from stock_df for zero-stock SKUs
        # (SKUs whose all lots had qty<=0 are absent from live_lots; seed preserves them at 0)
        final_stock_dict = (
            dict(zip(stock_df["SKU"], stock_df["Stock"]))
            if "Stock" in stock_df.columns
            else {}
        )
        for sku, lots in live_lots.items():
            final_stock_dict[sku] = sum(lot["qty"] for lot in lots)

    fulfillable_count = sum(
        1 for r in fulfillment_results.values() if r.get("fulfillable", False)
    )
    logger.debug(f"Fulfillable: {fulfillable_count}/{len(fulfillment_results)} orders")

    return fulfillment_results, lot_allocations, final_stock_dict


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def with_lots(df: pd.DataFrame, lots: dict | None, mode: str = "multi_first") -> pd.DataFrame:
    """R3 (ADR 0015): each SKU line of a fulfillable order owns its lots.

    `lots` is lot_table's lots per SKU, in draw order, or None. Orders draw in the run's
    priority sequence (_prioritize_orders, `mode`), an order's lines in row
    order. Units the lots can't cover get one "no lot" entry (expiry "1"), so
    a line's entries always sum to its Quantity. Held orders, no-SKU lines and
    SKUs without lots get None. Mutates and returns df, like with_stock_left.
    """
    df["Lot_Details"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    if not lots or df.empty:
        return df
    left = {sku: [dict(lot) for lot in lot_list] for sku, lot_list in lots.items()}
    drawing = drawing_rows(df)
    keys = df["Order_Number"].astype(str).str.strip()
    rows_of = keys[drawing].groupby(keys[drawing]).groups
    quantity = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    sequence = _prioritize_orders(df[["Order_Number"]], mode)["Order_Number"]
    # One pass per key: _prioritize_orders groups raw values, so 1001 and "1001 " come twice.
    for order in dict.fromkeys(str(o).strip() for o in sequence):
        for idx in rows_of.get(order, []):
            sku_lots = left.get(df.at[idx, "SKU"])
            if sku_lots is None:
                continue
            need = float(quantity[idx])
            entries = []
            for lot in sku_lots:
                if need <= 0:
                    break
                take = min(lot["qty"], need)
                if take > 0:
                    entries.append(
                        {
                            "expiry": lot["expiry"],
                            "expiry_dt": _iso(lot["expiry_dt"]),
                            "batch": lot["batch"],
                            "qty_allocated": take,
                        }
                    )
                    lot["qty"] -= take
                    need -= take
            if need > 0:
                entries.append({"expiry": "1", "expiry_dt": None, "batch": None, "qty_allocated": need})
            df.at[idx, "Lot_Details"] = entries
    return df


def _detect_repeated_orders(
    final_df: pd.DataFrame, history_df: pd.DataFrame, current_session: str | None = None
) -> pd.Series:
    """Mark orders already shipped by another session as "Repeat" (ADR 0012).

    Sessions are compared, not dates. `history_df` is the detection frame from
    `packed_orders.union_history_with_packed`: [Order_Number, Execution_Date,
    Session, Source]. A row makes its order Repeat when:

    | source                           | counts when                                  |
    |----------------------------------|----------------------------------------------|
    | history, Session set             | Session != current_session                   |
    | history, Session empty (legacy)  | its date is before today, or unparseable     |
    | packed (Packer signal)           | always (any live session, this one included) |

    A frame without a Session column is all legacy rows; one without Source is
    all history; one without Execution_Date counts every row. With
    `current_session=None` every sessioned history row counts. Order numbers
    compare as `str(x).strip()` on both sides, so numeric and text forms match.

    Returns:
        pd.Series (string) with "Repeat" for repeated orders, "" otherwise
    """
    logger.debug("Phase 5/7: Detecting repeated orders...")

    if history_df is None or history_df.empty:
        return pd.Series("", index=final_df.index)
    h = history_df
    keys = h["Order_Number"].astype(str).str.strip()
    session = h["Session"].fillna("").astype(str) if "Session" in h.columns else pd.Series("", index=h.index)
    source = h["Source"] if "Source" in h.columns else pd.Series("history", index=h.index)
    if "Execution_Date" in h.columns:
        # Deliberately naive: pd.to_datetime yields tz-naive dates.
        today = pd.Timestamp(datetime.now().date())  # noqa: DTZ005
        dates = pd.to_datetime(h["Execution_Date"], errors="coerce", format="mixed").dt.normalize()
        before_today = dates.isna() | (dates < today)
    else:
        before_today = pd.Series(True, index=h.index)
    counts = (
        (source == "packed")
        | ((session != "") & (session != (current_session or "")))
        | ((session == "") & before_today)
    )
    repeated_orders = set(keys[counts])
    repeated = np.where(final_df["Order_Number"].astype(str).str.strip().isin(repeated_orders), "Repeat", "")

    logger.debug(f"Found {(repeated == 'Repeat').sum()} repeated orders")
    return pd.Series(repeated, index=final_df.index)


def _migrate_packaging_tags(final_df: pd.DataFrame) -> pd.DataFrame:
    """
    Migrate Packaging_Tags to Internal_Tags system.

    This handles backward compatibility by migrating old packaging tags
    to the new structured tagging system.

    Args:
        final_df: DataFrame with potential Packaging_Tags column

    Returns:
        DataFrame with updated Internal_Tags column
    """
    logger.debug("Migrating Packaging_Tags to Internal_Tags (if present)...")

    # Migrate Packaging_Tags to Internal_Tags if it exists
    if "Packaging_Tags" in final_df.columns:
        from shopify_tool.tag_manager import add_tag

        logger.info("Migrating Packaging_Tags to Internal_Tags")

        # VECTORIZED approach: Apply function to each row
        # While apply() is not fully vectorized, it's better than iterrows()
        # and necessary here because add_tag modifies a JSON string
        def migrate_tag(row):
            packaging_tag = row["Packaging_Tags"]
            if pd.notna(packaging_tag) and packaging_tag != "":
                return add_tag(row["Internal_Tags"], str(packaging_tag))
            return row["Internal_Tags"]

        final_df["Internal_Tags"] = final_df.apply(migrate_tag, axis=1)
        logger.info("Packaging_Tags migration completed")

    return final_df


def _with_fulfillment_reasons(
    notes: pd.Series, order_numbers: pd.Series, fulfillment_results: dict
) -> pd.Series:
    """`notes` with "Cannot fulfill: <reason>" added for each held order's rows.

    The reason joins an existing note with "; ". Vectorised: one dict of the
    held orders' texts, then a map (AUDIT-07-L5).
    """
    reasons = {
        order: f"Cannot fulfill: {result.get('reason', 'Unknown reason')}"
        for order, result in fulfillment_results.items()
        if isinstance(result, dict) and not result.get("fulfillable", True)
    }
    reason = order_numbers.map(reasons).to_numpy(dtype=object)
    held = pd.notna(reason)
    note = notes.to_numpy(dtype=object)
    has_note = pd.notna(note) & (note.astype(str) != "")
    out = note.copy()
    both = held & has_note
    out[both] = note[both].astype(str) + "; " + reason[both]
    out[held & ~has_note] = reason[held & ~has_note]
    return pd.Series(out, index=notes.index, name=notes.name)


def _merge_results_to_dataframe(
    orders_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    order_item_counts: pd.Series,
    final_stock_levels: pd.DataFrame,
    fulfillment_results: dict[str, str],
    history_df: pd.DataFrame,
    courier_mappings: dict | None = None,
    current_session: str | None = None,
    additional_columns_config: list | None = None,
) -> pd.DataFrame:
    """
    Merge all analysis results into final output DataFrame.

    Combines:
    - Original order data
    - Stock information
    - Fulfillment simulation results
    - Item counts
    - Final stock levels
    - Repeated orders flags
    - Courier mappings
    - All calculated fields

    Args:
        orders_df: Cleaned orders DataFrame
        stock_df: Cleaned stock DataFrame
        order_item_counts: Series with item counts per order
        final_stock_levels: DataFrame with final stock calculations
        fulfillment_results: Dict of order fulfillment statuses
        history_df: Historical fulfillment data
        courier_mappings: Optional courier mapping configuration

    Returns:
        Complete analyzed DataFrame ready for reporting

    Output Columns:
    - All original order columns
    - Stock, Final_Stock (from stock data)
    - Warehouse_Name (from stock data)
    - Order_Fulfillment_Status (from simulation)
    - Order_Type (Single/Multi)
    - Shipping_Provider (mapped)
    - Destination_Country
    - System_note (Repeat flag)
    - Stock_Alert, Status_Note (initialized)
    - Source (initialized to "Order")
    - Internal_Tags (structured tagging)
    """
    logger.debug("Phase 6/7: Merging results to final DataFrame...")

    # --- Merge orders with stock data ---
    # If both have Product_Name, prefer the one from orders (use suffixes to handle conflict)
    has_product_name_in_orders = "Product_Name" in orders_df.columns
    has_product_name_in_stock = "Product_Name" in stock_df.columns

    if has_product_name_in_orders and has_product_name_in_stock:
        # Both have Product_Name - use suffixes and prefer orders
        final_df = pd.merge(
            orders_df, stock_df, on="SKU", how="left", suffixes=("", "_stock")
        )
        # Drop stock Product_Name, keep orders Product_Name
        if "Product_Name_stock" in final_df.columns:
            final_df = final_df.drop(columns=["Product_Name_stock"])
    else:
        # Simple merge - no conflict
        final_df = pd.merge(orders_df, stock_df, on="SKU", how="left")

    # --- Add Warehouse_Name column from stock file ---
    # Create stock name lookup dictionary
    if "Product_Name" in stock_df.columns:
        stock_lookup = dict(zip(stock_df["SKU"], stock_df["Product_Name"]))

        logger.info(f"Creating Warehouse_Name lookup: {len(stock_lookup)} SKUs")

        # Add Warehouse_Name column by mapping SKU
        final_df["Warehouse_Name"] = final_df["SKU"].map(stock_lookup)

        # Fill N/A for SKUs not found in stock
        final_df["Warehouse_Name"] = final_df["Warehouse_Name"].fillna("N/A")

        # Log statistics
        matched = (final_df["Warehouse_Name"] != "N/A").sum()
        total = len(final_df)
        logger.info(f"Warehouse names: {matched}/{total} SKUs matched")
    else:
        # No Product_Name in stock file
        logger.warning("Stock file has no Product_Name column, using N/A")
        final_df["Warehouse_Name"] = "N/A"

    # Merge item counts
    final_df = pd.merge(final_df, order_item_counts, on="Order_Number")

    # Merge final stock levels to the main dataframe
    final_df = pd.merge(final_df, final_stock_levels, on="SKU", how="left")
    final_df["Final_Stock"] = final_df["Final_Stock"].fillna(
        final_df["Stock"]
    )  # If an item was not fulfilled, its final stock is its initial stock

    # Add Order_Type (Single/Multi)
    final_df["Order_Type"] = np.where(final_df["item_count"] > 1, "Multi", "Single")

    # Fill missing stock with 0
    final_df["Stock"] = final_df["Stock"].fillna(0)

    # Use Shipping_Method with underscore (internal name)
    if "Shipping_Method" in final_df.columns:
        final_df["Shipping_Provider"] = final_df["Shipping_Method"].apply(
            lambda method: _generalize_shipping_method(method, courier_mappings)
        )
    else:
        final_df["Shipping_Provider"] = "Unknown"

    # Map fulfillment results
    # Extract status from the new dict structure
    def get_fulfillment_status(order_number):
        result = fulfillment_results.get(order_number, {})
        if isinstance(result, dict):
            return (
                "Fulfillable" if result.get("fulfillable", False) else "Not Fulfillable"
            )
        # Backward compatibility: if result is a string
        return result

    final_df["Order_Fulfillment_Status"] = final_df["Order_Number"].map(
        get_fulfillment_status
    )

    # Destination_Country now populated for ALL couriers (not just DHL)
    # All major couriers (DHL, PostOne, DPD) ship internationally
    # This enables country display on barcode labels for all orders
    if "Shipping_Country" in final_df.columns:
        final_df["Destination_Country"] = final_df["Shipping_Country"].fillna("")
    else:
        final_df["Destination_Country"] = ""

    # Detect repeated orders - VECTORIZED
    final_df["System_note"] = _detect_repeated_orders(
        final_df, history_df, current_session
    )

    # Add unfulfillable reasons to System_note
    final_df["System_note"] = _with_fulfillment_reasons(
        final_df["System_note"], final_df["Order_Number"], fulfillment_results
    )

    # Mark NO_SKU orders as Not Fulfillable with explanation
    if "Has_SKU" in final_df.columns:
        no_sku_mask = final_df["Has_SKU"] == False
        if no_sku_mask.any():
            final_df.loc[no_sku_mask, "Order_Fulfillment_Status"] = "Not Fulfillable"
            # Add NO_SKU tag to System_note
            final_df.loc[no_sku_mask, "System_note"] = final_df.loc[
                no_sku_mask, "System_note"
            ].apply(
                lambda note: (
                    f"{note} [NO_SKU]" if pd.notna(note) and note != "" else "[NO_SKU]"
                )
            )
            logger.info(f"Marked {no_sku_mask.sum()} NO_SKU items as Not Fulfillable")

    # Initialize additional columns
    final_df["Stock_Alert"] = ""  # Initialize the column
    final_df["Status_Note"] = ""  # Initialize column for user-defined rule tags

    # Initialize Source column (all orders start as "Order")
    final_df["Source"] = "Order"

    # Initialize Internal_Tags column (structured tagging system)
    final_df["Internal_Tags"] = "[]"

    # Migrate Packaging_Tags to Internal_Tags if it exists
    final_df = _migrate_packaging_tags(final_df)

    final_df["Lot_Details"] = None

    # Select and order output columns
    output_columns = [
        "Order_Number",
        "Order_Type",
        "SKU",
        "Product_Name",
        "Warehouse_Name",  # From stock file
        "Quantity",
        "Stock",
        "Final_Stock",
        "Source",  # "Order" or "Manual"
        "Stock_Alert",
        "Order_Fulfillment_Status",
        "Shipping_Provider",
        "Destination_Country",
        "Shipping_Method",
        "Tags",
        "Notes",
        "System_note",
        "Status_Note",
        "Internal_Tags",  # Structured tagging system
        "Lot_Details",  # Per-lot FIFO allocation data (None when no lot tracking)
        # Appended last so the positional inserts below (3, 6, 7) do not move.
        "Customer",
        "Created_At",
    ]
    if "Total_Price" in final_df.columns:
        # Insert 'Total_Price' into the list at a specific position for consistent column order.
        # Placed after 'Quantity'.
        output_columns.insert(6, "Total_Price")
    if "Subtotal" in final_df.columns:
        # Insert 'Subtotal' after Total_Price (position 7)
        output_columns.insert(7, "Subtotal")
    if "Has_SKU" in final_df.columns:
        # Insert 'Has_SKU' after SKU (position 3)
        output_columns.insert(3, "Has_SKU")

    # IMPORTANT: Add additional columns from configuration
    # Only add columns that are:
    # 1. Enabled in the configuration
    # 2. Actually present in the DataFrame
    if additional_columns_config:
        enabled_additional = [
            col["internal_name"]
            for col in additional_columns_config
            if col.get("enabled", False) and col["internal_name"] in final_df.columns
        ]

        if enabled_additional:
            logger.info(
                f"Adding {len(enabled_additional)} enabled additional columns to output: {enabled_additional}"
            )
            # Add enabled additional columns at the end
            output_columns.extend(enabled_additional)
        else:
            logger.debug("No enabled additional columns to add to output")
    else:
        logger.debug("No additional columns configuration provided")

    # Filter the list to include only columns that actually exist in the DataFrame.
    # This prevents errors if a column is unexpectedly missing.
    final_output_columns = [col for col in output_columns if col in final_df.columns]
    final_df = final_df[
        final_output_columns
    ].copy()  # Use .copy() to avoid SettingWithCopyWarning

    logger.debug(
        f"Final DataFrame: {len(final_df)} rows, {len(final_df.columns)} columns"
    )
    return final_df


def summary_present(final_df: pd.DataFrame) -> pd.DataFrame:
    """Units per SKU that the fulfillable orders ship: the Summary_Present sheet.

    Columns: Name, SKU, Total Quantity. Computed after rules (AUDIT-06-5).
    """
    from shopify_tool.report_filters import (
        fulfillable_only,  # local: avoids an import cycle
    )

    present_df = fulfillable_only(final_df)
    if "Product_Name" in present_df.columns:
        summary = present_df.groupby(["SKU", "Product_Name"], as_index=False)["Quantity"].sum()
        summary = summary.rename(columns={"Product_Name": "Name", "Quantity": "Total Quantity"})
    else:
        summary = present_df.groupby(["SKU"], as_index=False)["Quantity"].sum()
        summary["Name"] = "N/A"
        summary = summary.rename(columns={"Quantity": "Total Quantity"})
    return summary[["Name", "SKU", "Total Quantity"]]


def _generalize_shipping_method(method, courier_mappings=None):
    """Standardizes raw shipping method names to a consistent format.

    Takes a raw shipping method string, converts it to lowercase, and maps it
    to a standardized provider name using either the provided courier_mappings
    or hardcoded fallback rules.

    The function supports two courier_mappings formats:
    1. New format (preferred):
       {"DHL": {"patterns": ["dhl", "dhl express"]}, "DPD": {"patterns": ["dpd"]}}
    2. Legacy format (for backward compatibility):
       {"dhl": "DHL", "dpd": "DPD"}

    If the method is not recognized, it returns a title-cased version of the
    input. Handles NaN values by returning 'Unknown'.

    Args:
        method (str | float): The raw shipping method from the orders file.
            Can be a float (NaN) for empty values.
        courier_mappings (dict, optional): Dictionary mapping courier patterns to
            standardized courier codes. If None or empty, uses hardcoded fallback
            rules for backward compatibility.

    Returns:
        str: The standardized shipping provider name.

    Examples:
        >>> _generalize_shipping_method("dhl express", {"DHL": {"patterns": ["dhl"]}})
        'DHL'
        >>> _generalize_shipping_method("custom courier", {})
        'Custom Courier'
        >>> _generalize_shipping_method(None)
        'Unknown'
    """
    # Handle NaN and empty values
    if pd.isna(method):
        return "Unknown"
    method_str = str(method)
    if not method_str.strip():
        return "Unknown"

    method_lower = method_str.lower()

    # If courier_mappings provided and not empty, use dynamic mapping
    if courier_mappings:
        # Check if new format (dict of dicts with "patterns" key)
        # or legacy format (simple dict mapping)
        for courier_code, mapping_data in courier_mappings.items():
            if isinstance(mapping_data, dict):
                # New format: {"DHL": {"patterns": ["dhl", "dhl express"]}}
                patterns = mapping_data.get("patterns", [])
                for pattern in patterns:
                    if pattern.lower() in method_lower:
                        return courier_code
            else:
                # Legacy format: {"dhl": "DHL"}
                # Check if the pattern (key) is in the method
                if courier_code.lower() in method_lower:
                    return mapping_data
    else:
        # Fallback to hardcoded rules for backward compatibility
        if "dhl" in method_lower:
            return "DHL"
        if "dpd" in method_lower:
            return "DPD"
        if "international shipping" in method_lower:
            return "PostOne"

    # If no match found, return title-cased version
    return method_str.title()


def run_analysis(
    stock_df,
    orders_df,
    history_df,
    column_mappings=None,
    courier_mappings=None,
    current_session=None,
    mode: str = "multi_first",
):
    """
    Main analysis engine for order fulfillment simulation.

    Orchestrates complete analysis workflow through 7 specialized phases:
    1. Data cleaning and preparation
    2. Order prioritization
    3. Stock allocation simulation
    4. Final stock calculations
    5. Repeated orders detection
    6. Results merging to final DataFrame
    7. Summary statistics generation

    Algorithm:
    - Prioritizes orders per ``mode`` (see below)
    - Simulates stock allocation in priority sequence
    - Tracks repeated orders against history
    - Provides comprehensive fulfillment analytics

    This function operates purely on DataFrames and does not perform any
    file I/O.

    Args:
        stock_df (pd.DataFrame): DataFrame with stock levels for each SKU.
            Column names will be mapped according to column_mappings['stock'].
        orders_df (pd.DataFrame): DataFrame with all order line items.
            Column names will be mapped according to column_mappings['orders'].
        history_df (pd.DataFrame): DataFrame with previously fulfilled order
            numbers. Requires an 'Order_Number' column.
        column_mappings (dict, optional): Dictionary with 'orders' and 'stock' keys,
            each containing a mapping of CSV column names to internal standard names.
            Example: {"orders": {"Name": "Order_Number", "Lineitem sku": "SKU"},
                     "stock": {"Артикул": "SKU", "Наличност": "Stock"}}
            If None, uses default Shopify/Bulgarian mappings for backward compatibility.
        courier_mappings (dict, optional): Dictionary mapping courier patterns to
            standardized courier codes. Supports two formats:
            1. New: {"DHL": {"patterns": ["dhl", "dhl express"]}}
            2. Legacy: {"dhl": "DHL"}
            If None or empty, uses hardcoded fallback rules for backward compatibility.
        current_session (str, optional): Name of the session this run belongs
            to. History rows from this session never mark a repeat; rows from
            other sessions do. See `_detect_repeated_orders`.
        mode (str, optional): Order prioritization strategy.
            ``"multi_first"`` (default): multi-item orders processed first —
            maximizes the number of complete orders fulfilled.
            ``"fifo"``: strictly oldest order first regardless of item count.

    Returns:
        tuple[pd.DataFrame, dict]:
            A tuple containing two elements:
            - final_df (pd.DataFrame): The main DataFrame with detailed results
              for every line item, including the calculated
              'Order_Fulfillment_Status'.
            - stats (dict): A dictionary containing key statistics about the
              fulfillment analysis (e.g., total orders completed).

            Summary_Present is computed separately, after rules, via
            `summary_present(final_df)` (AUDIT-06-5).

    Raises:
        ValueError: If data validation fails
        KeyError: If required columns missing

    Example:
        >>> final_df, stats = run_analysis(
        ...     stock_df=stock,
        ...     orders_df=orders,
        ...     history_df=history
        ... )
    """
    logger.info("=" * 60)
    logger.info("STARTING ORDER FULFILLMENT ANALYSIS")
    logger.info("=" * 60)

    try:
        # Phase 1: Clean and prepare data
        logger.info("Phase 1/7: Data cleaning and preparation")

        # Extract additional columns config if present
        additional_columns_config = (
            column_mappings.get("additional_columns", []) if column_mappings else []
        )
        enabled_additional = [
            col for col in additional_columns_config if col.get("enabled", False)
        ]
        logger.info(
            f"Additional columns: {len(additional_columns_config)} total, {len(enabled_additional)} enabled"
        )
        if enabled_additional:
            logger.info(
                f"Enabled columns: {[col['csv_name'] for col in enabled_additional]}"
            )

        orders_clean, stock_clean, fifo_lots = _clean_and_prepare_data(
            orders_df, stock_df, column_mappings, additional_columns_config
        )
        if fifo_lots is not None:
            logger.info(f"FIFO lot tracking enabled for {len(fifo_lots)} SKUs")

        logger.info(
            f"After cleaning: orders_clean has {len(orders_clean.columns)} columns: {list(orders_clean.columns)}"
        )

        # Phase 2: Prioritize orders
        logger.info(f"Phase 2/7: Order prioritization (mode={mode})")
        prioritized_orders = _prioritize_orders(orders_clean, mode=mode)
        prioritized_orders = prioritized_orders[
            prioritized_orders["Order_Number"] != NO_ORDER_NUMBER
        ]

        # Phase 3: Simulate stock allocation
        logger.info("Phase 3/7: Stock allocation simulation")
        fulfillment_results, _lot_allocations, final_stock_dict = (
            _simulate_stock_allocation(
                orders_clean, stock_clean, prioritized_orders, fifo_lots
            )
        )
        if (orders_clean["Order_Number"] == NO_ORDER_NUMBER).any():
            fulfillment_results[NO_ORDER_NUMBER] = {
                "fulfillable": False,
                "reason": "No order number",
            }

        # Phase 4: Convert live stock dict to DataFrame (no replay needed — simulation already tracked it)
        logger.info("Phase 4/7: Final stock calculations")
        final_stock = (
            pd.Series(final_stock_dict, name="Final_Stock")
            .reset_index()
            .rename(columns={"index": "SKU"})
        )

        # Phase 5: Already handled in Phase 6 (_detect_repeated_orders is called there)
        # Phase 6: Merge all results
        logger.info("Phase 5/7: Merging results to final DataFrame")
        order_item_counts = (
            orders_clean.groupby("Order_Number").size().rename("item_count")
        )
        final_df = _merge_results_to_dataframe(
            orders_clean,
            stock_clean,
            order_item_counts,
            final_stock,
            fulfillment_results,
            history_df,
            courier_mappings,
            current_session,
            additional_columns_config,
        )
        final_df = with_lots(final_df, fifo_lots, mode)

        # Phase 7: Calculate statistics
        logger.info("Phase 7/7: Calculating statistics")
        stats = recalculate_statistics(final_df)

        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETED SUCCESSFULLY")
        logger.info(f"Total Orders Completed: {stats['total_orders_completed']}")
        logger.info(
            f"Total Orders Not Completed: {stats['total_orders_not_completed']}"
        )
        logger.info(
            f"Final DataFrame: {len(final_df)} rows, {len(final_df.columns)} columns"
        )
        logger.info(f"Columns: {list(final_df.columns)}")
        logger.info("=" * 60)

        return final_df, stats

    except ValueError:
        logger.exception("Validation error during analysis")
        raise
    except KeyError:
        logger.exception("Missing required column")
        raise
    except Exception:
        logger.exception("Unexpected error during analysis")
        raise


def recalculate_statistics(df):
    """Calculates statistics based on the provided analysis DataFrame.

    Aggregates data from the main analysis DataFrame to produce a summary
    of key metrics, such as the number of completed orders, total items,
    and a breakdown of orders per shipping courier.

    Args:
        df (pd.DataFrame): The main analysis DataFrame, which must contain
            'Order_Fulfillment_Status', 'Order_Number', 'Quantity',
            'Shipping_Provider', and 'System_note' columns.

    Returns:
        dict: A dictionary containing key statistics, including:
            - 'total_orders_completed' (int)
            - 'total_orders_not_completed' (int)
            - 'total_items_to_write_off' (int)
            - 'total_items_not_to_write_off' (int)
            - 'couriers_stats' (list[dict] | None): A list of dictionaries,
              each representing a courier's stats, or None if no orders
              were completed.
            - 'tags_breakdown' (dict | None): Dictionary mapping tags to counts.
            - 'sku_summary' (list[dict] | None): List of SKU summary data.
    """
    # Validate DataFrame has required columns
    # Shipping_Provider is optional - older sessions may not have it
    required_cols = [
        "Order_Fulfillment_Status",
        "Order_Number",
        "Quantity",
        "System_note",
    ]
    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        logger.error(f"Missing required columns in DataFrame: {missing}")
        logger.error(f"Available columns: {list(df.columns)}")
        raise ValueError(f"DataFrame missing required columns: {missing}")

    # Add Shipping_Provider if missing (older sessions may not have it)
    if "Shipping_Provider" not in df.columns:
        logger.warning("Shipping_Provider column missing - defaulting to 'Unknown'")
        df = df.copy()
        df["Shipping_Provider"] = "Unknown"

    stats = {}
    from shopify_tool.report_filters import (
        fulfillable_only,  # local: avoids an import cycle
    )

    completed_orders_df = fulfillable_only(df).copy()
    not_completed_orders_df = df.drop(index=completed_orders_df.index)

    stats["total_orders_completed"] = int(completed_orders_df["Order_Number"].nunique())
    stats["total_orders_not_completed"] = (
        int(df["Order_Number"].nunique()) - stats["total_orders_completed"]
    )
    stats["total_items_to_write_off"] = int(completed_orders_df["Quantity"].sum())
    stats["total_items_not_to_write_off"] = int(
        not_completed_orders_df["Quantity"].sum()
    )

    courier_stats = []
    if not completed_orders_df.empty:
        # Fill NA to include 'Unknown' providers in the stats
        completed_orders_df.loc[:, "Shipping_Provider"] = completed_orders_df[
            "Shipping_Provider"
        ].fillna("Unknown")
        grouped_by_courier = completed_orders_df.groupby("Shipping_Provider")
        for provider, group in grouped_by_courier:
            courier_data = {
                "courier_id": provider,
                "orders_assigned": int(group["Order_Number"].nunique()),
                "repeated_orders_found": int(
                    group[group["System_note"] == "Repeat"]["Order_Number"].nunique()
                ),
            }
            courier_stats.append(courier_data)
    # Keep empty list as is - UI will handle display appropriately
    stats["couriers_stats"] = courier_stats

    # === Tags Breakdown (split by fulfillment status, counted per unique order) ===
    # Each tag is counted once per ORDER that has it (union of tags across all SKU rows of the order).
    tags_breakdown = None
    tags_breakdown_fulfillable = None
    tags_breakdown_not_fulfillable = None
    if "Internal_Tags" in df.columns:
        try:
            from shopify_tool.tag_manager import parse_tags

            def _build_order_tag_counts(rows_df):
                """Count how many orders have each tag (union across all rows per order).

                Vectorized: parse → explode → deduplicate (order, tag) → value_counts.
                """
                if rows_df.empty:
                    return {}
                exploded = (
                    rows_df[["Order_Number", "Internal_Tags"]]
                    .assign(
                        Internal_Tags=lambda d: (
                            d["Internal_Tags"].fillna("[]").apply(parse_tags)
                        )
                    )
                    .explode("Internal_Tags")
                    .rename(columns={"Internal_Tags": "tag"})
                    .dropna(subset=["tag"])
                )
                exploded = exploded[exploded["tag"].astype(str).str.len() > 0]
                if exploded.empty:
                    return {}
                counts = exploded.drop_duplicates()["tag"].value_counts()
                return dict(counts.items())

            fulfillable_df = completed_orders_df
            not_fulfillable_df = not_completed_orders_df

            tags_breakdown_fulfillable = _build_order_tag_counts(fulfillable_df)
            tags_breakdown_not_fulfillable = _build_order_tag_counts(not_fulfillable_df)
            # Backward-compat key: fulfillable tags (primary view for UI)
            tags_breakdown = tags_breakdown_fulfillable

            logger.info(
                f"Tags breakdown: {len(tags_breakdown_fulfillable)} fulfillable, "
                f"{len(tags_breakdown_not_fulfillable)} not-fulfillable unique tags"
            )

        except Exception:
            logger.exception("Failed to calculate tags breakdown")

    # === NEW: SKU Summary ===
    sku_summary = None
    try:
        # Create a helper column for fulfillable quantity
        df_temp = df.copy()
        df_temp["Fulfillable_Qty"] = df_temp["Quantity"].where(
            df_temp.index.isin(completed_orders_df.index), 0
        )

        # Group by SKU and aggregate
        sku_groups = (
            df_temp.groupby("SKU")
            .agg(
                {
                    "Quantity": "sum",  # Total quantity across all orders
                    "Product_Name": "first",  # Product name (should be same for all rows)
                    "Warehouse_Name": "first",  # Warehouse name from stock
                    "Fulfillable_Qty": "sum",  # Sum of fulfillable quantities
                }
            )
            .reset_index()
        )

        # Rename columns for clarity
        sku_groups.columns = [
            "SKU",
            "Total_Quantity",
            "Product_Name",
            "Warehouse_Name",
            "Fulfillable_Items",
        ]

        # Calculate not fulfillable items
        sku_groups["Not_Fulfillable_Items"] = (
            sku_groups["Total_Quantity"] - sku_groups["Fulfillable_Items"]
        )

        # Sort by total quantity (descending)
        sku_groups = sku_groups.sort_values("Total_Quantity", ascending=False)

        # Convert to list of dicts
        sku_summary = sku_groups.to_dict("records")

        logger.info(f"SKU summary calculated: {len(sku_summary)} unique SKUs")

    except Exception:
        logger.exception("Failed to calculate SKU summary")
        sku_summary = None

    stats["tags_breakdown"] = tags_breakdown
    stats["tags_breakdown_fulfillable"] = tags_breakdown_fulfillable
    stats["tags_breakdown_not_fulfillable"] = tags_breakdown_not_fulfillable
    stats["sku_summary"] = sku_summary

    return stats


def toggle_order_fulfillment(df, order_number):
    """Manually toggles the fulfillment status of an order and re-derives Stock left.

    This function allows a user to manually override the automated fulfillment
    decision for a single order.

    - An order is 'Fulfillable' when every one of its SKU lines is (R1, see
      ``stock_ledger``). Toggling one flips every line of it.
    - Holding returns its stock to the pool. Force-fulfilling first checks that
      Stock left covers the order and fails if it does not.
    - 'Final_Stock' is never adjusted by hand: it is re-derived from Stock and
      the fulfillable orders (R2, ADR 0010).

    The function operates on and returns a modified copy of the input DataFrame.

    Args:
        df (pd.DataFrame): The main analysis DataFrame.
        order_number (str): The order number to toggle.

    Returns:
        tuple[bool, str | None, pd.DataFrame]: A tuple containing:
            - success (bool): True if the toggle was successful, False otherwise.
            - message (str | None): The error when it fails. When it succeeds,
              a warning or None: force-fulfilling an order with a SKU the
              stock file doesn't list is allowed, and the warning names the
              SKUs (AUDIT-09-O3).
            - updated_df (pd.DataFrame): The modified DataFrame. If the toggle
              fails, this is the original, unmodified DataFrame.
    """
    if df is None:
        return False, "DataFrame is None.", df

    order_mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
    if not order_mask.any():
        return False, "Order number not found.", df

    if is_fulfillable(df, order_number):
        new_status = NOT_FULFILLABLE
    else:
        lacking = shortfall(df, order_number)
        if lacking:
            return (
                False,
                "Cannot force fulfill. Insufficient stock for SKUs: "
                + ", ".join(map(str, lacking)),
                df,
            )
        new_status = FULFILLABLE

    df.loc[order_mask, "Order_Fulfillment_Status"] = new_status
    df = with_stock_left(df)
    unlisted = unlisted_skus(df, [order_number]) if new_status == FULFILLABLE else []
    if unlisted:
        return True, f"Not in the stock file: {', '.join(unlisted)}", df
    return True, None, df
