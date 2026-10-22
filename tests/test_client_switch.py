"""A client switch does not wait on the GUI thread (spec B2, B3)."""

import logging
import threading

from test_stale_session import main_window  # noqa: F401  main_window is a fixture

from gui.session_write_queue import HISTORY


def test_the_switch_returns_before_a_slow_write_finishes(main_window, qtbot):  # noqa: F811
    win = main_window
    gate = threading.Event()
    win.write_queue.submit("S", HISTORY, lambda: gate.wait(5))
    calls = []
    real = win._reset_session_state
    win._reset_session_state = lambda wait=True: (calls.append(wait), real(wait=wait))[1]
    win.on_client_changed("acme")
    assert calls == [False]  # returned without waiting
    gate.set()
    qtbot.waitUntil(lambda: not win.command_bar._client_loading, timeout=5000)
    assert calls == [False]  # load_client_config did not reset a second time


def test_the_switch_logs_one_timing_line(main_window, qtbot, caplog):  # noqa: F811
    win = main_window
    caplog.set_level(logging.INFO)
    win.on_client_changed("acme")
    qtbot.waitUntil(lambda: "Client switch to CLIENT_" in caplog.text, timeout=5000)
    line = next(r.getMessage() for r in caplog.records if "Client switch to" in r.getMessage())
    for part in ("flush", "read", "apply", "sessions", "total"):
        assert f"{part} " in line and " ms" in line


def test_a_superseded_switch_keeps_the_bar_loading(main_window, qtbot):  # noqa: F811
    win = main_window
    win.profile_manager.create_client_profile("beta", "Client Beta")
    win.on_client_changed("acme")
    win.on_client_changed("beta")
    # A's result arrives first or is discarded; the bar must stay loading until B applies.
    win._on_client_data_loaded("acme", ({"x": 1}, {}, {"flush_ms": 0, "read_ms": 0}))
    assert win.command_bar._client_loading
    qtbot.waitUntil(lambda: not win.command_bar._client_loading, timeout=5000)
    assert win.current_client_id == "beta"
