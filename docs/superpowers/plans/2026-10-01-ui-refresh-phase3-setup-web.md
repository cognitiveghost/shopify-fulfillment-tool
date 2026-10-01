# UI refresh phase 3: Setup on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Qt Setup card with a web page drawn to the approved mockup, in its own
`QWebEngineView`, with file cards, a Run summary that becomes the progress view with Cancel, and the command
bar the mockups draw.

**Architecture:** Python owns every fact and every sentence. One pure function, `setup_state(...)`
(`gui/setup_state.py`), builds a dict; `SetupBridge` (`gui/setup_bridge.py`) carries it to the page as one
`state` property; `gui/web/setup.js` renders it and reports clicks through named slots. The file slot becomes a
plain record. `core.run_full_analysis` gains a `progress` callback that also carries Cancel. The command bar
loses its screen-action mechanism and gains an always-present New session, a session chip and a step readout.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain CSS and JavaScript (no build
step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-01-ui-refresh-phase3-setup-web-design.md`. Read it whole before
starting; this plan argues from it. Copy (every headline, reason, problem text) is in spec §4.3, §4.4, §5.1
and §6.4 and is verbatim.
Mockups: `docs/design/ui-refresh/mockups/setup.html` and `app-shell.html` (render:
`mockups/renders/setup.png`). To read exact values, unpack a bundle with the script in
`docs/design/ui-refresh/mockups/README.md`.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-15` on branch
  `dr/15-ui-refresh-phase-3-move-setup-to-the-web`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other
  Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp dir.
  End every message with the attribution lines your session is given.
- **Baseline:** see "Baseline" just below this list. Every test that passes there must pass after every task,
  unless the task rewrites it.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`, `transform`,
  gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or
  `none`, and only in a `.css` file. Never set `element.style.*` to a colour from JavaScript: use a class.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is `var(--surface-raised)`.
  Type sizes are `var(--type-caption-size)`, `--type-body-size`, `--type-label-size`, `--type-heading-size`.
  The mono face is `var(--font-family-mono)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input, a
  switch or a radio card is `--border`.
- Nothing in `shared/` changes in this plan. Never touch `packing-tool/`.
- No `pyproject.toml`, no new dependency, no unused import (`.venv/bin/ruff check .` must pass).
- No UI call from a worker thread. The analysis runs on a `QThreadPool` thread; it reaches the UI only by
  emitting a Qt signal.
- Never mark a Chromium test skip, and never delete a test without a replacement that pins the new behaviour.
  The two files this plan deletes outright are named in Tasks 7 and 8, with what replaces them.
- The page's static copy lives in `setup.js`; everything that depends on data comes from `setup_state`. Do not
  compute a sentence, a count or an enabled flag in JavaScript.
- The implementer writes no "TODO". A step that cannot be finished is a stop: say what failed.

**Baseline.** Before Task 1, run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and write down the
pass and fail counts. On `origin/main` at d512cb9 the known failures are the three tests in
`tests/test_label_printing.py::TestImageToZpl`; they are not this task's and the PR body mentions them.

## Review Focus

1. **A file that cannot be read at all** (deleted between pick and load, a `.xlsx` renamed to `.csv`, a
   directory entry that vanished from the share). The card shows a Problem saying it could not be read; nothing
   raises, and Run stays disabled (tests in Tasks 3 and 7).
2. **A header-only file.** Zero data rows is a loaded file with "0" rows and "0" orders, never a division or
   an index error in the summary (test in Task 3).
3. **A drop while a run is in progress, or onto no card.** Nothing loads and the page does not navigate to
   the file (test in Task 6).
4. **Cancel pressed twice, or pressed after the run finished.** One cancel; a late one does nothing and leaves
   no "Cancelling…" state behind for the next run (test in Task 9).
5. **A folder with forty CSVs.** The parts list scrolls inside the card at 156px and the card does not push
   the options card off the page (test in Task 6).

## File structure

| File | Task | Responsibility |
|---|---|---|
| `gui/web_page.py` (new) | 1 | `PageBridge`, `mount_page`, `WEB_DIR`, `THEME_MARKER` |
| `gui/results_bridge.py` | 1 | `ResultsBridge(PageBridge)`, `mount_results_page` via `mount_page` |
| `shopify_tool/core.py` | 2 | `csv_row_stats`, `ANALYSIS_STEPS`, `CANCELLED`, `AnalysisCancelled`, `progress=` |
| `gui/setup_state.py` (new) | 3 | `FileSlot`, `SessionFacts`, `MemoryFacts`, `RunFacts`, `setup_state` |
| `gui/web/kit.css`, `tests/web/kit_sheet.html` | 4 | `.switch`, `.radio-card`, `.form-row` |
| `gui/setup_bridge.py` (new) | 5, 6 | `SetupBridge`; then `SetupView`, `mount_setup_page` |
| `gui/web/setup.html`, `setup.css`, `setup.js` (new) | 6 | The page |
| `gui/ui_manager.py`, `gui/file_handler.py`, `gui/main_window_pyside.py` | 7 | Tab 0 hosts the page; `refresh_setup`; one route for files |
| `gui/components/commandbar.py`, `gui/ui_manager.py` | 8 | The bar |
| `gui/actions_handler.py`, `gui/main_window_pyside.py` | 9 | Progress and Cancel |
| `gui/components/__init__.py`, `gui/main_window_pyside.py` | 10 | The toast router |
| Docs, CI, renders | 11 | §12 of the spec, the visual check, the gate |

---

### Task 1: What every page bridge shares (`gui/web_page.py`)

**Files:**
- Create: `gui/web_page.py`, `tests/test_web_page.py`
- Modify: `gui/results_bridge.py`

**Interfaces:**
- Produces: `gui.web_page.WEB_DIR: Path`, `THEME_MARKER: str`,
  `class PageBridge(QObject)` with `themeCss` (Property, notify `themeCssChanged`), `toastRaised = Signal(str, bool)`,
  `set_theme_css(css: str) -> None`, `raise_toast(message: str, undoable: bool = False) -> None`;
  `mount_page(view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str) -> None`.
- `gui.results_bridge` keeps exporting `WEB_DIR`, `THEME_MARKER`, `PAGE`, `CHANNEL_NAME`, `ResultsBridge`,
  `mount_results_page`, `normalize_column_settings`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_page.py`:

```python
"""What every web page's bridge shares (phase 3 spec section 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.results_bridge import ResultsBridge
from gui.web_page import THEME_MARKER, WEB_DIR, PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_a_theme_is_announced_once_per_change():
    bridge = PageBridge()
    seen = []
    bridge.themeCssChanged.connect(lambda: seen.append(bridge.themeCss))
    bridge.set_theme_css(":root { --a: 1 }")
    bridge.set_theme_css(":root { --a: 1 }")
    assert seen == [":root { --a: 1 }"]


def test_a_toast_carries_its_text_and_whether_it_can_be_undone():
    bridge = PageBridge()
    seen = []
    bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    bridge.raise_toast("Saved")
    bridge.raise_toast("3 orders held", undoable=True)
    assert seen == [("Saved", False), ("3 orders held", True)]


def test_the_results_bridge_is_a_page_bridge():
    assert issubclass(ResultsBridge, PageBridge)


def test_the_results_module_still_exports_what_its_tests_import():
    import gui.results_bridge as results

    assert results.WEB_DIR == WEB_DIR
    assert results.THEME_MARKER == THEME_MARKER
    assert results.PAGE == WEB_DIR / "results.html"
```

- [ ] **Step 2: Run it to see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py`
Expected: an import error, `No module named 'gui.web_page'`.

- [ ] **Step 3: Create `gui/web_page.py`**

```python
"""What every web page's bridge shares (ADR 0016, phase 3 spec section 3.2).

A page's bridge extends PageBridge and adds its own named members; mount_page
loads the page into a view with the theme already written into it.
"""

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
THEME_MARKER = "/* theme-vars */"


class PageBridge(QObject):
    """The theme and the toast: the two things every web page is told."""

    themeCssChanged = Signal()
    # JS-facing: the page draws its own toast, because a Qt child widget
    # cannot paint above a web view's surface (ADR 0007).
    toastRaised = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_css = ""

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()

    def raise_toast(self, message: str, undoable: bool = False) -> None:
        self.toastRaised.emit(str(message), bool(undoable))


def mount_page(
    view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str
) -> None:
    """Load `page` into `view` with `bridge` as the object it talks to.

    The theme is written into the page before it loads, so the first paint is
    already themed, then pushed through the bridge on every theme or density
    change, so the document repaints without a reload. The channel is
    parented to `view` and dies with it.
    """
    channel = QWebChannel(view)
    channel.registerObject(channel_name, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        # The manager's tokens rather than the argument: only those carry the
        # bundled Inter family the Qt tier renders in.
        bridge.set_theme_css(theme_css_vars(get_theme_manager().get_current_theme()))

    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
```

- [ ] **Step 4: Move `ResultsBridge` onto it**

In `gui/results_bridge.py`:

1. Replace the import block from `from pathlib import Path` down to `THEME_MARKER = "/* theme-vars */"` with:

```python
from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.orders_view import (
    ORDER_KEY,
    ORDER_LEVEL_COLUMNS,
    classify_columns,
    order_payload,
    results_summary,
)
from gui.web_page import THEME_MARKER, WEB_DIR, PageBridge, mount_page  # noqa: F401

# THEME_MARKER and WEB_DIR are re-exported: tests and tools import them here.
PAGE = WEB_DIR / "results.html"
```

   Keep `CHANNEL_NAME = "results"` under it.

2. `class ResultsBridge(QObject):` becomes `class ResultsBridge(PageBridge):`. Delete from the class:
   the `themeCssChanged = Signal()` line; the `toastRaised = Signal(str, bool)` line and its two-line comment;
   `self._theme_css = ""` in `__init__`; the `_get_theme_css` method and the `themeCss = Property(...)` line;
   the `set_theme_css` method; the `raise_toast` method.

3. Replace the whole `mount_results_page` function with:

```python
def mount_results_page(view: QWebEngineView) -> ResultsBridge:
    """Load the results page into `view` and return the bridge it talks to."""
    bridge = ResultsBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
```

4. At the end of the module docstring's last paragraph add the sentence:
   `The theme and the toast are PageBridge's (gui/web_page.py), shared with every other page's bridge.`

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py tests/test_results_bridge.py tests/test_results_bridge_bulk.py tests/test_results_document.py tests/test_results_toast.py tests/test_web_kit.py`
Expected: all pass. Then `.venv/bin/ruff check gui tests/test_web_page.py`: no findings.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/web_page.py gui/results_bridge.py tests/test_web_page.py`, then commit with the message
`Web tier: PageBridge and mount_page, shared by every page's bridge`.

---

### Task 2: Row stats, steps and Cancel in `core`

**Files:**
- Modify: `shopify_tool/core.py` (near `count_csv_rows`, line ~415; `run_full_analysis`, line ~1418)
- Test: `tests/test_core.py`

**Interfaces:**
- Produces:
  - `core.csv_row_stats(file_path, delimiter=",", key_column=None) -> tuple[int, int | None]`
  - `core.ANALYSIS_STEPS: tuple[str, str, str, str]`
  - `core.CANCELLED = "cancelled"`
  - `class core.AnalysisCancelled(Exception)`
  - `core.run_full_analysis(..., session_path=None, progress=None)`; `progress(i: int)` is called with 0, 1, 2, 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_core.py`:

```python
class TestCsvRowStats:
    def test_rows_and_distinct_keys(self, tmp_path):
        path = tmp_path / "orders.csv"
        path.write_text("Name,Lineitem sku\n#1,A\n#1,B\n#2,A\n")
        assert core.csv_row_stats(path, ",", "Name") == (3, 2)

    def test_a_semicolon_file(self, tmp_path):
        path = tmp_path / "stock.csv"
        path.write_text("Артикул;Наличност\nA;5\nB;0\n", encoding="utf-8")
        assert core.csv_row_stats(path, ";", "Артикул") == (2, 2)

    def test_a_quoted_newline_is_one_row(self, tmp_path):
        path = tmp_path / "orders.csv"
        path.write_text('Name,Note\n#1,"two\nlines"\n#2,x\n')
        assert core.csv_row_stats(path, ",", "Name") == (2, 2)

    def test_a_missing_key_column_counts_rows_only(self, tmp_path):
        path = tmp_path / "orders.csv"
        path.write_text("A,B\n1,2\n")
        assert core.csv_row_stats(path, ",", "Name") == (1, None)
        assert core.csv_row_stats(path, ",", None) == (1, None)

    def test_a_header_only_file_has_no_rows_and_no_keys(self, tmp_path):
        path = tmp_path / "orders.csv"
        path.write_text("Name,Lineitem sku\n")
        assert core.csv_row_stats(path, ",", "Name") == (0, 0)

    def test_a_file_that_is_not_there_is_zero_not_a_crash(self, tmp_path):
        assert core.csv_row_stats(tmp_path / "gone.csv", ",", "Name") == (0, None)


def _run_small_analysis(tmp_path, monkeypatch, progress):
    monkeypatch.setattr(
        core,
        "load_session_signals",
        lambda _pm, _cid: (
            pd.DataFrame(columns=["Order_Number", "Execution_Date", "Session"]),
            None,
        ),
    )
    monkeypatch.setattr(
        fulfillment_history, "get_persistent_data_path", lambda _n: tmp_path / "h.csv"
    )
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A1,1,Standard\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул,Име,Наличност\nA1,Widget,5\n", encoding="utf-8")
    return core.run_full_analysis(
        str(stock),
        str(orders),
        str(tmp_path / "out"),
        ",",
        ",",
        {
            "settings": {"repeat_detection_days": 1},
            "column_mappings": {
                "orders": _ORDERS_MAPPING,
                "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
            },
        },
        progress=progress,
    )


class TestAnalysisProgress:
    def test_there_are_four_named_steps(self):
        assert core.ANALYSIS_STEPS == (
            "Reading orders and stock",
            "Checking fulfilment history",
            "Allocating stock",
            "Saving results",
        )

    def test_a_run_reports_each_step_in_order(self, tmp_path, monkeypatch):
        seen = []
        ok, msg, _df, _stats = _run_small_analysis(tmp_path, monkeypatch, seen.append)
        assert ok, msg
        assert seen == [0, 1, 2, 3]

    def test_a_run_without_a_callback_still_runs(self, tmp_path, monkeypatch):
        ok, msg, _df, _stats = _run_small_analysis(tmp_path, monkeypatch, None)
        assert ok, msg

    def test_a_callback_that_cancels_stops_the_run_before_it_saves(
        self, tmp_path, monkeypatch
    ):
        seen = []

        def cancel_at_allocation(step):
            seen.append(step)
            if step == 2:
                raise core.AnalysisCancelled

        result = _run_small_analysis(tmp_path, monkeypatch, cancel_at_allocation)

        assert result == (False, core.CANCELLED, None, None)
        assert seen == [0, 1, 2]
        out = tmp_path / "out"
        assert not out.exists() or not any(out.iterdir())

    def test_cancelling_at_the_last_checkpoint_still_saves_nothing(
        self, tmp_path, monkeypatch
    ):
        def cancel_before_saving(step):
            if step == 3:
                raise core.AnalysisCancelled

        result = _run_small_analysis(tmp_path, monkeypatch, cancel_before_saving)

        assert result == (False, core.CANCELLED, None, None)
        out = tmp_path / "out"
        assert not out.exists() or not any(out.iterdir())
```

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_core.py`
Expected: the new tests fail with `AttributeError: module 'shopify_tool.core' has no attribute 'csv_row_stats'`
(and `ANALYSIS_STEPS`), and `TypeError: run_full_analysis() got an unexpected keyword argument 'progress'`.

- [ ] **Step 3: Add `csv_row_stats`**

In `shopify_tool/core.py`, directly after the `count_csv_rows` function:

```python
def csv_row_stats(file_path, delimiter=",", key_column=None) -> tuple[int, int | None]:
    """Data rows, and how many distinct values `key_column` holds.

    One csv.reader pass, for the same reasons count_csv_rows gives. The key
    column is the order number for an orders file and the SKU for a stock
    file, so the second number is "orders" or "SKUs". It is None when the
    header has no such column.
    """
    try:
        with open(file_path, encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle, delimiter=delimiter)
            header = [name.strip() for name in next(rows, [])]
            index = header.index(key_column) if key_column in header else None
            count = 0
            keys = set()
            for row in rows:
                if not any(field.strip() for field in row):
                    continue
                count += 1
                if index is not None and index < len(row) and row[index].strip():
                    keys.add(row[index].strip())
            return count, (len(keys) if index is not None else None)
    except Exception:
        logger.exception(f"Could not read row stats from {file_path}")
        return 0, None
```

- [ ] **Step 4: Add the steps, the cancel type and `progress`**

Directly above `def run_full_analysis(`:

```python
# The four stages a run names while it works (phase 3 spec section 7). The
# last one writes; a run that has reached it always finishes.
ANALYSIS_STEPS = (
    "Reading orders and stock",
    "Checking fulfilment history",
    "Allocating stock",
    "Saving results",
)
CANCELLED = "cancelled"


class AnalysisCancelled(Exception):
    """Raised by a progress callback to stop a run before it saves."""
```

In `run_full_analysis`:

1. Add the parameter after `session_path: str | None = None,`:
   `progress: Callable[[int], None] | None = None,`. If `Callable` is not imported in `core.py`, add
   `from collections.abc import Callable` to the imports.
2. Add to the docstring's Args:
   `progress (callable, optional): Called with the index of each step in ANALYSIS_STEPS as it begins. It may raise AnalysisCancelled to stop the run before it saves.`
   and to Returns: `A cancelled run returns (False, CANCELLED, None, None).`
3. Directly after `logger.info("--- Starting Full Analysis Process ---")`:

```python
    def step(index: int) -> None:
        if progress is not None:
            progress(index)
```

4. Inside the `try:`, call it four times, each on the line before the matching comment:
   `step(0)` before `# Step 1: Validate and prepare inputs`;
   `step(1)` before `# Step 3: Load history data`;
   `step(2)` before `# Step 4: Run analysis and apply rules`;
   `step(3)` before `# Step 5: Save results and reports`.
5. Make this the first `except` clause, above `except FileNotFoundError as e:`:

```python
    except AnalysisCancelled:
        # ponytail: cancelling a re-run leaves the new input copies beside the
        # old results until the next run completes. Not guarded: a re-run needs
        # the orders file loaded again, and running once more repairs it.
        logger.info("Analysis cancelled")
        return False, CANCELLED, None, None
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_core.py tests/test_analysis.py`
Expected: all pass. `.venv/bin/ruff check shopify_tool tests/test_core.py`: no findings.

- [ ] **Step 6: Commit**

`/usr/bin/git add shopify_tool/core.py tests/test_core.py`, message
`Analysis: four named steps, a progress callback that can cancel, and csv_row_stats`.

---

### Task 3: The state the page draws (`gui/setup_state.py`)

**Files:**
- Create: `gui/setup_state.py`, `tests/test_setup_state.py`
- Rewrite: `tests/test_file_slot.py`

The Qt widget `gui/components/file_slot.py` stays until Task 7. This task adds the record beside it; the two
share only a class name, in different modules.

**Interfaces:**
- Consumes: `shopify_tool.core.ANALYSIS_STEPS` (Task 2).
- Produces (all in `gui.setup_state`):
  - `FileSlot(kind, on_change=...)` with fields `path, is_valid, name, is_folder, rows, keys, delimiter, parts,
    note, problem, missing_columns, present_columns` and methods
    `set_loaded(path, *, rows=None, keys=None, delimiter="", parts=(), note="", name="")`,
    `set_invalid(path, missing, present, names=None, *, rows=None, delimiter="")`,
    `set_problem(path, title, text, fix_page="")`, `clear()`.
  - `SessionFacts(name, opened, analysed)`, `MemoryFacts(on, skus, session, updated)`,
    `RunFacts(running=False, step=0, cancelling=False)`.
  - `setup_state(*, connected, client, server_path, session, orders, stock, memory, strategy, run, now) -> dict`
    with the shape in spec §4.2.
- Test helpers other tasks import from `tests/test_setup_state.py`: `NOW`, `loaded(kind, **over)`,
  `make_state(**over)`.

- [ ] **Step 1: Write the slot's failing tests**

Replace `tests/test_file_slot.py` entirely:

```python
"""The file slot as a record (phase 3 spec section 4.1).

It replaces the Qt widget of the same name: the facts about one input file,
and the only thing that knows whether that file is usable.
"""

from pathlib import Path

from gui.setup_state import FileSlot


def _slot(kind="orders"):
    calls = []
    return FileSlot(kind, on_change=lambda: calls.append(1)), calls


def test_a_new_slot_is_empty_and_not_valid():
    slot, _ = _slot()
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.problem is None


def test_loading_a_file_makes_the_slot_valid_and_says_so_once():
    slot, calls = _slot()
    slot.set_loaded("/data/acme-orders.csv", rows=1204, keys=312, delimiter=",")
    assert slot.is_valid is True
    assert slot.path == Path("/data/acme-orders.csv")
    assert slot.name == "acme-orders.csv"
    assert (slot.rows, slot.keys, slot.delimiter) == (1204, 312, ",")
    assert slot.is_folder is False
    assert calls == [1]


def test_a_folder_merge_keeps_its_parts_and_its_own_name():
    slot, _ = _slot()
    parts = [{"name": "a.csv", "rows": 512}, {"name": "b.csv", "rows": 480}]
    slot.set_loaded(
        "/tmp/merged_orders.csv",
        rows=992,
        keys=300,
        delimiter="mixed",
        parts=parts,
        note="2 overlapping orders skipped",
        name="exports\\  ·  2 CSVs merged",
    )
    assert slot.is_folder is True
    assert slot.parts == parts
    assert slot.note == "2 overlapping orders skipped"
    assert slot.name == "exports\\  ·  2 CSVs merged"


def test_one_missing_column_names_it_and_what_it_is_mapped_to():
    slot, calls = _slot("orders")
    slot.set_invalid(
        "/data/orders.csv",
        ["Lineitem sku"],
        ["Name", "Total"],
        {"Lineitem sku": "SKU"},
        rows=1204,
        delimiter=",",
    )
    assert slot.is_valid is False
    assert slot.missing_columns == ["Lineitem sku"]
    assert slot.present_columns == ["Name", "Total"]
    assert slot.problem == {
        "title": "No SKU column",
        "text": "The orders file's header row has no “Lineitem sku” column, "
        "which is mapped to SKU.",
        "fix_page": "Orders Mapping",
        "fix_label": "Open Orders Mapping",
    }
    assert (slot.rows, slot.keys, slot.delimiter) == (1204, None, ",")
    assert calls == [1]


def test_several_missing_columns_are_listed():
    slot, _ = _slot("stock")
    slot.set_invalid(
        "/data/stock.csv",
        ["Артикул", "Наличност"],
        ["Име"],
        {"Артикул": "SKU", "Наличност": "Stock"},
    )
    assert slot.problem["title"] == "2 mapped columns missing"
    assert slot.problem["text"] == (
        "The stock file's header row has none of: “Артикул” (SKU), “Наличност” (stock)."
    )
    assert slot.problem["fix_page"] == "Stock Mapping"


def test_a_problem_without_a_fix_has_no_link():
    slot, calls = _slot()
    slot.set_problem(
        "/data/exports",
        "No CSV files in this folder",
        "Choose a folder that holds the exported CSV files.",
    )
    assert slot.is_valid is False
    assert slot.name == "exports"
    assert slot.problem["fix_page"] == ""
    assert slot.problem["fix_label"] == ""
    assert calls == [1]


def test_a_problem_with_a_fix_names_the_page():
    slot, _ = _slot("stock")
    slot.set_problem("/data/stock.csv", "The stock file couldn't be read", "…", "General")
    assert slot.problem["fix_label"] == "Open General"


def test_loading_after_a_problem_forgets_the_problem():
    slot, _ = _slot()
    slot.set_invalid("/data/o.csv", ["Name"], ["X"], {"Name": "Order_Number"})
    slot.set_loaded("/data/o.csv", rows=1, keys=1, delimiter=",")
    assert slot.problem is None
    assert slot.missing_columns == []


def test_clearing_returns_the_slot_to_empty_and_says_so():
    slot, calls = _slot()
    slot.set_loaded("/data/o.csv", rows=1, keys=1, delimiter=",")
    slot.clear()
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.name == ""
    assert calls == [1, 1]
```

- [ ] **Step 2: Write the state's failing tests**

Create `tests/test_setup_state.py`:

```python
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
        "fix_label": "Open Orders Mapping",
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_file_slot.py tests/test_setup_state.py`
Expected: an import error, `No module named 'gui.setup_state'`.

- [ ] **Step 4: Create `gui/setup_state.py`**

```python
"""Everything the Setup page draws, built in one place (phase 3 spec section 4).

Python owns every fact and every sentence: setup_state() returns one dict and
gui/web/setup.js renders it. No Qt in this module, so the whole rule set runs
under plain pytest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from shopify_tool.core import ANALYSIS_STEPS

_FILE = {"orders": "orders file", "stock": "stock file"}
_MAPPING_PAGE = {"orders": "Orders Mapping", "stock": "Stock Mapping"}
# How an internal column name reads in a sentence.
_INTERNAL = {
    "Order_Number": "order number",
    "SKU": "SKU",
    "Quantity": "quantity",
    "Shipping_Method": "shipping method",
    "Stock": "stock",
}
_DELIMITERS = {
    ",": "Comma  ,",
    ";": "Semicolon  ;",
    "\t": "Tab",
    "|": "Pipe  |",
    "mixed": "Mixed",
}
_STRATEGY = {"multi_first": "Multi-item first", "fifo": "Oldest first"}
_DASH = "—"


def _noop() -> None:
    pass


@dataclass
class FileSlot:
    """One of the two input files: where it is and whether it can be used.

    The only thing that knows whether its file is usable. Every mutator ends
    by calling on_change(), which is how the page hears about it.
    """

    kind: str  # "orders" | "stock"
    on_change: Callable[[], None] = _noop
    path: Path | None = None
    is_valid: bool = False
    name: str = ""
    is_folder: bool = False
    rows: int | None = None
    keys: int | None = None  # distinct orders, or distinct SKUs
    delimiter: str = ""  # the character; "mixed"; "" when unknown
    parts: list = field(default_factory=list)  # {"name", "rows"} per merged CSV
    note: str = ""
    problem: dict | None = None  # {"title", "text", "fix_page", "fix_label"}
    missing_columns: list = field(default_factory=list)
    present_columns: list = field(default_factory=list)

    def _reset(self, path) -> None:
        self.path = Path(path) if path is not None else None
        self.is_valid = False
        self.name = self.path.name if self.path is not None else ""
        self.is_folder = False
        self.rows = None
        self.keys = None
        self.delimiter = ""
        self.parts = []
        self.note = ""
        self.problem = None
        self.missing_columns = []
        self.present_columns = []

    def set_loaded(
        self, path, *, rows=None, keys=None, delimiter="", parts=(), note="", name=""
    ) -> None:
        self._reset(path)
        self.is_valid = True
        self.rows = rows
        self.keys = keys
        self.delimiter = delimiter
        self.parts = list(parts)
        self.is_folder = bool(self.parts)
        self.note = note
        if name:
            self.name = name
        self.on_change()

    def set_invalid(
        self, path, missing, present, names=None, *, rows=None, delimiter=""
    ) -> None:
        """The file is readable but lacks columns the mapping needs.

        `names` maps each missing CSV column to the internal name it is
        mapped to, so the sentence can say what the column is for.
        """
        self._reset(path)
        self.missing_columns = list(missing)
        self.present_columns = list(present)
        self.rows = rows
        self.delimiter = delimiter
        names = names or {}

        def internal(column: str) -> str:
            mapped = names.get(column, "")
            return _INTERNAL.get(mapped, mapped or column)

        file = _FILE[self.kind]
        if len(self.missing_columns) == 1:
            column = self.missing_columns[0]
            title = f"No {internal(column)} column"
            text = (
                f"The {file}'s header row has no “{column}” column, "
                f"which is mapped to {internal(column)}."
            )
        else:
            listed = ", ".join(f"“{c}” ({internal(c)})" for c in self.missing_columns)
            title = f"{len(self.missing_columns)} mapped columns missing"
            text = f"The {file}'s header row has none of: {listed}."
        self.problem = _problem(title, text, _MAPPING_PAGE[self.kind])
        self.on_change()

    def set_problem(self, path, title: str, text: str, fix_page: str = "") -> None:
        self._reset(path)
        self.problem = _problem(title, text, fix_page)
        self.on_change()

    def clear(self) -> None:
        self._reset(None)
        self.on_change()


def _problem(title: str, text: str, fix_page: str) -> dict:
    return {
        "title": title,
        "text": text,
        "fix_page": fix_page,
        "fix_label": f"Open {fix_page}" if fix_page else "",
    }


@dataclass(frozen=True)
class SessionFacts:
    name: str
    opened: datetime | None
    analysed: datetime | None


@dataclass(frozen=True)
class MemoryFacts:
    on: bool
    skus: int
    session: str
    updated: datetime | None


@dataclass(frozen=True)
class RunFacts:
    running: bool = False
    step: int = 0
    cancelling: bool = False


def _n(value) -> str:
    return _DASH if value is None else f"{value:,}"


def _when(moment: datetime, now: datetime) -> str:
    local = moment.astimezone()
    if local.date() == now.astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%d %b %H:%M")


def _stat(key: str, value) -> dict:
    return {"k": key, "v": _n(value), "muted": value is None}


def _card(slot: FileSlot, covered: bool) -> dict:
    if slot.path is None:
        return {
            "state": "missing",
            "badge": "From memory" if covered else "Missing",
            "badge_tone": "neutral",
            "name": "",
            "is_folder": False,
            "parts": [],
            "note": "",
            "stats": [],
            "problem": {},
        }
    delimiter = _DELIMITERS.get(slot.delimiter, slot.delimiter)
    problem = slot.problem or {}
    return {
        "state": "loaded" if slot.is_valid else "problem",
        "badge": "Loaded" if slot.is_valid else "Problem",
        "badge_tone": "success" if slot.is_valid else "danger",
        "name": slot.name,
        "is_folder": slot.is_folder,
        "parts": [{"name": p["name"], "rows": _n(p["rows"])} for p in slot.parts],
        "note": slot.note,
        "stats": [
            _stat("Rows", slot.rows),
            _stat("Orders" if slot.kind == "orders" else "SKUs", slot.keys),
            {"k": "Delimiter", "v": delimiter or _DASH, "muted": not delimiter},
        ],
        "problem": (
            {key: problem[key] for key in ("title", "text", "fix_label")}
            if problem
            else {}
        ),
    }


def _problem_row(slot: FileSlot) -> str:
    title = (slot.problem or {}).get("title", "")
    return f"Problem: {title[:1].lower()}{title[1:]}"


def setup_state(
    *,
    connected: bool,
    client: str,
    server_path: str,
    session: SessionFacts | None,
    orders: FileSlot,
    stock: FileSlot,
    memory: MemoryFacts,
    strategy: str,
    run: RunFacts,
    now: datetime,
) -> dict:
    """The one map the Setup page draws. Spec section 4.2 and 4.3."""
    if not connected and session is None:
        view = "unreachable"
    elif not client:
        view = "no_client"
    elif session is None:
        view = "no_session"
    else:
        view = "setup"

    strategy = strategy if strategy in _STRATEGY else "multi_first"
    strategy_title = _STRATEGY[strategy]
    strategy_words = strategy_title[:1].lower() + strategy_title[1:]

    orders_problem = orders.path is not None and not orders.is_valid
    stock_problem = stock.path is not None and not stock.is_valid
    memory_covers = memory.on and memory.skus > 0 and stock.path is None
    stock_ok = stock.is_valid or memory_covers
    ready = orders.is_valid and stock_ok
    analysed = session is not None and session.analysed is not None

    order_count, line_count = _n(orders.keys), _n(orders.rows)
    sku_count = _n(memory.skus if memory_covers else stock.keys)
    stock_phrase = (
        f"last run's stock for {sku_count} SKUs"
        if memory_covers
        else f"stock for {sku_count} SKUs"
    )

    if orders_problem:
        headline = "The orders file needs fixing before this can run"
    elif stock_problem:
        headline = "The stock file needs fixing before this can run"
    elif ready:
        headline = (
            f"{order_count} orders, {line_count} lines, {stock_phrase}, {strategy_words}"
        )
    elif orders.is_valid:
        headline = f"{order_count} orders, {line_count} lines, waiting for the stock file"
    elif stock_ok:
        headline = (
            f"{stock_phrase[:1].upper()}{stock_phrase[1:]}, waiting for the orders file"
        )
    else:
        headline = "Load both files to see what this run will do"

    if orders.is_valid:
        orders_row = f"{order_count} orders · {line_count} lines"
    elif orders_problem:
        orders_row = _problem_row(orders)
    else:
        orders_row = "Not loaded"

    if stock.is_valid:
        stock_row = f"Stock file · {sku_count} SKUs"
    elif memory_covers:
        stock_row = f"From {memory.session or 'memory'} · {sku_count} SKUs"
    elif stock_problem:
        stock_row = _problem_row(stock)
    else:
        stock_row = "Not loaded"

    tone = ""
    if run.running:
        reason = ""
    elif orders_problem:
        reason = "Fix the orders file to run."
    elif stock_problem:
        reason = "Fix the stock file to run."
    elif not orders.is_valid and not stock_ok:
        reason = "Load the orders and stock files to run."
    elif not orders.is_valid:
        reason = "Load the orders file to run."
    elif not stock_ok:
        reason = "Load the stock file to run."
    elif not connected:
        reason = "Server unreachable. Files stay loaded; Retry is in the sidebar."
        tone = "danger"
    elif analysed:
        reason = "Running again replaces this session's results."
    else:
        reason = "Results open when it finishes."

    if session is None:
        session_out = {}
    else:
        moment = session.analysed or session.opened
        verb = "analysed" if analysed else "opened"
        session_out = {
            "name": session.name,
            "title": "Session" if analysed else "New session",
            "meta": f"{client} · {verb} {_when(moment, now)}" if moment else client,
        }

    if not memory.on:
        previous = ""
    elif memory.skus > 0:
        bits = [f"Previous run {memory.session}".strip()]
        if memory.updated is not None:
            bits.append(memory.updated.astimezone().strftime("%d %b %H:%M"))
        bits.append(f"{_n(memory.skus)} SKUs")
        previous = " · ".join(bits)
    else:
        previous = "Nothing is remembered yet. The first run needs a stock file."

    last = len(ANALYSIS_STEPS) - 1
    step = min(max(int(run.step), 0), last)

    return {
        "view": view,
        "client": client,
        "server_path": server_path,
        "session": session_out,
        "files": {
            "orders": _card(orders, False),
            "stock": _card(stock, memory_covers),
        },
        "memory": {
            "on": memory.on,
            "text": (
                f"When on, a run with no stock file starts from the stock {client}'s "
                "previous run left. A loaded stock file is always used as it is."
            ),
            "previous": previous,
        },
        "strategy": strategy,
        "summary": {
            "headline": headline,
            "ready": ready,
            "rows": [
                {"k": "Orders", "v": orders_row, "muted": not orders.is_valid},
                {"k": "Stock", "v": stock_row, "muted": not stock_ok},
                {"k": "Strategy", "v": strategy_title, "muted": False},
            ],
            "reason": reason,
            "reason_tone": tone,
        },
        "run": {
            "enabled": (
                connected and session is not None and not run.running and ready
            ),
            "running": run.running,
            "locked": run.running,
            "step": step,
            "steps": len(ANALYSIS_STEPS),
            "step_name": ANALYSIS_STEPS[step] if run.running else "",
            "can_cancel": run.running and not run.cancelling and step < last,
            "cancelling": run.running and run.cancelling,
        },
    }
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_file_slot.py tests/test_setup_state.py`
Expected: all pass. If a copy assertion fails, fix the code to the spec's sentence, never the test.
`.venv/bin/ruff check gui/setup_state.py tests/test_file_slot.py tests/test_setup_state.py`: no findings.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/setup_state.py tests/test_file_slot.py tests/test_setup_state.py`, message
`Setup: the file slot as a record, and setup_state, the one map the page draws`.

---

### Task 4: Kit: switch, radio card, form row

**Files:**
- Modify: `gui/web/kit.css`, `tests/web/kit_sheet.html`
- Test: `tests/test_web_kit.py`

**Interfaces:**
- Produces the classes Task 6's page uses: `.switch`, `.switch-knob`, `.radio-card`, `.radio-mark`,
  `.radio-card-body`, `.radio-card-title`, `.radio-card-text`, `.form-row`, `.form-label`.

- [ ] **Step 1: Add the components to the kit sheet**

In `tests/web/kit_sheet.html`, add this section as the last child of `<main>`:

```html
  <section class="card" style="grid-column: 1 / -1">
    <h2>Switch, radio cards and form rows</h2>
    <div class="form-row" id="f-row">
      <span class="form-label" id="f-label">Inventory memory</span>
      <div class="row">
        <button id="w-off" class="switch" type="button" role="switch" aria-checked="false" aria-label="Off"><span class="switch-knob"></span></button>
        <button id="w-on" class="switch" type="button" role="switch" aria-checked="true" aria-label="On"><span class="switch-knob"></span></button>
        <button id="w-disabled" class="switch" type="button" role="switch" aria-checked="true" aria-label="Locked" disabled><span class="switch-knob"></span></button>
      </div>
    </div>
    <div class="form-row">
      <span class="form-label">Allocation strategy</span>
      <div class="row" role="radiogroup" aria-label="Allocation strategy">
        <button id="r-on" class="radio-card" type="button" role="radio" aria-checked="true">
          <span class="radio-mark"></span>
          <span class="radio-card-body"><span class="radio-card-title">Multi-item first</span><span class="radio-card-text">Fills orders that can go out whole before partial ones.</span></span>
        </button>
        <button id="r-off" class="radio-card" type="button" role="radio" aria-checked="false">
          <span class="radio-mark"></span>
          <span class="radio-card-body"><span class="radio-card-title">Oldest first</span><span class="radio-card-text">Fills strictly by order date.</span></span>
        </button>
        <button id="r-disabled" class="radio-card" type="button" role="radio" aria-checked="false" disabled>
          <span class="radio-mark"></span>
          <span class="radio-card-body"><span class="radio-card-title" id="r-disabled-title">Locked</span><span class="radio-card-text">While a run is in progress.</span></span>
        </button>
      </div>
    </div>
  </section>
```

(The `style` attribute here holds no colour and no shadow, as the sheet's first `.page-head` already does.)

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_web_kit.py`:

```python
@THEMES
def test_the_switch_takes_the_accent_when_on(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#w-on", "backgroundColor") == _rgb(theme.accent_fill)
    assert _style(qtbot, view, "#w-on", "justifyContent") == "flex-end"
    assert _style(qtbot, view, "#w-on .switch-knob", "backgroundColor") == _rgb(
        theme.on_accent
    )
    assert _style(qtbot, view, "#w-off", "backgroundColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#w-off .switch-knob", "backgroundColor") == _rgb(
        theme.surface
    )
    assert _style(qtbot, view, "#w-off", "width") == "32px"
    assert _style(qtbot, view, "#w-off", "height") == "18px"


@THEMES
def test_a_disabled_switch_is_dashed_and_flat(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#w-disabled", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#w-disabled", "backgroundColor") == _rgb(
        theme.control_disabled_bg
    )
    assert _style(qtbot, view, "#w-disabled .switch-knob", "boxShadow") == "none"


@THEMES
def test_the_checked_radio_card_wears_the_selection_tokens(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#r-on", "borderTopColor") == _rgb(theme.selection_border)
    assert _style(qtbot, view, "#r-on", "backgroundColor") == _rgb(theme.selection_bg)
    assert _style(qtbot, view, "#r-off", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#r-off", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#r-disabled-title", "color") == _rgb(theme.text_disabled)


def test_a_form_row_pins_its_label_column(qtbot):
    view = _sheet(qtbot, LIGHT_THEME)
    assert _style(qtbot, view, "#f-row", "gridTemplateColumns").startswith("160px ")
    assert _style(qtbot, view, "#f-label", "fontWeight") == "700"
```

- [ ] **Step 3: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py`
Expected: the four new tests fail (a `.switch` has no kit rule, so its background is not the accent).

- [ ] **Step 4: Add the rules to `gui/web/kit.css`**

Insert directly above the `/* --- focus ---` comment block:

```css
/* --- switch -------------------------------------------------------------- */

/* A button with role="switch". The knob moves by justify-content: the web
   tier may not transform anything (ADR 0016). */
.switch {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  width: 32px;
  height: 18px;
  padding: 1px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: var(--border);
  cursor: pointer;
}
.switch-knob {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: var(--card-shadow);
}
.switch[aria-checked="true"] {
  justify-content: flex-end;
  background: var(--accent-fill);
}
.switch[aria-checked="true"] .switch-knob { background: var(--on-accent); }
.switch:disabled {
  border: 1px dashed var(--border);
  background: var(--control-disabled-bg);
  cursor: not-allowed;
}
.switch:disabled .switch-knob {
  background: var(--text-disabled);
  box-shadow: none;
}

/* --- radio card ---------------------------------------------------------- */

/* A button with role="radio": a choice that states its consequence. */
.radio-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
}
.radio-card[aria-checked="true"] {
  border-color: var(--selection-border);
  background: var(--selection-bg);
}
.radio-mark {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  margin-top: 1px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
}
.radio-card[aria-checked="true"] .radio-mark { border-color: var(--selection-border); }
.radio-card[aria-checked="true"] .radio-mark::after {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--selection-border);
}
.radio-card-body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.radio-card-title { font-weight: 700; }
.radio-card-text { color: var(--text-secondary); }
.radio-card:disabled { cursor: default; }
.radio-card:disabled:not([aria-checked="true"]) .radio-card-title,
.radio-card:disabled:not([aria-checked="true"]) .radio-card-text {
  color: var(--text-disabled);
}

/* --- form row ------------------------------------------------------------ */

/* A label column and a control: Setup's options, and Tools' cards later. */
.form-row {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 16px;
  padding: 12px;
}
.form-row + .form-row { border-top: 1px solid var(--border-subtle); }
.form-label { padding-top: 2px; font-weight: 700; }
```

In the `/* --- focus ---` rule, add two selectors to the list: `.switch:focus-visible,` and
`.radio-card:focus-visible,`.

Update the file's first comment only if it lists the components by name (it does not today).

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py tests/test_style_literals_guard.py tests/test_style_lint.py`
Expected: all pass.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/web/kit.css tests/web/kit_sheet.html tests/test_web_kit.py`, message
`Web kit: switch, radio card and form row`.

---

### Task 5: `SetupBridge`

**Files:**
- Create: `gui/setup_bridge.py`, `tests/test_setup_bridge.py`

**Interfaces:**
- Consumes: `gui.web_page.PageBridge`, `WEB_DIR` (Task 1).
- Produces: `gui.setup_bridge.SetupBridge(PageBridge)` with
  - Property `state` (`QVariantMap`, notify `stateChanged`), setter `set_state(state: dict) -> None`;
  - slots `chooseFile(str)`, `chooseFolder(str)`, `clearFile(str)`, `fixProblem(str)`, `setMemory(bool)`,
    `setStrategy(str)`, `runAnalysis()`, `cancelRun()`, `newSession()`, `openRecent()`, `openConnection()`;
  - signals `fileRequested(str)`, `folderRequested(str)`, `clearRequested(str)`, `fixRequested(str)`,
    `memoryToggled(bool)`, `strategyChosen(str)`, `runRequested()`, `cancelRequested()`,
    `newSessionRequested()`, `recentRequested()`, `connectionRequested()`.
  - module constants `PAGE`, `CHANNEL_NAME = "setup"`, `KINDS = ("orders", "stock")`,
    `STRATEGIES = ("multi_first", "fifo")`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_setup_bridge.py`:

```python
"""The Setup page's bridge: every message is its own named member (ADR 0001)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.setup_bridge import SetupBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(SetupBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("chooseFile", "fileRequested"),
        ("chooseFolder", "folderRequested"),
        ("clearFile", "clearRequested"),
        ("fixProblem", "fixRequested"),
    ],
)
def test_a_card_slot_carries_its_kind_and_drops_an_unknown_one(slot, signal):
    bridge = SetupBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)("orders")
    getattr(bridge, slot)("stock")
    getattr(bridge, slot)("invoices")
    assert seen == [("orders",), ("stock",)]


def test_the_memory_switch_reports_a_bool():
    bridge = SetupBridge()
    seen = _caught(bridge.memoryToggled)
    bridge.setMemory(True)
    bridge.setMemory(False)
    assert seen == [(True,), (False,)]


def test_a_strategy_is_one_of_two_names():
    bridge = SetupBridge()
    seen = _caught(bridge.strategyChosen)
    bridge.setStrategy("fifo")
    bridge.setStrategy("multi_first")
    bridge.setStrategy("random")
    assert seen == [("fifo",), ("multi_first",)]


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("runAnalysis", "runRequested"),
        ("cancelRun", "cancelRequested"),
        ("newSession", "newSessionRequested"),
        ("openRecent", "recentRequested"),
        ("openConnection", "connectionRequested"),
    ],
)
def test_a_plain_command_emits_its_signal(slot, signal):
    bridge = SetupBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_a_state_is_announced_when_it_changes_and_only_then():
    bridge = SetupBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "setup"})
    assert len(seen) == 2
    assert bridge.state == {"view": "setup"}
```

- [ ] **Step 2: Run it to see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_bridge.py`
Expected: an import error, `No module named 'gui.setup_bridge'`.

- [ ] **Step 3: Create `gui/setup_bridge.py`**

```python
"""The Setup page's bridge (phase 3 spec section 3.3).

Python pushes one `state` map, built by gui/setup_state.py; the page renders
it and reports clicks through the named slots below. The catalogue is the
spec's section 3.3: add a member there before adding it here.
"""

from PySide6.QtCore import Property, Signal, Slot

from gui.web_page import WEB_DIR, PageBridge

PAGE = WEB_DIR / "setup.html"
CHANNEL_NAME = "setup"
KINDS = ("orders", "stock")
STRATEGIES = ("multi_first", "fifo")


class SetupBridge(PageBridge):
    """The Setup page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    fileRequested = Signal(str)
    folderRequested = Signal(str)
    clearRequested = Signal(str)
    fixRequested = Signal(str)
    memoryToggled = Signal(bool)
    strategyChosen = Signal(str)
    runRequested = Signal()
    cancelRequested = Signal()
    newSessionRequested = Signal()
    recentRequested = Signal()
    connectionRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def set_state(self, state: dict) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    # --- in: JS -> Python --------------------------------------------------

    @Slot(str)
    def chooseFile(self, kind) -> None:
        if kind in KINDS:
            self.fileRequested.emit(kind)

    @Slot(str)
    def chooseFolder(self, kind) -> None:
        if kind in KINDS:
            self.folderRequested.emit(kind)

    @Slot(str)
    def clearFile(self, kind) -> None:
        if kind in KINDS:
            self.clearRequested.emit(kind)

    @Slot(str)
    def fixProblem(self, kind) -> None:
        if kind in KINDS:
            self.fixRequested.emit(kind)

    @Slot(bool)
    def setMemory(self, on) -> None:
        self.memoryToggled.emit(bool(on))

    @Slot(str)
    def setStrategy(self, name) -> None:
        # A name, not a verb: an unknown one is dropped rather than guessed.
        if name in STRATEGIES:
            self.strategyChosen.emit(name)

    @Slot()
    def runAnalysis(self) -> None:
        self.runRequested.emit()

    @Slot()
    def cancelRun(self) -> None:
        self.cancelRequested.emit()

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def openRecent(self) -> None:
        self.recentRequested.emit()

    @Slot()
    def openConnection(self) -> None:
        self.connectionRequested.emit()
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_bridge.py`
Expected: all pass. `.venv/bin/ruff check gui/setup_bridge.py tests/test_setup_bridge.py`: no findings.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/setup_bridge.py tests/test_setup_bridge.py`, message
`Setup: SetupBridge, one state map out and eleven named slots in`.

---

### Task 6: The page, its view and its mount

**Files:**
- Create: `gui/web/setup.html`, `gui/web/setup.css`, `gui/web/setup.js`, `tests/test_setup_page.py`
- Modify: `gui/setup_bridge.py` (add `SetupView`, `mount_setup_page`)

Nothing in the app shows this page yet; Task 7 puts it in tab 0. This task ends with the page fully drawn and
tested on its own.

**Interfaces:**
- Consumes: `SetupBridge` (Task 5), `mount_page` (Task 1), the kit classes (Task 4), `setup_state` and the
  helpers `make_state`, `loaded`, `NOW`, `MEMORY` in `tests/test_setup_state.py` (Task 3).
- Produces:
  - `gui.setup_bridge.SetupView(QWebEngineView)` with `pathDropped = Signal(str, str)` (kind, local path);
  - `gui.setup_bridge.mount_setup_page(view: QWebEngineView) -> SetupBridge`;
  - the page sets `document.documentElement.dataset.bridge = "ready"` once connected, and bumps
    `document.documentElement.dataset.renders` (a counter) after every render;
  - DOM contract the tests and Task 7 rely on: `#setup[data-view]`; cards `section[data-card="orders"|"stock"]`
    with `data-state`, and `data-file-kind` only while not locked; every control has `data-act`, one of
    `choose-file`, `choose-folder`, `clear`, `fix`, `memory`, `strategy` (with `data-value`), `run`, `cancel`,
    `new-session`, `open-recent`, `open-connection`; card controls also carry `data-kind`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_page.py`:

```python
"""The Setup page, driven through a real Chromium (phase 3 spec section 5).

The page is a renderer: every test pushes a state built by setup_state() and
reads the DOM back. 1166x720 is the page a 1366x768 window gives. Never mark
skip.
"""

import json

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from test_results_bridge import _eval, _rgb, _until_js
from test_setup_state import MEMORY, loaded, make_state

from gui.setup_bridge import PAGE, SetupView, mount_setup_page
from gui.setup_state import FileSlot, RunFacts
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER


@pytest.fixture
def page(qtbot):
    view = SetupView()
    qtbot.addWidget(view)
    bridge = mount_setup_page(view)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _show(qtbot, view, bridge, state):
    """Push a state and wait for the page to have drawn it."""
    before = _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")
    bridge.set_state(state)
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _disabled(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).disabled")


def _problem_orders():
    slot = FileSlot("orders")
    slot.set_invalid(
        "/d/acme-orders-30-09.csv",
        ["Lineitem sku"],
        ["Name"],
        {"Lineitem sku": "SKU"},
        rows=1204,
        delimiter=",",
    )
    return slot


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="setup.css"')


# --- views -------------------------------------------------------------------


def test_no_client_shows_one_panel_and_no_cards(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(client="", session=None))
    assert _eval(qtbot, view, "document.getElementById('setup').dataset.view") == "no_client"
    assert _text(qtbot, view, ".state-title") == "Choose a client to begin"
    assert _count(qtbot, view, "[data-card]") == 0
    assert _count(qtbot, view, ".state .btn") == 0


def test_no_session_offers_a_new_one_and_a_recent_one(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(session=None))
    assert _text(qtbot, view, ".state-title") == "No session open for ACME"
    assert _text(qtbot, view, ".state-text") == (
        "Start a session for today's orders, or reopen one from this client."
    )
    with qtbot.waitSignal(bridge.newSessionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='new-session']")
    with qtbot.waitSignal(bridge.recentRequested, timeout=5000):
        _click(qtbot, view, "[data-act='open-recent']")
    assert "primary" in _eval(
        qtbot, view, "document.querySelector(\"[data-act='new-session']\").className"
    )


def test_unreachable_names_the_server_and_offers_the_way_out(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(connected=False, client="", session=None))
    assert _text(qtbot, view, ".state-title") == "This PC can't reach the fulfilment server"
    assert _text(qtbot, view, ".state-path") == r"\\fs01\fulfilment"
    with qtbot.waitSignal(bridge.connectionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='open-connection']")


def test_the_setup_view_has_the_head_two_cards_options_and_summary(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, ".page-title") == "New session"
    assert _text(qtbot, view, ".page-head .code") == "2026-09-30_1"
    assert _text(qtbot, view, ".page-meta") == "ACME · opened 14:02"
    assert _count(qtbot, view, "section[data-card]") == 2
    assert _count(qtbot, view, ".form-row") == 2
    assert _style(qtbot, view, ".summary", "width") == "300px"


# --- cards -------------------------------------------------------------------


def test_a_loaded_card_shows_its_badge_name_and_three_stats(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    card = "[data-card='orders']"
    assert _text(qtbot, view, f"{card} .badge") == "Loaded"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{card} .badge", "backgroundColor") == _rgb(
        theme.status_success_bg
    )
    assert _text(qtbot, view, f"{card} .file-name") == "acme-orders-30-09.csv"
    assert _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({card + ' .stat-v'!r})).map(e => e.textContent)",
    ) == ["1,204", "312", "Comma  ,"]
    with qtbot.waitSignal(bridge.clearRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='clear']")
    assert caught.args == ["orders"]


def test_a_missing_card_offers_a_file_and_a_folder(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(stock=FileSlot("stock")))
    card = "[data-card='stock']"
    assert _text(qtbot, view, f"{card} .badge") == "Missing"
    assert _text(qtbot, view, f"{card} .dropzone-text") == (
        "Drop the warehouse stock export here"
    )
    with qtbot.waitSignal(bridge.fileRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='choose-file']")
    assert caught.args == ["stock"]
    with qtbot.waitSignal(bridge.folderRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='choose-folder']")
    assert caught.args == ["stock"]


def test_memory_covering_badges_the_stock_card(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(memory=MEMORY, stock=FileSlot("stock")))
    assert _text(qtbot, view, "[data-card='stock'] .badge") == "From memory"
    assert not _disabled(qtbot, view, "[data-act='run']")


def test_a_folder_card_lists_its_parts_and_scrolls_when_there_are_many(qtbot, page):
    view, bridge = page
    parts = [{"name": f"export-{i:02d}.csv", "rows": 100 + i} for i in range(40)]
    orders = loaded(
        "orders",
        parts=parts,
        note="2 overlapping orders skipped",
        name="exports\\  ·  40 CSVs merged",
    )
    _show(qtbot, view, bridge, make_state(orders=orders))
    card = "[data-card='orders']"
    assert _count(qtbot, view, f"{card} .part") == 40
    assert _text(qtbot, view, f"{card} .part .part-rows") == "100 rows"
    assert _text(qtbot, view, f"{card} .file-note") == "2 overlapping orders skipped"
    assert _eval(
        qtbot, view, f"document.querySelector({card + ' .parts'!r}).clientHeight"
    ) <= 156
    # The options card is still on the page, under the cards, not pushed out.
    assert _eval(
        qtbot,
        view,
        "document.querySelector('.options').getBoundingClientRect().top < 720",
    )


def test_a_problem_card_explains_itself_and_links_to_the_fix(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(orders=_problem_orders()))
    card = "[data-card='orders']"
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, f"{card} .badge") == "Problem"
    assert _style(qtbot, view, card, "borderTopColor") == _rgb(theme.status_danger_border)
    assert _text(qtbot, view, f"{card} .problem-title") == "No SKU column"
    assert "mapped to SKU" in _text(qtbot, view, f"{card} .banner-text")
    assert _text(qtbot, view, f"{card} [data-act='fix']") == "Open Orders Mapping"
    with qtbot.waitSignal(bridge.fixRequested, timeout=5000) as caught:
        _click(qtbot, view, f"{card} [data-act='fix']")
    assert caught.args == ["orders"]


def test_a_problem_without_a_fix_has_no_link(qtbot, page):
    view, bridge = page
    orders = FileSlot("orders")
    orders.set_problem(
        "/d/exports",
        "No CSV files in this folder",
        "Choose a folder that holds the exported CSV files.",
    )
    _show(qtbot, view, bridge, make_state(orders=orders))
    assert _count(qtbot, view, "[data-card='orders'] [data-act='fix']") == 0


# --- options -----------------------------------------------------------------


def test_the_switch_follows_the_state_and_asks_for_the_opposite(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    switch = "[data-act='memory']"
    assert _eval(qtbot, view, f"document.querySelector({switch!r}).getAttribute('aria-checked')") == "false"
    assert _text(qtbot, view, ".memory-state") == "Off"
    assert _count(qtbot, view, ".memory-previous") == 0
    with qtbot.waitSignal(bridge.memoryToggled, timeout=5000) as caught:
        _click(qtbot, view, switch)
    assert caught.args == [True]

    _show(qtbot, view, bridge, make_state(memory=MEMORY))
    assert _eval(qtbot, view, f"document.querySelector({switch!r}).getAttribute('aria-checked')") == "true"
    assert _text(qtbot, view, ".memory-state") == "On"
    assert _text(qtbot, view, ".memory-previous") == (
        "Previous run 2026-09-29_2 · 29 Sep 16:40 · 191 SKUs"
    )


def test_a_radio_card_reports_the_strategy_it_names(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    checked = "document.querySelector(\"[data-act='strategy'][aria-checked='true']\").dataset.value"
    assert _eval(qtbot, view, checked) == "multi_first"
    with qtbot.waitSignal(bridge.strategyChosen, timeout=5000) as caught:
        _click(qtbot, view, "[data-act='strategy'][data-value='fifo']")
    assert caught.args == ["fifo"]
    _show(qtbot, view, bridge, make_state(strategy="fifo"))
    assert _eval(qtbot, view, checked) == "fifo"


def test_an_arrow_key_moves_between_the_two_radio_cards(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _eval(
        qtbot,
        view,
        "(() => { const el = document.querySelector(\"[data-value='multi_first']\");"
        " el.focus();"
        " el.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));"
        " return true; })()",
    )
    assert _eval(qtbot, view, "document.activeElement.dataset.value") == "fifo"


# --- summary -----------------------------------------------------------------


def test_the_summary_reads_the_state(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, ".summary-headline") == (
        "312 orders, 1,204 lines, stock for 188 SKUs, multi-item first"
    )
    assert _style(qtbot, view, ".summary-headline", "color") == _rgb(theme.text)
    assert _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.summary-row')).map(r =>"
        " r.querySelector('.summary-k').textContent + ': ' + r.querySelector('.summary-v').textContent)",
    ) == [
        "Orders: 312 orders · 1,204 lines",
        "Stock: Stock file · 188 SKUs",
        "Strategy: Multi-item first",
    ]
    assert _text(qtbot, view, ".summary-reason") == "Results open when it finishes."
    assert not _disabled(qtbot, view, "[data-act='run']")
    with qtbot.waitSignal(bridge.runRequested, timeout=5000):
        _click(qtbot, view, "[data-act='run']")


def test_run_is_disabled_with_a_reason_until_the_files_are_in(qtbot, page):
    view, bridge = page
    state = make_state(orders=FileSlot("orders"), stock=FileSlot("stock"))
    _show(qtbot, view, bridge, state)
    theme = get_theme_manager().get_current_theme()
    assert _disabled(qtbot, view, "[data-act='run']")
    assert _text(qtbot, view, ".summary-reason") == (
        "Load the orders and stock files to run."
    )
    assert _style(qtbot, view, ".summary-headline", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, ".summary-v.muted", "color") == _rgb(theme.text_disabled)


def test_a_danger_reason_is_drawn_in_the_danger_colour(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(connected=False))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".summary-reason", "color") == _rgb(theme.status_danger)
    assert _disabled(qtbot, view, "[data-act='run']")


def test_running_turns_the_summary_into_the_progress_view(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=2)))
    assert _text(qtbot, view, ".progress-label") == "Working · step 3 of 4"
    assert _text(qtbot, view, ".progress-step") == "Allocating stock"
    assert _count(qtbot, view, ".progress-bar") == 4
    assert _count(qtbot, view, ".progress-bar.done") == 3
    assert _text(qtbot, view, "[data-act='run']") == "Running…"
    assert _disabled(qtbot, view, "[data-act='run']")
    assert _count(qtbot, view, ".summary-reason") == 0
    with qtbot.waitSignal(bridge.cancelRequested, timeout=5000):
        _click(qtbot, view, "[data-act='cancel']")


def test_running_locks_every_input(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=0)))
    for selector in (
        "[data-card='orders'] [data-act='clear']",
        "[data-card='stock'] [data-act='clear']",
        "[data-act='memory']",
        "[data-act='strategy'][data-value='fifo']",
    ):
        assert _disabled(qtbot, view, selector), selector
    assert _count(qtbot, view, "[data-file-kind]") == 0


def test_cancel_is_disabled_once_saving_starts_and_while_cancelling(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=3)))
    assert _disabled(qtbot, view, "[data-act='cancel']")
    assert _eval(qtbot, view, "document.querySelector(\"[data-act='cancel']\").title") == (
        "Saving can't be cancelled"
    )
    _show(
        qtbot, view, bridge, make_state(run=RunFacts(running=True, step=1, cancelling=True))
    )
    assert _disabled(qtbot, view, "[data-act='cancel']")
    assert _text(qtbot, view, "[data-act='cancel']") == "Cancelling…"


def test_a_disabled_control_reports_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(orders=FileSlot("orders")))
    seen = []
    bridge.runRequested.connect(lambda: seen.append(1))
    _click(qtbot, view, "[data-act='run']")
    qtbot.wait(200)
    assert seen == []


# --- toast -------------------------------------------------------------------


def test_the_page_draws_its_own_toast_and_dismisses_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("Session 2026-09-30_1 created.")
    _until_js(qtbot, view, "!document.getElementById('toast').hidden")
    assert _text(qtbot, view, "#toast-text") == "Session 2026-09-30_1 created."
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, "#toast", "backgroundColor") == _rgb(theme.surface_inverse)
    _click(qtbot, view, "#toast-dismiss")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


# --- drop --------------------------------------------------------------------


def _centre(qtbot, view, selector):
    x, y = _json(
        qtbot,
        view,
        f"(() => {{ const r = document.querySelector({selector!r}).getBoundingClientRect();"
        " return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)]; })()",
    )
    return QPointF(x, y)


def _drag_to(view, point, path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    args = (Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(view, QDragEnterEvent(point.toPoint(), *args))
    QApplication.sendEvent(view, QDragMoveEvent(point.toPoint(), *args))
    return mime


def test_a_file_dropped_on_a_card_reaches_python_with_its_kind(qtbot, page, tmp_path):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(stock=FileSlot("stock")))
    dropped = tmp_path / "stock.csv"
    dropped.write_text("x")
    point = _centre(qtbot, view, "[data-card='stock']")
    mime = _drag_to(view, point, dropped)
    _until_js(
        qtbot, view, "!!document.querySelector(\"[data-card='stock'].over\")"
    )
    with qtbot.waitSignal(view.pathDropped, timeout=5000) as caught:
        QApplication.sendEvent(
            view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        )
    assert caught.args == ["stock", str(dropped)]
    # Chromium would otherwise navigate to the file.
    assert _count(qtbot, view, "section[data-card]") == 2
    _until_js(qtbot, view, "!document.querySelector('.over')")


def test_a_drop_on_no_card_or_during_a_run_loads_nothing(qtbot, page, tmp_path):
    view, bridge = page
    dropped = tmp_path / "stock.csv"
    dropped.write_text("x")
    seen = []
    view.pathDropped.connect(lambda kind, path: seen.append((kind, path)))

    _show(qtbot, view, bridge, make_state())
    point = _centre(qtbot, view, ".summary")
    mime = _drag_to(view, point, dropped)
    QApplication.sendEvent(
        view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    )

    _show(qtbot, view, bridge, make_state(run=RunFacts(running=True, step=0)))
    point = _centre(qtbot, view, "[data-card='stock']")
    mime = _drag_to(view, point, dropped)
    QApplication.sendEvent(
        view, QDropEvent(point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    )

    qtbot.wait(600)
    assert seen == []
    assert _count(qtbot, view, "section[data-card]") == 2
```

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_page.py`
Expected: an import error, `cannot import name 'SetupView' from 'gui.setup_bridge'`.

- [ ] **Step 3: Add `SetupView` and `mount_setup_page` to `gui/setup_bridge.py`**

Change the imports to:

```python
from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtGui import QDragLeaveEvent
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page
```

Append to the module:

```python
# Which card is under a point: the page knows its layout, Python does not.
_CARD_AT = (
    "(function () {"
    " var el = document.elementFromPoint(%d, %d);"
    " var card = el && el.closest('[data-file-kind]');"
    " return card ? card.dataset.fileKind : '';"
    " })()"
)


class SetupView(QWebEngineView):
    """The Setup page's view. It takes file drops itself (spec section 3.4).

    Chromium navigates to a dropped file, and a page cannot read a dropped
    file's path. So the drag reaches the page (it highlights the card) and
    the drop stops here: the path comes from the mime data and the card from
    the page.
    """

    pathDropped = Signal(str, str)  # kind, local path

    def dragEnterEvent(self, event) -> None:
        super().dragEnterEvent(event)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        super().dragMoveEvent(event)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        point = event.position().toPoint()
        # Never the base class: that is the navigation. Ending the drag this
        # way sends the page a dragleave, so its highlight clears.
        super().dragLeaveEvent(QDragLeaveEvent())
        if not urls:
            return
        path = urls[0].toLocalFile()
        event.acceptProposedAction()
        self.page().runJavaScript(
            _CARD_AT % (point.x(), point.y()),
            0,
            lambda kind: self._dropped(kind, path),
        )

    def _dropped(self, kind, path: str) -> None:
        if kind in KINDS and path:
            self.pathDropped.emit(kind, path)


def mount_setup_page(view: QWebEngineView) -> SetupBridge:
    """Load the Setup page into `view` and return the bridge it talks to."""
    bridge = SetupBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
```

- [ ] **Step 4: Create `gui/web/setup.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Setup</title>
<!-- gui/web_page.py writes theme_css_vars() over the marker before the page
     loads, then setup.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="setup.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="setup.js" defer></script>
</head>
<body>
<main id="setup" data-view=""></main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toast-text"></span>
  <button id="toast-dismiss" class="toast-close" type="button" aria-label="Dismiss"></button>
</div>
</body>
</html>
```

- [ ] **Step 5: Create `gui/web/setup.css`**

```css
/* The Setup page (phase 3 spec section 5). Layout only: every component is
   the kit's. Every colour is a token from theme_css_vars(). */

#setup {
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 24px;
}

/* --- the three panels ---------------------------------------------------- */

#setup > .state { flex: 1; gap: 8px; }
#setup > .state .state-glyph { width: 28px; height: 28px; }
#setup > .state .state-title { font-size: var(--type-heading-size); }
.state-path {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.state-actions { display: flex; gap: 8px; }

/* --- the grid ------------------------------------------------------------ */

.setup-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
  align-items: start;
}
.setup-main { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.file-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}

/* --- file card ----------------------------------------------------------- */

.file-card { display: flex; flex-direction: column; min-width: 0; }
.file-card[data-state="problem"] { border-color: var(--status-danger-border); }
.file-card.over { border-color: var(--selection-border); }

.file-head { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px 0; }
.file-titles { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.file-title { font-size: var(--type-label-size); font-weight: 700; }
.file-hint { font-size: var(--type-caption-size); color: var(--text-secondary); }

.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin: 10px 12px 12px;
  padding: 18px 12px;
  border: 1px dashed var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface-raised);
  text-align: center;
}
.file-card.over .dropzone {
  border-color: var(--selection-border);
  background: var(--selection-bg);
}
.dropzone-glyph {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: var(--text-secondary);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.dropzone-buttons { display: flex; gap: 6px; }
.dropzone-note { font-size: var(--type-caption-size); color: var(--text-secondary); }

.file-body { display: flex; flex-direction: column; gap: 10px; padding: 10px 12px 12px; }
.file-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.file-row .glyph { width: 16px; height: 16px; color: var(--text-secondary); stroke-width: 1.5; }
.file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-mono);
  font-weight: 700;
  white-space: pre;
  text-overflow: ellipsis;
}

.parts {
  max-height: 156px;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--kit-radius);
}
.part {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 26px;
  padding: 0 8px;
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
}
.part + .part { border-top: 1px solid var(--border-subtle); }
.part-name { flex: 1; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.part-rows { color: var(--text-secondary); white-space: nowrap; }
.file-note { font-size: var(--type-caption-size); color: var(--text-secondary); }

.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.stat { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.stat-k { font-size: var(--type-caption-size); color: var(--text-secondary); }
/* pre: "Comma  ," keeps its two spaces. */
.stat-v { font-family: var(--font-family-mono); font-weight: 700; white-space: pre; }
.stat-v.muted, .summary-v.muted { color: var(--text-disabled); }

.file-card .banner { margin: 0 12px 12px; border-radius: var(--kit-radius); }
.problem-title { font-weight: 700; color: var(--status-danger); }
.file-card .banner .btn.link { align-self: flex-start; }

/* --- options ------------------------------------------------------------- */

.options { display: flex; flex-direction: column; }
.memory { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.memory-toggle { display: flex; align-items: center; gap: 8px; }
.memory-state { font-weight: 700; }
.memory-text { color: var(--text-secondary); }
.memory-previous { font-size: var(--type-caption-size); color: var(--text-secondary); }
.strategies { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }

/* --- run summary --------------------------------------------------------- */

.summary {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}
.summary-head { display: flex; flex-direction: column; gap: 4px; }
.summary-label, .progress-label {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.summary-headline {
  font-size: var(--type-label-size);
  font-weight: 700;
  line-height: 1.35;
  color: var(--text-secondary);
}
.summary-headline.ready { color: var(--text); }
.summary-rows {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border-subtle);
}
.summary-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.summary-k { color: var(--text-secondary); }
.summary-v { min-width: 0; }

.progress { display: flex; flex-direction: column; gap: 4px; }
.progress-step { font-weight: 700; }
.progress-bars { display: flex; gap: 3px; margin-top: 4px; }
.progress-bar { flex: 1; height: 4px; background: var(--border-subtle); }
.progress-bar.done { background: var(--accent-fill); }

.summary-actions { display: flex; gap: 6px; }
.summary-actions .btn.primary { flex: 1; }
.summary-reason { font-size: var(--type-caption-size); color: var(--text-secondary); }
.summary-reason.danger { color: var(--status-danger); }

/* --- a narrow page ------------------------------------------------------- */

@media (max-width: 900px) {
  .file-cards, .strategies { grid-template-columns: minmax(0, 1fr); }
}
```

- [ ] **Step 6: Create `gui/web/setup.js`**

```js
// The Setup page (phase 3 spec section 5). Python builds everything this page
// draws (gui/setup_state.py) and sends it as bridge.state; this file renders
// that map and reports clicks through the bridge's named slots. It decides
// nothing: no sentence, count or enabled flag is computed here.
"use strict";

const TOAST_MS = 4000;

// Lucide glyphs, each as one path.
const GLYPH = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  clipboard: "M9 2h6a1 1 0 0 1 1 1v2a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M12 11h4M12 16h4M8 11h.01M8 16h.01",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  file: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM14 2v4a2 2 0 0 0 2 2h4",
  folder: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
  x: "M18 6 6 18M6 6l12 12",
};

const FILES = {
  orders: {
    title: "Orders file",
    hint: "Shopify orders export · CSV",
    drop: "Drop the Shopify orders export here",
  },
  stock: {
    title: "Stock file",
    hint: "Warehouse stock export · CSV",
    drop: "Drop the warehouse stock export here",
  },
};

const STRATEGIES = [
  {
    value: "multi_first",
    title: "Multi-item first",
    text: "Fills orders that can go out whole before partial ones. A few old orders wait longer for stock instead.",
  },
  {
    value: "fifo",
    title: "Oldest first",
    text: "Fills strictly by order date, whatever it contains. No order waits behind a newer one; more leave part-filled.",
  },
];

const els = {};
const page = { bridge: null, state: null, renders: 0, toastTimer: null };

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function off(disabled) {
  return disabled ? " disabled" : "";
}

// --- the three panels --------------------------------------------------------

function panel(s) {
  if (s.view === "unreachable") {
    return `<div class="state">
      ${svg(GLYPH.alert, "state-glyph")}
      <p class="state-title">This PC can't reach the fulfilment server</p>
      <p class="state-text">Clients, stock files and past sessions all live on the server. Until this PC reaches it, there is nothing to set up.</p>
      <span class="state-path">${esc(s.server_path)}</span>
      <button class="btn secondary" type="button" data-act="open-connection" data-key="open-connection">Server connection…</button>
    </div>`;
  }
  if (s.view === "no_session") {
    return `<div class="state">
      ${svg(GLYPH.clipboard, "state-glyph")}
      <p class="state-title">No session open for ${esc(s.client)}</p>
      <p class="state-text">Start a session for today's orders, or reopen one from this client.</p>
      <div class="state-actions">
        <button class="btn primary" type="button" data-act="new-session" data-key="new-session">New session</button>
        <button class="btn secondary" type="button" data-act="open-recent" data-key="open-recent">Open recent</button>
      </div>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.users, "state-glyph")}
    <p class="state-title">Choose a client to begin</p>
    <p class="state-text">Pick a client in the bar above. Sessions, stock and reports all belong to one client.</p>
  </div>`;
}

// --- file card ---------------------------------------------------------------

function dropzone(kind, locked) {
  return `<div class="dropzone">
    ${svg(GLYPH.upload, "dropzone-glyph")}
    <span class="dropzone-text">${FILES[kind].drop}</span>
    <div class="dropzone-buttons">
      <button class="btn secondary" type="button" data-act="choose-file" data-kind="${kind}" data-key="${kind}-file"${off(locked)}>Choose file…</button>
      <button class="btn secondary" type="button" data-act="choose-folder" data-kind="${kind}" data-key="${kind}-folder"${off(locked)}>Choose folder…</button>
    </div>
    <span class="dropzone-note">A folder merges every CSV in it into one input.</span>
  </div>`;
}

function fileBody(kind, card, locked) {
  const parts = card.parts.length
    ? `<div class="parts">${card.parts
        .map(
          (p) =>
            `<div class="part"><span class="part-name">${esc(p.name)}</span><span class="part-rows">${esc(p.rows)} rows</span></div>`,
        )
        .join("")}</div>`
    : "";
  const note = card.note ? `<span class="file-note">${esc(card.note)}</span>` : "";
  const stats = card.stats
    .map(
      (st) =>
        `<div class="stat"><span class="stat-k">${esc(st.k)}</span><span class="stat-v${st.muted ? " muted" : ""}">${esc(st.v)}</span></div>`,
    )
    .join("");
  return `<div class="file-body">
    <div class="file-row">
      ${svg(card.is_folder ? GLYPH.folder : GLYPH.file, "glyph")}
      <span class="file-name" title="${esc(card.name)}">${esc(card.name)}</span>
      <button class="btn secondary compact" type="button" data-act="clear" data-kind="${kind}" data-key="${kind}-clear"${off(locked)}>Replace</button>
    </div>
    ${parts}${note}
    <div class="stats">${stats}</div>
  </div>`;
}

function problemBlock(kind, problem) {
  const link = problem.fix_label
    ? `<button class="btn link" type="button" data-act="fix" data-kind="${kind}" data-key="${kind}-fix">${esc(problem.fix_label)}</button>`
    : "";
  return `<div class="banner danger" role="alert">
    ${svg(GLYPH.alert, "glyph")}
    <div class="banner-body">
      <span class="problem-title">${esc(problem.title)}</span>
      <span class="banner-text">${esc(problem.text)}</span>
      ${link}
    </div>
  </div>`;
}

function fileCard(kind, card, locked) {
  const body =
    card.state === "missing"
      ? dropzone(kind, locked)
      : fileBody(kind, card, locked) +
        (card.state === "problem" ? problemBlock(kind, card.problem) : "");
  // No data-file-kind while a run holds the inputs: a drop then finds no card.
  const target = locked ? "" : ` data-file-kind="${kind}"`;
  return `<section class="card file-card" data-card="${kind}" data-state="${card.state}"${target} aria-label="${FILES[kind].title}">
    <div class="file-head">
      <div class="file-titles">
        <span class="file-title">${FILES[kind].title}</span>
        <span class="file-hint">${FILES[kind].hint}</span>
      </div>
      <span class="badge ${esc(card.badge_tone)}">${esc(card.badge)}</span>
    </div>
    ${body}
  </section>`;
}

// --- options -----------------------------------------------------------------

function optionsCard(s) {
  const locked = s.run.locked;
  const on = s.memory.on;
  const previous = on && s.memory.previous
    ? `<span class="memory-previous">${esc(s.memory.previous)}</span>`
    : "";
  const radios = STRATEGIES.map((o) => {
    const checked = s.strategy === o.value;
    return `<button class="radio-card" type="button" role="radio" aria-checked="${checked}" tabindex="${checked ? 0 : -1}" data-act="strategy" data-value="${o.value}" data-key="strategy-${o.value}"${off(locked)}>
      <span class="radio-mark"></span>
      <span class="radio-card-body">
        <span class="radio-card-title">${o.title}</span>
        <span class="radio-card-text">${o.text}</span>
      </span>
    </button>`;
  }).join("");
  return `<section class="card options">
    <div class="form-row">
      <span class="form-label" id="memory-label">Inventory memory</span>
      <div class="memory">
        <div class="memory-toggle">
          <button class="switch" type="button" role="switch" aria-checked="${on}" aria-labelledby="memory-label" data-act="memory" data-key="memory"${off(locked)}><span class="switch-knob"></span></button>
          <span class="memory-state">${on ? "On" : "Off"}</span>
        </div>
        <span class="memory-text">${esc(s.memory.text)}</span>
        ${previous}
      </div>
    </div>
    <div class="form-row">
      <span class="form-label" id="strategy-label">Allocation strategy</span>
      <div class="strategies" role="radiogroup" aria-labelledby="strategy-label">${radios}</div>
    </div>
  </section>`;
}

// --- run summary -------------------------------------------------------------

function summaryCard(s) {
  const run = s.run;
  const rows = s.summary.rows
    .map(
      (r) =>
        `<div class="summary-row"><span class="summary-k">${esc(r.k)}</span><span class="summary-v${r.muted ? " muted" : ""}">${esc(r.v)}</span></div>`,
    )
    .join("");
  let progress = "";
  if (run.running) {
    const bars = Array.from(
      { length: run.steps },
      (_, n) => `<span class="progress-bar${n <= run.step ? " done" : ""}"></span>`,
    ).join("");
    progress = `<div class="progress">
      <span class="progress-label">Working · step ${run.step + 1} of ${run.steps}</span>
      <span class="progress-step">${esc(run.step_name)}</span>
      <div class="progress-bars">${bars}</div>
    </div>`;
  }
  const lastStep = run.step >= run.steps - 1;
  const cancel = run.running
    ? `<button class="btn secondary" type="button" data-act="cancel" data-key="cancel" title="${lastStep ? "Saving can't be cancelled" : ""}"${off(!run.can_cancel)}>${run.cancelling ? "Cancelling…" : "Cancel"}</button>`
    : "";
  const reason = s.summary.reason
    ? `<span class="summary-reason${s.summary.reason_tone === "danger" ? " danger" : ""}">${esc(s.summary.reason)}</span>`
    : "";
  return `<aside class="card summary" aria-label="Run summary">
    <div class="summary-head">
      <span class="summary-label">Run summary</span>
      <span class="summary-headline${s.summary.ready ? " ready" : ""}">${esc(s.summary.headline)}</span>
    </div>
    <div class="summary-rows">${rows}</div>
    ${progress}
    <div class="summary-actions">
      <button class="btn primary" type="button" data-act="run" data-key="run"${off(!run.enabled)}>${run.running ? "Running…" : "Run analysis"}</button>
      ${cancel}
    </div>
    ${reason}
  </aside>`;
}

// --- render ------------------------------------------------------------------

function setupView(s) {
  const locked = s.run.locked;
  return `<div class="page-head">
      <span class="page-title">${esc(s.session.title)}</span>
      <span class="code">${esc(s.session.name)}</span>
      <span class="page-meta">${esc(s.session.meta)}</span>
    </div>
    <div class="setup-grid">
      <div class="setup-main">
        <div class="file-cards">
          ${fileCard("orders", s.files.orders, locked)}
          ${fileCard("stock", s.files.stock, locked)}
        </div>
        ${optionsCard(s)}
      </div>
      ${summaryCard(s)}
    </div>`;
}

function render() {
  const s = page.state;
  if (!s || !s.view) return;
  // The whole page is redrawn, so the control that had focus is found again
  // by its key: a click on the switch must not drop focus to the body.
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : null;
  els.setup.dataset.view = s.view;
  els.setup.innerHTML = s.view === "setup" ? setupView(s) : panel(s);
  if (key) {
    const again = els.setup.querySelector(`[data-key="${key}"]`);
    if (again && !again.disabled) again.focus();
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// --- input -------------------------------------------------------------------

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const kind = el.dataset.kind;
  switch (el.dataset.act) {
    case "choose-file": bridge.chooseFile(kind); break;
    case "choose-folder": bridge.chooseFolder(kind); break;
    case "clear": bridge.clearFile(kind); break;
    case "fix": bridge.fixProblem(kind); break;
    case "memory": bridge.setMemory(el.getAttribute("aria-checked") !== "true"); break;
    case "strategy": bridge.setStrategy(el.dataset.value); break;
    case "run": bridge.runAnalysis(); break;
    case "cancel": bridge.cancelRun(); break;
    case "new-session": bridge.newSession(); break;
    case "open-recent": bridge.openRecent(); break;
    case "open-connection": bridge.openConnection(); break;
  }
}

// Arrow keys move between the radio cards; Space and Enter are the button's own.
function onKey(event) {
  const el = event.target.closest('[role="radio"]');
  if (!el) return;
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
  const radios = Array.from(els.setup.querySelectorAll('[role="radio"]:not(:disabled)'));
  if (radios.length < 2) return;
  const step = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
  const next = radios[(radios.indexOf(el) + step + radios.length) % radios.length];
  event.preventDefault();
  next.focus();
}

// The drop itself is the view's (gui/setup_bridge.py, SetupView); the page only
// shows which card would take it.
function markDropTarget(event) {
  const target = event.target.closest ? event.target.closest("[data-file-kind]") : null;
  els.setup.querySelectorAll(".file-card.over").forEach((card) => {
    if (card !== target) card.classList.remove("over");
  });
  if (target) target.classList.add("over");
}

function clearDropTarget() {
  els.setup.querySelectorAll(".file-card.over").forEach((card) => card.classList.remove("over"));
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

// --- boot --------------------------------------------------------------------

function bind() {
  els.setup = document.getElementById("setup");
  els.themeVars = document.getElementById("theme-vars");
  els.toast = document.getElementById("toast");
  els.toastText = document.getElementById("toast-text");
  els.toastDismiss = document.getElementById("toast-dismiss");
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
  els.setup.addEventListener("click", onClick);
  els.setup.addEventListener("keydown", onKey);
  document.addEventListener("dragenter", (event) => { event.preventDefault(); markDropTarget(event); });
  document.addEventListener("dragover", (event) => { event.preventDefault(); markDropTarget(event); });
  document.addEventListener("dragleave", (event) => {
    // Leaving the document, not moving between two of its elements.
    if (!event.relatedTarget) clearDropTarget();
  });
  document.addEventListener("drop", (event) => { event.preventDefault(); clearDropTarget(); });
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.toastRaised.connect((text) => raiseToast(text));
  page.state = bridge.state;
  render();
  window.setupBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 7: Run the page tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_page.py tests/test_setup_bridge.py tests/test_style_literals_guard.py`
Expected: all pass.

If a test fails, read the page before changing anything: `_eval(qtbot, view, "document.getElementById('setup').outerHTML")`
shows what was drawn. Two things to know:
- `_show` waits for the render counter, so a state equal to the previous one never returns. Each test pushes
  a state that differs from the one before it.
- The drop tests send the drag events to the view itself. If `pathDropped` never fires, check that
  `dropEvent` is reached (`QApplication.sendEvent(view, …)` needs the view, not its page).

- [ ] **Step 8: Look at it**

Write a throwaway script under your job's tmp dir (not in the repo) that mounts the page with
`mount_setup_page(SetupView())` at 1166×720, pushes `make_state()` (import it from `tests/test_setup_state.py`
by adding `tests` to `sys.path`), pumps the event loop for 1500 ms, and saves `view.grab()` to a PNG, once in
each theme (`get_theme_manager().set_theme("dark")`). Read both PNGs and compare the light one with
`docs/design/ui-refresh/mockups/renders/setup.png`: card positions, the 300px column, badge, stats, the
switch, the checked radio card, the primary button. Fix what is wrong in `setup.css`. The full visual check
is Task 11; this step catches a broken layout early.

- [ ] **Step 9: Commit**

`/usr/bin/git add gui/setup_bridge.py gui/web/setup.html gui/web/setup.css gui/web/setup.js tests/test_setup_page.py`,
message `Setup: the web page, its view that takes file drops, and its mount`.

---

### Task 7: Put the page in tab 0

This is the swap. After it the Qt setup card is gone, `mw.orders_slot` and `mw.stock_slot` are records, and
the web page is what the operator sees. The command bar is not touched here (Task 8): it still mirrors the
hidden `run_analysis_button`, so for this one commit Run analysis shows in the bar and on the page.

**Files:**
- Modify: `gui/ui_manager.py`, `gui/file_handler.py`, `gui/main_window_pyside.py`, `gui/components/__init__.py`
- Delete: `gui/components/file_slot.py`, `gui/components/radio_card.py`, `tests/test_components_radio_card.py`
  (the radio card's replacement is tested in `tests/test_web_kit.py`, Task 4, and `tests/test_setup_page.py`,
  Task 6)
- Rewrite: `tests/test_session_setup_layout.py`
- Adapt: `tests/test_file_handler.py`, `tests/test_first_run.py`, `tests/test_shell.py`

**Interfaces:**
- Consumes: `FileSlot`, `SessionFacts`, `MemoryFacts`, `RunFacts`, `setup_state` (Task 3); `SetupView`,
  `mount_setup_page`, `SetupBridge`'s signals (Tasks 5, 6); `core.csv_row_stats` (Task 2).
- Produces:
  - `mw.setup_view: SetupView`, `mw.setup_bridge: SetupBridge`, `mw.orders_slot` / `mw.stock_slot: FileSlot` (records);
  - `mw.session_facts: SessionFacts | None`, `mw._analysis_step: int`, `mw._analysis_cancelling: bool`;
  - `UIManager.refresh_setup() -> None`;
  - `FileHandler.load_file(kind: str, path: str) -> None`;
  - `FileHandler.validate_file(file_type, loaded: dict | None = None)`;
  - `FileHandler.validate_multiple_files(...)` returns four values: `(valid_files, invalid_files, total_rows, parts)`.
- Removed from `mw`: `setup_stack`, `setup_state_panel`, `inventory_memory_checkbox`, `strategy_multi_item`,
  `strategy_fifo`, `strategy_group`. Removed from `UIManager`: `_refresh_setup_panel`, `_create_strategy_picker`,
  `_SetupPage`.

- [ ] **Step 1: Rewrite `tests/test_session_setup_layout.py`**

```python
"""Setup is one web page in tab 0 (phase 3 spec sections 3 and 4.5).

What the page draws is tested in test_setup_page.py and what the state says
in test_setup_state.py. This file tests the wiring: the window builds the
state from its own facts and the page's requests reach the handlers.
"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from gui.setup_bridge import SetupView
from gui.setup_state import FileSlot


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


@pytest.fixture
def client_window(main_window):
    """The window with one client loaded, as test_file_handler.py does it."""
    main_window.profile_manager.create_client_profile("acme", "Client Acme")
    main_window.current_client_id = "acme"
    main_window.current_client_config = main_window.profile_manager.load_shopify_config(
        "acme"
    )
    main_window.load_client_config("acme")
    main_window.update_ui_state()
    return main_window


def _state(win):
    return win.setup_bridge.state


def _write_inputs(tmp_path):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
        "#1,A1,2,Standard\n#1,B2,1,Standard\n#2,A1,1,Express\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул;Наличност\nA1;5\nB2;3\n", encoding="utf-8")
    return orders, stock


def test_tab_0_holds_the_setup_view(main_window):
    assert isinstance(main_window.setup_view, SetupView)
    assert main_window.main_tabs.widget(0).findChild(SetupView) is main_window.setup_view


def test_the_qt_setup_card_is_gone(main_window):
    for name in (
        "setup_stack",
        "setup_state_panel",
        "inventory_memory_checkbox",
        "strategy_multi_item",
        "strategy_fifo",
    ):
        assert not hasattr(main_window, name), name


def test_the_slots_are_records(main_window):
    assert isinstance(main_window.orders_slot, FileSlot)
    assert isinstance(main_window.stock_slot, FileSlot)
    assert main_window.orders_slot.kind == "orders"
    assert main_window.stock_slot.kind == "stock"


def test_with_no_client_the_page_asks_for_one(main_window):
    assert _state(main_window)["view"] == "no_client"


def test_a_client_with_no_session_gets_the_no_session_view(client_window):
    state = _state(client_window)
    assert state["view"] == "no_session"
    assert state["client"] == "acme"
    assert client_window.run_analysis_button.isEnabled() is False


def test_new_session_opens_the_cards(client_window):
    client_window.setup_bridge.newSession()
    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["session"]["name"] == Path(client_window.session_path).name
    assert state["session"]["title"] == "New session"
    assert state["session"]["meta"].startswith("acme · opened ")
    assert state["files"]["orders"]["state"] == "missing"


def test_run_follows_the_one_rule(client_window, tmp_path):
    orders, stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()

    client_window.file_handler.load_file("orders", str(orders))
    assert _state(client_window)["files"]["orders"]["state"] == "loaded"
    assert client_window.run_analysis_button.isEnabled() is False

    client_window.file_handler.load_file("stock", str(stock))
    state = _state(client_window)
    assert state["run"]["enabled"] is True
    assert client_window.run_analysis_button.isEnabled() is True
    assert state["summary"]["headline"] == (
        "2 orders, 3 lines, stock for 2 SKUs, multi-item first"
    )
    assert [s["v"] for s in state["files"]["stock"]["stats"]] == ["2", "2", "Semicolon  ;"]


def test_replace_empties_the_card(client_window, tmp_path):
    orders, _stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()
    client_window.file_handler.load_file("orders", str(orders))

    client_window.setup_bridge.clearFile("orders")

    assert client_window.orders_file_path is None
    assert _state(client_window)["files"]["orders"]["state"] == "missing"


def test_losing_the_server_keeps_the_cards_and_stops_run(client_window, tmp_path):
    orders, stock = _write_inputs(tmp_path)
    client_window.setup_bridge.newSession()
    client_window.file_handler.load_file("orders", str(orders))
    client_window.file_handler.load_file("stock", str(stock))

    client_window.profile_manager.is_network_available = False
    client_window.connectionChanged.emit(False)

    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["run"]["enabled"] is False
    assert state["summary"]["reason_tone"] == "danger"
    assert client_window.run_analysis_button.isEnabled() is False


def test_the_page_buttons_reach_the_file_dialogs(client_window, monkeypatch):
    calls = []
    handler = client_window.file_handler
    monkeypatch.setattr(handler, "select_orders_file", lambda: calls.append("orders file"))
    monkeypatch.setattr(handler, "select_stock_file", lambda: calls.append("stock file"))
    monkeypatch.setattr(handler, "select_folder", lambda kind: calls.append(f"{kind} folder"))

    bridge = client_window.setup_bridge
    bridge.chooseFile("orders")
    bridge.chooseFile("stock")
    bridge.chooseFolder("orders")

    assert calls == ["orders file", "stock file", "orders folder"]


def test_a_dropped_path_takes_the_file_route(client_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        client_window.file_handler, "load_file", lambda kind, path: seen.append((kind, path))
    )
    client_window.setup_view.pathDropped.emit("stock", "/d/s.csv")
    assert seen == [("stock", "/d/s.csv")]


def test_the_strategy_is_saved_to_the_client(client_window):
    client_window.setup_bridge.setStrategy("fifo")
    assert client_window.active_profile_config["analysis_mode"] == "fifo"
    assert _state(client_window)["strategy"] == "fifo"
    saved = client_window.profile_manager.load_shopify_config("acme")
    assert saved["analysis_mode"] == "fifo"


def test_the_memory_switch_is_saved_to_the_client(client_window):
    client_window.setup_bridge.setMemory(False)
    assert client_window.active_profile_config["inventory_memory"]["enabled"] is False
    assert _state(client_window)["memory"]["on"] is False
    client_window.setup_bridge.setMemory(True)
    assert _state(client_window)["memory"]["on"] is True


def test_the_fix_link_opens_the_page_the_problem_names(client_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        client_window.actions_handler,
        "open_settings_window",
        lambda page=None: opened.append(page),
    )
    client_window.orders_slot.set_invalid(
        "/d/o.csv", ["Lineitem sku"], ["Name"], {"Lineitem sku": "SKU"}
    )

    client_window.setup_bridge.fixProblem("orders")
    client_window.setup_bridge.fixProblem("stock")  # no problem there: nothing opens

    assert opened == ["Orders Mapping"]


def test_open_recent_from_the_page_opens_the_bars_menu(client_window, monkeypatch):
    shown = []
    monkeypatch.setattr(
        client_window.command_bar.session_button, "showMenu", lambda: shown.append(1)
    )
    client_window.setup_bridge.openRecent()
    assert shown == [1]


def test_the_unreachable_button_opens_the_connection_dialog(client_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        client_window.ui_manager, "_open_connection_settings", lambda: opened.append(1)
    )
    client_window.setup_bridge.openConnection()
    assert opened == [1]


def test_run_from_the_page_clicks_the_hidden_run_button(client_window, monkeypatch):
    """The hidden button is the guard: the page goes through it, never round it."""
    clicks = []
    monkeypatch.setattr(
        client_window.run_analysis_button, "click", lambda: clicks.append(1)
    )
    client_window.setup_bridge.runAnalysis()
    assert clicks == [1]


def test_an_opened_session_brings_its_facts(client_window, tmp_path):
    path = client_window.session_manager.create_session("acme")
    client_window.load_existing_session(path)
    state = _state(client_window)
    assert state["view"] == "setup"
    assert state["session"]["name"] == Path(path).name
```

- [ ] **Step 2: Adapt `tests/test_file_handler.py`**

1. Replace the module docstring with:

```python
"""FileHandler writes the file slot's record; the slot says whether Run may go.

Phase 3 spec section 6: one route for a picked and a dropped path, and every
file failure lands in the slot as a problem, never in a dialog or a banner.
"""
```

2. Add `from unittest.mock import Mock` to the imports.

3. In the `main_window` fixture, after `win.load_client_config("acme")`, add:

```python
    # Files load only into an open session (the page shows no cards without one).
    win.session_path = win.session_manager.create_session("acme")
    win.update_ui_state()
```

4. Every `set_loaded(orders, "1 row")` becomes `set_loaded(orders)` and every `set_loaded(stock, "1 row")`
   becomes `set_loaded(stock)`.

5. In `test_a_stock_file_missing_its_quantity_column_puts_the_slot_in_error`, replace the three assertions
   after `assert slot.missing_columns` with:

```python
    assert slot.problem["title"] == "No stock column"
    assert slot.problem["fix_page"] == "Stock Mapping"
    assert "“Наличност”" in slot.problem["text"]
    assert slot.delimiter == ";"
```

6. In `test_a_dropped_folder_merges_its_csvs_into_the_slot`, replace the two `_loaded_summary` assertions with:

```python
    assert slot.is_folder is True
    assert [p["name"] for p in slot.parts] == ["a.csv", "b.csv"]
    assert [p["rows"] for p in slot.parts] == [1, 1]
    assert (slot.rows, slot.keys, slot.delimiter) == (2, 2, ",")
    assert slot.name == "exports\\  ·  2 CSVs merged"
    assert slot.note == ""
```

7. In `test_a_dropped_missing_file_shows_the_invalid_state_instead_of_raising`, add after the existing assertion:

```python
    assert main_window.orders_slot.problem["title"] == "The orders file couldn't be read"
    assert main_window.orders_slot.problem["fix_page"] == ""
    assert main_window.error_banner.isHidden()
```

8. In `test_a_folder_merge_keeps_repeat_lines_and_reports_overlaps`, replace the four lines from
   `text = main_window.orders_slot._loaded_summary.text()` through the `"1 overlapping order skipped"`
   assertion with:

```python
    slot = main_window.orders_slot
    assert len(slot.parts) == 2
    assert slot.rows == 3
    assert slot.note == "1 overlapping order skipped"
```

9. In `test_clearing_the_stock_slot_keeps_run_analysis_alive_in_memory_mode`, delete the line
   `main_window.session_path = main_window.session_manager.create_session("acme")` (the fixture opens one) and
   the line `main_window.inventory_memory_checkbox.setChecked(True)`.

10. Append these tests:

```python
def test_a_picked_and_a_dropped_path_take_the_same_route(main_window, monkeypatch):
    seen = []
    handler = main_window.file_handler
    monkeypatch.setattr(handler, "load_file", lambda kind, path: seen.append((kind, path)))
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: ("/d/picked.csv", "")
    )

    handler.select_orders_file()
    handler.select_stock_file()
    handler.accept_dropped_path("stock", "/d/dropped.csv")

    assert seen == [
        ("orders", "/d/picked.csv"),
        ("stock", "/d/picked.csv"),
        ("stock", "/d/dropped.csv"),
    ]


def test_a_cancelled_file_dialog_loads_nothing(main_window, monkeypatch):
    seen = []
    handler = main_window.file_handler
    monkeypatch.setattr(handler, "load_file", lambda kind, path: seen.append((kind, path)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    handler.select_orders_file()
    handler.select_stock_file()
    assert seen == []


def test_a_dropped_stock_file_gets_the_anomaly_check(main_window, tmp_path, monkeypatch):
    """A dropped stock file used to skip the check a picked one gets."""
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул;Наличност\nX;1\nY;1\n", encoding="utf-8")
    memory = {"enabled": True, "skus": {"A": 50.0, "B": 50.0}, "total_units": 100}
    main_window.active_profile_config["client_id"] = "acme"
    monkeypatch.setattr(
        main_window.profile_manager, "get_inventory_memory", lambda _client: memory
    )
    asked = []

    def decline(*_args, **kwargs):
        asked.append(kwargs.get("title"))
        return False

    monkeypatch.setattr("gui.file_handler.ConfirmDialog.ask", decline)

    main_window.file_handler.accept_dropped_path("stock", str(stock))

    assert asked == ["Use this stock file?"]
    assert main_window.stock_file_path is None
    assert main_window.stock_slot.path is None


def test_an_unreadable_stock_file_is_a_problem_in_its_card(
    main_window, tmp_path, monkeypatch
):
    stock = tmp_path / "stock.csv"
    stock.write_text("x")
    monkeypatch.setattr(
        "gui.file_handler.pd.read_csv", Mock(side_effect=ValueError("not a csv"))
    )

    main_window.file_handler.load_file("stock", str(stock))

    slot = main_window.stock_slot
    assert slot.is_valid is False
    assert slot.problem["title"] == "The stock file couldn't be read"
    assert "Client settings › General" in slot.problem["text"]
    assert slot.problem["fix_page"] == "General"
    assert main_window.stock_file_path is None
    assert main_window.error_banner.isHidden()


def test_a_folder_with_no_csv_is_a_problem_in_its_card(main_window, tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    slot = main_window.orders_slot
    assert slot.problem["title"] == "No CSV files in this folder"
    assert slot.problem["text"] == "Choose a folder that holds the exported CSV files."
    assert slot.problem["fix_page"] == ""
    assert slot.name == "empty"
    assert main_window.error_banner.isHidden()


def test_a_folder_with_no_valid_csv_names_the_files_and_the_fix(main_window, tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir()
    (folder / "wrong.csv").write_text("A,B\n1,2\n")

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    slot = main_window.orders_slot
    assert slot.problem["title"] == "None of the 1 files can be used"
    assert slot.problem["text"] == "wrong.csv. Each is missing a mapped column."
    assert slot.problem["fix_page"] == "Orders Mapping"


def test_a_folder_that_skips_a_file_says_so(main_window, tmp_path, monkeypatch):
    folder = tmp_path / "exports"
    folder.mkdir()
    header = "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
    (folder / "a.csv").write_text(header + "#1,A1,2,Standard\n")
    (folder / "wrong.csv").write_text("A,B\n1,2\n")
    monkeypatch.setattr(
        main_window.file_handler, "show_file_preview", lambda *a, **k: True
    )

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    slot = main_window.orders_slot
    assert slot.is_valid is True
    assert slot.name == "exports\\  ·  1 CSV merged"
    assert slot.note == "1 file skipped"


def test_with_no_session_nothing_loads(main_window, tmp_path):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A1,2,Standard\n"
    )
    main_window.session_path = None

    main_window.file_handler.load_file("orders", str(orders))
    main_window.file_handler.load_folder("orders", str(tmp_path))

    assert main_window.orders_slot.path is None
    assert main_window.orders_file_path is None


def test_a_loaded_file_counts_its_rows_and_orders(main_window, tmp_path):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
        "#1,A1,2,Standard\n#1,B2,1,Standard\n#2,A1,1,Express\n"
    )

    main_window.file_handler.load_file("orders", str(orders))

    slot = main_window.orders_slot
    assert (slot.rows, slot.keys, slot.delimiter) == (3, 2, ",")
```

- [ ] **Step 3: Adapt `tests/test_first_run.py`**

Replace `test_setup_shows_the_panel_and_names_the_path` and `test_the_one_accent_pixel_is_the_way_out` with:

```python
def test_setup_shows_the_unreachable_view_and_names_the_path(offline_window, unreachable):
    state = offline_window.setup_bridge.state
    assert state["view"] == "unreachable"
    assert state["server_path"] == str(unreachable)


def test_the_way_out_opens_the_connection_dialog(offline_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        offline_window.ui_manager, "_open_connection_settings", lambda: opened.append(1)
    )
    offline_window.setup_bridge.openConnection()
    assert opened == [1]
```

(The panel's words, its one button and its secondary role are asserted in `tests/test_setup_page.py`,
`test_unreachable_names_the_server_and_offers_the_way_out`.)

Replace `test_a_reachable_share_with_no_clients_asks_for_one` and
`test_the_second_beat_has_no_accent_pixel_of_its_own` with:

```python
def test_a_reachable_share_with_no_clients_asks_for_one(online_window):
    assert online_window.is_connected() is True
    assert online_window.setup_bridge.state["view"] == "no_client"


def test_with_no_client_the_selector_has_the_focus(online_window):
    # The action is the selector, so it takes focus; the page's panel has no button.
    assert online_window.command_bar.client_selector.hasFocus()
```

- [ ] **Step 4: Adapt `tests/test_shell.py`**

1. In `test_the_shell_leaves_the_page_the_size_later_screens_assume`: the docstring's second paragraph becomes
   `A Qt page keeps the 5px inset it was laid out against (phase 1 spec section 5.1); Setup is a web page now and has none.`
   Replace the last assertion with:

```python
    assert main_window.main_tabs.width() == 1166  # Setup: a web page, no inset
    main_window.main_tabs.setCurrentIndex(3)  # Logs: a Qt page
    QApplication.processEvents()
    assert main_window.main_tabs.width() == 1156
```

2. In `test_a_web_page_takes_the_page_area_to_its_edges`, the tail that switches to index 0 and expects the
   5px inset must switch to index 3 (Logs) instead: change `main_window.main_tabs.setCurrentIndex(0)` to
   `main_window.main_tabs.setCurrentIndex(3)`. Then add, before that line, the same zero-margin assertion for
   index 0:

```python
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    margins = main_window.page_area.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
```

- [ ] **Step 5: Run the tests to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_setup_layout.py tests/test_file_handler.py tests/test_first_run.py`
Expected: failures (`MainWindow` has no `setup_view`; `set_loaded()` takes no summary; no `load_file`).

- [ ] **Step 6: `gui/file_handler.py`**

1. Imports: `from gui.components import ConfirmDialog` (drop `show_error`: nothing here raises a banner any
   more). Keep the rest.

2. Under `_FOLDER_SCAN_RECURSIVE = True`, add:

```python
# What each kind of file must carry, and the column that counts its orders or
# its SKUs.
_REQUIRED = {
    "orders": ("Order_Number", "SKU", "Quantity", "Shipping_Method"),
    "stock": ("SKU", "Stock"),
}
_KEY = {"orders": "Order_Number", "stock": "SKU"}
# A v1 profile names no columns: these are the defaults it meant.
_V1_COLUMNS = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method",
    },
    "stock": {"Артикул": "SKU", "Наличност": "Stock"},
}
_FILE = {"orders": "orders file", "stock": "stock file"}
_MAPPING_PAGE = {"orders": "Orders Mapping", "stock": "Stock Mapping"}


def _columns(config: dict | None, kind: str) -> dict:
    """CSV column -> internal name, for the columns this client maps."""
    mappings = (config or {}).get("column_mappings", {})
    columns = mappings.get(kind, {})
    if not columns and f"{kind}_required" in mappings:
        return _V1_COLUMNS[kind]
    return columns
```

3. Replace `select_orders_file`, `select_stock_file` (whole methods, down to but not including
   `_check_inventory_anomaly`) with:

```python
    def select_orders_file(self):
        """Opens a file dialog for the orders CSV, then loads what was chosen."""
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Orders File", "", "CSV files (*.csv)"
        )
        if filepath:
            self.load_file("orders", filepath)

    def select_stock_file(self):
        """Opens a file dialog for the stock CSV, then loads what was chosen."""
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Stock File", "", "CSV files (*.csv);;All Files (*)"
        )
        if filepath:
            self.load_file("stock", filepath)

    def load_file(self, kind: str, path: str) -> None:
        """A picked or a dropped path, loaded into its slot. One route for both.

        A folder is a supported gesture, not a malformed file. The file is
        read with the client's delimiter setting: Auto detects it per file,
        an override is used as is.
        """
        if not self.mw.session_path:
            self.log.warning(f"load_file({kind!r}) called with no session open")
            return
        if os.path.isdir(path):
            self.load_folder(kind, path)
            return

        setattr(self.mw, f"{kind}_file_path", path)
        self.log.info(f"{kind} file selected: {path}")
        if kind == "orders":
            # For column discovery in Client settings; a failure here must not
            # fail the load.
            self._remember_orders_dataframe(path)
        elif not self._stock_file_usable(path):
            return
        self.validate_file(kind)

    def _fail(self, kind: str, path, title: str, text: str, fix_page: str = "") -> None:
        """The file cannot be used: say so in its card and forget its path."""
        setattr(self.mw, f"{kind}_file_path", None)
        getattr(self.mw, f"{kind}_slot").set_problem(path, title, text, fix_page)

    def _stock_file_usable(self, path: str) -> bool:
        """Read the stock file once and check it against inventory memory.

        False when it cannot be read (its card says why) or when the operator
        turned it down at the anomaly check (its slot is emptied).
        """
        delimiter = ""
        try:
            delimiter = self._delimiter_for("stock", path)
            # SKU columns as text, so a numeric SKU is not read as a float.
            dtype = {
                column: str
                for column, name in _columns(self.mw.active_profile_config, "stock").items()
                if name == "SKU"
            }
            stock_df = pd.read_csv(
                path, delimiter=delimiter, encoding="utf-8-sig", dtype=dtype
            )
            self.log.info(
                f"Loaded stock CSV with delimiter '{delimiter}': {len(stock_df)} rows"
            )
        except Exception:
            self.log.exception("Failed to load stock CSV")
            self._fail(
                "stock",
                path,
                "The stock file couldn't be read",
                f"It was read with “{delimiter}” as the delimiter. Check the stock "
                "delimiter in Client settings › General, then replace the file.",
                "General",
            )
            return False

        client_id = (self.mw.active_profile_config or {}).get("client_id")
        if client_id and hasattr(self.mw, "profile_manager"):
            try:
                stock_mappings = _columns(self.mw.active_profile_config, "stock")
                # An internal-name view of the stock file for the anomaly check.
                rename_map = {
                    column: name
                    for column, name in stock_mappings.items()
                    if name in ("SKU", "Stock") and column in stock_df.columns
                }
                mapped_df = stock_df.rename(columns=rename_map)

                memory = self.mw.profile_manager.get_inventory_memory(client_id)
                if memory.get("enabled", False):
                    is_anomaly, anomaly_msg = self._check_inventory_anomaly(
                        mapped_df, memory
                    )
                    if is_anomaly and not ConfirmDialog.ask(
                        self.mw,
                        title="Use this stock file?",
                        body=anomaly_msg,
                        verb="Use this stock file",
                    ):
                        self.clear_file("stock")
                        return False
                # Memory is updated with Final Stock after analysis, not on load.
            except Exception as e:
                self.log.warning(f"Inventory memory check/update failed: {e}")
        return True
```

4. Replace `validate_file` and `_summary_for` (both whole methods) with:

```python
    def validate_file(self, file_type, loaded: dict | None = None):
        """Checks a selected CSV for its mapped columns and writes its slot.

        The required column names come from the client's column mappings.
        A valid file loads the slot with its row count, its orders or SKUs
        and its delimiter; anything else is a problem the card explains.

        Args:
            file_type (str): "orders" or "stock".
            loaded (dict, optional): For a folder merge, what the merged file
                cannot say about itself: name, parts, note, delimiter.
        """
        if not self.mw.current_client_id or not self.mw.current_client_config:
            self.log.warning("No client selected or config not loaded")
            return

        path = getattr(self.mw, f"{file_type}_file_path")
        if not path:
            self.log.warning(f"Validation skipped for '{file_type}': path is missing.")
            return

        columns = _columns(self.mw.current_client_config, file_type)
        required_cols = [c for c, name in columns.items() if name in _REQUIRED[file_type]]
        key_column = next(
            (c for c, name in columns.items() if name == _KEY[file_type]), None
        )

        delimiter = self._delimiter_for(file_type, path)
        self.log.info(f"Validating '{file_type}' file: {path}")
        is_valid, missing_cols = core.validate_csv_headers(
            path, required_cols, delimiter
        )

        slot = getattr(self.mw, f"{file_type}_slot")
        if is_valid:
            rows, keys = core.csv_row_stats(path, delimiter, key_column)
            facts = {"rows": rows, "keys": keys, "delimiter": delimiter}
            facts.update(loaded or {})
            slot.set_loaded(path, **facts)
            self.log.info(f"'{file_type}' file is valid.")
            return

        present = core.read_csv_headers(path, delimiter)
        if not present:
            # No header row at all: missing, a directory, not a CSV.
            self._fail(
                file_type,
                path,
                f"The {_FILE[file_type]} couldn't be read",
                "Check that it still exists and is a CSV export, then replace it.",
            )
        else:
            slot.set_invalid(
                path,
                missing_cols,
                present,
                columns,
                rows=core.count_csv_rows(path, delimiter),
                delimiter=delimiter,
            )
        self.log.warning(
            f"'{file_type}' file is invalid. Missing columns: {', '.join(missing_cols)}"
        )
```

5. Replace `check_files_ready` with:

```python
    def check_files_ready(self):
        """Whether both slots hold a usable file.

        Run analysis is gated by setup_state (gui/setup_state.py), which also
        knows that inventory memory can stand in for a stock file; this is
        only the plain question.
        """
        return self.mw.orders_slot.is_valid and self.mw.stock_slot.is_valid
```

6. Replace `clear_file`'s docstring body (keep the code) so it no longer names `check_files_ready`:

```python
    def clear_file(self, file_type: str) -> None:
        """Empty one slot: forget the path, reset the record, re-gate the run."""
        setattr(self.mw, f"{file_type}_file_path", None)
        getattr(self.mw, f"{file_type}_slot").clear()
        self.mw.update_ui_state()
        self.log.info(f"Cleared the {file_type} slot")
```

7. Replace `accept_dropped_path` with:

```python
    def accept_dropped_path(self, file_type: str, path: str) -> None:
        """A file or a folder was dropped on a file card: the same route a pick takes."""
        self.load_file(file_type, path)
```

8. Replace `load_folder` with:

```python
    def load_folder(self, file_type: str, folder_path: str) -> None:
        """Scan, validate, merge and load a folder of CSVs into a slot.

        Split from select_folder so a dropped folder takes the same route as
        a picked one. Every way this can fail ends in the slot's card.
        """
        if not self.mw.session_path:
            self.log.warning(f"load_folder({file_type!r}) called with no session open")
            return
        self.log.info(f"{file_type} folder selected: {folder_path}")

        csv_files = self.scan_folder_for_csv(folder_path, _FOLDER_SCAN_RECURSIVE)
        if not csv_files:
            self._fail(
                file_type,
                folder_path,
                "No CSV files in this folder",
                "Choose a folder that holds the exported CSV files.",
            )
            return

        try:
            valid_files, invalid_files, total_rows, parts = self.validate_multiple_files(
                csv_files, file_type
            )
        except Exception:
            self.log.exception("Error validating files")
            self._fail(
                file_type, folder_path, "The files weren't merged", "Details are in Logs."
            )
            return

        if not valid_files:
            names = ", ".join(os.path.basename(f) for f, _m in invalid_files[:5])
            self._fail(
                file_type,
                folder_path,
                f"None of the {len(csv_files)} files can be used",
                f"{names}. Each is missing a mapped column.",
                _MAPPING_PAGE[file_type],
            )
            return

        if not self.show_file_preview(
            file_type, valid_files, invalid_files, total_rows
        ):
            return  # User cancelled

        try:
            merged_path, _rows, skipped = self.merge_and_save_files(
                valid_files, file_type, folder_path
            )
        except Exception:
            self.log.exception("Failed to merge files")
            self._fail(
                file_type, folder_path, "The files weren't merged", "Details are in Logs."
            )
            return

        if file_type == "orders":
            self.mw.orders_file_path = merged_path
            self.mw.orders_source_files = valid_files
            self._remember_orders_dataframe(merged_path)
        else:
            self.mw.stock_file_path = merged_path
            self.mw.stock_source_files = valid_files

        notes = []
        if skipped:
            noun = "order" if file_type == "orders" else "SKU"
            notes.append(
                f"{skipped} overlapping {noun}{'' if skipped == 1 else 's'} skipped"
            )
        if invalid_files:
            n = len(invalid_files)
            notes.append(f"{n} file{'' if n == 1 else 's'} skipped")
        delimiters = {p["delimiter"] for p in parts}
        count = len(valid_files)

        self.validate_file(
            file_type,
            loaded={
                "name": f"{Path(folder_path).name}\\  ·  "
                f"{count} CSV{'' if count == 1 else 's'} merged",
                "parts": [{"name": p["name"], "rows": p["rows"]} for p in parts],
                "note": " · ".join(notes),
                "delimiter": delimiters.pop() if len(delimiters) == 1 else "mixed",
            },
        )
        self.log.info(f"Successfully merged {count} files into {merged_path}")
```

9. In `validate_multiple_files`: change the return annotation to
   `tuple[list[str], list[tuple[str, list[str]]], int, list[dict]]`; add `parts = []` beside `total_rows = 0`;
   replace the block that builds `required_csv_cols` (from `# Get config` to the list comprehension) with:

```python
        mappings = _columns(self.mw.active_profile_config, file_type)
        required_csv_cols = [
            csv_col for csv_col, name in mappings.items() if name in _REQUIRED[file_type]
        ]
```

   after `total_rows += len(df)` add:

```python
                    parts.append(
                        {
                            "name": os.path.basename(filepath),
                            "rows": len(df),
                            "delimiter": file_delimiter,
                        }
                    )
```

   and make the return `return valid_files, invalid_files, total_rows, parts`. Update its docstring's Returns
   to list the fourth value: `parts: per valid file, its name, rows and delimiter`.

10. Update the class docstring's first paragraph only if it mentions a status label (it does not). Leave
    `select_folder`, `_remember_orders_dataframe`, `scan_folder_for_csv`, `show_file_preview`,
    `merge_and_save_files` and `_check_inventory_anomaly` as they are.

- [ ] **Step 7: `gui/ui_manager.py`**

1. Imports. Remove `QCheckBox` from the `PySide6.QtWidgets` import and remove
   `from shared.components.state_panel import StatePanel`. Add:

```python
from gui.setup_state import FileSlot, MemoryFacts, RunFacts, SessionFacts, setup_state
```

2. Delete the constants `_SETUP_LABEL_GUTTER` and `_SETUP_CARD_MAX_WIDTH` with their comment, and the whole
   `_SetupPage` class.

3. `_WEB_PAGES = frozenset({1})` becomes `_WEB_PAGES = frozenset({0, 1})`.

4. Under `age_text`, add:

```python
def _parse_time(text) -> datetime | None:
    """An ISO timestamp from a JSON file, as a local aware datetime, or None."""
    try:
        moment = datetime.fromisoformat(text or "")
    except (TypeError, ValueError):
        return None
    return moment.astimezone()
```

5. In `_on_connection_changed`, replace

```python
        self._refresh_setup_panel()
        self.mw.setup_stack.setCurrentIndex(
            1 if connected and self.mw.current_client_id else 0
        )
```

   with

```python
        self.refresh_setup()
        # With no client the selector is the thing to act on, so it takes focus.
        if connected and not self.mw.current_client_id:
            self.mw.command_bar.client_selector.setFocus()
```

6. Replace `_create_tab1_session_setup`, `_create_strategy_picker` and `_refresh_setup_panel` (three whole
   methods) with:

```python
    def _create_tab1_session_setup(self):
        """Setup: one QWebEngineView, no Qt inside (phase 3 spec).

        Everything drawn on this screen is in gui/web/setup.*; what it draws
        is built by refresh_setup(). The two slots are records the file
        handler writes and setup_state reads.
        """
        from gui.setup_bridge import SetupView, mount_setup_page

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mw.orders_slot = FileSlot("orders", on_change=self.refresh_setup)
        self.mw.stock_slot = FileSlot("stock", on_change=self.refresh_setup)

        # Never shown. Its enabled state is the guard (refresh_setup sets it),
        # and the page's Run analysis, Ctrl+R and Results' "Run analysis
        # again" all click it.
        self.mw.run_analysis_button = QPushButton("Run analysis", tab)
        self.mw.run_analysis_button.setEnabled(False)
        self.mw.run_analysis_button.hide()

        # Written by update_session_info_label() for compatibility; never shown.
        self.mw.session_path_label = QLabel("No session", tab)
        self.mw.session_path_label.hide()

        view = SetupView(tab)
        self.mw.setup_view = view
        self.mw.setup_bridge = mount_setup_page(view)
        layout.addWidget(view, 1)
        return tab

    def refresh_setup(self) -> None:
        """Build the Setup page's state from the window's facts and push it.

        The one place Run analysis is gated (phase 3 spec section 4.3). Never
        touches the share: the session's times are read where
        update_session_chips already reads them.
        """
        mw = self.mw
        if not hasattr(mw, "setup_bridge"):
            return  # asked before the page was mounted
        config = mw.active_profile_config or {}
        memory = config.get("inventory_memory") or {}

        session = None
        if mw.session_path:
            name = Path(mw.session_path).name
            facts = mw.session_facts
            session = (
                facts
                if facts is not None and facts.name == name
                else SessionFacts(name, None, None)
            )

        state = setup_state(
            connected=mw.is_connected(),
            client=mw.current_client_id or "",
            server_path=str(mw.profile_manager.base_path),
            session=session,
            orders=mw.orders_slot,
            stock=mw.stock_slot,
            memory=MemoryFacts(
                on=bool(memory.get("enabled", True)),
                skus=len(memory.get("skus") or {}),
                session=memory.get("session") or "",
                updated=_parse_time(memory.get("last_updated")),
            ),
            strategy=config.get("analysis_mode", "multi_first"),
            run=RunFacts(
                mw._analysis_running, mw._analysis_step, mw._analysis_cancelling
            ),
            now=datetime.now().astimezone(),
        )
        mw.run_analysis_button.setEnabled(state["run"]["enabled"])
        mw.setup_bridge.set_state(state)
```

7. Replace `update_session_chips` with:

```python
    def update_session_chips(self) -> None:
        """What the bar and the Setup page say about the open session's times.

        `Analysed 09:33` and `Stock file 19 h old` for the bar; when the
        session was opened and analysed for the page. Stock age is measured at
        analysis time, not now: it qualifies the analysis. The stock copy in
        the session keeps the source file's mtime (shutil.copy2 in core.py).
        """
        bar = self.mw.command_bar
        session_path = getattr(self.mw, "session_path", None)
        info = (
            self.mw.session_manager.get_session_info(session_path)
            if session_path
            else None
        ) or {}
        analysed = _parse_time(info.get("analysis_completed_at"))
        # The one read of session_info.json: refresh_setup never touches the share.
        self.mw.session_facts = (
            SessionFacts(
                Path(session_path).name, _parse_time(info.get("created_at")), analysed
            )
            if session_path
            else None
        )
        try:
            if analysed is None:
                bar.set_status("text_secondary", "")
                bar.set_stock_age("")
                return
            bar.set_status("text_secondary", f"Analysed {analysed.strftime('%H:%M')}")
            stock = (
                Path(self.mw.session_manager.get_input_dir(session_path))
                / "inventory.csv"
            )
            try:
                copied = datetime.fromtimestamp(stock.stat().st_mtime, tz=UTC)
            except OSError:
                bar.set_stock_age("")
                return
            bar.set_stock_age(f"Stock file {age_text(analysed - copied)} old")
        finally:
            self.refresh_setup()
```

8. In `set_ui_busy`, replace `self.mw.run_analysis_button.setEnabled(not is_busy)` with
   `self.refresh_setup()`: the state knows whether a run is in progress, and one rule gates the button.

9. In `_create_tabs`, the loop over `_SCREEN_ACTIONS` that hides in-page buttons stays for now (Task 8 removes
   it); `run_analysis_button` is already hidden.

- [ ] **Step 8: `gui/main_window_pyside.py`**

1. In `__init__`, directly after `self._analysis_running = False  # Guard against duplicate analysis runs`:

```python
        self._analysis_step = 0  # index into core.ANALYSIS_STEPS while a run is going
        self._analysis_cancelling = False
        # The open session's name and times, read by update_session_chips.
        self.session_facts = None
```

2. In `load_client_config`:
   - delete the block that begins `# Sync the strategy radios` (through the two `blockSignals(False)` lines);
   - replace

```python
                self.ui_manager._refresh_setup_panel()
                self.setup_stack.setCurrentIndex(
                    1 if self.is_connected() and self.current_client_id else 0
                )
```

     with `self.ui_manager.refresh_setup()`;
   - delete the block that begins `# Restore inventory memory checkbox state from config`;
   - delete the block that begins `# Disable starting a new file pick until a session exists` (the four
     `choose_button` / `choose_folder_button` lines);
   - delete the line `self.run_analysis_button.setEnabled(False)` under `# Disable report buttons until new analysis`
     (refresh_setup gates it); keep the comment and the lines after it.

3. In `connect_signals`, replace the whole `for slot, kind in (...)` loop (from `for slot, kind in (` through
   the `slot.clearRequested.connect(...)` line) with:

```python
        # The Setup page's requests. Lambdas, so each handler is looked up when
        # the request arrives.
        setup = self.setup_bridge
        setup.fileRequested.connect(
            lambda kind: getattr(self.file_handler, f"select_{kind}_file")()
        )
        setup.folderRequested.connect(lambda kind: self.file_handler.select_folder(kind))
        setup.clearRequested.connect(lambda kind: self.file_handler.clear_file(kind))
        setup.fixRequested.connect(self._fix_file_problem)
        setup.memoryToggled.connect(self._on_inventory_memory_toggled)
        setup.strategyChosen.connect(
            lambda name: self._on_analysis_mode_changed(1 if name == "fifo" else 0)
        )
        setup.runRequested.connect(lambda: self.run_analysis_button.click())
        setup.newSessionRequested.connect(
            lambda: self.actions_handler.create_new_session()
        )
        setup.recentRequested.connect(
            lambda: self.command_bar.session_button.showMenu()
        )
        setup.connectionRequested.connect(
            lambda: self.ui_manager._open_connection_settings()
        )
        self.setup_view.pathDropped.connect(
            lambda kind, path: self.file_handler.accept_dropped_path(kind, path)
        )
```

   and delete the block

```python
        # Inventory memory toggle
        if hasattr(self, "inventory_memory_checkbox"):
            self.inventory_memory_checkbox.stateChanged.connect(
                self._on_inventory_memory_toggled
            )
```

4. Add this method after `_focus_results_search`:

```python
    def _fix_file_problem(self, kind: str) -> None:
        """The link under a file card's problem: open the page that fixes it."""
        page = (getattr(self, f"{kind}_slot").problem or {}).get("fix_page")
        if page:
            self.actions_handler.open_settings_window(page=page)
```

5. In `update_ui_state`: delete from the comment `# File loading -- gate the pick, not the whole slot` through
   the `self.run_analysis_button.setEnabled(...)` call that ends the memory rule (the four `choose_button`
   lines, the `inv_memory_has_skus` expression and the `setEnabled` call). The unused locals `has_orders`
   goes too if nothing else reads it (`has_stock` is still read by `add_product_button_tab2`). Make the
   method's last two lines:

```python
        self.ui_manager._refresh_nav()
        self.ui_manager.refresh_setup()
```

6. `_on_inventory_memory_toggled(self, state: int)`: change the signature to `(self, enabled: bool)`, replace
   `enabled = bool(state)` with `enabled = bool(enabled)`, and update the docstring to
   `"""Persist the inventory memory switch when the Setup page flips it."""`. In its `except` branch, after
   the toast, add `self.ui_manager.refresh_setup()` so the page shows what the config now holds.

7. `_on_analysis_mode_changed`: after the `try`/`except` (as the method's last line) add
   `self.ui_manager.refresh_setup()`. Update its docstring to
   `"""Save the allocation strategy when the Setup page's radio cards change it."""`.

8. Fix the two comments that still name the old widgets: in `_on_client_data_loaded`, the comment listing
   `strategy radio sync, inventory_memory_checkbox restore` becomes `the Setup page's state`.

- [ ] **Step 9: Remove the Qt components**

In `gui/components/__init__.py` delete the lines `from gui.components.file_slot import FileSlot`,
`from gui.components.radio_card import RadioCard`, and the `"FileSlot",` and `"RadioCard",` entries of
`__all__`.

Run, one command per call:
`/usr/bin/git rm gui/components/file_slot.py`
`/usr/bin/git rm gui/components/radio_card.py`
`/usr/bin/git rm tests/test_components_radio_card.py`

Then search for leftovers: `rg -n "FileSlot|RadioCard|setup_stack|setup_state_panel|inventory_memory_checkbox|strategy_multi_item|strategy_fifo|_refresh_setup_panel|choose_folder_button" gui shared tests`.
Expected: only `gui/setup_state.py`, `gui/ui_manager.py` (the record), and the tests written in this plan.
Fix any other hit to the new names.

- [ ] **Step 10: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_setup_layout.py tests/test_file_handler.py tests/test_first_run.py tests/test_shell.py tests/test_session_restore.py tests/test_results_screen.py tests/test_setup_page.py`
Expected: all pass.

Then the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: the baseline's failures only. A test elsewhere that still reaches for a deleted widget is rewritten
to read `win.setup_bridge.state` or the slot record; never skipped.

`.venv/bin/ruff check .`: no findings.

- [ ] **Step 11: Commit**

`/usr/bin/git add -A gui tests`, then check `/usr/bin/git status --short` lists only files this task names,
and commit with the message `Setup: the web page takes tab 0; one route for files; one rule for Run`.

---

### Task 8: The command bar

The bar stops mirroring a screen's button. It gains an always-present New session, a session chip, and a step
readout with a disabled "Running…". Spec §8.

**Files:**
- Modify: `gui/components/commandbar.py`, `gui/ui_manager.py`
- Rewrite: `tests/test_commandbar_states.py`
- Adapt: `tests/test_components_commandbar.py`, `tests/test_components_render_roles.py`, `tests/test_shell.py`,
  `tests/test_results_screen.py`
- Delete: `tests/test_screen_primary_actions.py` (it tests the mechanism this task removes; the bar's new
  states are pinned in `tests/test_commandbar_states.py`, and the page's Run button in `tests/test_setup_page.py`)

**Interfaces:**
- Produces on `CommandBar`:
  - widgets `new_session_button`, `session_button`, `session_chip`, `meta_label`, `step_count_label`,
    `step_name_label`, `running_button`, `overflow`, `overflow_button`, `client_selector`;
  - `set_screen(chip: bool, meta: bool) -> None`;
  - `set_step(index: int, total: int, name: str) -> None`;
  - unchanged: `set_state`, `set_session_text`, `set_status(role, text)`, `set_stock_age(text)`,
    `set_recent_sessions`, `set_clients`, `set_clients_from`, `set_current_client`, `current_client`.
- Removed from `CommandBar`: `action_button`, `cancel_button`, `open_folder_button`, `status_chip`,
  `stock_chip`, `progress_label`, `set_action`, `bind_action`, `set_results_mode`, `set_progress`, and the
  signals `actionTriggered`, `cancelRequested`, `openFolderRequested`.
- Removed from `gui/ui_manager.py`: `_SCREEN_ACTIONS`, `UIManager._bind_screen_action`.

- [ ] **Step 1: Rewrite `tests/test_commandbar_states.py`**

```python
"""The command bar's four states (phase 3 spec section 8).

New session and Open recent are always there. The session's name is a chip
on every screen but Setup, whose page head shows it. While a run is going the
bar names the step beside a disabled "Running…".
"""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.commandbar import BarState, CommandBar


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    widget.resize(1310, 48)
    # isVisible() reflects the whole ancestor chain, not just a widget's own
    # setVisible() flag -- an unshown top-level always reports False.
    widget.show()
    yield widget
    widget.deleteLater()


def _analysed(bar):
    bar.set_session_text("2026-09-30_1")
    bar.set_status("text_secondary", "Analysed 14:06")
    bar.set_stock_age("Stock file 19 h old")
    bar.set_state(BarState.SESSION)
    return bar


@pytest.mark.parametrize("state", list(BarState))
def test_new_session_and_open_recent_are_always_shown(bar, state):
    bar.set_state(state)
    assert bar.new_session_button.isVisible()
    assert bar.session_button.isVisible()
    assert bar.session_button.text() == "Open recent"


@pytest.mark.parametrize(
    ("state", "usable"),
    [
        (BarState.NO_CLIENT, False),
        (BarState.NO_SESSION, True),
        (BarState.SESSION, True),
        (BarState.RUNNING, False),
    ],
)
def test_they_are_usable_with_a_client_and_no_run(bar, state, usable):
    bar.set_state(state)
    assert bar.new_session_button.isEnabled() is usable
    assert bar.session_button.isEnabled() is usable


def test_new_session_is_a_secondary_button_that_asks_for_a_session(bar, qtbot):
    bar.set_state(BarState.NO_SESSION)
    assert bar.new_session_button.property("role") == "secondary"
    assert bar.new_session_button.text() == "New session"
    assert not bar.new_session_button.icon().isNull()
    with qtbot.waitSignal(bar.newSessionRequested):
        bar.new_session_button.click()


def test_the_bar_has_no_screen_action_cancel_or_folder_button(bar):
    for name in (
        "action_button",
        "cancel_button",
        "open_folder_button",
        "status_chip",
        "stock_chip",
        "progress_label",
    ):
        assert not hasattr(bar, name), name


def test_the_chip_shows_the_session_off_setup(bar):
    _analysed(bar).set_screen(chip=True, meta=False)
    assert bar.session_chip.isVisible()
    assert bar.session_chip.text() == "2026-09-30_1"
    assert "border-radius: 6px" in bar.session_chip.styleSheet()
    assert not bar.meta_label.isVisible()


def test_setup_shows_no_chip_because_its_page_head_does(bar):
    _analysed(bar).set_screen(chip=False, meta=False)
    assert not bar.session_chip.isVisible()
    assert not bar.meta_label.isVisible()


def test_results_adds_the_analysis_age_as_text(bar):
    _analysed(bar).set_screen(chip=True, meta=True)
    assert bar.session_chip.isVisible()
    assert bar.meta_label.isVisible()
    assert bar.meta_label.text() == "analysed 14:06 · stock file 19 h old"


def test_the_meta_text_follows_what_changes_under_it(bar):
    _analysed(bar).set_screen(chip=True, meta=True)
    bar.set_stock_age("")
    assert bar.meta_label.text() == "analysed 14:06"
    bar.set_status("text_secondary", "")
    assert not bar.meta_label.isVisible()


@pytest.mark.parametrize("state", [BarState.NO_CLIENT, BarState.NO_SESSION])
def test_with_no_session_there_is_no_chip_and_no_meta(bar, state):
    bar.set_session_text("No session")
    bar.set_state(state)
    bar.set_screen(chip=True, meta=True)
    assert not bar.session_chip.isVisible()
    assert not bar.meta_label.isVisible()


def test_the_session_id_is_never_elided(bar):
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.SESSION)
    bar.set_screen(chip=True, meta=False)
    assert bar.session_chip.text() == "2026-09-04_tuesday-restock"
    assert bar.session_chip.maximumWidth() >= 16777215


def test_running_names_the_step_beside_a_disabled_running_button(bar):
    _analysed(bar).set_screen(chip=False, meta=False)
    bar.set_state(BarState.RUNNING)
    bar.set_step(1, 4, "Checking fulfilment history")
    assert bar.step_count_label.isVisible()
    assert bar.step_count_label.text() == "Step 2 of 4"
    assert bar.step_name_label.isVisible()
    assert bar.step_name_label.text() == "Checking fulfilment history"
    assert bar.running_button.isVisible()
    assert bar.running_button.text() == "Running…"
    assert bar.running_button.property("role") == "primary"
    assert not bar.running_button.isEnabled()


@pytest.mark.parametrize(
    "state", [BarState.NO_CLIENT, BarState.NO_SESSION, BarState.SESSION]
)
def test_nothing_about_a_run_shows_when_none_is_going(bar, state):
    bar.set_step(2, 4, "Allocating stock")
    bar.set_state(state)
    assert not bar.step_count_label.isVisible()
    assert not bar.step_name_label.isVisible()
    assert not bar.running_button.isVisible()


def test_the_bar_is_the_height_every_later_screen_assumes(bar):
    assert bar.height() == 48


def test_the_client_name_is_what_gives_way_first(bar):
    bar.set_clients(["CLIENT_WAREHOUSE_NTH"])
    bar.set_current_client("CLIENT_WAREHOUSE_NTH")
    _analysed(bar).set_screen(chip=True, meta=False)
    bar.resize(700, 48)
    QApplication.processEvents()
    # 120, not "<= 200": the selector is setFixedWidth to one of exactly two
    # values, so a <= assertion passes whether or not the rung fired.
    assert bar.client_selector.width() == 120
    assert bar.session_chip.text() == "2026-09-30_1"


def test_a_narrow_bar_keeps_the_step_count_and_drops_its_name(bar):
    _analysed(bar)
    bar.set_state(BarState.RUNNING)
    bar.set_step(2, 4, "Allocating stock")
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.step_name_label.isVisible()

    bar.resize(620, 48)
    QApplication.processEvents()
    assert bar.step_count_label.text() == "Step 3 of 4"
    assert not bar.step_name_label.isVisible()


def test_new_session_goes_icon_only_last(bar):
    bar.set_state(BarState.NO_SESSION)
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == "New session"

    bar.resize(420, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == ""
    assert not bar.new_session_button.icon().isNull()


def test_open_recent_is_usable_even_with_no_recent_sessions(qapp):
    """Its menu always ends with the route to the browser."""
    bar = CommandBar()
    bar.set_recent_sessions([])
    bar.set_state(BarState.NO_SESSION)
    assert bar.session_button.isEnabled()
    assert "Browse all sessions" in bar.session_menu.actions()[-1].text()


def test_choosing_a_session_emits_its_path(qapp, qtbot):
    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1"), ("Monday", "/s/2")])
    actions = [a for a in bar.session_menu.actions() if a.data()]
    with qtbot.waitSignal(bar.sessionChosen) as caught:
        actions[0].trigger()
    assert caught.args == ["/s/1"]


def test_the_menu_ends_with_a_route_to_the_browser(qapp, qtbot):
    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1")])
    last = bar.session_menu.actions()[-1]
    assert "Browse all sessions" in last.text()
    with qtbot.waitSignal(bar.browseAllRequested):
        last.trigger()
```

- [ ] **Step 2: Adapt the other bar tests**

`tests/test_components_commandbar.py`:
- `test_session_id_is_shown_verbatim`: add `bar.set_screen(chip=True, meta=False)` after `set_state` and
  assert on `bar.session_chip.text()`.
- Delete `test_status_uses_a_shared_status_chip`, `test_the_action_button_is_the_screens_one_primary`,
  `test_the_action_emits_actionTriggered`, `test_set_action_called_twice_relabels_one_button`,
  `test_bind_action_mirrors_the_bound_buttons_label_and_state`,
  `test_a_later_setEnabled_on_the_source_reaches_the_bar`,
  `test_the_bars_click_fires_the_bound_buttons_own_connections`, `test_binding_none_hides_the_slot`,
  `test_rebinding_stops_the_old_button_reaching_the_bar`,
  `test_set_action_after_a_bind_stops_mirroring_the_old_button`. Their replacement is
  `test_the_bar_has_no_screen_action_cancel_or_folder_button` and the tests around it in Step 1. Remove the
  `QPushButton` import if nothing else in the file uses it.

`tests/test_components_render_roles.py`: replace `test_the_command_bar_action_still_renders_primary` with:

```python
def test_the_bars_new_session_button_takes_its_role_from_the_app_sheet(styled_app):
    """The bar's own sheet is type-scoped, so it must not flatten a child's role."""
    bar = CommandBar()
    bar.set_state(BarState.NO_SESSION)
    bar.resize(600, 48)
    bar.show()
    QApplication.processEvents()

    plain = QPushButton("New session")
    set_button_role(plain, "secondary")
    plain.resize(bar.new_session_button.size())
    plain.show()
    QApplication.processEvents()

    assert _dominant_color(bar.new_session_button) == _dominant_color(plain)
```

  and add what it needs to that file's imports: `BarState` (from `gui.components.commandbar`), `QPushButton`
  (from `PySide6.QtWidgets`) and `set_button_role` (from `shared.theme`), each only if not already imported.

`tests/test_shell.py`:
- `test_session_label_keeps_its_name_so_its_writer_needs_no_edit`: the assertion becomes
  `assert main_window.command_bar.session_chip.text() == "SESSION_7"`.
- `test_resuming_a_past_session_reaches_the_session_state`: replace the `open_folder_button` assertion with:

```python
    menu = main_window.command_bar.overflow
    menu.aboutToShow.emit()
    item = next(a for a in menu.actions() if a.text() == "Open session folder")
    assert item.isEnabled()
```

- Replace `test_new_session_is_reachable_from_the_overflow_with_a_session_open` with:

```python
def test_new_session_is_reachable_from_the_bar_with_a_session_open(main_window):
    """Phase 3 spec section 8: the bar's New session is always there, so the
    overflow no longer carries a copy of it."""
    from gui.components.commandbar import BarState

    main_window.profile_manager.create_client_profile("M", "Client M")
    main_window.command_bar.set_clients(["M"])
    main_window.command_bar.set_current_client("M")
    main_window.command_bar.set_state(BarState.SESSION)

    button = main_window.command_bar.new_session_button
    assert button.isVisible()
    assert button.isEnabled()

    calls = []
    main_window.actions_handler.create_new_session = lambda: calls.append(1)
    button.click()
    assert calls == [1]
```

- `test_the_overflow_keeps_only_what_the_sidebar_does_not`: the expected list becomes
  `["No client", "Open session folder", "THIS PC", "Server connection…", "Keyboard shortcuts…"]`, and add:

```python
    menu.aboutToShow.emit()
    folder = next(a for a in menu.actions() if a.text() == "Open session folder")
    assert not folder.isEnabled()  # no session is open
```

`tests/test_results_screen.py`:
- Replace `test_results_has_no_bar_action_and_draws_the_session_chip` with:

```python
def test_the_bar_draws_the_chip_and_the_age_on_results_only(main_window):
    from PySide6.QtWidgets import QApplication

    bar = main_window.command_bar
    main_window.main_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert (bar._show_chip, bar._show_meta) == (True, True)
    main_window.main_tabs.setCurrentIndex(3)
    QApplication.processEvents()
    assert (bar._show_chip, bar._show_meta) == (True, False)
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert (bar._show_chip, bar._show_meta) == (False, False)
```

- In the three session-chip tests near line 242, the bar no longer has chips. Replace
  `assert main_window.command_bar.status_chip.text() == "Analysed 09:33"` and the `stock_chip` line under it
  with `assert main_window.command_bar.meta_label.text() == "analysed 09:33 · stock file 19 h old"`; replace
  each later pair of `status_chip.text() == ""` / `stock_chip.text() == ""` assertions with
  `assert main_window.command_bar.meta_label.text() == ""` (use `bar.meta_label` where the test has `bar`).

Delete the old file: `/usr/bin/git rm tests/test_screen_primary_actions.py`.

- [ ] **Step 3: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_commandbar_states.py`
Expected: failures (`CommandBar` has no `set_screen`, `session_chip`, `set_step`).

- [ ] **Step 4: `gui/components/commandbar.py`**

1. Module docstring becomes:

```python
"""The one-row bar across the top of every screen.

Client selector, New session, Open recent, and the open session's name as a
chip. It holds no screen's action: each page draws its own primary. While a
run is going it names the step beside a disabled "Running…" (phase 3 spec
section 8). Replaces the sidebar of 70px client cards with a dropdown.
"""
```

2. Imports: from `PySide6.QtCore` keep `QPoint, Qt, Signal` (drop `QEvent`); from `shared.theme` keep
   `on_theme_changed` (drop `StatusChip`). Everything else stays.

3. `BarState`'s docstring becomes:

```python
    """What the bar knows about: no client, no session, a session, a run.

    It decides what is enabled and whether the chip and the step readout
    show. Which screen is showing is set_screen's, separately.
    """
```

4. In `_LADDER`, the third entry becomes `(700, "step"),  # the step readout drops its name, keeps the count`.

5. In the `CommandBar` class, delete the signals `actionTriggered`, `openFolderRequested` and
   `cancelRequested`.

6. In `__init__`, replace everything from `self._repopulating = False` down to the end of the method with:

```python
        self._repopulating = False
        self._restore_client = ""
        self._show_chip = False
        self._show_meta = False
        self._analysed_text = ""
        self._stock_text = ""
        self._recent: list[tuple[str, str]] = []
        self._session_text = ""
        self._state = BarState.NO_CLIENT
        self._step = (0, 0, "")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)
        # The ladder shrinks this bar below its content's natural width when
        # the window narrows. SetDefaultConstraint would instead push that
        # width onto the widget as a hard minimum, so resize() below it (and
        # therefore the ladder's own resizeEvent) would never fire.
        layout.setSizeConstraint(QLayout.SetNoConstraint)

        self.client_selector = _ClientCombo(self)
        self.client_selector.setModel(QStandardItemModel(self.client_selector))
        self.client_selector.setPlaceholderText("Choose a client")
        self.client_selector.currentTextChanged.connect(self._on_client_changed)
        self.client_selector.activated.connect(self._on_row_activated)
        view = self.client_selector.view()
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self._on_row_context_menu)
        layout.addWidget(self.client_selector)

        self.setFixedHeight(BAR_HEIGHT)
        self.client_selector.setFixedWidth(_CLIENT_NAME_WIDTH)

        # Always there: a session can be started from any screen. Secondary,
        # because the screen's primary is the page's own.
        self.new_session_button = QPushButton("New session", self)
        set_button_role(self.new_session_button, "secondary")
        self.new_session_button.clicked.connect(self.newSessionRequested.emit)
        # A QIcon is a snapshot: re-rendered on a theme change.
        on_theme_changed(
            self.new_session_button,
            lambda _t=None, b=self.new_session_button: b.setIcon(icon("plus")),
        )
        layout.addWidget(self.new_session_button)

        # The route back to yesterday's work. Always reads "Open recent": the
        # open session's name is the chip beside it, or the page's own head.
        self.session_button = QToolButton(self)
        self.session_button.setAutoRaise(True)
        self.session_button.setPopupMode(QToolButton.InstantPopup)
        self.session_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.session_button.setText("Open recent")
        self.session_menu = QMenu(self.session_button)
        self.session_button.setMenu(self.session_menu)
        layout.addWidget(self.session_button)

        # The open session's name, never elided: an elided ID is a wrong ID.
        self.session_chip = QLabel("", self)
        self.session_chip.hide()
        layout.addWidget(self.session_chip)

        # Results only: "analysed 14:06 · stock file 19 h old".
        self.meta_label = QLabel("", self)
        self.meta_label.hide()
        layout.addWidget(self.meta_label)

        layout.addStretch()

        # While a run is going: "Step 2 of 4", the step's name, and a button
        # that only says so. Cancel is on the Setup page.
        self.step_count_label = QLabel("", self)
        self.step_count_label.hide()
        layout.addWidget(self.step_count_label)
        self.step_name_label = QLabel("", self)
        self.step_name_label.hide()
        layout.addWidget(self.step_name_label)
        self.running_button = QPushButton("Running…", self)
        set_button_role(self.running_button, "primary")
        self.running_button.setEnabled(False)
        self.running_button.hide()
        layout.addWidget(self.running_button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        layout.addWidget(self.overflow_button)

        on_theme_changed(self.session_chip, self._style_labels)
        self._refresh()
```

   Keep the lines above `self._repopulating = False` (the `theme` lookup is now unused there: delete the
   `theme = get_theme_manager().get_current_theme()` line at the top of `__init__` if ruff flags it; keep
   `setAttribute`, `_apply_theme()` and the `theme_changed` connection).

7. Replace `_style_session`, `set_results_mode` and `_refresh_meta` with:

```python
    def _style_labels(self, theme=None) -> None:
        """The chip, the meta text and the step readout.

        Their own sheets rather than the app's: a widget sheet has to be
        re-applied on a theme change.
        """
        theme = theme or get_theme_manager().get_current_theme()
        self.session_button.setStyleSheet(font_css("caption"))
        self.session_chip.setStyleSheet(
            f"QLabel {{ {font_css('caption')}"
            f" font-family: {theme.font_family_mono};"
            f" background-color: {theme.surface_raised};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_md}px;"
            " padding: 0px 8px; min-height: 20px; max-height: 20px; }"
        )
        quiet = f"{font_css('caption')} color: {theme.text_secondary};"
        self.meta_label.setStyleSheet(quiet)
        self.step_count_label.setStyleSheet(
            f"{quiet} font-family: {theme.font_family_mono};"
        )
        self.step_name_label.setStyleSheet(font_css("caption", bold=True))

    def set_screen(self, chip: bool, meta: bool) -> None:
        """Which screen is showing: whether the bar draws the session chip
        (every screen but Setup, whose page head has it) and the analysis age
        (Results)."""
        self._show_chip = bool(chip)
        self._show_meta = bool(meta)
        self._refresh()

    def _refresh_meta(self) -> None:
        """`analysed 14:06 · stock file 19 h old`."""
        parts = [t for t in (self._analysed_text, self._stock_text) if t]
        self.meta_label.setText(" · ".join(t[0].lower() + t[1:] for t in parts))
        has_session = self._state in (BarState.SESSION, BarState.RUNNING)
        self.meta_label.setVisible(self._show_meta and has_session and bool(parts))
```

8. Replace `set_status` and `set_stock_age` with:

```python
    def set_status(self, role: str, text: str) -> None:
        """When the open session was analysed. `role` is kept for the callers
        that pass one; the text is drawn in one quiet colour."""
        self._analysed_text = text
        self._refresh_meta()

    def set_stock_age(self, text: str) -> None:
        self._stock_text = text
        self._refresh_meta()
```

9. Delete `set_action`, `_unbind`, `bind_action`, `_forward_action_click` and `eventFilter`.

10. Replace `set_progress`, `_refresh` and `_apply_ladder` with:

```python
    def set_step(self, index: int, total: int, name: str) -> None:
        """The run's current step: its index in the run's steps, how many
        there are, and its name."""
        self._step = (int(index), int(total), str(name))
        self._refresh()

    def _refresh(self) -> None:
        """Resolve state and screen into what is actually visible.

        One method rather than setters that each hide things: ui_manager
        calls them from a connection change and a screen change that do not
        know about each other.
        """
        state = self._state
        has_session = state in (BarState.SESSION, BarState.RUNNING)
        usable = state in (BarState.NO_SESSION, BarState.SESSION)

        self.new_session_button.setEnabled(usable)
        self.session_button.setEnabled(usable)

        self.session_chip.setText(self._session_text)
        self.session_chip.setVisible(
            has_session and self._show_chip and bool(self._session_text)
        )
        self._refresh_meta()

        running = state is BarState.RUNNING
        self.step_count_label.setVisible(running)
        self.running_button.setVisible(running)
        self._apply_ladder(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_ladder(self.width())

    def _apply_ladder(self, width: int) -> None:
        fired = {name for trigger, name in _LADDER if width < trigger}

        self.layout().setSpacing(8 if "spacer" in fired else 12)

        self.client_selector.setFixedWidth(
            120 if "client" in fired else _CLIENT_NAME_WIDTH
        )

        index, total, name = self._step
        self.step_count_label.setText(f"Step {index + 1} of {total}" if total else "")
        self.step_name_label.setText(name)
        self.step_name_label.setVisible(
            self._state is BarState.RUNNING and "step" not in fired and bool(name)
        )

        self.new_session_button.setText("" if "new_session" in fired else "New session")
```

    (`resizeEvent` already exists: keep one copy.)

11. `set_recent_sessions` and `set_session_text` stay as they are: both end in `self._refresh()`.

- [ ] **Step 5: `gui/ui_manager.py`**

1. Delete the `_SCREEN_ACTIONS` dict and the comment block above it.

2. In `_create_tabs`, replace from the comment `# The screen's primary action moves into the command bar's one slot.`
   to the end of the method with:

```python
        self.mw.main_tabs.currentChanged.connect(self._apply_page_inset)
        # The session chip on every screen but Setup, whose page head shows it;
        # the analysis age on Results.
        self.mw.main_tabs.currentChanged.connect(
            lambda index: self.mw.command_bar.set_screen(
                chip=index != 0, meta=index == 1
            )
        )
```

3. Delete the `_bind_screen_action` method.

4. In `_create_command_bar`, delete `bar.openFolderRequested.connect(self._open_session_folder)` and add,
   after `self._populate_overflow(bar)`:

```python
        bar.overflow.aboutToShow.connect(self._refresh_overflow)
```

5. Replace `_populate_overflow` with:

```python
    def _populate_overflow(self, bar) -> None:
        """The open session's folder, then this PC's server and shortcuts.

        Rebuilt on a client change, because the first section's header is the
        client's name and a stale header points at the wrong profile. New
        session is the bar's own button now (phase 3 spec section 8).
        """
        menu = bar.overflow
        menu.clear()

        menu.add_section(self.mw.current_client_id or "No client")
        self._open_folder_item = menu.add_item(
            "Open session folder", self._open_session_folder
        )
        self._refresh_overflow()

        menu.add_section("THIS PC")
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.add_item("Keyboard shortcuts…", lambda: ShortcutsDialog(self.mw).exec())

    def _refresh_overflow(self) -> None:
        self._open_folder_item.setEnabled(bool(getattr(self.mw, "session_path", None)))
```

6. Fix the comments in `ui_manager.py` that still describe the old bar: the class-level comment above
   `_BUTTON_ICONS` (it names `open_folder_button`) becomes
   `# No long-lived button icon is re-themed here: the bar re-renders its own.`

- [ ] **Step 6: Search for leftovers**

`rg -n "bind_action|set_action\(|action_button|cancel_button|open_folder_button|status_chip|stock_chip|set_results_mode|_results_mode|set_progress|progress_label|_SCREEN_ACTIONS|_bind_screen_action|actionTriggered|openFolderRequested|cancelRequested" gui tests`

Expected hits: `setup.cancelRequested` and `SetupBridge.cancelRequested` (the page's Cancel, a different
object), `cancel_button` in `tests/test_components_confirm_dialog.py` and any dialog (a different widget), and
`status_chip` in `tests/test_shared_theme_widgets.py` / `tests/test_components_render_roles.py` test names (the
shared `StatusChip` widget). Anything else on the command bar is fixed to the new API.

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_commandbar_states.py tests/test_components_commandbar.py tests/test_components_render_roles.py tests/test_shell.py tests/test_results_screen.py tests/test_session_setup_layout.py tests/test_first_run.py`
Expected: all pass. Then the whole suite: only the baseline's failures. `.venv/bin/ruff check .`: no findings.

- [ ] **Step 8: Commit**

`/usr/bin/git add -A gui tests`, check `/usr/bin/git status --short`, and commit with the message
`Command bar: New session always there, the session chip, and the run's step`.

---

### Task 9: Progress and Cancel, wired

**Files:**
- Modify: `gui/actions_handler.py`, `gui/main_window_pyside.py`
- Test: `tests/test_actions_handler.py`

**Interfaces:**
- Consumes: `core.ANALYSIS_STEPS`, `core.AnalysisCancelled`, `core.CANCELLED`, `progress=` (Task 2);
  `CommandBar.set_step` (Task 8); `UIManager.refresh_setup`, `mw._analysis_step`, `mw._analysis_cancelling`,
  `SetupBridge.cancelRequested` (Tasks 5, 7).
- Produces on `ActionsHandler`: `analysis_progress = Signal(int)`, `cancel_analysis() -> None`,
  `_report_step(index: int) -> None` (the callback handed to the run).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_actions_handler.py` (add `from shopify_tool import core` to its imports):

```python
def _running_mw():
    return SimpleNamespace(
        _analysis_running=True,
        _analysis_step=1,
        _analysis_cancelling=False,
        command_bar=Mock(),
        ui_manager=Mock(),
    )


def test_a_step_the_run_reports_reaches_the_bar_and_the_page():
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler._report_step(2)

    assert mw._analysis_step == 2
    mw.command_bar.set_step.assert_called_once_with(2, 4, "Allocating stock")
    mw.ui_manager.refresh_setup.assert_called_once()


def test_a_step_that_arrives_after_the_run_ended_is_ignored():
    mw = _running_mw()
    mw._analysis_running = False
    handler = ActionsHandler(mw)

    handler._report_step(3)

    assert mw._analysis_step == 1
    mw.command_bar.set_step.assert_not_called()


def test_cancel_stops_the_run_at_its_next_step():
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is True
    mw.ui_manager.refresh_setup.assert_called_once()
    with pytest.raises(core.AnalysisCancelled):
        handler._report_step(2)


def test_cancel_pressed_twice_is_one_cancel():
    mw = _running_mw()
    handler = ActionsHandler(mw)
    handler.cancel_analysis()
    handler.cancel_analysis()
    mw.ui_manager.refresh_setup.assert_called_once()


def test_cancel_with_no_run_going_does_nothing():
    mw = _running_mw()
    mw._analysis_running = False
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is False
    mw.ui_manager.refresh_setup.assert_not_called()
    mw._analysis_running = True
    handler._report_step(0)  # the next run is not cancelled before it starts


def test_cancel_once_saving_has_begun_does_nothing():
    mw = _running_mw()
    mw._analysis_step = 3
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is False


def test_a_finished_run_leaves_no_cancel_behind():
    mw = _running_mw()
    handler = ActionsHandler(mw)
    handler.cancel_analysis()

    handler._on_analysis_finished()

    assert mw._analysis_running is False
    assert mw._analysis_cancelling is False
    mw._analysis_running = True
    handler._report_step(0)  # does not raise: the flag was cleared


def test_a_cancelled_result_is_a_toast_not_an_error(monkeypatch):
    said = Mock()
    failed = Mock()
    monkeypatch.setattr("gui.actions_handler.toast", said)
    monkeypatch.setattr("gui.actions_handler.show_error", failed)
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.on_analysis_complete((False, core.CANCELLED, None, None))

    said.assert_called_once_with(mw, "Analysis cancelled")
    failed.assert_not_called()


def test_a_failed_result_is_still_an_error(monkeypatch):
    failed = Mock()
    monkeypatch.setattr("gui.actions_handler.show_error", failed)
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.on_analysis_complete((False, "Validation error: no SKU", None, None))

    failed.assert_called_once()


def test_run_analysis_hands_the_run_its_progress_callback(monkeypatch):
    captured = {}

    def fake_worker(fn, *args, **kwargs):
        captured["fn"] = fn
        captured["kwargs"] = kwargs
        return Mock()

    monkeypatch.setattr("gui.actions_handler.Worker", fake_worker)
    mw = SimpleNamespace(
        session_path="/sessions/2026-09-30_1",
        current_client_id="acme",
        _analysis_running=False,
        _analysis_step=3,
        _analysis_cancelling=True,
        active_profile_config={},
        stock_file_path="/d/stock.csv",
        orders_file_path="/d/orders.csv",
        session_manager=Mock(),
        profile_manager=Mock(),
        threadpool=Mock(),
        command_bar=Mock(),
        ui_manager=Mock(),
    )
    handler = ActionsHandler(mw)

    handler.run_analysis()

    assert captured["fn"] is core.run_full_analysis
    assert captured["kwargs"]["progress"] == handler._report_step
    assert mw._analysis_running is True
    assert mw._analysis_step == 0
    assert mw._analysis_cancelling is False
    mw.command_bar.set_step.assert_called_once_with(0, 4, "Reading orders and stock")
    mw.threadpool.start.assert_called_once()
```

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_actions_handler.py`
Expected: the new tests fail (`ActionsHandler` has no `_report_step`, no `cancel_analysis`).

- [ ] **Step 3: `gui/actions_handler.py`**

1. Add `import threading` to the standard-library imports.

2. In the class, under `data_changed = Signal()`:

```python
    # Emitted on the analysis thread; the connection to the slot below is
    # queued across threads, which is how a step reaches the UI.
    analysis_progress = Signal(int)
```

3. In `__init__`, after `self._stats_workers = set()`:

```python
        # Set by Cancel on the UI thread, read by the run at each step.
        self._cancel = threading.Event()
        self.analysis_progress.connect(self._on_analysis_progress)
```

4. In `run_analysis`, replace

```python
        self.mw._analysis_running = True
        self.mw.command_bar.set_state(BarState.RUNNING)
```

   with

```python
        self.mw._analysis_running = True
        self.mw._analysis_step = 0
        self.mw._analysis_cancelling = False
        self._cancel.clear()
        self.mw.command_bar.set_step(
            0, len(core.ANALYSIS_STEPS), core.ANALYSIS_STEPS[0]
        )
        self.mw.command_bar.set_state(BarState.RUNNING)
```

   and add `progress=self._report_step,` as the last keyword argument of the `Worker(...)` call, after
   `session_path=self.mw.session_path,`.

5. Add these three methods after `run_analysis`:

```python
    def _report_step(self, index: int) -> None:
        """The run's progress callback. Runs on the analysis thread.

        Raising here is how Cancel reaches the run: core catches it before
        anything is saved. Nothing else may touch the UI from this thread, so
        the step travels as a signal.
        """
        if self._cancel.is_set():
            raise core.AnalysisCancelled
        self.analysis_progress.emit(index)

    def _on_analysis_progress(self, index: int) -> None:
        if not self.mw._analysis_running:
            return  # a step delivered after the run ended
        self.mw._analysis_step = index
        self.mw.command_bar.set_step(
            index, len(core.ANALYSIS_STEPS), core.ANALYSIS_STEPS[index]
        )
        self.mw.ui_manager.refresh_setup()

    def cancel_analysis(self) -> None:
        """Stop the run at its next step. No effect once saving has begun.

        If the run passes its last checkpoint before it sees the flag, it
        finishes normally: a result that arrives is never thrown away.
        """
        if not self.mw._analysis_running or self._cancel.is_set():
            return
        if self.mw._analysis_step >= len(core.ANALYSIS_STEPS) - 1:
            return
        self._cancel.set()
        self.mw._analysis_cancelling = True
        self.mw.ui_manager.refresh_setup()
```

6. In `_on_analysis_finished`, after `self.mw._analysis_running = False` add:

```python
        self.mw._analysis_cancelling = False
        self._cancel.clear()
```

7. In `on_analysis_complete`, directly after `success, result_msg, df, stats = result`:

```python
        if not success and result_msg == core.CANCELLED:
            self.log.info("Analysis cancelled by the operator")
            toast(self.mw, "Analysis cancelled")
            return
```

- [ ] **Step 4: `gui/main_window_pyside.py`**

In `connect_signals`, in the block of Setup page requests added in Task 7, after the `runRequested` line:

```python
        setup.cancelRequested.connect(lambda: self.actions_handler.cancel_analysis())
```

- [ ] **Step 5: Write the wiring test**

Append to `tests/test_session_setup_layout.py`:

```python
def test_cancel_from_the_page_reaches_the_run(client_window, monkeypatch):
    cancelled = []
    monkeypatch.setattr(
        client_window.actions_handler, "cancel_analysis", lambda: cancelled.append(1)
    )
    client_window.setup_bridge.cancelRun()
    assert cancelled == [1]


def test_a_step_shows_on_the_page_and_in_the_bar(client_window):
    client_window.setup_bridge.newSession()
    client_window._analysis_running = True
    client_window.actions_handler.analysis_progress.emit(2)

    run = client_window.setup_bridge.state["run"]
    assert (run["running"], run["step"], run["step_name"]) == (
        True,
        2,
        "Allocating stock",
    )
    assert client_window.command_bar.step_count_label.text() == "Step 3 of 4"
    assert client_window.run_analysis_button.isEnabled() is False

    client_window.actions_handler.cancel_analysis()
    run = client_window.setup_bridge.state["run"]
    assert (run["cancelling"], run["can_cancel"]) == (True, False)

    client_window.actions_handler._on_analysis_finished()
    assert client_window.setup_bridge.state["run"]["running"] is False
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_actions_handler.py tests/test_session_setup_layout.py tests/test_core.py`
Expected: all pass. `.venv/bin/ruff check gui tests`: no findings.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/actions_handler.py gui/main_window_pyside.py tests/test_actions_handler.py tests/test_session_setup_layout.py`,
message `Run: named steps reach the bar and the page, and Cancel stops the run before it saves`.

---

### Task 10: One toast router

**Files:**
- Modify: `gui/components/__init__.py`, `gui/main_window_pyside.py`, `gui/settings/window.py`,
  `gui/settings/sets.py`
- Create: `tests/test_toast_router.py`
- Adapt: `tests/test_shell.py`

**Interfaces:**
- Produces: `gui.components.toast(source, text, *, role="success", action_text="", on_action=None)` (same
  signature as `shared.components.toast`; returns the Qt `Toast`, or `None` when a web page drew it);
  `MainWindow.web_toast(text: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_toast_router.py`:

```python
"""One router for toasts (phase 3 spec section 9, ADR 0007).

A Qt toast is a child of the window and cannot paint above a web view, so a
toast raised while a web page shows is drawn by that page.
"""

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui.components import Toast, toast


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def _raised(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    return seen


def test_on_setup_the_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Session 2026-09-30_1 created.")

    assert seen == [("Session 2026-09-30_1 created.", False)]
    assert shown is None
    assert Toast.for_window(main_window) is None


def test_on_results_the_results_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(1)
    seen = _raised(main_window.results_bridge)
    other = _raised(main_window.setup_bridge)

    toast(main_window, "Settings saved")

    assert seen == [("Settings saved", False)]
    assert other == []


def test_on_a_qt_page_the_qt_toast_shows(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    seen = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Saved")

    assert shown is Toast.for_window(main_window)
    assert not shown.isHidden()
    assert seen == []


def test_a_child_of_the_window_is_routed_like_the_window(main_window):
    """A dialog toasts on its parent after it closes."""
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)
    child = QWidget(main_window)

    toast(child, "Settings saved")

    assert seen == [("Settings saved", False)]


def test_a_toast_with_an_action_stays_qt(main_window):
    """A web page's toast has no button to carry the action."""
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)

    shown = toast(
        main_window, "Exported 30 orders.", action_text="Open folder", on_action=lambda: None
    )

    assert shown is Toast.for_window(main_window)
    assert seen == []


def test_a_window_with_no_web_pages_keeps_the_qt_toast(qapp):
    window = QWidget()
    window.show()
    shown = toast(window, "Group created.")
    assert shown is Toast.for_window(window)
    window.close()
```

In `tests/test_shell.py`, replace `test_undo_toasts_into_the_document_while_the_results_screen_shows` and
`test_undo_keeps_the_qt_toast_when_another_screen_shows` with:

```python
def test_undo_says_so_once_through_the_window_toast(one_shot_undo, monkeypatch):
    """Where it is drawn is the router's question (tests/test_toast_router.py);
    undo only has to say it."""
    said = Mock()
    monkeypatch.setattr("gui.main_window_pyside.toast", said)

    one_shot_undo.undo_last_operation()

    said.assert_called_once_with(one_shot_undo, "Undid the last thing")
```

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_toast_router.py`
Expected: the Setup and Results tests fail (the Qt toast is shown and no bridge hears anything).

- [ ] **Step 3: `gui/components/__init__.py`**

In the `from shared.components import (...)` list, remove `toast,`. Under the imports add:

```python
from shared.components import toast as _qt_toast


def toast(source, text, *, role="success", action_text="", on_action=None):
    """Good news that never blocks, drawn where it can be seen.

    A Qt toast is a child of its window and cannot paint above a web view
    (ADR 0007). So a window that is showing a web page is asked first
    (`web_toast`) and that page draws the toast; anything else, and any toast
    that carries an action, is the Qt toast. Returns the Qt Toast, or None
    when a page drew it.
    """
    window = source.window() if hasattr(source, "window") else None
    web_toast = getattr(window, "web_toast", None)
    if web_toast is not None and not action_text and web_toast(text):
        return None
    return _qt_toast(
        source, text, role=role, action_text=action_text, on_action=on_action
    )
```

`"toast"` stays in `__all__`.

- [ ] **Step 4: `gui/main_window_pyside.py`**

1. Add this method after `is_connected`:

```python
    def web_toast(self, text: str) -> bool:
        """Draw a toast in the web page that is showing, if one is.

        gui.components.toast asks this first: a Qt toast would land behind
        the view (ADR 0007). False means "not a web page, use the Qt toast".
        """
        bridge = getattr(
            self,
            {0: "setup_bridge", 1: "results_bridge"}.get(
                self.main_tabs.currentIndex(), ""
            ),
            None,
        )
        if bridge is None:
            return False
        bridge.raise_toast(text)
        return True
```

2. In `undo_last_operation`, replace the comment and the `results_view` branch (from `# ADR 0007: a Qt toast lands behind`
   through the `else: toast(self, message)`) with:

```python
            # gui.components.toast sends it to the web page when one is showing.
            toast(self, message)
```

- [ ] **Step 5: The two direct imports**

In `gui/settings/window.py` and `gui/settings/sets.py`, change `from shared.components.toast import toast` to
`from gui.components import toast`. If either file already imports other names from `gui.components`, merge
into that import. Check for an import cycle by running the settings tests in Step 6; if `gui.components`
cannot be imported from `gui.settings` at module load, import it inside the function that toasts instead.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_toast_router.py tests/test_shell.py tests/test_components_toast.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_actions_handler.py tests/test_message_routes.py`
Expected: all pass. Then the whole suite: only the baseline's failures. A test that asserted a Qt toast while
tab 0 or 1 was current now listens on that page's `toastRaised`, or moves to tab 3.
`.venv/bin/ruff check .`: no findings.

- [ ] **Step 7: Commit**

`/usr/bin/git add -A gui tests`, check `/usr/bin/git status --short`, and commit with the message
`Toasts: one router sends a window's toast to the web page that is showing`.

---

### Task 11: Docs, the build check, the visual check, the gate

**Files:**
- Modify: `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `docs/adr/0007-the-results-screen-toasts-inside-the-document.md`, `docs/design/ui-refresh/roadmap.md`,
  `.github/workflows/build_release.yml`
- Create: `docs/design/ui-refresh/renders/phase3/*.png`

- [ ] **Step 1: `CONTEXT.md`**

Read the file's Rendering and Session setup sections first, and keep its style (one bold term, a dash, a
definition; a glossary only).

1. **Web tier**: replace `Analysis Results today; ADR 0016 lets each other screen move in its own task.` with
   `Analysis Results and Session Setup today; ADR 0016 lets each other screen move in its own task.`
2. Replace the **File slot** entry with:

```markdown
**File slot** — the record holding one of the two input files. One slot per
file, three states (missing, loaded, problem), and the only thing that knows
whether its file is usable. Not a **file picker**, which is the dialog a slot
opens: the slot persists and changes state, the picker appears and closes.

**File card** — a file slot as the Setup page draws it: a badge for its state,
the file's name, its rows, its orders or SKUs, its delimiter, and under a
problem the sentence that explains it and the link that fixes it.
```

3. Add to the Session setup section, after **File card**:

```markdown
**Setup state** — the one map Python builds for the Setup page: which view
shows, both file cards, the run summary's sentences, and whether a run may
start. The page draws it and decides nothing.

**Run summary** — the fixed column beside the file cards that says what the
run will do, holds Run analysis with the reason it is disabled, and becomes
the progress view while a run is going.

**Step** — one of a run's four named stages: reading the files, checking the
fulfilment history, allocating stock, saving the results. Cancel takes effect
between steps and never once saving has begun.
```

4. **Inventory memory**: add this sentence at the end of the entry:
   `A loaded stock file is always used as it is; memory stands in only when a run has no stock file.`

- [ ] **Step 2: The ADRs**

`docs/adr/0016-the-web-tier-grows-screen-by-screen.md`:
- Under **Consequences**, add a bullet:
  `- Setup moved in phase 3 (2026-10-01) with the second bridge, \`SetupBridge\`. What every bridge shares (the theme, the toast, the mount) is \`gui/web_page.py\`.`
- Under **What would reverse it**, add a paragraph:

```markdown
Measured on Linux, offscreen, 2026-10-01 (phase 3 spec section 2): the first view costs about 195 MB,
each further view about 31 MB and at most 0.15 s. Two views total about 372 MB against 340 MB for one.
A frozen Windows build over RDP has not been measured; that check is in the phase 3 PR and is done on a
warehouse PC before the release that carries Setup.
```

`docs/adr/0007-the-results-screen-toasts-inside-the-document.md`: read it, then add at the end of its
consequences (or as a closing paragraph if it has no such list):

```markdown
Since phase 3 (2026-10-01) one router decides: `gui.components.toast` asks the window (`web_toast`) and a
window showing a web page has that page draw the toast. A toast with an action stays a Qt toast.
```

- [ ] **Step 3: `docs/design/ui-refresh/roadmap.md`**

Replace the heading `### 3. Setup to the web tier` and its four bullets with:

```markdown
### 3. Setup to the web tier (built in run 41)

Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase3-setup-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase3-setup-web.md`.

Built as listed below, with these differences. The second view was measured on Linux only (about +31 MB and
at most +0.15 s); the Windows check over RDP is in the PR and is done before the release. With a client and
no session the page shows the "No session open" panel from `app-shell.html`, not live cards. The run names
four real steps and has no per-order count. The session chip is in the page head on Setup and in the bar on
every other screen, until Browse, Logs and Tools get their own page heads. One router sends a toast to the
web page that is showing.

- The second `QWebEngineView`, with its own bridge (`SetupBridge`). `gui/web_page.py` holds what every
  bridge shares.
- File cards (Missing / Loaded / Problem) with rows, orders or SKUs, and the detected delimiter. Folder merge,
  and problems inline with a link to the fix. The inventory memory switch with its explanation, and
  allocation strategy as radio cards. A fixed 300px Run summary column holding Run analysis. The run summary
  becomes the progress view with its step and Cancel.
- Picking files through the bridge (a Qt file dialog opened by a Slot) and dropping files onto the page.
- Command bar: New session is always shown as a secondary button and disabled with no client. While running,
  the bar shows the step count and step name and a disabled "Running…". Cancel is on the page.
- Kit: `.switch`, `.radio-card`, `.form-row`. Phase 5 reuses `.form-row`.
```

- [ ] **Step 4: The build check**

In `.github/workflows/build_release.yml`, in the `foreach ($name in ...)` list that checks the bundle, add
`"setup.html"` after `"results.html"`.

- [ ] **Step 5: The visual check (required by CLAUDE.md)**

Write this script under your job's tmp dir, not in the repo, as `render_phase3.py`:

```python
"""Throwaway: render the Setup page in every state and both themes."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "tests")]

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from test_setup_state import MEMORY, loaded, make_state

from gui.setup_bridge import SetupView, mount_setup_page
from gui.setup_state import FileSlot, RunFacts
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


bad = FileSlot("orders")
bad.set_invalid(
    "/d/acme-orders-30-09.csv", ["Lineitem sku"], ["Name"], {"Lineitem sku": "SKU"},
    rows=1204, delimiter=",",
)
parts = [
    {"name": "shopify-export-1.csv", "rows": 512},
    {"name": "shopify-export-2.csv", "rows": 480},
    {"name": "shopify-export-3.csv", "rows": 212},
]
folder = loaded(
    "orders", parts=parts, name="acme-orders-30-09\\  ·  3 CSVs merged",
    note="2 overlapping orders skipped",
)
STATES = {
    "no-client": make_state(client="", session=None),
    "no-session": make_state(session=None),
    "unreachable": make_state(connected=False, client="", session=None),
    "no-files": make_state(orders=FileSlot("orders"), stock=FileSlot("stock")),
    "orders-folder": make_state(orders=folder, stock=FileSlot("stock")),
    "file-problem": make_state(orders=bad),
    "ready": make_state(),
    "memory-covering": make_state(memory=MEMORY, stock=FileSlot("stock")),
    "running": make_state(run=RunFacts(running=True, step=2)),
    "cancelling": make_state(run=RunFacts(running=True, step=1, cancelling=True)),
    "server-lost": make_state(connected=False),
}

view = SetupView()
bridge = mount_setup_page(view)
view.resize(1166, 720)  # the page a 1366x768 window gives Setup
view.show()
pump(1500)
for theme in ("light", "dark"):
    get_theme_manager().set_theme(theme)
    for name, state in STATES.items():
        bridge.set_state(state)
        pump(500)
        view.grab().save(str(OUT / f"{theme}-{name}.png"))
get_theme_manager().set_theme("light")
print("saved to", OUT)
```

Run it: `QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/python <tmp>/render_phase3.py <tmp>/renders`
(the working directory must be the worktree root). Read every PNG. Then:

1. Compare `light-ready.png` with `docs/design/ui-refresh/mockups/renders/setup.png`, element by element: the
   page head and its chip, the two file cards and their badges, the three stats, the options card's label
   column, the switch, the two radio cards, the 300px summary, its rows and the primary button.
2. For the other states and for dark, unpack `mockups/setup.html` with the script in `mockups/README.md` and
   read the template's `PRESETS` and style helpers, or open the file in Chrome if a browser tool is
   available; compare each with its PNG.
3. Check by eye for what tests cannot: clipped or overlapping text, a badge pushed off its card, a folder
   name that elides before its "N CSVs merged" can be read (if it does, the `title` tooltip is the fallback,
   and say so in the PR), a switch whose off state is hard to see in either theme, a disabled control that
   looks enabled, an unreadable colour pair in dark, the summary column narrower or wider than 300px.
4. Render the kit sheet in both themes (mount `tests/web/kit_sheet.html` the way `tests/test_web_kit.py`'s
   `_sheet` does and save `view.grab()`); check the switch, the radio cards and the form row.
5. Render the shell: construct `MainWindow` as `tests/test_shell.py`'s `main_window` fixture does (set
   `FULFILLMENT_SERVER_PATH` to a temp dir), `resize(1366, 768)`, and save `win.grab()` (a) as it opens,
   (b) after `win.command_bar.set_session_text("2026-09-30_1")`, `set_state(BarState.SESSION)` and
   `win.main_tabs.setCurrentIndex(3)`, (c) after `set_state(BarState.RUNNING)` and
   `set_step(1, 4, "Checking fulfilment history")`. The web view may come out blank in a window grab
   offscreen; that is expected. Judge the bar: New session with its plus, Open recent, the chip on Logs and
   not on Setup, the step text and the disabled "Running…", and that Setup's page area has no 5px ring.

Fix what is wrong in the CSS, the script or the bar, re-run the affected tests, and render again. Every
departure you keep must already be in spec §10; if you find a new one, add it to §10 in the same commit and
say so in the PR.

Copy four renders into the repo under `docs/design/ui-refresh/renders/phase3/`: `light-ready.png`,
`dark-running.png`, `light-file-problem.png`, `light-no-session.png`.

- [ ] **Step 6: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: only the baseline's failures (the three `tests/test_label_printing.py::TestImageToZpl` tests).

Run: `.venv/bin/ruff check .`
Expected: no findings.

Run: `graphify update .`

- [ ] **Step 7: Commit**

`/usr/bin/git add CONTEXT.md docs .github/workflows/build_release.yml`, check `/usr/bin/git status --short`,
and commit with the message `Phase 3 docs: glossary, ADR notes, roadmap, renders, and the bundle check`.

- [ ] **Step 8: What the PR must say (for Stage C)**

Leave these in your handoff note; the PR body carries them:

- Nothing in `shared/` changed, so nothing reaches Packing Tool.
- The three pre-existing `TestImageToZpl` failures.
- **The Windows check, before the release:** on a warehouse PC over RDP, with this build and with the
  previous release, open Task Manager's Details tab once the window is idle on Setup, add up Memory for the
  app's own process and every `QtWebEngineProcess.exe`, and time the launch to a drawn Setup page. Linux says
  about +31 MB and under +0.2 s. If Windows shows much more, say so on the roadmap task before phase 4.
- Behaviour changes an operator will notice: file problems are in the card, not in a banner; a dropped stock
  file now gets the anomaly check a picked one gets; Replace empties the card; New session is always in the
  bar; Run analysis is on the page, not in the bar; Cancel works; Open session folder is in the ⋯ menu.
- Known limit (spec §7.1): cancelling a re-run leaves the new input copies beside the old results until the
  next run.

---

## Self-review (done at planning time)

- **Spec coverage:** §3.1 files → Tasks 1, 3, 5, 6, 7, 8. §3.2 → Task 1. §3.3 → Task 5. §3.4 → Task 6.
  §4 → Task 3; §4.5 → Task 7. §5 → Tasks 4, 6. §6 → Task 7 (and `csv_row_stats` in Task 2). §7 → Tasks 2, 9.
  §8 → Task 8. §9 → Task 10. §11's seams each have a test in the task that owns the code. §12 → Task 11.
- **Checked against a real Chromium at planning time:** the code in Tasks 3, 4 (CSS), 5 and 6 was extracted
  from this plan into a scratch directory and its tests run: 49 state and slot tests, 13 bridge tests and 25
  page tests passed, and seven states were rendered in both themes and looked at. Tasks 7 to 10 were not run;
  they are written against the code as it stands at d512cb9.
- **Types:** `FileSlot.set_loaded(path, *, rows, keys, delimiter, parts, note, name)` is what Task 7's
  `validate_file` passes; `validate_multiple_files` returns four values and `load_folder` unpacks four;
  `CommandBar.set_step(index, total, name)` is called with those three in Task 9; `setup_state`'s `run` dict
  keys match what `setup.js` reads (`enabled`, `running`, `locked`, `step`, `steps`, `step_name`,
  `can_cancel`, `cancelling`).
