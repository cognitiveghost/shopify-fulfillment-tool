# UI refresh phase 6: Logs on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Qt log viewer with one web page drawn to the approved mockup, in its own
`QWebEngineView`: Source and Level segmented controls with live counts, search, dense rows with the newest
at the bottom, a traceback under the row that carries one, Follow that tracks the scroll, and Save as text
for the entries shown.

**Architecture:** Python keeps the entries and words every row. `LogBuffer` (`gui/log_buffer.py`, no Qt)
holds 5,000 rows per stream and turns each `LogEntry` into a dict of strings. `LogsWidget`
(`gui/logs_widget.py`) hosts the view and sends rows in batches, at most every 100 ms, through
`LogsBridge.entriesAdded` (`gui/logs_bridge.py`). The page (`gui/web/logs.js`) keeps every row it is sent
and owns the whole view state: source, level, search, wrap, follow and which rows are open. It builds each
row once and filters by setting `hidden`. It names entries to Python by id for Save and Copy.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain CSS and JavaScript (no
build step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-refresh-phase6-logs-web-design.md`. Read it whole before
starting; this plan argues from it. Copy (every label, empty-state sentence and toast) is in spec §5, §6
and §8 and is verbatim. Mockup: `docs/design/ui-refresh/mockups/logs.html` (render:
`mockups/renders/logs.png`). To read exact values, unpack the bundle with the script in
`docs/design/ui-refresh/mockups/README.md`.

**Every code block in this plan was run before the plan was written**, against a scratch copy of the repo
at 29b90c5 (code identical to `origin/main` at 47f0f79). This document was generated from that copy: each
"Create" block is the file as it ran, and each "Find exactly / Replace with" pair was applied to the
untouched file and compared with the copy. There, the tests of every task passed, `ruff check .` passed,
and the whole suite passed but for the three baseline failures below. The page was rendered in both themes
and compared with the mockup. If a block fails for you, suspect a typo in transcription, or a change on
`main` since 47f0f79, before you suspect the design, and say what differed.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-18` on branch
  `dr/18-ui-refresh-phase-6-move-logs-to-the-web`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any
  other Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp
  dir. End every message with the attribution lines your session is given.
- **Transcribe code blocks exactly.** A block headed "Create" is the whole file. A block pair headed "Find
  exactly" / "Replace with" is one Edit: the first block is the `old_string`, the second the `new_string`,
  and the first occurs once in the file at the moment you reach it. Apply a file's edits in the order
  given. "Replace the whole file" means Read the file, then Write the block over it.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`,
  `transform`, gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`,
  `var(--overlay-shadow)` or `none`, and only in a `.css` file. Never set `element.style.*` to a colour
  from JavaScript: use a class.
- The lint reads a colour word after a colour property up to the next `;`. So every CSS declaration ends
  with `;`, including the last one in a rule.
- The lint reads `rotate`, `scale`, `translate` and `opacity` followed by `:` as a banned CSS property, in
  `.js` files too. The blocks in this plan avoid it; do not "tidy" them. The chevron is swapped, never
  turned (spec §9).
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is
  `var(--surface-raised)`. Type sizes are `var(--type-caption-size)`, `--type-body-size`,
  `--type-label-size`, `--type-heading-size`. The mono face is `var(--font-family-mono)`. A list row's
  height is `var(--row-height)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input or
  a box the eye must find is `--border`.
- **Nothing from a log row goes through `innerHTML`.** A log message can hold text from a CSV. `logs.js`
  builds rows with `createElement` and `textContent`; the only `innerHTML` in it writes constant glyphs
  and the two fixed controls. Keep it that way.
- **`LogsWidget.append` and `LogsWidget._flush` must never log**, and nothing they call may. The root
  logger's handler calls `append` for every record on the GUI thread: a log call there calls itself
  without end.
- `gui/web/kit.css` and everything under `shared/` do not change in this task (spec §3.1, §13).
- No `pyproject.toml`. No new dependency. No direct commit to `main`.
- `ruff check .` must pass after every task. `ruff` forbids `date.today()` and a `datetime(...)` with no
  `tzinfo` (rules DTZ011, DTZ001): the blocks use `datetime.now().astimezone()` and `tzinfo=UTC`.

## Baseline

On this dev VM three tests fail before any change, and they are not yours:
`tests/test_label_printing.py::TestImageToZpl::test_black_pixels_become_set_bits`,
`::test_invert_flips_the_polarity` and `::test_rotate_and_invert_compose`. Every other test passes on
29b90c5. Every test that passes there must pass after every task, unless the task rewrites or deletes it
and says so. The whole suite takes about six minutes; run it once, in Task 7. Each task before that runs
the files it names.

## Review Focus

The inputs the spec implies and a person will meet, most likely first. Each has its test in the task that
owns the code.

1. **Entries arrive while the Logs tab is hidden, then the window is shown or made smaller.** The list
   must still sit at its end with Follow on. Test: `test_a_smaller_window_keeps_a_following_list_at_its_end`
   (Task 4).
2. **A message with a line break in it** (an exception text, a multi-line warning). An unwrapped row stays
   one 26px line; a wrapped one shows both lines. Test:
   `test_a_row_is_twenty_six_pixels_and_a_wrapped_long_one_is_taller` (Task 4).
3. **A message with markup in it** (a product name from a CSV, `<b>`). It is drawn as text. Test:
   `test_a_message_with_markup_in_it_is_drawn_as_text` (Task 4).
4. **A search with characters a pattern would read** (`.*`, `#`). It is plain text. Test:
   `test_search_reads_the_message_and_the_source_but_not_the_traceback` (Task 4).
5. **Text outside ASCII in a saved file** (a customer's name, the `—` in every exception summary). The
   file is UTF-8. Test: `test_text_outside_ascii_is_saved_as_utf8` (Task 5).

Also covered where it lives: an id the page still shows after Python dropped it
(`test_save_with_no_row_left_opens_no_dialog`, Task 5; `test_pick_...skips_a_dropped_id`, Task 2); a batch
answered twice (`test_a_batch_sent_twice_is_drawn_once`, Task 4); junk sent to a slot
(`test_save_shown_keeps_whole_numbers_only`, Task 3).

## File map

| File | Task | What it is |
|---|---|---|
| `gui/log_entry.py`, `gui/log_handler.py` | 1 | `LogEntry.traceback`; the handler fills it |
| `gui/log_buffer.py` (new) | 2 | `LogBuffer`, `to_row`, `band`, `save_text`, `default_filename`. No Qt |
| `gui/logs_bridge.py` (new) | 3 | `LogsBridge(PageBridge)`, `mount_logs_page` |
| `gui/web/logs.html`, `logs.css`, `logs.js` (new) | 4 | The page |
| `gui/logs_widget.py` (new) | 5 | `LogsWidget(QWidget)`: the view, the buffer, the batch timer, save, copy |
| `gui/ui_manager.py`, `gui/main_window_pyside.py` | 6 | Tab 3 is `LogsWidget`; the inset rule is deleted |
| `gui/log_viewer.py`, `log_model.py`, `log_filter.py`, `log_follow.py` and their four test files, `tests/test_log_viewer_theme.py` | 6 | Deleted |
| `.github/workflows/build_release.yml` | 6 | The bundle check names `logs.html` |
| `CONTEXT.md`, ADR 0016, `roadmap.md`, five PNGs | 7 | Docs and renders |

---

### Task 1: The traceback on a log entry

**Files:**
- Modify: `gui/log_entry.py`, `gui/log_handler.py`
- Test: `tests/test_log_entry.py`, `tests/test_log_handler.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `LogEntry(timestamp, level, source, message, traceback="")`, a frozen dataclass whose fifth
  field is the whole traceback or `""`. `QtLogHandler.emit` fills it from `record.exc_info`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_log_entry.py`, 1 edit, in this order.

**Edit 1 of 1** (near line 30). Find exactly:

````
    assert entry.message == "Generated: picklist"
    assert isinstance(entry.timestamp, datetime)
````

Replace with:

````
    assert entry.message == "Generated: picklist"
    assert isinstance(entry.timestamp, datetime)


def test_an_entry_has_no_traceback_unless_it_is_given_one():
    plain = LogEntry(datetime.now().astimezone(), logging.INFO, "root", "fine")
    assert plain.traceback == ""
    assert LogEntry.activity("Report", "Generated: picklist").traceback == ""
    failed = LogEntry(
        datetime.now().astimezone(), logging.ERROR, "root", "bad", "Traceback (most recent call last):"
    )
    assert failed.traceback == "Traceback (most recent call last):"
````

In `tests/test_log_handler.py`, 1 edit, in this order.

**Edit 1 of 1** (near line 87). Find exactly:

````

    assert received[0].message == "careful now"
````

Replace with:

````

    assert received[0].message == "careful now"


def _raised(exc_info):
    return logging.LogRecord(
        name="gui.actions_handler",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Save failed",
        args=(),
        exc_info=exc_info,
    )


def test_the_whole_traceback_rides_beside_the_summary(qapp):
    import sys

    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)
    try:
        raise PermissionError("share is read-only")
    except PermissionError:
        record = _raised(sys.exc_info())

    handler.emit(record)

    trace = received[0].traceback
    assert trace.startswith("Traceback (most recent call last):")
    assert 'raise PermissionError("share is read-only")' in trace
    assert trace.endswith("PermissionError: share is read-only")
    # The summary stays on the message: a row that is not open still names the cause.
    assert received[0].message == "Save failed — PermissionError: share is read-only"


def test_a_record_without_an_exception_has_no_traceback(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record())
    handler.emit(_raised((None, None, None)))

    assert [entry.traceback for entry in received] == ["", ""]
    assert received[1].message == "Save failed"
````

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_log_entry.py tests/test_log_handler.py`

Expected: 3 failed. `test_an_entry_has_no_traceback_unless_it_is_given_one` fails with `AttributeError:
'LogEntry' object has no attribute 'traceback'` (or `TypeError` on the fifth argument), and the two handler
tests fail the same way.

- [ ] **Step 3: Add the field and fill it**

In `gui/log_entry.py`, 1 edit, in this order.

**Edit 1 of 1** (near line 19). Find exactly:

````
    source: str
    message: str

    @property
````

Replace with:

````
    source: str
    message: str
    # The whole traceback when the record carried an exception, else "".
    traceback: str = ""

    @property
````

In `gui/log_handler.py`, 2 edits, in this order.

**Edit 1 of 2** (near line 36). Find exactly:

````

        An exception's one-line summary rides on the message: the error banner
        (9.25) sends the operator here for the cause, and a row per record
        keeps the viewer one line per entry. The full traceback stays in the
        JSON file log.
        """
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            etype, value = record.exc_info[:2]
            summary = traceback.format_exception_only(etype, value)[-1].strip()
            message = f"{message} — {summary}"
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).astimezone(),
````

Replace with:

````

        An exception's one-line summary rides on the message: the error banner
        (9.25) sends the operator here for the cause, and a row that is not
        open still names it. The whole traceback rides beside it, and the
        Logs page shows it under the row (phase 6 spec section 4.1).
        """
        message = record.getMessage()
        trace = ""
        if record.exc_info and record.exc_info[1] is not None:
            etype, value = record.exc_info[:2]
            summary = traceback.format_exception_only(etype, value)[-1].strip()
            message = f"{message} — {summary}"
            trace = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).astimezone(),
````

**Edit 2 of 2** (near line 50). Find exactly:

````
            source=record.name,
            message=message,
        )
        self.entry_received.emit(entry)
````

Replace with:

````
            source=record.name,
            message=message,
            traceback=trace,
        )
        self.entry_received.emit(entry)
````

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_log_entry.py tests/test_log_handler.py tests/test_logs_destination.py tests/test_log_viewer.py tests/test_log_model.py`

Expected: all pass. The Qt viewer still runs on the old four fields; it is deleted in Task 6.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/log_entry.py gui/log_handler.py tests/test_log_entry.py tests/test_log_handler.py` and commit.
Message subject: `Logs: a log entry carries its traceback`.

---

### Task 2: `LogBuffer` and the row

**Files:**
- Create: `gui/log_buffer.py`
- Test: `tests/test_log_buffer.py`

**Interfaces:**
- Consumes: `LogEntry` with `traceback` (Task 1).
- Produces, all in `gui/log_buffer.py`:
  - `CAPACITY = 5000`, `ACTIVITY = "Activity"`, `EXECUTION = "Execution"`.
  - `band(level: int) -> str`: `"info"`, `"warning"` or `"error"`.
  - `to_row(entry_id: int, entry: LogEntry, stream: str) -> dict` with the keys `id`, `time`, `date`,
    `band`, `level`, `stream`, `source`, `short`, `message`, `traceback` (spec §4.2).
  - `LogBuffer(capacity=CAPACITY)` with `.capacity`, `.add(entry, stream) -> dict`, `.rows() -> list[dict]`,
    `.pick(ids) -> list[dict]`.
  - `save_text(rows) -> str` and `default_filename(client_id, day: date) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_buffer.py`:

````python
"""The Logs page's rows and buffer: no Qt (phase 6 spec section 4.2)."""

import logging
from datetime import UTC, date, datetime

import pytest

from gui.log_buffer import (
    ACTIVITY,
    CAPACITY,
    EXECUTION,
    LogBuffer,
    band,
    default_filename,
    save_text,
    to_row,
)
from gui.log_entry import LogEntry

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_900, tzinfo=UTC)
TRACE = (
    "Traceback (most recent call last):\n"
    '  File "gui/tools_widget.py", line 142, in _on_run\n'
    "PermissionError: share is read-only"
)


def entry(
    message="Scanned order #48254",
    level=logging.INFO,
    source="shopify_tool.core",
    trace="",
):
    return LogEntry(STAMP, level, source, message, trace)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (logging.DEBUG, "info"),
        (logging.INFO, "info"),
        (25, "info"),
        (logging.WARNING, "warning"),
        (35, "warning"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "error"),
    ],
)
def test_a_level_falls_in_one_of_three_bands(level, expected):
    assert band(level) == expected


def test_a_row_carries_every_word_the_page_draws():
    row = to_row(
        12, entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
    )
    assert row == {
        "id": 12,
        "time": "14:00:53.508",
        "date": "2026-09-30",
        "band": "error",
        "level": "Error",
        "stream": "Execution",
        "source": "gui.tools_widget",
        "short": "tools_widget",
        "message": "Save failed",
        "traceback": TRACE,
    }


@pytest.mark.parametrize(
    ("level", "name"),
    [(logging.DEBUG, "Debug"), (logging.CRITICAL, "Critical"), (25, "Level 25")],
)
def test_the_badge_shows_the_real_level_name(level, name):
    assert to_row(0, entry(level=level), EXECUTION)["level"] == name


@pytest.mark.parametrize(
    ("source", "short"),
    [("Data Edit", "Data Edit"), ("root", "root"), ("a.b.c", "c"), ("odd.", "odd.")],
)
def test_short_is_the_source_after_its_last_dot(source, short):
    assert to_row(0, entry(source=source), ACTIVITY)["short"] == short


def test_milliseconds_are_cut_not_rounded():
    stamp = datetime(2026, 9, 30, 9, 5, 7, 999_999, tzinfo=UTC)
    late = LogEntry(stamp, logging.INFO, "root", "x")
    assert to_row(0, late, EXECUTION)["time"] == "09:05:07.999"


def test_ids_count_up_across_both_streams():
    buffer = LogBuffer()
    ids = [
        buffer.add(entry(), EXECUTION)["id"],
        buffer.add(entry(), ACTIVITY)["id"],
        buffer.add(entry(), EXECUTION)["id"],
    ]
    assert ids == [0, 1, 2]


def test_rows_are_both_streams_oldest_first():
    buffer = LogBuffer()
    buffer.add(entry("a"), EXECUTION)
    buffer.add(entry("b"), ACTIVITY)
    buffer.add(entry("c"), EXECUTION)
    assert [(row["id"], row["stream"], row["message"]) for row in buffer.rows()] == [
        (0, "Execution", "a"),
        (1, "Activity", "b"),
        (2, "Execution", "c"),
    ]


def test_a_full_stream_drops_its_oldest_and_leaves_the_other_alone():
    buffer = LogBuffer(capacity=2)
    buffer.add(entry("kept"), ACTIVITY)
    for message in ("one", "two", "three"):
        buffer.add(entry(message), EXECUTION)
    assert [row["message"] for row in buffer.rows()] == ["kept", "two", "three"]
    # A dropped id is gone for good: the next entry does not take it.
    assert buffer.add(entry("four"), EXECUTION)["id"] == 4


def test_the_default_capacity_is_five_thousand_a_stream():
    assert CAPACITY == 5000
    assert LogBuffer().capacity == 5000


def test_pick_returns_the_named_rows_oldest_first_and_skips_a_dropped_id():
    buffer = LogBuffer(capacity=2)
    for message in ("one", "two", "three"):
        buffer.add(entry(message), EXECUTION)
    assert [row["message"] for row in buffer.pick([2, 0, 1, 99])] == ["two", "three"]
    assert buffer.pick([]) == []


def test_save_text_is_a_line_per_row_with_the_traceback_indented():
    rows = [
        to_row(0, entry("New session created", source="Session"), ACTIVITY),
        to_row(
            1, entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
        ),
    ]
    assert save_text(rows) == (
        "2026-09-30 14:00:53.508  INFO      Activity   Session  New session created\n"
        "2026-09-30 14:00:53.508  ERROR     Execution  gui.tools_widget  Save failed\n"
        "    Traceback (most recent call last):\n"
        '      File "gui/tools_widget.py", line 142, in _on_run\n'
        "    PermissionError: share is read-only\n"
    )


def test_save_text_of_nothing_is_empty():
    assert save_text([]) == ""


@pytest.mark.parametrize(
    ("client", "name"),
    [
        ("ACME", "logs_ACME_2026-09-30.txt"),
        (None, "logs_2026-09-30.txt"),
        ("", "logs_2026-09-30.txt"),
        ("A/B C", "logs_A_B_C_2026-09-30.txt"),
    ],
)
def test_the_default_file_name_carries_the_client_and_the_day(client, name):
    assert default_filename(client, date(2026, 9, 30)) == name
````

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_log_buffer.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.log_buffer'`.

- [ ] **Step 3: Write the module**

Create `gui/log_buffer.py`:

````python
"""The entries the Logs page shows, and every word of a row (phase 6 spec section 4).

Two ring buffers, one per stream, of rows: dicts of strings that
gui/web/logs.js draws as they are. No Qt in this module, so the whole rule
set runs without a QApplication.
"""

import logging
import re
from collections import deque
from datetime import date
from heapq import merge
from operator import itemgetter

from gui.log_entry import LogEntry

CAPACITY = 5000
ACTIVITY = "Activity"
EXECUTION = "Execution"


def band(level: int) -> str:
    """The Level segment an entry counts under: Debug is Info, Critical is Error."""
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    return "info"


def to_row(entry_id: int, entry: LogEntry, stream: str) -> dict:
    """What the page draws for one entry (spec section 4.2)."""
    stamp = entry.timestamp
    source = str(entry.source)
    return {
        "id": entry_id,
        "time": f"{stamp:%H:%M:%S}.{stamp.microsecond // 1000:03d}",
        "date": f"{stamp:%Y-%m-%d}",
        "band": band(entry.level),
        "level": logging.getLevelName(entry.level).title(),
        "stream": stream,
        "source": source,
        "short": source.rsplit(".", 1)[-1] or source,
        "message": str(entry.message),
        "traceback": entry.traceback,
    }


class LogBuffer:
    """Each stream's last `capacity` rows. An id is never reused."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self.capacity = capacity
        # One deque per stream: a busy Execution stream cannot push the
        # day's Activity out.
        self._streams: dict[str, deque[dict]] = {
            ACTIVITY: deque(maxlen=capacity),
            EXECUTION: deque(maxlen=capacity),
        }
        self._next_id = 0

    def add(self, entry: LogEntry, stream: str) -> dict:
        """Keep one entry and return its row. A full stream drops its oldest."""
        row = to_row(self._next_id, entry, stream)
        self._next_id += 1
        self._streams[stream].append(row)
        return row

    def rows(self) -> list[dict]:
        """Every row of both streams, oldest first."""
        return list(merge(*self._streams.values(), key=itemgetter("id")))

    def pick(self, ids) -> list[dict]:
        """The rows with these ids, oldest first. A dropped id is skipped."""
        wanted = set(ids)
        return [row for row in self.rows() if row["id"] in wanted]


def save_text(rows) -> str:
    """Save as text: one line per row, then its traceback, indented."""
    lines = []
    for row in rows:
        lines.append(
            f"{row['date']} {row['time']}  {row['level'].upper():<8}  "
            f"{row['stream']:<9}  {row['source']}  {row['message']}"
        )
        lines.extend(f"    {line}" for line in row["traceback"].splitlines())
    return "".join(f"{line}\n" for line in lines)


def default_filename(client_id, day: date) -> str:
    """`logs_ACME_2026-09-30.txt`, or `logs_2026-09-30.txt` with no client."""
    client = re.sub(r"[^A-Za-z0-9_-]", "_", str(client_id or ""))
    middle = f"{client}_" if client else ""
    return f"logs_{middle}{day:%Y-%m-%d}.txt"
````

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_log_buffer.py`

Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/log_buffer.py tests/test_log_buffer.py` and commit. Message subject:
`Logs: LogBuffer keeps the entries and words every row`.

---

### Task 3: `LogsBridge`

**Files:**
- Create: `gui/logs_bridge.py`
- Test: `tests/test_logs_bridge.py`

**Interfaces:**
- Consumes: `CAPACITY` (Task 2); `PageBridge`, `mount_page`, `WEB_DIR` from `gui/web_page.py` (already in
  the repo: `PageBridge` gives `themeCss`, `toastRaised(str, bool)` and `raise_toast(text)`).
- Produces, in `gui/logs_bridge.py`:
  - `PAGE = WEB_DIR / "logs.html"`, `CHANNEL_NAME = "logs"`.
  - `LogsBridge(parent=None, wrap=False, capacity=CAPACITY)` with the Properties `capacity` (int) and
    `wrap` (bool), the method `send(rows)`, the JS-facing signal `entriesAdded` (`QVariantList`), the
    slots `start()`, `saveShown(ids)`, `copyTraceback(entry_id)`, `setWrap(on)` and the Python-facing
    signals `started()`, `saveRequested(list)`, `copyRequested(int)`, `wrapRequested(bool)`.
  - `mount_logs_page(view, wrap=False, capacity=CAPACITY) -> LogsBridge`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_logs_bridge.py`:

````python
"""The Logs page's bridge: every message is its own named member (phase 6 spec 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.log_buffer import CAPACITY
from gui.logs_bridge import LogsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(LogsBridge, PageBridge)


def test_it_tells_the_page_the_capacity_and_whether_wrap_starts_on():
    assert LogsBridge().capacity == CAPACITY
    assert LogsBridge().wrap is False
    bridge = LogsBridge(wrap=True, capacity=3)
    assert bridge.capacity == 3
    assert bridge.wrap is True


def test_send_emits_one_batch_and_nothing_for_an_empty_one():
    bridge = LogsBridge()
    seen = _caught(bridge.entriesAdded)
    bridge.send([{"id": 0}, {"id": 1}])
    bridge.send([])
    assert seen == [([{"id": 0}, {"id": 1}],)]


def test_start_is_a_request_python_hears():
    bridge = LogsBridge()
    seen = _caught(bridge.started)
    bridge.start()
    assert seen == [()]


def test_save_shown_keeps_whole_numbers_only():
    bridge = LogsBridge()
    seen = _caught(bridge.saveRequested)
    bridge.saveShown([0, 2.0, 7, "3", 1.5, None, True, float("nan"), float("inf")])
    assert seen == [([0, 2, 7],)]
    assert all(type(value) is int for value in seen[0][0])


def test_copy_traceback_carries_the_id():
    bridge = LogsBridge()
    seen = _caught(bridge.copyRequested)
    bridge.copyTraceback(12)
    assert seen == [(12,)]


def test_set_wrap_carries_the_choice():
    bridge = LogsBridge()
    seen = _caught(bridge.wrapRequested)
    bridge.setWrap(True)
    bridge.setWrap(False)
    assert seen == [(True,), (False,)]
````

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_bridge.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.logs_bridge'`.

- [ ] **Step 3: Write the bridge**

Create `gui/logs_bridge.py`:

````python
"""The Logs page's bridge (phase 6 spec section 3.2).

Rows go out in batches through one signal, `entriesAdded`; the page keeps
them and filters them itself. The page names an entry by its id. Nothing it
sends is written to disk or used as a path. The catalogue is the spec's
section 3.2: add a member there before adding it here.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.log_buffer import CAPACITY
from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "logs.html"
CHANNEL_NAME = "logs"


def _whole(value) -> bool:
    """A whole number. A JavaScript number can reach a slot as a float."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float(value).is_integer()
    )


class LogsBridge(PageBridge):
    """The Logs page's one channel object."""

    # JS-facing: a batch of rows (gui/log_buffer.py to_row), oldest first.
    entriesAdded = Signal("QVariantList")
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    started = Signal()
    saveRequested = Signal(list)
    copyRequested = Signal(int)
    wrapRequested = Signal(bool)

    def __init__(self, parent=None, wrap: bool = False, capacity: int = CAPACITY):
        super().__init__(parent)
        self._wrap = bool(wrap)
        self._capacity = int(capacity)

    # --- out: Python -> JS -------------------------------------------------

    def _get_capacity(self) -> int:
        return self._capacity

    def _get_wrap(self) -> bool:
        return self._wrap

    capacity = Property(int, _get_capacity, constant=True)
    wrap = Property(bool, _get_wrap, constant=True)

    def send(self, rows) -> None:
        """One batch to the page. An empty batch is not sent."""
        if rows:
            self.entriesAdded.emit(list(rows))

    # --- in: JS -> Python --------------------------------------------------

    @Slot()
    def start(self) -> None:
        self.started.emit()

    @Slot("QVariantList")
    def saveShown(self, ids) -> None:
        self.saveRequested.emit([int(value) for value in ids if _whole(value)])

    @Slot(int)
    def copyTraceback(self, entry_id) -> None:
        self.copyRequested.emit(int(entry_id))

    @Slot(bool)
    def setWrap(self, on) -> None:
        self.wrapRequested.emit(bool(on))


def mount_logs_page(
    view: QWebEngineView, wrap: bool = False, capacity: int = CAPACITY
) -> LogsBridge:
    """Load the Logs page into `view` and return the bridge it talks to."""
    bridge = LogsBridge(view, wrap=wrap, capacity=capacity)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
````

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_bridge.py`

Expected: all pass. `PAGE` names a file that does not exist yet; nothing here reads it.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/logs_bridge.py tests/test_logs_bridge.py` and commit. Message subject:
`Logs: LogsBridge streams rows to the page in batches`.

---

### Task 4: The page

**Files:**
- Create: `gui/web/logs.html`, `gui/web/logs.css`, `gui/web/logs.js`
- Test: `tests/test_logs_page.py`

**Interfaces:**
- Consumes: `mount_logs_page`, `PAGE` (Task 3); `to_row` (Task 2); the kit classes already in
  `gui/web/kit.css`: `.card`, `.segmented`, `.segment`, `.segment-count`, `.input`, `.btn.secondary`,
  `.btn.compact`, `.badge.neutral|warning|danger`, `.state`, `.state-glyph`, `.state-title`,
  `.state-text`, `.toast`, `.toast-close`, `.spacer`, `.mono`, `.glyph`, and its checkbox styling.
- Produces: the page. For tests and for Task 5: `document.documentElement.dataset.bridge === "ready"` once
  the channel is up and `start()` was called; `dataset.renders` counts up after every batch and every
  change the page draws; a row is `#list .row[data-id="<id>"]`; the controls are `#streams`, `#bands`
  (segments carry `data-key`), `#search`, `#count`, `#save`, `#wrap`, `#follow`, `#paused`,
  `#paused-text`, `#jump`, `#empty`, `#empty-title`, `#empty-text`, `#clear-search`, `#show-all`,
  `#toast`, `#toast-text`, `#toast-dismiss`.

How the page works, so the code below reads easily (spec §5):

- `rows` is every row the page holds, oldest first, as `{ data, hay, el, block }`. `el` is built once by
  `rowEl`; `block` is the open traceback's element or `null`. `byId` finds a row by id; `held` counts rows
  per stream for the capacity rule.
- A filter change (`refilter`) sets `hidden` on every row and its block. Nothing is rebuilt.
- `draw()` redraws everything that is not a row: the segments and their counts, the count label, Save's
  disabled state, the empty panel, the footer. If Follow is on, it scrolls the list to its end. It is the
  one place that bumps `dataset.renders`.
- Follow needs no "I scrolled it myself" flag: the scroll handler only compares "is the list at its end"
  with `view.follow`, and a scroll the page made itself always ends at the end.

- [ ] **Step 1: Write the failing test**

Create `tests/test_logs_page.py`:

````python
"""The Logs page, driven through a real Chromium (phase 6 spec section 5).

The page keeps the rows it is sent and owns its view state: every test sends
rows built by to_row() through the bridge and reads the DOM back. 1166x720 is
the page a 1366x768 window gives. Never mark skip.
"""

import json
import logging
from datetime import UTC, datetime

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.log_buffer import ACTIVITY, EXECUTION, to_row
from gui.log_entry import LogEntry
from gui.logs_bridge import PAGE, mount_logs_page
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER
from shared.theme import DARK_THEME, LIGHT_THEME

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_000, tzinfo=UTC)
TRACE = (
    "Traceback (most recent call last):\n"
    '  File "gui/tools_widget.py", line 142, in _on_run\n'
    "    self._sock.sendall(data)\n"
    "PermissionError: share is read-only"
)


def row(
    entry_id,
    message,
    level=logging.INFO,
    stream=EXECUTION,
    source="shopify_tool.core",
    trace="",
):
    return to_row(entry_id, LogEntry(STAMP, level, source, message, trace), stream)


def sample():
    """Six rows: four Execution (one warning, one error with a traceback), two Activity."""
    return [
        row(0, "Scanned order #48254"),
        row(1, "New session created: 2026-09-30_1", stream=ACTIVITY, source="Session"),
        row(
            2, "Stock file is 19 h old", logging.WARNING, source="shopify_tool.analysis"
        ),
        row(
            3,
            "Save failed — PermissionError: share is read-only",
            logging.ERROR,
            source="gui.tools_widget",
            trace=TRACE,
        ),
        row(4, "Generated: picklist", stream=ACTIVITY, source="Report"),
        row(5, "Label printer ready", source="shopify_tool.pdf_processor"),
    ]


def many(n, start=0):
    return [row(start + i, f"Scanned order #{start + i}") for i in range(n)]


def _mount(qtbot, wrap=False, capacity=5000):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_logs_page(view, wrap=wrap, capacity=capacity)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


@pytest.fixture
def page(qtbot):
    return _mount(qtbot)


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _drawn(qtbot, view, before):
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _send(qtbot, view, bridge, rows):
    """Send a batch and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.send(rows)
    _drawn(qtbot, view, before)


def _do(qtbot, view, script):
    """Run a statement in the page and wait for the redraw it causes."""
    before = _renders(qtbot, view)
    _eval(qtbot, view, f"(function () {{ {script}; return true; }})()")
    _drawn(qtbot, view, before)


def _click(qtbot, view, selector):
    _do(qtbot, view, f"document.querySelector({selector!r}).click()")


def _search(qtbot, view, text):
    _do(
        qtbot,
        view,
        "const el = document.querySelector('#search');"
        f" el.value = {json.dumps(text)};"
        " el.dispatchEvent(new Event('input', { bubbles: true }))",
    )


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _hidden(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).hidden")


def _shown_ids(qtbot, view):
    return _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .row'))"
        ".filter((el) => !el.hidden).map((el) => Number(el.dataset.id))",
    )


def _counts(qtbot, view):
    return _json(
        qtbot,
        view,
        "Object.fromEntries(Array.from(document.querySelectorAll('#bands .segment'))"
        ".map((el) => [el.dataset.key, Number(el.querySelector('.segment-count').textContent)]))",
    )


def _at_end(qtbot, view):
    return _eval(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list');"
        " return l.scrollHeight - l.scrollTop - l.clientHeight < 4; })()",
    )


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


STREAM = '#streams [data-key="{}"]'
BAND = '#bands [data-key="{}"]'
ERROR_ROW = '#list .row[data-id="3"]'


# --- the files ----------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="logs.css"')


# --- start --------------------------------------------------------------------


def test_the_page_says_when_it_is_listening(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_logs_page(view)
    started = _caught(bridge.started)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    qtbot.waitUntil(lambda: started == [()])


def test_with_no_entries_the_page_says_so_and_save_is_off(qtbot, page):
    view, _ = page
    assert _hidden(qtbot, view, "#empty") is False
    assert _hidden(qtbot, view, "#list") is True
    assert _text(qtbot, view, "#empty-title") == "No entries yet"
    assert _hidden(qtbot, view, "#empty-text") is True
    assert _hidden(qtbot, view, "#clear-search") is True
    assert _hidden(qtbot, view, "#show-all") is True
    assert _eval(qtbot, view, "document.querySelector('#save').disabled") is True
    assert _text(qtbot, view, "#count") == "0 entries"
    assert _hidden(qtbot, view, "#paused") is True


# --- rows ---------------------------------------------------------------------


def test_rows_are_drawn_oldest_first_with_their_cells(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert _hidden(qtbot, view, "#empty") is True
    assert _text(qtbot, view, "#count") == "6 entries"
    cells = _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({ERROR_ROW + ' > span'!r}))"
        ".map((el) => [el.className, el.textContent, el.title])",
    )
    assert cells == [
        ["cell-chev", "", ""],
        ["cell-time mono", "14:00:53.508", "2026-09-30 14:00:53.508"],
        ["cell-level", "Error", ""],
        ["cell-from", "Execution", ""],
        ["cell-source mono", "tools_widget", "gui.tools_widget"],
        ["cell-message", "Save failed — PermissionError: share is read-only", ""],
    ]


def test_only_warning_and_error_carry_a_tone(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    badges = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .badge')).map((el) => el.className)",
    )
    assert badges == [
        "badge neutral",
        "badge neutral",
        "badge warning",
        "badge danger",
        "badge neutral",
        "badge neutral",
    ]
    assert _eval(
        qtbot,
        view,
        f"getComputedStyle(document.querySelector({ERROR_ROW + ' .cell-message'!r})).color",
    ) == _rgb(LIGHT_THEME.status_danger)
    assert _eval(
        qtbot,
        view,
        "getComputedStyle(document.querySelector('#list .row[data-id=\"2\"] .cell-message')).color",
    ) == _rgb(LIGHT_THEME.text)


def test_only_a_row_with_a_traceback_is_a_button(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#list .row[role=\"button\"]'))"
        ".map((el) => [Number(el.dataset.id), el.tabIndex, el.getAttribute('aria-expanded'),"
        " el.querySelectorAll('.cell-chev svg').length])",
    ) == [[3, 0, "false", 1]]
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#list .cell-chev svg').length")
        == 1
    )


def test_a_message_with_markup_in_it_is_drawn_as_text(qtbot, page):
    view, bridge = page
    hostile = "<img src=x onerror=\"document.title='pwned'\"><b>bold</b>"
    _send(
        qtbot,
        view,
        bridge,
        [row(0, hostile, source="<i>x</i>.<u>y</u>", trace="<s>tb</s>")],
    )
    assert _text(qtbot, view, "#list .cell-message") == hostile
    assert _text(qtbot, view, "#list .cell-source") == "<u>y</u>"
    _click(qtbot, view, '#list .row[data-id="0"]')
    assert _text(qtbot, view, "#list .tb-text") == "<s>tb</s>"
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelectorAll('#list img, #list b, #list u, #list s').length",
        )
        == 0
    )
    assert _eval(qtbot, view, "document.title") == "Logs"


def test_a_batch_sent_twice_is_drawn_once(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _send(qtbot, view, bridge, sample())
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]


def test_the_page_keeps_the_newest_rows_of_each_stream(qtbot):
    view, bridge = _mount(qtbot, capacity=3)
    first = [row(0, "kept", stream=ACTIVITY, source="Session")] + many(5, start=1)
    _send(qtbot, view, bridge, first)
    assert _shown_ids(qtbot, view) == [0, 3, 4, 5]
    assert _text(qtbot, view, "#count") == "4 entries"
    _send(qtbot, view, bridge, many(1, start=6))
    assert _shown_ids(qtbot, view) == [0, 4, 5, 6]


def test_five_thousand_rows_arrive_in_one_batch(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(5000))
    assert _eval(qtbot, view, "document.querySelectorAll('#list .row').length") == 5000
    assert _text(qtbot, view, "#count") == "5000 entries"
    assert _at_end(qtbot, view) is True


# --- source, level and search -------------------------------------------------


def test_the_level_counts_follow_the_source(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    assert _counts(qtbot, view) == {"all": 6, "info": 4, "warning": 1, "error": 1}
    assert (
        _eval(
            qtbot, view, "document.querySelectorAll('#streams .segment-count').length"
        )
        == 0
    )
    _click(qtbot, view, STREAM.format("Activity"))
    assert _counts(qtbot, view) == {"all": 2, "info": 2, "warning": 0, "error": 0}
    assert _shown_ids(qtbot, view) == [1, 4]
    assert _text(qtbot, view, "#count") == "2 of 6 entries"


def test_the_error_count_is_toned_only_above_zero(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    alert = "document.querySelector('#bands [data-key=\"error\"] .segment-count').classList.contains('alert')"
    assert _eval(qtbot, view, alert) is True
    _click(qtbot, view, STREAM.format("Activity"))
    assert _eval(qtbot, view, alert) is False
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#bands .seg-dot').length") == 2
    )


def test_one_source_drops_the_from_column(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    from_cell = "getComputedStyle(document.querySelector('{} .cell-from')).display"
    assert _eval(qtbot, view, from_cell.format(".list-head")) == "block"
    _click(qtbot, view, STREAM.format("Execution"))
    assert _shown_ids(qtbot, view) == [0, 2, 3, 5]
    assert _eval(qtbot, view, from_cell.format(".list-head")) == "none"
    assert _eval(qtbot, view, from_cell.format(ERROR_ROW)) == "none"
    _click(qtbot, view, STREAM.format("all"))
    assert _eval(qtbot, view, from_cell.format(ERROR_ROW)) == "block"


def test_a_level_is_one_band_not_a_floor(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, BAND.format("warning"))
    assert _shown_ids(qtbot, view) == [2]
    assert _text(qtbot, view, "#count") == "1 of 6 entries"
    _click(qtbot, view, BAND.format("info"))
    assert _shown_ids(qtbot, view) == [0, 1, 4, 5]
    checked = "Array.from(document.querySelectorAll('#bands .segment')).map((el) => [el.getAttribute('aria-checked'), el.tabIndex])"
    assert _json(qtbot, view, checked) == [
        ["false", -1],
        ["true", 0],
        ["false", -1],
        ["false", -1],
    ]


def test_search_reads_the_message_and_the_source_but_not_the_traceback(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _search(qtbot, view, "  PICKLIST ")
    assert _shown_ids(qtbot, view) == [4]
    _search(qtbot, view, "gui.tools")
    assert _shown_ids(qtbot, view) == [3]
    assert _counts(qtbot, view) == {"all": 1, "info": 0, "warning": 0, "error": 1}
    _search(qtbot, view, "sendall")
    assert _shown_ids(qtbot, view) == []
    # The search text is plain text, never a pattern.
    _search(qtbot, view, ".*")
    assert _shown_ids(qtbot, view) == []
    _search(qtbot, view, "#48254")
    assert _shown_ids(qtbot, view) == [0]


def test_the_arrow_keys_move_along_a_control_and_choose(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    press = (
        "const el = document.querySelector('#bands [aria-checked=\"true\"]'); el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', {{ key: '{}', bubbles: true }}))"
    )
    _do(qtbot, view, press.format("ArrowLeft"))  # wraps from All to Error
    assert _shown_ids(qtbot, view) == [3]
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "error"
    _do(qtbot, view, press.format("ArrowRight"))
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "all"


# --- empty states -------------------------------------------------------------


def test_a_search_that_finds_nothing_says_where_it_looked(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _search(qtbot, view, "zebra")
    assert _text(qtbot, view, "#empty-title") == "No entries match"
    assert _text(qtbot, view, "#empty-text") == (
        "Nothing contains “zebra” in its message or source."
    )
    assert _hidden(qtbot, view, "#clear-search") is False
    assert _hidden(qtbot, view, "#show-all") is True
    assert _eval(qtbot, view, "document.querySelector('#save').disabled") is True

    _click(qtbot, view, BAND.format("error"))
    _click(qtbot, view, STREAM.format("Execution"))
    assert _text(qtbot, view, "#empty-text") == (
        "Nothing in Error Execution contains “zebra” in its message or source."
    )
    assert _hidden(qtbot, view, "#show-all") is False

    _click(qtbot, view, "#clear-search")
    assert _shown_ids(qtbot, view) == [3]
    assert _eval(qtbot, view, "document.querySelector('#search').value") == ""


def test_a_filter_with_nothing_in_it_offers_to_show_everything(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, STREAM.format("Activity"))
    _click(qtbot, view, BAND.format("warning"))
    assert _text(qtbot, view, "#empty-title") == "No entries match"
    assert _text(qtbot, view, "#empty-text") == "No Warning Activity entries yet."
    assert _hidden(qtbot, view, "#clear-search") is True
    _click(qtbot, view, "#show-all")
    assert _shown_ids(qtbot, view) == [0, 1, 2, 3, 4, 5]
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#streams [aria-checked=\"true\"]').dataset.key",
        )
        == "all"
    )
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#bands [aria-checked=\"true\"]').dataset.key",
        )
        == "all"
    )


# --- traceback ----------------------------------------------------------------


def test_a_click_opens_the_traceback_under_its_row_and_another_closes_it(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    assert (
        _eval(
            qtbot,
            view,
            f"document.querySelector({ERROR_ROW!r}).nextElementSibling.className",
        )
        == "tb"
    )
    assert (
        _eval(qtbot, view, f"document.querySelector({ERROR_ROW!r}).className")
        == "row grid error has-tb open"
    )
    assert (
        _eval(
            qtbot,
            view,
            f"document.querySelector({ERROR_ROW!r}).getAttribute('aria-expanded')",
        )
        == "true"
    )
    assert (
        _eval(qtbot, view, "document.querySelector('#list .tb-text').textContent")
        == TRACE
    )
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelector('#list .tb-head').children).map((el) => el.textContent)",
    ) == ["Traceback", "gui.tools_widget", "", "Copy"]
    _click(qtbot, view, ERROR_ROW)
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 0
    assert (
        _eval(qtbot, view, f"document.querySelector({ERROR_ROW!r}).className")
        == "row grid error has-tb"
    )


def test_enter_opens_a_focused_row_and_a_plain_row_ignores_a_click(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _do(
        qtbot,
        view,
        f"const el = document.querySelector({ERROR_ROW!r}); el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))",
    )
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1
    before = _renders(qtbot, view)
    _eval(
        qtbot, view, "document.querySelector('#list .row[data-id=\"0\"]').click(); true"
    )
    qtbot.wait(100)
    assert _renders(qtbot, view) == before
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1


def test_a_click_that_ends_a_selection_does_not_toggle(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _eval(
        qtbot,
        view,
        f"window.getSelection().selectAllChildren(document.querySelector({ERROR_ROW + ' .cell-message'!r}));"
        f" document.querySelector({ERROR_ROW!r}).click(); true",
    )
    qtbot.wait(100)
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 0


def test_copy_names_the_entry_to_python_and_leaves_the_row_open(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    copied = _caught(bridge.copyRequested)
    _eval(qtbot, view, "document.querySelector('#list [data-copy]').click(); true")
    qtbot.waitUntil(lambda: copied == [(3,)])
    assert _eval(qtbot, view, "document.querySelectorAll('#list .tb').length") == 1


def test_a_filter_that_hides_a_row_hides_its_open_traceback(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    _click(qtbot, view, ERROR_ROW)
    _click(qtbot, view, BAND.format("info"))
    assert _hidden(qtbot, view, "#list .tb") is True
    _click(qtbot, view, BAND.format("all"))
    assert _hidden(qtbot, view, "#list .tb") is False


# --- follow -------------------------------------------------------------------


def _scroll_up(qtbot, view):
    _eval(qtbot, view, "document.querySelector('#list').scrollTop = 0; true")
    _until_js(qtbot, view, "document.querySelector('#follow').checked === false")


def test_follow_keeps_the_list_at_its_end(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    assert _at_end(qtbot, view) is True
    _send(qtbot, view, bridge, many(50, start=200))
    assert _at_end(qtbot, view) is True
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _hidden(qtbot, view, "#paused") is True


def test_scrolling_up_pauses_and_counts_what_arrives_below(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    assert _hidden(qtbot, view, "#paused") is False
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"

    _send(qtbot, view, bridge, many(1, start=200))
    assert _text(qtbot, view, "#paused-text") == "1 new entry below"
    _send(qtbot, view, bridge, many(2, start=201))
    assert _text(qtbot, view, "#paused-text") == "3 new entries below"
    assert _eval(qtbot, view, "document.querySelector('#list').scrollTop") == 0

    _click(qtbot, view, "#jump")
    assert _at_end(qtbot, view) is True
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _hidden(qtbot, view, "#paused") is True


def test_the_count_below_is_of_the_entries_the_filter_shows(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _click(qtbot, view, BAND.format("info"))
    _scroll_up(qtbot, view)
    _send(
        qtbot,
        view,
        bridge,
        [
            row(200, "shown"),
            row(201, "not shown", logging.ERROR),
            row(202, "shown too"),
        ],
    )
    assert _text(qtbot, view, "#paused-text") == "2 new entries below"


def test_scrolling_back_to_the_end_follows_again(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    _send(qtbot, view, bridge, many(1, start=200))
    _eval(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list'); l.scrollTop = l.scrollHeight; return true; })()",
    )
    _until_js(qtbot, view, "document.querySelector('#follow').checked === true")
    assert _hidden(qtbot, view, "#paused") is True
    _scroll_up(qtbot, view)
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"


def test_a_filter_change_follows_again(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _scroll_up(qtbot, view)
    _click(qtbot, view, STREAM.format("Execution"))
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
    assert _at_end(qtbot, view) is True


def test_unticking_follow_stops_it_and_ticking_it_jumps(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    _click(qtbot, view, "#follow")
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is False
    _eval(qtbot, view, "document.querySelector('#list').scrollTop = 0; true")
    _send(qtbot, view, bridge, many(1, start=200))
    assert _eval(qtbot, view, "document.querySelector('#list').scrollTop") == 0
    _click(qtbot, view, "#follow")
    assert _at_end(qtbot, view) is True


def test_opening_a_row_stops_follow(qtbot, page):
    view, bridge = page
    _send(
        qtbot,
        view,
        bridge,
        many(200) + [row(200, "Save failed", logging.ERROR, trace=TRACE)],
    )
    _click(qtbot, view, '#list .row[data-id="200"]')
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is False
    assert _text(qtbot, view, "#paused-text") == "Paused while scrolled up"


# --- wrap ---------------------------------------------------------------------


def test_wrap_starts_as_this_pc_left_it_and_tells_python_when_it_changes(qtbot):
    view, bridge = _mount(qtbot, wrap=True)
    _send(qtbot, view, bridge, sample())
    assert _eval(qtbot, view, "document.querySelector('#wrap').checked") is True
    assert (
        _eval(qtbot, view, "document.querySelector('#list').classList.contains('wrap')")
        is True
    )
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('#list .cell-message')).whiteSpace",
        )
        == "pre-wrap"
    )
    wraps = _caught(bridge.wrapRequested)
    _click(qtbot, view, "#wrap")
    qtbot.waitUntil(lambda: wraps == [(False,)])
    assert (
        _eval(qtbot, view, "document.querySelector('#list').classList.contains('wrap')")
        is False
    )
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('#list .cell-message')).whiteSpace",
        )
        == "nowrap"
    )


def test_a_row_is_twenty_six_pixels_and_a_wrapped_long_one_is_taller(qtbot, page):
    view, bridge = page
    _send(
        qtbot,
        view,
        bridge,
        [row(0, "word " * 200), row(1, "first line\nsecond line"), row(2, "short")],
    )
    heights = (
        "Array.from(document.querySelectorAll('#list .row'))"
        ".map((el) => el.getBoundingClientRect().height)"
    )
    assert _json(qtbot, view, heights) == [26, 26, 26]
    _click(qtbot, view, "#wrap")
    long, two_lines, short = _json(qtbot, view, heights)
    assert long > two_lines > short == 26


# --- save ---------------------------------------------------------------------


def test_save_sends_the_ids_of_the_rows_shown(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    saves = _caught(bridge.saveRequested)
    _click(qtbot, view, STREAM.format("Execution"))
    _eval(qtbot, view, "document.querySelector('#save').click(); true")
    qtbot.waitUntil(lambda: saves == [([0, 2, 3, 5],)])
    assert _text(qtbot, view, "#save") == "Save as text"
    assert _eval(qtbot, view, "document.querySelector('#save').title") == (
        "Save shown entries as text  Ctrl+S"
    )


def test_ctrl_s_saves_and_does_nothing_when_no_row_is_shown(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    saves = _caught(bridge.saveRequested)
    press = (
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " { key: 's', ctrlKey: true, bubbles: true, cancelable: true })); true"
    )
    _eval(qtbot, view, press)
    qtbot.waitUntil(lambda: saves == [([0, 1, 2, 3, 4, 5],)])
    _search(qtbot, view, "zebra")
    _eval(qtbot, view, press)
    qtbot.wait(200)
    assert len(saves) == 1


# --- toast and theme ----------------------------------------------------------


def test_a_toast_is_drawn_in_the_page_and_can_be_dismissed(qtbot, page):
    view, bridge = page
    assert _hidden(qtbot, view, "#toast") is True
    bridge.raise_toast("Traceback copied")
    _until_js(qtbot, view, "document.querySelector('#toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "Traceback copied"
    _eval(qtbot, view, "document.querySelector('#toast-dismiss').click(); true")
    assert _hidden(qtbot, view, "#toast") is True


def test_a_theme_switch_repaints_the_rows(qtbot, page):
    view, bridge = page
    _send(qtbot, view, bridge, sample())
    get_theme_manager().set_theme(
        "dark"
    )  # conftest's reset_theme_and_density restores light
    _until_js(
        qtbot,
        view,
        f"getComputedStyle(document.body).backgroundColor === '{_rgb(DARK_THEME.surface_sunken)}'",
    )
    assert _eval(
        qtbot,
        view,
        f"getComputedStyle(document.querySelector({ERROR_ROW + ' .cell-message'!r})).color",
    ) == _rgb(DARK_THEME.status_danger)


def test_a_smaller_window_keeps_a_following_list_at_its_end(qtbot, page):
    """The Logs tab is usually hidden while entries arrive, and sized when shown."""
    view, bridge = page
    _send(qtbot, view, bridge, many(200))
    view.resize(1166, 420)
    _until_js(qtbot, view, "window.innerHeight < 500")
    _until_js(
        qtbot,
        view,
        "(function () { const l = document.querySelector('#list');"
        " return l.scrollHeight - l.scrollTop - l.clientHeight < 4; })()",
    )
    assert _eval(qtbot, view, "document.querySelector('#follow').checked") is True
````

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_page.py -x`

Expected: the first test fails with `FileNotFoundError` on `gui/web/logs.html`.

- [ ] **Step 3: The document**

Create `gui/web/logs.html`:

````html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Logs</title>
<!-- gui/web_page.py writes theme_css_vars() over the marker before the page
     loads, then logs.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="logs.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="logs.js" defer></script>
</head>
<body>
<main id="logs">
  <section id="card" class="card">
    <div class="toolbar">
      <div id="streams" class="segmented" role="radiogroup" aria-label="Source"></div>
      <div id="bands" class="segmented" role="radiogroup" aria-label="Level"></div>
      <label id="search-box" class="input search">
        <input id="search" type="search" placeholder="Search messages and sources" aria-label="Search messages and sources">
      </label>
      <span class="spacer"></span>
      <span id="count" class="count"></span>
      <button id="save" class="btn secondary" type="button" title="Save shown entries as text  Ctrl+S"></button>
    </div>
    <div class="list-head grid">
      <span class="cell-chev"></span>
      <span>Time</span>
      <span>Level</span>
      <span class="cell-from">From</span>
      <span>Source</span>
      <span>Message</span>
    </div>
    <div id="list" class="list"></div>
    <div id="empty" class="state" hidden>
      <p id="empty-title" class="state-title"></p>
      <p id="empty-text" class="state-text"></p>
      <div class="empty-actions">
        <button id="clear-search" class="btn secondary" type="button">Clear search</button>
        <button id="show-all" class="btn secondary" type="button">Show all levels and sources</button>
      </div>
    </div>
    <div class="footer">
      <label class="tick"><input id="wrap" type="checkbox">Wrap long messages</label>
      <label class="tick"><input id="follow" type="checkbox" checked>Follow the newest entry</label>
      <span id="paused" class="paused" hidden>
        <span id="paused-text"></span>
        <span>·</span>
        <button id="jump" class="link" type="button">Jump to newest</button>
      </span>
      <span class="spacer"></span>
      <span>Click an Error with ▸ to see its traceback</span>
    </div>
  </section>
</main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toast-text"></span>
  <button id="toast-dismiss" class="toast-close" type="button" aria-label="Dismiss"></button>
</div>
</body>
</html>
````

- [ ] **Step 4: The stylesheet**

Create `gui/web/logs.css`:

````css
/* The Logs page (phase 6 spec section 5). Layout, and what only this page
   draws: the row grid, the traceback block and the footer. Every colour is a
   token from theme_css_vars(). A divider is --border-subtle, the edge of a
   control is --border (ADR 0018). */

#logs {
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  display: flex;
  flex-direction: column;
  padding: 16px 24px 20px;
}
#logs > .card {
  flex: 1;
  min-width: 780px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* --- toolbar ------------------------------------------------------------- */

.toolbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.toolbar .segmented { align-self: center; flex: none; }
.seg-dot { flex: none; width: 6px; height: 6px; border-radius: 50%; }
.seg-dot.warning { background: var(--status-warning); }
.seg-dot.error { background: var(--status-danger-dot); }
.segment-count.alert { color: var(--status-danger); }
.search { flex: 1 1 200px; min-width: 150px; max-width: 320px; }
.count {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}

/* --- the row grid: the header row and every row share it ----------------- */

.grid {
  display: grid;
  grid-template-columns: 24px 112px 84px 84px 170px minmax(0, 1fr);
  align-items: center;
}
.one-stream .grid { grid-template-columns: 24px 112px 84px 170px minmax(0, 1fr); }
.one-stream .cell-from { display: none; }
.grid > * { min-width: 0; padding: 0 8px; }
.grid > .cell-chev {
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--text-secondary);
}

.list-head {
  flex: none;
  height: 30px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}

/* --- rows ---------------------------------------------------------------- */

.list { flex: 1; min-height: 0; overflow: auto; }
.row {
  height: calc(var(--row-height) - 2px);
  border-bottom: 1px solid var(--border-subtle);
}
.row:hover, .row.open { background: var(--surface-raised); }
.row.open { border-bottom-color: transparent; }
.row.has-tb { cursor: pointer; }
.row.has-tb:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.cell-time, .cell-from { color: var(--text-secondary); white-space: nowrap; }
.cell-from { font-size: var(--type-caption-size); }
.cell-level { display: flex; }
/* The line box is taller than the text, so overflow: hidden does not cut an
   underscore off the mono face. */
.cell-source, .cell-message {
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row.error .cell-message { color: var(--status-danger); }

.wrap .row {
  height: auto;
  min-height: calc(var(--row-height) - 2px);
  align-items: start;
  padding: 3px 0 2px;
}
.wrap .cell-message { white-space: pre-wrap; word-break: break-word; }

/* --- traceback: indented to the Source column ---------------------------- */

.tb {
  padding: 0 12px 10px 312px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.one-stream .tb { padding-left: 228px; }
.tb-box {
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface-sunken);
}
.tb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 6px 0 12px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.tb-title { font-weight: 700; color: var(--text); }
.tb-text {
  margin: 0;
  padding: 8px 12px 10px;
  font-size: var(--type-caption-size);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

/* --- empty state --------------------------------------------------------- */

#empty { flex: 1; min-height: 0; }
#empty .state-title { font-size: var(--type-heading-size); }
.empty-actions { display: flex; gap: 8px; }

/* --- footer -------------------------------------------------------------- */

.footer {
  flex: none;
  display: flex;
  align-items: center;
  gap: 20px;
  height: 36px;
  padding: 0 12px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.tick {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.paused { display: flex; align-items: center; gap: 6px; }
.link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font-weight: 700;
  text-decoration: underline;
  cursor: pointer;
}
.link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
````

- [ ] **Step 5: The script**

Create `gui/web/logs.js`:

````javascript
// The Logs page (phase 6 spec section 5). Python words every row
// (gui/log_buffer.py) and sends rows in batches as bridge.entriesAdded. This
// file keeps every row it was sent and owns the whole view state: the source,
// the level, the search text, wrap, follow and which rows are open. It
// reports what the operator asks for through the bridge's named slots, always
// by entry id.
//
// A row is built once and stays in the list; a filter change sets `hidden`
// on rows and rebuilds nothing. A log message can hold text from a CSV, so
// nothing from a row goes through innerHTML: textContent only.
//
// ponytail: no row windowing. Measured with 10,000 rows in QtWebEngine: a
// filter change 20 ms, a batch of 200 entries 26 ms. Window the rows, as
// results.js does, if the capacity ever grows tenfold.
"use strict";

const TOAST_MS = 4000;
// How far from its end the list may sit and still count as at its end.
const AT_END_PX = 4;

// Lucide glyphs, each as one path.
const GLYPH = {
  search: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3",
  searchX: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  right: "m9 18 6-6-6-6",
  down: "m6 9 6 6 6-6",
  x: "M18 6 6 18M6 6l12 12",
};

const STREAMS = [
  { key: "all", label: "All" },
  { key: "Activity", label: "Activity" },
  { key: "Execution", label: "Execution" },
];
const BANDS = [
  { key: "all", label: "All" },
  { key: "info", label: "Info" },
  { key: "warning", label: "Warning" },
  { key: "error", label: "Error" },
];
// A band's badge tone in the kit.
const TONE = { error: "danger", warning: "warning", info: "neutral" };

const els = {};
const page = { bridge: null, capacity: 5000, lastId: -1, renders: 0, toastTimer: null };
const view = { stream: "all", band: "all", typed: "", query: "", wrap: false, follow: true, unseen: 0 };
// Every row the page holds, oldest first: { data, hay, el, block }. `block`
// is the open traceback's element, or null.
const rows = [];
const byId = new Map();
const held = { Activity: 0, Execution: 0 };

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function entries(n) {
  return n === 1 ? "1 entry" : `${n} entries`;
}

// --- building a row ------------------------------------------------------------

function cell(cls, text, title) {
  const span = document.createElement("span");
  span.className = cls;
  span.textContent = text;
  if (title) span.title = title;
  return span;
}

function rowEl(data) {
  const el = document.createElement("div");
  el.className = `row grid ${data.band}`;
  el.dataset.id = String(data.id);
  const chevron = cell("cell-chev", "");
  if (data.traceback) {
    el.classList.add("has-tb");
    el.setAttribute("role", "button");
    el.setAttribute("aria-expanded", "false");
    el.tabIndex = 0;
    chevron.innerHTML = svg(GLYPH.right, "glyph");
  }
  const level = cell("cell-level", "");
  level.appendChild(cell(`badge ${TONE[data.band] || "neutral"}`, data.level));
  el.append(
    chevron,
    cell("cell-time mono", data.time, `${data.date} ${data.time}`),
    level,
    cell("cell-from", data.stream),
    cell("cell-source mono", data.short, data.source),
    cell("cell-message", data.message),
  );
  return el;
}

function blockEl(data) {
  const block = document.createElement("div");
  block.className = "tb";
  const box = document.createElement("div");
  box.className = "tb-box";
  const head = document.createElement("div");
  head.className = "tb-head";
  const copy = document.createElement("button");
  copy.className = "btn secondary compact";
  copy.type = "button";
  copy.textContent = "Copy";
  copy.dataset.copy = String(data.id);
  head.append(cell("tb-title", "Traceback"), cell("mono", data.source), cell("spacer", ""), copy);
  const text = document.createElement("pre");
  text.className = "tb-text mono";
  text.textContent = data.traceback;
  box.append(head, text);
  block.appendChild(box);
  return block;
}

// --- what the view state selects -----------------------------------------------

// Passes the source and the search: what the Level counts count.
function inScope(row) {
  return (
    (view.stream === "all" || row.data.stream === view.stream) &&
    (!view.query || row.hay.includes(view.query))
  );
}

function shown(row) {
  return inScope(row) && (view.band === "all" || row.data.band === view.band);
}

function setHidden(row, hidden) {
  row.el.hidden = hidden;
  if (row.block) row.block.hidden = hidden;
}

function counts() {
  const n = { all: 0, info: 0, warning: 0, error: 0 };
  for (const row of rows) {
    if (!inScope(row)) continue;
    n.all += 1;
    if (row.data.band in n) n[row.data.band] += 1;
  }
  return n;
}

// --- drawing everything but the rows -------------------------------------------

function atEnd() {
  const list = els.list;
  return list.scrollHeight - list.scrollTop - list.clientHeight < AT_END_PX;
}

function drawSegments(group, chosen, n) {
  for (const button of group.children) {
    const on = button.dataset.key === chosen;
    button.setAttribute("aria-checked", String(on));
    button.tabIndex = on ? 0 : -1;
    const count = button.querySelector(".segment-count");
    if (!count) continue;
    count.textContent = String(n[button.dataset.key]);
    count.classList.toggle("alert", button.dataset.key === "error" && n.error > 0);
  }
}

function drawEmpty(visible) {
  const empty = visible === 0;
  els.list.hidden = empty;
  els.empty.hidden = !empty;
  if (!empty) return;
  const scope = [
    view.band === "all" ? "" : BANDS.find((band) => band.key === view.band).label,
    view.stream === "all" ? "" : view.stream,
  ].filter(Boolean).join(" ");
  let title = "No entries match";
  let text = "";
  if (view.query) {
    text = `Nothing${scope ? ` in ${scope}` : ""} contains “${view.typed}” in its message or source.`;
  } else if (scope) {
    text = `No ${scope} entries yet.`;
  } else {
    title = "No entries yet";
  }
  els.emptyTitle.textContent = title;
  els.emptyText.textContent = text;
  els.emptyText.hidden = !text;
  els.clearSearch.hidden = !view.query;
  els.showAll.hidden = !scope;
}

function draw() {
  const n = counts();
  const visible = n[view.band];
  drawSegments(els.streams, view.stream, n);
  drawSegments(els.bands, view.band, n);
  els.count.textContent =
    visible === rows.length ? entries(rows.length) : `${visible} of ${entries(rows.length)}`;
  els.save.disabled = visible === 0;
  els.card.classList.toggle("one-stream", view.stream !== "all");
  els.list.classList.toggle("wrap", view.wrap);
  drawEmpty(visible);
  els.wrap.checked = view.wrap;
  els.follow.checked = view.follow;
  els.paused.hidden = view.follow || visible === 0;
  els.pausedText.textContent = view.unseen
    ? `${view.unseen} new ${view.unseen === 1 ? "entry" : "entries"} below`
    : "Paused while scrolled up";
  if (view.follow) els.list.scrollTop = els.list.scrollHeight;
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// --- rows arriving -------------------------------------------------------------

// Each stream keeps its newest `capacity` rows, as Python's buffer does.
function evict() {
  for (const stream of Object.keys(held)) {
    let at = 0;
    while (held[stream] > page.capacity) {
      while (rows[at].data.stream !== stream) at += 1;
      const row = rows.splice(at, 1)[0];
      row.el.remove();
      if (row.block) row.block.remove();
      byId.delete(row.data.id);
      held[stream] -= 1;
    }
  }
}

function onEntries(batch) {
  const fragment = document.createDocumentFragment();
  let unseen = 0;
  for (const data of batch) {
    if (data.id <= page.lastId) continue; // start() was answered twice
    page.lastId = data.id;
    const row = {
      data,
      hay: `${data.message} ${data.source}`.toLowerCase(),
      el: rowEl(data),
      block: null,
    };
    if (shown(row)) unseen += 1;
    else row.el.hidden = true;
    rows.push(row);
    byId.set(data.id, row);
    held[data.stream] = (held[data.stream] || 0) + 1;
    fragment.appendChild(row.el);
  }
  els.list.appendChild(fragment);
  evict();
  if (!view.follow) view.unseen += unseen;
  draw();
}

// --- input ---------------------------------------------------------------------

function setFollow(on) {
  view.follow = on;
  view.unseen = 0;
  draw();
}

// Source, Level or the search changed: every row is asked again.
function refilter() {
  for (const row of rows) setHidden(row, !shown(row));
  setFollow(true);
}

function choose(kind, key) {
  view[kind] = key;
  refilter();
}

function setSearch(text) {
  els.search.value = text;
  view.typed = text.trim();
  view.query = view.typed.toLowerCase();
  refilter();
}

function onSegmentClick(event, kind) {
  const button = event.target.closest("[data-key]");
  if (button) choose(kind, button.dataset.key);
}

function onSegmentKey(event, kind, options, group) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const index = options.findIndex((option) => option.key === view[kind]);
  const step = event.key === "ArrowLeft" ? -1 : 1;
  const next = options[(index + step + options.length) % options.length];
  event.preventDefault();
  choose(kind, next.key);
  group.querySelector(`[data-key="${next.key}"]`).focus();
}

function toggle(row) {
  const open = row.block === null;
  if (open) {
    row.block = blockEl(row.data);
    row.el.after(row.block);
  } else {
    row.block.remove();
    row.block = null;
  }
  row.el.classList.toggle("open", open);
  row.el.setAttribute("aria-expanded", String(open));
  row.el.firstChild.innerHTML = svg(open ? GLYPH.down : GLYPH.right, "glyph");
  view.follow = false;
  draw();
}

function onListClick(event) {
  const copy = event.target.closest("[data-copy]");
  if (copy) {
    if (page.bridge) page.bridge.copyTraceback(Number(copy.dataset.copy));
    return;
  }
  const el = event.target.closest(".row.has-tb");
  // A click that ends a drag over the text is a selection, not a toggle.
  if (!el || String(window.getSelection())) return;
  toggle(byId.get(Number(el.dataset.id)));
}

function onListKey(event) {
  if (event.key !== "Enter" && event.key !== " ") return;
  if (!event.target.classList.contains("has-tb")) return;
  event.preventDefault();
  toggle(byId.get(Number(event.target.dataset.id)));
}

function onScroll() {
  const end = atEnd();
  if (end === view.follow) return;
  view.follow = end;
  if (end) view.unseen = 0;
  draw();
}

function save() {
  if (!page.bridge) return;
  const ids = rows.filter((row) => !row.el.hidden).map((row) => row.data.id);
  if (ids.length) page.bridge.saveShown(ids);
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text) {
  els.toastText.textContent = text;
  els.toast.hidden = false;
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(dismissToast, TOAST_MS);
}

function dismissToast() {
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = null;
  els.toast.hidden = true;
}

// --- boot ----------------------------------------------------------------------

function segments(options, counted) {
  return options.map((option) => {
    const dot = counted && option.key in TONE && option.key !== "info"
      ? `<span class="seg-dot ${option.key}"></span>`
      : "";
    const count = counted ? `<span class="segment-count">0</span>` : "";
    return `<button class="segment" type="button" role="radio" aria-checked="false" tabindex="-1" data-key="${option.key}">${dot}${option.label}${count}</button>`;
  }).join("");
}

function bind() {
  const ids = {
    card: "card", streams: "streams", bands: "bands", searchBox: "search-box", search: "search",
    count: "count", save: "save", list: "list", empty: "empty", emptyTitle: "empty-title",
    emptyText: "empty-text", clearSearch: "clear-search", showAll: "show-all", wrap: "wrap",
    follow: "follow", paused: "paused", pausedText: "paused-text", jump: "jump",
    themeVars: "theme-vars", toast: "toast", toastText: "toast-text", toastDismiss: "toast-dismiss",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  // The fixed parts of the page: the two controls and the glyphs.
  els.streams.innerHTML = segments(STREAMS, false);
  els.bands.innerHTML = segments(BANDS, true);
  els.searchBox.insertAdjacentHTML("afterbegin", svg(GLYPH.search, "glyph"));
  els.save.innerHTML = `${svg(GLYPH.download, "glyph")}Save as text`;
  els.empty.insertAdjacentHTML("afterbegin", svg(GLYPH.searchX, "state-glyph"));
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");

  els.streams.addEventListener("click", (event) => onSegmentClick(event, "stream"));
  els.bands.addEventListener("click", (event) => onSegmentClick(event, "band"));
  els.streams.addEventListener("keydown", (event) => onSegmentKey(event, "stream", STREAMS, els.streams));
  els.bands.addEventListener("keydown", (event) => onSegmentKey(event, "band", BANDS, els.bands));
  els.search.addEventListener("input", () => setSearch(els.search.value));
  els.save.addEventListener("click", save);
  els.list.addEventListener("click", onListClick);
  els.list.addEventListener("keydown", onListKey);
  els.list.addEventListener("scroll", onScroll);
  els.clearSearch.addEventListener("click", () => setSearch(""));
  els.showAll.addEventListener("click", () => {
    view.stream = "all";
    view.band = "all";
    refilter();
  });
  els.wrap.addEventListener("change", () => {
    view.wrap = els.wrap.checked;
    if (page.bridge) page.bridge.setWrap(view.wrap);
    draw();
  });
  els.follow.addEventListener("change", () => setFollow(els.follow.checked));
  els.jump.addEventListener("click", () => setFollow(true));
  els.toastDismiss.addEventListener("click", dismissToast);
  // A window made smaller leaves the list short of its end, with no scroll event.
  window.addEventListener("resize", () => {
    if (view.follow) els.list.scrollTop = els.list.scrollHeight;
  });
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
    event.preventDefault();
    save();
  });
}

bind();
draw();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.logs;
  page.bridge = bridge;
  page.capacity = bridge.capacity;
  view.wrap = bridge.wrap;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.toastRaised.connect((text) => raiseToast(text));
  bridge.entriesAdded.connect(onEntries);
  draw();
  bridge.start();
  window.logsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
````

- [ ] **Step 6: Run the page's tests and the style guard**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_page.py tests/test_style_literals_guard.py tests/test_web_kit.py`

Expected: all pass. If `test_a_row_is_twenty_six_pixels_and_a_wrapped_long_one_is_taller` fails on the
last line, check `.wrap .row` in `logs.css`: its padding is `3px 0 2px`, which with the 1px line under the
row makes a one-line wrapped row 26px.

- [ ] **Step 7: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/web/logs.html gui/web/logs.css gui/web/logs.js tests/test_logs_page.py` and commit. Message
subject: `Logs: the page, drawn to the mockup on the kit`.

---

### Task 5: `LogsWidget`

**Files:**
- Create: `gui/logs_widget.py`
- Test: `tests/test_logs_widget.py`

**Interfaces:**
- Consumes: `LogBuffer`, `default_filename`, `save_text` (Task 2); `mount_logs_page` (Task 3); the page
  (Task 4); `show_error(parent, title, text)` from `gui/components` (already in the repo).
- Produces, in `gui/logs_widget.py`:
  - `LogsWidget(main_window, parent=None)` with `.view` (the `QWebEngineView`), `.bridge` (the
    `LogsBridge`), `.buffer` (the `LogBuffer`) and `.append(entry: LogEntry, stream: str) -> None`.
  - `BATCH_MS = 100`, `WRAP_KEY = "logs/wrap"`, and `_settings()`, a module function that tests replace.
  - The module looks up `mount_logs_page` and `show_error` by their module-level names, so a test can
    replace either with `monkeypatch.setattr(logs_widget, ...)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_logs_widget.py`:

````python
"""The Logs screen's widget: the buffer, the batches, save and copy (phase 6 spec 6).

The page itself is tested in test_logs_page.py. Here the widget is tested
against a bare bridge with no page loaded, so nothing calls start() but the
test. The last test loads the real page once, end to end.
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog
from test_results_bridge import _eval, _until_js

from gui import logs_widget
from gui.log_buffer import ACTIVITY, EXECUTION
from gui.log_entry import LogEntry
from gui.logs_bridge import LogsBridge
from gui.logs_widget import BATCH_MS, LogsWidget

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_000, tzinfo=UTC)
TRACE = "Traceback (most recent call last):\nPermissionError: share is read-only"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path, monkeypatch):
    """This PC's settings, in a file under tmp_path."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(
        logs_widget, "_settings", lambda: QSettings(path, QSettings.IniFormat)
    )
    return logs_widget._settings


@pytest.fixture
def window():
    """What LogsWidget reads from the main window."""
    return SimpleNamespace(current_client_id="ACME")


@pytest.fixture
def bare(monkeypatch):
    """No page: the bridge alone, so only the test calls start()."""
    monkeypatch.setattr(
        logs_widget,
        "mount_logs_page",
        lambda view, wrap=False: LogsBridge(view, wrap=wrap),
    )


@pytest.fixture
def logs(qtbot, window, store, bare):
    widget = LogsWidget(window)
    qtbot.addWidget(widget)
    return widget


def entry(message, level=logging.INFO, source="shopify_tool.core", trace=""):
    return LogEntry(STAMP, level, source, message, trace)


def _batches(bridge):
    seen = []
    bridge.entriesAdded.connect(
        lambda rows: seen.append([row["message"] for row in rows])
    )
    return seen


def _toasts(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, _flag: seen.append(text))
    return seen


def _save_to(monkeypatch, path):
    asked = []

    def dialog(parent, title, name, filters):
        asked.append((title, name, filters))
        return str(path) if path else "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", dialog)
    return asked


# --- batches ------------------------------------------------------------------


def test_it_hosts_one_web_view_with_no_margins(logs):
    assert logs.findChildren(QWebEngineView) == [logs.view]
    margins = logs.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )


def test_entries_before_the_page_starts_leave_as_one_backlog_batch(qtbot, logs):
    seen = _batches(logs.bridge)
    logs.append(entry("one"), EXECUTION)
    logs.append(entry("two"), ACTIVITY)
    qtbot.wait(BATCH_MS * 2)
    assert seen == []
    logs.bridge.start()
    assert seen == [["one", "two"]]


def test_entries_after_the_start_leave_together_on_the_timer(qtbot, logs):
    logs.bridge.start()
    seen = _batches(logs.bridge)
    for message in ("one", "two", "three"):
        logs.append(entry(message), EXECUTION)
    assert seen == []
    qtbot.waitUntil(lambda: seen == [["one", "two", "three"]], timeout=2000)
    logs.append(entry("four"), EXECUTION)
    qtbot.waitUntil(lambda: seen == [["one", "two", "three"], ["four"]], timeout=2000)


def test_a_second_start_resends_the_whole_backlog(qtbot, logs):
    logs.append(entry("one"), EXECUTION)
    logs.bridge.start()
    logs.append(entry("two"), EXECUTION)
    seen = _batches(logs.bridge)
    logs.bridge.start()
    assert seen == [["one", "two"]]
    qtbot.wait(BATCH_MS * 2)
    assert seen == [["one", "two"]]  # nothing was left pending


def test_append_does_not_log(logs, caplog):
    """The root logger's handler calls append(): a log call here would recurse."""
    logs.bridge.start()
    with caplog.at_level(logging.DEBUG):
        logs.append(entry("one"), EXECUTION)
        logs._flush()
    assert caplog.records == []


# --- save ---------------------------------------------------------------------


def test_save_writes_the_picked_rows_and_toasts_the_file_name(
    logs, tmp_path, monkeypatch
):
    logs.append(entry("New session created", source="Session"), ACTIVITY)
    logs.append(
        entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
    )
    logs.append(entry("not shown"), EXECUTION)
    target = tmp_path / "out.txt"
    asked = _save_to(monkeypatch, target)
    toasts = _toasts(logs.bridge)

    logs.bridge.saveShown([0, 1])

    assert asked == [
        (
            "Save log as text",
            f"logs_ACME_{datetime.now().astimezone():%Y-%m-%d}.txt",
            "Text files (*.txt);;All files (*)",
        )
    ]
    assert target.read_text(encoding="utf-8") == (
        "2026-09-30 14:00:53.508  INFO      Activity   Session  New session created\n"
        "2026-09-30 14:00:53.508  ERROR     Execution  gui.tools_widget  Save failed\n"
        "    Traceback (most recent call last):\n"
        "    PermissionError: share is read-only\n"
    )
    assert toasts == ["Saved 2 entries to out.txt"]


def test_saving_one_entry_says_one_entry(logs, tmp_path, monkeypatch):
    logs.append(entry("only"), EXECUTION)
    _save_to(monkeypatch, tmp_path / "one.txt")
    toasts = _toasts(logs.bridge)
    logs.bridge.saveShown([0])
    assert toasts == ["Saved 1 entry to one.txt"]


def test_a_cancelled_dialog_writes_nothing(logs, tmp_path, monkeypatch):
    logs.append(entry("only"), EXECUTION)
    _save_to(monkeypatch, None)
    toasts = _toasts(logs.bridge)
    logs.bridge.saveShown([0])
    assert toasts == []
    assert list(tmp_path.glob("*.txt")) == []


def test_save_with_no_row_left_opens_no_dialog(logs, monkeypatch):
    asked = _save_to(monkeypatch, None)
    logs.bridge.saveShown([5, 6])
    assert asked == []


def test_a_file_that_cannot_be_written_shows_the_dialog_and_no_toast(
    logs, tmp_path, monkeypatch
):
    logs.append(entry("only"), EXECUTION)
    target = tmp_path / "missing_folder" / "out.txt"
    _save_to(monkeypatch, target)
    shown = []
    monkeypatch.setattr(
        logs_widget,
        "show_error",
        lambda parent, title, text: shown.append((title, text)),
    )
    toasts = _toasts(logs.bridge)

    logs.bridge.saveShown([0])

    assert shown == [
        (
            "The log wasn't saved",
            f"{target} couldn't be written. Choose another folder and save again.",
        )
    ]
    assert toasts == []


def test_with_no_client_the_file_name_has_only_the_day(
    logs, window, tmp_path, monkeypatch
):
    window.current_client_id = None
    logs.append(entry("only"), EXECUTION)
    asked = _save_to(monkeypatch, tmp_path / "x.txt")
    logs.bridge.saveShown([0])
    assert asked[0][1] == f"logs_{datetime.now().astimezone():%Y-%m-%d}.txt"


# --- copy and wrap ------------------------------------------------------------


def test_copy_puts_the_traceback_on_the_clipboard(logs):
    logs.append(entry("Save failed", logging.ERROR, trace=TRACE), EXECUTION)
    QGuiApplication.clipboard().setText("before")
    toasts = _toasts(logs.bridge)
    logs.bridge.copyTraceback(0)
    assert QGuiApplication.clipboard().text() == TRACE
    assert toasts == ["Traceback copied"]


def test_copy_does_nothing_for_a_row_without_a_traceback_or_an_unknown_id(logs):
    logs.append(entry("plain"), EXECUTION)
    QGuiApplication.clipboard().setText("before")
    toasts = _toasts(logs.bridge)
    logs.bridge.copyTraceback(0)
    logs.bridge.copyTraceback(99)
    assert QGuiApplication.clipboard().text() == "before"
    assert toasts == []


def test_wrap_is_read_from_this_pc_and_written_back(qtbot, window, store, bare):
    first = LogsWidget(window)
    qtbot.addWidget(first)
    assert first.bridge.wrap is False
    first.bridge.setWrap(True)
    assert store().value("logs/wrap", False, type=bool) is True

    second = LogsWidget(window)
    qtbot.addWidget(second)
    assert second.bridge.wrap is True


# --- end to end ---------------------------------------------------------------


def test_the_real_page_draws_the_backlog_and_then_each_batch(qtbot, window, store):
    widget = LogsWidget(window)
    qtbot.addWidget(widget)
    widget.append(entry("before the page was ready"), EXECUTION)
    widget.resize(1166, 720)
    widget.show()
    view = widget.view
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    _until_js(qtbot, view, "document.querySelectorAll('#list .row').length === 1")

    widget.append(entry("after"), ACTIVITY)
    _until_js(qtbot, view, "document.querySelectorAll('#list .row').length === 2")
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#list .row:last-child .cell-message').textContent",
        )
        == "after"
    )


def test_text_outside_ascii_is_saved_as_utf8(logs, tmp_path, monkeypatch):
    logs.append(entry("Oberländer-Schwarz — bitte zweimal klingeln ✓"), EXECUTION)
    target = tmp_path / "utf8.txt"
    _save_to(monkeypatch, target)
    logs.bridge.saveShown([0])
    assert (
        target.read_bytes()
        .decode("utf-8")
        .endswith("Oberländer-Schwarz — bitte zweimal klingeln ✓\n")
    )
````

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_widget.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.logs_widget'`.

- [ ] **Step 3: Write the widget**

Create `gui/logs_widget.py`:

````python
"""The Logs screen (phase 6 spec section 6): one web view over a LogBuffer.

Everything drawn on this screen is in gui/web/logs.*. This widget keeps the
entries, sends the page its rows in batches, and does the two things the page
cannot: write a file and set the clipboard.

append() and _flush() must never log. The root logger's handler calls
append() for every record, on the GUI thread, so a log call inside either
would call itself without end.
"""

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.log_buffer import LogBuffer, default_filename, save_text
from gui.logs_bridge import mount_logs_page

logger = logging.getLogger(__name__)

# How long a row waits for others before the batch leaves (spec section 3).
BATCH_MS = 100
WRAP_KEY = "logs/wrap"


def _settings() -> QSettings:
    """This PC's store, the same pair theme_manager uses. A function so tests
    can point it at an INI file under tmp_path."""
    return QSettings("ShopifyFulfillmentTool", "FulfillmentApp")


def _entries(n: int) -> str:
    return "1 entry" if n == 1 else f"{n} entries"


class LogsWidget(QWidget):
    """The Logs screen's widget: one web view and the buffer behind it."""

    def __init__(self, main_window, parent=None):
        """main_window: read for current_client_id, which names the saved file."""
        super().__init__(parent)
        self.mw = main_window
        self.buffer = LogBuffer()
        self._pending: list[dict] = []
        self._started = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        wrap = bool(_settings().value(WRAP_KEY, False, type=bool))
        self.bridge = mount_logs_page(self.view, wrap=wrap)
        layout.addWidget(self.view, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(BATCH_MS)
        self._timer.timeout.connect(self._flush)

        self.bridge.started.connect(self._on_started)
        self.bridge.saveRequested.connect(self._save)
        self.bridge.copyRequested.connect(self._copy)
        self.bridge.wrapRequested.connect(self._remember_wrap)

    # --- entries -------------------------------------------------------------

    def append(self, entry, stream) -> None:
        """Keep one entry. It reaches the page with the next batch."""
        row = self.buffer.add(entry, stream)
        if not self._started:
            return  # the backlog carries it when the page starts
        self._pending.append(row)
        if not self._timer.isActive():
            self._timer.start()

    def _flush(self) -> None:
        batch, self._pending = self._pending, []
        self.bridge.send(batch)

    def _on_started(self) -> None:
        """The page is listening: everything held so far, as one batch."""
        self._started = True
        self._pending = []
        self.bridge.send(self.buffer.rows())

    # --- what the page asks for ----------------------------------------------

    def _remember_wrap(self, on: bool) -> None:
        _settings().setValue(WRAP_KEY, bool(on))

    def _save(self, ids) -> None:
        rows = self.buffer.pick(ids)
        if not rows:
            return
        client = getattr(self.mw, "current_client_id", None)
        name = default_filename(client, datetime.now().astimezone().date())
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save log as text", name, "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(save_text(rows), encoding="utf-8")
        except OSError as error:
            # Operators save to UNC shares that go away mid-write. An
            # unhandled OSError out of a Qt slot takes the app down rather
            # than telling anyone which file failed.
            logger.warning("Could not save log to %s: %s", path, error)
            show_error(
                self,
                "The log wasn't saved",
                f"{path} couldn't be written. Choose another folder and save again.",
            )
            return
        self.bridge.raise_toast(f"Saved {_entries(len(rows))} to {Path(path).name}")

    def _copy(self, entry_id: int) -> None:
        rows = self.buffer.pick([entry_id])
        if not rows or not rows[0]["traceback"]:
            return
        QGuiApplication.clipboard().setText(rows[0]["traceback"])
        self.bridge.raise_toast("Traceback copied")
````

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_widget.py`

Expected: all pass, the last one against the real page.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/logs_widget.py tests/test_logs_widget.py` and commit. Message subject:
`Logs: LogsWidget hosts the page, batches rows, saves and copies`.

---

### Task 6: The shell, and the Qt viewer goes

**Files:**
- Modify: `gui/ui_manager.py`, `gui/main_window_pyside.py`, `.github/workflows/build_release.yml`
- Delete: `gui/log_viewer.py`, `gui/log_model.py`, `gui/log_filter.py`, `gui/log_follow.py`,
  `tests/test_log_viewer.py`, `tests/test_log_viewer_theme.py`, `tests/test_log_model.py`,
  `tests/test_log_filter.py`, `tests/test_log_follow.py`
- Test: `tests/test_logs_destination.py` (rewritten), `tests/test_shell.py`, `tests/test_toast_router.py`

**Interfaces:**
- Consumes: `LogsWidget` (Task 5); `ACTIVITY`, `EXECUTION` (Task 2).
- Produces: `main_window.logs_widget` (tab 3's widget); `main_window.log_viewer` is gone;
  `MainWindow.web_toast` answers on tab 3; `UIManager._apply_page_inset` and `_WEB_PAGES` are gone and the
  page area's layout has no margins. `MainWindow.log_activity(op_type, desc)` keeps its signature.

- [ ] **Step 1: Rewrite the destination test**

Replace the whole file `tests/test_logs_destination.py`:

````python
import logging

import pytest

from gui import logs_widget
from gui.logs_bridge import LogsBridge
from gui.logs_widget import LogsWidget
from gui.main_window_pyside import MainWindow
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
    for gone in (
        "update_statistics_tab",
        "_clear_statistics_view",
        "_on_sku_search_changed",
    ):
        assert not hasattr(MainWindow, gone), f"{gone} should be deleted"


def test_the_qt_log_viewer_is_gone():
    """Phase 6 spec section 7: the page replaced the widget, its model, proxy and follow state."""
    import importlib.util

    for gone in ("gui.log_viewer", "gui.log_model", "gui.log_filter", "gui.log_follow"):
        assert importlib.util.find_spec(gone) is None, f"{gone} should be deleted"
    assert not hasattr(UIManager, "_apply_page_inset")


class _JustTheLogging:
    """A MainWindow reduced to the methods that route into the Logs widget.

    Building a real MainWindow drags in the profile manager, the server path
    and a full UI; these methods only ever touch `self.logs_widget`, so
    binding them to a stub tests the routing and nothing else.
    """

    log_activity = MainWindow.log_activity
    _on_log_entry = MainWindow._on_log_entry
    setup_logging = MainWindow.setup_logging

    def __init__(self, widget):
        self.logs_widget = widget


@pytest.fixture
def logs(qtbot, monkeypatch):
    """A LogsWidget with no page loaded: these tests read its buffer."""
    monkeypatch.setattr(
        logs_widget,
        "mount_logs_page",
        lambda view, wrap=False: LogsBridge(view, wrap=wrap),
    )
    widget = LogsWidget(None)
    qtbot.addWidget(widget)
    return widget


def test_log_activity_appends_to_the_activity_stream(logs):
    _JustTheLogging(logs).log_activity("Report", "Generated: picklist")

    rows = logs.buffer.rows()
    assert [(row["stream"], row["source"], row["message"]) for row in rows] == [
        ("Activity", "Report", "Generated: picklist")
    ]


def test_a_root_logger_record_reaches_the_execution_stream(logs):
    """The whole wiring, end to end: logging call -> handler -> buffer.

    test_log_handler covers emit() in isolation and this file covers
    log_activity, but nothing proved the signal is actually connected -- the
    one edge where a rename would fail silently, because a log line that
    never arrives looks exactly like a quiet program.
    """
    window = _JustTheLogging(logs)
    window.setup_logging()
    try:
        try:
            raise FileNotFoundError("inventory.csv")
        except FileNotFoundError:
            logging.getLogger("shopify_tool.engine").exception("stock file vanished")

        row = logs.buffer.rows()[-1]
        assert row["stream"] == "Execution"
        assert row["level"] == "Error"
        assert row["source"] == "shopify_tool.engine"
        assert (
            row["message"] == "stock file vanished — FileNotFoundError: inventory.csv"
        )
        assert row["traceback"].startswith("Traceback (most recent call last):")
        assert row["traceback"].endswith("FileNotFoundError: inventory.csv")
    finally:
        logging.getLogger().removeHandler(window.log_handler)
````

- [ ] **Step 2: The shell's tests**

In `tests/test_shell.py`, 5 edits, in this order.

**Edit 1 of 5** (near line 182). Find exactly:

````
    """1366x768 minus the 200px sidebar and the 48px command bar; no status bar.

    A Qt page keeps the 5px inset it was laid out against (phase 1 spec section
    5.1); Setup is a web page now and has none.
    """
    from PySide6.QtWidgets import QStatusBar
````

Replace with:

````
    """1366x768 minus the 200px sidebar and the 48px command bar; no status bar.

    Every page is a web page and has no inset (phase 6 spec section 6.3).
    """
    from PySide6.QtWidgets import QStatusBar
````

**Edit 2 of 5** (near line 194). Find exactly:

````
    assert main_window.command_bar.height() == 48
    assert main_window.findChild(QStatusBar) is None
    assert main_window.main_tabs.width() == 1166  # Setup: a web page, no inset
    main_window.main_tabs.setCurrentIndex(3)  # Logs: a Qt page
    QApplication.processEvents()
    assert main_window.main_tabs.width() == 1156


````

Replace with:

````
    assert main_window.command_bar.height() == 48
    assert main_window.findChild(QStatusBar) is None
    assert main_window.main_tabs.width() == 1166  # Setup
    main_window.main_tabs.setCurrentIndex(3)  # Logs
    QApplication.processEvents()
    assert main_window.main_tabs.width() == 1166


````

**Edit 3 of 5** (near line 461). Find exactly:

````

def test_a_web_page_takes_the_page_area_to_its_edges(main_window):
    """Phase 2 spec section 5.1: a Qt page keeps its 5px inset, a web page has
    none, or a white ring would show around the grey page."""
    main_window.resize(1366, 768)
    main_window.main_tabs.setCurrentIndex(1)
````

Replace with:

````

def test_a_web_page_takes_the_page_area_to_its_edges(main_window):
    """Phase 6 spec section 6.3: every page is a web page, so the page area
    has no inset on any tab, or a white ring would show around the grey page."""
    main_window.resize(1366, 768)
    main_window.main_tabs.setCurrentIndex(1)
````

**Edit 4 of 5** (near line 480). Find exactly:

````
    main_window.main_tabs.setCurrentIndex(3)
    QApplication.processEvents()
    assert main_window.page_area.layout().contentsMargins().left() == 5
    assert main_window.main_tabs.width() == 1156


````

Replace with:

````
    main_window.main_tabs.setCurrentIndex(3)
    QApplication.processEvents()
    assert main_window.page_area.layout().contentsMargins().left() == 0
    assert main_window.main_tabs.width() == 1166


````

**Edit 5 of 5** (near line 581). Find exactly:

````
    main_window.tools_widget.bridge.openRecent()
    assert calls == ["new", "recent"]
````

Replace with:

````
    main_window.tools_widget.bridge.openRecent()
    assert calls == ["new", "recent"]


def test_logs_is_one_web_view(main_window):
    """Phase 6 spec section 6.3: tab 3 holds the Logs page and nothing else."""
    from PySide6.QtWebEngineWidgets import QWebEngineView

    from gui.logs_widget import LogsWidget

    tab = main_window.main_tabs.widget(3)
    assert isinstance(tab, LogsWidget)
    assert tab is main_window.logs_widget
    assert not hasattr(main_window, "log_viewer")
    assert tab.findChildren(QWebEngineView) == [tab.view]
    margins = tab.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)


def test_what_the_window_logs_reaches_the_logs_buffer(main_window):
    main_window.log_activity("Report", "Generated: picklist")
    row = main_window.logs_widget.buffer.rows()[-1]
    assert (row["stream"], row["source"], row["message"]) == (
        "Activity",
        "Report",
        "Generated: picklist",
    )
````

In `tests/test_toast_router.py`, 1 edit, in this order.

**Edit 1 of 1** (near line 84). Find exactly:

````


def test_on_a_qt_page_the_qt_toast_shows(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    seen = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Saved")

    assert shown is Toast.for_window(main_window)
    assert not shown.isHidden()
    assert seen == []


````

Replace with:

````


def test_on_logs_the_logs_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    seen = _raised(main_window.logs_widget.bridge)
    other = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Settings saved")

    assert seen == [("Settings saved", False)]
    assert other == []
    assert shown is None
    assert Toast.for_window(main_window) is None


````

- [ ] **Step 3: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_destination.py tests/test_shell.py tests/test_toast_router.py`

Expected: failures. `test_the_qt_log_viewer_is_gone` fails (the four modules exist); the two routing tests
in `test_logs_destination.py` fail with `AttributeError` on `logs_widget`; `test_logs_is_one_web_view`,
`test_what_the_window_logs_reaches_the_logs_buffer` and `test_on_logs_the_logs_page_draws_it` fail with
`AttributeError: 'MainWindow' object has no attribute 'logs_widget'`; the two page-size tests fail with
`1156 != 1166`.

- [ ] **Step 4: The shell**

In `gui/ui_manager.py`, 6 edits, in this order.

**Edit 1 of 6** (near line 28). Find exactly:

````

# The sidebar's collapsed state is this PC's, like the theme -- same QSettings
# pair theme_manager and log_viewer use. A function so tests can point it at
# an INI file under tmp_path.
_COLLAPSED_KEY = "shell/sidebar_collapsed"

# The tabs drawn on the web tier. A web page paints the sunken plane to its
# own edges, so the page area's 5px inset would show as a white ring around
# it. Each phase that moves a screen adds its index (phase 2 spec section 5.1).
_WEB_PAGES = frozenset({0, 1, 2, 4})


````

Replace with:

````

# The sidebar's collapsed state is this PC's, like the theme -- same QSettings
# pair theme_manager and logs_widget use. A function so tests can point it at
# an INI file under tmp_path.
_COLLAPSED_KEY = "shell/sidebar_collapsed"


````

**Edit 2 of 6** (near line 164). Find exactly:

````
        right_layout.addWidget(self._create_command_bar())

        # The pages keep the 5px inset they were laid out against (phase 1 §5.1).
        page_area = QWidget()
        self.mw.page_area = page_area
        page_layout = QVBoxLayout(page_area)
        page_layout.setSpacing(5)
        page_layout.setContentsMargins(5, 5, 5, 5)

        # 9.25: a failure waits here, under the command bar, until dismissed.
````

Replace with:

````
        right_layout.addWidget(self._create_command_bar())

        # Every page is a web page and paints the sunken plane to its own
        # edges, so the page area has no inset (phase 6 spec section 6.3).
        page_area = QWidget()
        self.mw.page_area = page_area
        page_layout = QVBoxLayout(page_area)
        page_layout.setSpacing(5)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # 9.25: a failure waits here, under the command bar, until dismissed.
````

**Edit 3 of 6** (near line 180). Find exactly:

````
        self._create_tabs()
        page_layout.addWidget(self.mw.main_tabs, 1)
        # Setup is a web page and tab 0 is current from the start, so no
        # currentChanged has told the page area yet.
        self._apply_page_inset(self.mw.main_tabs.currentIndex())

        right_layout.addWidget(page_area, 1)
````

Replace with:

````
        self._create_tabs()
        page_layout.addWidget(self.mw.main_tabs, 1)

        right_layout.addWidget(page_area, 1)
````

**Edit 4 of 6** (near line 321). Find exactly:

````
        self._setup_tab_shortcuts()

        self.mw.main_tabs.currentChanged.connect(self._apply_page_inset)
        # The session chip on every screen but Setup and Tools, whose page
        # heads show it; the analysis age on Results.
````

Replace with:

````
        self._setup_tab_shortcuts()

        # The session chip on every screen but Setup and Tools, whose page
        # heads show it; the analysis age on Results.
````

**Edit 5 of 6** (near line 371). Find exactly:

````
    def _refresh_overflow(self) -> None:
        self._open_folder_item.setEnabled(bool(getattr(self.mw, "session_path", None)))

    def _apply_page_inset(self, index: int) -> None:
        """No inset around a web page, the old 5px around a Qt one."""
        inset = 0 if index in _WEB_PAGES else 5
        self.mw.page_area.layout().setContentsMargins(inset, inset, inset, inset)

    def _open_connection_settings(self):
````

Replace with:

````
    def _refresh_overflow(self) -> None:
        self._open_folder_item.setEnabled(bool(getattr(self.mw, "session_path", None)))

    def _open_connection_settings(self):
````

**Edit 6 of 6** (near line 667). Find exactly:

````

    def _create_tab4_logs(self):
        """Create Tab 4: Logs -- one viewer, two sources, no sub-tabs.

        Statistics is deleted (9.20) and the two log widgets are one widget
        (9.21), so there is nothing left to tab between.
        """
        from gui.log_viewer import LogViewer

        self.mw.log_viewer = LogViewer(self.mw)
        return self.mw.log_viewer

    def _open_session_folder(self):
````

Replace with:

````

    def _create_tab4_logs(self):
        """Logs: one QWebEngineView, no Qt inside (phase 6 spec).

        LogsWidget hosts the view and keeps the entries; everything drawn on
        this screen is in gui/web/logs.*.
        """
        from gui.logs_widget import LogsWidget

        self.mw.logs_widget = LogsWidget(self.mw)
        return self.mw.logs_widget

    def _open_session_folder(self):
````

In `gui/main_window_pyside.py`, 4 edits, in this order.

**Edit 1 of 4** (near line 19). Find exactly:

````
from gui.components.commandbar import BarState
from gui.file_handler import FileHandler
from gui.log_entry import LogEntry
from gui.log_handler import QtLogHandler
from gui.log_model import LogBufferModel
from gui.results_bridge import normalize_column_settings
from gui.selection_helper import SelectionHelper
````

Replace with:

````
from gui.components.commandbar import BarState
from gui.file_handler import FileHandler
from gui.log_buffer import ACTIVITY, EXECUTION
from gui.log_entry import LogEntry
from gui.log_handler import QtLogHandler
from gui.results_bridge import normalize_column_settings
from gui.selection_helper import SelectionHelper
````

**Edit 2 of 4** (near line 161). Find exactly:

````
        if index == 2:
            bridge = getattr(getattr(self, "session_browser", None), "bridge", None)
        elif index == 4:
            bridge = getattr(getattr(self, "tools_widget", None), "bridge", None)
````

Replace with:

````
        if index == 2:
            bridge = getattr(getattr(self, "session_browser", None), "bridge", None)
        elif index == 3:
            bridge = getattr(getattr(self, "logs_widget", None), "bridge", None)
        elif index == 4:
            bridge = getattr(getattr(self, "tools_widget", None), "bridge", None)
````

**Edit 3 of 4** (near line 292). Find exactly:

````
    def _on_log_entry(self, entry):
        """A record from the root logger reaches the Execution source."""
        self.log_viewer.append(entry, LogBufferModel.EXECUTION)

    def connect_signals(self):
````

Replace with:

````
    def _on_log_entry(self, entry):
        """A record from the root logger reaches the Execution source."""
        self.logs_widget.append(entry, EXECUTION)

    def connect_signals(self):
````

**Edit 4 of 4** (near line 1088). Find exactly:

````
            desc (str): A description of the activity.
        """
        self.log_viewer.append(
            LogEntry.activity(op_type, desc), LogBufferModel.ACTIVITY
        )

    def closeEvent(self, event):
````

Replace with:

````
            desc (str): A description of the activity.
        """
        self.logs_widget.append(LogEntry.activity(op_type, desc), ACTIVITY)

    def closeEvent(self, event):
````

- [ ] **Step 5: Delete the Qt viewer and its tests**

Run, as one command:

```bash
/usr/bin/git rm gui/log_viewer.py gui/log_model.py gui/log_filter.py gui/log_follow.py tests/test_log_viewer.py tests/test_log_viewer_theme.py tests/test_log_model.py tests/test_log_filter.py tests/test_log_follow.py
```

`gui/status_edge_delegate.py` stays: deleting it is out of scope (spec §12).

- [ ] **Step 6: The bundle check**

In `.github/workflows/build_release.yml`, 1 edit, in this order.

**Edit 1 of 1** (near line 152). Find exactly:

````
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html", "setup.html", "browse.html", "tools.html", "pikepdf", "fulfilment-tool.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name."
````

Replace with:

````
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html", "setup.html", "browse.html", "tools.html", "logs.html", "pikepdf", "fulfilment-tool.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name."
````

- [ ] **Step 7: Run the tests, and look for leftovers**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_logs_destination.py tests/test_shell.py tests/test_toast_router.py tests/test_logs_widget.py tests/test_logs_page.py tests/test_log_handler.py tests/test_log_entry.py`

Expected: all pass.

Then search with the Grep tool for `log_viewer|LogViewer|LogBufferModel|log_model|log_filter|log_follow|_apply_page_inset|_WEB_PAGES`
in `gui`, `tests`, `shared` and `scripts`. Expected hits, and no others: the names inside
`test_the_qt_log_viewer_is_gone` in `tests/test_logs_destination.py`, and the one
`not hasattr(main_window, "log_viewer")` in `tests/test_shell.py`.

- [ ] **Step 8: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/ui_manager.py gui/main_window_pyside.py .github/workflows/build_release.yml tests/test_logs_destination.py tests/test_shell.py tests/test_toast_router.py`
(the deletions are already staged by `git rm`). Check with `/usr/bin/git status --short` that nothing else
is staged. Commit. Message subject: `Logs: tab 3 is the web page; the Qt log viewer is deleted`.

---

### Task 7: Docs, the visual check, the gate

**Files:**
- Modify: `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `docs/design/ui-refresh/roadmap.md`
- Create: five PNGs under `docs/design/ui-refresh/renders/phase6/`

**Interfaces:**
- Consumes: everything above.
- Produces: the docs spec §11 lists, and the renders the PR carries.

- [ ] **Step 1: The glossary**

In `CONTEXT.md`, 2 edits, in this order.

**Edit 1 of 2** (near line 16). Find exactly:

````

**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Analysis Results, Session Setup, Browse and Tools today; ADR 0016 lets each other
screen move in its own task. See ADR 0001 for why Results moved first.

**Renderer** — either tier, when the point is that there are two of them and
````

Replace with:

````

**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Every screen today: Session Setup, Analysis Results, Browse, Logs and Tools. The
Client settings window is still Qt; ADR 0016 lets it move in its own tasks. See
ADR 0001 for why Results moved first.

**Renderer** — either tier, when the point is that there are two of them and
````

**Edit 2 of 2** (near line 261). Find exactly:

````
folder of three unrelated pages.

**Log entry** — one line in the viewer: time, level, source, message. The same
four fields whichever stream produced it.

**Source** — which stream a log entry came from. **Activity** is what the
operator did (`log_activity`, ten call sites); **Execution** is what the
program logged (the root logger, through `QtLogHandler`). One viewer, one
switch, never two widgets.

**Follow-tail** — the viewer scrolling itself to the newest entry. On only
while the user is already at the bottom; it stops the moment they scroll up and
counts what arrived since.

**Connection state** — whether this PC can currently reach the file server.
````

Replace with:

````
folder of three unrelated pages.

**Log entry** — one line on the Logs page: time, level, source, message, and
the traceback when the record carried an exception. The same fields whichever
stream produced it.

**Source** — which stream a log entry came from. **Activity** is what the
operator did (`log_activity`); **Execution** is what the program logged (the
root logger, through `QtLogHandler`). On the page the Source control picks the
stream and the From column names it. The Source column shows where in the
stream the entry came from: the logger's name, or the kind of action.

**Level band** — the Level segment a log entry counts under: Info, Warning or
Error. A band, not a floor: Warning shows warnings only. Debug falls in Info
and Critical in Error.

**Follow-tail** — the Logs page scrolling itself to the newest entry, which is
at the bottom. On only while the operator is already at the end; it stops the
moment they scroll up or open a traceback, and counts what arrived since.

**Connection state** — whether this PC can currently reach the file server.
````

- [ ] **Step 2: ADR 0016**

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, 1 edit, in this order.

**Edit 1 of 1** (near line 50). Find exactly:

````
  measurement. Its page owns only which menu and which Label setup fold is open; Python owns every fact
  about a tool.

## What would reverse it
````

Replace with:

````
  measurement. Its page owns only which menu and which Label setup fold is open; Python owns every fact
  about a tool.
- Logs moved in phase 6 (2026-10-02) with the fifth bridge, `LogsBridge`, and a fifth view, on the same
  measurement. No Qt page is left in the shell. Its page keeps the rows it is sent and owns its whole view
  state (source, level, search, wrap, follow, open rows); Python keeps the entries, words every row and
  streams rows in batches, never one message a line.

## What would reverse it
````

- [ ] **Step 3: The roadmap**

In `docs/design/ui-refresh/roadmap.md`, 1 edit, in this order.

**Edit 1 of 1** (near line 135). Find exactly:

````
names the folder and offers Open folder. A bad mapping CSV is flagged under its own field.

### 6. Logs to the web tier

Two single-select segmented controls, Source (All, Activity, Execution) and Level (All, Info, Warning,
````

Replace with:

````
names the folder and offers Open folder. A bad mapping CSV is flagged under its own field.

### 6. Logs to the web tier (built in run 50)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase6-logs-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase6-logs-web.md`.

Built as listed below, with these differences. The counts are on Level only, as the mockup draws them. Save
as text opens a save dialog first, then the toast names the file. The count of entries below is of the
entries the filter shows. Any row with a traceback expands, whatever its level. The chevron swaps its glyph
and does not turn. The session chip stays in the bar on Logs, as on Browse: the mockup has no page head. No
Qt page is left, so the page area's inset rule is deleted.

Two single-select segmented controls, Source (All, Activity, Execution) and Level (All, Info, Warning,
````

- [ ] **Step 4: Render the page and look at it (required, CLAUDE.md)**

Write this throwaway script to your job's tmp dir as `render_logs.py` (never into the repo):

````python
"""Throwaway: render the Logs page in the mockup's four states. Never commit."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from gui.log_buffer import ACTIVITY, EXECUTION, to_row
from gui.log_entry import LogEntry
from gui.logs_bridge import mount_logs_page
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

TRACE = (
    "Traceback (most recent call last):\n"
    '  File "C:\\FulfilmentTool\\gui\\tools_widget.py", line 142, in _on_run\n'
    "    self.reference.run(folder)\n"
    '  File "C:\\FulfilmentTool\\shopify_tool\\pdf_processor.py", line 58, in process\n'
    '    raise PermissionError(f"{target} is read-only")\n'
    "PermissionError: \\\\fs01\\fulfilment\\ACME\\2026-09-30_1\\reference_labels is read-only"
)
LONG = (
    "Address line 2 exceeds 35 characters for order #48231, label will truncate it: "
    "'Hinterhaus, 3. Obergeschoss links, bei Familie Oberländer-Schwarz, bitte zweimal klingeln'"
)
POOL = [
    (EXECUTION, logging.INFO, "shopify_tool.core", "Scanned order #{n} (3 items)", ""),
    (ACTIVITY, logging.INFO, "Session", "Loaded session: 2026-09-30_1", ""),
    (EXECUTION, logging.INFO, "shopify_tool.analysis", "Reserved stock for #{n}", ""),
    (EXECUTION, logging.INFO, "gui.main_window_pyside", "Main window refreshed, 188 orders", ""),
    (ACTIVITY, logging.INFO, "Report", "Generated: picklist_DHL", ""),
    (EXECUTION, logging.WARNING, "shopify_tool.analysis", "SKU SRM-30ML short by 2, order #{n} blocked", ""),
    (EXECUTION, logging.INFO, "shopify_tool.pdf_processor", "Stamped page {n}", ""),
    (ACTIVITY, logging.INFO, "Data Edit", "Marked order #{n} fulfillable.", ""),
    (EXECUTION, logging.WARNING, "shopify_tool.core", LONG, ""),
    (
        EXECUTION,
        logging.ERROR,
        "gui.tools_widget",
        "Reference labels failed — PermissionError: reference_labels is read-only",
        TRACE,
    ),
]


def rows(n):
    start = datetime(2026, 9, 30, 13, 46, 0)
    out = []
    for i in range(n):
        stream, level, source, message, trace = POOL[(i * 7 + i // 11) % len(POOL)]
        if level == logging.ERROR and i % 3:
            stream, level, source, message, trace = POOL[0]
        stamp = start + timedelta(seconds=i * 4.317)
        out.append(to_row(i, LogEntry(stamp, level, source, message.format(n=48180 + i), trace), stream))
    return out


def settle(ms=400):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def run(view, script):
    view.page().runJavaScript(script)
    settle()


STATES = {
    "200-entries": "",
    "errors": "document.querySelector('#bands [data-key=\"error\"]').click();",
    "no-match": (
        "document.querySelector('#bands [data-key=\"all\"]').click();"
        " const s = document.querySelector('#search'); s.value = 'zebra-printer';"
        " s.dispatchEvent(new Event('input', { bubbles: true }));"
    ),
    "traceback": (
        "const s = document.querySelector('#search'); s.value = '';"
        " s.dispatchEvent(new Event('input', { bubbles: true }));"
        " const all = document.querySelectorAll('#list .row.has-tb');"
        " const last = all[all.length - 1]; last.scrollIntoView({ block: 'center' });"
        " setTimeout(() => last.click(), 100);"
    ),
    "wrap-paused": (
        "document.querySelector('#wrap').click();"
        " document.querySelector('#streams [data-key=\"Execution\"]').click();"
        " document.querySelector('#list').scrollTop = 1200;"
    ),
}

app = QApplication(sys.argv)
for theme in ("light", "dark"):
    get_theme_manager().set_theme(theme)
    view = QWebEngineView()
    bridge = mount_logs_page(view)
    view.resize(1166, 724)
    view.show()
    settle(1500)
    bridge.send(rows(202))
    settle()
    for name, script in STATES.items():
        if script:
            run(view, f"(function () {{ {script} }})()")
        if name == "wrap-paused":
            bridge.send(rows(205)[202:])
            settle()
        view.grab().save(str(OUT / f"{theme}-{name}.png"))
    view.deleteLater()
print(sorted(p.name for p in OUT.iterdir()))
````

Run, from the repo root:
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python <your tmp dir>/render_logs.py <your tmp dir>/renders`

It writes ten PNGs. Read each with the Read tool and compare with `docs/design/ui-refresh/mockups/renders/logs.png`
and, for the other states, with the mockup opened as its README describes. Check, in both themes:

- `*-200-entries.png`: the toolbar reads Source segments, Level segments with counts and two dots, the
  search box, `202 entries`, Save as text. Rows are 26px with hairlines; only Warning and Error badges are
  toned; an Error row's message is in the danger colour; the list sits at its end; Follow is ticked.
- `*-errors.png`: only Error rows, each with a chevron; the count reads `5 of 202 entries`.
- `*-no-match.png`: the "No entries match" panel with its sentence and Clear search.
- `*-traceback.png`: one open row on the raised plane with a down chevron, the Traceback box indented to
  the Source column with Copy on the right; the footer reads `Paused while scrolled up · Jump to newest`.
- `*-wrap-paused.png`: no From column (Execution is chosen), long messages on two lines, the footer reads
  `3 new entries below · Jump to newest`.

An underscore in the Source column must be visible (`pdf_processor`, not `pdf processor`). If anything
differs from the mockup beyond the departures in spec §9, fix the CSS, re-run Task 4's tests, and render
again.

Copy five of the PNGs into the repo with the Bash tool (`mkdir -p docs/design/ui-refresh/renders/phase6`,
then `cp`): `light-200-entries.png`, `light-errors.png`, `light-no-match.png`, `light-traceback.png`,
`dark-200-entries.png`. Delete the script and the rest.

- [ ] **Step 5: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

Expected: the three baseline failures in `tests/test_label_printing.py::TestImageToZpl` and nothing else
(in the scratch copy: 3 failed, 2966 passed).

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Run: `graphify update .` (CLAUDE.md: right after modifying code). `graphify-out/` is not tracked; commit
nothing from it.

- [ ] **Step 6: Commit**

Stage `CONTEXT.md docs/adr/0016-the-web-tier-grows-screen-by-screen.md docs/design/ui-refresh/roadmap.md`
and the five PNGs under `docs/design/ui-refresh/renders/phase6/`. Commit. Message subject:
`Logs: docs and renders for phase 6`.

For the PR description (Stage C writes it): no `shared/` change, so nothing for Packing Tool to sync. The
fifth `QWebEngineView` rests on the phase 3 Linux measurement; the Windows check over RDP stays with the
release. Departures from the mockup are spec §9.
