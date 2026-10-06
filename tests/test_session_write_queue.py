"""The per-session coalescing write queue (AUDIT-07-H2, design note §2)."""

import threading

from session_queue_support import gated

from gui.session_write_queue import (
    ANALYSIS_STATS,
    HISTORY,
    SESSION_INFO,
    SessionWriteQueue,
    submit_or_run,
)


def test_a_newer_write_replaces_a_pending_one(qapp):
    q, ran = SessionWriteQueue(), []
    gate = gated(q)
    try:
        q.submit("S1", HISTORY, lambda: ran.append("old"))
        q.submit("S1", HISTORY, lambda: ran.append("new"))
    finally:
        gate.set()
    assert q.flush(timeout=5) and ran == ["new"]


def test_a_replaced_write_keeps_its_place_in_line(qapp):
    q, ran = SessionWriteQueue(), []
    gate = gated(q)
    try:
        q.submit("S1", HISTORY, lambda: ran.append("s1-old"))
        q.submit("S2", HISTORY, lambda: ran.append("s2"))
        q.submit("S1", HISTORY, lambda: ran.append("s1-new"))
        q.submit("S1", ANALYSIS_STATS, lambda: ran.append("s1-stats"))
    finally:
        gate.set()
    q.flush(timeout=5)
    assert ran == ["s1-new", "s2", "s1-stats"]


def test_a_write_submitted_while_its_key_runs_runs_after_it(qapp):
    q, ran = SessionWriteQueue(), []
    release, running = threading.Event(), threading.Event()

    def first():
        running.set()
        release.wait(5)
        ran.append("A")

    try:
        q.submit("S1", HISTORY, first)
        assert running.wait(5)
        q.submit("S1", HISTORY, lambda: ran.append("B"))
    finally:
        release.set()
    assert q.flush(timeout=5)
    assert ran == ["A", "B"]


def test_flush_times_out_and_says_so(qapp):
    q = SessionWriteQueue()
    gate = gated(q)
    try:
        assert q.flush(timeout=0.1) is False
        assert q.pending() == [("S0", "gate")]
    finally:
        gate.set()
    assert q.flush(timeout=5) is True and q.pending() == []


def test_flush_waits_only_for_the_session_asked_about(qapp):
    q = SessionWriteQueue()
    gate = gated(q)
    try:
        assert q.flush("S1", timeout=0.1) is True
        assert q.flush("S0", timeout=0.1) is False
    finally:
        gate.set()


def test_a_failed_write_is_signalled_on_the_gui_thread(qapp, qtbot):
    q, threads = SessionWriteQueue(), []
    q.failed.connect(lambda path, kind: threads.append((path, kind, threading.current_thread())))
    q.submit("S1", HISTORY, lambda: False)
    q.submit("S1", SESSION_INFO, lambda: 1 / 0)
    qtbot.waitUntil(lambda: len(threads) == 2, timeout=5000)
    assert threads == [("S1", HISTORY, threading.main_thread()), ("S1", SESSION_INFO, threading.main_thread())]


def test_without_a_queue_the_job_runs_now():
    ran = []
    submit_or_run(None, "S1", HISTORY, lambda: ran.append(1))
    assert ran == [1]


def test_without_a_queue_a_failing_job_is_only_logged(caplog):
    submit_or_run(None, "S1", HISTORY, lambda: 1 / 0)
    assert any("history" in r.getMessage() for r in caplog.records)
