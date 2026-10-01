"""browse_state: the one map the Browse page draws (phase 4 spec section 4).

Pure: no Qt and no file server.
"""

from datetime import datetime, timedelta

import pytest

from gui.browse_state import browse_state

NOW = datetime(2026, 9, 30, 14, 0).astimezone()
H = timedelta(hours=1)
D = timedelta(days=1)


def session(
    name="2026-09-30_1",
    *,
    status="active",
    age=6 * H,
    orders=197,
    items=402,
    blocked=None,
    lists=0,
    done=0,
    paused=False,
    idle=H,
    comment="",
    **extra,
):
    """One entry shaped like SessionManager.list_client_sessions() returns it.

    `lists` packing lists, of which `done` are completed. `paused` pauses the
    next one. `idle` is how long ago Packing Tool last wrote progress.
    """
    names = [f"list{i}" for i in range(lists)]
    stamp = (NOW - idle).isoformat()
    progress = {n: {"status": "completed", "updated_at": stamp} for n in names[:done]}
    if paused:
        progress[names[done]] = {"status": "paused", "updated_at": stamp}
    entry = {
        "session_name": name,
        "session_path": f"/srv/Sessions/CLIENT_ACME/{name}",
        "created_at": (NOW - age).isoformat(),
        "status": status,
        "statistics": {
            "total_orders": orders,
            "total_items": items,
            "packing_lists": names,
        },
        "packing_progress": progress,
        "comments": comment,
    }
    if blocked is not None:
        entry["not_fulfillable_orders"] = blocked
    entry.update(extra)
    return entry


def make_state(sessions=(), **overrides):
    args = {"client": "ACME", "loading": False, "failed": False, "sessions": list(sessions), "now": NOW}
    args.update(overrides)
    return browse_state(**args)


def row(**kwargs):
    return make_state([session(**kwargs)])["rows"][0]


# --- views -------------------------------------------------------------------


def test_no_client_wins_over_everything():
    state = make_state([session()], client="", loading=True, failed=True)
    assert state == {"view": "no_client", "client": "", "rows": []}


def test_a_failed_load_wins_over_a_load_in_flight():
    assert make_state([session()], failed=True, loading=True)["view"] == "failed"


def test_a_loud_load_shows_loading_and_no_rows():
    state = make_state([session()], loading=True)
    assert state == {"view": "loading", "client": "ACME", "rows": []}


def test_a_client_with_no_sessions_is_empty():
    assert make_state([]) == {"view": "empty", "client": "ACME", "rows": []}


def test_sessions_make_a_list_in_the_order_given():
    state = make_state([session("b"), session("c"), session("a")])
    assert state["view"] == "list"
    assert [r["name"] for r in state["rows"]] == ["b", "c", "a"]


def test_an_entry_that_is_not_a_session_is_skipped():
    junk = [None, "text", {"status": "active"}, {"session_name": ""}, {"session_name": 7}]
    assert [r["name"] for r in make_state([*junk, session("ok")])["rows"]] == ["ok"]
    assert make_state(junk)["view"] == "empty"


def test_no_session_list_at_all_is_empty():
    state = browse_state(client="ACME", loading=False, failed=False, sessions=None, now=NOW)
    assert state["view"] == "empty"


# --- the status --------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "status", "label", "tone", "dot", "tab"),
    [
        ({"lists": 2}, "not_started", "Not started", "neutral", "hollow", "active"),
        ({"lists": 3, "done": 1}, "in_progress", "In progress", "info", "half", "active"),
        ({"lists": 2, "paused": True}, "paused", "Paused", "warning", "half", "active"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, "stale", "Stale", "warning", "half", "active"),
        ({"status": "completed", "lists": 2, "done": 2}, "completed", "Completed", "success", "solid", "completed"),
        ({"status": "completed", "lists": 5, "done": 4}, "incomplete", "Incomplete", "danger", "solid", "completed"),
        ({"status": "abandoned"}, "abandoned", "Abandoned", "neutral", "solid", "abandoned"),
        ({"status": "archived"}, "archived", "Archived", "neutral", "solid", "archived"),
        ({"status": "frozen"}, "frozen", "Frozen", "neutral", "hollow", ""),
    ],
)
def test_each_status_has_its_label_tone_dot_and_tab(kwargs, status, label, tone, dot, tab):
    r = row(**kwargs)
    assert (r["status"], r["label"], r["tone"], r["dot"], r["tab"]) == (
        status,
        label,
        tone,
        dot,
        tab,
    )


@pytest.mark.parametrize("stored", [None, "", 7])
def test_a_missing_status_reads_active(stored):
    r = row(status=stored)
    assert r["tab"] == "active"
    assert r["status"] == "not_started"


# --- the numbers -------------------------------------------------------------


def test_counts_carry_a_comma_for_thousands():
    r = row(orders=1204, items=12402)
    assert (r["orders"], r["items"]) == ("1,204", "12,402")


@pytest.mark.parametrize("value", [0, None, "12", True, -3])
def test_a_count_that_is_zero_or_unreadable_is_empty(value):
    r = row(orders=value, items=value)
    assert (r["orders"], r["items"]) == ("", "")


def test_missing_statistics_leave_the_counts_empty():
    r = row(statistics="oops")
    assert (r["orders"], r["items"], r["pack"]) == ("", "", "")


def test_blocked_is_empty_at_zero_and_when_never_analysed():
    assert row(blocked=0)["blocked"] == ""
    assert row()["blocked"] == ""
    assert row()["blocked_alert"] is False


@pytest.mark.parametrize(
    ("kwargs", "alert", "why"),
    [
        ({"lists": 3, "done": 1}, True, "blocked"),
        ({"lists": 2}, True, "blocked"),
        ({"lists": 2, "paused": True}, True, "paused"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, True, "stale"),
        ({"status": "completed", "lists": 5, "done": 4}, False, "incomplete"),
        ({"status": "completed", "lists": 2, "done": 2}, False, ""),
        ({"status": "abandoned"}, False, ""),
        ({"status": "archived"}, False, ""),
    ],
)
def test_blocked_orders_alert_only_while_the_session_is_in_flight(kwargs, alert, why):
    r = row(blocked=9, **kwargs)
    assert r["blocked"] == "9"
    assert r["blocked_alert"] is alert
    assert r["why"] == why


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"lists": 3, "done": 1}, ""),
        ({"lists": 2}, ""),
        ({"lists": 2, "paused": True}, "paused"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, "stale"),
        ({"status": "completed", "lists": 5, "done": 4}, "incomplete"),
        ({"status": "completed", "lists": 2, "done": 2}, ""),
    ],
)
def test_why_names_the_reason_a_session_needs_attention(kwargs, why):
    assert row(**kwargs)["why"] == why


# --- packing -----------------------------------------------------------------


def test_a_session_with_no_packing_lists_has_no_packing():
    r = row()
    assert (r["pack"], r["pack_pct"], r["pack_tone"], r["pack_title"]) == ("", 0, "", "")


def test_packing_in_progress():
    r = row(lists=3, done=2)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("2 / 3", 67, "")
    assert r["pack_title"] == "2 of 3 packing lists completed in Packing Tool"


def test_packing_finished_is_success():
    r = row(status="completed", lists=3, done=3)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("3 / 3", 100, "success")


def test_packing_closed_unfinished_is_danger():
    r = row(status="completed", lists=5, done=4)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("4 / 5", 80, "danger")


def test_an_abandoned_session_shows_no_packing():
    r = row(status="abandoned", lists=3, done=1)
    assert (r["pack"], r["pack_pct"], r["pack_title"]) == ("", 0, "")


# --- age and comment ---------------------------------------------------------


def test_the_age_is_short_and_its_title_carries_the_stamp():
    r = row(age=6 * H)
    assert r["age"] == "6 h"
    assert r["age_title"].startswith("Created ")
    assert r["age_warn"] is False


def test_the_age_warns_before_the_auto_archive():
    r = row(status="completed", lists=1, done=1, age=26 * D)
    assert r["age"] == "26 d"
    assert r["age_warn"] is True
    assert r["age_title"].endswith(" · Archives in 4 d")


def test_the_comment_is_trimmed_and_a_non_string_is_empty():
    assert row(comment="  call courier \n")["comment"] == "call courier"
    assert row(comments=None)["comment"] == ""
    assert row(comments=5)["comment"] == ""


def test_no_shape_of_entry_raises():
    r = row(statistics=None, packing_progress="x", comments=5, created_at="nope",
            not_fulfillable_orders="many")
    assert r["age"] == "—"
    assert r["blocked"] == ""
