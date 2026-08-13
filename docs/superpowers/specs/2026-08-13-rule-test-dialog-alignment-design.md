# Rule Test dialog — before/after frame alignment

**Date:** 2026-08-13
**Todoist:** `6hGfgP6cF5gJMfcV` (p2, "Rule Test button crashes")
**Status:** design, ready to implement

---

## 1. The report

The user tested the rule editor on the `worktree-rule-engine-ui` branch and
filed: *the Rule Test button crashes*. It is not a disabled button and not a
visible traceback — `RuleTestDialog._run_test` wraps everything in
`except Exception` and shows a "Failed to test rule" `QMessageBox`, so the
symptom the user sees is a modal error box where a preview should be.

## 2. What was actually reproduced

The previous run's diagnosis was **"`rule_test_dialog.py:383` KeyErrors on
`Status_Note`, created by ADD_TAG"**, with a caveat that the repro used a
synthetic DataFrame. That caveat turned out to matter: **the ADD_TAG theory is
wrong on real data.**

`shopify_tool/analysis.py:1097` and `:1103` initialise `Status_Note` and
`Internal_Tags` on every analysis DataFrame. So `_prepare_df_for_actions`
(`rules.py:927-930`) finds them already present and creates nothing, and
ADD_TAG never introduces a new column on a real analysis df.

Driving the real `RuleTestDialog` against an analysis-shaped df (all of
`Order_Number`, `SKU`, `Quantity`, `Total_Price`, `Product_Name`,
`Warehouse_Name`, `Order_Fulfillment_Status`, `Status_Note`, `Internal_Tags`
present), with the swallow-all handler removed:

| Rule under test | Result |
|---|---|
| `ADD_TAG` only | OK — matched 2 |
| `CALCULATE` → new `target` | **`KeyError: 'Line_Total'`** |
| `COPY_FIELD` → new `target` | **`KeyError: 'SKU_Copy'`** |
| `ADD_PRODUCT` only | No crash, but reports **"0 rows affected"** for a rule that added 2 rows |
| `ADD_PRODUCT` + `ADD_TAG` | **`IndexingError: Unalignable boolean Series provided as indexer`** |

Repro driver: `/home/cognitiveghost/.claude/jobs/d7a71174/tmp/repro2.py`
(scratch, not committed — Task 1 replaces it with a committed test).

## 3. Root cause

`RuleTestDialog` compares `self.df_before` against `self.df_after` and assumes
the two frames share **columns**, **index**, and **row count**. `RuleEngine`
guarantees none of the three.

`df_before` is snapshotted at `rule_test_dialog.py:191`, *before*
`engine.apply()` runs. `apply()` then changes the frame's shape in two ways:

**(a) New columns appear mid-apply.** `_prepare_df_for_actions` only ever
materialises `Status_Note` and `Internal_Tags` (`rules.py:927-930`) — it
collects `COPY_FIELD`/`CALCULATE` targets into `needed_columns`
(`rules.py:920-923`) and then never creates them. Those columns are instead
created by the action itself: `CALCULATE` at `rules.py:1189-1190`
(`df[target] = 0.0`), and `COPY_FIELD` likewise. Either way the column exists
in `df_after` and not in `df_before`.

`_detect_changed_rows` handles this correctly — it has a dedicated `new_cols`
branch (`rule_test_dialog.py:220`, `:231-235`) that marks rows changed when a
new column holds a value. But `_populate_after_actions_table` then derives
`display_cols` from `matched_after` (`:373`) — which *includes* the new column
— and indexes `row_before[col_name]` (`:383`) with it. `row_before` came from
`df_before`, which has no such column. **KeyError.**

**(b) New rows appear at the end.** `ADD_PRODUCT` accumulates rows and
`apply()` concatenates them at `rules.py:891-893` with `ignore_index=True`, so
`df_after` is longer than `df_before` and carries a fresh `RangeIndex`.
`self.matches` is a boolean Series on `df_before.index`. At
`rule_test_dialog.py:370`, `self.df_after[self.matches]` is a boolean indexer
whose length no longer matches the frame. **IndexingError.**

The same mismatch is why `ADD_PRODUCT`-only reports 0 rows:
`_detect_changed_rows` compares `df_after.loc[df_before.index]` positionally
against `df_before` and finds the original rows unmodified, while the appended
rows fall outside `df_before.index` entirely and are never considered. The
dialog tells the user a rule that adds products does nothing. This is worse
than the crash — a crash is visible; this is silently wrong.

`_populate_preview_table` is safe today only by accident: it reads from
`df_before` and picks `display_cols` from `df_before` too (`:288-291`).

**One root cause, four symptoms.** Guarding line 383 alone — the previously
proposed fix — leaves (b) crashing and leaves ADD_PRODUCT silently wrong.

## 4. Design

Normalise the two frames **once**, immediately after `apply()`, so every
consumer downstream is comparing like with like. No per-site guards.

### 4.1 Splitting original rows from added rows

`apply()` never drops, sorts, reindexes, or reorders rows — `git grep` over
`shopify_tool/rules.py` finds no `.drop(`, `sort_values`, `reset_index`, or
`.reindex(` anywhere in the file. The concat at `rules.py:893` is the only
shape change, and it appends: `pd.concat([df, new_df])`.

Therefore **the first `len(df_before)` positional rows of `df_after` are the
original rows, in their original order.** Slice positionally and reattach
`df_before`'s labels:

```python
n = len(self.df_before)
after_existing = self.df_after.iloc[:n].copy()
after_existing.index = self.df_before.index
added_rows = self.df_after.iloc[n:]
```

Positional slicing is deliberate: it is correct whether `ignore_index` fired
or not, and it does not care what the index labels are. Label-based alignment
(`df_after.loc[df_before.index]`) is what breaks today.

This is an assumption about `RuleEngine`, so it gets asserted by a test
(Task 1, `test_added_rows_are_appended_not_interleaved`) rather than trusted.
If a future engine change starts reordering rows, that test fails loudly
instead of the dialog quietly mispairing rows.

### 4.2 Aligning columns

```python
before_aligned = self.df_before.reindex(columns=self.df_after.columns)
```

A column the rule created reads as `NaN` in `before_aligned` and as its value
in `after_existing` — which is exactly right: the rule *did* change that cell,
from "not there" to a value. It highlights, and the tooltip shows the change.
`row_before[col]` can no longer `KeyError` for any column drawn from
`df_after`.

`reindex(columns=...)` is stdlib pandas doing the whole job in one call. No
loop, no `.get()` guards, no defaulting logic.

### 4.3 Added rows are a category, not a change

`ADD_PRODUCT` rows have no "before" to diff against, so they are not part of
`changed`. They are counted and displayed separately:

- `matched_count` becomes `changed.sum() + len(added_rows)` — the number the
  summary label reports as "rows affected". A rule that adds 2 products
  affects 2 rows; reporting 0 is the bug.
- The summary label spells the split out when rows were added, so the two
  kinds are never conflated: `"… 2 rows affected (2 added by rule)"`.
- The after-table appends the added rows below the changed ones, tinted green
  with an "Added by rule" tooltip, so the preview shows what the rule will
  actually produce.

**Decision — show added rows rather than only counting them.** Counting is the
smaller diff, but the dialog exists to answer "what will this rule do to my
data", and a rule whose entire effect is adding rows would render an empty
preview. The rows are already in the frame; displaying them is a few lines.

**Decision — green tint, literal hex, no new theme token.** Follows the
precedent already set and commented at `rule_test_dialog.py:389-390` for the
yellow diff highlight. Two literal colours at one call site do not earn a
`ThemeTokens` field.

### 4.4 Where the normalisation lives

A new `_align_frames()` called from `_run_test` between `apply()` and
`_detect_changed_rows()`, setting `self.before_aligned`, `self.after_existing`,
`self.added_rows`. Every populate method then reads those three instead of
`df_before`/`df_after`.

`df_before` and `df_after` stay as they are — they are the raw record of what
the engine did, and tests assert against them.

## 5. Out of scope

- **`_prepare_df_for_actions` never creates `COPY_FIELD`/`CALCULATE` targets**
  despite collecting them into `needed_columns` (`rules.py:920-923`). Dead
  intent in the engine. Harmless — the actions create their own targets — and
  fixing it changes engine behaviour to fix a display bug. Left alone
  deliberately; worth its own task.
- **`ignore_index=True` at `rules.py:893`.** Correct for the production
  pipeline (it prevents duplicate index labels after the concat). The dialog is
  what is wrong, not the engine.
- The two sibling tasks from the same testing session —
  `6hGfgP9C7355Gm83` (validation feedback unreadable) and
  `6hGfgPGhxWp2cFwV` (rule actions refactor). Different code paths.

## 6. Verification

`QT_QPA_PLATFORM=offscreen python -m pytest` (567 passing on `main` at
`f441346`) plus `ruff check . --exclude shared`.

The five rows of the table in §2 become five committed tests, and each one
fails on `main` today for the reason listed.
