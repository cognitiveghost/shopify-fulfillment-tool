# Rule Engine & Rule UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This repo's runner declines subagent-driven-development** — Stage B runs
> in-session with `superpowers:executing-plans`. See the runner prompt.

**Goal:** Make rule conditions fail closed instead of silently widening a rule's
match, cut order-level rule evaluation from O(orders x rules x steps x rows) to
O(orders x rules x steps x order-size), and give the rule editor an overview
(collapse, summary, filter) plus level-aware field lists that stop producing the
broken conditions in the first place.

**Architecture:** Two phases in one PR. Phase 1 is `shopify_tool/rules.py` only:
a shared condition-resolution helper used by both evaluation paths, and a
positional-index rewrite of the order-rule loop. Phase 2 is
`gui/settings/rules.py`: a collapsible card per rule, a filter box, level-aware
field dropdowns sourced from the engine's own `ORDER_LEVEL_FIELDS`, and a field
validity indicator reusing the existing validation-feedback machinery.

**Tech Stack:** Python 3.11+, pandas, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-13-rule-engine-ui-design.md`

## Global Constraints

- Windows 10/11 is the production target; development is on Ubuntu Linux. Do not
  add platform-specific code.
- `python` is not on PATH. Use `.venv/bin/python` or the `scripts/` wrappers.
- Never hand-edit anything under `shared/` — it is one-way synced from
  `../packing-tool`.
- Never hardcode colors in stylesheets. Use
  `get_theme_manager().get_current_theme()` tokens (`theme.accent_red`,
  `theme.text_secondary`, `theme.border`, …).
- No UI calls from background threads.
- Gate before finishing: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
  and `.venv/bin/ruff check . --exclude shared` must both be clean.
- No direct commits to `main`. This work is on `worktree-rule-engine-ui`.
- Run `graphify update .` after the code changes land.
- Do not bump the version string — this is not a release.

---

### Task 1: Shared condition resolution, failing closed

Closes F1 and F2's engine half. This is the behaviour change the user approved:
an unresolvable condition evaluates to `False` instead of being dropped from the
match.

**Files:**
- Modify: `shopify_tool/rules.py:918-997` (`_get_matching_rows`)
- Modify: `shopify_tool/rules.py:1246-1310` (`_evaluate_order_conditions`)
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `RuleEngine._resolve_condition(self, cond, columns, allow_order_fields)`
  returning `tuple[str | None, str | None, object, str | None]` —
  `(field, operator, value, error)`. `error` is `None` when the condition is
  usable; otherwise it is a human-readable reason string and the first three
  values must not be used. Task 2 calls this from the rewritten order loop.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules.py`:

```python
class TestUnresolvableConditionsFailClosed:
    """An unresolvable condition evaluates to False, it is not dropped.

    Before this change _get_matching_rows skipped conditions it could not
    resolve, so an ALL-match rule fired on its surviving conditions alone and
    tagged more rows than the rule was written to tag.
    """

    def test_all_match_with_unknown_field_does_not_fire(self):
        df = _df({"Order_Type": ["Single", "Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "item_count", "operator": "is greater than", "value": 3}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    def test_any_match_with_unknown_field_still_fires_on_valid_condition(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "no_such_column", "operator": "equals", "value": "x"}],
            [{"type": "ADD_TAG", "value": "YES"}],
            match="ANY",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["YES", ""]

    def test_unknown_operator_fails_closed(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "sounds like", "value": "Single"}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]

    def test_separator_field_fails_closed(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "--- ORDER-LEVEL FIELDS ---", "operator": "equals", "value": ""}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]

    def test_order_level_rule_agrees_on_unknown_field(self):
        df = _df({
            "Order_Number": ["A", "A"],
            "Quantity": [1, 2],
        })
        rules = [_rule(
            [{"field": "item_count", "operator": "equals", "value": 2},
             {"field": "no_such_column", "operator": "equals", "value": "x"}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL", level="order",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py::TestUnresolvableConditionsFailClosed -v`

Expected: `test_all_match_with_unknown_field_does_not_fire`,
`test_unknown_operator_fails_closed` and `test_separator_field_fails_closed` FAIL
with `assert ['NOPE', 'NOPE', ''] == ['', '', '']` or similar — the rule fires
because the bad condition was dropped. `test_any_match_...` and
`test_order_level_rule_agrees_on_unknown_field` should already PASS (the order
path already fails closed, and ANY is unaffected by dropping); they are
regression guards, not new behaviour. If `test_order_level_...` fails, stop and
re-read `_evaluate_order_conditions` before continuing.

- [ ] **Step 3: Add the shared resolver**

Insert this method on `RuleEngine`, immediately above `_get_matching_rows`:

```python
    def _resolve_condition(self, cond, columns, allow_order_fields):
        """Resolves a condition to (field, operator, value, error).

        A condition the engine cannot evaluate is an error, not something to
        skip. Skipping one drops it out of an ALL-match, which makes the rule
        fire on its remaining conditions and match more rows than written.

        Args:
            cond (dict): The condition, with 'field', 'operator' and 'value'.
            columns: The DataFrame columns available to this condition.
            allow_order_fields (bool): True on the order-level path, where
                ORDER_LEVEL_FIELDS names are computed rather than looked up.

        Returns:
            tuple: (field, operator, value, error). error is None when the
                condition is usable; otherwise it explains why not and the
                other three values must not be used.
        """
        field = cond.get("field")
        operator = cond.get("operator")
        value = cond.get("value")

        if not field:
            return None, None, None, "condition has no field"
        if field.startswith("---"):
            return None, None, None, f"'{field}' is a dropdown separator, not a field"
        if not operator:
            return None, None, None, f"condition on '{field}' has no operator"
        if operator not in OPERATOR_MAP:
            return None, None, None, f"unknown operator '{operator}'"

        if allow_order_fields and field in self.ORDER_LEVEL_FIELDS:
            return field, operator, value, None
        if field not in columns:
            hint = "" if allow_order_fields else " (order-level fields need level: order)"
            return None, None, None, f"field '{field}' is not a column{hint}"

        return field, operator, value, None
```

- [ ] **Step 4: Use it in the article path**

In `_get_matching_rows`, replace the whole per-condition validation block
(rules.py:946-985, from `for cond in conditions:` down to
`condition_results.append(result)`) with:

```python
        for cond in conditions:
            field, operator, value, error = self._resolve_condition(
                cond, df.columns, allow_order_fields=False
            )
            if error:
                logger.warning(
                    f"[RULE ENGINE] Condition cannot be evaluated and is treated "
                    f"as no-match: {error}"
                )
                condition_results.append(pd.Series(False, index=df.index))
                continue

            op_func = globals()[OPERATOR_MAP[operator]]
            logger.debug(
                f"[RULE ENGINE] {field} {operator} {value!r} "
                f"(dtype {df[field].dtype})"
            )
            result = op_func(df[field], value)
            condition_results.append(result)
```

`globals()[OPERATOR_MAP[operator]]` is the form the rest of the file uses today —
match it here. Task 4 replaces every occurrence at once, or is dropped and they
all stay as they are. Do not introduce a second form in this task.

The `logger.info` lines dumping dtype, value repr and five sample values are
deleted, not demoted individually — the single `logger.debug` above replaces
them all.

- [ ] **Step 5: Use it in the order path**

In `_evaluate_order_conditions`, replace the block from `field = condition.get("field")`
through the `if not all([field, operator]): continue` / separator checks
(rules.py:1261-1270) with:

```python
            field, operator, value, error = self._resolve_condition(
                condition, order_df.columns, allow_order_fields=True
            )
            if error:
                logger.warning(
                    f"[RULE ENGINE] Order condition cannot be evaluated and is "
                    f"treated as no-match: {error}"
                )
                results.append(False)
                continue
```

`_evaluate_order_conditions` has no module-level logger in scope — add
`import logging; logger = logging.getLogger(__name__)` at the top of the method,
matching the existing style used by `apply` and `_get_matching_rows`.

Then delete the now-unreachable `if field not in order_df.columns or operator not in OPERATOR_MAP:`
guard at the old rules.py:1294, replacing that `if/else` with just the `else`
body — the resolver has already guaranteed both.

- [ ] **Step 6: Run the new tests, then the whole rule suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v`

Expected: all PASS, including the five new ones.

If a *pre-existing* test now fails, do not weaken it — read it first. A
pre-existing test that depended on a condition being dropped is documenting the
bug, and its expectation should change with a comment saying so.

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/rules.py tests/test_rules.py
git commit -m "fix(rules): unresolvable conditions fail closed instead of widening the match"
```

---

### Task 2: Rewrite the order-rule loop with positional indexing

Closes F3, F4 and F5. No behaviour change is intended here — this task is pure
performance plus the removal of dead code, and Step 1's equivalence test is what
proves it.

**Files:**
- Modify: `shopify_tool/rules.py:820-874` (the order-rule block inside `apply`)
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `_resolve_condition` from Task 1 (already wired into
  `_evaluate_order_conditions`; this task does not call it directly).
- Produces: no new public names. `_execute_actions(self, df, matches, actions)`
  keeps its signature — `matches` stays a boolean `pd.Series` indexed like `df`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules.py`:

```python
class TestOrderRuleLoopRewrite:
    """Order-level rules: same results, without O(rows) slicing per step."""

    def test_multi_order_multi_rule_output_unchanged(self):
        df = _df({
            "Order_Number": ["A", "A", "B", "C", "C", "C"],
            "Quantity": [1, 2, 5, 1, 1, 1],
            "SKU": ["x", "y", "z", "x", "x", "y"],
        })
        rules = [
            _rule([{"field": "item_count", "operator": "is greater than", "value": 2}],
                  [{"type": "ADD_TAG", "value": "BIG"}],
                  level="order", priority=1, name="big"),
            _rule([{"field": "total_quantity", "operator": "is greater than or equal", "value": 5}],
                  [{"type": "ADD_TAG", "value": "HEAVY"}],
                  level="order", priority=2, name="heavy"),
        ]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == [
            "", "", "HEAVY", "BIG", "BIG", "BIG",
        ]

    def test_later_step_sees_earlier_step_action_writes(self):
        """Guards the deliberate re-slice: order_df is re-taken every step."""
        df = _df({
            "Order_Number": ["A", "A"],
            "Quantity": [1, 1],
        })
        rules = [{
            "name": "two-step", "level": "order", "priority": 1,
            "steps": [
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 2}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "FIRST"}]},
                {"conditions": [{"field": "Status_Note", "operator": "contains", "value": "FIRST"}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "SECOND"}]},
            ],
        }]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["FIRST, SECOND", "FIRST, SECOND"]

    def test_first_row_action_targets_one_row_with_duplicate_index_labels(self):
        df = pd.DataFrame(
            {"Order_Number": ["A", "A"], "Quantity": [1, 1]},
            index=[0, 0],
        )
        rules = [_rule([{"field": "item_count", "operator": "equals", "value": 2}],
                       [{"type": "ADD_ORDER_TAG", "value": "ONCE"}],
                       level="order")]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["ONCE", "ONCE"]

    def test_order_step_gates_and_stops(self):
        df = _df({"Order_Number": ["A", "A"], "Quantity": [1, 1]})
        rules = [{
            "name": "gate", "level": "order", "priority": 1,
            "steps": [
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 99}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "NO"}]},
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 2}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "ALSO_NO"}]},
            ],
        }]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]
```

`ADD_ORDER_TAG` is routed to `apply_to_all_actions` by the current code
(rules.py:858), so `test_first_row_action_targets_one_row_with_duplicate_index_labels`
asserts both rows are tagged. Before writing the assertion, confirm that routing
is still what the code does; if `ADD_ORDER_TAG` has moved to the first-row branch,
the expectation becomes `["ONCE", ""]`. Do not change the routing in this task.

- [ ] **Step 2: Run the tests to verify which fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py::TestOrderRuleLoopRewrite -v`

Expected: `test_first_row_action_targets_one_row_with_duplicate_index_labels`
FAILS on the current label-based addressing. The other three should PASS — they
are the equivalence baseline that must keep passing through the rewrite. If any
of those three fails now, the rewrite has no safe baseline: stop and report it
rather than proceeding.

- [ ] **Step 3: Rewrite the loop**

Replace the whole block at rules.py:820-874 (`if order_rules and "Order_Number" in df.columns:`
through the end of the order-rule `for` body) with:

```python
        if order_rules and "Order_Number" in df.columns:
            # Group once. .indices gives positional arrays, so every slice and
            # mask below is positional -- index labels are not guaranteed unique
            # (apply() itself concatenates with ignore_index at the end).
            positions_by_order = df.groupby("Order_Number", sort=False).indices

            for order_number, positions in positions_by_order.items():
                for rule in order_rules:
                    rule_name = rule.get("name", "Unnamed")
                    steps = rule.get("steps", [])

                    for step_idx, step in enumerate(steps):
                        # Re-taken every step on purpose: a later step's
                        # conditions must see what an earlier step's actions
                        # wrote. O(len(order)), not O(len(df)).
                        order_df = df.iloc[positions]

                        matched = self._evaluate_order_conditions(
                            order_df,
                            step.get("conditions", []),
                            step.get("match", "ALL"),
                        )
                        if not matched:
                            logger.info(
                                f"[RULE ENGINE] Order {order_number} rule "
                                f"'{rule_name}' step {step_idx+1}: no match, stopping"
                            )
                            break

                        actions = step.get("actions", [])
                        apply_to_all = [
                            a for a in actions
                            if a.get("type", "").upper() in ("ADD_TAG", "ADD_ORDER_TAG")
                        ]
                        apply_to_first = [
                            a for a in actions
                            if a.get("type", "").upper() not in ("ADD_TAG", "ADD_ORDER_TAG")
                        ]

                        # Masks are built only once a step has matched and has
                        # actions, so the O(len(df)) allocation stays off the
                        # hot path.
                        if apply_to_all:
                            mask = pd.Series(False, index=df.index)
                            mask.iloc[positions] = True
                            all_new_rows.extend(
                                self._execute_actions(df, mask, apply_to_all)
                            )

                        if apply_to_first:
                            mask = pd.Series(False, index=df.index)
                            mask.iloc[positions[0]] = True
                            all_new_rows.extend(
                                self._execute_actions(df, mask, apply_to_first)
                            )
```

What this deletes, deliberately:
- `order_mask = df["Order_Number"] == order_number` — an O(rows) scan per order,
  replaced by the single groupby
- `df[order_mask]` on the old line 824 — computed and discarded
- `order_eligible_mask = order_mask.copy()` — never reassigned inside the step
  loop, so it never narrowed anything (F4)
- `eligible_df.index[0]` label addressing — now `positions[0]` (F5)

`positions_by_order` is keyed by order number; `.items()` preserves first-seen
order because of `sort=False`, which keeps log output in the same sequence as
before.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v`

Expected: all PASS, including all four in `TestOrderRuleLoopRewrite`.

- [ ] **Step 5: Correct the step-semantics documentation**

Order-level steps gate; article-level steps narrow. Two places say otherwise.

In `gui/settings/rules.py:359`, replace the tooltip:

```python
        add_step_btn.setToolTip(
            "Add a step to this rule.\n"
            "article rules: each step narrows the rows matched by the step before it.\n"
            "order rules: each step is a gate on the whole order - if it does not\n"
            "match, the rule stops and later steps do not run."
        )
```

In `shopify_tool/rules.py`, extend the `apply()` docstring's
"Supports both article-level (row-by-row) and order-level (entire order) rules."
line with:

```
        Multi-step rules behave differently by level: article-level steps narrow
        the matched rows progressively, while order-level steps act as sequential
        gates on the whole order.
```

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/rules.py gui/settings/rules.py tests/test_rules.py
git commit -m "perf(rules): group orders once and index positionally in the order-rule loop"
```

---

### Task 3: Quiet the leftover debug logging

Closes F6. Task 1 already removed the per-condition dumps in `_get_matching_rows`;
this task handles the editor side.

**Files:**
- Modify: `gui/settings/rules.py:194-226` (`get_available_rule_fields`)
- Modify: `shopify_tool/rules.py` (three comments, Step 2)
- Test: none — this is deletion of logging and comment translation, with no
  behavioural surface.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. `get_available_rule_fields()` keeps its current signature
  here; Task 5 changes it.

- [ ] **Step 1: Delete the development-time logging**

In `get_available_rule_fields`, delete these five `logger` calls outright:

```python
logger.info(f"[RULE ENGINE] DataFrame has {len(all_columns)} columns")
logger.info(f"[RULE ENGINE] ALL COLUMNS: {all_columns}")
logger.info(f"[RULE ENGINE] 'Stock' in columns: {'Stock' in all_columns}")
logger.info(f"[RULE ENGINE] 'Total_Price' in columns: {'Total_Price' in all_columns}")
logger.info(f"[RULE ENGINE] Found {len(custom_columns)} custom columns: {custom_columns}")
```

Keep the `logger.warning` in the `else` branch — a missing `analysis_df` is worth
knowing about. Leave the surrounding logic untouched.

- [ ] **Step 2: Translate the two Ukrainian comments in the rewritten area**

The spec limits this to comments next to code these tasks already touch — no
repo-wide sweep. Task 2 rewrote the order-rule loop, which sits between these
two, in `shopify_tool/rules.py`:

```python
    # Збирати нові рядки з ADD_PRODUCT actions        (~line 772)
    all_new_rows = []
```
becomes
```python
    # Rows created by ADD_PRODUCT actions, appended after all rules run.
    all_new_rows = []
```

and

```python
    # Додати всі нові рядки з ADD_PRODUCT actions     (~line 876)
    if all_new_rows:
```
becomes
```python
    # Append the rows ADD_PRODUCT actions created.
    if all_new_rows:
```

There is a third inside `_execute_actions` (`new_rows = []  # Збирати нові рядки тут`)
— translate it to `# Rows to append, collected here.` while you are in the file.
Leave every other Ukrainian string alone; the Phase 6 tag-categories task owns
those.

- [ ] **Step 3: Verify nothing else referenced them**

Run: `.venv/bin/ruff check gui/settings/rules.py`

Expected: clean. If `logger` is now unused in the module, ruff will say so —
check before deleting the import, since other methods in this 1256-line file use
it.

- [ ] **Step 4: Commit**

```bash
git add gui/settings/rules.py shopify_tool/rules.py
git commit -m "chore(rules): drop development-time column logging, translate stale comments"
```

---

### Task 4 (optional, droppable): OPERATOR_MAP holds functions

Closes F5's tidy half of the spec (section 1.5). **Drop this task if the diff is
already large** — it is cleanup, not a fix, and nothing depends on it.

**Files:**
- Modify: `shopify_tool/rules.py:26-52` (`OPERATOR_MAP`) and its eight call sites
- Test: `tests/test_rules.py` (existing coverage is the check)

**Interfaces:**
- Consumes: nothing.
- Produces: `OPERATOR_MAP: dict[str, Callable]` — values become the operator
  functions themselves rather than their names. Nothing outside `rules.py`
  imports it (verified: the only other operator vocabulary is
  `CONDITION_OPERATORS` in `gui/settings/fields.py`, a plain list of display
  strings, which is unaffected).

- [ ] **Step 1: Move the map below the operator definitions**

`OPERATOR_MAP` currently sits at line 26, above every `_op_*` function, which is
why it holds strings. Move the literal to just after `_op_does_not_match_regex`
(the last operator, ending around line 630) and above `class RuleEngine`, then
change the values from names to references:

```python
OPERATOR_MAP = {
    "equals": _op_equals,
    "does not equal": _op_not_equals,
    "contains": _op_contains,
    "does not contain": _op_not_contains,
    "is greater than": _op_greater_than,
    "is less than": _op_less_than,
    "is greater than or equal": _op_greater_than_or_equal,
    "is less than or equal": _op_less_than_or_equal,
    "starts with": _op_starts_with,
    "ends with": _op_ends_with,
    "is empty": _op_is_empty,
    "is not empty": _op_is_not_empty,
    "in list": _op_in_list,
    "not in list": _op_not_in_list,
    "between": _op_between,
    "not between": _op_not_between,
    "date before": _op_date_before,
    "date after": _op_date_after,
    "date equals": _op_date_equals,
    "matches regex": _op_matches_regex,
    "does not match regex": _op_does_not_match_regex,
}
```

Drop the `# NEW:` comments while moving it — they have not been new for a long
time.

- [ ] **Step 2: Replace every `globals()` lookup**

Change all eight occurrences of

```python
op_func = globals()[OPERATOR_MAP[operator]]
```

to

```python
op_func = OPERATOR_MAP[operator]
```

They are at (pre-edit line numbers) 1289, 1297, 1363, 1379, 1409, 1447, plus the
one Task 1 wrote into `_get_matching_rows`. Find them all with
`grep -n "globals()\[" shopify_tool/rules.py` and confirm the count reaches zero
afterwards.

Also update the module docstring at rules.py:18-19, which describes the map as
pointing at "internal function names".

- [ ] **Step 3: Run the full rule suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v`

Expected: all PASS. The existing operator tests are the real check here — this
change is behaviour-preserving by construction, so any failure means a name was
mistyped in the map.

Run: `grep -n "globals()\[" shopify_tool/rules.py` — expected: no output.

- [ ] **Step 4: Commit**

```bash
git add shopify_tool/rules.py
git commit -m "refactor(rules): OPERATOR_MAP holds operator functions, not their names"
```

---

### Task 5: Level-aware field lists, one source of truth

Closes F2 and F9. This is where Phase 2 starts, and it is the task that stops
users creating the conditions Task 1 now fails closed.

**Files:**
- Modify: `gui/settings/rules.py:156-226` (`get_available_rule_fields`)
- Modify: `gui/settings/rules.py:524-560` (`add_condition_row`, combo population)
- Modify: `gui/settings/rules.py:253-398` (`add_rule_widget`, level change wiring)
- Modify: `gui/settings/fields.py:29-40` (delete dead lists)
- Test: `tests/test_rules_page.py` (create)

**Interfaces:**
- Consumes: `RuleEngine.ORDER_LEVEL_FIELDS` (a `dict[str, str]`; only its keys
  are used here).
- Produces:
  - `RulesPage.get_available_rule_fields(self, level="article")` — returns
    `list[str]`. When `level == "order"` the returned list starts with the
    `"--- ORDER-LEVEL FIELDS ---"` separator followed by the engine's order-level
    field names; when `level == "article"` that block is omitted entirely.
  - `RulesPage._repopulate_field_combos(self, rule_widget_refs)` — returns
    `None`. Rebuilds every condition field combo in the rule for the rule's
    current level, preserving each combo's current selection.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rules_page.py`:

```python
"""RulesPage field vocabularies and level awareness."""
import pandas as pd
import pytest

from gui.settings.rules import RulesPage
from shopify_tool.rules import RuleEngine


@pytest.fixture
def analysis_df():
    return pd.DataFrame({
        "Order_Number": ["A", "B"],
        "SKU": ["x", "y"],
        "Quantity": [1, 2],
    })


def _order_field_names():
    return set(RuleEngine.ORDER_LEVEL_FIELDS.keys())


class TestLevelAwareFields:
    def test_article_level_omits_order_fields(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = set(page.get_available_rule_fields(level="article"))
        assert not (fields & _order_field_names())
        assert "--- ORDER-LEVEL FIELDS ---" not in fields

    def test_order_level_includes_every_engine_order_field(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = set(page.get_available_rule_fields(level="order"))
        assert _order_field_names() <= fields

    def test_article_level_still_offers_dataframe_columns(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = page.get_available_rule_fields(level="article")
        assert "SKU" in fields
        assert "Quantity" in fields


class TestLevelSwitchPreservesSavedField:
    def test_switching_to_article_keeps_unknown_field_selected(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "order",
            "steps": [{
                "conditions": [{"field": "item_count", "operator": "equals", "value": "2"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        refs = page.rule_widgets[0]
        refs["level_combo"].setCurrentText("article")

        combo = refs["steps"][0]["conditions"][0]["field"]
        assert combo.currentText() == "item_count"
        assert page.collect()["rules"][0]["steps"][0]["conditions"][0]["field"] == "item_count"
```

If `qtbot` is not available, check `tests/conftest.py` for the fixture this repo
already uses for widget tests (`tests/test_column_config_dialog.py` is a working
example) and follow that pattern instead — do not add `pytest-qt` as a
dependency for this.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v`

Expected: FAIL with `TypeError: get_available_rule_fields() got an unexpected
keyword argument 'level'`.

- [ ] **Step 3: Make the field list level-aware and engine-sourced**

In `gui/settings/rules.py`, add the import:

```python
from shopify_tool.rules import RuleEngine
```

Then change the signature and the hardcoded block:

```python
    def get_available_rule_fields(self, level="article"):
        """Fields offered for a condition on a rule of the given level.

        Order-level field names come from RuleEngine.ORDER_LEVEL_FIELDS so the
        editor cannot drift from what the engine dispatches on, and they are
        offered only on order-level rules -- on an article rule they are never
        DataFrame columns, so selecting one produces a condition the engine
        treats as no-match.
        """
        fields = []
        if level == "order":
            fields += ["--- ORDER-LEVEL FIELDS ---"]
            fields += list(RuleEngine.ORDER_LEVEL_FIELDS.keys())
```

Keep the rest of the method as it is (common fields, then discovered DataFrame
columns), appending to `fields` instead of concatenating the removed
`order_level_fields` local. Delete that local entirely.

- [ ] **Step 4: Pass the level in, and preserve unknown selections**

In `add_condition_row`, the level is reachable from the rule the step belongs to.
The simplest correct route: give `add_condition_row` the level via the step refs.
Add a `"level_combo"` key to `step_refs` in `_add_step_widget` (it already
receives `rule_widget_refs`):

```python
        step_refs = {
            "step_box": step_box,
            "separator_label": separator_label,
            "match_combo": match_combo,
            "conditions_layout": conditions_rows_layout,
            "actions_layout": actions_rows_layout,
            "conditions": [],
            "actions": [],
            "level_combo": rule_widget_refs["level_combo"],
        }
```

Then in `add_condition_row`, replace

```python
        available_fields = self.get_available_rule_fields()
```

with

```python
        level_combo = rule_widget_refs.get("level_combo")
        level = level_combo.currentText() if level_combo else "article"
        available_fields = self.get_available_rule_fields(level=level)
```

The existing "field not found in combo box - add it to preserve saved value"
branch (around line 570) already handles a saved field that the level no longer
offers. Leave it exactly as it is — it is the mechanism the spec relies on.

- [ ] **Step 5: Rebuild combos when the level changes**

Add this method to `RulesPage`, next to `_update_priority_labels`:

```python
    def _repopulate_field_combos(self, rule_widget_refs):
        """Rebuilds condition field combos after the rule's level changed.

        A field the new level does not offer is kept as an extra item so a
        saved condition is never silently reset; Task 6's validation marks it.
        """
        level = rule_widget_refs["level_combo"].currentText()
        available_fields = self.get_available_rule_fields(level=level)

        for step_refs in rule_widget_refs.get("steps", []):
            for cond_refs in step_refs["conditions"]:
                combo = cond_refs["field"]
                previous = combo.currentText()

                combo.blockSignals(True)
                combo.clear()
                for field in available_fields:
                    combo.addItem(field)
                    if field.startswith("---"):
                        combo.model().item(combo.count() - 1).setEnabled(False)

                index = combo.findText(previous)
                if index < 0:
                    combo.addItem(previous)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
```

`blockSignals` matters: `currentTextChanged` is wired to
`_on_rule_condition_changed`, which rebuilds the value widget. Letting it fire
once per `addItem` during a rebuild would churn widgets and can drop the user's
typed value.

Wire it in `add_rule_widget`, alongside the existing button connections:

```python
        level_combo.currentTextChanged.connect(
            lambda: [self._repopulate_field_combos(widget_refs),
                     self._update_priority_labels()]
        )
```

`_update_priority_labels` is included because the label is per-level, so changing
a rule's level renumbers every rule.

- [ ] **Step 6: Delete the dead duplicate lists**

In `gui/settings/fields.py`, delete `ORDER_LEVEL_FIELDS` (lines 29-38) and
`CONDITION_FIELDS` (line 40) together with the comment above them. Nothing
imports either name.

Verify first: `grep -rn "CONDITION_FIELDS\|ORDER_LEVEL_FIELDS" --include=*.py . | grep -v .venv`
Expected after the change: only `shopify_tool/rules.py` and the new uses in
`gui/settings/rules.py`.

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py tests/test_rules.py -v`

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add gui/settings/rules.py gui/settings/fields.py tests/test_rules_page.py
git commit -m "fix(rules-ui): offer order-level fields only on order rules, sourced from the engine"
```

---

### Task 6: Flag conditions the engine cannot evaluate

Closes the UI half of decision D1. Without this, Task 1's fail-closed change is
discovered from a log file after a run instead of in the editor before it.

**Files:**
- Modify: `gui/settings/rules.py:807-855` (`_show_validation_feedback` area — add
  a sibling helper)
- Modify: `gui/settings/rules.py:738-806` (`_perform_validation`)
- Modify: `gui/settings/rules.py:611-709` (`_on_rule_condition_changed` — trigger)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `RulesPage.get_available_rule_fields(level=...)` from Task 5.
- Produces: `RulesPage._check_field_resolvable(self, condition_refs)` — returns
  `bool`. `True` when the selected field is one the engine can evaluate for this
  rule's level. Styles the field combo red and shows a message when `False`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules_page.py`:

```python
class TestUnresolvableFieldIsFlagged:
    def test_order_field_on_article_rule_is_flagged(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "item_count", "operator": "equals", "value": "2"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert page._check_field_resolvable(cond_refs) is False
        assert "border" in cond_refs["field"].styleSheet()

    def test_real_column_is_not_flagged(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert page._check_field_resolvable(cond_refs) is True
        assert cond_refs["field"].styleSheet() == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py::TestUnresolvableFieldIsFlagged -v`

Expected: FAIL with `AttributeError: 'RulesPage' object has no attribute '_check_field_resolvable'`.

- [ ] **Step 3: Add the check**

Add to `RulesPage`, directly after `_show_validation_feedback`:

```python
    def _check_field_resolvable(self, condition_refs):
        """Marks a field the engine will treat as no-match.

        The engine fails a condition closed when its field is not a column (or,
        on an order rule, a known order-level field). Showing that here means the
        user sees it while editing rather than finding a rule that quietly
        stopped firing.

        Returns:
            bool: True when the field is one the engine can evaluate.
        """
        theme = get_theme_manager().get_current_theme()
        combo = condition_refs.get("field")
        if combo is None:
            return True

        field = combo.currentText()
        level_combo = condition_refs.get("level_combo")
        level = level_combo.currentText() if level_combo else "article"
        known = set(self.get_available_rule_fields(level=level))
        resolvable = bool(field) and not field.startswith("---") and field in known

        if resolvable:
            combo.setStyleSheet("")
        else:
            combo.setStyleSheet(f"border: 1px solid {theme.accent_red};")
            self._show_validation_feedback(
                condition_refs,
                "error",
                f"'{field}' is not available on an {level} rule - this condition "
                f"will never match.",
            )
        return resolvable
```

`_show_validation_feedback` styles `value_widget` and reuses `feedback_label`;
this helper styles the *field* combo itself, so the two do not fight over the
same widget.

- [ ] **Step 4: Give conditions access to their level, and call the check**

`_check_field_resolvable` reads `condition_refs["level_combo"]`. Set it where
`condition_refs` is built in `add_condition_row`:

```python
        condition_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "value_layout": row_layout,
            "level_combo": rule_widget_refs.get("level_combo"),
        }
```

Then call the check at the end of `_perform_validation`, so it runs on the same
trigger as the existing value validation:

```python
        self._check_field_resolvable(condition_refs)
```

Place it as the final statement of the method, after the existing operator-based
branches — a value that is itself valid should still show the field error.

Also call it from `_repopulate_field_combos` (Task 5), once per condition after
`combo.blockSignals(False)`, so changing a rule's level re-marks affected
conditions immediately:

```python
                self._check_field_resolvable(cond_refs)
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/rules.py tests/test_rules_page.py
git commit -m "feat(rules-ui): flag conditions the engine cannot evaluate"
```

---

### Task 7: Collapsible rule cards with a summary header

Closes F7. The largest UI change; keep `collect()` untouched so a collapsed rule
still round-trips.

**Files:**
- Modify: `gui/settings/rules.py:253-398` (`add_rule_widget`)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: nothing from Tasks 5-6 beyond the existing `widget_refs` dict.
- Produces: two new `widget_refs` keys —
  - `"body"`: the `QWidget` holding level combo, steps container and "+ Add Step";
    its visibility is the collapse state
  - `"summary_label"`: the `QLabel` in the header showing the counts line
  - and `RulesPage._update_rule_summary(self, widget_refs)` returning `None`,
    which rewrites that label from the current widget state.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py`:

```python
class TestCollapsibleRuleCards:
    def _rule(self, name="r"):
        return {
            "name": name, "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    def test_loaded_rules_start_collapsed(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        assert page.rule_widgets[0]["body"].isVisibleTo(page) is False

    def test_added_rule_starts_expanded(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        page.add_rule_widget()
        assert page.rule_widgets[0]["body"].isVisibleTo(page) is True

    def test_summary_reports_counts(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        text = page.rule_widgets[0]["summary_label"].text()
        assert "article" in text
        assert "1 step" in text
        assert "1 condition" in text
        assert "1 action" in text

    def test_collect_is_unaffected_by_collapse_state(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        collapsed = page.collect()
        page.rule_widgets[0]["body"].setVisible(True)
        assert page.collect() == collapsed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py::TestCollapsibleRuleCards -v`

Expected: FAIL with `KeyError: 'body'`.

- [ ] **Step 3: Move the rule body into a toggled widget**

In `add_rule_widget`, add a disclosure button as the first header widget, before
the priority label:

```python
        toggle_btn = QPushButton("▶")
        set_button_role(toggle_btn, "secondary")
        toggle_btn.setMaximumWidth(30)
        toggle_btn.setToolTip("Show or hide this rule's conditions and actions")
        header_layout.addWidget(toggle_btn)
```

Add the summary label after the name field, before the Delete button:

```python
        summary_label = QLabel("")
        summary_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
        header_layout.addWidget(summary_label)
```

Then wrap everything below the header in a body widget. Replace the direct
`rule_layout.addLayout(level_layout)` / `rule_layout.addLayout(steps_container)` /
`rule_layout.addWidget(add_step_btn, ...)` calls with:

```python
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(level_layout)
        body_layout.addLayout(steps_container)
        body_layout.addWidget(add_step_btn, 0, Qt.AlignLeft)
        rule_layout.addWidget(body)
```

Register both in `widget_refs`:

```python
            "body": body,
            "summary_label": summary_label,
```

and wire the toggle:

```python
        def _toggle():
            visible = not body.isVisible()
            body.setVisible(visible)
            toggle_btn.setText("▼" if visible else "▶")

        toggle_btn.clicked.connect(_toggle)
```

- [ ] **Step 4: Set the initial state**

A rule loaded from config starts collapsed; a rule the user just added starts
expanded, because they are about to edit it. `add_rule_widget(config=None)` is
exactly that distinction — it is called with a config when loading
(`for rule_config in rules: self.add_rule_widget(rule_config)`) and without one
from the "Add New Rule" button. At the end of `add_rule_widget`, after the steps
are loaded:

```python
        expanded = config_was_none
        body.setVisible(expanded)
        toggle_btn.setText("▼" if expanded else "▶")
        self._update_rule_summary(widget_refs)
```

`config_was_none` must be captured at the very top of the method, before the
`if not isinstance(config, dict): config = {...}` line overwrites it:

```python
        config_was_none = not isinstance(config, dict)
```

- [ ] **Step 5: Add the summary**

```python
    def _update_rule_summary(self, widget_refs):
        """Rewrites a rule's header summary from its current widget state."""
        level = widget_refs["level_combo"].currentText()
        steps = widget_refs.get("steps", [])
        conditions = sum(len(s["conditions"]) for s in steps)
        actions = sum(len(s["actions"]) for s in steps)

        def plural(n, word):
            return f"{n} {word}" if n == 1 else f"{n} {word}s"

        widget_refs["summary_label"].setText(
            f"{level} · {plural(len(steps), 'step')} · "
            f"{plural(conditions, 'condition')} · {plural(actions, 'action')}"
        )
```

Keep it accurate by calling it wherever the counts can change. Add
`self._update_rule_summary(rule_widget_refs)` as the last line of
`_add_step_widget`, `_delete_step`, `add_condition_row` and `add_action_row`, and
in the `level_combo.currentTextChanged` lambda from Task 5. The condition and
action *delete* buttons route through `_delete_row_from_list`, which does not
receive the rule refs — extend those two `clicked.connect` lambdas instead:

```python
        delete_btn.clicked.connect(
            lambda: [self._delete_row_from_list(row_widget,
                                                rule_widget_refs["conditions"],
                                                condition_refs),
                     self._update_rule_summary_for_step(rule_widget_refs)]
        )
```

where the step-level helper resolves back to the owning rule:

```python
    def _update_rule_summary_for_step(self, step_refs):
        """Finds the rule a step belongs to and refreshes its summary."""
        for rule_w in self.rule_widgets:
            if step_refs in rule_w.get("steps", []):
                self._update_rule_summary(rule_w)
                return
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v`

Expected: all PASS, including Tasks 5 and 6's tests — Task 5's
`test_switching_to_article_keeps_unknown_field_selected` reaches into
`refs["steps"][0]["conditions"][0]`, which the body rewrap must not disturb.

- [ ] **Step 7: Commit**

```bash
git add gui/settings/rules.py tests/test_rules_page.py
git commit -m "feat(rules-ui): collapsible rule cards with a counts summary"
```

---

### Task 8: Filter box and level-aware reordering

Closes F8 and the filter half of F7.

**Files:**
- Modify: `gui/settings/rules.py:44-69` (`__init__` header row)
- Modify: `gui/settings/rules.py:84-155` (`_move_rule_up`, `_move_rule_down`,
  `_update_priority_labels`)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `widget_refs["group_box"]` and `widget_refs["level_combo"]`.
- Produces: `RulesPage._filter_rules(self, text)` returning `None` — hides rule
  cards whose name does not contain `text`, case-insensitively. Empty text shows
  all.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py`:

```python
class TestFilterAndReorder:
    def _rule(self, name, level="article"):
        return {
            "name": name, "level": level,
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    def test_filter_hides_non_matching_rules(self, qtbot, analysis_df):
        page = RulesPage([self._rule("alpha"), self._rule("beta")], analysis_df)
        qtbot.addWidget(page)
        page._filter_rules("alp")
        assert page.rule_widgets[0]["group_box"].isVisibleTo(page) is True
        assert page.rule_widgets[1]["group_box"].isVisibleTo(page) is False

    def test_empty_filter_shows_everything(self, qtbot, analysis_df):
        page = RulesPage([self._rule("alpha"), self._rule("beta")], analysis_df)
        qtbot.addWidget(page)
        page._filter_rules("alp")
        page._filter_rules("")
        assert page.rule_widgets[1]["group_box"].isVisibleTo(page) is True

    def test_move_up_skips_over_other_level(self, qtbot, analysis_df):
        page = RulesPage(
            [self._rule("a1", "article"),
             self._rule("o1", "order"),
             self._rule("a2", "article")],
            analysis_df,
        )
        qtbot.addWidget(page)
        page._move_rule_up(page.rule_widgets[2])
        names = [r["name_edit"].text() for r in page.rule_widgets]
        assert names == ["a2", "o1", "a1"]

    def test_first_of_its_level_cannot_move_up(self, qtbot, analysis_df):
        page = RulesPage(
            [self._rule("a1", "article"), self._rule("o1", "order")],
            analysis_df,
        )
        qtbot.addWidget(page)
        assert page.rule_widgets[0]["up_btn"].isEnabled() is False
        assert page.rule_widgets[1]["up_btn"].isEnabled() is False
```

`test_move_up_skips_over_other_level` expects a *swap* with the previous
article rule (`a1`), which sits two positions up — `o1` keeps its slot.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py::TestFilterAndReorder -v`

Expected: FAIL — `_filter_rules` does not exist, and the reorder tests fail
because the current code swaps with the adjacent entry regardless of level.

- [ ] **Step 3: Add the filter box**

In `__init__`, between the Add button and the stretch in `header_row`:

```python
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter rules by name…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._filter_rules)
        header_row.addWidget(self.filter_edit)
```

and the method:

```python
    def _filter_rules(self, text):
        """Hides rule cards whose name does not contain `text`."""
        needle = (text or "").strip().lower()
        for rule_w in self.rule_widgets:
            name = rule_w["name_edit"].text().lower()
            rule_w["group_box"].setVisible(not needle or needle in name)
```

- [ ] **Step 4: Reorder within level**

Replace `_move_rule_up` and `_move_rule_down` with a shared implementation that
finds the nearest neighbour of the same level:

```python
    def _neighbour_of_same_level(self, idx, direction):
        """Index of the nearest rule sharing this one's level, or None."""
        level = self.rule_widgets[idx]["level_combo"].currentText()
        candidate = idx + direction
        while 0 <= candidate < len(self.rule_widgets):
            if self.rule_widgets[candidate]["level_combo"].currentText() == level:
                return candidate
            candidate += direction
        return None

    def _swap_rules(self, idx_a, idx_b):
        """Swaps two rules in both the refs list and the layout."""
        widgets = self.rule_widgets
        widgets[idx_a], widgets[idx_b] = widgets[idx_b], widgets[idx_a]

        layout = self.rules_layout
        for position in sorted((idx_a, idx_b)):
            box = widgets[position]["group_box"]
            layout.removeWidget(box)
            layout.insertWidget(position, box)

        self._update_priority_labels()

    def _move_rule_up(self, widget_refs):
        """Moves a rule above the nearest rule of the same level."""
        idx = self.rule_widgets.index(widget_refs)
        target = self._neighbour_of_same_level(idx, -1)
        if target is not None:
            self._swap_rules(idx, target)

    def _move_rule_down(self, widget_refs):
        """Moves a rule below the nearest rule of the same level."""
        idx = self.rule_widgets.index(widget_refs)
        target = self._neighbour_of_same_level(idx, +1)
        if target is not None:
            self._swap_rules(idx, target)
```

`_swap_rules` re-inserts in ascending position order so the second `insertWidget`
is not thrown off by the first one's removal.

- [ ] **Step 5: Enable the buttons per level**

In `_update_priority_labels`, replace the two `setEnabled` lines:

```python
            rule_w["up_btn"].setEnabled(
                self._neighbour_of_same_level(idx, -1) is not None
            )
            rule_w["down_btn"].setEnabled(
                self._neighbour_of_same_level(idx, +1) is not None
            )
```

The per-level `Article #n` / `Order #n` labelling above them is already correct
and does not change — it is the button behaviour that was out of step with it.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v`

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/settings/rules.py tests/test_rules_page.py
git commit -m "feat(rules-ui): filter box, and reorder within a rule's own level"
```

---

### Task 9: Full gate and graph refresh

**Files:**
- No source changes expected. If the gate finds something, fix it here.

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Expected: PASS. The baseline before this work was 541 passing tests; this plan
adds roughly 20, so expect ~561. A *drop* below 541 means something was
deleted or broken — investigate rather than accepting the new number.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check . --exclude shared`

Expected: clean. Likely findings after these tasks: an unused `logging` import in
`gui/settings/fields.py` after the deletions, or an unused local where
`order_level_fields` used to be.

- [ ] **Step 3: Headless smoke check**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import pandas as pd
from PySide6.QtWidgets import QApplication
from gui.settings.rules import RulesPage
app = QApplication([])
df = pd.DataFrame({'Order_Number': ['A'], 'SKU': ['x'], 'Quantity': [1]})
rule = {'name': 'smoke', 'level': 'article', 'steps': [{'conditions': [{'field': 'SKU', 'operator': 'equals', 'value': 'x'}], 'match': 'ALL', 'actions': [{'type': 'ADD_TAG', 'value': 'T'}]}]}
page = RulesPage([rule], df)
print(page.collect())
"`

Expected: prints a `{'rules': [...]}` dict whose single rule round-trips the SKU
condition and the ADD_TAG action, with `priority: 1`. This catches a page that
imports and constructs but cannot serialise.

- [ ] **Step 4: Refresh the knowledge graph**

Run: `graphify update .`

Required by this repo's CLAUDE.md after modifying code.

- [ ] **Step 5: Commit anything the gate changed**

```bash
git add -A
git commit -m "chore(rules): gate fixes and graph refresh"
```

Skip this commit if the gate was clean and `graphify update` produced no tracked
changes.

---

## Notes for the implementer

**The one behaviour change is Task 1.** Everything else is performance, dead code,
or UI. If Task 1's tests pass but a pre-existing test breaks, that test may be
encoding the old widening behaviour — read it before touching it, and say so in
the commit message if you change its expectation.

**Task 4 is optional.** Drop it if the diff is already large; nothing depends on
it.

**Do not restructure the editor into separate article and order sections.** That
was considered and deliberately left out of scope — Task 8's within-level
reordering is the smaller answer to the same problem.

**Watch the `rule_widget_refs` parameter name.** `add_condition_row` and
`add_action_row` declare a parameter called `rule_widget_refs`, but they are
called as `self.add_condition_row(step_refs, ...)` — inside those two methods the
name refers to a *step's* refs, not a rule's. That is why Task 5 puts
`"level_combo"` on `step_refs` and Task 7 passes that same object to
`_update_rule_summary_for_step` (which searches for the owning rule) rather than
to `_update_rule_summary` (which needs rule refs). Renaming the parameter is out
of scope; just do not assume it means what it says.

**`collect()` must not change.** Tasks 7 and 8 alter how rules are displayed and
ordered, never how they serialise. `test_collect_is_unaffected_by_collapse_state`
guards the collapse half; the existing settings round-trip tests guard the rest.
