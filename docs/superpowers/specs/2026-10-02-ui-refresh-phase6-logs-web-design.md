# UI refresh phase 6: Logs on the web tier

**Task:** dev-runner run 50, Todoist 6hfx8crw35xvqRxM: "UI refresh phase 6: move Logs to the web tier".
Brief: `docs/design/ui-refresh/roadmap.md`, phase 6. Depends on phase 2 (merged, #356).
**Path:** architectural. It adds the fifth web view and the fifth bridge, replaces the Qt log viewer and its
model, proxy and follow state, and changes what a log entry carries (the traceback).
**Mockup followed:** `docs/design/ui-refresh/mockups/logs.html` (all four states, both themes). Every
departure is in §9.

## 1. What this task delivers

1. The Logs page as a web page on the kit: `gui/web/logs.html`, `logs.css`, `logs.js` (§5).
2. `LogBuffer`, a module with no Qt that holds the entries and words every row (§4).
3. `LogsBridge`, which streams rows to the page in batches (§3.2), and `LogsWidget`, which hosts the view (§6).
4. The traceback on a log entry, shown under the row that carries one (§4.1, §5.5).
5. Save as text that writes the entries shown, tracebacks included (§6.2).
6. The shell with no Qt page left: the page inset rule is deleted (§6.3).
7. Docs: `CONTEXT.md`, ADR 0016, `roadmap.md` (§11).

## 2. Owner's decisions (2026-10-02, run 50)

| Question | Answer |
|---|---|
| Save as text: where the file goes | A save dialog, as today, with `logs_<client>_<date>.txt` filled in. The toast names the file after it is written |
| The design (§3 to §10) | Approved |

The fifth `QWebEngineView` follows the owner's phase 3 decision: build on the Linux numbers (about 31 MB and
at most 0.15 s a view, phase 3 spec §2). The Windows check stays with the release.

**What the code did that the mockup does not know** (the facts behind the design):

- The newest entry was at the top. The mockup puts it at the bottom, and its footer ("3 new entries below",
  "Jump to newest") rests on that. The page follows the mockup.
- The level filter was a floor: Warning showed warnings and errors. In the mockup a level is one band with its
  own count. The page follows the mockup.
- The handler kept a one-line exception summary on the message and dropped the traceback. The mockup's rows
  expand to the whole traceback.
- There was no "All": Activity and Execution were two buffers of 5,000 behind a two-button switch.
- Save as text wrote the whole current source and ignored the level filter and the search.
- An Activity entry's `source` is the kind of action ("Session", "Report", "Data Edit"), not a module path.
- The theme has no `status_warning_dot`. Browse draws its warning dot with `status_warning`.

## 3. Architecture

```
QtLogHandler ─┐
log_activity ─┴► LogsWidget.append(entry, stream) ► LogBuffer.add ► row ► pending
                                   100 ms timer ► LogsBridge.entriesAdded([row, ...]) ► logs.js
logs.js ► saveShown(ids) / copyTraceback(id) / setWrap(on) ► LogsBridge signal ► LogsWidget
```

- **Python keeps the entries and words every row.** `LogBuffer` gives each entry an id and turns it into a
  row: a dict of strings the page shows as they are (§4.2).
- **The page owns the view.** It holds every row it was sent and does the filtering, the counts, the search,
  wrap, follow and expand itself. This is the opposite of Tools, where Python pushes one `state`. A pushed
  list would resend up to 10,000 rows on every keystroke.
- **Entries cross the bridge in batches.** A row waits in `LogsWidget` for at most 100 ms and leaves with
  every other row that arrived in that time, in one signal. The backlog leaves as one batch when the page
  says it is ready.
- **The page names entries by id.** Save and Copy send ids; Python finds the rows, writes the file or sets
  the clipboard, and toasts. The page never sends text that Python writes to disk.
- **No virtual list.** Each row is built once and stays in the DOM; a filter change sets `hidden` on rows.
  Measured in QtWebEngine on the dev VM with 10,000 rows: a filter change 20 ms, a batch of 200 entries
  26 ms, one entry 9 ms, turning wrap on 460 ms.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/log_buffer.py` (new) | `LogBuffer`, `to_row`, `band`, `save_text`, `default_filename`, `CAPACITY`, `ACTIVITY`, `EXECUTION`. No Qt import |
| `gui/logs_bridge.py` (new) | `LogsBridge(PageBridge)`, `mount_logs_page(view, wrap)` |
| `gui/logs_widget.py` (new) | `LogsWidget(QWidget)`: the view, the buffer, the batch timer, save and copy |
| `gui/web/logs.html`, `logs.css`, `logs.js` (new) | The page |
| `gui/log_entry.py` | `LogEntry.traceback: str = ""` |
| `gui/log_handler.py` | `emit` fills `traceback` |
| `gui/ui_manager.py` | Tab 3 is `LogsWidget`; `_WEB_PAGES` and `_apply_page_inset` are deleted |
| `gui/main_window_pyside.py` | `logs_widget` replaces `log_viewer`; `web_toast` knows tab 3 |
| Deleted | `gui/log_viewer.py`, `gui/log_model.py`, `gui/log_filter.py`, `gui/log_follow.py` and their tests (§7) |

`gui/web/kit.css` does not change: the segmented control, the input, the checkbox, the badge, the state
panel and the toast are all in it already.

### 3.2 `LogsBridge`: the catalogue

Channel name `logs`. Add a member here before adding it to the code.

| member | direction | meaning |
|---|---|---|
| `entriesAdded(rows)` Signal (`QVariantList`) | Python → JS | A batch of rows (§4.2), oldest first. The only way a row reaches the page |
| `capacity` Property (`int`, constant) | Python → JS | How many rows of one stream the page keeps (§5.7) |
| `wrap` Property (`bool`, constant) | Python → JS | Whether Wrap starts ticked on this PC |
| `themeCss`, `toastRaised(text, flag)` | Python → JS | From `PageBridge`. The flag is unused on this page |
| `start()` → `started()` | JS → Python | The page is listening. Python answers with the backlog as one batch |
| `saveShown(ids)` → `saveRequested(list)` | JS → Python | Save as text: the ids of the rows shown, oldest first |
| `copyTraceback(id)` → `copyRequested(int)` | JS → Python | Copy on a traceback block |
| `setWrap(on)` → `wrapRequested(bool)` | JS → Python | The Wrap box changed; Python remembers it |

`send(rows)` is the Python-side method that emits `entriesAdded`; it emits nothing for an empty list.
`saveShown` is `@Slot("QVariantList")` and keeps only the integers it is given. JavaScript numbers reach a
slot as `float`, so the slot converts each whole number with `int()` and drops anything else.

## 4. The data

### 4.1 `LogEntry` and the handler

`LogEntry` gains `traceback: str = ""`, last, so every existing call still builds one.

`QtLogHandler.emit` keeps the summary on the message (`Save failed — PermissionError: share is read-only`):
a row that is not open still names the cause, and search finds the exception's name. When the record has
`exc_info` with an exception in it, `traceback` is `"".join(traceback.format_exception(*record.exc_info))`
with trailing whitespace stripped. Otherwise it is `""`.

### 4.2 `gui/log_buffer.py`

```python
CAPACITY = 5000
ACTIVITY = "Activity"
EXECUTION = "Execution"
```

**`band(level: int) -> str`**: `"error"` at `logging.ERROR` and above, `"warning"` at `logging.WARNING` and
above, otherwise `"info"`. Debug entries (seen only with `FULFILLMENT_LOG_LEVEL=DEBUG`) are in the Info band
and Critical is in the Error band.

**`to_row(entry_id: int, entry: LogEntry, stream: str) -> dict`**: the row the page draws.

| key | value | example |
|---|---|---|
| `id` | the entry's id | `12` |
| `time` | `%H:%M:%S` plus `.` and three digits of milliseconds | `"14:00:53.508"` |
| `date` | `%Y-%m-%d` | `"2026-09-30"` |
| `band` | `band(entry.level)` | `"error"` |
| `level` | `logging.getLevelName(entry.level).title()` | `"Error"`, `"Debug"`, `"Critical"` |
| `stream` | `ACTIVITY` or `EXECUTION` | `"Execution"` |
| `source` | `entry.source` | `"shopify_tool.pdf_processor"`, `"Data Edit"` |
| `short` | `source` after its last dot | `"pdf_processor"`, `"Data Edit"` |
| `message` | `entry.message` | |
| `traceback` | `entry.traceback` | `""` when there is none |

**`LogBuffer(capacity: int = CAPACITY)`**: one `deque(maxlen=capacity)` of rows per stream, and a counter.

- `add(entry, stream) -> dict`: builds the row with the next id (ids start at 0 and never repeat), appends it
  to that stream's deque, and returns it. A full deque drops its oldest row.
- `rows() -> list[dict]`: every row of both streams, in id order.
- `pick(ids) -> list[dict]`: the rows whose id is in `ids`, in id order. An id the buffer no longer holds is
  skipped.

Each stream keeps its own 5,000, as before: a busy Execution stream cannot push the day's Activity out.

**`save_text(rows) -> str`**: the file's text. One line per row, oldest first, then the traceback indented by
four spaces. Every line ends with `\n`.

```
2026-09-30 14:00:53.508  ERROR     Execution  shopify_tool.pdf_processor  Save failed — PermissionError: share is read-only
    Traceback (most recent call last):
      File "C:\FulfilmentTool\gui\tools_widget.py", line 142, in _on_run
    PermissionError: share is read-only
```

The line is `f"{date} {time}  {level.upper():<8}  {stream:<9}  {source}  {message}"`.

**`default_filename(client_id, day: date) -> str`**: `logs_ACME_2026-09-30.txt`, or `logs_2026-09-30.txt`
with no client. Characters in the client id other than letters, digits, `-` and `_` become `_`.

## 5. The page

`gui/web/logs.html` links `kit.css` then `logs.css`, as every page does. `logs.js` builds every row with
`createElement` and `textContent`. A log message can hold text from a CSV, so nothing from a row ever goes
through `innerHTML`.

### 5.1 Frame

`<main id="logs">` with 16px 24px 20px padding holds one `.card` that fills it (min-width 780px; the main
scrolls sideways below that, as Browse does). The card is a column: toolbar, header row, list, footer. There
is no page head: the mockup has none.

### 5.2 Toolbar

Padding 8px, gap 12px, a `--border-subtle` line under it. Left to right:

1. **Source**, a kit `.segmented` (`role="radiogroup"`, `aria-label="Source"`): All, Activity, Execution. No
   counts.
2. **Level**, a kit `.segmented` (`aria-label="Level"`): All, Info, Warning, Error. Each segment ends in a
   `.segment-count`. Warning and Error start with a 6px dot (`--status-warning`, `--status-danger-dot`). The
   Error count is `--status-danger` when it is above 0.
3. **Search**, a kit `.input` wrapping a search glyph and `<input type="search">`, placeholder
   "Search messages and sources". It grows to at most 320px.
4. A spacer, then the **count**: `202 entries` when everything is shown, `18 of 202 entries` when not, `1
   entry` for one. Caption size, secondary colour.
5. **Save as text**, a `.btn.secondary` with the download glyph, `title="Save shown entries as text  Ctrl+S"`.
   Disabled when no row is shown.

A segment is `role="radio"` with `aria-checked`. Only the checked one is in the tab order; Left and Right
move to the next segment and choose it, wrapping at the ends.

**The counts.** A Level count is the number of rows in that band that pass the current Source and the
current search. All is their sum. So a count says what a click would show.

**The filter.** A row is shown when all three hold: Source is All or equals the row's `stream`; Level is All
or equals the row's `band`; the search text is empty or is found, ignoring case, in `message + " " + source`.
The traceback is not searched.

### 5.3 Header row and columns

A grid, 30px high, `--surface-raised`, a `--border` line under it, caption size, bold, secondary colour.

| column | width | cell |
|---|---|---|
| chevron | 24px | a chevron when the row has a traceback |
| Time | 112px | `time`, mono, secondary; `title` is `date + " " + time` |
| Level | 84px | a kit badge with `level`: `.badge.danger` for the error band, `.badge.warning` for warning, `.badge.neutral` for info |
| From | 84px | `stream`, caption size, secondary. The column is not drawn when Source is not All |
| Source | 170px | `short`, mono, elided; `title` is `source` |
| Message | the rest | `message` |

### 5.4 Rows

Row height is `calc(var(--row-height) - 2px)`: 26px in the compact density. A `--border-subtle` line under
each. Hover is `--surface-raised`. Only the badge carries a tone, except that an error row's message is
`--status-danger`.

With Wrap off, a message is one line and elides, line breaks included. With Wrap on, the list has the class
`wrap`: a row is as tall as its message (`white-space: pre-wrap`, `word-break: break-word`), never shorter
than an unwrapped row, and the cells align to the top.

### 5.5 A row with a traceback

It shows a right chevron, has `role="button"`, `tabindex="0"` and `aria-expanded`, and a pointer cursor. A
click, Enter or Space opens it; the same closes it. A click that ends a text selection does nothing, so the
operator can drag over a message to copy it.

Open, the row is `--surface-raised` with a down chevron and no line under it, and a block follows it,
indented to the Source column: a `--surface-sunken` box with a `--border` edge and an 8px radius. Its head
(30px) reads **Traceback**, then `source` in mono, then a compact **Copy** button on the right. Its body is a
`<pre>` in mono at caption size, wrapping. Copy calls `copyTraceback(id)`; Python sets the clipboard and
toasts "Traceback copied".

Opening a row turns Follow off. Any number of rows can be open. A filter that hides a row hides its block.

### 5.6 Footer and Follow

36px, a `--border-subtle` line above it, caption size. Left to right: a checkbox **Wrap long messages**, a
checkbox **Follow the newest entry**, the paused note, a spacer, and the hint
"Click an Error with ▸ to see its traceback".

**Follow** is on at the start. While it is on, the list is scrolled to its end after every batch, every
filter change, every wrap change and every window resize. The Logs tab is usually hidden while entries
arrive, and a window made smaller moves the end of the list without a scroll event.

| What happens | Follow | Unseen count |
|---|---|---|
| The list is scrolled and ends more than 4px above its end | off | unchanged |
| The list is scrolled and ends at its end | on | 0 |
| A row is opened or closed | off | unchanged |
| Source, Level or the search changes; Clear search; Show all levels and sources | on | 0 |
| The Follow box is ticked, or Jump to newest is clicked | on | 0 |
| The Follow box is unticked | off | 0 |
| A batch arrives while Follow is off | off | plus the batch's rows that the filter shows |

**The paused note** is drawn when Follow is off and at least one row is shown: `3 new entries below` (`1 new
entry below`) when the count is above 0, otherwise `Paused while scrolled up`; then `·` and a text button
**Jump to newest**.

Wrap is remembered per PC under the QSettings key `logs/wrap`, as before. Follow is not remembered.

### 5.7 The page's buffer

The page keeps at most `capacity` rows of each stream. When a batch takes a stream over that, the page drops
that stream's oldest rows, and their open blocks with them. Python's buffer drops the same rows by the same
rule, so `pick` finds every id the page can send.

### 5.8 Empty states

When no row is shown, the list holds a kit `.state` panel with the search-x glyph.

| Case | Title | Text | Buttons |
|---|---|---|---|
| A search is set | No entries match | `Nothing in Error Execution contains “zebra” in its message or source.` (without ` in …` when Source and Level are All) | Clear search; and Show all levels and sources when Source or Level is not All |
| No search, Source or Level set | No entries match | `No Error Execution entries yet.` | Show all levels and sources |
| No search, nothing set | No entries yet | none | none |

The scope is the Level's label then the Source's label, each left out when it is All.

### 5.9 Keyboard and toast

Ctrl+S anywhere on the page saves, when a row is shown. Escape in the search box clears it (the browser does
this for `type="search"`). The toast is the kit's, bottom right, text and a dismiss button, gone after 4 s.

### 5.10 Test hooks

`document.documentElement.dataset.bridge` is `"ready"` once the channel is connected and `start()` has been
called. `dataset.renders` counts up after every batch and every change the page draws.

## 6. The widget and the shell

### 6.1 `LogsWidget` (`gui/logs_widget.py`)

`LogsWidget(main_window, parent=None)` holds a `LogBuffer`, one `QWebEngineView`, the bridge from
`mount_logs_page(view, wrap)` and a single-shot 100 ms `QTimer`. It reads `main_window.current_client_id`
for the file name and nothing else from the window.

- `append(entry, stream)`: adds to the buffer. Once the page has started, the row also joins `pending` and
  the timer starts if it is not running. The timer sends `pending` as one batch and empties it.
- On `started`: the page is marked started, `pending` is emptied, and `buffer.rows()` is sent as one batch.
- **`append` and the timer's slot never log.** The handler calls `append` for every record the program
  logs, on the GUI thread, so a log call inside either would call itself without end.

### 6.2 Save and Copy

**Save** (`saveRequested(ids)`): `rows = buffer.pick(ids)`. With no rows, nothing happens. Otherwise
`QFileDialog.getSaveFileName(self, "Save log as text", default_filename(client, today), "Text files
(*.txt);;All files (*)")`. A cancelled dialog does nothing. The file is `save_text(rows)` in UTF-8. Then the
toast: `Saved 202 entries to logs_ACME_2026-09-30.txt` (`Saved 1 entry to …`), naming the file as saved.

**Copy** (`copyRequested(id)`): when the buffer holds the row and it has a traceback, the clipboard gets the
traceback and the toast reads `Traceback copied`.

### 6.3 The shell

- `UIManager._create_tab4_logs` returns `LogsWidget(self.mw)` and stores it as `mw.logs_widget`.
  `mw.log_viewer` is gone.
- `MainWindow._on_log_entry` and `log_activity` call `self.logs_widget.append(...)` with
  `log_buffer.EXECUTION` and `log_buffer.ACTIVITY`. `log_activity` keeps its signature.
- `MainWindow.web_toast` sends a toast raised on tab 3 to the Logs page.
- Every tab is a web page now, so `_WEB_PAGES` and `_apply_page_inset` are deleted and the page area's
  layout has no margins from the start.
- The session chip stays in the command bar on Logs (`chip=index not in (0, 4)` is unchanged).

## 7. Deleted

| Gone | Why |
|---|---|
| `gui/log_viewer.py`, `tests/test_log_viewer.py`, `tests/test_log_viewer_theme.py` | The page replaces the widget |
| `gui/log_model.py`, `tests/test_log_model.py` | `LogBuffer` holds the entries |
| `gui/log_filter.py`, `tests/test_log_filter.py` | The page filters |
| `gui/log_follow.py`, `tests/test_log_follow.py` | The page follows |
| `UIManager._apply_page_inset`, `_WEB_PAGES` | No Qt page is left |

`tests/test_logs_destination.py` is rewritten against `LogsWidget`.

## 8. Errors

- **The file cannot be written.** `OSError` is caught: a warning is logged and the existing dialog is shown
  (`show_error`, "The log wasn't saved", "<path> couldn't be written. Choose another folder and save
  again."). No toast.
- **An id the buffer dropped.** `pick` skips it. The file holds the rows that are left.
- **A slot is sent junk.** `saveShown` drops values that are not whole numbers; `copyTraceback` with an
  unknown id does nothing.

## 9. Departures from the mockup

| Mockup | Built | Why |
|---|---|---|
| The chevron turns with a 0.12 s transition | The glyph is swapped, right to down | Transforms and transitions are banned on the web tier (ADR 0016, `shared/style_lint.py`) |
| The Warning dot is `status_warning_dot` | `status_warning` | No such token; Browse does the same |
| The Info badge is a ring; badges are 18px | The kit's `.badge.neutral`, 20px | The kit's badge |
| The checked segment has its own `seg_shadow` | The kit's `.segment` | The kit's segmented control |
| The search box has a `border_strong` edge and its own clear button | The kit's `.input`, and the browser's clear button for `type="search"` | The kit's input, as on Browse |
| The unseen count is every entry that arrived | Only the entries the filter shows | "3 new entries below" is then true of the list on screen |
| The toast alone answers Save as text | A save dialog first | Owner's decision (§2) |
| Rows are 26px or 32px by a density prop | `calc(var(--row-height) - 2px)`: 26px compact, 38px comfortable | The app's density profiles own row height |
| The bar shows no session chip | The chip stays in the bar | No page head to move it to; phase 4 did the same on Browse |
| Sources are module paths | Activity rows show the kind of action | That is what an Activity entry's source is |

The roadmap's sentence says both controls carry a live count. The mockup draws counts on Level only, and the
page follows the mockup.

## 10. Tests (test-first; the seams)

| Seam | File | What it proves |
|---|---|---|
| `LogBuffer`, `to_row`, `band`, `save_text`, `default_filename` | `tests/test_log_buffer.py` (new, no Qt) | Row keys and wording; bands for Debug and Critical; ids; one stream's capacity leaves the other alone; `rows()` and `pick()` order; the file's text with a traceback; the file name with and without a client |
| `LogEntry`, `QtLogHandler` | `tests/test_log_entry.py`, `tests/test_log_handler.py` | `traceback` defaults to `""`; a record with `exc_info` carries the whole traceback and keeps its summary; one without carries `""` |
| `LogsBridge` | `tests/test_logs_bridge.py` (new) | It is a `PageBridge`; `send` emits once and not for `[]`; each slot emits its signal; `saveShown` keeps whole numbers only |
| The page | `tests/test_logs_page.py` (new, real Chromium) | Kit linked first; rows drawn in order with the right cells; From hidden for one stream; counts follow Source and search; Level filters by band; search matches message and source, not traceback; the three empty states and their buttons; expand, collapse, Copy reaches Python; Follow off on scroll up, the unseen count, Jump to newest; Wrap class and `setWrap`; Save sends the shown ids, is disabled with none, and answers Ctrl+S; the page drops the oldest row of a full stream; a message with markup in it is drawn as text; a message with a line break; a smaller window keeps a following list at its end; the toast; both themes |
| `LogsWidget` | `tests/test_logs_widget.py` (new) | Rows before `started` leave as one backlog batch; rows after it leave in one batch per timer tick; Save writes `save_text` of the picked rows and toasts the file name; a cancelled dialog writes nothing; `OSError` shows the dialog and no toast; Copy sets the clipboard; Wrap is read from and written to `logs/wrap` |
| The shell | `tests/test_logs_destination.py` (rewritten), `tests/test_shell.py` | `log_activity` and a root-logger record reach the buffer in their streams; tab 3 is one web view; the page area has no inset on any tab; a toast on tab 3 goes to the Logs page |

Renders: the four mockup states (200 entries, Errors, No match, Traceback) in light, and the first in dark,
saved under `docs/design/ui-refresh/renders/phase6/` and compared with the mockup.

Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, plus `ruff check .`.

## 11. Docs

- `CONTEXT.md`: **Log entry** gains the traceback. **Source** says how the page uses the word: the Source
  control picks the stream, the From column names it, and the Source column shows the logger or the kind of
  action. **Follow-tail** says the newest entry is at the bottom. A new **Level band** entry.
- `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`: one line for phase 6. Logs moved with the fifth
  bridge and view; its page owns its rows and its whole view state, and Python streams rows in batches.
- `docs/design/ui-refresh/roadmap.md`: phase 6 is marked built, with its spec, its plan and the differences
  in §9.

No new ADR: streaming batches to a page that owns its rows is ADR 0016's own pattern (Browse and Results
own their view state), applied to a list that grows.

## 12. Out of scope

- `gui/status_edge_delegate.py` loses its last user in `gui/` with the log viewer. Deleting it, with the
  tests it shares with the selection ring, is its own cleanup.
- A Debug segment, a Clear button, remembering Follow, and searching inside tracebacks. The mockup draws
  none of them.
- Keeping the scroll position exact when the page drops rows above a paused view. The browser's scroll
  anchoring does it; nothing is added.
- Packing Tool. `shared/` does not change in this task.

## 13. Delivery

One branch, `dr/18-ui-refresh-phase-6-move-logs-to-the-web`, one PR. No `shared/` change, so nothing for
Packing Tool to sync.
