# UI refresh phase 3: Setup on the web tier

**Task:** dev-runner run 41, Todoist 6hfx8cpvrCcx5QMv: "UI refresh phase 3: move Setup to the web tier".
Brief: `docs/design/ui-refresh/roadmap.md`, phase 3. Depends on phase 2 (merged, #356).
**Path:** architectural. It adds a second web view and a second bridge, gives `core.run_full_analysis` a
progress and cancel contract, and rebuilds the command bar's states.
**Mockup followed:** `docs/design/ui-refresh/mockups/setup.html` (all seven states, both themes), and
`app-shell.html` for the no-session panel and the running bar. Every departure is in §10.

## 1. What this task delivers

1. The Setup page as a web page on the kit: `gui/web/setup.html`, `setup.css`, `setup.js` (§5).
2. `SetupBridge`, a view that takes file drops, and one pure function that builds everything the page
   draws (§3, §4).
3. The file slot as a plain record, with every file failure shown in its card (§6).
4. Named steps and Cancel for a run: a `progress` callback on `core.run_full_analysis` (§7).
5. The command bar as the mockups draw it (§8).
6. One toast router, so a toast raised while a web page shows is drawn by that page (§9).
7. Three kit components: switch, radio card, form row (§5.6).
8. Docs: `CONTEXT.md`, ADR 0016, `roadmap.md` (§12).

## 2. Owner's decisions (2026-10-01, run 41)

| Question | Answer |
|---|---|
| The second web view's cost (ADR 0016's reversal test) | Build on the Linux numbers. The PR body carries a Task Manager check for a warehouse PC over RDP, done before the release |
| Setup with a client and no session | The explicit panel from `app-shell.html`: "No session open for ACME", New session, Open recent. The cards appear only once a session exists |
| How far the progress view goes | Four named steps and Cancel. Cancel stops at the next step boundary and is disabled once saving starts. No per-order count |
| The design (§3 to §11) | Approved |

**The measurement (Linux, offscreen, this repo's `results.html` in each view, PSS over the process tree):**

| views | processes | memory | load after `QApplication` |
|---|---|---|---|
| 0 | 1 | 148 MB | n/a |
| 1 (today) | 4 | 339 to 343 MB | 0.27 s |
| 2 (this phase) | 5 | 370 to 374 MB | 0.27 to 0.42 s |
| 3 | 6 | 400 MB | 0.28 s |

The first view costs about 195 MB (the engine). Each further view costs about 31 MB (one renderer process)
and at most 0.15 s. A frozen Windows build over RDP was not measured: it cannot be run from the dev VM.

## 3. Architecture

```
MainWindow state ──► UIManager.refresh_setup() ──► setup_state(...) ──► SetupBridge.state ──► setup.js render()
                                                     (pure, a dict)        (one Property)       (draws all of it)
setup.js ──► SetupBridge slot ──► Signal ──► FileHandler / ActionsHandler / MainWindow ──► refresh_setup()
```

- **Python owns every fact and every sentence.** `setup_state` returns one dict: which view to show, both
  file cards, the summary sentence, its rows, the reason under the button, and whether Run is enabled. The
  page renders that dict and holds no state of its own except the drag highlight and the toast timer.
- **One rule for Run.** Today two rules race: `update_ui_state` (paths exist) and `check_files_ready` (slots
  valid), and whichever ran last wins. The rule moves into `setup_state` (§4.3) and both callers ask it.
- **The hidden `run_analysis_button` stays the guard**, as `generate_reports_button_tab2` is for Export.
  `refresh_setup` sets its enabled state from `state["run"]["enabled"]`. Ctrl+R and Results' "Run analysis
  again" click it, unchanged.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/web_page.py` (new) | `WEB_DIR`, `THEME_MARKER`, `PageBridge(QObject)` and `mount_page(view, bridge, page, channel)`: what every web page's bridge shares |
| `gui/results_bridge.py` | `ResultsBridge` extends `PageBridge`; `mount_results_page` calls `mount_page`. `WEB_DIR`, `THEME_MARKER` and `PAGE` stay importable from here |
| `gui/setup_state.py` (new) | `FileSlot` (the record), `SessionFacts`, `MemoryFacts`, `RunFacts`, and `setup_state(...)`. No Qt import |
| `gui/setup_bridge.py` (new) | `SetupBridge(PageBridge)`, `SetupView(QWebEngineView)`, `mount_setup_page(view)` |
| `gui/web/setup.html`, `setup.css`, `setup.js` (new) | The page |
| `gui/web/kit.css` | `.switch`, `.radio-card`, `.form-row` |
| `gui/ui_manager.py` | Tab 0 hosts the view; `refresh_setup()`; the Qt setup card and its helpers go |
| `gui/file_handler.py` | Writes the slot record; one route for a picked and a dropped path |
| `gui/actions_handler.py` | Progress, cancel |
| `gui/main_window_pyside.py` | Wiring; `web_toast`; the checkbox and radio code goes |
| `gui/components/commandbar.py` | §8 |
| `gui/components/__init__.py` | The toast router; `FileSlot` and `RadioCard` leave the exports |
| `shopify_tool/core.py` | `ANALYSIS_STEPS`, `AnalysisCancelled`, `CANCELLED`, `progress=`, `csv_row_stats` |
| Deleted | `gui/components/file_slot.py`, `gui/components/radio_card.py` |

### 3.2 `PageBridge` and `mount_page`

`PageBridge` holds what `ResultsBridge` has today and `SetupBridge` needs too: the `themeCss` Property with
`themeCssChanged`, `set_theme_css(css)`, the `toastRaised = Signal(str, bool)` signal and
`raise_toast(message, undoable=False)`. `mount_page` is `mount_results_page`'s body with the page path and
channel name as arguments: register the bridge on a `QWebChannel`, push the theme on every theme or density
change, write the theme over `THEME_MARKER`, and load the page with `gui/web/` as its base URL.

### 3.3 `SetupBridge`: the catalogue

Channel name `setup`. Add a member here before adding it to the code.

| member | direction | meaning |
|---|---|---|
| `state` Property (`QVariantMap`, notify `stateChanged`) | Python → JS | Everything the page draws (§4) |
| `themeCss`, `toastRaised(text, undoable)` | Python → JS | From `PageBridge`. Setup never raises an undoable toast |
| `chooseFile(kind)` → `fileRequested(str)` | JS → Python | Open the file dialog for this card |
| `chooseFolder(kind)` → `folderRequested(str)` | JS → Python | Open the folder dialog for this card |
| `clearFile(kind)` → `clearRequested(str)` | JS → Python | The card's Replace button: empty the slot |
| `fixProblem(kind)` → `fixRequested(str)` | JS → Python | The problem's link. Python knows where it leads |
| `setMemory(on)` → `memoryToggled(bool)` | JS → Python | The inventory memory switch |
| `setStrategy(name)` → `strategyChosen(str)` | JS → Python | `"multi_first"` or `"fifo"`; anything else is dropped |
| `runAnalysis()` → `runRequested()` | JS → Python | Run analysis |
| `cancelRun()` → `cancelRequested()` | JS → Python | Cancel |
| `newSession()` → `newSessionRequested()` | JS → Python | The no-session panel's primary |
| `openRecent()` → `recentRequested()` | JS → Python | The no-session panel's secondary: opens the bar's Open recent menu |
| `openConnection()` → `connectionRequested()` | JS → Python | The unreachable panel's button |

`kind` is `"orders"` or `"stock"`; a slot drops any other value. `set_state(state: dict)` is the Python-facing
setter; it emits `stateChanged` only when the dict differs from the last one.

### 3.4 `SetupView`: dropping a file

Chromium navigates to a file dropped on a page, and a page cannot read a dropped file's path. So the view
takes the drop, as verified with a throwaway probe on 2026-10-01:

- `dragEnterEvent` and `dragMoveEvent` call the base class (the page then gets `dragenter`, `dragover` and
  `dragleave`, and highlights the card under the pointer) and accept the event when the mime data has URLs.
- `dropEvent` does not call the base class. It calls `super().dragLeaveEvent(QDragLeaveEvent())` so Chromium
  ends its drag, then asks the page which card is under the drop point:
  `document.elementFromPoint(x, y)?.closest('[data-file-kind]')?.dataset.fileKind`. With an answer it emits
  `pathDropped(kind, path)` with the first URL's local path.
- A drop that lands on no card, or while the page shows no cards (another view, or a run in progress, where
  the cards carry no `data-file-kind`), does nothing.

`UIManager` connects `pathDropped` to `FileHandler.accept_dropped_path`.

## 4. The state

### 4.1 Inputs (`gui/setup_state.py`)

```python
@dataclass
class FileSlot:
    kind: str                                  # "orders" | "stock"
    on_change: Callable[[], None] = _noop
    path: Path | None = None
    is_valid: bool = False
    name: str = ""                             # what the card shows as the file's name
    is_folder: bool = False
    rows: int | None = None
    keys: int | None = None                    # distinct orders, or distinct SKUs
    delimiter: str = ""                        # the character; "mixed"; "" when unknown
    parts: list[dict] = field(default_factory=list)   # {"name", "rows"} per merged CSV
    note: str = ""                             # the folder merge's caption
    problem: dict | None = None                # {"title", "text", "fix_page", "fix_label"}
    missing_columns: list[str] = field(default_factory=list)
    present_columns: list[str] = field(default_factory=list)

    def set_loaded(self, path, *, rows, keys, delimiter, parts=(), note="") -> None
    def set_invalid(self, path, missing: list[str], present: list[str], names: dict[str, str],
                    *, rows=None, delimiter="") -> None
    def set_problem(self, path, title: str, text: str, fix_page: str = "") -> None
    def clear(self) -> None

@dataclass(frozen=True)
class SessionFacts:  name: str; opened: datetime | None; analysed: datetime | None
@dataclass(frozen=True)
class MemoryFacts:   on: bool; skus: int; session: str; updated: datetime | None
@dataclass(frozen=True)
class RunFacts:      running: bool = False; step: int = 0; cancelling: bool = False
```

Every `FileSlot` mutator ends by calling `on_change()`. `set_loaded` with `parts` sets `is_folder`.
`names` in `set_invalid` maps each missing CSV column to the internal name it is mapped to (§6.4); its
`rows` and `delimiter` fill the Problem card's stats, where the key count stays unknown ("—").
`fix_label` is `"Open " + fix_page`, or `""` with no page.

```python
def setup_state(*, connected: bool, client: str, server_path: str, session: SessionFacts | None,
                orders: FileSlot, stock: FileSlot, memory: MemoryFacts, strategy: str,
                run: RunFacts, now: datetime) -> dict
```

### 4.2 Output

```python
{
  "view": "unreachable" | "no_client" | "no_session" | "setup",
  "client": "ACME",
  "server_path": r"\\fs01\fulfilment",
  "session": {"name": "2026-09-30_1", "title": "New session", "meta": "ACME · opened 14:02"},  # {} with none
  "files": {"orders": card, "stock": card},
  "memory": {"on": False, "text": "...", "previous": "..."},
  "strategy": "multi_first",
  "summary": {"headline": "...", "ready": True, "rows": [{"k", "v", "muted"}, ...],
              "reason": "...", "reason_tone": "" | "danger"},
  "run": {"enabled": True, "running": False, "locked": False, "step": 0, "steps": 4,
          "step_name": "", "can_cancel": False, "cancelling": False},
}
card = {"state": "missing" | "loaded" | "problem", "badge": "Missing", "badge_tone": "neutral",
        "name": "...", "is_folder": False, "parts": [{"name", "rows"}], "note": "",
        "stats": [{"k", "v", "muted"}, ...],            # three entries, or [] when missing
        "problem": {"title", "text", "fix_label"} | {}}
```

**View**, first match wins: `unreachable` when not connected and no session is open; `no_client` with no
client; `no_session` with no session; otherwise `setup`. A session that loses the server keeps its cards
(the mockup's Unreachable state).

**Session.** `title` is "New session" until the session has an analysis, then "Session". `meta` is
"{client} · opened {time}", or "{client} · analysed {time}" once analysed. `time` is `%H:%M` when the
moment is on `now`'s date, else `%d %b %H:%M` ("29 Sep 16:40"). With no timestamp, `meta` is the client.

**Numbers** use a comma for thousands ("1,204"), as the mockup and the Results page do.

### 4.3 Run, summary and reason

`memory_covers = memory.on and memory.skus > 0 and stock.path is None`.
`stock_ok = stock.is_valid or memory_covers`.
`run.enabled = connected and session is not None and not run.running and orders.is_valid and stock_ok`.
`run.locked = run.running` (the page disables every input). `summary.ready = orders.is_valid and stock_ok`.

`O` is `orders.keys`, `L` is `orders.rows`, `S` is `stock.keys` (or `memory.skus` when memory covers).
The strategy reads "multi-item first" or "oldest first" in the headline and "Multi-item first" or "Oldest
first" in the row.

| situation, first match | headline |
|---|---|
| orders has a problem | "The orders file needs fixing before this can run" |
| stock has a problem | "The stock file needs fixing before this can run" |
| ready, stock file loaded | "{O} orders, {L} lines, stock for {S} SKUs, {strategy}" |
| ready, memory covers | "{O} orders, {L} lines, last run's stock for {S} SKUs, {strategy}" |
| orders valid, no stock | "{O} orders, {L} lines, waiting for the stock file" |
| stock valid, no orders | "Stock for {S} SKUs, waiting for the orders file" |
| memory covers, no orders | "Last run's stock for {S} SKUs, waiting for the orders file" |
| neither | "Load both files to see what this run will do" |

Rows, in order:

| k | v | muted |
|---|---|---|
| Orders | "{O} orders · {L} lines" / "Problem: {title, first letter lowered}" / "Not loaded" | when not valid |
| Stock | "Stock file · {S} SKUs" / "From {memory.session} · {S} SKUs" (or "From memory · {S} SKUs" with no session name) / "Problem: …" / "Not loaded" | when not `stock_ok` |
| Strategy | "Multi-item first" / "Oldest first" | never |

| situation, first match | reason | tone |
|---|---|---|
| running | "" | |
| orders has a problem | "Fix the orders file to run." | |
| stock has a problem | "Fix the stock file to run." | |
| no orders and not `stock_ok` | "Load the orders and stock files to run." | |
| no orders | "Load the orders file to run." | |
| not `stock_ok` | "Load the stock file to run." | |
| not connected | "Server unreachable. Files stay loaded; Retry is in the sidebar." | danger |
| the session has an analysis | "Running again replaces this session's results." | |
| otherwise | "Results open when it finishes." | |

**Run while running:** `step` and `step_name` come from `core.ANALYSIS_STEPS`. `can_cancel` is
`run.running and not run.cancelling and run.step < 3`. `cancelling` passes through.

### 4.4 Memory

`on` is `MemoryFacts.on`. `text`, with the client's name:
"When on, a run with no stock file starts from the stock {client}'s previous run left. A loaded stock file
is always used as it is."

`previous`, shown under it while on:
- with remembered SKUs: "Previous run {session} · {updated as %d %b %H:%M} · {skus} SKUs" (parts that are
  unknown are left out);
- with none: "Nothing is remembered yet. The first run needs a stock file."

### 4.5 `UIManager.refresh_setup()`

Gathers the inputs from `MainWindow`, calls `setup_state`, sets `run_analysis_button`'s enabled state, and
calls `setup_bridge.set_state`. It is called by `update_ui_state` (its last line), by each slot's
`on_change`, by `_on_connection_changed`, and by the run's start, progress, cancel and finish.

- `MemoryFacts` comes from `active_profile_config["inventory_memory"]`: `enabled` (default `True`, as the
  checkbox restored it), `len(skus)`, `session`, `last_updated`.
- `strategy` is `active_profile_config.get("analysis_mode", "multi_first")`.
- `SessionFacts` is read from `session_info.json` **only** where `update_session_chips` already reads it
  (a new session, an opened session, a finished run) and kept on `mw.session_facts`. `refresh_setup` never
  touches the share. With no `session_path`, the session is `None` whatever `session_facts` holds.
- `RunFacts` is `mw._analysis_running`, `mw._analysis_step` and `mw._analysis_cancelling`.

`setup_stack`, `setup_state_panel`, `_refresh_setup_panel`, `_SetupPage`, `_create_strategy_picker`,
`inventory_memory_checkbox`, `strategy_multi_item`, `strategy_fifo` and `strategy_group` are deleted, with
the code in `load_client_config`, `update_ui_state` and `connect_signals` that drove them.

## 5. The page

Geometry is the mockup's at 1366×768 unless §10 says otherwise. Colours are kit tokens; the border mapping is
phase 2's (ADR 0018): a hairline is `--border-subtle`, a control's edge is `--border`.

### 5.1 Frame

`body` is `--surface-sunken`. `#setup` fills the view, scrolls (`overflow: auto`), has padding `20px 24px`
and is a column with a 12px gap. `_WEB_PAGES` becomes `frozenset({0, 1})`, so the page area's inset is 0 on
Setup.

`#setup` carries `data-view`. Three views are a kit `.state` panel, centred in the page:

| view | glyph | title | text | buttons |
|---|---|---|---|---|
| `no_client` | users | "Choose a client to begin" | "Pick a client in the bar above. Sessions, stock and reports all belong to one client." | none |
| `unreachable` | alert triangle | "This PC can't reach the fulfilment server" | "Clients, stock files and past sessions all live on the server. Until this PC reaches it, there is nothing to set up." then the server path in mono caption | "Server connection…" (secondary) → `openConnection()` |
| `no_session` | clipboard | "No session open for {client}" | "Start a session for today's orders, or reopen one from this client." | "New session" (primary) → `newSession()`; "Open recent" (secondary) → `openRecent()` |

The state panel's title is heading size here (the mockup's 14pt), set in `setup.css`.

### 5.2 Head and grid (view `setup`)

A kit `.page-head`: `.page-title` (the session's `title`), a `.code` chip with the session name, `.page-meta`.

Under it a grid, `minmax(0, 1fr) 300px`, gap 16px, `align-items: start`. Left: a column, gap 12px, holding
the two file cards in a two-column grid (gap 12px) and the options card. Right: the Run summary, which is
`position: sticky; top: 0` so it stays on screen when a short window scrolls the page. At a page width
under 900px the two file cards stack in one column; the summary column stays.

### 5.3 File card

A `.card` with `data-file-kind`. In the Problem state its border is `--status-danger-border`.

- **Head** (padding `10px 12px 0`): the title in label size, bold ("Orders file", "Stock file"); a hint in
  caption, `--text-secondary` ("Shopify orders export · CSV", "Warehouse stock export · CSV"); the badge on
  the right: `.badge.neutral` "Missing", `.badge.success` "Loaded", `.badge.danger` "Problem", or
  `.badge.neutral` "From memory" (the stock card while memory covers a missing stock file).
- **Missing:** a drop zone (margin `10px 12px 12px`, padding `18px 12px`, `1px dashed var(--border)`,
  radius 8, `--surface-raised`, centred column, gap 8): the upload glyph (22px), the drop text ("Drop the
  Shopify orders export here", "Drop the warehouse stock export here"), two secondary buttons "Choose
  file…" and "Choose folder…", and the caption "A folder merges every CSV in it into one input." While a
  file is dragged over the card the zone takes `--selection-bg` and a `--selection-border` edge.
- **Loaded** (padding `10px 12px 12px`, gap 10): a row with the file or folder glyph, the name in mono
  bold with ellipsis, and a compact secondary **Replace** → `clearFile(kind)`. For a folder, a box
  (`1px solid var(--border-subtle)`, radius 8) lists each CSV: its name and "{rows} rows", both mono
  caption, 26px rows divided by hairlines; with more than six parts the box scrolls at 156px. The `note`
  follows in caption, `--text-secondary`. Then three stats in a three-column grid: a caption label over a
  mono bold value; a muted value is `--text-disabled`.
- **Problem:** the loaded block, then a kit `.banner.danger` (margin `0 12px 12px`, radius 8): the alert
  glyph, the title in bold `--status-danger`, the text, and when `fix_label` is set a `.btn.link` with that
  label → `fixProblem(kind)`.

Stats: "Rows", then "Orders" or "SKUs", then "Delimiter". A delimiter reads "Comma  ,", "Semicolon  ;",
"Tab", "Pipe  |", "Mixed", or the bare character. An unknown value is "—", muted.

A folder's name is "{folder name}\  ·  {n} CSVs merged".

### 5.4 Options card

One `.card` with two kit `.form-row`s.

- **Inventory memory:** a kit `.switch` (`role="switch"`, `aria-checked`) with its "On" or "Off" label in
  bold; `memory.text` in `--text-secondary`; `memory.previous` in caption when on. Clicking calls
  `setMemory(!on)`.
- **Allocation strategy:** `role="radiogroup"`, a two-column grid (gap 8) of kit `.radio-card`s:
  - "Multi-item first": "Fills orders that can go out whole before partial ones. A few old orders wait
    longer for stock instead."
  - "Oldest first": "Fills strictly by order date, whatever it contains. No order waits behind a newer one;
    more leave part-filled."

  Clicking, or Space or Enter on a focused card, calls `setStrategy`. Left and Right arrows move focus
  between the two. Under 900px the cards stack.

While `run.locked`, the switch, both radio cards and both Replace buttons are `disabled`, and the cards carry
no `data-file-kind` (§3.4).

### 5.5 Run summary

A `.card` (`aside`), padding 12, a column with a 12px gap.

1. "Run summary" in caption `--text-secondary`, then the headline in label size, bold, line-height 1.35,
   `--text-secondary` unless `summary.ready`.
2. The rows: a `72px minmax(0, 1fr)` grid each, padding `6px 0`, hairlines above the first and under each;
   the key in `--text-secondary`, a muted value in `--text-disabled`.
3. While running: "Working · step {n} of 4" in caption, the step name in bold, and four bars (4px high,
   gap 3): filled `--accent-fill` up to and including the current step, `--border-subtle` after it.
4. The buttons, one row, gap 6:
   - idle: **Run analysis**, primary, full width, `disabled` unless `run.enabled` → `runAnalysis()`;
   - running: a disabled primary **Running…** and a secondary **Cancel** → `cancelRun()`. Cancel is
     `disabled` unless `run.can_cancel`; it reads "Cancelling…" while `run.cancelling`, and on the last
     step its title is "Saving can't be cancelled".
5. The reason in caption: `--text-secondary`, or `--status-danger` when its tone is danger. Hidden when empty.

### 5.6 Kit additions (`gui/web/kit.css`, and the kit sheet)

| class | what it is |
|---|---|
| `.switch` | A button, 32×18, radius 9, a flex row with 1px padding. Off: `--surface-sunken`, `1px solid var(--border)`, knob at the start. `[aria-checked="true"]`: `--accent-fill`, transparent edge, knob at the end (`justify-content: flex-end`; no transform). `.switch-knob`: 14px circle, `--surface` off and `--on-accent` on, `box-shadow: var(--card-shadow)`. `:disabled`: `--control-disabled-bg`, `1px dashed var(--border)`, knob `--text-disabled`, no shadow |
| `.radio-card` | A button: flex, gap 10, padding `10px 12px`, radius 8, `1px solid var(--border)`, `--surface`, text left, wraps. `[aria-checked="true"]`: `--selection-border` edge, `--selection-bg`. `.radio-mark`: 16px circle, `1px solid var(--border)`, `--surface`; checked: `--selection-border` edge and an 8px `--selection-border` dot (`::after`). `.radio-card-title`: bold. `.radio-card-text`: `--text-secondary`. `:disabled`: cursor default; an unchecked one's title and text are `--text-disabled` |
| `.form-row` | A grid, `160px minmax(0, 1fr)`, gap 16, padding 12. `.form-row + .form-row` has a `--border-subtle` top rule. `.form-label`: bold |

`.switch` and `.radio-card` join the kit's `:focus-visible` rule. `tests/web/kit_sheet.html` gains one of
each, in both states and disabled. Phase 5 (Tools) reuses `.form-row`.

### 5.7 Toast and keyboard

The page draws the kit `.toast`: the text and a dismiss button (`id="toast-dismiss"`, × glyph, label
"Dismiss"). It hides after 4 s; a new toast replaces the old one. No Undo, no badge.

Every control is a real `<button>`, in document order: orders card, stock card, switch, the checked radio
card, Run or Cancel. Nothing traps focus.

## 6. Files

### 6.1 The slot record

`mw.orders_slot` and `mw.stock_slot` keep their names and are `FileSlot` records (§4.1), created in
`UIManager` with `on_change=self.refresh_setup`. `check_files_ready` keeps its name and returns
`orders.is_valid and stock.is_valid`; it no longer touches `run_analysis_button` (§3). The
`choose_button.setEnabled(has_session)` lines go: with no session there are no cards.

### 6.2 One route in

`select_orders_file`, `select_stock_file` and `accept_dropped_path` end in one method,
`FileHandler.load_file(kind, path)`:

1. a folder goes to `load_folder(kind, path)`;
2. the path is stored on `mw.{kind}_file_path`;
3. orders: the frame is read for column discovery (today's `select_orders_file` body);
   stock: the file is read with its delimiter (today's check) and the inventory anomaly check runs
   (today's `select_stock_file` body). A dropped stock file skips both today;
4. `validate_file(kind)`.

`select_folder` and `load_folder` stay. With no session open, `load_file` and `load_folder` log a warning
and return (the page shows no cards then, so this guards only a stray call).

### 6.3 What the card needs

- `core.csv_row_stats(path, delimiter, key_column) -> tuple[int, int | None]`: data rows, and distinct
  non-empty values of `key_column` (`None` when the header has no such column), in one `csv.reader` pass.
  The key column is the CSV column mapped to `Order_Number` (orders) or `SKU` (stock).
  `count_csv_rows` stays for its other callers.
- `validate_file` calls `slot.set_loaded(path, rows=, keys=, delimiter=)` with the delimiter it validated
  with, or `slot.set_invalid(path, missing, present, names, rows=, delimiter=)`.
- `validate_multiple_files` returns a fourth value: per valid file, `{"name", "rows", "delimiter"}`.
  `load_folder` passes them as `parts`, with `delimiter` the parts' common delimiter or `"mixed"`, and
  `rows`/`keys` from `csv_row_stats` on the merged file. The `note` is today's summary tail: "2 overlapping
  orders skipped · 1 file skipped", or `""`.

### 6.4 Problems

Each is `slot.set_problem(...)` (or `set_invalid`, which builds one). `{file}` is "orders file" or "stock
file". A problem's link opens Client settings on `fix_page` (`open_settings_window(page=...)`), which
re-validates both files on save, as today.

| cause | title | text | fix page |
|---|---|---|---|
| one mapped column missing | "No {internal} column" | "The {file}'s header row has no “{column}” column, which is mapped to {internal}." | "Orders Mapping" / "Stock Mapping" |
| several missing | "{n} mapped columns missing" | "The {file}'s header row has none of: “{column}” ({internal}), …" | the same |
| the stock file cannot be read | "The stock file couldn't be read" | "It was read with “{delimiter}” as the delimiter. Check the stock delimiter in Client settings › General, then replace the file." | "General" |
| a folder with no CSV | "No CSV files in this folder" | "Choose a folder that holds the exported CSV files." | none |
| a folder with no valid CSV | "None of the {n} files can be used" | "{up to five names}. Each is missing a mapped column." | the mapping page |
| the files could not be validated or merged | "The files weren't merged" | "Details are in Logs." | none |

`{internal}` reads: `Order_Number` "order number", `SKU` "SKU", `Quantity` "quantity", `Shipping_Method`
"shipping method", `Stock` "stock". These replace four `show_error` calls and the Qt slot's invalid face.

**Kept as Qt dialogs:** "Merge N files?" (the preview before a folder merge) and "Use this stock file?"
(the anomaly check). They ask a question; a modal dialog paints above the view.

## 7. Progress and Cancel

### 7.1 `shopify_tool/core.py`

```python
ANALYSIS_STEPS = ("Reading orders and stock", "Checking fulfilment history",
                  "Allocating stock", "Saving results")
CANCELLED = "cancelled"

class AnalysisCancelled(Exception):
    """Raised by a progress callback to stop a run before it saves."""

def run_full_analysis(..., session_path=None, progress: Callable[[int], None] | None = None)
```

`progress(i)` is called, when given, immediately before: step 1 (`i = 0`), step 3 (`1`), step 4 (`2`) and
step 5 (`3`). A callback may raise `AnalysisCancelled`; `run_full_analysis` catches it before its other
handlers, logs "Analysis cancelled", and returns `(False, CANCELLED, None, None)`. Nothing is called after
`progress(3)` returns, so a run that has begun saving always finishes.

What a cancelled run leaves: the input copies in `<session>/input/` and their two keys in
`session_info.json` (step 1), and possibly `memory_baseline.json` (step 2). No analysis state, no reports,
no history, no memory write.

`# ponytail:` cancelling a **re-run** leaves the new input copies beside the old results until the next run
completes. Not guarded: a re-run needs the orders file loaded again, and running once more repairs it.

### 7.2 `gui/actions_handler.py`

- `analysis_progress = Signal(int)`; `self._cancel = threading.Event()`.
- `run_analysis` clears the event, sets `mw._analysis_step = 0` and `mw._analysis_cancelling = False`, and
  passes `progress=self._report_step`. `_report_step(i)` runs on the worker thread: it raises
  `core.AnalysisCancelled` when the event is set, else emits `analysis_progress(i)`.
- `analysis_progress` is connected to a slot that stores the step, calls
  `command_bar.set_step(i, len(core.ANALYSIS_STEPS), core.ANALYSIS_STEPS[i])` and `refresh_setup()`.
- `cancel_analysis()`: while running, sets the event and `_analysis_cancelling`, and refreshes.
- `on_analysis_complete`: a result whose message is `core.CANCELLED` toasts "Analysis cancelled" and
  returns. No error banner.
- `_on_analysis_finished` clears both flags and refreshes.

`MainWindow` connects `setup_bridge.cancelRequested` to `cancel_analysis` and `setup_bridge.runRequested`
to `run_analysis_button.click`.

## 8. Command bar (Qt)

Left to right: the client selector; **New session**; **Open recent**; the session chip; the meta text; a
stretch; the step text; **Running…**; the overflow.

| part | rule |
|---|---|
| `new_session_button` | Always shown. Role `secondary`, the `plus` icon, "New session". Enabled in `NO_SESSION` and `SESSION` |
| `session_button` | Always shown, always reads "Open recent", drawn as today's plain menu button, opens the recent-sessions menu. Enabled in `NO_SESSION` and `SESSION` |
| `session_chip` (new `QLabel`) | The session name as the mockup's chip (mono caption, `surface_raised`, `1px solid border`, radius `radius_md`, 22px high). Shown with a session open (`SESSION`, `RUNNING`) on every screen but Setup |
| `meta_label` | "analysed 14:06 · stock file 19 h old". Shown on Results with a session open |
| `step_label` (was `progress_label`) | "Step 2 of 4" in mono caption `text_secondary`, then the step name in bold caption. Shown in `RUNNING` |
| `running_button` (new) | "Running…", role `primary`, always disabled. Shown in `RUNNING` |

API:

- `set_screen(chip: bool, meta: bool)` replaces `set_results_mode`. `UIManager` calls
  `set_screen(chip=index != 0, meta=index == 1)` on a tab change.
- `set_step(index: int, total: int, name: str)` replaces `set_progress`.
- `set_session_text(text)` feeds the chip. `set_status(role, text)` and `set_stock_age(text)` keep their
  signatures and feed only the meta text.
- Deleted: `action_button`, `set_action`, `bind_action`, `_unbind`, `_forward_action_click`, the event
  filter, `actionTriggered`; `cancel_button`, `cancelRequested`; `open_folder_button`,
  `openFolderRequested`; `status_chip`, `stock_chip`. In `ui_manager.py`: `_SCREEN_ACTIONS` and
  `_bind_screen_action`.
- The ladder keeps its four triggers. Under 700px the step text drops the name and keeps "Step 2 of 4".
  Under 500px New session goes icon-only.

The overflow: under the client's name, **Open session folder** (enabled with a session open; it was the
bar's button); under THIS PC, Server connection… and Keyboard shortcuts…. "New session…" leaves it: the
bar's button is always there now.

`setup_bridge.recentRequested` shows `session_button`'s menu (`showMenu()`).

## 9. Toasts

A Qt toast is a child of the window and cannot paint above a web view (ADR 0007). Phase 2 handled that at
each call site. Now there is one router.

- `gui/components/__init__.py` defines `toast(source, text, *, role="success", action_text="",
  on_action=None)`. When `source.window()` has a `web_toast` and the toast has no action, it calls
  `web_toast(text)`; if that returns `True` the toast is done. Otherwise it calls the shared Qt toast.
- `MainWindow.web_toast(text) -> bool`: when the current tab is a web page (`setup_bridge` for 0,
  `results_bridge` for 1), it calls that bridge's `raise_toast(text)` and returns `True`.
- `gui/settings/window.py` and `gui/settings/sets.py` import `toast` from `gui.components`, not from
  `shared`, so "Settings saved" reaches the router.
- `undo_last_operation`'s visibility check collapses to one `toast(self, message)`.
  `ActionsHandler._results_toast` stays for the undoable Results toasts.

No call site's text changes. Nothing in `shared/` changes.

## 10. Departures from the mockup

| Mockup | Phase 3 | Why |
|---|---|---|
| "No files" with no session: the cards are live and the chip appears with the first file | The no-session panel from `app-shell.html` | Owner, §2 |
| "This run starts from the stock left by the previous run instead of the stock file's numbers" | "A run with no stock file starts from … A loaded stock file is always used as it is." | That is what the code does (`_load_and_validate_files`): memory stands in only when no stock file is loaded |
| With memory on and a stock file loaded, the Stock row reads "From 2026-09-29_2" | "Stock file · 188 SKUs"; "From …" only while memory covers a missing file | The same |
| A stock card with no file is always "Missing" | "From memory" while memory covers it | Run is enabled then; "Missing" would contradict it |
| Steps "Matching 1,204 lines to stock", "Building results"; "Allocating stock — 140 of 312 orders" | The four real steps, no count | Owner, §2; the names say what the code does |
| "Analysis finished · opening Results" for 1.8 s | Dropped | The app opens Results at once; holding the page back to show a line is a delay with no use |
| A spinner in "Running…" | No spinner | Transforms and transitions are banned on both tiers (ADR 0016) |
| The switch knob's own shadow; `opacity` on locked controls | The card shadow token; disabled tokens | Only the two shadow tokens may be a `box-shadow`; opacity is banned |
| 28px controls, pale edges and disabled text | `--control-height` (32px at desk), `--border`, `--text-disabled` | The density token; ADR 0018 |
| The session chip in each page's head | In the page head on Setup; in the bar on every other screen | Browse, Logs and Tools are Qt until phases 4 to 6 and have no page head yet |
| A 44px command bar | 48px | Phase 1's bar height stands |
| Segoe UI, Consolas | Inter and the theme's mono face | The bundled faces both tiers use |
| No scrolling | The page scrolls when the window is short | A real folder merge lists many CSVs |

Kept though the mockup does not draw them: the folder merge's note (overlaps and skipped files), the
"Merge N files?" and "Use this stock file?" dialogs, the unreachable panel, "Cancelling…".

## 11. Tests (test-first; the seams)

| Seam | File | Asserts |
|---|---|---|
| State: views | `test_setup_state.py` (new) | Each of the four views from its inputs; a session that loses the server stays `setup` |
| State: cards | `test_setup_state.py` | Missing, loaded (file and folder with parts and note), problem, and "From memory"; the three stats and their formats ("1,204", "Comma  ,", "Mixed", "—") |
| State: run rule | `test_setup_state.py` | Enabled only with connection, session, valid orders and (valid stock or memory covering); disabled while running; a stock file with a problem is not covered by memory |
| State: copy | `test_setup_state.py` | Every headline, row and reason in §4.3 from the inputs that select it; the session title and meta before and after analysis, today and on another day; both memory lines |
| Slot record | `test_file_slot.py` (rewritten) | `set_loaded`, `set_invalid`, `set_problem` and `clear` set the fields and call `on_change` once each; the two missing-column titles and texts |
| Core: stats | `test_core.py` | `csv_row_stats`: rows and distinct keys for a comma and a semicolon file; quoted newlines are one row; a missing key column gives `None` |
| Core: progress | `test_core.py` | A run calls `progress` with 0, 1, 2, 3 in order; a callback raising `AnalysisCancelled` at 2 returns `(False, CANCELLED, None, None)` and writes no `analysis/` state; `progress=None` still runs |
| Bridge | `test_setup_bridge.py` (new) | Each slot emits its signal with its argument; an unknown `kind` and an unknown strategy are dropped; `set_state` emits once for a change and not for the same dict |
| Web page base | `test_results_bridge.py` | `ResultsBridge` still serves `themeCss` and `toastRaised` (existing tests pass unchanged) |
| Page: views | `test_setup_page.py` (new) | Through a real Chromium: each view shows its panel or the grid; the no-session buttons call `newSession` and `openRecent`; the unreachable button calls `openConnection` |
| Page: cards | `test_setup_page.py` | Badges and their tones; Choose file and Choose folder call their slots with the card's kind; Replace calls `clearFile`; the folder parts list; the problem banner and its link calling `fixProblem`; the Problem card's border colour |
| Page: options | `test_setup_page.py` | The switch's `aria-checked` and label follow the state and a click calls `setMemory`; a radio card click calls `setStrategy`; both are disabled while locked |
| Page: summary | `test_setup_page.py` | Headline, three rows, reason and its danger colour; Run is disabled with `enabled` false and a click calls `runAnalysis`; running shows the step text, four bars with the right number filled, Running… and Cancel; Cancel is disabled on the last step |
| Page: toast | `test_setup_page.py` | `raise_toast` shows the text; `#toast-dismiss` hides it |
| Drop | `test_setup_page.py` | A `QDropEvent` with a file URL over the stock card emits `pathDropped("stock", path)`; over no card, nothing; the page URL does not change |
| Kit | `test_web_kit.py` | On the sheet, in both themes: the switch's two fills, the checked radio card's edge and fill, a disabled switch's dashed edge, the form row's label column width |
| File handler | `test_file_handler.py` (adapted) | A picked and a dropped path both reach `load_file`; a dropped stock file now gets the anomaly check; each row of §6.4 sets its title, text and fix page with no `show_error`; a folder merge fills `parts`, `note` and the common delimiter; with no session nothing loads |
| Run | `test_actions_handler.py` | `run_analysis` passes a `progress`; a progress signal updates the bar and the state; `cancel_analysis` sets the flag; a cancelled result toasts "Analysis cancelled" and raises no error |
| Command bar | `test_commandbar_states.py`, `test_components_commandbar.py` (rewritten where they pin the old bar) | New session is shown in every state, secondary, disabled in `NO_CLIENT` and `RUNNING`; Open recent always reads "Open recent"; the chip follows `set_screen` and the state; the meta text only with `meta`; `RUNNING` shows the step text and a disabled "Running…"; no `action_button`, `cancel_button` or `open_folder_button` |
| Shell | `test_shell.py`, `test_session_setup_layout.py` (rewritten) | Tab 0 holds a `SetupView`; the inset is 0 on Setup and Results and 5 on Browse; the overflow's items in order; `refresh_setup` pushes `no_session` after a client is chosen and `setup` after New session; `recentRequested` opens the menu |
| Toast router | `test_message_routes.py` | On Setup and on Results a `toast(window, …)` reaches that page's bridge and no Qt toast shows; on Browse the Qt toast shows; a toast with an action stays Qt |
| Lint | `test_style_literals_guard.py` | unchanged: `gui/` scans clean with the three new assets |

`test_components_radio_card.py` and `test_screen_primary_actions.py` are deleted with what they test. Every
other test that pins what this spec changes is rewritten to the new behaviour in the same commit as the
change, never skipped.

**Visual check (required, CLAUDE.md):** render the page through `QWebEngineView.grab()` at 1166×720 (the
page area of a 1366×768 window), in light and dark, in each state: no client, no session, unreachable, no
files, orders loaded from a folder, file problem, ready, memory covering, running (step 3), cancelling.
Render the kit sheet in both themes, and `MainWindow` on Setup and on Browse in both themes for the bar.
Compare with `mockups/renders/setup.png` and the mockup's other states opened in Chrome. Save the light
Ready, the dark Running, the light File problem and the light No session under
`docs/design/ui-refresh/renders/phase3/` and attach them to the PR.

**Gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`, then
`graphify update .`.

## 12. Docs

- `CONTEXT.md`:
  - **Web tier**: Results and Setup today.
  - **File slot**: the record holding one of the two input files, with three states (missing, loaded,
    problem), and the only thing that knows whether its file is usable. Add **File card**: the slot as the
    Setup page draws it.
  - Add **Setup state**: the one map Python builds and the Setup page draws; the page decides nothing.
  - Add **Run summary**: the fixed column that says what the run will do, holds Run analysis, and becomes
    the progress view.
  - Add **Step**: one of a run's four named stages. Cancel takes effect between steps and not once saving
    has begun.
  - **Inventory memory**: add that a loaded stock file is always used as it is.
- ADR 0016: under "What would reverse it", the Linux measurement of §2 and that the Windows check is the
  release's. Under Consequences: `SetupBridge` is the second bridge, and `gui/web_page.py` holds what
  bridges share.
- ADR 0007: one router sends a window's toast to the web page that is showing.
- `docs/design/ui-refresh/roadmap.md`: phase 3 gets its spec and plan paths and the differences from the
  list (the no-session panel, four real steps, no count, the chip in the bar off Setup).
- `gui/results_bridge.py`'s docstring: the shared base lives in `gui/web_page.py`.
- `.github/workflows/build_release.yml`: the bundle check also looks for `setup.html`.

## 13. Out of scope

- A per-order count during allocation. Guarding a cancelled re-run. Any change to how memory and the stock
  file interact.
- Browse, Tools, Logs, Client settings. The Qt toast's look. Packing Tool.
- Moving both pages into one view: only if the Windows check says the second view is expensive.

## 14. Delivery

One PR on `cognitiveghost/shopify-fulfillment-tool` from `dr/15-ui-refresh-phase-3-move-setup-to-the-web`.
No Packing Tool PR: nothing in `shared/` changes.

The PR body carries the Windows check, to run on a warehouse PC over RDP with the release build and with
the previous release: in Task Manager's Details tab, add up Memory for the app's own process and every
`QtWebEngineProcess.exe` once the window is idle on Setup, and time the launch to a drawn Setup page. Linux
says about +31 MB and under +0.2 s. If Windows shows much more, say so on the roadmap task before phase 4.
