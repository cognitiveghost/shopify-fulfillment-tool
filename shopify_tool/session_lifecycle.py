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


def _count(value) -> int | None:
    """A non-negative int, or None for anything else.

    bool is an int in Python and would sail through isinstance; a True here
    means the file holds something we do not understand, so it reads as None.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def blocked_orders(entry: dict) -> int | None:
    """Orders this session cannot fulfil, or None when it was never analysed.

    None is not 0: a session with no analysis has no answer, and the Blocked
    column must stay blank rather than claim nothing is blocked.

    `core.py` has written `not_fulfillable_orders` into session_info.json on
    every session-mode analysis since the session architecture landed, and the
    index carries whole session_info dicts, so the stored key is the normal
    path. The subtraction is the fallback for a session written by something
    that recorded only the two halves.
    """
    if not isinstance(entry, dict):
        return None

    stored = _count(entry.get("not_fulfillable_orders"))
    if stored is not None:
        return stored

    total = _count(entry.get("total_orders"))
    fulfillable = _count(entry.get("fulfillable_orders"))
    if total is None or fulfillable is None or fulfillable > total:
        return None
    return total - fulfillable


# The eight states a row shows, in the order they progress. The four a person
# can set live in SessionManager.VALID_STATUSES; the other four are derived
# here from packing progress and idle time.
DISPLAY_STATUSES = (
    "not_started", "in_progress", "paused", "stale",
    "completed", "incomplete", "abandoned", "archived",
)

# An in-flight session nobody has touched for this long has stopped moving.
# Not age from creation -- the Age column already carries that, and drawing
# one fact twice is what this phase keeps deleting.
STALE_AFTER_DAYS = 7


def _has_paused_list(entry: dict) -> bool:
    progress = entry.get("packing_progress")
    if not isinstance(progress, dict):
        return False
    return any(
        isinstance(block, dict) and block.get("status") == "paused"
        for block in progress.values()
    )


def _idle_since(entry: dict):
    """When this session was last written, or None if unreadable.

    packing-tool writes packing_progress through its own path, so
    `last_updated` can be missing on a session it touched last. Falling back
    to created_at makes the answer conservative rather than absent.
    """
    return (
        parse_created_at(entry.get("last_updated"))
        or parse_created_at(entry.get("created_at"))
    )


def display_status(entry: dict, now: datetime) -> str:
    """One of DISPLAY_STATUSES for this entry. Pure, total, never raises.

    An unrecognised stored status is returned unchanged, so a value some
    future version writes renders as its own name rather than as a lie.
    """
    if not isinstance(entry, dict):
        return "active"

    stored = entry.get("status", "active")

    if stored in ("abandoned", "archived"):
        return stored

    packed, total = packing_completion(entry)

    if stored == "completed":
        # A person called it done. If lists are still unpacked, that is a
        # human judgment someone can still act on -- not an automation
        # artefact: derive_status_updates only ever promotes a fully packed
        # session.
        return "incomplete" if total > 0 and packed < total else "completed"

    if stored != "active":
        return stored

    if _has_paused_list(entry):
        return "paused"
    if packed == 0:
        return "not_started"

    idle_since = _idle_since(entry)
    if idle_since is not None and now - idle_since >= timedelta(days=STALE_AFTER_DAYS):
        return "stale"
    return "in_progress"


# How long before the auto-archive the row starts counting down. The 23-day
# threshold the countdown appears at is AUTO_ARCHIVE_AFTER_DAYS minus this;
# writing 23 anywhere would let the two drift apart.
ARCHIVE_WARNING_DAYS = 7

# The states still in flight. Blocked orders matter on these and nowhere
# else: a blocked count on a session someone already closed is history.
_IN_FLIGHT = ("not_started", "in_progress", "paused", "stale")


def age_label(created, now: datetime) -> tuple[str, str]:
    """(cell, tooltip) for the Age column.

    The cell is relative and one unit deep -- "3d", "2w", "6mo". The absolute
    stamp goes in the tooltip, which is the only place it was ever read.
    Inside the archive window the cell also carries the countdown.
    """
    if not isinstance(created, datetime):
        return ("—", "Created date unreadable")

    tooltip = f"Created {created:%Y-%m-%d %H:%M}"
    days = max(0, (now - created).days)

    if days == 0:
        cell = "today"
    elif days < 14:
        cell = f"{days}d"
    elif days < 60:
        cell = f"{days // 7}w"
    else:
        cell = f"{days // 30}mo"

    # A full warning-window early, drop the week/month bucket for a plain day
    # count, so the jump into the countdown itself isn't the first time the
    # display switches units.
    remaining = AUTO_ARCHIVE_AFTER_DAYS - days
    if 0 < remaining <= 2 * ARCHIVE_WARNING_DAYS:
        cell = f"{days}d"
        if remaining <= ARCHIVE_WARNING_DAYS:
            cell += f" · archives in {remaining}d"
    return (cell, tooltip)


def needs_attention(state: str, blocked: int | None) -> bool:
    """True when this row belongs in the Needs attention group.

    Either the state itself is a request for someone -- paused, stale, or
    finished-but-not-packed -- or the session is still in flight and carrying
    orders it cannot fulfil.
    """
    if state in ("paused", "stale", "incomplete"):
        return True
    return bool(blocked) and state in _IN_FLIGHT


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
