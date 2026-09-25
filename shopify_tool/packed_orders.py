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
from pathlib import Path

import pandas as pd

from .session_manager import SessionManager

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date", "Session"]


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def _session_name(entry) -> str:
    name = entry.get("session_name") or Path(str(entry.get("session_path") or "")).name
    return str(name or "")


def load_session_signals(profile_manager, client_id: str) -> tuple[pd.DataFrame, set[str] | None]:
    """The orders Packing Tool has completed, and which sessions are live.

    Args:
        profile_manager: provides get_sessions_root()
        client_id: client identifier, case-insensitive

    Returns:
        (packed, live). `packed` has columns [Order_Number, Execution_Date,
        Session] (dates as YYYY-MM-DD strings), earliest date per order and
        session. `live` is the names of the sessions whose status isn't
        "abandoned". On any failure `packed` is empty and `live` is None,
        which means "unknown": nothing may be filtered by it, so a failed
        index read never hides every sessioned history row.
    """
    if not profile_manager or not client_id:
        return _empty(), None

    # Broad by design: every value below comes from a file another tool
    # writes, and no shape it can take may abort the analysis.
    try:
        return _load_session_signals(profile_manager, client_id)
    except Exception:
        logger.exception("Could not read packed orders; repeat detection will use analysis history only")
        return _empty(), None


def _load_session_signals(profile_manager, client_id: str) -> tuple[pd.DataFrame, set[str] | None]:
    entries = SessionManager(profile_manager).list_client_sessions(client_id)
    if not entries:
        # An unreachable sessions folder also lists as empty. Rows can't name
        # sessions that never existed, so "no sessions" is "unknown".
        return _empty(), None
    live = {
        _session_name(e)
        for e in entries
        if isinstance(e, dict) and e.get("status") != "abandoned" and _session_name(e)
    }

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
            # started_at, not updated_at. A packing list left open across
            # days carries ONE updated_at for the whole block, so dating by
            # it re-dates every order already packed in that list to the
            # later day: an order packed Monday looks "packed today" on
            # Tuesday, never gets flagged Repeat, and ships a second time.
            # started_at is the stable lower bound the earliest-wins union
            # below actually wants. The cost is the opposite error -- an
            # order packed on day 2 is flagged a day early -- which is a
            # badge reading "already packed", and that is still true.
            #
            # Fall back per-parse, not per-value: a block whose started_at is
            # garbage still has a usable updated_at, and `a or b` on the raw
            # values would pick the garbage and drop the whole block.
            packed_date = _to_date(block.get("started_at")) or _to_date(
                block.get("updated_at")
            )
            if packed_date is None:
                continue
            session = _session_name(entry)
            rows.extend(
                {"Order_Number": o, "Execution_Date": packed_date, "Session": session}
                for o in orders
                if isinstance(o, str) and o
            )

    if not rows:
        return _empty(), live

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values("Execution_Date").drop_duplicates(
        subset=["Order_Number", "Session"], keep="first"
    )
    logger.info(f"Loaded {len(df)} packed orders for repeat detection ({client_id})")
    return df.reset_index(drop=True), live


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
    history_df: pd.DataFrame, packed_df: pd.DataFrame, live_sessions: set[str] | None = None
) -> pd.DataFrame:
    """Combine analysis history with packed orders into the detection frame.

    Columns: [Order_Number, Execution_Date, Session, Source], Source being
    "history" or "packed". The two sources follow different rules in
    `_detect_repeated_orders`, so a row per (order, session, source) is kept,
    the earliest date each. The result is for detection only -- it must never
    be written to fulfillment_history.csv, which is this repo's own record of
    what it analyzed.

    Rows whose Session is set and isn't in `live_sessions` (abandoned or
    deleted sessions) are dropped. `live_sessions=None` means the session
    index couldn't be read: nothing is filtered.

    Returns `history_df` untouched if it cannot be unioned, so the
    backward-compatibility branch in `_detect_repeated_orders` still sees
    the shape it expects.
    """
    if history_df is not None and not history_df.empty:
        missing = [c for c in ("Order_Number", "Execution_Date") if c not in history_df.columns]
        if missing:
            # Legacy history file. _detect_repeated_orders handles this
            # shape itself; unioning here would only break it.
            logger.debug(f"History missing {missing}; skipping packed-order union")
            return history_df

    out_cols = COLUMNS + ["Source"]
    frames = [
        f.reindex(columns=COLUMNS).fillna({"Session": ""}).assign(Source=source)
        for f, source in ((history_df, "history"), (packed_df, "packed"))
        if f is not None and not f.empty
    ]
    if not frames:
        return pd.DataFrame(columns=out_cols)

    combined = pd.concat(frames, ignore_index=True)
    if live_sessions is not None:
        dead = (combined["Session"] != "") & ~combined["Session"].isin(live_sessions)
        combined = combined[~dead]
    # Sort on parsed dates, not the strings: a legacy row in another format
    # ("27/11/2025") would otherwise sort wrong and win "earliest".
    order = pd.to_datetime(combined["Execution_Date"], errors="coerce", format="mixed")
    combined = combined.assign(_sort_key=order).sort_values(
        "_sort_key", na_position="last"
    )
    combined = combined.drop_duplicates(subset=["Order_Number", "Session", "Source"], keep="first")
    return combined.drop(columns="_sort_key").reset_index(drop=True)
