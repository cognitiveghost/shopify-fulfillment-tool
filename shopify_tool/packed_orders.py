"""Read the orders Packing Tool has finished packing.

Packing Tool records the order numbers it completed into the
`packing_progress` block of each session's `session_info.json`. This module
reads them through `SessionManager.list_client_sessions()`, which serves the
per-client `session_index.json` cache -- one network read instead of a walk
of the session tree.

Going through that method rather than reading the index file directly is
load-bearing, not stylistic: it is the only path that runs
`SessionManager._index_is_stale()`, which rebuilds the index when a session
directory is newer than it. Packing Tool's writes are exactly that case, so
a raw index read would report the packed orders as empty forever.

Everything here is best-effort by contract: a missing file, malformed JSON
or an old-format entry yields an empty result and a log line. Repeat
detection then degrades to using analysis history alone. An analysis must
never fail because the packing signal is unavailable -- the warehouse can
still ship.
"""

import logging

import pandas as pd

from .session_manager import SessionManager

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date"]


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
    entries = SessionManager(profile_manager).list_client_sessions(client_id)

    rows = []
    for entry in entries:
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
