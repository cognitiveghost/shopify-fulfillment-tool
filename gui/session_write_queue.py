"""Background writes of a session's derived files, one at a time (AUDIT-07-H2).

An edit writes only `current_state.pkl` before the window responds. The
files derived from it -- fulfilment history, inventory memory,
`analysis_stats.json`, `session_info.json`'s counts and the undo file -- go
through this queue and are written on one background thread.

- A key is `(session_path, kind)`. Submitting to a key that is already
  pending replaces its job and keeps its place in line; every job writes a
  whole snapshot, so the last one submitted always wins. A job that is
  already running is never cancelled: the newer one runs after it.
- Keys run first in, first out, by the time each was first queued. Every
  job carries its own session path, so a session switched away from still
  gets its writes.
- One thread, so two writes never overlap.
- A job that raises or returns False is logged on the worker thread and
  reported through `failed`, which Qt delivers on the GUI thread. The worker
  never touches a widget.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

HISTORY = "history"
INVENTORY_MEMORY = "inventory_memory"
ANALYSIS_STATS = "analysis_stats"
SESSION_INFO = "session_info"
UNDO_HISTORY = "undo_history"


def _run_job(key: tuple[str, str], job: Callable[[], object]) -> bool:
    """Run one job; True unless it raised or returned False."""
    try:
        return job() is not False
    except Exception:
        logger.exception(f"Background write {key[1]} failed for {key[0]}")
        return False


class SessionWriteQueue(QObject):
    """Per-session, coalescing, first-in-first-out background writes."""

    # (session_path, kind) of a write that failed. Emitted on the worker
    # thread; a slot on a GUI object runs on the GUI thread.
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cond = threading.Condition()
        self._pending: OrderedDict[tuple[str, str], Callable[[], object]] = OrderedDict()
        self._running: tuple[str, str] | None = None
        self._thread: threading.Thread | None = None

    def submit(self, session_path: str, kind: str, job: Callable[[], object]) -> None:
        """Queue `job` for (session_path, kind), replacing a pending one in place."""
        with self._cond:
            self._pending[(str(session_path), kind)] = job
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="session-writes", daemon=True)
                self._thread.start()
            self._cond.notify_all()

    def pending(self, session_path: str | None = None) -> list[tuple[str, str]]:
        """The keys still to be written (the running one first), of one session or all."""
        with self._cond:
            keys = ([self._running] if self._running else []) + list(self._pending)
        return [k for k in keys if session_path is None or k[0] == str(session_path)]

    def flush(self, session_path: str | None = None, timeout: float | None = None) -> bool:
        """Wait until no write of that session (or of any) is pending or running.

        Returns False if `timeout` seconds pass first; the writes still land.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while self._busy(session_path):
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    return False
                self._cond.wait(left)
        return True

    def _busy(self, session_path: str | None) -> bool:
        keys = list(self._pending) + ([self._running] if self._running else [])
        return any(session_path is None or k[0] == str(session_path) for k in keys)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._pending:
                    self._cond.wait()
                key, job = self._pending.popitem(last=False)
                self._running = key
            ok = _run_job(key, job)
            with self._cond:
                self._running = None
                self._cond.notify_all()
            if not ok:
                self.failed.emit(*key)


def submit_or_run(
    queue: SessionWriteQueue | None, session_path: str, kind: str, job: Callable[[], object]
) -> None:
    """Queue `job`, or run it now (logging a failure) when there is no queue.

    No queue means a caller without a window, such as a test's plain
    namespace standing in for one.
    """
    if queue is None:
        _run_job((str(session_path), kind), job)
    else:
        queue.submit(session_path, kind, job)
