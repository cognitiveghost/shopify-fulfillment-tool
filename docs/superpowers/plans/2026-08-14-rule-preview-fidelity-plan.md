# Rule Editor & Test Dialog Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> The roadmap runner's Stage B explicitly declines `subagent-driven-development` — stay in-session.

**Goal:** Stop the rule editor and its Test dialog from telling the user things `shopify_tool/rules.py` will not do.

**Architecture:** Three independent defects in two GUI files, all the same shape — the UI's model of the rule engine drifted from the engine. No engine changes, no new modules, no new dependencies. Each task is one behaviour, one test class, one commit.

**Tech Stack:** Python 3, PySide6, pandas, pytest + pytest-qt (headless via `QT_QPA_PLATFORM=offscreen`).

**Spec:** None. This is a bounded task under the p1 "Revision, bug fixes" milestone; `superpowers:brainstorming`'s bounded path produces no spec document. The design is inlined in Context below.

## Global Constraints

- Python target and dependencies come from `requirements.txt`. **Do not add a dependency**, and do not create a `pyproject.toml` (CLAUDE.md).
- **Never hand-edit anything under `shared/`** — it is one-way synced from `../packing-tool` (CLAUDE.md). No task here touches it.
- **No hardcoded colors in stylesheets** — use `get_theme_manager().get_current_theme()` tokens. No task here adds a color.
- Gate before finishing, from the worktree root:
  - `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
  - `.venv/bin/ruff check . --exclude shared`
  - `python` and `ruff` are **not** on PATH on this machine — always go through `.venv/bin/`.
- Branch `worktree-rule-preview-fidelity`. Commit per task. **No direct commits to `main`; PR-only.**
- Run `graphify update .` once at the end (CLAUDE.md).

## Context — the three defects

**1. The `is empty` operator's dead branch.** `gui/settings/rules.py:778` reads:

```python
if op in ["is_empty", "is_not_empty"]:
```

but the combo is filled from `CONDITION_OPERATORS` (`gui/settings/fields.py:29-51`), which supplies `"is empty"` and `"is not empty"` — with spaces. The branch never fires, so choosing "is empty" builds a `QLineEdit` for a value that `_op_is_empty(series_val, rule_val)` (`shopify_tool/rules.py:175`) discards. The user types a value that does nothing.

Saving is already safe: `_gather_rule_config` defaults `val = ""` when `value_widget` is `None` (`gui/settings/rules.py:1122-1131`).

Making the branch live makes `_perform_validation`'s early `return` at `:895` reachable for the first time. That `return` skips the `_check_field_resolvable(condition_refs)` at the method's tail (`:947`) — the "this field will never match" flag from PR #278. Both existing callers happen to re-call it themselves (`:198-199` and `:779`), so nothing regresses today, but the early exits at `:895` and `:906` must fall through to the resolvability check rather than bail, or the next caller added will silently lose the flag.

**2. The Test dialog does not normalize action-type case.** The engine uppercases at `shopify_tool/rules.py:917` and `:1051`; `gui/rule_test_dialog.py:389` does not. A rule carrying `"type": "set_status"` (hand-edited JSON, or an older config) executes correctly but the dialog's explanation chain at `:398-417` matches nothing, so the dialog stays silent about what the action does. Normalize to upper — the dialog's job is to report what the engine will run, not how the JSON was spelled.

**3. The Test dialog renders missing values as the literal text `nan`.** `gui/rule_test_dialog.py:363`, `:452`, `:462`, `:471` call bare `str(value)`. The app's own main table renders a missing value as `""` (`gui/pandas_model.py:192-194`), so the Test dialog contradicts the table the user compares it against.

**The trap:** `pandas_model.py` checks `isinstance(value, list)` at `:182` *before* `pd.isna` at `:192`, and that ordering is load-bearing. `Lot_Details` is a genuinely list-valued column (`shopify_tool/analysis.py:1111-1116`), and `_get_display_columns` (`gui/rule_test_dialog.py:506-508`) fills its spare slots from `df.columns` verbatim, so `Lot_Details` can reach these tables. `pd.isna([...])` returns an **array**, and `if <array>:` raises `ValueError: The truth value of an array with more than one element is ambiguous`. A naive `pd.isna` guard would therefore reintroduce exactly the crash class PR #276 fixed.

The same trap already sits, latent, at `:459`: `pd.isna(value_before) and pd.isna(value_after)` only escapes it because `value_before != value_after` short-circuits first whenever the lists are equal.

---

### Task 1: `is empty` takes no value

**Files:**
- Modify: `gui/settings/rules.py:778` (operator strings), `gui/settings/rules.py:893-906` (early-return fall-through), `gui/settings/rules.py:750` (docstring)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on. Task 1 is independent of Tasks 2 and 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules_page.py`:

```python
class TestValuelessOperators:
    """'is empty'/'is not empty' ignore rule_val (shopify_tool/rules.py:175),
    so the editor must not offer a value box for them."""

    def _rule(self, operator):
        return {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": operator, "value": ""}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    @pytest.mark.parametrize("operator", ["is empty", "is not empty"])
    def test_no_value_widget_on_load(self, qtbot, analysis_df, operator):
        page = RulesPage([self._rule(operator)], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert cond_refs["value_widget"] is None

    @pytest.mark.parametrize("operator", ["is empty", "is not empty"])
    def test_no_value_widget_after_switching_operator(self, qtbot, analysis_df, operator):
        page = RulesPage([self._rule("equals")], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert cond_refs["value_widget"] is not None  # baseline: 'equals' has one
        cond_refs["op"].setCurrentText(operator)
        assert cond_refs["value_widget"] is None

    def test_collect_still_emits_an_empty_value(self, qtbot, analysis_df):
        """The engine reads condition['value'] unconditionally; a valueless
        operator must still round-trip a key, not drop it."""
        page = RulesPage([self._rule("is empty")], analysis_df)
        qtbot.addWidget(page)

        condition = page.collect()["rules"][0]["steps"][0]["conditions"][0]
        assert condition["operator"] == "is empty"
        assert condition["value"] == ""

    def test_unresolvable_field_is_still_flagged_without_a_value_widget(
        self, qtbot, analysis_df
    ):
        """PR #278's flag must survive the now-reachable no-widget path."""
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [
                    {"field": "item_count", "operator": "is empty", "value": ""}
                ],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert cond_refs["value_widget"] is None
        assert "border" in cond_refs["field"].styleSheet()
        # The tail of _perform_validation must run even with no value widget.
        page._perform_validation(cond_refs)
        assert page._check_field_resolvable(cond_refs) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py::TestValuelessOperators -v`

Expected: FAIL. `test_no_value_widget_on_load` and `test_no_value_widget_after_switching_operator` fail with `assert <PySide6.QtWidgets.QLineEdit(...)> is None`, because `gui/settings/rules.py:778` never matches and falls through to the `QLineEdit` branch at `:819`.

- [ ] **Step 3: Fix the operator strings**

In `gui/settings/rules.py`, change line 778 from:

```python
        # Operators that don't need a value input
        if op in ["is_empty", "is_not_empty"]:
```

to:

```python
        # Operators that don't need a value input. These must match
        # CONDITION_OPERATORS (gui/settings/fields.py) verbatim -- they carry
        # spaces, not underscores, and the underscored spelling silently
        # rendered a value box the engine throws away.
        if op in ["is empty", "is not empty"]:
```

Also fix the stale docstring at `gui/settings/rules.py:750`, changing `For operators like 'is_empty', it hides the value widget.` to `For operators like 'is empty', it hides the value widget.`

- [ ] **Step 4: Make `_perform_validation` fall through to the resolvability check**

In `gui/settings/rules.py`, replace the value-extraction block at `:892-906`:

```python
        op = condition_refs["op"].currentText()
        value_widget = condition_refs.get("value_widget")

        if not value_widget:
            return

        # Get value based on widget type
        if isinstance(value_widget, QComboBox):
            value = value_widget.currentText()
        elif isinstance(value_widget, QDateEdit):
            value = value_widget.date().toString("yyyy-MM-dd")
        elif isinstance(value_widget, QLineEdit):
            value = value_widget.text()
        else:
            return
```

with:

```python
        op = condition_refs["op"].currentText()
        value_widget = condition_refs.get("value_widget")

        # A valueless operator ('is empty') has no widget to read, and an
        # unrecognised widget type has no text. Neither can be value-validated,
        # but both still need the field-resolvability mark at the tail -- an
        # early return here drops PR #278's "never matches" flag.
        if isinstance(value_widget, QComboBox):
            value = value_widget.currentText()
        elif isinstance(value_widget, QDateEdit):
            value = value_widget.date().toString("yyyy-MM-dd")
        elif isinstance(value_widget, QLineEdit):
            value = value_widget.text()
        else:
            self._show_validation_feedback(condition_refs, "clear", "")
            self._check_field_resolvable(condition_refs)
            return
```

The three `isinstance` arms are mutually exclusive, so their order does not matter — keep the existing order to minimise the diff. `value_widget` being `None` now falls to the `else` arm, which is the point: it clears any stale message, re-applies the resolvability flag, and only then returns.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v`

Expected: PASS, including the pre-existing `TestUnresolvableFieldIsFlagged` class (its `_perform_validation` call at `:252`/`:267` must still behave).

- [ ] **Step 6: Commit**

```bash
git add gui/settings/rules.py tests/test_rules_page.py
git commit -m "Rule editor: 'is empty' no longer offers a value box the engine discards"
```

---

### Task 2: The Test dialog reports the action type the engine will run

**Files:**
- Modify: `gui/rule_test_dialog.py:389`
- Test: `tests/test_rule_test_dialog.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on. Independent of Tasks 1 and 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rule_test_dialog.py`:

```python
class TestActionTypeCaseIsNormalized:
    """RuleEngine uppercases action types (shopify_tool/rules.py:917, :1051),
    so a lowercase type executes. The dialog must explain it, not go silent."""

    def test_lowercase_type_still_gets_its_explanation(
        self, qtbot, analysis_df, no_modals
    ):
        rule = _rule({"type": "set_status", "value": "Ready"})
        dialog = _open(qtbot, rule, analysis_df)
        assert "Sets Order_Fulfillment_Status" in dialog.actions_label.text()

    def test_mixed_case_copy_field_still_gets_its_explanation(
        self, qtbot, analysis_df, no_modals
    ):
        rule = _rule({"type": "Copy_Field", "source": "SKU", "target": "Status_Note"})
        dialog = _open(qtbot, rule, analysis_df)
        text = dialog.actions_label.text()
        assert "Copies 'SKU' to 'Status_Note'" in text

    def test_uppercase_type_is_unchanged(self, qtbot, analysis_df, no_modals):
        """Baseline: passes today."""
        rule = _rule({"type": "SET_STATUS", "value": "Ready"})
        dialog = _open(qtbot, rule, analysis_df)
        assert "Sets Order_Fulfillment_Status" in dialog.actions_label.text()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py::TestActionTypeCaseIsNormalized -v`

Expected: the first two FAIL (`assert 'Sets Order_Fulfillment_Status' in '...<b>set_status</b>...'`), the third PASSES.

- [ ] **Step 3: Normalize the type**

In `gui/rule_test_dialog.py`, change line 389 from:

```python
            action_type = action.get("type", "")
```

to:

```python
            # Normalized, because the engine dispatches on the uppercased type
            # (shopify_tool/rules.py:917). Reporting the raw spelling would let
            # a lowercase type run with no explanation shown for it.
            action_type = action.get("type", "").upper()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v`

Expected: PASS, all classes.

- [ ] **Step 5: Commit**

```bash
git add gui/rule_test_dialog.py tests/test_rule_test_dialog.py
git commit -m "Rule Test dialog: match the engine's action-type casing"
```

---

### Task 3: The Test dialog renders a missing value as blank, not "nan"

**Files:**
- Modify: `gui/rule_test_dialog.py` (add module-level `_cell_text`; call it at `:363`, `:452`, `:459-462`, `:471`)
- Test: `tests/test_rule_test_dialog.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `_cell_text(value) -> str`, a module-level private function in `gui/rule_test_dialog.py`. No other task or module consumes it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rule_test_dialog.py`:

```python
class TestMissingValuesRenderBlank:
    """gui/pandas_model.py:192 renders a missing cell as "", so the dialog the
    user compares against that table must not print the literal text 'nan'."""

    def _texts(self, table):
        return {
            table.item(r, c).text()
            for r in range(table.rowCount())
            for c in range(table.columnCount())
            if table.item(r, c) is not None
        }

    def test_nan_is_not_shown_as_the_word_nan(self, qtbot, analysis_df, no_modals):
        analysis_df.loc[0, "Product_Name"] = float("nan")
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        assert "nan" not in self._texts(dialog.preview_table)
        assert "nan" not in self._texts(dialog.after_table)

    def test_none_is_not_shown_as_the_word_none(self, qtbot, analysis_df, no_modals):
        analysis_df["Lot_Details"] = None
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        assert "None" not in self._texts(dialog.preview_table)

    def test_a_list_valued_column_does_not_crash_the_dialog(
        self, qtbot, analysis_df, no_modals
    ):
        """Lot_Details holds real lists (shopify_tool/analysis.py:1111), and
        _get_display_columns pulls spare columns straight from df.columns.
        pd.isna() on a list returns an array, so an unguarded truth test raises
        'truth value of an array is ambiguous'."""
        analysis_df["Lot_Details"] = [
            [{"lot": "L1", "quantity": 1}, {"lot": "L2", "quantity": 2}],
            [],
            None,
        ]
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        texts = self._texts(dialog.preview_table)
        assert "2 lots" in texts
        assert "nan" not in texts

    def test_a_changed_cell_is_still_highlighted(self, qtbot, analysis_df, no_modals):
        """Baseline for the rewritten diff test: a real change must still tint."""
        rule = _rule({"type": "SET_STATUS", "value": "Shipped"})
        dialog = _open(qtbot, rule, analysis_df)

        col = [
            dialog.after_table.horizontalHeaderItem(c).text()
            for c in range(dialog.after_table.columnCount())
        ].index("Order_Fulfillment_Status")
        item = dialog.after_table.item(0, col)
        assert item.text() == "Shipped"
        assert item.background().color().name().lower() == "#ffeb3b"

    def test_an_unchanged_missing_cell_is_not_highlighted(
        self, qtbot, analysis_df, no_modals
    ):
        """NaN != NaN, so a naive object diff tints every missing cell."""
        analysis_df.loc[0, "Product_Name"] = float("nan")
        rule = _rule({"type": "SET_STATUS", "value": "Shipped"})
        dialog = _open(qtbot, rule, analysis_df)

        col = [
            dialog.after_table.horizontalHeaderItem(c).text()
            for c in range(dialog.after_table.columnCount())
        ].index("Product_Name")
        item = dialog.after_table.item(0, col)
        assert item.background().color().name().lower() != "#ffeb3b"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py::TestMissingValuesRenderBlank -v`

Expected: FAIL. `test_nan_is_not_shown_as_the_word_nan` fails on `'nan' in {...}`; `test_a_list_valued_column_does_not_crash_the_dialog` fails on the literal `str([...])` rendering rather than `"2 lots"`.

- [ ] **Step 3: Add the `_cell_text` helper**

In `gui/rule_test_dialog.py`, add at module level immediately after the imports (before the first class definition):

```python
def _cell_text(value) -> str:
    """Render one DataFrame cell the way the main analysis table renders it.

    Mirrors gui/pandas_model.py:182-194, including its ordering: the list
    check comes first because Lot_Details holds real lists, and pd.isna()
    on a list returns an array, which makes a plain `if` raise
    "truth value of an array is ambiguous".
    """
    if isinstance(value, list):
        if not value:
            return ""
        return f"{len(value)} lot{'s' if len(value) != 1 else ''}"
    if pd.isna(value):
        return ""
    return str(value)
```

`pd` is already imported in this module.

- [ ] **Step 4: Use it in the preview table**

In `gui/rule_test_dialog.py`, change line 363 from:

```python
                item = QTableWidgetItem(str(value))
```

to:

```python
                item = QTableWidgetItem(_cell_text(value))
```

- [ ] **Step 5: Use it in the after-actions diff**

In `gui/rule_test_dialog.py`, replace the diff block at `:449-464`:

```python
                value_before = row_before[col_name]
                value_after = row_after[col_name]

                item = QTableWidgetItem(str(value_after))

                # Highlight changed cells
                # ponytail: literal diff-highlight yellow/green, not worth two
                # new ThemeTokens fields for this one call site. The tints are
                # light in both themes, so pin a dark foreground too -- dark
                # theme's text_primary is near-white and vanishes on them.
                if value_before != value_after and not (pd.isna(value_before) and pd.isna(value_after)):
                    item.setBackground(QColor("#FFEB3B"))  # Yellow
                    item.setForeground(QColor("#000000"))
                    item.setToolTip(f"Changed from: {value_before}")

                self.after_table.setItem(row_idx, col_idx, item)
```

with:

```python
                # Diff what the cells display, not the raw objects. That drops
                # the NaN != NaN special case (both render "") and is safe on
                # list columns, where pd.isna() returns an array.
                text_before = _cell_text(row_before[col_name])
                text_after = _cell_text(row_after[col_name])

                item = QTableWidgetItem(text_after)

                # Highlight changed cells
                # ponytail: literal diff-highlight yellow/green, not worth two
                # new ThemeTokens fields for this one call site. The tints are
                # light in both themes, so pin a dark foreground too -- dark
                # theme's text_primary is near-white and vanishes on them.
                if text_before != text_after:
                    item.setBackground(QColor("#FFEB3B"))  # Yellow
                    item.setForeground(QColor("#000000"))
                    item.setToolTip(f"Changed from: {text_before}")

                self.after_table.setItem(row_idx, col_idx, item)
```

- [ ] **Step 6: Use it in the added-rows loop**

In `gui/rule_test_dialog.py`, change line 471 from:

```python
                item = QTableWidgetItem(str(row_added[col_name]))
```

to:

```python
                item = QTableWidgetItem(_cell_text(row_added[col_name]))
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v`

Expected: PASS, all classes — including the pre-existing `TestNoCrashOnShapeChange` and `TestZeroResultsAreChanges`. `TestZeroResultsAreChanges` matters most here: it asserts a CALCULATE result of `0` counts as changed, and text diffing must not regress it (`""` vs `"0"` still differ).

- [ ] **Step 8: Commit**

```bash
git add gui/rule_test_dialog.py tests/test_rule_test_dialog.py
git commit -m "Rule Test dialog: render missing values blank, and survive list columns"
```

---

### Task 4: Gate and graph

**Files:**
- Modify: none (verification only, plus the graphify output the repo tracks)

**Interfaces:**
- Consumes: Tasks 1-3 complete and committed.
- Produces: nothing.

- [ ] **Step 1: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Expected: PASS. The baseline before this branch was 656 passed (recorded in the runner's `state.md` for PR #283); this plan adds 14 tests, so expect 670 passed with no failures. If the baseline has moved, what matters is zero failures and zero errors — do not claim a pass without reading the summary line.

- [ ] **Step 2: Run the linter**

Run: `.venv/bin/ruff check . --exclude shared`

Expected: `All checks passed!`

- [ ] **Step 3: Update the knowledge graph**

Run: `graphify update .`

Expected: completes without error. CLAUDE.md requires this immediately after modifying code, not "eventually".

- [ ] **Step 4: Commit any graph changes**

```bash
git add -A
git commit -m "graphify: refresh after rule preview fidelity fixes"
```

Skip this commit if `git status` shows nothing to commit.

---

## Out of scope

Named explicitly so Stage C does not treat them as omissions:

- The literal `#ffebee` / `#fff3e0` / `#1A1A1A` validation tints at `gui/settings/rules.py:963-967`. They carry a deliberate `ponytail:` comment, and doing it properly means new `ThemeTokens` fields — which live in `packing-tool`'s `shared/theme.py` and arrive here only via `scripts/sync_shared.py`. That is a cross-repo change, not this PR.
- The `ColumnConfigPanel` list-stretch bug (Columns / Additional CSV Columns lists collapse to ~2 visible rows).
- Long validation messages clipping at minimum window width. `setHeightForWidth(True)` was already probed and does **not** fix it — do not retry it here.
