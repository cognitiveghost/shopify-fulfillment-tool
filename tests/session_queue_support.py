"""Helpers for tests of the session write queue (not a conftest: see tests/audit/audit_support.py)."""

import threading


def gated(queue) -> threading.Event:
    """Hold `queue`'s worker on a job until the returned event is set.

    The job sits on its own key, ("S0", "gate"), so the jobs a test submits
    after it queue up behind it. Set the event in a `finally`: a failing test
    must never leave a window's close waiting on it.
    """
    gate = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        gate.wait(10)

    queue.submit("S0", "gate", hold)
    started.wait(5)
    return gate
