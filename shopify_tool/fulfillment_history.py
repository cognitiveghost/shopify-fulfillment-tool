"""Per-client fulfillment history: which orders each session currently ships.

One row per order per session (ADR 0012). A session's rows are replaced
whenever its state is saved, so history follows what the session ships, not
what its run proposed (AUDIT-02-3, -4). Rows written before sessions were
recorded have Session "" and keep the old date rule in detection.

The file is never written over when it can't be read (AUDIT-02-6), and every
write re-reads under a lock sidecar and replaces atomically, so two PCs don't
lose each other's rows (AUDIT-02-7).
"""

import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from shared.file_lock import locked_file
from shopify_tool import stock_ledger
from shopify_tool.utils import get_persistent_data_path

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date", "Session"]
FILE_NAME = "fulfillment_history.csv"
LOCK_TIMEOUT = 2.0


class HistoryUnreadable(Exception):
    """The history file exists but can't be read; it must not be written over."""


def history_path(profile_manager, client_id) -> Path:
    if profile_manager and client_id:
        return Path(profile_manager.get_client_directory(client_id)) / FILE_NAME
    return Path(get_persistent_data_path(FILE_NAME))


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def load(path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return _empty()  # a 0-byte file holds nothing to lose
    except Exception as e:  # ParserError, UnicodeDecodeError, OSError on the share
        raise HistoryUnreadable(f"{path}: {e}") from e
    if not isinstance(df.index, pd.RangeIndex):
        # Every row has more fields than the header: pandas made the first
        # column the index, and the data would be written back shifted.
        raise HistoryUnreadable(f"{path}: rows have more fields than the header")
    if "Order_Number" not in df.columns:
        raise HistoryUnreadable(f"{path}: no Order_Number column")
    df = df.reindex(columns=COLUMNS, fill_value="").fillna("")
    df["Order_Number"] = df["Order_Number"].str.strip()
    return df


def merge_earliest(history_df, new_rows) -> pd.DataFrame:
    """Earliest date per order; NaT sorts last (moved from core, unchanged)."""
    combined = pd.concat([history_df, new_rows])
    key = pd.to_datetime(combined["Execution_Date"], errors="coerce", format="mixed")
    combined = combined.assign(_k=key).sort_values("_k", na_position="last")
    return combined.drop_duplicates(subset=["Order_Number"], keep="first").drop(columns="_k")


def _replace(history, session, ships, today) -> pd.DataFrame:
    if session is None:
        legacy = history["Session"] == ""
        new = pd.DataFrame({"Order_Number": sorted(ships), "Execution_Date": today, "Session": ""})
        return pd.concat([history[~legacy], merge_earliest(history[legacy], new)])
    mine = history["Session"] == session
    first_seen = dict(zip(history.loc[mine, "Order_Number"], history.loc[mine, "Execution_Date"]))
    new = pd.DataFrame(
        {
            "Order_Number": sorted(ships),
            "Execution_Date": [first_seen.get(o) or today for o in sorted(ships)],
            "Session": session,
        }
    )
    return pd.concat([history[~mine], new])


def _write_atomic(path: Path, df: pd.DataFrame) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fulfillment_history_tmp_", suffix=".csv")
    os.close(fd)
    try:
        df.to_csv(tmp, index=False, columns=COLUMNS)
        # Windows refuses to replace a file another PC has open; that's brief.
        for attempt in range(3):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.15)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def record_session(path, session, df, today=None) -> bool:
    """Replace `session`'s rows with the orders df ships. False = not written."""
    path = Path(path)
    today = today or datetime.now().astimezone().strftime("%Y-%m-%d")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a+") as lock, locked_file(lock, timeout=LOCK_TIMEOUT):
            try:
                history = load(path)
            except HistoryUnreadable:
                logger.warning(f"Fulfillment history unreadable; not writing over it: {path}", exc_info=True)
                return False
            ships = stock_ledger.fulfillable_orders(df)
            _write_atomic(path, _replace(history, session, ships, today))
            return True
    except Exception:  # FileLockError, OSError, anything pandas raises: never fail the caller
        logger.exception(f"Could not record fulfillment history for {session!r}")
        return False
