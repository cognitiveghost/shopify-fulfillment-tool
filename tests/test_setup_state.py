"""Everything the Setup page draws, built from plain facts (phase 3 spec section 4)."""

from datetime import datetime

import pytest

from gui.setup_state import (
    FileSlot,
    MemoryFacts,
    RunFacts,
    SessionFacts,
    setup_state,
)

NOW = datetime(2026, 9, 30, 15, 0).astimezone()
OPENED = datetime(2026, 9, 30, 14, 2).astimezone()
NO_MEMORY = MemoryFacts(on=False, skus=0, session="", updated=None)
MEMORY = MemoryFacts(
    on=True,
    skus=191,
    session="2026-09-29_2",
    updated=datetime(2026, 9, 29, 16, 40).astimezone(),
)


def loaded(kind, **over):
    """A valid slot: the mockup's orders or stock file."""
    slot = FileSlot(kind)
    facts = (
        {"path": "/d/acme-orders-30-09.csv", "rows": 1204, "keys": 312, "delimiter": ","}
        if kind == "orders"
        else {"path": "/d/acme-stock-30-09.csv", "rows": 188, "keys": 188, "delimiter": ";"}
    )
    facts.update(over)
    slot.set_loaded(facts.pop("path"), **facts)
    return slot


def make_state(**over):
    """setup_state with the mockup's Ready state as the default."""
    facts = {
        "connected": True,
        "client": "ACME",
        "server_path": r"\\fs01\fulfilment",
        "session": SessionFacts("2026-09-30_1", OPENED, None),
        "orders": loaded("orders"),
        "stock": loaded("stock"),
        "memory": NO_MEMORY,
        "strategy": "multi_first",
        "run": RunFacts(),
        "now": NOW,
    }
    facts.update(over)
    return setup_state(**facts)


# --- views -------------------------------------------------------------------


def test_no_connection_and_no_session_is_the_unreachable_panel():
    state = make_state(connected=False, client="", session=None)
    assert state["view"] == "unreachable"
    assert state["server_path"] == r"\\fs01\fulfilment"


def test_no_client_asks_for_one():
    assert make_state(client="", session=None)["view"] == "no_client"


def test_a_client_with_no_session_gets_the_no_session_panel():
    state = make_state(session=None)
    assert state["view"] == "no_session"
    assert state["client"] == "ACME"
    assert state["session"] == {}


def test_a_session_that_loses_the_server_keeps_its_cards():
    state = make_state(connected=False)
    assert state["view"] == "setup"
    assert state["run"]["enabled"] is False
    assert state["summary"]["reason"] == (
        "Server unreachable. Files stay loaded; Retry is in the sidebar."
    )
    assert state["summary"]["reason_tone"] == "danger"


# --- session -----------------------------------------------------------------


def test_a_new_session_says_when_it_was_opened():
    assert make_state()["session"] == {
        "name": "2026-09-30_1",
        "title": "New session",
        "meta": "ACME · opened 14:02",
    }


def test_an_analysed_session_says_when_it_was_analysed():
    analysed = datetime(2026, 9, 30, 14, 6).astimezone()
    session = SessionFacts("2026-09-30_1", OPENED, analysed)
    state = make_state(session=session)
    assert state["session"]["title"] == "Session"
    assert state["session"]["meta"] == "ACME · analysed 14:06"
    assert state["summary"]["reason"] == "Running again replaces this session's results."


def test_another_days_session_shows_its_date():
    opened = datetime(2026, 9, 29, 16, 40).astimezone()
    state = make_state(session=SessionFacts("2026-09-29_2", opened, None))
    assert state["session"]["meta"] == "ACME · opened 29 Sep 16:40"


def test_a_session_with_no_timestamp_shows_the_client_only():
    state = make_state(session=SessionFacts("SESSION_OLD", None, None))
    assert state["session"]["meta"] == "ACME"


# --- cards -------------------------------------------------------------------


def test_a_loaded_file_card():
    card = make_state()["files"]["orders"]
    assert card["state"] == "loaded"
    assert (card["badge"], card["badge_tone"]) == ("Loaded", "success")
    assert card["name"] == "acme-orders-30-09.csv"
    assert card["is_folder"] is False
    assert card["stats"] == [
        {"k": "Rows", "v": "1,204", "muted": False},
        {"k": "Orders", "v": "312", "muted": False},
        {"k": "Delimiter", "v": "Comma  ,", "muted": False},
    ]
    assert card["problem"] == {}


def test_the_stock_card_counts_skus_and_names_its_delimiter():
    stats = make_state()["files"]["stock"]["stats"]
    assert stats[1] == {"k": "SKUs", "v": "188", "muted": False}
    assert stats[2]["v"] == "Semicolon  ;"


@pytest.mark.parametrize(
    ("delimiter", "shown"),
    [("\t", "Tab"), ("|", "Pipe  |"), ("mixed", "Mixed"), ("^", "^")],
)
def test_other_delimiters(delimiter, shown):
    state = make_state(orders=loaded("orders", delimiter=delimiter))
    assert state["files"]["orders"]["stats"][2]["v"] == shown


def test_a_missing_file_card():
    card = make_state(orders=FileSlot("orders"))["files"]["orders"]
    assert card["state"] == "missing"
    assert (card["badge"], card["badge_tone"]) == ("Missing", "neutral")
    assert card["stats"] == []


def test_a_folder_merge_lists_its_parts():
    parts = [{"name": "a.csv", "rows": 1512}, {"name": "b.csv", "rows": 480}]
    orders = loaded(
        "orders",
        parts=parts,
        note="2 overlapping orders skipped",
        name="exports\\  ·  2 CSVs merged",
    )
    card = make_state(orders=orders)["files"]["orders"]
    assert card["is_folder"] is True
    assert card["name"] == "exports\\  ·  2 CSVs merged"
    assert card["parts"] == [
        {"name": "a.csv", "rows": "1,512"},
        {"name": "b.csv", "rows": "480"},
    ]
    assert card["note"] == "2 overlapping orders skipped"


def test_a_problem_card_keeps_what_is_known_and_mutes_the_rest():
    orders = FileSlot("orders")
    orders.set_invalid(
        "/d/acme-orders-30-09.csv",
        ["Lineitem sku"],
        ["Name"],
        {"Lineitem sku": "SKU"},
        rows=1204,
        delimiter=",",
    )
    card = make_state(orders=orders)["files"]["orders"]
    assert card["state"] == "problem"
    assert (card["badge"], card["badge_tone"]) == ("Problem", "danger")
    assert card["stats"] == [
        {"k": "Rows", "v": "1,204", "muted": False},
        {"k": "Orders", "v": "—", "muted": True},
        {"k": "Delimiter", "v": "Comma  ,", "muted": False},
    ]
    assert card["problem"] == {
        "title": "No SKU column",
        "text": "The orders file's header row has no “Lineitem sku” column, "
        "which is mapped to SKU.",
        "fix_label": "Open Orders mapping",
    }


def test_a_file_that_could_not_be_read_mutes_every_stat():
    stock = FileSlot("stock")
    stock.set_problem("/d/stock.csv", "The stock file couldn't be read", "…", "General")
    card = make_state(stock=stock)["files"]["stock"]
    assert [s["v"] for s in card["stats"]] == ["—", "—", "—"]
    assert all(s["muted"] for s in card["stats"])


def test_a_header_only_file_is_loaded_with_zeroes():
    state = make_state(orders=loaded("orders", rows=0, keys=0))
    assert state["files"]["orders"]["stats"][0]["v"] == "0"
    assert state["summary"]["headline"].startswith("0 orders, 0 lines")
    assert state["run"]["enabled"] is True


# --- the run rule ------------------------------------------------------------


def test_ready():
    state = make_state()
    assert state["run"]["enabled"] is True
    assert state["summary"]["ready"] is True
    assert state["summary"]["headline"] == (
        "312 orders, 1,204 lines, stock for 188 SKUs, multi-item first"
    )
    assert state["summary"]["rows"] == [
        {"k": "Orders", "v": "312 orders · 1,204 lines", "muted": False},
        {"k": "Stock", "v": "Stock file · 188 SKUs", "muted": False},
        {"k": "Strategy", "v": "Multi-item first", "muted": False},
    ]
    assert state["summary"]["reason"] == "Results open when it finishes."
    assert state["summary"]["reason_tone"] == ""


def test_the_other_strategy():
    state = make_state(strategy="fifo")
    assert state["strategy"] == "fifo"
    assert state["summary"]["headline"].endswith("oldest first")
    assert state["summary"]["rows"][2]["v"] == "Oldest first"


def test_an_unknown_strategy_reads_as_the_default():
    assert make_state(strategy="nonsense")["strategy"] == "multi_first"


def test_no_files():
    state = make_state(orders=FileSlot("orders"), stock=FileSlot("stock"))
    assert state["run"]["enabled"] is False
    assert state["summary"]["ready"] is False
    assert state["summary"]["headline"] == "Load both files to see what this run will do"
    assert state["summary"]["rows"][0] == {"k": "Orders", "v": "Not loaded", "muted": True}
    assert state["summary"]["rows"][1] == {"k": "Stock", "v": "Not loaded", "muted": True}
    assert state["summary"]["reason"] == "Load the orders and stock files to run."


def test_orders_only():
    state = make_state(stock=FileSlot("stock"))
    assert state["run"]["enabled"] is False
    assert state["summary"]["headline"] == (
        "312 orders, 1,204 lines, waiting for the stock file"
    )
    assert state["summary"]["reason"] == "Load the stock file to run."


def test_stock_only():
    state = make_state(orders=FileSlot("orders"))
    assert state["summary"]["headline"] == "Stock for 188 SKUs, waiting for the orders file"
    assert state["summary"]["reason"] == "Load the orders file to run."


def test_an_orders_problem():
    orders = FileSlot("orders")
    orders.set_invalid("/d/o.csv", ["Lineitem sku"], ["Name"], {"Lineitem sku": "SKU"})
    state = make_state(orders=orders)
    assert state["run"]["enabled"] is False
    assert state["summary"]["headline"] == (
        "The orders file needs fixing before this can run"
    )
    assert state["summary"]["rows"][0] == {
        "k": "Orders",
        "v": "Problem: no SKU column",
        "muted": True,
    }
    assert state["summary"]["reason"] == "Fix the orders file to run."


def test_a_stock_problem():
    stock = FileSlot("stock")
    stock.set_problem("/d/s.csv", "The stock file couldn't be read", "…", "General")
    state = make_state(stock=stock)
    assert state["run"]["enabled"] is False
    assert state["summary"]["headline"] == "The stock file needs fixing before this can run"
    assert state["summary"]["rows"][1]["v"] == "Problem: the stock file couldn't be read"
    assert state["summary"]["reason"] == "Fix the stock file to run."


def test_running_disables_run_and_locks_the_inputs():
    state = make_state(run=RunFacts(running=True, step=2))
    assert state["run"] == {
        "enabled": False,
        "running": True,
        "locked": True,
        "step": 2,
        "steps": 4,
        "step_name": "Allocating stock",
        "can_cancel": True,
        "cancelling": False,
    }
    assert state["summary"]["reason"] == ""


def test_the_saving_step_cannot_be_cancelled():
    run = make_state(run=RunFacts(running=True, step=3))["run"]
    assert run["step_name"] == "Saving results"
    assert run["can_cancel"] is False


def test_a_cancel_already_asked_for_cannot_be_asked_again():
    run = make_state(run=RunFacts(running=True, step=1, cancelling=True))["run"]
    assert run["can_cancel"] is False
    assert run["cancelling"] is True


def test_an_idle_run_reports_no_step_name_and_no_stale_cancel():
    run = make_state(run=RunFacts(running=False, step=3, cancelling=True))["run"]
    assert run["step_name"] == ""
    assert run["cancelling"] is False
    assert run["can_cancel"] is False


# --- memory ------------------------------------------------------------------


def test_memory_off():
    memory = make_state()["memory"]
    assert memory["on"] is False
    assert memory["text"] == (
        "When on, a run with no stock file starts from the stock ACME's previous run "
        "left. A loaded stock file is always used as it is."
    )
    assert memory["previous"] == ""


def test_memory_on_names_the_previous_run():
    memory = make_state(memory=MEMORY)["memory"]
    assert memory["on"] is True
    assert memory["previous"] == "Previous run 2026-09-29_2 · 29 Sep 16:40 · 191 SKUs"


def test_memory_on_with_nothing_remembered():
    empty = MemoryFacts(on=True, skus=0, session="", updated=None)
    assert make_state(memory=empty)["memory"]["previous"] == (
        "Nothing is remembered yet. The first run needs a stock file."
    )


def test_memory_with_a_loaded_stock_file_changes_nothing_about_the_run():
    state = make_state(memory=MEMORY)
    assert state["summary"]["rows"][1]["v"] == "Stock file · 188 SKUs"
    assert state["files"]["stock"]["badge"] == "Loaded"


def test_memory_covers_a_missing_stock_file():
    state = make_state(memory=MEMORY, stock=FileSlot("stock"))
    assert state["run"]["enabled"] is True
    assert state["summary"]["ready"] is True
    assert state["files"]["stock"]["state"] == "missing"
    assert state["files"]["stock"]["badge"] == "From memory"
    assert state["summary"]["headline"] == (
        "312 orders, 1,204 lines, last run's stock for 191 SKUs, multi-item first"
    )
    assert state["summary"]["rows"][1] == {
        "k": "Stock",
        "v": "From 2026-09-29_2 · 191 SKUs",
        "muted": False,
    }


def test_memory_covering_with_no_orders_yet():
    state = make_state(
        memory=MEMORY, stock=FileSlot("stock"), orders=FileSlot("orders")
    )
    assert state["summary"]["headline"] == (
        "Last run's stock for 191 SKUs, waiting for the orders file"
    )
    assert state["summary"]["reason"] == "Load the orders file to run."


def test_memory_with_no_session_name_says_from_memory():
    nameless = MemoryFacts(on=True, skus=12, session="", updated=None)
    state = make_state(memory=nameless, stock=FileSlot("stock"))
    assert state["summary"]["rows"][1]["v"] == "From memory · 12 SKUs"


def test_memory_does_not_cover_a_stock_file_with_a_problem():
    stock = FileSlot("stock")
    stock.set_problem("/d/s.csv", "The stock file couldn't be read", "…", "General")
    state = make_state(memory=MEMORY, stock=stock)
    assert state["run"]["enabled"] is False
    assert state["files"]["stock"]["badge"] == "Problem"


def test_empty_memory_does_not_cover_a_missing_stock_file():
    empty = MemoryFacts(on=True, skus=0, session="", updated=None)
    state = make_state(memory=empty, stock=FileSlot("stock"))
    assert state["run"]["enabled"] is False
    assert state["files"]["stock"]["badge"] == "Missing"
