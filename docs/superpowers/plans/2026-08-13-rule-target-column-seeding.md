# Rule Target Column Seeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> (The runner's Stage B declines subagent-driven-development and stays in-session.)

**Goal:** A column a rule *creates* must hold "no value" (NaN) on every row the rule
did not write — not `""` and not `0.0` — which fixes a hard crash on pandas 3 and
removes the change-detection heuristic it forced on the Rule Test dialog.

**Architecture:** Three small edits at one root cause. `shopify_tool/rules.py` seeds a
brand-new COPY_FIELD/CALCULATE target column with a *typed* value (`""` → `str` dtype,
`0.0` → `float64`) and then writes real values into a subset of rows. On pandas 3 the
`""` seed makes the column `str` dtype, so writing a numeric source into it raises
`TypeError`. Seeding NaN instead is both crash-free and semantically right: an untouched
row genuinely has no value. `gui/rule_test_dialog.py` then no longer needs its
`!= 0 / != 0.0` guards, which existed only to work around the `0.0` seed and which
under-reported any legitimate CALCULATE result of zero.

**Tech Stack:** Python, pandas 3.0.5 (pinned), PySide6, pytest.

**Spec:** No separate design doc — this is a bounded fix. The design is the "Design"
section below. Source ticket: Todoist `6hGfvcx2W8JcQjR3`, filed from the Stage C review
of PR #276.

## Global Constraints

- Python entry points: use `.venv/bin/python`. Bare `python`/`python3` are not usable
  on this machine.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and
  `.venv/bin/ruff check . --exclude shared`.
- Never hand-edit anything under `shared/`.
- No hardcoded colors; use `theme_manager` tokens. (No UI styling is touched here, but
  the rule stands.)
- Do not bump the version string — this is a bugfix on a pre-release line and version
  bumps are handled separately.
- Baseline test count on this branch is **575 passing** (verified on
  `worktree-copy-field-dtype` before any edits). This plan adds 5 tests → **580**:
  3 in Task 1, 1 in Task 2, 1 in Task 3. If Task 2 and Task 3 are dropped together
  (see Task 2's note), the target is 578.

---

## Design

### The crash, reproduced

`shopify_tool/rules.py:1103-1106`:

```python
if target not in df.columns:
    df[target] = ""                                   # -> str dtype on pandas 3
df.loc[matches, target] = df.loc[matches, source]     # numeric source -> TypeError
```

Verified on the pinned pandas 3.0.5:

```
TypeError: Invalid value for dtype 'str'. Value should be a string or missing
value (or array of those).
```

Any COPY_FIELD whose **source is numeric** and whose **target is a new column** raises.
`gui/rule_test_dialog.py` catches it into its generic "Failed to test rule" box, which
is why this reads to a user as the same symptom as the (separate, already-fixed) Rule
Test crash in PR #276.

### The fix

Build the new column *from the source*, masked, instead of seeding-then-assigning:

```python
if target not in df.columns:
    df[target] = df[source].where(matches)
else:
    df.loc[matches, target] = df.loc[matches, source]
```

`Series.where(mask)` keeps the source value where the mask is True and puts NaN
elsewhere, carrying the source column's own dtype (int64 widens to float64 to hold NaN;
a `str` column stays `str` with NaN in the gaps). No dtype has to be guessed. `matches`
is a `pd.Series` built on `df.index` (`rules.py:792-808`), so alignment is exact.

CALCULATE has the same bug shape one branch away — `df[target] = 0.0` at
`rules.py:1189-1190` — which does not crash but leaves a literal `0.0` on every row the
rule never touched. Seeding `float("nan")` instead is a one-word change and needs no
numpy import (numpy is only imported locally inside the `divide` branch today).

### Why NaN is safe downstream

Verified read paths for a rule-created column:

| Consumer | Behaviour on NaN |
|---|---|
| `gui/pandas_model.py:192-194` | `if pd.isna(value): return ""` — renders blank, identical to today |
| Excel export (`core.py`, `to_excel`) | pandas writes NaN as an empty cell (`na_rep=''` default) |
| `core.py:930` | `final_df.fillna("").astype(str)` — column-width math only, unaffected |
| `gui/rule_test_dialog.py:_detect_changed_rows` | improves; see Task 3 |

So the user-visible result for COPY_FIELD is unchanged (blank stays blank) and the
crash goes away.

### The one deliberate behaviour change

CALCULATE's unmatched rows change from displaying `0` to displaying blank. This is a
correction — `0` asserts "the calculation produced zero" for rows the rule never
evaluated — but it *is* visible in exports. **Task 2 is written to be revertible on its
own** so it can be dropped without touching Tasks 1, 3 or 4 if the user wants the `0.0`
seed kept.

### File structure

| File | Responsibility here |
|---|---|
| `shopify_tool/rules.py` | Seeds rule-created target columns (Tasks 1, 2, 4) |
| `gui/rule_test_dialog.py` | Diffs before/after frames; drops its `0.0`-seed workaround (Task 3) |
| `tests/test_rules.py` | Engine regression tests (Tasks 1, 2) |
| `tests/test_rule_test_dialog.py` | Dialog diff regression test (Task 3) |

---

### Task 1: COPY_FIELD with a numeric source must not crash

**Files:**
- Modify: `shopify_tool/rules.py:1103-1106`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the invariant *"a COPY_FIELD target column created by the engine is NaN on
  unmatched rows and holds the source value, at the source's dtype, on matched rows."*
  Task 3 relies on this.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules.py`, at the end of the file, a new class. `_df` and `_rule`
are the module-level helpers already defined at `tests/test_rules.py:12-22`.

```python
class TestRuleCreatedColumnSeeding:
    """A column the engine creates is NaN where the rule did not write.

    Regression: seeding a new COPY_FIELD target with "" made it str dtype on
    pandas 3, so copying a numeric source into it raised TypeError.
    """

    def test_copy_field_numeric_source_into_new_column(self):
        df = _df({"Quantity": [1, 2, 3], "SKU": ["a", "b", "c"]})
        rules = [_rule([{"field": "Quantity", "operator": "greater_than", "value": 1}],
                       [{"type": "COPY_FIELD", "source": "Quantity", "target": "Qty_Copy"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert "Qty_Copy" in out.columns
        assert out.loc[0, "Qty_Copy"] != out.loc[0, "Qty_Copy"]  # NaN: unmatched
        assert out.loc[1, "Qty_Copy"] == 2
        assert out.loc[2, "Qty_Copy"] == 3

    def test_copy_field_string_source_into_new_column(self):
        df = _df({"Quantity": [1, 2, 3], "SKU": ["a", "b", "c"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "COPY_FIELD", "source": "SKU", "target": "SKU_Copy"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert out.loc[1, "SKU_Copy"] == "b"
        assert pd.isna(out.loc[0, "SKU_Copy"])
        assert pd.isna(out.loc[2, "SKU_Copy"])

    def test_copy_field_into_existing_column_leaves_other_rows_alone(self):
        df = _df({"Quantity": [1, 2], "SKU": ["a", "b"], "Note": ["keep", "keep"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "COPY_FIELD", "source": "SKU", "target": "Note"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert out.loc[0, "Note"] == "keep"
        assert out.loc[1, "Note"] == "b"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py::TestRuleCreatedColumnSeeding -v`

Expected: `test_copy_field_numeric_source_into_new_column` FAILS. The engine catches
per-action exceptions in places, so the failure may surface either as a raised
`TypeError: Invalid value for dtype 'str'` or as `"Qty_Copy"` holding `""` instead of
numbers — either way the assertions do not hold. The other two tests should already
pass; they are there to pin behaviour the fix must not break.

- [ ] **Step 3: Write the implementation**

In `shopify_tool/rules.py`, replace lines 1103-1106:

```python
                if target not in df.columns:
                    df[target] = ""

                df.loc[matches, target] = df.loc[matches, source]
```

with:

```python
                if target not in df.columns:
                    # Build the column from the source so it takes the source's
                    # dtype. Seeding "" first made it str dtype on pandas 3, and
                    # writing a numeric source into that raises TypeError.
                    # Unmatched rows are NaN -- the rule never wrote them.
                    df[target] = df[source].where(matches)
                else:
                    df.loc[matches, target] = df.loc[matches, source]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v`

Expected: all PASS, including the three new ones.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/rules.py tests/test_rules.py
git commit -m "fix(rules): COPY_FIELD no longer crashes on a numeric source

Seeding a new target column with \"\" made it str dtype on pandas 3, so
writing a numeric source into it raised TypeError. Build the column from
the source instead, masked, so it takes the source's dtype and unmatched
rows are NaN."
```

---

### Task 2: CALCULATE seeds NaN, not 0.0

**Independently revertible.** If the behaviour change (unmatched rows read blank instead
of `0`) is unwanted, drop this task alone; Tasks 1 and 4 do not depend on it. Task 3
does — see the note in Task 3, Step 3.

**Files:**
- Modify: `shopify_tool/rules.py:1188-1190`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: the `TestRuleCreatedColumnSeeding` class created in Task 1.
- Produces: the invariant *"a CALCULATE target column created by the engine is NaN on
  unmatched rows."* Task 3 relies on this.

- [ ] **Step 1: Write the failing test**

Add this method to the `TestRuleCreatedColumnSeeding` class created in Task 1:

```python
    def test_calculate_leaves_unmatched_rows_empty(self):
        df = _df({"Quantity": [1, 2], "Price": [10, 20]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "CALCULATE", "operation": "multiply",
                         "field1": "Quantity", "field2": "Price", "target": "Total"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert pd.isna(out.loc[0, "Total"]), "unmatched row must be blank, not 0.0"
        assert out.loc[1, "Total"] == 40
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest "tests/test_rules.py::TestRuleCreatedColumnSeeding::test_calculate_leaves_unmatched_rows_empty" -v`

Expected: FAIL — `assert pd.isna(0.0)` is False, because the column is seeded `0.0`.

- [ ] **Step 3: Write the implementation**

In `shopify_tool/rules.py`, replace lines 1188-1190:

```python
                # Створити target column якщо не існує
                if target not in df.columns:
                    df[target] = 0.0
```

with:

```python
                # Створити target column якщо не існує.
                # NaN, not 0.0 -- a row the rule never matched has no result,
                # and a literal 0.0 there is indistinguishable from a real one.
                # float("nan") gives a float64 column without importing numpy
                # (numpy is imported locally in the divide branch below).
                if target not in df.columns:
                    df[target] = float("nan")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/rules.py tests/test_rules.py
git commit -m "fix(rules): CALCULATE seeds a new target column with NaN, not 0.0

A row the rule never matched has no result. A literal 0.0 there is
indistinguishable from a real calculated zero, which is what forced the
Rule Test dialog's != 0 workaround."
```

---

### Task 3: Drop the Rule Test dialog's 0.0-seed workaround

**Files:**
- Modify: `gui/rule_test_dialog.py:256-294` (docstring and the `has_value` line)
- Modify: `gui/rule_test_dialog.py:248-251` (the `_align_frames` comment, one line)
- Test: `tests/test_rule_test_dialog.py`

**Interfaces:**
- Consumes: the two invariants produced by Tasks 1 and 2 — a rule-created column is NaN
  on rows the rule did not write.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

`tests/test_rule_test_dialog.py` already has everything this needs: the `analysis_df`
fixture (`:14-31`), the `_rule(*actions)` helper (`:34-48`) which builds a rule matching
the two `"Ready"` rows (indices 0 and 2), the `_open(qtbot, rule, df)` helper (`:51-54`),
and the `no_modals` fixture used by every test there. Append this new class to the end of
that file:

```python
class TestZeroResultsAreChanges:
    def test_calculate_result_of_zero_counts_as_changed(self, qtbot, analysis_df, no_modals):
        """A legitimate CALCULATE result of 0 is a change, not a seed value.

        The old detector filtered out `!= 0` to hide CALCULATE's 0.0 seed, and
        hid every real zero result with it. The seed is NaN now, so a real 0 is
        distinguishable and must be counted.
        """
        df = analysis_df.copy()
        df["Total_Price"] = 0.0          # every product is now legitimately 0

        dialog = _open(qtbot, _rule({
            "type": "CALCULATE", "operation": "multiply",
            "field1": "Quantity", "field2": "Total_Price",
            "target": "Line_Total",
        }), df)

        assert no_modals == []
        # Rows 0 and 2 match and get a real result of 0.0; row 1 stays NaN.
        assert dialog.changed_count == 2
        assert pd.isna(dialog.df_after.loc[1, "Line_Total"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py -v`

Expected: the new test FAILS with `assert 0 == 2` — the `!= 0` guard filters both rows out.

- [ ] **Step 3: Write the implementation**

In `gui/rule_test_dialog.py`, replace line 291:

```python
                has_value = after_vals.notna() & (after_vals != 0) & (after_vals != "") & (after_vals != 0.0)
```

with:

```python
                has_value = after_vals.notna() & (after_vals != "")
```

Keep the `!= ""` term: `_prepare_df_for_actions` still seeds `Status_Note` with `""` for
every row, and that seed is not a change. Drop only the `!= 0` / `!= 0.0` terms, which
existed for CALCULATE's old `0.0` seed. (**If Task 2 was dropped, do not make this
change** — the `0.0` seed would still be present and the guards are still load-bearing.
Skip Task 3 entirely in that case.)

Then replace the second and third paragraphs of the `_detect_changed_rows` docstring
(`gui/rule_test_dialog.py:262-280`, from "A column the rule creates" through
"the dialog was wrong.") with:

```
        A column the rule creates (CALCULATE/COPY_FIELD's target) is NaN on
        every row the rule did not write, so `notna()` identifies exactly the
        rows it did. Pre-existing columns get a plain before/after string diff.

        ponytail: still not a proof at one end -- a brand-new Internal_Tags
        over-reports, because _prepare_df_for_actions seeds it with the truthy
        string "[]" for every row. That stays latent in practice: analysis.py
        initialises Internal_Tags on every real analysis, so it always takes
        the exact pre-existing-column path. Fixing it properly needs rules.py
        to report which rows it wrote, which is out of scope here.
```

Finally, update the stale comment at `gui/rule_test_dialog.py:250`:

```python
        # _detect_changed_rows treats new columns specially; see there.
```

to:

```python
        # _detect_changed_rows reads a new column's NaNs as "untouched"; see there.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py tests/test_rules.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/rule_test_dialog.py tests/test_rule_test_dialog.py
git commit -m "fix(rule-test): count a real CALCULATE result of zero as a change

The != 0 guards existed only to hide CALCULATE's old 0.0 seed, and they
hid every legitimate zero result with it. The seed is NaN now, so notna()
is exact for rule-created columns."
```

---

### Task 4: Delete the dead column-collection intent

`_prepare_df_for_actions` collects COPY_FIELD/CALCULATE targets into `needed_columns`
and then never creates them — only `Status_Note` and `Internal_Tags` are acted on. After
Tasks 1 and 2 the action handlers create their own target columns with the correct
dtype, so this branch is dead and misleading: it reads as though the columns are
pre-created here.

**Files:**
- Modify: `shopify_tool/rules.py:898-930`

**Interfaces:**
- Consumes: nothing. Pure deletion.
- Produces: nothing.

- [ ] **Step 1: Delete the dead branch**

In `shopify_tool/rules.py`, delete these four lines (`rules.py:920-923`):

```python
                    elif action_type == "COPY_FIELD" or action_type == "CALCULATE":
                        target = action.get("target")
                        if target:
                            needed_columns.add(target)
```

- [ ] **Step 2: Update the docstring to match**

In the same function, replace this sentence in the docstring
(`rules.py:901-905`):

```
        Scans all rules to find out which columns will be modified or created
        by the actions (e.g., 'Status_Note', 'Internal_Tags'). If these columns
        do not already exist in the DataFrame, they are created and initialized
        with a default value. This prevents errors when an action tries to
        modify a non-existent column.
```

with:

```
        Scans all rules for the tag columns their actions append to --
        'Status_Note' and 'Internal_Tags' -- and creates them if missing, so an
        action can read-modify-write them without a existence check.

        COPY_FIELD and CALCULATE targets are deliberately NOT created here: each
        handler builds its own target column so it can give it the right dtype
        and leave unmatched rows NaN, neither of which is knowable from here.
```

- [ ] **Step 3: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Expected: **580 passed** (575 baseline + 5 new). If the count differs, stop and
investigate before committing — a dropped test is a regression, not a rounding error.

- [ ] **Step 4: Run the linter**

Run: `.venv/bin/ruff check . --exclude shared`

Expected: clean. If it flags `needed_columns` as now-unused, it is not — `Status_Note`
and `Internal_Tags` are still added to it and read at `rules.py:927-930`.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/rules.py
git commit -m "refactor(rules): drop dead COPY_FIELD/CALCULATE column collection

_prepare_df_for_actions collected these targets and never created them.
Each action handler now creates its own target with the right dtype, so
the collection was dead code that read as though it did the work."
```

---

## Verification before finishing Stage B

- [ ] `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` → 580 passed
- [ ] `.venv/bin/ruff check . --exclude shared` → clean
- [ ] `graphify update .` run in this worktree
- [ ] Manual sanity (optional, needs a display): open a rule with
      `COPY_FIELD: Quantity -> Qty_Copy`, hit **Test Rule**, confirm the preview table
      renders and unmatched rows show blank in the `Qty_Copy` column.

## Out of scope

- The Rule Test dialog's layout/alignment work — already landed in PR #276.
- Any change to how `Internal_Tags` is seeded (`"[]"`). Its over-report in
  `_detect_changed_rows` is documented and latent; fixing it needs the engine to report
  written rows, which is a larger change.
- The validation-feedback layout fix (Todoist `6hGfgP9C7355Gm83`) — separate task.
