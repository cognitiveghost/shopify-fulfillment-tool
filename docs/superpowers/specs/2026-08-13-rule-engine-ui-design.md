# Rule Engine & Rule UI — Design

Date: 2026-08-13
Roadmap: Phase 6 — "Rule engine / Rule UI: fresh look at logic and UI"
Touches: `shopify_tool/rules.py`, `gui/settings/rules.py`

## Problem

The rule engine and its editor have grown to 1457 and 1256 lines respectively
without a review pass. Reading both end to end surfaced one correctness bug that
silently changes which orders get tagged, one performance problem that scales
with order count, and a UI that has no overview at all.

This document covers both halves in one change, engine first.

## Findings

### F1 — Invalid conditions widen the match (correctness)

`_get_matching_rows` evaluates a rule's conditions and skips any it cannot
resolve:

```python
if field not in df.columns:
    logger.warning(...)
    continue          # rules.py:963
```

The skipped condition never reaches `condition_results`, so `ALL` (`.all(axis=1)`)
combines only the survivors. A rule written as

> `Order_Type equals Single` **AND** `item_count is greater than 3`

where the second condition cannot resolve does not stop matching — it silently
becomes

> `Order_Type equals Single`

and tags **every** single-type row instead of a narrow subset. The failure is
invisible: a `WARNING` in a log no warehouse operator reads, and correct-looking
output that is simply too broad.

The order-level path handles the identical mistake the opposite way:

```python
if field not in order_df.columns or operator not in OPERATOR_MAP:
    result = False    # rules.py:1294 — fails closed
```

So the two evaluation paths disagree on the same input.

### F2 — The UI hands users the input that triggers F1

`get_available_rule_fields()` returns the order-level fields
(`item_count`, `total_quantity`, `has_sku`, …) unconditionally, and
`add_condition_row` offers that same list on **every** condition regardless of
the rule's level. On an article-level rule those names are never DataFrame
columns, so selecting one produces exactly the unresolvable condition F1 then
drops. The most natural user mistake and the silent-widening bug are wired
directly together.

### F3 — Order-rule evaluation is O(orders x rules x steps x rows)

```python
for order_number in df["Order_Number"].unique():
    order_mask = df["Order_Number"] == order_number   # O(N)
    df[order_mask]                                    # O(N), result discarded
    for rule in order_rules:
        order_eligible_mask = order_mask.copy()
        for step_idx, step in enumerate(steps):
            eligible_df = df[order_eligible_mask]     # O(N), every step
```

Every slice is a boolean mask over the **whole** DataFrame, re-taken per step per
rule per order. For 3000 orders, 3 order-level rules and 9000 rows that is on the
order of 10^8 element operations spent selecting rows, before a single condition
is evaluated. Line 824 (`df[order_mask]`) computes a slice and discards it
outright.

### F4 — Order-rule steps gate, they do not narrow

`order_eligible_mask` is copied at rules.py:833 and never reassigned inside the
step loop. Article-level rules genuinely narrow (`current_matches & full_step_matches`,
rules.py:805); order-level rules re-evaluate the same full order every step and
either proceed or `break`.

Gating is arguably the correct semantics — order-level conditions are aggregates
over the whole order, so "narrowing" the order is not meaningful. The defect is
that the code carries a narrowing-shaped variable that never narrows, and the
"+ Add Step" tooltip promises narrowing unconditionally:

> "Add a new step to this rule (narrowing: each step filters rows from previous step)"

### F5 — Label-based row addressing is unsafe

`first_row_index = eligible_df.index[0]` followed by
`first_row_mask[first_row_index] = True` (rules.py:870-872) addresses by index
*label*. `apply()` ends with `pd.concat([df, new_df], ignore_index=True)`, and
callers are free to hand in a DataFrame with duplicate labels; a duplicate label
would set more than one row. Latent, not currently observed.

### F6 — Debug logging left at INFO

`_get_matching_rows` logs the column dtype, the rule value's repr and five sample
values for **every condition of every step of every rule**. `get_available_rule_fields`
logs the full column list plus leftover probes:

```python
logger.info(f"[RULE ENGINE] 'Total_Price' in columns: {'Total_Price' in all_columns}")
```

These are development aids that shipped. They cost log I/O on a network share and
bury the per-rule audit line that is actually worth keeping.

### F7 — No overview in the editor

Every rule renders fully expanded into one scroll area: header row, level combo,
then N steps each with an `IF` group box of condition rows and a `THEN` group box
of action rows. There is no collapse, no summary, no filter. A dozen rules is an
unreadable scroll, and finding the rule you want to edit means visually scanning
all of them.

### F8 — Reorder buttons disagree with priority labels

`_move_rule_up`/`_move_rule_down` swap adjacent entries in the single mixed
`self.rule_widgets` list. `_update_priority_labels` numbers **per level**
(`Article #1`, `Order #1`). Moving an article rule past an order rule therefore
changes nothing the user can see and nothing the engine does — `apply()`
partitions by level before sorting by priority, so priorities only ever compare
within a level. The button appears broken because, for that pairing, it is.

### F9 — Three copies of the order-level field list, one of them dead

The names of the order-level fields exist in three places:

1. `RuleEngine.ORDER_LEVEL_FIELDS` (rules.py:636) — the authority; the engine
   dispatches on these keys
2. `get_available_rule_fields()` (gui/settings/rules.py:166) — a hardcoded list
   that feeds the editor's dropdowns
3. `gui/settings/fields.py:31` — `ORDER_LEVEL_FIELDS` and the `CONDITION_FIELDS`
   built from it

Copy 3 is **dead**: nothing imports either name (`gui/settings/rules.py` takes only
`ACTION_TYPES` and `CONDITION_OPERATORS` from that module). It has also drifted —
it lists `Has_SKU`, which the engine has never supported, so anything reviving it
would offer users a field that cannot match. Copy 2 is live but must be kept in
step with copy 1 by hand.

## Decisions

Two decisions were put to the user before designing; both were answered.

**D1 — Unresolvable conditions fail closed, and the UI flags them.**
An unresolvable condition evaluates to `False` rather than being dropped. This
composes correctly under both match types with no rule-level special case: under
`ALL` the rule stops matching, under `ANY` the remaining conditions still decide.
It also makes the article path agree with what the order path already does.

This is a live behaviour change. A rule that currently "works" because a broken
condition is being ignored will stop firing after this change — which is the
intent, but it means output can shift on the first run. The UI half is what makes
that survivable: the offending condition is marked in the editor before the run,
using the existing validation-feedback mechanism.

**D2 — Both halves, engine first, one PR in two phases.**
Phase 1 carries the correctness and performance value and is well covered by the
existing `tests/test_rules.py`. Phase 2 is the larger, riskier Qt diff and depends
on nothing in Phase 1 except the level-aware field list.

## Design

### Phase 1 — Engine

**1.1 One condition-resolution rule, failing closed.**
Both `_get_matching_rows` and `_evaluate_order_conditions` classify each condition
as resolvable or not, on the same criteria: field present, operator present and in
`OPERATOR_MAP`, field is a real column (or, on the order path, a known
`ORDER_LEVEL_FIELDS` key). A separator field (`--- … ---`) is unresolvable like any
other — separators are disabled items in the combo, so they can only reach the
engine from a hand-edited config, where `False` is the right answer.

Unresolvable yields an all-`False` result for that condition and a single
`WARNING` naming the rule, the field and why. The existing behaviour when *every*
condition is unresolvable (all-`False`) is unchanged; only mixed valid/invalid
rules move.

**1.2 Group orders once; index positionally.**

```python
positions_by_order = df.groupby("Order_Number", sort=False).indices  # once
for positions in positions_by_order.values():
    for rule in order_rules:
        for step in rule.get("steps", []):
            order_df = df.iloc[positions]        # O(k), not O(N)
            if not self._evaluate_order_conditions(order_df, ...):
                break
            ...
```

`order_df` is still re-taken per step, deliberately: today's code re-slices each
step, so a later step's conditions observe writes made by an earlier step's
actions. Hoisting the slice out of the loop would silently change that. The win is
replacing an O(N) boolean mask with an O(k) positional take.

`.indices` returns positional arrays, and all row addressing moves to `.iloc`,
which fixes F5 for free:

```python
mask = pd.Series(False, index=df.index)
mask.iloc[positions] = True          # all rows of the order
mask.iloc[positions[0]] = True       # first row only
```

Masks are built only after a step's conditions pass and only when that step has
actions, so the O(N) allocation happens on the rare path instead of every step.

The discarded `df[order_mask]` (F3) and the never-reassigned `order_eligible_mask`
(F4) both disappear in this rewrite.

**1.3 Say what steps actually do.**
Order-level step semantics stay as they are — sequential gates. The `_add_step_widget`
tooltip becomes level-accurate: article steps narrow the matched rows, order steps
gate on the whole order. Docstrings on `apply()` follow.

**1.4 Logging levels.**
Per-condition dtype/sample-value dumps drop to `DEBUG`. The leftover
`'Stock' in columns` / `'Total_Price' in columns` probes and the full-column-list
dump in `get_available_rule_fields` are deleted. The per-rule `INFO` line (name,
priority, step count, matched count) stays — that is the audit trail worth having.

**1.5 Optional tidy, droppable.**
`OPERATOR_MAP` maps operator names to function *name strings*, resolved through
`globals()[...]` at eight call sites. Mapping to the functions directly removes the
indirection and makes the module statically checkable. It has no consumers outside
`rules.py`. This is cleanup, not a fix — drop it if the diff is already large.

### Phase 2 — UI

**2.1 Collapsible rule cards.**
The header row (priority label, up/down, Test, name, Delete) stays visible. Level
combo, steps container and "+ Add Step" move into a body widget toggled by a
disclosure button. Rules load **collapsed**; "Add New Rule" creates an expanded
one, since you are about to edit it.

**2.2 Header summary line.**
Collapsed cards need to be identifiable without expanding. The header gains a
level badge and a counts summary — `article · 2 steps · 3 conditions · 2 actions`
— rebuilt on collect-relevant edits. Counts, not a rendered sentence: cheap to
keep correct, and enough to find the rule you meant.

**2.3 Filter box.**
A `QLineEdit` above the list that hides cards whose rule name does not match.
`setVisible` on the group box; no model, no proxy.

**2.4 Reorder within level.**
↑/↓ swap with the nearest rule of the **same** level rather than the adjacent list
entry, so the per-level label always changes and the button is never a no-op.
Enablement follows the same rule (first/last *of its level*). This keeps the
existing flat list; splitting the page into article and order sections is the
larger alternative and is deliberately not done here.

**2.5 Level-aware field lists (closes F2 and F9).**
`get_available_rule_fields()` takes the rule's level and omits the order-level
block for article rules. Its hardcoded order-level names are replaced by
`RuleEngine.ORDER_LEVEL_FIELDS.keys()` so the editor cannot drift from what the
engine dispatches on, and the dead `ORDER_LEVEL_FIELDS`/`CONDITION_FIELDS` pair in
`gui/settings/fields.py` is deleted. `level_combo.currentTextChanged` repopulates the field
combos of that rule's conditions. A previously-saved field that is no longer
offered is preserved as an extra combo item and marked invalid, reusing the
existing "field not found in combo box — add it to preserve saved value" path at
`gui/settings/rules.py:570` and the existing `_show_validation_feedback` styling.
Nothing is silently reset.

**2.6 Flag unresolvable conditions (closes D1's UI half).**
`_perform_validation` gains a field-resolvability check on the same code path as
the current regex/date/range validation, so a condition the engine will now treat
as `False` is visibly marked in the editor before the run rather than discovered
afterwards.

## Testing

**Engine** — extend `tests/test_rules.py`:
- mixed valid/invalid condition under `ALL` no longer matches (the F1 regression;
  must fail on `main`)
- mixed valid/invalid under `ANY` still matches on the valid condition
- order-level and article-level paths agree on an unresolvable field
- a separator field resolves to no match
- groupby rewrite is output-equivalent to the current implementation on a
  multi-order, multi-step, multi-rule fixture
- a later step observes an earlier step's action writes (guards the deliberate
  re-slice in 1.2)
- first-row-only actions target exactly one row when index labels are duplicated
  (F5)

**UI** — a focused test module, offscreen:
- collapse toggle hides/shows the body; new rules start expanded
- filter box hides non-matching cards
- ↑/↓ swap within level and disable correctly at level boundaries
- article-level rules are not offered order-level fields; switching level
  preserves an unknown saved field as a flagged item
- `collect()` output is unchanged by collapse state (a collapsed rule must still
  round-trip)

Gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared`.

## Out of scope

- Splitting the editor into separate article and order sections (2.4 alternative)
- Deprecated action types (`SET_PRIORITY`, `EXCLUDE_FROM_REPORT`,
  `SET_PACKAGING_TAG`, `EXCLUDE_SKU`) still warn-and-skip; removing them is a
  config-migration question, not a cleanup
- The `ColumnConfigPanel` list-stretch bug noted during the Mappings work — its
  own ticket
- Ukrainian inline comments in `rules.py` are cleaned where the surrounding code
  is already being rewritten, but no repo-wide sweep; that belongs to the Phase 6
  tag-categories task
