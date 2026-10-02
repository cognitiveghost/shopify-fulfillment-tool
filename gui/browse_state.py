"""What the Browse page draws (phase 4 spec section 4).

One pure function: the loaded sessions in, one map out. No Qt and no I/O.
Every fact about a session is worded here; the page filters, counts and
groups the rows it is given and decides none of them.
"""

from datetime import datetime

from shopify_tool.session_lifecycle import (
    DISPLAY_STATUSES,
    IN_FLIGHT,
    age_cell,
    blocked_orders,
    display_status,
    needs_attention,
    packing_completion,
)
from shopify_tool.session_manager import SessionManager

# A status with no entry here is neutral: not started, abandoned, archived,
# and any status this build has never heard of.
_TONES = {
    "in_progress": "info",
    "paused": "warning",
    "stale": "warning",
    "completed": "success",
    "incomplete": "danger",
}
_HALF_DOT = ("in_progress", "paused", "stale")
# The states that are themselves a request for someone.
_ATTENTION_STATES = ("paused", "stale", "incomplete")


def _number(value) -> str:
    """A positive count with a comma for thousands, or "" for anything else."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return ""
    return f"{value:,}"


def _dot(status: str) -> str:
    """How far the session has come: hollow, half or solid."""
    if status in _HALF_DOT:
        return "half"
    if status == "not_started" or status not in DISPLAY_STATUSES:
        return "hollow"
    return "solid"


def _tab(entry: dict) -> str:
    """The stored status, which is what a tab filters on."""
    stored = entry.get("status")
    if not isinstance(stored, str) or not stored:
        stored = "active"  # as display_status reads a missing status
    return stored if stored in SessionManager.VALID_STATUSES else ""


def _row(entry: dict, now: datetime) -> dict:
    status = display_status(entry, now)
    blocked = blocked_orders(entry) or 0
    packed, total = packing_completion(entry)
    has_pack = total > 0 and status != "abandoned"
    stats = entry.get("statistics")
    if not isinstance(stats, dict):
        stats = {}
    comment = entry.get("comments")
    age, age_title, age_warn = age_cell(entry, now)

    if status in _ATTENTION_STATES:
        why = status
    elif needs_attention(status, blocked):
        why = "blocked"
    else:
        why = ""

    if not has_pack:
        pack_tone = ""
    elif packed >= total:
        pack_tone = "success"
    elif status == "incomplete":
        pack_tone = "danger"
    else:
        pack_tone = ""

    return {
        "name": entry["session_name"],
        "age": age,
        "age_title": age_title,
        "age_warn": age_warn,
        "status": status,
        "label": status.replace("_", " ").capitalize(),
        "tone": _TONES.get(status, "neutral"),
        "dot": _dot(status),
        "tab": _tab(entry),
        "orders": _number(stats.get("total_orders")),
        "items": _number(stats.get("total_items")),
        "blocked": _number(blocked),
        "blocked_alert": blocked > 0 and status in IN_FLIGHT,
        "pack": f"{packed} / {total}" if has_pack else "",
        "pack_pct": round(packed / total * 100) if has_pack else 0,
        "pack_tone": pack_tone,
        "pack_title": (
            f"{packed} of {total} packing lists completed in Packing Tool"
            if has_pack
            else ""
        ),
        "comment": comment.strip() if isinstance(comment, str) else "",
        "why": why,
    }


def browse_state(
    *, client: str, loading: bool, failed: bool, sessions: list, now: datetime
) -> dict:
    """The map the Browse page draws. `sessions` stays in the order given."""
    rows = []
    if not client:
        view = "no_client"
    elif failed:
        view = "failed"
    elif loading:
        view = "loading"
    else:
        rows = [
            _row(entry, now)
            for entry in sessions or []
            if isinstance(entry, dict)
            and isinstance(entry.get("session_name"), str)
            and entry["session_name"]
        ]
        view = "list" if rows else "empty"
    return {"view": view, "client": client or "", "rows": rows}
