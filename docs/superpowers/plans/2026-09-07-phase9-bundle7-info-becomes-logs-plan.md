# Phase 9 Bundle 7 — Info becomes Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete Info › Statistics, rename the destination `Info` → `Logs`, and replace `activity_log_table` + `execution_log_edit` with one `QTreeView` over a ring-buffer model carrying two sources.

**Architecture:** Build the new viewer bottom-up from pure, Qt-free pieces (`LogEntry`, `FollowState`) through the model layer (`LogBufferModel`, `LogFilterProxy`) to the widget (`LogViewer`), then swap it into Tab 4 and delete the old pages last. Every task before the swap is additive, so the app keeps running throughout and the deletion lands once with nothing left pointing at it.

**Tech Stack:** Python 3.12, PySide6 (`QAbstractTableModel`, `QSortFilterProxyModel`, `QTreeView`), pytest, `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md`

## Global Constraints

- **Windows-only production, Linux dev.** Never call `python` bare — use `.venv/bin/python` or `scripts/run_tests.sh`. `python` is not on PATH here.
- **Run tests as:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
- **Lint as:** `.venv/bin/python -m ruff check . --exclude shared`
- **Never hand-edit anything under `shared/`.** It is one-way synced from `../packing-tool`. This bundle adds no token and no icon, so `scripts/sync_shared.py` is never run.
- **No hardcoded colours.** Every colour comes from `get_theme_manager().get_current_theme()`. Never `#666`, `#999`, `color: gray`. Use `theme.text_secondary`, `theme.border`, `theme.status_danger_bg`.
- **No UI calls from background threads.** `QtLogHandler.emit` runs on whatever thread logged; it must only emit a signal, never touch a widget.
- **QTreeView performance:** `setVerticalScrollMode(ScrollPerPixel)` and `setHorizontalScrollMode(ScrollPerPixel)` on the view. `setUniformRowHeights(True)` only while wrap is off.
- **Ring buffer capacity:** 5000 entries per source.
- **Newest-first ordering** in the model, matching `log_activity`'s current `insertRow(0)`.
- **No primary button** anywhere in the viewer — a log viewer has no committing action.
- **Version string is NOT bumped in this bundle.** It stays `1.9.9.1`.
- **PR-only.** Never commit to `main`. This work is on branch `worktree-phase9-bundle7-info-becomes-logs`.
- After code changes land, run `graphify update .` from the repo root (Task 8).

---

### Task 1: `LogEntry` — the unified row

**Files:**
- Create: `gui/log_entry.py`
- Test: `tests/test_log_entry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LogEntry` — a frozen dataclass with fields `timestamp: datetime`, `level: int`, `source: str`, `message: str`; a property `level_name -> str`; and a classmethod `activity(op_type: str, desc: str) -> LogEntry`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_entry.py
import logging
from datetime import datetime

from gui.log_entry import LogEntry


def test_entry_is_frozen():
    entry = LogEntry(
        timestamp=datetime(2026, 9, 7, 12, 0, 0),
        level=logging.INFO,
        source="Session",
        message="New session created",
    )
    try:
        entry.level = logging.ERROR
    except Exception:
        return
    raise AssertionError("LogEntry must be frozen")


def test_level_name_is_the_logging_name():
    entry = LogEntry(datetime.now(), logging.WARNING, "root", "careful")
    assert entry.level_name == "WARNING"


def test_activity_entries_are_info_and_carry_the_op_type_as_source():
    entry = LogEntry.activity("Report", "Generated: picklist")
    assert entry.level == logging.INFO
    assert entry.source == "Report"
    assert entry.message == "Generated: picklist"
    assert isinstance(entry.timestamp, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_entry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.log_entry'`

- [ ] **Step 3: Write minimal implementation**

```python
# gui/log_entry.py
"""One line in the log viewer, whatever stream produced it.

Activity (what the operator did) and Execution (what the program logged)
differ by which value lands in `source`, not by shape. Keeping one dataclass
is what lets the level filter and the error tint work on both sources.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime
    level: int
    source: str
    message: str

    @property
    def level_name(self) -> str:
        return logging.getLevelName(self.level)

    @classmethod
    def activity(cls, op_type: str, desc: str) -> "LogEntry":
        """An operator action. Always INFO -- the stream has no severity."""
        return cls(
            timestamp=datetime.now().astimezone(),
            level=logging.INFO,
            source=op_type,
            message=desc,
        )
```

Note: `field` is imported but unused — delete that import before committing, `ruff` will flag it.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_entry.py -v`
Expected: 3 passed

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_entry.py tests/test_log_entry.py
git commit -m "9.21: one entry shape for both log sources"
```

---

### Task 2: `FollowState` — follow-tail without pixels

**Files:**
- Create: `gui/log_follow.py`
- Test: `tests/test_log_follow.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FollowState` with attributes `following: bool` (starts `True`) and `pending: int` (starts `0`), and methods `scrolled(at_bottom: bool) -> None`, `appended() -> None`, `jumped_to_latest() -> None`.

This exists so follow-tail is testable without driving real scrollbar pixels. Without it, the one genuinely stateful behaviour in the viewer would go untested.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_follow.py
from gui.log_follow import FollowState


def test_starts_following_with_nothing_pending():
    state = FollowState()
    assert state.following is True
    assert state.pending == 0


def test_appending_while_following_counts_nothing():
    state = FollowState()
    state.appended()
    state.appended()
    assert state.pending == 0


def test_scrolling_up_stops_following():
    state = FollowState()
    state.scrolled(at_bottom=False)
    assert state.following is False


def test_arrivals_after_a_scroll_up_are_counted():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.appended()
    state.appended()
    assert state.pending == 3


def test_scrolling_back_to_the_bottom_resumes_and_clears():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.scrolled(at_bottom=True)
    assert state.following is True
    assert state.pending == 0


def test_jump_to_latest_resumes_and_clears():
    state = FollowState()
    state.scrolled(at_bottom=False)
    state.appended()
    state.jumped_to_latest()
    assert state.following is True
    assert state.pending == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_follow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.log_follow'`

- [ ] **Step 3: Write minimal implementation**

```python
# gui/log_follow.py
"""Whether the log viewer is following its own tail, and what it missed.

Pure state, no Qt: driving a real QScrollBar in a test proves the widget
scrolls, not that the rule is right. The rule is the part that breaks.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""


class FollowState:
    """Follow the newest entry, but only while the user is already there."""

    def __init__(self) -> None:
        self.following = True
        self.pending = 0

    def scrolled(self, at_bottom: bool) -> None:
        """The view's scrollbar moved. At the bottom means follow again."""
        self.following = at_bottom
        if at_bottom:
            self.pending = 0

    def appended(self) -> None:
        """An entry arrived. Counted only when the user is not watching."""
        if not self.following:
            self.pending += 1

    def jumped_to_latest(self) -> None:
        """The user pressed Jump to latest."""
        self.following = True
        self.pending = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_follow.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_follow.py tests/test_log_follow.py
git commit -m "9.21: follow-tail is a rule, not a scrollbar"
```

---

### Task 3: `LogBufferModel` — two ring buffers behind one model

**Files:**
- Create: `gui/log_model.py`
- Test: `tests/test_log_model.py`

**Interfaces:**
- Consumes: `LogEntry` from Task 1.
- Produces: `LogBufferModel(QAbstractTableModel)` with `CAPACITY = 5000`, `ACTIVITY = "Activity"`, `EXECUTION = "Execution"`, `COLUMNS = ("TIME", "LEVEL", "SOURCE", "MESSAGE")`; methods `append(entry: LogEntry, source: str) -> None`, `set_source(source: str) -> None`, `current_source() -> str`, `clear() -> None`, `entries() -> list[LogEntry]`.

`ROLE_STATUS` is imported from `gui.pandas_model` — the same role `StatusEdgeDelegate.edge_token` already reads. Answering it here is what lets the shipped delegate paint the error edge with no new delegate class.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_model.py
import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.pandas_model import ROLE_STATUS


def _entry(message="hello", level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0), level, source, message)


def test_newest_entry_is_row_zero(qapp):
    model = LogBufferModel()
    model.append(_entry("first"), LogBufferModel.EXECUTION)
    model.append(_entry("second"), LogBufferModel.EXECUTION)
    assert model.rowCount() == 2
    assert model.index(0, 3).data(Qt.DisplayRole) == "second"


def test_the_buffer_evicts_the_oldest_at_capacity(qapp):
    model = LogBufferModel()
    for n in range(LogBufferModel.CAPACITY + 10):
        model.append(_entry(f"m{n}"), LogBufferModel.EXECUTION)
    assert model.rowCount() == LogBufferModel.CAPACITY
    # Newest survives, oldest is gone.
    assert model.index(0, 3).data(Qt.DisplayRole) == f"m{LogBufferModel.CAPACITY + 9}"
    messages = {model.index(r, 3).data(Qt.DisplayRole) for r in range(model.rowCount())}
    assert "m0" not in messages


def test_the_two_sources_keep_separate_buffers(qapp):
    model = LogBufferModel()
    model.append(_entry("did a thing", source="Report"), LogBufferModel.ACTIVITY)
    model.append(_entry("debug noise"), LogBufferModel.EXECUTION)

    model.set_source(LogBufferModel.ACTIVITY)
    assert model.rowCount() == 1
    assert model.index(0, 3).data(Qt.DisplayRole) == "did a thing"

    model.set_source(LogBufferModel.EXECUTION)
    assert model.rowCount() == 1
    assert model.index(0, 3).data(Qt.DisplayRole) == "debug noise"


def test_columns_are_time_level_source_message(qapp):
    model = LogBufferModel()
    model.append(_entry("boom", level=logging.ERROR, source="ShopifyToolLogger"),
                 LogBufferModel.EXECUTION)
    assert model.columnCount() == 4
    assert model.index(0, 1).data(Qt.DisplayRole) == "ERROR"
    assert model.index(0, 2).data(Qt.DisplayRole) == "ShopifyToolLogger"
    assert model.index(0, 3).data(Qt.DisplayRole) == "boom"


def test_error_rows_carry_the_danger_status_role(qapp):
    model = LogBufferModel()
    model.append(_entry("boom", level=logging.ERROR), LogBufferModel.EXECUTION)
    model.append(_entry("fine", level=logging.INFO), LogBufferModel.EXECUTION)
    # Row 0 is the newest -- "fine".
    assert model.index(0, 0).data(ROLE_STATUS) is None
    assert model.index(1, 0).data(ROLE_STATUS) == "status_danger"


def test_critical_counts_as_danger_too(qapp):
    model = LogBufferModel()
    model.append(_entry("worse", level=logging.CRITICAL), LogBufferModel.EXECUTION)
    assert model.index(0, 0).data(ROLE_STATUS) == "status_danger"


def test_clear_empties_only_the_current_source(qapp):
    model = LogBufferModel()
    model.append(_entry("a"), LogBufferModel.EXECUTION)
    model.append(_entry("b"), LogBufferModel.ACTIVITY)
    model.set_source(LogBufferModel.EXECUTION)
    model.clear()
    assert model.rowCount() == 0
    model.set_source(LogBufferModel.ACTIVITY)
    assert model.rowCount() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.log_model'`

- [ ] **Step 3: Write minimal implementation**

```python
# gui/log_model.py
"""Two ring buffers, one model, one selected source.

Callers push entries and pick a source. They never see a row index, the
buffer's capacity, or the point it wraps at -- which is the whole reason
this is a module rather than a list on the widget.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
from collections import deque

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from gui.log_entry import LogEntry
from gui.pandas_model import ROLE_STATUS
from gui.theme_manager import get_theme_manager

_TIME = 0
_LEVEL = 1
_SOURCE = 2
_MESSAGE = 3


class LogBufferModel(QAbstractTableModel):
    """The rows the viewer shows, for whichever source is selected."""

    CAPACITY = 5000
    ACTIVITY = "Activity"
    EXECUTION = "Execution"
    COLUMNS = ("TIME", "LEVEL", "SOURCE", "MESSAGE")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buffers: dict[str, deque[LogEntry]] = {
            self.ACTIVITY: deque(maxlen=self.CAPACITY),
            self.EXECUTION: deque(maxlen=self.CAPACITY),
        }
        self._source = self.EXECUTION

    # -- the interface callers actually use ---------------------------------

    def append(self, entry: LogEntry, source: str) -> None:
        """Add one entry to a source's buffer, evicting the oldest at capacity.

        Only the *visible* source touches the model's row signals; an entry
        landing in the other buffer changes nothing on screen.
        """
        buffer = self._buffers[source]
        visible = source == self._source
        evicting = len(buffer) == self.CAPACITY

        if visible and not evicting:
            self.beginInsertRows(QModelIndex(), 0, 0)
            buffer.appendleft(entry)
            self.endInsertRows()
        elif visible:
            # A full deque both inserts and drops in one operation; a plain
            # insert signal would leave the view one row longer than the model.
            self.beginResetModel()
            buffer.appendleft(entry)
            self.endResetModel()
        else:
            buffer.appendleft(entry)

    def set_source(self, source: str) -> None:
        if source == self._source:
            return
        self.beginResetModel()
        self._source = source
        self.endResetModel()

    def current_source(self) -> str:
        return self._source

    def clear(self) -> None:
        """Empty the visible source. The other buffer is untouched."""
        self.beginResetModel()
        self._buffers[self._source].clear()
        self.endResetModel()

    def entries(self) -> list[LogEntry]:
        """The visible source's entries, newest first. For Save as text."""
        return list(self._buffers[self._source])

    # -- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._buffers[self._source])

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._buffers[self._source][index.row()]

        if role == Qt.DisplayRole:
            column = index.column()
            if column == _TIME:
                return entry.timestamp.strftime("%H:%M:%S")
            if column == _LEVEL:
                return entry.level_name
            if column == _SOURCE:
                return entry.source
            return entry.message

        if role == Qt.ToolTipRole:
            # The absolute time lives here; the cell only has room for a clock.
            if index.column() == _TIME:
                return entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            return entry.message

        if role == ROLE_STATUS:
            # StatusEdgeDelegate reads exactly this role, so answering it is
            # all the 3px error edge needs -- no delegate of our own.
            return "status_danger" if entry.level >= logging.ERROR else None

        if role == Qt.BackgroundRole and entry.level >= logging.ERROR:
            theme = get_theme_manager().get_current_theme()
            return QColor(theme.status_danger_bg)

        return None
```

Add `from PySide6.QtGui import QColor` to the imports — the `BackgroundRole` branch needs it.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_model.py -v`
Expected: 7 passed

If `ROLE_STATUS` is not exported from `gui/pandas_model.py`, grep for its definition and import from wherever it lives — do not redefine it, a second constant with the same value would silently diverge.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_model.py tests/test_log_model.py
git commit -m "9.21: two ring buffers behind one model"
```

---

### Task 4: `LogFilterProxy` — level floor and text search

**Files:**
- Create: `gui/log_filter.py`
- Test: `tests/test_log_filter.py`

**Interfaces:**
- Consumes: `LogBufferModel` from Task 3.
- Produces: `LogFilterProxy(QSortFilterProxyModel)` with `set_level_floor(level: int) -> None` and `set_search(text: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_filter.py
import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_filter import LogFilterProxy
from gui.log_model import LogBufferModel


def _model_with(*entries):
    model = LogBufferModel()
    for entry in entries:
        model.append(entry, LogBufferModel.EXECUTION)
    return model


def _entry(message, level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0), level, source, message)


def _messages(proxy):
    return [proxy.index(r, 3).data(Qt.DisplayRole) for r in range(proxy.rowCount())]


def test_level_floor_hides_everything_below_it(qapp):
    model = _model_with(
        _entry("chatty", logging.DEBUG),
        _entry("normal", logging.INFO),
        _entry("careful", logging.WARNING),
        _entry("boom", logging.ERROR),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_level_floor(logging.WARNING)
    assert sorted(_messages(proxy)) == ["boom", "careful"]


def test_search_matches_the_message(qapp):
    model = _model_with(_entry("picklist generated"), _entry("stock loaded"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("pick")
    assert _messages(proxy) == ["picklist generated"]


def test_search_also_matches_the_source(qapp):
    model = _model_with(
        _entry("something", source="Report"),
        _entry("other", source="Session"),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("repo")
    assert _messages(proxy) == ["something"]


def test_search_is_case_insensitive(qapp):
    model = _model_with(_entry("Picklist Generated"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("PICKLIST")
    assert _messages(proxy) == ["Picklist Generated"]


def test_the_two_filters_compose(qapp):
    model = _model_with(
        _entry("picklist ok", logging.INFO),
        _entry("picklist failed", logging.ERROR),
        _entry("stock failed", logging.ERROR),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_level_floor(logging.ERROR)
    proxy.set_search("picklist")
    assert _messages(proxy) == ["picklist failed"]


def test_an_empty_search_matches_everything(qapp):
    model = _model_with(_entry("a"), _entry("b"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("")
    assert len(_messages(proxy)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_filter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.log_filter'`

- [ ] **Step 3: Write minimal implementation**

```python
# gui/log_filter.py
"""Level floor and text search over the log buffer. No sorting.

The model's order is the truth -- entries arrive in time order and a log
sorted by anything else is not a log. This proxy filters and nothing more.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging

from PySide6.QtCore import QSortFilterProxyModel, Qt

_LEVEL = 1
_SOURCE = 2
_MESSAGE = 3


class LogFilterProxy(QSortFilterProxyModel):
    """Show entries at or above a level whose text contains a substring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._floor = logging.NOTSET
        self._search = ""

    def set_level_floor(self, level: int) -> None:
        self._floor = level
        self.invalidateFilter()

    def set_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        level_name = model.index(row, _LEVEL, parent).data(Qt.DisplayRole)
        # getLevelName round-trips a name back to its number.
        level = logging.getLevelName(level_name)
        if isinstance(level, int) and level < self._floor:
            return False

        if not self._search:
            return True

        source = model.index(row, _SOURCE, parent).data(Qt.DisplayRole) or ""
        message = model.index(row, _MESSAGE, parent).data(Qt.DisplayRole) or ""
        haystack = f"{source} {message}".lower()
        return self._search in haystack
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_filter.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_filter.py tests/test_log_filter.py
git commit -m "9.21: level floor and search, composed"
```

---

### Task 5: `QtLogHandler` emits structure, not a formatted string

**Files:**
- Modify: `gui/log_handler.py` (whole file)
- Test: `tests/test_log_handler.py`

**Interfaces:**
- Consumes: `LogEntry` from Task 1.
- Produces: `QtLogHandler` with signal `entry_received = Signal(object)` carrying a `LogEntry`. `log_message_received` is **removed**.

A level filter cannot read a level back out of `"%(asctime)s - %(levelname)s - %(message)s"` without parsing it, so the handler stops formatting and emits the structure.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_handler.py
import logging

from gui.log_entry import LogEntry
from gui.log_handler import QtLogHandler


def _record(level=logging.WARNING, name="ShopifyToolLogger", msg="careful %s", args=("now",)):
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


def test_emit_sends_a_log_entry(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record())

    assert len(received) == 1
    assert isinstance(received[0], LogEntry)


def test_the_entry_carries_level_logger_name_and_rendered_message(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record(level=logging.ERROR, name="shopify_tool.core",
                         msg="failed on %s", args=("order 42",)))

    entry = received[0]
    assert entry.level == logging.ERROR
    assert entry.source == "shopify_tool.core"
    # Rendered, not the raw template -- args must be interpolated.
    assert entry.message == "failed on order 42"


def test_the_old_string_signal_is_gone(qapp):
    assert not hasattr(QtLogHandler, "log_message_received")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_handler.py -v`
Expected: FAIL — `entry_received` does not exist.

- [ ] **Step 3: Rewrite `gui/log_handler.py`**

```python
"""Bridges Python logging to Qt, as structure rather than as text.

This handler runs on whatever thread logged, so it must only emit a signal --
never touch a widget. That is the whole reason it exists.

It emits a LogEntry, not a formatted line: the viewer filters by level, and a
level parsed back out of a formatted string is a level you can get wrong.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from gui.log_entry import LogEntry


class QtLogHandler(logging.Handler, QObject):
    """Emits one LogEntry per record, on the thread that logged it.

    Signals:
        entry_received (object): the LogEntry for each record.
    """

    entry_received = Signal(object)

    def __init__(self, parent=None):
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record):
        """Turn a LogRecord into a LogEntry and emit it."""
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).astimezone(),
            level=record.levelno,
            source=record.name,
            message=record.getMessage(),
        )
        self.entry_received.emit(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_handler.py -v`
Expected: 3 passed

The app will not launch until Task 7 rewires `main_window_pyside.py:293-304`; that is expected and is why the rewiring is one task away, not five.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_handler.py tests/test_log_handler.py
git commit -m "9.21: the handler emits a record, not a rendered line"
```

---

### Task 6: `LogViewer` — the page

**Files:**
- Delete then create: `gui/log_viewer.py` (the dead CustomTkinter file; the path is reused)
- Test: `tests/test_log_viewer.py`

**Interfaces:**
- Consumes: `LogEntry`, `FollowState`, `LogBufferModel`, `LogFilterProxy`, and `StatusEdgeDelegate` from `gui/status_edge_delegate.py`.
- Produces: `LogViewer(QWidget)` with `append(entry: LogEntry, source: str) -> None`, `set_source(source: str) -> None`, `set_wrap(on: bool) -> None`, and attributes `view` (the `QTreeView`), `model`, `proxy`, `follow`, `footer_label`, `jump_button`, `search_input`, `wrap_toggle`, `save_button`.

**Step 0 — delete the dead file first.** `gui/log_viewer.py` is CustomTkinter with zero importers (`grep -rn "log_viewer" --include=*.py .` returns nothing outside itself). Delete it before writing the new one so the new file is not written on top of unrelated code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_viewer.py
import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.log_viewer import LogViewer


def _entry(message="hello", level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0), level, source, message)


def test_both_sources_render_in_one_widget(qapp):
    viewer = LogViewer()
    viewer.append(_entry("operator did a thing", source="Report"),
                  LogBufferModel.ACTIVITY)
    viewer.append(_entry("program logged a thing"), LogBufferModel.EXECUTION)

    viewer.set_source(LogBufferModel.ACTIVITY)
    assert viewer.proxy.rowCount() == 1
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "operator did a thing"

    viewer.set_source(LogBufferModel.EXECUTION)
    assert viewer.proxy.rowCount() == 1
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "program logged a thing"


def test_there_is_no_primary_button(qapp):
    from PySide6.QtWidgets import QPushButton

    viewer = LogViewer()
    roles = [b.property("role") for b in viewer.findChildren(QPushButton)]
    assert "primary" not in roles


def test_a_long_traceback_survives_both_wrap_modes(qapp):
    viewer = LogViewer()
    traceback = "Traceback (most recent call last): " + "x" * 300
    viewer.append(_entry(traceback, level=logging.ERROR), LogBufferModel.EXECUTION)

    viewer.set_wrap(False)
    assert viewer.view.uniformRowHeights() is True
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == traceback

    viewer.set_wrap(True)
    assert viewer.view.uniformRowHeights() is False
    assert viewer.view.wordWrap() is True
    # The text is never truncated in the model -- eliding is the view's job.
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == traceback


def test_alternating_row_colours_are_off(qapp):
    viewer = LogViewer()
    assert viewer.view.alternatingRowColors() is False


def test_the_footer_is_hidden_while_following(qapp):
    viewer = LogViewer()
    viewer.append(_entry(), LogBufferModel.EXECUTION)
    assert viewer.follow.following is True
    assert viewer.footer_label.isVisibleTo(viewer) is False


def test_the_footer_counts_arrivals_after_a_scroll_up(qapp):
    viewer = LogViewer()
    viewer.follow.scrolled(at_bottom=False)
    viewer.append(_entry("a"), LogBufferModel.EXECUTION)
    viewer.append(_entry("b"), LogBufferModel.EXECUTION)
    viewer._sync_footer()
    assert viewer.follow.pending == 2
    assert "2" in viewer.footer_label.text()


def test_jump_to_latest_resumes_following(qapp):
    viewer = LogViewer()
    viewer.follow.scrolled(at_bottom=False)
    viewer.append(_entry(), LogBufferModel.EXECUTION)
    viewer.jump_button.click()
    assert viewer.follow.following is True
    assert viewer.follow.pending == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_viewer.py -v`
Expected: FAIL — `LogViewer` does not exist (the old module has no such class).

- [ ] **Step 3: Write the implementation**

Build `gui/log_viewer.py` as a `QWidget` with a three-row `QVBoxLayout`:

1. **Control row** (`QHBoxLayout`): a source switch (two checkable `QPushButton`s, `Activity` / `Execution`, in a `QButtonGroup` so exactly one is checked); level filter buttons (`All`, `Info`, `Warning`, `Error`, checkable, one group) calling `proxy.set_level_floor`; a `QLineEdit` with placeholder `"Search logs…"` calling `proxy.set_search` on `textChanged`; a `Wrap` toggle (`QCheckBox`) calling `set_wrap`; and a `Save as text` button with `set_button_role(button, "ghost")`.
2. **The view**: `QTreeView` with `setRootIsDecorated(False)`, `setModel(self.proxy)`, `setItemDelegate(StatusEdgeDelegate(self.view))`, `setAlternatingRowColors(False)`, `setVerticalScrollMode(QTreeView.ScrollPerPixel)`, `setHorizontalScrollMode(QTreeView.ScrollPerPixel)`, `setSelectionBehavior(QTreeView.SelectRows)`, `setEditTriggers(QTreeView.NoEditTriggers)`. Column 3 (`MESSAGE`) stretches; 0–2 resize to contents.
3. **Footer row** (`QHBoxLayout`, a real row, never an overlay): `footer_label` and `jump_button` (`set_button_role(..., "ghost")`), both hidden while following.

Wire it:

```python
    def append(self, entry, source):
        self.model.append(entry, source)
        if source == self.model.current_source():
            self.follow.appended()
            if self.follow.following:
                self.view.scrollToTop()   # newest-first: the tail is the top
            self._sync_footer()

    def set_source(self, source):
        self.model.set_source(source)
        self.follow.jumped_to_latest()
        self.view.scrollToTop()
        self._sync_footer()

    def set_wrap(self, on: bool):
        # Uniform heights and word wrap are mutually exclusive: a wrapped row
        # is taller than its neighbours by definition.
        self.view.setWordWrap(on)
        self.view.setUniformRowHeights(not on)
        self._settings.setValue("logs/wrap", on)

    def _on_scrolled(self, _value):
        bar = self.view.verticalScrollBar()
        # Newest-first, so the tail is the TOP of the view.
        self.follow.scrolled(at_bottom=bar.value() == bar.minimum())
        self._sync_footer()

    def _sync_footer(self):
        pending = self.follow.pending
        visible = pending > 0
        self.footer_label.setVisible(visible)
        self.jump_button.setVisible(visible)
        if visible:
            noun = "entry" if pending == 1 else "entries"
            self.footer_label.setText(f"{pending} new {noun}")

    def _jump_to_latest(self):
        self.follow.jumped_to_latest()
        self.view.scrollToTop()
        self._sync_footer()
```

**Note the orientation carefully:** the model is newest-first, so "the tail"
is row 0 at the **top**. Following means `scrollToTop()`, and "at the tail"
means `bar.value() == bar.minimum()`. Getting this backwards makes follow-tail
appear to work while never actually following.

Theme: no hardcoded colours. Subscribe with `on_theme_changed(self, lambda _t: self._apply_theme())` from `shared.theme`, as `gui/session_browser_widget.py` does, and read every colour from `get_theme_manager().get_current_theme()`. `TIME` uses the mono face.

`Save as text` writes `self.model.entries()` through a `QFileDialog.getSaveFileName`, one entry per line as `f"{ts}  {level:<8} {source}  {message}"`. Guard the empty path (user cancelled).

Wrap is restored from `QSettings` on construction, defaulting to **off**.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_viewer.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add gui/log_viewer.py tests/test_log_viewer.py
git commit -m "9.21: one viewer, two sources, a tail that follows"
```

---

### Task 7: The swap — Logs replaces Info, Statistics is deleted

This is the one task that deletes. Everything before it was additive, so the app has kept running; after it, nothing points at the old pages.

**Files:**
- Modify: `gui/ui_manager.py` — `_TAB_LABELS`, `_RAIL_LABELS`, `_TAB_TOOLTIPS`, `_create_tab4_information`; delete `_create_statistics_subtab`, `_make_stat_card`, `_make_courier_card`, `_make_tag_card`, `_create_activity_log_subtab`, `_create_execution_log_subtab`
- Modify: `gui/main_window_pyside.py` — `log_activity` (~1323), the handler wiring (~293-304); delete `update_statistics_tab` (~1175), `_clear_statistics_view`, `_on_sku_search_changed` and their three call sites in `_update_all_views` (~1146, ~1150, ~1154)
- Modify: `gui/components/card.py` — module docstring only
- Modify: `tests/test_components_card.py` — remove the three helper tests
- Delete: `tests/test_main_window_statistics.py`
- Test: `tests/test_logs_destination.py`

**Interfaces:**
- Consumes: `LogViewer` from Task 6.
- Produces: `self.mw.log_viewer`, the `LogViewer` instance. `MainWindow.log_activity(op_type, desc)` keeps its exact signature — all ten call sites in `actions_handler.py` are untouched.

**Do NOT delete** (spec §2, "Kept"): `self.analysis_stats`, `recalculate_statistics`, the `analysis_stats.json` read/write at ~906 / ~956 / ~987, `shared/stats_manager.py`, `global_stats.json`, or `gui/components/statcard.py`. `analysis_stats` is session persistence, not the deleted view; deleting it breaks session reload.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logs_destination.py
from gui.log_model import LogBufferModel
from gui.log_viewer import LogViewer
from gui.ui_manager import UIManager


def test_the_rail_reads_logs():
    assert UIManager._RAIL_LABELS[3] == "Logs"
    assert UIManager._TAB_LABELS[3] == "Logs"
    assert "Statistics" not in UIManager._TAB_TOOLTIPS[3]


def test_no_statistics_page_is_reachable():
    for gone in (
        "_create_statistics_subtab",
        "_create_activity_log_subtab",
        "_create_execution_log_subtab",
        "_make_stat_card",
        "_make_courier_card",
        "_make_tag_card",
    ):
        assert not hasattr(UIManager, gone), f"{gone} should be deleted"


def test_the_statistics_update_methods_are_gone():
    from gui.main_window_pyside import MainWindow

    for gone in ("update_statistics_tab", "_clear_statistics_view",
                 "_on_sku_search_changed"):
        assert not hasattr(MainWindow, gone), f"{gone} should be deleted"


def test_log_activity_appends_to_the_activity_source(qapp):
    viewer = LogViewer()

    class Stub:
        log_viewer = viewer
        log_activity = __import__(
            "gui.main_window_pyside", fromlist=["MainWindow"]
        ).MainWindow.log_activity

    Stub().log_activity("Report", "Generated: picklist")

    viewer.set_source(LogBufferModel.ACTIVITY)
    assert viewer.proxy.rowCount() == 1
    from PySide6.QtCore import Qt
    assert viewer.proxy.index(0, 2).data(Qt.DisplayRole) == "Report"
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "Generated: picklist"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_logs_destination.py -v`
Expected: FAIL — the rail still reads `Info` and the deleted methods still exist.

- [ ] **Step 3: Make the changes**

In `gui/ui_manager.py`, index 3 of each tuple:

```python
    _TAB_LABELS = (
        "Session Setup",
        "Analysis Results",
        "Session Browser",
        "Logs",
        "Tools",
    )
    _RAIL_LABELS = ("Setup", "Results", "Browse", "Logs", "Tools")
    _TAB_TOOLTIPS = (
        "Session setup and file loading (Ctrl+1)",
        "View and edit analysis results (Ctrl+2)",
        "Browse past sessions (Ctrl+3)",
        "Activity and execution logs (Ctrl+4)",
        "PDF processing and utilities (Ctrl+5)",
    )
```

`_TAB_ICONS` is **unchanged** — index 3 stays `"info"`. Adding a `scroll-text`
glyph means editing `packing-tool` and running `scripts/sync_shared.py`, a
cross-repo cost this bundle declines (spec §2).

Replace `_create_tab4_information` with:

```python
    def _create_tab4_logs(self):
        """Create Tab 4: Logs -- one viewer, two sources, no sub-tabs.

        Statistics is deleted (9.20) and the two log widgets are one widget
        (9.21), so there is nothing left to tab between.
        """
        from gui.log_viewer import LogViewer

        self.mw.log_viewer = LogViewer(self.mw)
        return self.mw.log_viewer
```

Update the `pages` tuple to call `self._create_tab4_logs()`.

Delete `_create_statistics_subtab`, `_make_stat_card`, `_make_courier_card`, `_make_tag_card`, `_create_activity_log_subtab`, `_create_execution_log_subtab`. Then remove any imports left unused (`QPlainTextEdit` among them) — `ruff` will name them.

In `gui/main_window_pyside.py`, the handler wiring (~293-304) loses its formatter:

```python
        self.log_handler = QtLogHandler()
        # Root logger level is owned by shared.logger.setup_logging
        # (called from ProfileManager, before this runs) - don't
        # override it back to INFO here, or FULFILLMENT_LOG_LEVEL=DEBUG
        # would silently have no effect.
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.entry_received.connect(self._on_log_entry)
```

and gains the slot plus the rewritten `log_activity`:

```python
    def _on_log_entry(self, entry):
        """A record from the root logger reaches the Execution source."""
        self.log_viewer.append(entry, LogBufferModel.EXECUTION)

    def log_activity(self, op_type, desc):
        """Records an operator action in the Logs destination.

        Signature is unchanged on purpose: actions_handler calls this from
        ten places and none of them should have to know the widget changed.

        Args:
            op_type (str): The type of operation (e.g., "Session", "Analysis").
            desc (str): A description of the activity.
        """
        self.log_viewer.append(
            LogEntry.activity(op_type, desc), LogBufferModel.ACTIVITY
        )
```

Import `LogEntry` and `LogBufferModel` at the top of `main_window_pyside.py`.

Delete `update_statistics_tab`, `_clear_statistics_view`, `_on_sku_search_changed`, and their three call sites in `_update_all_views` (the `self.update_statistics_tab()` line and the two `self._clear_statistics_view()` lines). Keep the surrounding `self.analysis_stats = ...` assignments — they still feed the file.

Reword `gui/components/card.py`'s module docstring: it names `_make_stat_card`, `_make_courier_card`, `_make_tag_card` as the code `Card` was extracted from. Say instead that `Card` was extracted from three near-identical card builders in `ui_manager.py`, since deleted.

Delete `tests/test_main_window_statistics.py`. In `tests/test_components_card.py`, delete the three tests calling `UIManager._make_stat_card`, `_make_courier_card`, `_make_tag_card` (around lines 67, 76, 84) and any import left unused.

- [ ] **Step 4: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
Expected: all pass. Any failure naming `activity_log_table`, `execution_log_edit`, `sku_table`, or a statistics method is a call site missed above — fix it rather than skipping the test.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m ruff check . --exclude shared
git add -A
git commit -m "9.20: Statistics deleted, Info becomes Logs"
```

---

### Task 8: Glossary, both themes, and the gate

**Files:**
- Modify: `CONTEXT.md` (already edited at spec time — verify, do not duplicate)
- Test: `tests/test_log_viewer_theme.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_log_viewer_theme.py
import logging
from datetime import datetime

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.theme_manager import get_theme_manager


def _error_background(theme_name):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    model = LogBufferModel()
    model.append(
        LogEntry(datetime.now(), logging.ERROR, "root", "boom"),
        LogBufferModel.EXECUTION,
    )
    return model.index(0, 0).data(Qt.BackgroundRole)


def test_the_error_tint_is_a_token_in_both_themes(qapp):
    light = _error_background("light")
    dark = _error_background("dark")
    assert isinstance(light, QColor)
    assert isinstance(dark, QColor)
    # Both themes define status_danger_bg, and they are not the same colour.
    assert light != dark
```

`get_theme_manager().set_theme(name)` accepts exactly `"light"` and `"dark"` (verified at `gui/theme_manager.py:124`), and returns early when the name is already current — so set the *other* theme first if a test needs a guaranteed transition. The `qapp` fixture is in `tests/conftest.py:93`.

- [ ] **Step 2: Run it, then make it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_viewer_theme.py -v`

- [ ] **Step 3: Eyeball both themes with no display**

Render the widget to a PNG and look at it — the technique 9.19 established:

```python
# scratch, not committed
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from gui.log_viewer import LogViewer
from gui.log_model import LogBufferModel
from gui.log_entry import LogEntry
import logging, datetime

app = QApplication([])
viewer = LogViewer()
viewer.resize(1000, 500)
for level, msg in [
    (logging.INFO, "Session created: 2026-09-07_ACME"),
    (logging.WARNING, "Stock file is 4 days old"),
    (logging.ERROR, "Traceback (most recent call last): " + "x" * 300),
]:
    viewer.append(LogEntry(datetime.datetime.now(), level, "ShopifyToolLogger", msg),
                  LogBufferModel.EXECUTION)
image = QImage(viewer.size(), QImage.Format_ARGB32)
viewer.render(image)
image.save("/tmp/logs_light.png")
```

Repeat after switching the theme, save as `logs_dark.png`, and read both PNGs. Confirm: the error row's tint and 3px edge are visible in both, `TIME`/`SOURCE` sit back in `text_secondary`, and the message elides rather than wrapping while wrap is off.

- [ ] **Step 4: Verify `CONTEXT.md` carries the new terms**

It should already define **Logs**, **Log entry**, **Source**, **Follow-tail**, and say the web tier is Analysis Results only. Confirm, do not duplicate.

- [ ] **Step 5: The gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/python -m ruff check . --exclude shared
```

Both must be clean. Then, from the repo root:

```bash
graphify update .
```

- [ ] **Step 6: Commit and push**

```bash
git add -A
git commit -m "9.21: both themes, the glossary, and the gate"
git push -u origin worktree-phase9-bundle7-info-becomes-logs
```

---

## Done when

**9.20** — the rail reads `Logs`, no statistics page is reachable, and `global_stats.json` still gains a record when an analysis runs.

**9.21** — both sources render in one widget, a 300-character traceback survives both wrap modes, and follow resumes correctly after a scroll-up.

**Bundle** — both hold, the full suite passes, `ruff` is clean, and `graphify update .` has run.

## Self-review notes

- Spec §1's decision (delete all four blocks) is carried by Task 7's deletions; §1's `CONTEXT.md` correction by Task 8 Step 4.
- Spec §2's "Kept" list is restated at the head of Task 7, where the risk of over-deleting actually lives.
- Spec §3's five modules map to Tasks 1, 2, 3, 4, 6; the handler change to Task 5.
- Spec §4 (theme) is Task 8; §5 (seams) is distributed — every pure seam has a Qt-free test, and only Tasks 6–8 need `qapp`.
- Names used consistently throughout: `append(entry, source)`, `set_source`, `set_level_floor`, `set_search`, `scrolled`, `appended`, `jumped_to_latest`, `entry_received`.
