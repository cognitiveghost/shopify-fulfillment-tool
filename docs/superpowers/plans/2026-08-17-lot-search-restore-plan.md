# Lot Search Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **The runner's Stage B declines the `subagent-driven-development` switch — stay in-session.**

**Goal:** Make batch numbers and expiry dates searchable again in the fulfillment table's search
box, on both single-lot and multi-lot rows.

**Architecture:** Add `cell_search_text()` to `gui/pandas_model.py` — a haystack builder used
*only* by the filter proxy, kept separate from `cell_display_text()` which renders what the table
shows. For a `Lot_Details` list cell the haystack is the display text, plus each lot's tooltip
line, plus each lot's raw expiry string. For every other cell it returns `cell_display_text()`
unchanged. Then fix the sibling tag filter four lines away, which has the same
`pd.isna`-on-a-list defect.

**Tech Stack:** Python 3.14, PySide6 (`QSortFilterProxyModel`), pandas, pytest.

**Spec:** None — bounded task. The design is inlined in the Context section below, per the same
convention PR #285's plan used.

## Global Constraints

- **Never hand-edit anything under `shared/`** — one-way synced from `../packing-tool`.
  This plan does not touch `shared/`.
- **No hardcoded colors.** This plan adds no stylesheets.
- **No new dependencies.** `json` is stdlib; everything else is already imported.
- **Do not bump the version string.** Bug fix on a pre-release; `1.9.9.1` stays.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and
  `ruff check . --exclude shared`.
- **Baseline is 677 passed**, measured first-hand on this worktree at `06dbf2e` on 2026-08-17.
  Expected after this plan: **683**.
- Use `.venv/bin/python` — bare `python` is not on PATH on this machine.

---

## Context: why this change, and why not the obvious alternatives

### What broke

PR #285 consolidated three copies of cell-rendering logic into `cell_display_text()` and pointed
the search filter at it (`gui/pandas_model.py:74`). That fixed a real crash. It also changed what
the filter searches for `Lot_Details` cells: from the raw Python repr of the lot list to the
string `"2 lots"`. Batch numbers and expiry dates stopped being findable.

### The prior behaviour was *also* wrong — don't just revert

Before #285 the haystack was `str(lot_list)`, e.g.:

```
[{'expiry': '261230', 'expiry_dt': datetime.date(2026, 12, 30), 'batch': 'B1', 'qty_allocated': 2.0}]
```

- Searching `261230` or `B1` worked — **only on single-lot rows**.
- Any row with 2+ lots raised `ValueError: truth value of an array is ambiguous` instead.
- Searching `2026-12-30` never worked: the repr spells it `datetime.date(2026, 12, 30)`.
- Searching `qty_allocated` matched every lot row — dict *key names* were in the haystack.

So "old vs new" is a false choice. Neither made the ISO date searchable; neither worked on
multi-lot rows. Reverting to `str(cell)` would reintroduce the #285 crash.

### The shape of a lot dict (verified, `shopify_tool/analysis.py:152-160` and `:696-702`)

```python
{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0}
```

`expiry` is the **raw string exactly as it appeared in the stock CSV** — this is the form a
warehouse user reads off the ERP and types into the search box. `expiry_dt` is the parsed date,
and is what `_format_lot()` renders into the tooltip as ISO `2026-12-30`. **These are different
strings, and users may reasonably type either.** That is the entire reason the haystack includes
both rather than picking one.

Two further wrinkles that are already covered by the design, so don't "fix" them:

- When a stock row has no expiry, `_build_fifo_lots` stores the sentinel `expiry="1"`
  (`analysis.py:133`). It lands in the haystack. Searching `1` in all-columns mode already
  matches order numbers and quantities everywhere, so this changes nothing meaningful.
- An unparseable expiry renders as `exp unparsed ('2805')`, so the raw value appears twice in the
  haystack. Harmless.

### The contract this establishes

> **You can search anything the cell shows you — its display text and its tooltip — plus the raw
> expiry string as it appears in the stock file.**

That is a strict superset of the pre-#285 behaviour for every field a person would actually type
(batch, raw expiry), it adds the ISO date, and it works on multi-lot rows, which worked at no
prior revision. What it drops is repr noise (`qty_allocated` as a literal token,
`datetime.date(...)`), which nobody searches for.

### Why a second function instead of changing `cell_display_text`

`cell_display_text` has three other callers that render cells into visible widgets
(`gui/rule_test_dialog.py:364,460-461,482` and `PandasModel.data` at `:208`). Widening it would
put `"2x, exp 2026-12-30, Batch B1\n261230"` into table cells. The renderer and the haystack want
genuinely different strings — that is a real requirement, not speculative generality.

### Task 2: the sibling bug, and why `json.dumps` and not a reordered check

`state.md` lists the tag filter at `gui/pandas_model.py:58` as the last known member of the
`pd.isna`-on-a-list bug class. It sits four lines above the line Task 1 edits, in the same method.
Leaving it is precisely how the #285 bug happened: PR #276 patched one caller of this pattern and
left its sibling broken.

It is currently unreachable — every `Internal_Tags` write path serializes to a JSON string. But
two other modules already defend against the unserialized case in as many words:
`shopify_tool/tag_manager.py:78` (`# Check list first (before pd.isna which fails on lists)`) and
`shopify_tool/barcode_processor.py:82` (`Internal_Tags is sometimes stored unserialized`).
`pandas_model.py:58` is the only one of the three that doesn't.

**The non-obvious part:** reordering the `isna` check is not enough. Verified in the interpreter:

```
str(["URGENT"])         -> "['URGENT']"     # single quotes
'"URGENT"' in that      -> False            # the needle MISSES
json.dumps(["URGENT"])  -> '["URGENT"]'
'"URGENT"' in that      -> True
```

The needle is built as `f'"{tag}"'` with double quotes (`set_tag_filter`, `:36`). A plain
`str()` on a list produces Python repr with single quotes, so it would silently filter every row
out instead of raising. `json.dumps` is required.

### Out of scope — do not add these

- Caching the haystack per row. `filterAcceptsRow` rebuilds it per keystroke, but the pre-#285
  code built a full `repr` of the same list on the same path, so this is not a regression. Measure
  before optimizing.
- Making the `"N lots"` wording column-aware.
- `ColumnConfigPanel` list-stretch bug; `gui/settings/rules.py:963-967` hardcoded colors (needs
  `shared/theme.py` in `packing-tool`); long validation messages clipping
  (`setHeightForWidth(True)` was already probed and does **not** fix it).

### Note for whoever opens the PR

`docs/superpowers/` was deleted wholesale in PR #286 (46 files, 27.5k lines) — that was
housekeeping of *completed* plans and specs, not a change of convention (the runner's `prompt.md`
and this repo's `CLAUDE.md` both still reference the path). This plan recreates the directory with
a single file. Mention in the PR body that it can be deleted once merged, so the archive doesn't
regrow.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `gui/pandas_model.py` | Qt model + filter proxy for the fulfillment table | Add `cell_search_text()`; repoint the filter at it; fix the tag filter's list case |
| `tests/test_pandas_model.py` | Regression tests for that module | Append 6 tests |

No new files. `tests/test_pandas_model.py` uses **module-level test functions** (not classes — the
sibling `tests/test_rule_test_dialog.py` uses classes; do not copy that style here). It already
defines the fixtures the new tests need:

- `_lot_proxy(lots)` (`:29`) — a `FulfillmentFilterProxy` over a one-row frame whose columns are
  `SKU` (value `"A1"`) then `Lot_Details`.
- `_TWO_LOTS` (`:36`) — exactly the fixture these tests need. **Reuse both; do not redefine them.**

---

## Task 1: Searchable lot fields

**Files:**
- Modify: `gui/pandas_model.py` — add `cell_search_text()` after `cell_display_text()` (which ends
  at `:104`); change `:74`
- Test: `tests/test_pandas_model.py` — append at end of file (currently 127 lines)

**Interfaces:**
- Consumes: `cell_display_text(value) -> str` (`:91`) and `_format_lot(lot: dict) -> str` (`:80`),
  both already in this module.
- Produces: `cell_search_text(value) -> str` — module-level, imported by name in tests.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pandas_model.py`. Note the import line at `:16` must gain
`cell_search_text`:

```python
from gui.pandas_model import (
    FulfillmentFilterProxy,
    PandasModel,
    cell_display_text,
    cell_search_text,
)
```

```python
def test_cell_search_text_exposes_batch_and_both_expiry_forms():
    """The haystack carries the raw stock-file expiry AND the parsed ISO date.

    Users read '261230' off the ERP but see '2026-12-30' in the tooltip; both
    must find the row. See the plan's Context section.
    """
    hay = cell_search_text(_TWO_LOTS)
    assert "B1" in hay             # batch
    assert "261230" in hay         # raw expiry, as typed from the ERP
    assert "2026-12-30" in hay     # parsed expiry, as shown in the tooltip
    assert "270101" in hay         # second lot, raw
    assert "2027-01-01" in hay     # second lot, parsed
    assert "2 lots" in hay         # display text is still part of the haystack


def test_cell_search_text_leaves_non_list_cells_identical_to_display_text():
    """Only list cells widen; every other column must behave exactly as before."""
    for value in ["A1", None, float("nan"), 5, []]:
        assert cell_search_text(value) == cell_display_text(value)


def test_text_filter_finds_a_row_by_batch_number():
    """The #285 regression, stated as the user sees it."""
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("B1")
    assert proxy.rowCount() == 1


def test_text_filter_finds_a_row_by_raw_and_iso_expiry():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("261230")
    assert proxy.rowCount() == 1
    proxy.set_text_filter("2026-12-30")
    assert proxy.rowCount() == 1


def test_batch_search_works_on_the_second_lot_of_a_multi_lot_row():
    """Never worked at any revision: pre-#285 this raised, post-#285 it missed."""
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("2027-01-01")
    assert proxy.rowCount() == 1
```

Two things that were verified in the interpreter, so don't second-guess them:

- `set_text_filter` casefolds by default, and `"b1"` only matches after casefolding — the needles
  above are written in the case they appear in, so they pass either way.
- `_lot_proxy`'s first column holds `"A1"`, which contains no digits used above, so none of these
  needles short-circuit on an earlier column.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v
```

Expected: collection fails with `ImportError: cannot import name 'cell_search_text'`. That single
error is the correct "red" here — the import is at module scope, so every test in the file errors
until Step 3 lands.

- [ ] **Step 3: Add `cell_search_text` and point the filter at it**

Insert directly after `cell_display_text` (after `:104`, before `class PandasModel`):

```python
def cell_search_text(value) -> str:
    """Render one DataFrame cell as the text the *search filter* matches against.

    Deliberately wider than :func:`cell_display_text`: a ``Lot_Details`` cell
    displays as "2 lots", but users search it by batch number or expiry date.
    The haystack is the display text, plus each lot's tooltip line, plus each
    lot's raw ``expiry`` string.

    Both expiry forms are included on purpose. ``expiry`` is the raw stock-file
    string ("261230") that a user reads off the ERP; ``_format_lot`` renders the
    parsed ISO date ("2026-12-30") that the tooltip shows. They are different
    strings and either is a reasonable thing to type.

    Non-list cells return ``cell_display_text(value)`` unchanged, so no other
    column's filtering behaviour changes.
    """
    text = cell_display_text(value)
    if not isinstance(value, list) or not value:
        return text
    parts = [text]
    for lot in value:
        if not isinstance(lot, dict):
            parts.append(str(lot))
            continue
        parts.append(_format_lot(lot))
        raw = lot.get("expiry")
        if raw:
            parts.append(str(raw))
    return "\n".join(parts)
```

Then change `gui/pandas_model.py:74` from:

```python
            hay = cell_display_text(cell)
```

to:

```python
            hay = cell_search_text(cell)
```

Finally, update the class docstring at `:16-17`, which currently promises the now-outdated
contract "Matching is plain substring on the cell's display text." Replace that sentence with:

```
    cell's search text (see :func:`cell_search_text` — the display text, widened
    for lot cells so batch numbers and expiry dates stay findable), and the text
```

so the full sentence reads "Matching is plain substring on the cell's search text (see
`cell_search_text` — the display text, widened for lot cells so batch numbers and expiry dates
stay findable), and the text and tag filters are ANDed together instead of being mutually
exclusive."

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v
```

Expected: PASS, 17 tests in this file (11 existing + 5 new). The pre-existing
`test_text_filter_matches_a_lot_cell_by_its_displayed_text` and
`test_text_filter_over_a_multi_lot_row_does_not_raise` must **still** pass — the display text
remains in the haystack precisely so they do.

- [ ] **Step 5: Commit**

```bash
git add gui/pandas_model.py tests/test_pandas_model.py
git commit -m "Restore batch and expiry search on lot cells

PR #285 pointed the search filter at cell_display_text, so Lot_Details
cells became searchable only as \"2 lots\" -- batch numbers and expiry
dates stopped matching.

Add cell_search_text: display text + each lot's tooltip line + each lot's
raw expiry string. Superset of the pre-#285 repr for every field a user
types, and unlike the repr it works on multi-lot rows and matches the ISO
date the tooltip shows."
```

---

## Task 2: Tag filter survives an unserialized tag list

**Files:**
- Modify: `gui/pandas_model.py:57-58`, and add `import json` at `:1`
- Test: `tests/test_pandas_model.py` — append at end of file

**Interfaces:**
- Consumes: `FulfillmentFilterProxy.set_tag_filter(tag)` (`:34`), which builds the needle as
  `f'"{tag}"'`.
- Produces: nothing new. Behaviour change only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pandas_model.py`:

```python
def test_tag_filter_matches_an_unserialized_tag_list():
    """Internal_Tags is normally a JSON string, but tag_manager.py:78 and
    barcode_processor.py:82 both document that it is sometimes a native list.

    Two distinct bugs on that path: pd.isna(list) raises for 2+ elements, and
    str(["URGENT"]) is "['URGENT']" -- single quotes, so the double-quoted
    needle misses even when it doesn't raise. Hence json.dumps.
    """
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(
        PandasModel(pd.DataFrame({"SKU": ["A1"], "Internal_Tags": [["URGENT", "FRAGILE"]]}))
    )
    proxy.set_tag_filter("URGENT")
    assert proxy.rowCount() == 1  # must not raise, and must not filter the row out
    proxy.set_tag_filter("MISSING")
    assert proxy.rowCount() == 0
```

The two-element list is deliberate: a one-element list would not trigger the `pd.isna` raise, so
it would only catch the quoting half of the bug.

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_pandas_model.py::test_tag_filter_matches_an_unserialized_tag_list -v
```

Expected: FAIL with `ValueError: The truth value of an array with more than one element is
ambiguous` raised from `pd.isna(val)` at `gui/pandas_model.py:58`.

- [ ] **Step 3: Use json.dumps for the list case**

Add to the imports at the top of `gui/pandas_model.py` (stdlib first, above `import pandas as pd`):

```python
import json
```

Replace `gui/pandas_model.py:57-58`:

```python
            val = df.iat[source_row, df.columns.get_loc("Internal_Tags")]
            if self._tag_needle not in ("" if pd.isna(val) else str(val)):
                return False
```

with:

```python
            val = df.iat[source_row, df.columns.get_loc("Internal_Tags")]
            if isinstance(val, list):
                # Internal_Tags is normally a JSON string, but is sometimes stored
                # unserialized (tag_manager.py:78, barcode_processor.py:82). json.dumps,
                # not str(): repr uses single quotes, so the double-quoted needle misses.
                hay = json.dumps(val)
            else:
                hay = "" if pd.isna(val) else str(val)
            if self._tag_needle not in hay:
                return False
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pandas_model.py -v
```

Expected: PASS, 18 tests in this file.

- [ ] **Step 5: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: **683 passed** (677 baseline + 6). Ruff clean. If the count is not 683, stop and
reconcile before committing — do not adjust the number to match.

- [ ] **Step 6: Commit**

```bash
git add gui/pandas_model.py tests/test_pandas_model.py
git commit -m "Tag filter: handle an unserialized Internal_Tags list

Last known member of the pd.isna-on-a-list class, four lines from the one
PR #285 fixed. Unreachable today -- every write path serializes to JSON --
but tag_manager.py:78 and barcode_processor.py:82 both already defend
against a native list on this column.

json.dumps rather than a reordered isna check: str([\"URGENT\"]) is
\"['URGENT']\" with single quotes, so the double-quoted needle would miss
silently instead of raising."
```

- [ ] **Step 7: Refresh the knowledge graph**

Required by this repo's CLAUDE.md after modifying code:

```bash
graphify update .
```

---

## Self-Review

**Spec coverage.** The design has three claims and each maps to a task: batch/expiry searchable
again → Task 1 Steps 3-4; works on multi-lot rows →
`test_batch_search_works_on_the_second_lot_of_a_multi_lot_row`; sibling tag bug closed → Task 2.
The "no other column changes" claim is pinned by
`test_cell_search_text_leaves_non_list_cells_identical_to_display_text`.

**Placeholders.** None. Every code step carries literal code; every test step carries a literal
command and its expected output.

**Type consistency.** `cell_search_text(value) -> str` is named identically in the test import,
the implementation, the call site at `:74`, and the docstring cross-reference. `_format_lot` and
`cell_display_text` are consumed at their existing signatures, unmodified.

**Test count arithmetic.** `tests/test_pandas_model.py` collects **12** today — measured, not
counted by eye: it defines 10 test functions, but `test_empty_lot_details_shows_blank_and_no_tooltip`
is parametrized over three empty values and so collects as 3. Task 1 adds 5 → 17 in the file.
Task 2 adds 1 → 18 in the file. Suite: 677 + 6 = **683**.
