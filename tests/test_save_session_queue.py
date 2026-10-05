"""An edit writes only the pickle on the click; the rest goes through the queue (AUDIT-07-H2)."""

import json
import threading
import time
from pathlib import Path

from session_queue_support import gated
from test_stale_session import (  # noqa: F401  main_window is a fixture
    _open_with_state,
    _orders,
    main_window,
)

import gui.main_window_pyside as main_window_module
from gui.session_write_queue import HISTORY
from shopify_tool import fulfillment_history, session_state


def test_an_edit_writes_only_the_pickle_before_returning(main_window, monkeypatch):  # noqa: F811
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    calls = []
    monkeypatch.setattr(fulfillment_history, "record_session", lambda *a, **k: calls.append("history") or True)
    monkeypatch.setattr(main_window.session_manager, "update_session_info",
                        lambda *a, **k: calls.append("info") or True)
    before = session_state.state_stamp(path)
    gate = gated(main_window.write_queue)
    try:
        main_window.actions_handler.bulk_change_status(["#1002"], False)
        assert session_state.state_stamp(path) != before  # the pickle is written
        assert calls == []  # nothing else yet
    finally:
        gate.set()
    assert main_window.write_queue.flush(timeout=10)
    assert sorted(calls) == ["history", "info"]
    assert not (Path(path) / "analysis" / "current_state.xlsx").exists()


def test_a_failed_history_write_toasts_on_the_gui_thread(main_window, qtbot, monkeypatch):  # noqa: F811
    _open_with_state(main_window, _orders("Fulfillable"))
    seen = []
    monkeypatch.setattr(fulfillment_history, "record_session", lambda *a, **k: False)
    monkeypatch.setattr(main_window_module, "toast",
                        lambda src, text, **k: seen.append((text, threading.current_thread())))
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    qtbot.waitUntil(lambda: bool(seen), timeout=5000)
    assert seen == [("Fulfilment history wasn't saved. It's saved again with your next change.",
                     threading.main_thread())]


def test_a_failed_memory_write_toasts_and_a_failed_count_only_logs(main_window, qtbot, monkeypatch):  # noqa: F811
    seen = []
    monkeypatch.setattr(main_window_module, "toast", lambda src, text, **k: seen.append(text))
    main_window._on_session_write_failed("S", "session_info")
    main_window._on_session_write_failed("S", "inventory_memory")
    assert seen == ["Inventory memory wasn't updated. It's updated again with your next change."]


def test_switching_sessions_waits_for_pending_writes(main_window):  # noqa: F811
    _open_with_state(main_window, _orders("Fulfillable"))
    done = []
    main_window.write_queue.submit("S", HISTORY, lambda: time.sleep(0.3) or done.append(1))
    main_window._reset_session_state()
    assert done == [1]


def test_closing_waits_for_pending_writes(main_window):  # noqa: F811
    done = []
    main_window.write_queue.submit("S", HISTORY, lambda: time.sleep(0.3) or done.append(1))
    main_window.close()
    assert done == [1]


def _confirm(answers, asked):
    """Stands in for ConfirmDialog: answers from `answers`, records each ask."""

    class Confirm:
        def __init__(self, parent, *, title, body, verb):
            self.cancel_button = type("Button", (), {"setText": lambda self, text: None})()
            asked.append((title, verb))

        def exec(self):
            return answers.pop(0)

    return Confirm


def test_close_asks_when_writes_outlast_the_wait(main_window, monkeypatch):  # noqa: F811
    asked = []
    monkeypatch.setattr(main_window.write_queue, "flush", lambda *a, **k: False)
    # Keep waiting, then Close anyway
    monkeypatch.setattr(main_window_module, "ConfirmDialog", _confirm([False, True], asked))
    assert main_window.close() is True
    assert asked == [("Still saving this session", "Close anyway")] * 2


def test_a_session_with_an_unreadable_pickle_opens_from_the_run_report(main_window):  # noqa: F811
    path = Path(main_window.session_manager.create_session("acme"))
    analysis = path / "analysis"
    report = _orders("Fulfillable", "Fulfillable").assign(System_note="")
    report.to_excel(analysis / "fulfillment_analysis.xlsx", index=False)
    (analysis / "analysis_data.json").write_text(json.dumps({"orders": []}), encoding="utf-8")
    (analysis / "current_state.pkl").write_bytes(b"not a pickle")
    stale = _orders("Not Fulfillable").assign(System_note="")  # from an older build
    stale.to_excel(analysis / "current_state.xlsx", index=False)
    main_window.load_existing_session(str(path))
    assert main_window.analysis_results_df["Order_Number"].tolist() == ["#1001", "#1002"]
    assert main_window.analysis_stats is not None  # loaded whole, not half-way
