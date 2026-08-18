"""Read the orders Packing Tool has finished packing.

Packing Tool records the order numbers it completed into the
`packing_progress` block of each session's `session_info.json`, which this
repo mirrors into the per-client `session_index.json` cache. Reading that
one file per client avoids walking the session tree on the network share.

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

    try:
        sessions_root = Path(profile_manager.get_sessions_root())
        index_path = sessions_root / f"CLIENT_{client_id.upper()}" / INDEX_FILENAME
        if not index_path.exists():
            logger.debug(f"No session index for packed orders: {index_path}")
            return _empty()
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, AttributeError):
        logger.exception("Could not read packed orders; repeat detection will use analysis history only")
        return _empty()

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
            if not orders:
                # Written before completed_orders existed, or nothing packed.
                continue
            packed_date = _to_date(block.get("updated_at") or block.get("started_at"))
            if packed_date is None:
                continue
            rows.extend(
                {"Order_Number": str(o), "Execution_Date": packed_date}
                for o in orders
                if o
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
    """ISO timestamp -> 'YYYY-MM-DD', or None if unparseable."""
    if not timestamp:
        return None
    parsed = pd.to_datetime(timestamp, errors="coerce", utc=True)
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
    """
    frames = [f for f in (history_df, packed_df) if f is not None and not f.empty]
    if not frames:
        return _empty()

    combined = pd.concat(frames, ignore_index=True)[COLUMNS]
    combined = combined.sort_values("Execution_Date").drop_duplicates(
        subset=["Order_Number"], keep="first"
    )
    return combined.reset_index(drop=True)
