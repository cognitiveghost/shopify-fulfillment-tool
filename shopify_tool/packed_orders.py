"""Read the orders Packing Tool has finished packing.

Packing Tool records the order numbers it completed into the
`packing_progress` block of each session's `session_info.json`. This module
reads them from the per-client `session_index.json` cache, which is one
network read instead of a walk of the session tree.

**Freshness caveat.** That index is SFT-owned and is refreshed only by SFT's
own writes (`SessionManager._upsert_index_entry`) or by its directory-count
staleness check. Packing Tool writing `session_info.json` triggers neither,
so a session's `completed_orders` reach the index only if SFT happens to
rewrite that session afterwards. Until that transport is fixed, this module
under-reports rather than over-reports: it can miss packed orders, never
invent them.

Everything here is best-effort by contract: a missing file, malformed JSON
or an old-format entry yields an empty result and a log line. Repeat
detection then degrades to using analysis history alone. An analysis must
never fail because the packing signal is unavailable -- the warehouse can
still ship.
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date"]

INDEX_FILENAME = "session_index.json"


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def load_packed_orders(profile_manager, client_id: str) -> pd.DataFrame:
    """Order numbers Packing Tool has completed, with the date packed.

    Args:
        profile_manager: provides get_sessions_root()
        client_id: client identifier, case-insensitive

    Returns:
        DataFrame with columns [Order_Number, Execution_Date] (dates as
        YYYY-MM-DD strings), earliest date per order. Empty on any failure.
    """
    if not profile_manager or not client_id:
        return _empty()

    # Broad by design: every value below comes from a file another tool
    # writes, and no shape it can take may abort the analysis.
    try:
        return _load_packed_orders(profile_manager, client_id)
    except Exception:
        logger.exception("Could not read packed orders; repeat detection will use analysis history only")
        return _empty()


def _load_packed_orders(profile_manager, client_id: str) -> pd.DataFrame:
    sessions_root = Path(profile_manager.get_sessions_root())
    index_path = sessions_root / f"CLIENT_{client_id.upper()}" / INDEX_FILENAME
    if not index_path.exists():
        logger.debug(f"No session index for packed orders: {index_path}")
        return _empty()
    entries = json.loads(index_path.read_text(encoding="utf-8"))

    if not isinstance(entries, list):
        logger.warning("Session index is not a list; ignoring packed orders")
        return _empty()

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        progress = entry.get("packing_progress")
        if not isinstance(progress, dict):
            continue
        for block in progress.values():
            if not isinstance(block, dict):
                continue
            orders = block.get("completed_orders")
            # A bare string is iterable and would yield one row per
            # character, so the list check is load-bearing, not defensive.
            if not isinstance(orders, list) or not orders:
                # Written before completed_orders existed, or nothing packed.
                continue
            packed_date = _to_date(block.get("updated_at") or block.get("started_at"))
            if packed_date is None:
                continue
            rows.extend(
                {"Order_Number": str(o), "Execution_Date": packed_date}
                for o in orders
                if isinstance(o, str) and o
            )

    if not rows:
        return _empty()

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values("Execution_Date").drop_duplicates(
        subset=["Order_Number"], keep="first"
    )
    logger.info(f"Loaded {len(df)} packed orders for repeat detection ({client_id})")
    return df.reset_index(drop=True)


def _to_date(timestamp) -> str | None:
    """ISO timestamp -> 'YYYY-MM-DD', or None if unparseable.

    Deliberately NOT utc=True. The stamp carries the warehouse's local
    offset, and `analysis._detect_repeated_orders` compares against a naive
    local `datetime.now()`. Normalising to UTC would date orders packed
    after midnight-minus-offset to the previous day, flagging a fresh order
    as a repeat on the same working day.
    """
    if not isinstance(timestamp, str) or not timestamp:
        return None
    parsed = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def union_history_with_packed(
    history_df: pd.DataFrame, packed_df: pd.DataFrame
) -> pd.DataFrame:
    """Combine analysis history with packed orders, earliest date per order.

    An order is a repeat if it was seen at least N days ago in EITHER
    source, so the earliest sighting is the one that matters. The result is
    for detection only -- it must never be written to
    fulfillment_history.csv, which is this repo's own record of what it
    analyzed.

    Returns `history_df` untouched if it cannot be unioned, so the
    backward-compatibility branch in `_detect_repeated_orders` still sees
    the shape it expects.
    """
    if history_df is not None and not history_df.empty:
        missing = [c for c in COLUMNS if c not in history_df.columns]
        if missing:
            # Legacy history file. _detect_repeated_orders handles this
            # shape itself; unioning here would only break it.
            logger.debug(f"History missing {missing}; skipping packed-order union")
            return history_df

    frames = [f for f in (history_df, packed_df) if f is not None and not f.empty]
    if not frames:
        return _empty()

    combined = pd.concat(frames, ignore_index=True).reindex(columns=COLUMNS)
    # Sort on parsed dates, not the strings: a legacy row in another format
    # ("27/11/2025") would otherwise sort wrong and win "earliest".
    order = pd.to_datetime(combined["Execution_Date"], errors="coerce", format="mixed")
    combined = combined.assign(_sort_key=order).sort_values(
        "_sort_key", na_position="last"
    )
    combined = combined.drop_duplicates(subset=["Order_Number"], keep="first")
    return combined.drop(columns="_sort_key").reset_index(drop=True)
