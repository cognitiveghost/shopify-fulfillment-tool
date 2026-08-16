# Cell Render Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> The runner's Stage B runs **in-session** — `executing-plans` will offer to switch to
> `subagent-driven-development`; **decline it**.

**Goal:** Route every DataFrame-cell-to-text rendering in the GUI through one function, which
fixes a live crash in the main table's search box on lot-tracked analyses.

**Architecture:** `gui/pandas_model.py` grows a module-level `cell_display_text(value) -> str`
holding the list-before-`pd.isna` ordering that PR #276 established. Its three callers —
`PandasModel.data()`, `FulfillmentFilterProxy._matches_text()`, and `gui/rule_test_dialog.py` —
all call it instead of carrying their own copy. Net-negative diff; the only behaviour change is
in the search filter, which stops crashing.

**Tech Stack:** PySide6 (`QAbstractTableModel`, `QSortFilterProxyModel`), pandas, pytest.

**Spec:** none. This is a bounded change to code that already exists here, so
`superpowers:brainstorming`'s bounded path produces no spec doc — the design is inlined in the
Context section below. (Same convention as the `rule-preview-fidelity` plan.)

## Global Constraints

- Windows-only product, developed on Linux. Run everything through `.venv/bin/python`; bare
  `python` is not on PATH.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and
  `.venv/bin/ruff check . --exclude shared`.
- Never hand-edit anything under `shared/`. This plan touches nothing there.
- No hardcoded colors. This plan adds no styling.
- No version bump — this matches the surrounding bug-fix PRs (#281–#284), none of which bumped.

---

## Context — what is wrong and why

### The duplication

`gui/rule_test_dialog.py:30-44` defines `_cell_text(value)`. Its own docstring says it "Mirrors
gui/pandas_model.py:182-194" — a line-number reference, which this repo's history shows goes
stale. The two copies share the `"N lots"` wording, the empty-list-is-blank rule, and the
load-bearing ordering (list check **before** `pd.isna`).

### The bug that duplication hid

`FulfillmentFilterProxy._matches_text` (`gui/pandas_model.py:74`) is a **third** copy of the same
idea, written wrong:

```python
hay = "" if pd.isna(cell) else str(cell)
```

`pd.isna()` on a list of 2+ elements returns an **array**, and `if <array>:` raises
`ValueError: The truth value of an array with more than one element is ambiguous`. That is
exactly the crash class PR #276 fixed — but #276 fixed it at one caller (`data()`) and left this
sibling caller broken.

**It is live in production, not theoretical:**

- `gui/ui_manager.py:886` builds the model from **all** columns (`main_df = data_df.copy()`,
  commented "visibility is handled by the view"), so `Lot_Details` is in the proxy's frame even
  when the column is hidden.
- `Lot_Details` is a standard analysis output column (`shopify_tool/analysis.py:1139`) holding
  real `list[dict]` on any lot-tracked run.
- The search box defaults to "All Columns" (`df_col = -1`, `gui/main_window_pyside.py:1207`), so
  the scan reaches the `Lot_Details` cell.

Reproduced against the real classes before this plan was written:

| search text | result |
|---|---|
| `1001` (matches `Order_Number`, an earlier column) | 1 row — the loop short-circuits before `Lot_Details` |
| `zzz` (matches nothing) | **`ValueError` — crash** |

So it survives only while every scanned row matches on some column left of `Lot_Details`. Any
search that narrows the table — i.e. the point of searching — walks a non-matching row into the
list cell and raises. Single-lot and empty rows are safe; 2+ lots on one SKU line crash.

The tag-filter path two lines up (`:58`) has the same shape but is **safe**: `Internal_Tags`
holds a JSON *string* (`analysis.py:1103` sets `"[]"`), never a list. Verified — leave it alone.

### Judgment call, so review does not re-litigate it

**The filter will match a lot cell's displayed text (`"2 lots"`), not its raw `repr`.**

Today an uncrashed single-lot row is searched as `str([{'expiry': '261230', 'batch': 'B1', ...}])`,
so typing `qty_allocated` or a batch number matches a row whose visible cells contain no such
text. That is not a feature anyone can use deliberately, the class docstring already promises
"Matching is plain substring on the cell's display text", and on the multi-lot rows where batch
search would actually matter it crashes instead.

Known cost: batch/expiry text stops being searchable on single-lot rows. Accepted. If the user
wants it back it is one line — `hay` becomes the tooltip join for list cells — but that would
mean searching text the table does not show.

### Deliberately out of scope

- The `"N lots"` wording is column-agnostic — any list-valued column renders as lots. Only
  `Lot_Details` holds lists today; fixing it needs column context threaded into the renderer, for
  no present gain.
- Multi-element `ndarray`/`Series` cells still raise from `pd.isna`. Nothing in the app puts them
  in a frame; consolidating means the fix would now land in one place if that ever changes.
- `gui/settings/rules.py:963-967` hardcoded colors (cross-repo, needs `shared/theme.py`).
- `ColumnConfigPanel` list-stretch bug.

---

## File Structure

- `gui/pandas_model.py` — gains `cell_display_text()` next to the existing `_format_lot()` helper;
  `data()` and `_matches_text()` both call it. Owner of the rendering rule.
- `gui/rule_test_dialog.py` — loses `_cell_text()`, imports the shared function. Pure consumer.
- `tests/test_pandas_model.py` — already the home of this crash class (its module docstring
  describes it). The new proxy regression tests append here.

---

### Task 1: Extract the shared renderer

**Files:**
- Modify: `gui/pandas_model.py` (add `cell_display_text` after `_format_lot` at `:89`; rewrite the
  `DisplayRole`/`ToolTipRole` branch of `PandasModel.data()` at `:177-194`)
- Test: `tests/test_pandas_model.py`

**Interfaces:**
- Produces: `cell_display_text(value) -> str` — module-level in `gui/pandas_model.py`. Public (no
  leading underscore) because Task 3 imports it from another module. Total function, never raises
  for `None`, scalars, `NaN`, or lists.

This task is a pure extraction: the five existing tests in `tests/test_pandas_model.py` already
pin every branch of `data()` and are the real gate. The two new tests below exist only because
Task 3 makes this function a cross-module contract.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pandas_model.py`. Match the file's existing style — plain asserts, a
docstring only where the *why* is not obvious from the name.

```python
def test_cell_display_text_renders_empty_and_missing_as_blank():
    assert cell_display_text(None) == ""
    assert cell_display_text([]) == ""
    assert cell_display_text(float("nan")) == ""


def test_cell_display_text_counts_lots_without_raising():
    """The list check must precede pd.isna(); see this module's docstring."""
    lots = [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
    ]
    assert cell_display_text(lots) == "2 lots"
    assert cell_display_text(lots[:1]) == "1 lot"
    assert cell_display_text("A1") == "A1"
```

Extend the existing import at the top of the file:

```python
from gui.pandas_model import PandasModel, cell_display_text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v`
Expected: collection error — `ImportError: cannot import name 'cell_display_text'`.

- [ ] **Step 3: Add the function**

Insert directly after `_format_lot()` (which ends at `gui/pandas_model.py:88`):

```python
def cell_display_text(value) -> str:
    """Render one DataFrame cell as the text the user sees in a table.

    The list check MUST come before ``pd.isna()``: ``Lot_Details`` holds real
    Python lists, and ``pd.isna()`` on a list returns an *array*, so a plain
    ``if`` on it raises "truth value of an array is ambiguous". Every caller
    that renders or searches cell text must go through here — a private copy
    is how that crash got reintroduced in the filter proxy.
    """
    if isinstance(value, list):
        if not value:
            return ""
        return f"{len(value)} lot{'s' if len(value) != 1 else ''}"
    if pd.isna(value):
        return ""
    return str(value)
```

- [ ] **Step 4: Rewrite the `data()` branch to use it**

Replace `gui/pandas_model.py:177-194` — the whole block from `if role in (...)` down to and
including `return str(value)` — with:

```python
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            try:
                value = self._dataframe.iloc[row, col_index]
            except IndexError:
                return None

            if role == Qt.ItemDataRole.ToolTipRole:
                if isinstance(value, list) and value:
                    return "\n".join(_format_lot(lot) for lot in value)
                return None  # no tooltip for empty or plain scalar cells

            return cell_display_text(value)
```

This is behaviour-identical to the original on all six paths (Display/ToolTip × non-empty list /
empty list / scalar). Do not "improve" it further — the existing tests encode each one.

- [ ] **Step 5: Run the full model test file**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add gui/pandas_model.py tests/test_pandas_model.py
git commit -m "refactor: extract cell_display_text() from PandasModel.data()"
```

---

### Task 2: Fix the search-filter crash

**Files:**
- Modify: `gui/pandas_model.py:74` (inside `FulfillmentFilterProxy._matches_text`)
- Test: `tests/test_pandas_model.py`

**Interfaces:**
- Consumes: `cell_display_text` from Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pandas_model.py`. `FulfillmentFilterProxy` is not yet imported in this file
— extend the import from Task 1 again:

```python
from gui.pandas_model import FulfillmentFilterProxy, PandasModel, cell_display_text
```

Add a helper next to the existing `_model()` helper:

```python
def _lot_proxy(lots):
    """Proxy over a frame whose *last* column holds a lot list, as analysis emits it."""
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(PandasModel(pd.DataFrame({"SKU": ["A1"], "Lot_Details": [lots]})))
    return proxy


_TWO_LOTS = [
    {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
    {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
]
```

and the tests:

```python
def test_text_filter_over_a_multi_lot_row_does_not_raise():
    """Regression: pd.isna(list) raised inside filterAcceptsRow.

    The needle must match no earlier column, otherwise the column scan
    short-circuits before it ever reaches the list cell -- which is why this
    crash survived in production while ordinary searches looked fine.
    """
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("zzz")
    assert proxy.rowCount() == 0  # must not raise


def test_text_filter_matches_a_lot_cell_by_its_displayed_text():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("2 lots")
    assert proxy.rowCount() == 1


def test_text_filter_still_matches_plain_scalar_columns():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("a1")  # case-insensitive by default
    assert proxy.rowCount() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -k filter -v`

Expected: `test_text_filter_over_a_multi_lot_row_does_not_raise` and
`test_text_filter_matches_a_lot_cell_by_its_displayed_text` FAIL. The first fails with
`ValueError: The truth value of an array with more than one element is ambiguous`, wrapped by
PySide6 as an error calling the `filterAcceptsRow` override. The second fails on
`assert 0 == 1`. The third passes already — it is there to prove the fix does not regress the
normal path.

- [ ] **Step 3: Make the fix**

In `_matches_text`, replace:

```python
            hay = "" if pd.isna(cell) else str(cell)
```

with:

```python
            hay = cell_display_text(cell)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v`
Expected: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add gui/pandas_model.py tests/test_pandas_model.py
git commit -m "fix: search filter crashed on rows with 2+ allocated lots"
```

---

### Task 3: Point the rule test dialog at the shared renderer

**Files:**
- Modify: `gui/rule_test_dialog.py` (delete `_cell_text` at `:30-44`; add the import; update the
  three call sites at `:380`, `:476-477`, `:498`)
- Test: `tests/test_rule_test_dialog.py` (existing, unchanged)

**Interfaces:**
- Consumes: `cell_display_text` from Task 1.

A pure move — `_cell_text`'s body is character-identical to `cell_display_text`'s. The seventeen
existing tests in `tests/test_rule_test_dialog.py` are the gate; add no new ones. (Note that file
groups its tests in classes, unlike `tests/test_pandas_model.py` — you are adding nothing there,
but do not let the two conventions bleed into each other.)

- [ ] **Step 1: Delete the private copy**

Remove `gui/rule_test_dialog.py:30-44` entirely — the `def _cell_text(value) -> str:` block and
its docstring.

- [ ] **Step 2: Import the shared function**

`gui/rule_test_dialog.py:27` already reads `from gui.theme_manager import font_css,
get_theme_manager`. Add above it:

```python
from gui.pandas_model import cell_display_text
```

**Keep `import pandas as pd` at `:13`.** It is still used at `:294` (`pd.Series(False, ...)`),
verified before this plan was written — deleting it breaks the dialog. Ruff will confirm nothing
went unused.

- [ ] **Step 3: Update the three call sites**

Rename `_cell_text(` to `cell_display_text(` at `:380`, `:476`, `:477` and `:498`:

```bash
.venv/bin/python - <<'PY'
import pathlib
p = pathlib.Path("gui/rule_test_dialog.py")
p.write_text(p.read_text().replace("_cell_text(", "cell_display_text("))
PY
```

Then confirm no stale references survive:

Run: `grep -n "_cell_text" gui/rule_test_dialog.py`
Expected: no output.

- [ ] **Step 4: Run the dialog tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v`
Expected: PASS, all pre-existing tests, no new failures.

- [ ] **Step 5: Run the whole gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: the full suite green — **675 tests: 670 on this branch's base (measured at
`origin/main` before any of this work), plus the 5 added here**. Ruff clean. If the count
differs, say so in the commit rather than adjusting the number to match.

- [ ] **Step 6: Commit**

```bash
git add gui/rule_test_dialog.py
git commit -m "refactor: rule test dialog renders cells via the shared helper"
```

- [ ] **Step 7: Refresh the knowledge graph**

```bash
graphify update .
```

Per this repo's CLAUDE.md, run this immediately after the code changes land, not "eventually".
Commit any resulting `graphify-out/` changes.

---

## Note for whoever reviews this at Stage C

The one thing worth a second opinion is the judgment call in the Context section — the search
filter now matches a lot cell's *displayed* text rather than its raw `repr`. Everything else is a
move plus a one-line bug fix.

Do not add the out-of-scope items listed above; they were considered and deferred on purpose.
