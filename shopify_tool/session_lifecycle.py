"""Derive session status from packing progress and age.

Pure functions over the entry dicts `SessionManager.list_client_sessions()`
returns. No I/O and no Qt, so the rules can be tested without a file server
or a QApplication.

Every value read here comes from a file another tool writes, so no shape it
can take may raise -- a session list that will not load is far worse than one
carrying a stale status.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Packing Tool's whole-session mode records progress under this literal key
# instead of a packing list's file stem (packing-tool src/main.py:2249). It
# can never match a stem, so a plain "are all lists completed?" check scores
# such a session 0/N forever even though every order in it was packed.
FULL_SESSION_KEY = "full_session"

AUTO_ARCHIVE_AFTER_DAYS = 30

# Statuses the automation is allowed to move a session out of. "abandoned" is
# an explicit human judgment and "archived" is already terminal.
_ARCHIVABLE_FROM = ("active", "completed")


def packing_completion(entry: dict) -> tuple[int, int]:
    """(packed, total) packing lists for one session entry.

    total == 0 means the session has nothing to pack, which is never
    "complete" -- vacuous truth would mark every empty session done.
    """
    stats = entry.get("statistics")
    lists = stats.get("packing_lists") if isinstance(stats, dict) else None
    if not isinstance(lists, list):
        lists = []
    names = [n for n in lists if isinstance(n, str)]

    progress = entry.get("packing_progress")
    if not isinstance(progress, dict):
        progress = {}

    def _done(key: str) -> bool:
        block = progress.get(key)
        # Only "completed" counts; "in_progress" and "paused" do not.
        return isinstance(block, dict) and block.get("status") == "completed"

    total = len(names)
    if _done(FULL_SESSION_KEY):
        # The whole session was packed in one go. Report it as covering every
        # list, and as 1/1 when the lists were never written to disk.
        return (total, total) if total else (1, 1)

    # Denominator is the lists actually on disk, so a progress key with no
    # matching file is ignored rather than able to block completion.
    return sum(1 for name in names if _done(name)), total


def is_fully_packed(entry: dict) -> bool:
    """True only when the session has packing lists and every one is done."""
    packed, total = packing_completion(entry)
    return total > 0 and packed == total


def parse_created_at(value) -> datetime | None:
    """ISO timestamp -> aware datetime, or None if unreadable.

    `.astimezone()` with no argument does both cases in one call: on a naive
    datetime Python attaches the local offset (DST-correctly), and on an
    already-aware one it preserves the instant.

    Reading naive stamps as local rather than skipping them is load-bearing.
    created_at only became offset-aware on 2026-07-27 (PR #253), so every
    session old enough to archive predates the fix -- skipping them would
    archive nothing at all, forever.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone()
    except (ValueError, TypeError, OSError):
        return None


def derive_status_updates(entries, now: datetime) -> dict:
    """{session_name: new_status} for sessions whose status should change.

    Returns only actual changes, so a steady state writes nothing and the
    pass is self-limiting: the first refresh clears the backlog, every later
    one derives an empty set.

    `entries` must come from a single client. Session names are unique only
    within a client, so pooling clients silently collapses same-named
    sessions into one key -- and apply_status_updates is per-client anyway.
    """
    cutoff = now - timedelta(days=AUTO_ARCHIVE_AFTER_DAYS)
    updates = {}

    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("session_name")
        if not isinstance(name, str) or not name:
            continue
        # Once a human sets a status by hand, this stops managing that session
        # -- otherwise un-archiving an old session just re-archives it.
        if entry.get("status_manually_set"):
            continue

        status = entry.get("status")

        # Archive beats complete: "archived" means get this out of my default
        # view, and the Packing column still shows it was fully packed.
        if status in _ARCHIVABLE_FROM:
            created = parse_created_at(entry.get("created_at"))
            # Never act on a date that could not be read.
            if created is not None and created < cutoff:
                updates[name] = "archived"
                continue

        if status == "active" and is_fully_packed(entry):
            updates[name] = "completed"

    return updates
