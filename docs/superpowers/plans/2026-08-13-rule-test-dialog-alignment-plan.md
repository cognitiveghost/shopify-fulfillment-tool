# Rule Test Dialog Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Runner note:** executing-plans will offer to switch to
> `subagent-driven-development`. **Decline it** and stay in-session — the
> roadmap runner forbids subagents at Stage B.

**Goal:** Make `RuleTestDialog` stop crashing (and stop silently under-reporting) when a rule creates a column or adds a row, by aligning `df_before` and `df_after` once instead of guarding each access site.

**Architecture:** `RuleEngine.apply()` can change a frame's columns, index, and row count. The dialog assumes it changes none of them. Add one `_align_frames()` step immediately after `apply()` that (a) splits `df_after` positionally into original rows and appended rows, reattaching `df_before`'s index to the originals, and (b) `reindex`es `df_before`'s columns onto `df_after`'s. Every populate method then reads the aligned frames, so no per-site `KeyError` guard is needed. Added rows become a counted, displayed category of their own rather than a diff.

**Tech Stack:** Python 3.14, PySide6 (`QDialog`, `QTableWidget`), pandas, pytest + pytest-qt (`qtbot`), ruff.

**Spec:** `docs/superpowers/specs/2026-08-13-rule-test-dialog-alignment-design.md`

## Global Constraints

- **Windows-only production**; development on Ubuntu. Run GUI tests with `QT_QPA_PLATFORM=offscreen`.
- **Never hand-edit `shared/`** — one-way synced from `../packing-tool`.
- **No hardcoded colours in stylesheets** — use `theme_manager` tokens. The two literal diff-highlight hexes in `rule_test_dialog.py` are a documented, `ponytail:`-commented exception at a single call site; extend that comment rather than adding a new `ThemeTokens` field.
- **Do not modify `shopify_tool/rules.py`.** The engine is correct; the dialog is wrong. See spec §5.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared`.
- Use `.venv/bin/python` — bare `python` is not on PATH on this machine. In a fresh worktree run `./scripts/setup_venv.sh` first.
- Version string is **not** bumped by this change (bugfix on an unreleased line).

---

## File Structure

| File | Responsibility |
|---|---|
| `gui/rule_test_dialog.py` (modify) | Add `_align_frames()`; rewrite `_detect_changed_rows`, `_populate_conditions_table`, `_populate_preview_table` and `_populate_after_actions_table` to read the aligned frames. |
| `tests/test_rule_test_dialog.py` (create) | New file. There is no existing coverage for this dialog. Holds the five spec §2 scenarios plus the engine-ordering assumption test. |

No new modules. `rule_test_dialog.py` is 431 lines and gains roughly 40 — no split warranted.

---

### Task 1: Pin the crashes and the engine assumption with failing tests

Establishes the harness and reproduces every symptom before any fix. `_run_test` swallows exceptions into a `QMessageBox.critical`, so "did it crash" is asserted via the `no_modals` fixture from `tests/conftest.py`, which records popups into a list and returns it.

**Files:**
- Create: `tests/test_rule_test_dialog.py`
- Read for reference: `gui/rule_test_dialog.py`, `tests/conftest.py:96-109`

**Interfaces:**
- Consumes: `no_modals` fixture (`tests/conftest.py`), `qtbot` (pytest-qt), `RuleTestDialog(rule_config, analysis_df, parent=None)`.
- Produces: `analysis_df` fixture and `_rule(*actions)` helper used by Tasks 2-4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rule_test_dialog.py`:

```python
"""RuleTestDialog before/after frame alignment.

RuleEngine.apply() can add columns (CALCULATE/COPY_FIELD targets) and append
rows (ADD_PRODUCT, concatenated with ignore_index). The dialog diffs
df_before against df_after, so every one of those shape changes used to
either raise or silently report nothing.
"""
import pandas as pd
import pytest

from gui.rule_test_dialog import RuleTestDialog


@pytest.fixture
def analysis_df():
    """Analysis-shaped: Status_Note and Internal_Tags already exist.

    analysis.py:1097 and :1103 initialise both on every real analysis, so a
    fixture without them tests a frame production never produces.
    """
    return pd.DataFrame({
        "Order_Number": ["1001", "1002", "1003"],
        "SKU": ["A", "B", "A"],
        "Quantity": [1, 2, 3],
        "Total_Price": [10.0, 20.0, 30.0],
        "Product_Name": ["Pa", "Pb", "Pa"],
        "Warehouse_Name": ["Wa", "Wb", "Wa"],
        "Order_Fulfillment_Status": ["Ready", "Not Ready", "Ready"],
        "Status_Note": ["", "", ""],
        "Internal_Tags": ["[]", "[]", "[]"],
    })


def _rule(*actions):
    """Single-step rule matching the two 'Ready' rows."""
    return {
        "name": "t",
        "enabled": True,
        "steps": [{
            "match": "ALL",
            "conditions": [{
                "field": "Order_Fulfillment_Status",
                "operator": "equals",
                "value": "Ready",
            }],
            "actions": list(actions),
        }],
    }


def _open(qtbot, rule, df):
    dialog = RuleTestDialog(rule, df)
    qtbot.addWidget(dialog)
    return dialog


class TestNoCrashOnShapeChange:
    def test_add_tag_is_unaffected(self, qtbot, analysis_df, no_modals):
        """Baseline: passes today. Status_Note already exists, so nothing
        about the frame's shape changes."""
        dialog = _open(qtbot, _rule({"type": "ADD_TAG", "value": "hello"}), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_calculate_target_column_does_not_crash(self, qtbot, analysis_df, no_modals):
        """CALCULATE creates its target at rules.py:1190, so the column is in
        df_after and not in df_before."""
        dialog = _open(qtbot, _rule({
            "type": "CALCULATE", "operation": "multiply",
            "field1": "Quantity", "field2": "Total_Price",
            "target": "Line_Total",
        }), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_copy_field_target_column_does_not_crash(self, qtbot, analysis_df, no_modals):
        dialog = _open(qtbot, _rule({
            "type": "COPY_FIELD", "source": "SKU", "target": "SKU_Copy",
        }), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_add_product_with_a_tag_does_not_crash(self, qtbot, analysis_df, no_modals):
        """ADD_PRODUCT appends rows with ignore_index, so a boolean mask built
        on df_before.index no longer aligns with df_after."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
            {"type": "ADD_TAG", "value": "bonus"},
        ), analysis_df)
        assert no_modals == []


class TestAddedRowsAreReported:
    def test_add_product_alone_reports_the_added_rows(self, qtbot, analysis_df, no_modals):
        """Two matched rows each spawn one product row. Reporting 0 tells the
        user a working rule does nothing."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
        ), analysis_df)
        assert no_modals == []
        assert len(dialog.added_rows) == 2
        assert dialog.matched_count == 2


class TestEngineOrderingAssumption:
    def test_added_rows_are_appended_not_interleaved(self, qtbot, analysis_df, no_modals):
        """_align_frames slices df_after positionally, which is only correct
        while apply() appends. If the engine ever reorders or drops rows, this
        fails here instead of silently mispairing rows in the preview."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
        ), analysis_df)
        n = len(dialog.df_before)
        original = dialog.df_after.iloc[:n]
        assert list(original["Order_Number"]) == list(dialog.df_before["Order_Number"])
        assert list(original["SKU"]) == list(dialog.df_before["SKU"])
```

- [ ] **Step 2: Run the tests to verify they fail for the documented reasons**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v
```

Expected on `main`:
- `test_add_tag_is_unaffected` — **PASS** (baseline).
- `test_calculate_target_column_does_not_crash` — FAIL, `no_modals` non-empty (swallowed `KeyError: 'Line_Total'`).
- `test_copy_field_target_column_does_not_crash` — FAIL, `no_modals` non-empty (swallowed `KeyError: 'SKU_Copy'`).
- `test_add_product_with_a_tag_does_not_crash` — FAIL, `no_modals` non-empty (swallowed `IndexingError: Unalignable boolean Series`).
- `test_add_product_alone_reports_the_added_rows` — FAIL, `AttributeError: 'RuleTestDialog' object has no attribute 'added_rows'`.
- `test_added_rows_are_appended_not_interleaved` — **PASS** (documents current engine behaviour).

If any *other* failure appears, stop and read it — the fix in Task 2 assumes these exact causes.

- [ ] **Step 3: Commit**

```bash
git add tests/test_rule_test_dialog.py
git commit -m "test: pin RuleTestDialog crashes on engine shape changes"
```

---

### Task 2: Align the frames once, after apply()

**Files:**
- Modify: `gui/rule_test_dialog.py:174-237` (`_run_test`, `_detect_changed_rows`)
- Test: `tests/test_rule_test_dialog.py`

**Interfaces:**
- Consumes: `self.df_before`, `self.df_after` as set by `_run_test`.
- Produces: three new instance attributes read by Task 3 —
  - `self.before_aligned: pd.DataFrame` — `df_before` reindexed onto `df_after.columns`; same index as `df_before`.
  - `self.after_existing: pd.DataFrame` — the original rows of `df_after`, carrying `df_before`'s index.
  - `self.added_rows: pd.DataFrame` — rows `apply()` appended; empty when none.
  - `self.matched_count: int` — now `changed.sum() + len(added_rows)`.
  - `self.matches: pd.Series` — unchanged meaning: boolean, indexed like `df_before`, True where an **existing** row changed.

- [ ] **Step 1: Add the three attribute declarations in `__init__`**

In `gui/rule_test_dialog.py`, after the existing `self.matched_count = 0` (line 61):

```python
        # Set by _align_frames(): df_before/df_after made comparable.
        self.before_aligned = None
        self.after_existing = None
        self.added_rows = None
```

- [ ] **Step 2: Call `_align_frames()` from `_run_test`**

Replace lines 196-197 (`# Detect matched rows…` and `self.matches = self._detect_changed_rows()`) with:

```python
            # RuleEngine.apply() may add columns and append rows, so make the
            # two frames comparable before anything diffs them.
            self._align_frames()

            # Detect matched rows by comparing before/after (works for all rule types)
            self.matches = self._detect_changed_rows()
```

And replace line 198 (`self.matched_count = self.matches.sum()`) with:

```python
            self.matched_count = int(self.matches.sum()) + len(self.added_rows)
```

- [ ] **Step 3: Write `_align_frames()`**

Insert immediately before `_detect_changed_rows` (i.e. before line 215):

```python
    def _align_frames(self):
        """Make df_before and df_after comparable.

        apply() changes the frame two ways: CALCULATE/COPY_FIELD create their
        target column mid-apply, and ADD_PRODUCT rows are concatenated with
        ignore_index=True. Either one breaks a naive before/after diff.

        apply() only ever appends -- it has no drop, sort, or reindex -- so
        the first len(df_before) positional rows of df_after are the original
        rows in order. Slice positionally rather than by label: it is correct
        whether or not ignore_index fired, and label alignment is precisely
        what breaks. tests/test_rule_test_dialog.py asserts that assumption.
        """
        n = len(self.df_before)

        self.after_existing = self.df_after.iloc[:n].copy()
        self.after_existing.index = self.df_before.index
        self.added_rows = self.df_after.iloc[n:]

        # A column the rule created reads as NaN before and a value after,
        # which is the truth: the rule changed that cell from nothing.
        self.before_aligned = self.df_before.reindex(columns=self.df_after.columns)

        if len(self.added_rows):
            logger.info(f"[RULE TEST] Rule appended {len(self.added_rows)} new rows")
```

- [ ] **Step 4: Rewrite `_detect_changed_rows` to use the aligned frames**

Replace the whole body of `_detect_changed_rows` (lines 216-237) with:

```python
        """Detect which existing rows were modified, comparing aligned frames.

        Rows the rule *added* are not changes -- they have no before state --
        and are tracked separately in self.added_rows.
        """
        changed = pd.Series(False, index=self.before_aligned.index)

        for col in self.df_after.columns:
            before_vals = self.before_aligned[col].fillna("").astype(str)
            after_vals = self.after_existing[col].fillna("").astype(str)
            changed = changed | (before_vals != after_vals)

        return changed
```

Both frames now carry exactly `df_after.columns` and `df_before.index`, so the
`common_cols`/`new_cols` split and the `.loc[]` lookup are gone. A newly
created column compares `""` (from `NaN`) against its value, so a row only
counts as changed where the rule actually wrote something — the old
`notna() & != 0 & != "" & != 0.0` heuristic is no longer needed.

- [ ] **Step 5: Run the tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v
```

Expected: `TestAddedRowsAreReported` and `TestEngineOrderingAssumption` PASS. The `TestNoCrashOnShapeChange` cases may still FAIL — `_populate_after_actions_table` is fixed in Task 3.

- [ ] **Step 6: Commit**

```bash
git add gui/rule_test_dialog.py
git commit -m "fix: align before/after frames once in RuleTestDialog"
```

---

### Task 3: Read the aligned frames in every populate method

**Files:**
- Modify: `gui/rule_test_dialog.py:239-397` (`_populate_conditions_table`, `_populate_preview_table`, `_populate_after_actions_table`)
- Test: `tests/test_rule_test_dialog.py`

**Interfaces:**
- Consumes: `self.before_aligned`, `self.after_existing`, `self.added_rows`, `self.matches`, `self.matched_count` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Report the added-row split in the summary label**

In `_populate_conditions_table`, replace the summary block (lines 270-272) with:

```python
        summary = f"Final Result ({step_info}, narrowing): "
        summary += f"<span style='color: {theme.accent_green}; {font_css('heading')}'>{self.matched_count}</span> rows affected "
        summary += f"({percentage:.1f}% of {total_rows} total rows)"
        if len(self.added_rows):
            summary += f" — {len(self.added_rows)} added by rule"
```

Changed and added rows are different things; conflating them into one count is
what made ADD_PRODUCT read as a no-op.

- [ ] **Step 2: Point `_populate_preview_table` at the aligned before-frame**

In `_populate_preview_table`, replace line 288:

```python
        matched_df = self.df_before[self.matches].head(5)
```

with:

```python
        matched_df = self.before_aligned[self.matches].head(5)
```

`_get_display_columns` then sees the same column set the after-table does, so
the two previews line up column-for-column.

- [ ] **Step 3: Rewrite `_populate_after_actions_table`**

Replace lines 368-397 (everything after the `matched_count == 0` early return, through `resizeColumnsToContents`) with:

```python
        # Aligned frames: same columns, same index, same length.
        matched_before = self.before_aligned[self.matches].head(5)
        matched_after = self.after_existing[self.matches].head(5)
        added = self.added_rows.head(5)

        display_cols = self._get_display_columns(self.after_existing)

        self.after_table.setRowCount(len(matched_after) + len(added))
        self.after_table.setColumnCount(len(display_cols))
        self.after_table.setHorizontalHeaderLabels(display_cols)

        for row_idx, (idx_after, row_after) in enumerate(matched_after.iterrows()):
            row_before = matched_before.loc[idx_after]

            for col_idx, col_name in enumerate(display_cols):
                value_before = row_before[col_name]
                value_after = row_after[col_name]

                item = QTableWidgetItem(str(value_after))

                # Highlight changed cells
                # ponytail: literal diff-highlight yellow/green, not worth two
                # new ThemeTokens fields for this one call site.
                if value_before != value_after and not (pd.isna(value_before) and pd.isna(value_after)):
                    item.setBackground(QColor("#FFEB3B"))  # Yellow
                    item.setToolTip(f"Changed from: {value_before}")

                self.after_table.setItem(row_idx, col_idx, item)

        # Rows the rule created have no before state, so they are tinted whole
        # rather than diffed cell by cell.
        for offset, (_, row_added) in enumerate(added.iterrows()):
            row_idx = len(matched_after) + offset
            for col_idx, col_name in enumerate(display_cols):
                item = QTableWidgetItem(str(row_added[col_name]))
                item.setBackground(QColor("#C8E6C9"))  # Green
                item.setToolTip("Added by rule")
                self.after_table.setItem(row_idx, col_idx, item)

        self.after_table.resizeColumnsToContents()
```

- [ ] **Step 4: Extend the legend**

Replace line 167:

```python
        legend = QLabel("Yellow highlight = Modified by rule actions")
```

with:

```python
        legend = QLabel(
            "Yellow highlight = Modified by rule actions   |   "
            "Green highlight = Row added by rule"
        )
```

- [ ] **Step 5: Fix the `matched_count == 0` early return**

At line 360 the guard returns before drawing anything. With added rows counted
into `matched_count`, an ADD_PRODUCT-only rule now has `matched_count > 0` and
`self.matches.sum() == 0`, so it falls through correctly and the added rows
render. No change is needed to the condition itself — **verify** it reads:

```python
        if self.matches is None or self.matched_count == 0:
```

and leave it. The same guard in `_populate_preview_table` (line 279) also
stays: that table shows *before* rows, and an added row has no before state, so
"No rows matched the conditions" is the right thing to show there.

- [ ] **Step 6: Run the tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v
```

Expected: all six PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/rule_test_dialog.py
git commit -m "fix: show added rows and stop KeyErroring on rule-created columns"
```

---

### Task 4: Full gate

**Files:**
- Modify: none expected.

**Interfaces:**
- Consumes: everything above.
- Produces: a green branch.

- [ ] **Step 1: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Expected: 567 prior + 6 new = **573 passed**. If anything else broke, it is
almost certainly a test asserting the old `matched_count` semantics — read it
before changing it, and prefer fixing the dialog over loosening the test.

- [ ] **Step 2: Lint**

```bash
.venv/bin/ruff check . --exclude shared
```

Expected: clean. Watch for an unused `pd` import if the `pd.isna` call moved.

- [ ] **Step 3: Commit any gate fixes**

```bash
git add -A
git commit -m "fix: gate fixes for rule test dialog alignment"
```

Skip if nothing changed.

- [ ] **Step 4: Push**

```bash
git push -u origin worktree-rule-test-crash
```

---

## Self-Review

**Spec coverage:**
- §3(a) new columns → Task 2 Step 3 (`reindex`), Task 3 Step 3 (`display_cols` from `after_existing`). Tests: `test_calculate_…`, `test_copy_field_…`.
- §3(b) appended rows → Task 2 Step 3 (positional split). Test: `test_add_product_with_a_tag_does_not_crash`.
- §3 silent under-report → Task 2 Step 2 (`matched_count`), Task 3 Step 1 (summary). Test: `test_add_product_alone_reports_the_added_rows`.
- §4.1 ordering assumption → Task 1, `test_added_rows_are_appended_not_interleaved`.
- §4.3 added rows displayed → Task 3 Steps 3-4.
- §5 out-of-scope items → Global Constraints forbids touching `rules.py`.

**Placeholders:** none — every code step carries the literal code.

**Type consistency:** `before_aligned`, `after_existing`, `added_rows` are declared in Task 2 Step 1, set in Task 2 Step 3, and consumed under those exact names in Task 3 Steps 1-3 and in Task 1's tests. `matched_count` stays `int`; `matches` keeps its `df_before`-indexed boolean meaning.
