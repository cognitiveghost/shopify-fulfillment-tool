"""A session's saved state (analysis/current_state.pkl) and its stale check.

Every edit rewrites the whole state from one PC's memory, so a PC that loaded
it before another PC saved would silently undo that PC's edits (AUDIT-05-3).
Each PC keeps the stamp it last loaded or saved; a save against a different
file on disk is refused. ADR 0011.
"""

import os
import tempfile
from pathlib import Path

from shared.file_lock import locked_file
from shopify_tool import stock_ledger

STATE_FILE = "current_state.pkl"


class StaleSessionError(Exception):
    """Another PC saved this session's state after this PC loaded it."""


def _state_path(session_path) -> Path:
    return Path(session_path) / "analysis" / STATE_FILE


def state_stamp(session_path):
    """(mtime_ns, size) of the saved state, or None when there is none yet.

    ponytail: two same-size saves inside one file-time tick share a stamp;
    upgrade to a version token written with the state if that ever shows up.
    """
    try:
        st = _state_path(session_path).stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def is_stale(session_path, loaded_stamp) -> bool:
    return state_stamp(session_path) != loaded_stamp


def save_state(session_path, df, loaded_stamp):
    """Write df as the session's state, atomically; return the new stamp.

    Raises StaleSessionError, writing nothing, when the state on disk is not
    the one this PC loaded or last saved. The lock spans only the check and
    the replace, so two PCs can't both pass the check and both write.
    """
    path = _state_path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(STATE_FILE + ".lock"), "a+") as lock, locked_file(lock):
        if is_stale(session_path, loaded_stamp):
            raise StaleSessionError(str(path))
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".current_state_tmp_", suffix=".pkl")
        os.close(fd)
        try:
            df.to_pickle(tmp)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return state_stamp(session_path)


def order_counts(df) -> dict:
    """The session_info.json order counts, by order (R1), for the browser."""
    total = df["Order_Number"].astype(str).str.strip().nunique()
    fulfillable = len(stock_ledger.fulfillable_orders(df))
    return {
        "total_orders": total,
        "fulfillable_orders": fulfillable,
        "not_fulfillable_orders": total - fulfillable,
    }
