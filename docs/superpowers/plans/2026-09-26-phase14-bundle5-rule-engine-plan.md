# Phase 14 Bundle 5: rule engine. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in this session (the runner forbids fanning out). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the twelve AUDIT-03 findings. Stock stays honest when a rule holds an order or adds a bonus line.

**Architecture:** Operator and matching fixes go in `shopify_tool/rules.py`. The stock side is a new settle step, `core._settle_rule_changes`, which runs after `RuleEngine.apply` and works only through `stock_ledger` (ADR 0010, ADR 0013). Rule holds and bonus holds write reason codes into `System_note` in the run's own `Cannot fulfill: …` format, so the results pane can tell them from a person's hold. The Rules page gets one rule builder, a `validate()`, the engine's execution order, and a fixed SET_STATUS picker. The rule test dialog counts the rows the engine reports it matched.

**Tech Stack:** Python 3, pandas, PySide6, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-26-phase14-bundle5-rule-engine-design.md`. Read it first; its decision table (D1–D11) is binding. Background: `docs/audit/03-rule-engine.md`. Glossary: `CONTEXT.md` § Rules. ADRs: 0010, 0013.

## Global Constraints

- Work in worktree `.claude/worktrees/phase14-bundle5-rule-engine`, branch `phase14-bundle5-rule-engine`. Never `cd` out of it.
- git: `/usr/bin/git`, one plain git command per Bash call. Commit with `/usr/bin/git commit -F <abs path in $CLAUDE_JOB_DIR/tmp>`. Every commit message ends with the `Co-Authored-By` line from the session's attribution reminder.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no <target>`. If `.venv` is missing, run `ln -s /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.venv .venv`. The full suite takes ~4.5 min, so run it in the background. A hook blocks Bash text containing "pytest" in any other form, so write test files with Write/Edit, never with heredocs.
- Never edit `shared/`. Nothing here needs it.
- No hardcoded colours in Qt stylesheets.
- Audit proof tests are in `tests/audit/test_03_rule_engine.py`. **Remove a test's `@pytest.mark.xfail(...)` line in the same task that fixes it.** `strict=True` means an xfail that starts passing fails the suite. The seven unmarked "verified correct" tests must keep passing. So must `test_order_level_set_status_holds_the_whole_order`, which already has no marker.
- `stock_ledger` constants are `FULFILLABLE = "Fulfillable"` and `NOT_FULFILLABLE = "Not Fulfillable"`. Import them rather than retyping the strings in new code.
- Blocker format (from `analysis.add_fulfillment_reason`): `Cannot fulfill: <part>; <part>`. A NO_SKU order's note may end in ` [NO_SKU]`, and that suffix must stay last.
- Reason parts this bundle writes: `Held by rule: <rule name>`, `<SKU>: Out of stock`, and `<SKU>: Insufficient stock (need <n>, have <m>)`, with integers.
- UI copy, verbatim: pane title **Held by a rule**. Pane sentence `Rule “<name>” held this order.` Pane text suffix ` Change the rule, or mark the order fulfillable if it should ship.` Range error `Start is greater than end. Write the smaller number first, for example 10-100.` Dialog note `Tested on the last analysis, which already has your saved rules applied.` Validation line `Rule “<name>”, step <n>, condition <m>: <error>`.

## Review Focus

1. **An order with a NO_SKU line gets a bonus.** Re-claiming must not turn its NO_SKU line Fulfillable. Statuses are restored, not overwritten. Pinned in Task 8.
2. **Numeric order numbers** (`1001` as int in the frame, str in `claim_detail` keys). The settle step has to match them with `str(x).strip()` the same way `stock_ledger._keys` does. Pinned in Task 8.
3. **Rules applied twice**: a re-analysis or `test_applying_rules_twice_equals_applying_once`. `Held by rule: X` must not be appended twice. Pinned in Task 5.
4. **A rule name containing `; `** splits the blocker parser. The engine writes it as `, `. Pinned in Task 5.
5. **A hand-edited config with `SET_STATUS "Fulfillable"`** is skipped with a warning. The order keeps the simulation's status and stock. Pinned in Task 5.

---

### Task 1: Operators: literal `contains`, safe negative regex, Shopify timestamps (AUDIT-03-3, -4, -6)

**Files:**
- Modify: `shopify_tool/rules.py:114-122` (`_op_contains`, `_op_not_contains`)
- Modify: `shopify_tool/rules.py:188-229` (`_parse_date_safe`)
- Modify: `shopify_tool/rules.py:619-629` (`_op_does_not_match_regex`)
- Test: `tests/audit/test_03_rule_engine.py`, `tests/test_rules.py`

**Interfaces:** Produces nothing new. The signatures don't change.

- [ ] **Step 1: Remove the xfail markers** on `test_contains_is_literal`, `test_contains_with_a_bracket_does_not_crash_the_run`, `test_invalid_negative_regex_matches_nothing` and `test_date_operators_read_shopify_timestamps`. Append to `tests/test_rules.py`:

```python
def test_shopify_timestamp_compares_by_its_own_date():
    """D9: the offset is ignored; the date as written is the shop's date."""
    from shopify_tool.rules import _op_date_equals, _parse_date_safe

    late = pd.Series(["2026-01-14 23:30:00 +0200", "2026-01-14T23:30:00+02:00"])
    assert _op_date_equals(late, "2026-01-14").tolist() == [True, True]
    assert _parse_date_safe("2026-01-14 23:30:00 +0200").tzinfo is None


def test_not_contains_is_literal_too():
    from shopify_tool.rules import _op_not_contains

    assert _op_not_contains(pd.Series(["ABC"]), ".").tolist() == [True]
```

(If `tests/test_rules.py` doesn't import `pandas as pd` at the top, add it.)

- [ ] **Step 2: Run them and confirm they fail.** Run `tests/audit/test_03_rule_engine.py tests/test_rules.py`. Expected: the 4 unmarked audit tests and the 2 new tests FAIL.

- [ ] **Step 3: Implement**

```python
def _op_contains(series_val, rule_val):
    """Returns True where the series string contains the rule string (case-insensitive, literal)."""
    return _as_str_series(series_val).str.contains(rule_val, case=False, na=False, regex=False)


def _op_not_contains(series_val, rule_val):
    """Returns True where the series string does not contain the rule string (case-insensitive, literal)."""
    return ~_op_contains(series_val, rule_val)
```

In `_parse_date_safe`, replace the format list and the loop body:

```python
    # Rule values and plain date cells, then Shopify's "Created at"
    # (2026-01-14 18:56:50 +0200) and its ISO form. A timestamp is compared
    # by the date as written -- the shop's local date -- so the offset is
    # dropped, not converted (spec 2026-09-26 D9).
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            parsed = pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            continue
        return parsed.tz_localize(None) if parsed.tzinfo is not None else parsed
```

Update the docstring's format list to match.

```python
def _op_does_not_match_regex(series_val, rule_val):
    """Returns True where the series value does NOT match the regex pattern.

    An invalid pattern matches nothing here, as in `matches regex`: negating
    that all-False result would match every row (AUDIT-03-4).
    """
    if _compile_regex_safe(rule_val) is None:
        return pd.Series(False, index=series_val.index)
    return ~_op_matches_regex(series_val, rule_val)
```

- [ ] **Step 4: Run** `tests/audit/test_03_rule_engine.py tests/test_rules.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(rules): literal contains, safe negative regex, Shopify timestamps (AUDIT-03-3, -4, -6)`.

---

### Task 2: Order-rule negation and match case (AUDIT-03-7, -11)

**Files:**
- Modify: `shopify_tool/rules.py` (new module constant near `OPERATOR_MAP`; `_evaluate_order_conditions` ~1295-1356; `_check_has_sku` ~1429-1467; `_check_has_product` ~1469-1503)
- Test: `tests/audit/test_03_rule_engine.py`, `tests/test_rules.py`

**Interfaces:** Produces `NEGATIVE_OPERATORS: frozenset[str]` in `shopify_tool.rules`.

- [ ] **Step 1: Remove the xfail markers** on `test_negative_operator_means_the_same_on_sku_and_has_sku` and `test_lowercase_match_all_is_all_on_order_rules`. Append to `tests/test_rules.py`:

```python
def test_order_rule_negation_on_a_line_field_means_no_line():
    """D2: 'SKU does not equal GIFT' on an order rule = no line is GIFT."""
    from shopify_tool.rules import RuleEngine

    df = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "GIFT", "A"],
        "Internal_Tags": ["[]"] * 3,
    })
    rule = {"name": "r", "level": "order", "steps": [{
        "conditions": [{"field": "SKU", "operator": "does not equal", "value": "GIFT"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": "NO_GIFT"}]}]}
    out = RuleEngine([rule]).apply(df)
    tagged = out.loc[out["Internal_Tags"].str.contains("NO_GIFT"), "Order_Number"]
    assert set(tagged) == {"#2"}
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** Next to `OPERATOR_MAP`:

```python
# On an order rule a negative operator means *no line* matches the positive
# form, for a line field exactly as for has_sku (spec 2026-09-26 D2).
NEGATIVE_OPERATORS = frozenset({
    "does not equal", "does not contain", "not in list",
    "not between", "does not match regex",
})
```

In `_check_has_sku`, delete the local `negative_operators` list and test `if operator in NEGATIVE_OPERATORS:`. Do the same in `_check_has_product` if it has its own list. In `_evaluate_order_conditions`, replace the line-field branch:

```python
            else:
                # A line field: positive operators need one matching line,
                # negative ones need every line to satisfy the negation.
                op_func = globals()[OPERATOR_MAP[operator]]
                series_result = op_func(order_df[field], value)
                result = bool(
                    series_result.all() if operator in NEGATIVE_OPERATORS
                    else series_result.any()
                )
```

and the combine block:

```python
        if str(match_type).upper() == "ALL":
            return all(results)
        return any(results)
```

- [ ] **Step 4: Run** `tests/audit/test_03_rule_engine.py tests/test_rules.py`. Expected: PASS, including the ALMADERM-shaped tests.
- [ ] **Step 5: Commit** `fix(rules): order-rule negation means no line; match is case-insensitive (AUDIT-03-7, -11)`.

---

### Task 3: One execution order for engine and Rules page (AUDIT-03-12)

**Files:**
- Modify: `shopify_tool/rules.py:688-718` (`__init__`) and add `execution_order`
- Modify: `gui/settings/rules.py:309` (the loader reads `self._rules_config`)
- Test: `tests/audit/test_03_rule_engine.py`, `tests/test_rules.py`

**Interfaces:** Produces `RuleEngine.execution_order(rules: list[dict]) -> list[dict]`, a static method. It returns the same dict objects, reordered, and never mutates them.

- [ ] **Step 1: Remove the xfail marker** on `test_rules_page_shows_rules_in_execution_order`. Append to `tests/test_rules.py`:

```python
def test_execution_order_puts_unprioritised_rules_last_in_list_order():
    from shopify_tool.rules import RuleEngine

    a, b, c = {"name": "a"}, {"name": "b", "priority": 5}, {"name": "c"}
    assert [r["name"] for r in RuleEngine.execution_order([a, b, c])] == ["b", "a", "c"]
    assert "priority" not in a  # the caller's dicts are not written to
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement**

```python
    @staticmethod
    def execution_order(rules):
        """The rules in the order apply() runs them.

        Lower priority first; a rule with no priority runs after every
        prioritised one below 1000, in list order (1000, 1001, ...). Stable.
        The Rules page lists rules with this, so what it shows is what runs.
        """
        defaults = iter(range(1000, 1000 + len(rules)))
        keys = [r["priority"] if "priority" in r else next(defaults) for r in rules]
        return [r for _, r in sorted(zip(keys, rules), key=lambda kr: kr[0])]
```

In `__init__`, replace the `sorted(...)` line with
`self.rules = self.execution_order(self.rules)`. `_normalize_priorities` has already run, so every rule has a priority and the result is unchanged. In `gui/settings/rules.py:309`, change `rules = self._rules_config` to `rules = RuleEngine.execution_order(self._rules_config)`.

- [ ] **Step 4: Run** `tests/audit/test_03_rule_engine.py tests/test_rules.py tests/test_rules_page.py tests/test_settings_page_rules.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(rules-page): list rules in execution order (AUDIT-03-12)`.

---

### Task 4: One rule builder, a SET_STATUS picker, and Save-time validation (AUDIT-03-10, -9, -5, D3 UI)

**Files:**
- Modify: `shopify_tool/rules.py:261-306` (`RANGE_PATTERN` constant; `_parse_range` uses it)
- Modify: `gui/rule_validator.py:85-126` (`validate_range`) and add `condition_error`
- Modify: `gui/settings/rules.py:1185-1250` (`_build_rule_config_from_widgets`), `:1418` (SET_STATUS widget), `:1544-1629` (`collect`), plus new `_rule_config` and `validate`
- Test: `tests/audit/test_03_rule_engine.py`, `tests/test_rules_page.py`

**Interfaces:**
- Produces `shopify_tool.rules.RANGE_PATTERN: re.Pattern`.
- Produces `gui.rule_validator.condition_error(operator: str, value: str) -> str | None`.
- Produces `RulesPage._rule_config(rule_w: dict, priority: int | None) -> dict`. It omits the `priority` key when `priority` is None.
- Produces `RulesPage.validate() -> tuple[bool, list[str]]`.

- [ ] **Step 1: Remove the xfail markers** on `test_range_validator_agrees_with_engine`, `test_rules_page_refuses_to_save_an_invalid_rule` and `test_rule_test_config_keeps_add_product_quantity`. Append to `tests/test_rules_page.py`, reusing its existing imports and qtbot style:

```python
def test_set_status_offers_only_a_hold(qtbot):
    import pandas as pd
    from gui.settings.rules import RulesPage

    rule = {"name": "hold big", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than", "value": "6"}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": "Fulfillable"}]}]}
    page = RulesPage([rule], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    saved = page.collect()["rules"][0]["steps"][0]["actions"][0]
    assert saved == {"type": "SET_STATUS", "value": "Not Fulfillable"}


def test_validate_names_the_rule_step_and_condition(qtbot):
    import pandas as pd
    from gui.settings.rules import RulesPage

    rule = {"name": "sizes", "level": "article", "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"},
                       {"field": "Quantity", "operator": "between", "value": "100-10"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": "X"}]}]}
    page = RulesPage([rule], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1]}))
    qtbot.addWidget(page)

    ok, errors = page.validate()
    assert not ok
    assert errors == ["Rule “sizes”, step 1, condition 2: Start is greater than end. "
                      "Write the smaller number first, for example 10-100."]
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3a: Range.** In `rules.py`:

```python
# start-end, each side optionally negative: "10-100", "-10-0", "-10--5".
RANGE_PATTERN = re.compile(r"^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$")
```

`_parse_range` uses `RANGE_PATTERN.match(range_str)` in place of its inline `re.match`. In `gui/rule_validator.py`:

```python
def validate_range(range_str: str) -> tuple[bool, str | None, str | None]:
    """Validate a 'start-end' range exactly as the rule engine will read it.

    Valid means rules._parse_range accepts it, so the page and the engine
    can't disagree (AUDIT-03-9). A reversed range is an error, not a warning:
    the engine refuses it. The third slot is kept for callers and is None.

    Examples:
        >>> validate_range("10-100")
        (True, None, None)
        >>> validate_range("-10-0")
        (True, None, None)
        >>> validate_range("100-10")[0]
        False
    """
    from shopify_tool.rules import RANGE_PATTERN, _parse_range

    text = str(range_str or "").strip()
    if not text:
        return (False, "Range cannot be empty", None)
    if not RANGE_PATTERN.match(text):
        return (False, "Invalid format. Use: start-end (e.g., 10-100)", None)
    if _parse_range(text) is None:
        return (False, "Start is greater than end. Write the smaller number first, for example 10-100.", None)
    return (True, None, None)
```

- [ ] **Step 3b: `condition_error`**, appended to `gui/rule_validator.py`:

```python
_NUMERIC_OPERATORS = {
    "is greater than", "is less than",
    "is greater than or equal", "is less than or equal",
}


def condition_error(operator: str, value: str) -> str | None:
    """The error the Rules page shows in red for this condition, or None.

    The same checks as the live feedback (RulesPage._perform_validation),
    so Save refuses exactly what the page marks red (AUDIT-03-5).
    """
    if operator in ("matches regex", "does not match regex"):
        ok, msg = validate_regex(value)
        return None if ok else msg
    if operator in ("between", "not between"):
        ok, msg, _ = validate_range(value)
        return None if ok else msg
    if operator in ("in list", "not in list"):
        ok, _count, msg = validate_list(value)
        return None if ok else msg
    if operator in _NUMERIC_OPERATORS:
        ok, msg = validate_numeric(value)
        return None if ok else msg
    return None
```

- [ ] **Step 3c: SET_STATUS picker.** At `gui/settings/rules.py:1418`, drop `"SET_STATUS"` from the `["ADD_TAG", "ADD_ORDER_TAG", "SET_STATUS"]` list and add a branch before it:

```python
        elif action_type == "SET_STATUS":
            # A rule can only hold an order; it can never make one
            # fulfillable (spec 2026-09-26 D3). A saved config with any
            # other value loads as the hold.
            status_combo = WheelIgnoreComboBox()
            status_combo.addItems([NOT_FULFILLABLE])
            layout.insertWidget(insert_pos, status_combo, 1)
            action_refs["param_widgets"]["value"] = status_combo
```

Import it: `from shopify_tool.stock_ledger import NOT_FULFILLABLE`.

- [ ] **Step 3d: One builder.** Add `_rule_config` and make both callers use it. The body is today's `collect()` per-rule body, with two changes: the condition value reader handles `QDateEdit`, and `SET_STATUS` reads `currentText()`.

```python
    @staticmethod
    def _condition_value(value_widget) -> str:
        if isinstance(value_widget, QComboBox):
            return value_widget.currentText()
        if isinstance(value_widget, QDateEdit):
            return value_widget.date().toString("yyyy-MM-dd")
        if isinstance(value_widget, QLineEdit):
            return value_widget.text()
        return ""

    def _rule_config(self, rule_w, priority=None) -> dict:
        """One rule from its widgets. Save and Test both build through here,
        so a test runs exactly what Save would store (AUDIT-03-10)."""
        steps = []
        for step_refs in rule_w.get("steps", []):
            conditions = [
                {
                    "field": c["field"].currentText(),
                    "operator": c["op"].currentText(),
                    "value": self._condition_value(c.get("value_widget")),
                }
                for c in step_refs["conditions"]
            ]
            actions = []
            for act_refs in step_refs["actions"]:
                action_type = act_refs["type"].currentText()
                params = act_refs["param_widgets"]
                act = {"type": action_type}
                if action_type in ["ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG", "SET_STATUS"]:
                    act["value"] = params["value"].currentText()
                elif action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"]:
                    act["value"] = params["value"].text()
                elif action_type == "COPY_FIELD":
                    act["source"] = params["source"].currentText()
                    act["target"] = params["target"].text()
                elif action_type == "CALCULATE":
                    act["operation"] = params["operation"].currentText()
                    act["field1"] = params["field1"].currentText()
                    act["field2"] = params["field2"].currentText()
                    act["target"] = params["target"].text()
                elif action_type == "ALERT_NOTIFICATION":
                    act["message"] = params["message"].text()
                    act["severity"] = params["severity"].currentText()
                elif action_type == "ADD_PRODUCT":
                    act["sku"] = params["sku"].text()
                    act["quantity"] = params["quantity"].value()
                actions.append(act)
            steps.append({
                "conditions": conditions,
                "match": step_refs["match_combo"].currentText(),
                "actions": actions,
            })

        rule = {"name": rule_w["name_edit"].text()}
        if priority is not None:
            rule["priority"] = priority
        rule["level"] = rule_w["level_combo"].currentText()
        rule["steps"] = steps
        return rule

    def _build_rule_config_from_widgets(self, rule_widget_refs):
        """The rule as Test runs it: Save's config, without a priority."""
        return self._rule_config(rule_widget_refs)

    def collect(self) -> dict:
        return {"rules": [
            self._rule_config(rule_w, priority=idx + 1)
            for idx, rule_w in enumerate(self.rule_widgets)
        ]}

    def validate(self) -> tuple[bool, list[str]]:
        """Refuse to save a rule the page marks red (AUDIT-03-5)."""
        from gui.rule_validator import condition_error

        errors = []
        for rule in self.collect()["rules"]:
            for s, step in enumerate(rule["steps"], 1):
                for c, cond in enumerate(step["conditions"], 1):
                    msg = condition_error(cond["operator"], cond["value"])
                    if msg:
                        errors.append(f"Rule “{rule['name']}”, step {s}, condition {c}: {msg}")
        return not errors, errors
```

Check the widget types before you trust this block. Look at how `collect()` reads each action's param widgets today: `SET_MULTI_TAGS` and `ADD_TAG` use a `QLineEdit`, and the internal-tag actions use a combo. Keep whatever it does for each type, except `SET_STATUS`, which is now a combo. Keep the key order `name, priority, level, steps`, so saved JSON doesn't churn.

- [ ] **Step 4: Run** `tests/audit/test_03_rule_engine.py tests/test_rules_page.py tests/test_settings_page_rules.py tests/test_rule_test_dialog.py`. Expected: PASS. If an existing test asserts that a reversed range gives a warning, change it to expect the error, and say so in the commit message.
- [ ] **Step 5: Commit** `fix(rules-page): one rule builder, hold-only SET_STATUS, Save refuses invalid rules (AUDIT-03-5, -9, -10)`.

---

### Task 5: SET_STATUS holds the whole order and says so (AUDIT-03-1 engine side, D3, D5, D8)

**Files:**
- Modify: `shopify_tool/stock_ledger.py` (add `BLOCKER_PREFIX`, `append_blocker`)
- Modify: `shopify_tool/rules.py` (`_execute_actions` gains `rule_name`; the `SET_STATUS` branch; both `apply()` call sites pass `rule_name`)
- Test: `tests/test_stock_ledger.py`, `tests/test_rules.py`

**Interfaces:**
- Produces `stock_ledger.BLOCKER_PREFIX = "Cannot fulfill: "`.
- Produces `stock_ledger.append_blocker(note, part: str) -> str`. It is idempotent: a part already present is not added again.
- Produces `RuleEngine._execute_actions(df, matches, actions, rule_name=None)`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_stock_ledger.py`:

```python
from shopify_tool.stock_ledger import append_blocker


@pytest.mark.parametrize("note, expected", [
    ("", "Cannot fulfill: Held by rule: R"),
    (None, "Cannot fulfill: Held by rule: R"),
    ("Repeat order", "Repeat order; Cannot fulfill: Held by rule: R"),
    ("Cannot fulfill: A: Out of stock", "Cannot fulfill: A: Out of stock; Held by rule: R"),
    ("Cannot fulfill: Held by rule: R", "Cannot fulfill: Held by rule: R"),
    ("Cannot fulfill: A: Out of stock [NO_SKU]",
     "Cannot fulfill: A: Out of stock; Held by rule: R [NO_SKU]"),
])
def test_append_blocker(note, expected):
    assert append_blocker(note, "Held by rule: R") == expected
```

In `tests/test_rules.py`:

```python
def _status_frame():
    return pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "B", "A"],
        "Quantity": [4, 3, 1],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        "System_note": ["", "", ""],
        "Internal_Tags": ["[]"] * 3,
    })


def _hold(level, value="Not Fulfillable", name="big; heavy"):
    field = "total_quantity" if level == "order" else "SKU"
    op, val = ("is greater than or equal", "7") if level == "order" else ("equals", "B")
    return {"name": name, "level": level, "steps": [{
        "conditions": [{"field": field, "operator": op, "value": val}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": value}]}]}


@pytest.mark.parametrize("level", ["order", "article"])
def test_set_status_holds_every_line_and_records_the_rule(level):
    out = RuleEngine([_hold(level)]).apply(_status_frame())
    one = out[out["Order_Number"] == "#1"]
    assert (one["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert (one["System_note"] == "Cannot fulfill: Held by rule: big, heavy").all()
    assert out.loc[out["Order_Number"] == "#2", "Order_Fulfillment_Status"].tolist() == ["Fulfillable"]


def test_set_status_twice_records_the_rule_once():
    engine = RuleEngine([_hold("order")])
    out = engine.apply(engine.apply(_status_frame()))
    assert (out.loc[out["Order_Number"] == "#1", "System_note"]
            == "Cannot fulfill: Held by rule: big, heavy").all()


def test_set_status_never_makes_an_order_fulfillable(caplog):
    df = _status_frame()
    df["Order_Fulfillment_Status"] = "Not Fulfillable"
    out = RuleEngine([_hold("order", value="Fulfillable")]).apply(df)
    assert (out["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert (out["System_note"] == "").all()
    assert "SET_STATUS can only hold" in caplog.text
```

(Import `RuleEngine` and `pytest` at the top of `tests/test_rules.py` if they aren't already there.)

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** In `stock_ledger.py`:

```python
BLOCKER_PREFIX = "Cannot fulfill: "
_NO_SKU_SUFFIX = " [NO_SKU]"


def append_blocker(note, part: str) -> str:
    """Add one reason to a System_note, in the run's own format.

    `Cannot fulfill: <part>; <part>` (analysis.add_fulfillment_reason), after
    any other note, before a trailing ` [NO_SKU]`. A part already there is
    not repeated, so re-applying rules changes nothing.
    """
    text = "" if note is None or pd.isna(note) else str(note)
    suffix = _NO_SKU_SUFFIX if text.endswith(_NO_SKU_SUFFIX) else ""
    text = text.removesuffix(suffix)
    _, sep, tail = text.partition(BLOCKER_PREFIX)
    if sep:
        if part in tail.split("; "):
            return text + suffix
        return f"{text}; {part}{suffix}"
    return f"{text}; {BLOCKER_PREFIX}{part}{suffix}" if text else f"{BLOCKER_PREFIX}{part}{suffix}"
```

In `rules.py`, change `_execute_actions(self, df, matches, actions)` to `_execute_actions(self, df, matches, actions, rule_name=None)`. Pass `rule_name=rule_name` at all three call sites in `apply()`: the article loop and both order-level buckets. Replace the `SET_STATUS` branch:

```python
            elif action_type == "SET_STATUS":
                # A rule can only hold (spec 2026-09-26 D3), and an order
                # ships whole, so the hold covers every line (D5). The reason
                # makes the pane read it as the run's, not a person's (D8).
                from shopify_tool.stock_ledger import NOT_FULFILLABLE, append_blocker
                from shopify_tool.tag_manager import expand_to_order_rows

                if value != NOT_FULFILLABLE:
                    logger.warning(
                        f"[RULE ENGINE] SET_STATUS can only hold an order; "
                        f"ignoring value {value!r} in rule {rule_name!r}"
                    )
                    continue
                order_mask = (
                    expand_to_order_rows(df, matches)
                    if "Order_Number" in df.columns else matches
                )
                df.loc[order_mask, "Order_Fulfillment_Status"] = NOT_FULFILLABLE
                if "System_note" in df.columns:
                    part = "Held by rule: " + str(rule_name or "unnamed").replace("; ", ", ")
                    df.loc[order_mask, "System_note"] = df.loc[order_mask, "System_note"].apply(
                        lambda n, part=part: append_blocker(n, part)
                    )
```

- [ ] **Step 4: Run** `tests/test_stock_ledger.py tests/test_rules.py tests/audit/test_03_rule_engine.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(rules): SET_STATUS holds the whole order and records a reason (AUDIT-03-1)`.

---

### Task 6: The rule test counts what the rule matched (AUDIT-03-8)

**Files:**
- Modify: `shopify_tool/rules.py` (`apply()` records `self.matched_rows`)
- Modify: `gui/rule_test_dialog.py:192-236` (`_run_test`), `:336-350` (summary), plus a module-level `_whole_order_sample`
- Test: `tests/audit/test_03_rule_engine.py`, `tests/test_rule_test_dialog.py`, `tests/test_rules.py`

**Interfaces:**
- Produces `RuleEngine.matched_rows: pd.Series[bool]`. It is indexed like the frame `apply()` received and is set on every call.
- Produces `gui.rule_test_dialog._whole_order_sample(df, min_rows=100) -> pd.DataFrame`.

- [ ] **Step 1: Remove the xfail marker** on `test_rule_test_dialog_reports_rows_the_saved_rule_already_tagged`. In `tests/test_rule_test_dialog.py::test_summary_percentage_never_exceeds_total_rows`, change `assert dialog.matched_count == 4` to `== 2`, and add the comment `# matched rows only; the 2 added rows are reported beside it`. Append:

```python
def test_sample_never_splits_an_order():
    import pandas as pd
    from gui.rule_test_dialog import _whole_order_sample

    df = pd.DataFrame({"Order_Number": [f"#{i // 3}" for i in range(150)]})
    sample = _whole_order_sample(df, min_rows=100)
    assert len(sample) == 102  # 34 whole orders of 3
    assert sample["Order_Number"].value_counts().eq(3).all()
```

In `tests/test_rules.py`:

```python
def test_matched_rows_covers_an_order_rules_whole_order():
    df = _status_frame()
    engine = RuleEngine([{"name": "t", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than or equal", "value": "7"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": "BIG"}]}]}])
    engine.apply(df)
    assert engine.matched_rows.tolist() == [True, True, False]
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** In `apply()`, first line after the logger setup:

```python
        # Rows some step's actions ran on, on the input's index. The rule
        # test reads it: a diff can't see a write that changed nothing.
        self.matched_rows = pd.Series(False, index=df.index)
```

It has to come before the `if not self.rules` early return. In the article loop, inside `if current_matches.any():`, add `self.matched_rows |= current_matches`. In the order loop, right after `if not matched: ... break`, add `self.matched_rows.iloc[positions] = True`.

In `gui/rule_test_dialog.py`:

```python
def _whole_order_sample(df, min_rows=100):
    """The first orders, in frame order, until at least min_rows rows.

    A cut through an order would show an order rule half an order.
    """
    if "Order_Number" not in df.columns or len(df) <= min_rows:
        return df.head(min_rows).copy()
    keys = df["Order_Number"]
    sizes = keys.value_counts(dropna=False)
    taken, rows = [], 0
    for order in keys.drop_duplicates():
        if rows >= min_rows:
            break
        taken.append(order)
        rows += int(sizes.get(order, 0))
    return df[keys.isin(taken)].copy()
```

In `_run_test`, change `self.test_df = self.analysis_df.head(100).copy()` to `self.test_df = _whole_order_sample(self.analysis_df)`. After `self.changed_count = ...`, change the count:

```python
            self.matched_count = int(engine.matched_rows.sum())
```

In the summary, show the matched rows and their share:

```python
        percentage = (self.matched_count / total_rows * 100) if total_rows > 0 else 0
        ...
        summary += f"({self.matched_count} of {total_rows} existing rows, {percentage:.1f}%)"
```

Then add the note on its own line, following the label's existing HTML style:
`summary += "<br>Tested on the last analysis, which already has your saved rules applied."`

Check what reads `changed_count` and `matched_count` before and after this edit, especially `_populate_preview_table` and `_populate_after_actions_table`. Keep `self.matches` as the diff-based mask for the preview. Only the counts change.

- [ ] **Step 4: Run** `tests/test_rule_test_dialog.py tests/test_rules.py tests/audit/test_03_rule_engine.py`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(rule-test): count matched rows, sample whole orders (AUDIT-03-8)`.

---

### Task 7: `claim_detail`: the shortfall at each order's turn

**Files:**
- Modify: `shopify_tool/stock_ledger.py` (`claim` becomes a wrapper)
- Test: `tests/test_stock_ledger.py`

**Interfaces:** Produces `stock_ledger.claim_detail(df, order_numbers) -> tuple[list, dict]`, returning `(covered, lacking)`. `lacking` maps an order number (as passed) to `[(sku, need: float, have: float), ...]`, where `have` is the Stock left at that order's turn, floored at 0. `claim(df, order_numbers)` keeps its signature and returns `(covered, list(lacking))`.

- [ ] **Step 1: Write the failing test**

```python
from shopify_tool.stock_ledger import claim_detail


def test_claim_detail_reports_stock_at_each_orders_turn():
    df = frame([
        ("#1", "GIFT", 1, NF, 3, 3), ("#2", "GIFT", 2, NF, 3, 3), ("#3", "GIFT", 1, NF, 3, 3),
    ])
    covered, lacking = claim_detail(df, ["#1", "#2", "#3"])
    assert covered == ["#1", "#2"]
    assert lacking == {"#3": [("GIFT", 1.0, 0.0)]}
    assert claim(df, ["#1", "#2", "#3"]) == (["#1", "#2"], ["#3"])
```

- [ ] **Step 2: Run it and confirm it fails.** Expected: ImportError.

- [ ] **Step 3: Implement.** Move `claim`'s body into `claim_detail`:

```python
def claim_detail(df, order_numbers) -> tuple:
    """claim(), plus what each skipped order lacked at its turn.

    Returns (covered, lacking): lacking maps an order number, as passed, to
    [(sku, need, have)], have being Stock left when its turn came (>= 0).
    """
    already = fulfillable_orders(df)
    left = stock_left(df)
    by_order = _needs_by_order(df) if _has_ledger(df) else {}
    covered, lacking = [], {}
    for number in order_numbers:
        if _key(number) in already:
            continue
        needs = by_order.get(_key(number), {})
        short = _short(needs, left)
        if short:
            lacking[number] = [
                (sku, float(needs[sku]), max(0.0, float(left[sku]))) for sku in short
            ]
            continue
        for sku, need in needs.items():
            if sku in left:
                left[sku] -= need
        covered.append(number)
    return covered, lacking


def claim(df, order_numbers) -> tuple:
    """Which of these orders Stock left covers, taken in the order given.

    (Keep the existing docstring text.)
    """
    covered, lacking = claim_detail(df, order_numbers)
    return covered, list(lacking)
```

- [ ] **Step 4: Run** `tests/test_stock_ledger.py`. Expected: PASS, and the existing `claim` tests are unchanged.
- [ ] **Step 5: Commit** `feat(stock-ledger): claim_detail reports what a skipped order lacked`.

---

### Task 8: Settle stock after the rules (AUDIT-03-2, AUDIT-03-1 stock side, D1, D4, D6, D7)

**Files:**
- Modify: `shopify_tool/core.py:903-910` (call site) and add `_settle_rule_changes` right after `_run_analysis_and_rules`
- Test: `tests/audit/test_03_rule_engine.py`, new `tests/test_rule_settle.py`

**Interfaces:**
- Consumes `stock_ledger.claim_detail`, `append_blocker`, `fulfillable_orders`, `with_stock_left`, `FULFILLABLE`, `NOT_FULFILLABLE` (Tasks 5, 7), and `analysis.stock_with_internal_columns` and `analysis._prioritize_orders`.
- Produces `core._settle_rule_changes(final_df, stock_df, config) -> pd.DataFrame`.

- [ ] **Step 1: Remove the xfail markers** on `test_add_product_cannot_promise_more_stock_than_exists` and `test_add_product_is_counted_in_final_stock`. Create `tests/test_rule_settle.py`:

```python
"""core._settle_rule_changes: stock after rules (spec 2026-09-26 §2, ADR 0013)."""

import pandas as pd

from shopify_tool import core
from shopify_tool.tag_manager import add_tag

CONFIG = {"column_mappings": {}}  # stock frame below already has internal names


def _run(tmp_path, orders_csv, stock_csv, rules):
    (tmp_path / "orders.csv").write_text(orders_csv, encoding="utf-8")
    (tmp_path / "stock.csv").write_text(stock_csv, encoding="utf-8")
    config = {
        "column_mappings": {
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
                       "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
        },
        "settings": {},
        "rules": rules,
    }
    orders_df, stock_df = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    return core._run_analysis_and_rules(orders_df, stock_df, history, config)[0]


def test_a_rule_hold_returns_the_orders_stock(tmp_path):
    hold = {"name": "big", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than or equal", "value": "7"}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": "Not Fulfillable"}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,4,DHL\n#1,B,3,DHL\n#2,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,10\nB,Beta,10\n", [hold])
    one = out[out["Order_Number"] == "#1"]
    assert (one["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert one["System_note"].str.contains("Cannot fulfill: Held by rule: big", regex=False).all()
    assert (out.loc[out["SKU"] == "A", "Final_Stock"] == 9).all()   # only #2 draws
    assert (out.loc[out["SKU"] == "B", "Final_Stock"] == 10).all()


def test_an_uncovered_bonus_holds_its_order_with_the_runs_reason(tmp_path):
    gift = {"name": "gift", "level": "article", "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,5\nGIFT,Gift box,1\n", [gift])
    status = out.groupby("Order_Number")["Order_Fulfillment_Status"].agg(set).to_dict()
    assert status == {"#1": {"Fulfillable"}, "#2": {"Not Fulfillable"}}
    assert out.loc[out["Order_Number"] == "#2", "System_note"].str.contains(
        "Cannot fulfill: GIFT: Out of stock", regex=False).all()
    assert (out.loc[out["SKU"] == "A", "Final_Stock"] == 4).all()   # #2's A released
    assert set(out.loc[out["SKU"] == "GIFT", "Warehouse_Name"]) == {"Gift box"}


def test_a_bonus_the_stock_file_does_not_list_holds_the_order(tmp_path):
    gift = {"name": "gift", "level": "article", "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_PRODUCT", "sku": "NOPE", "quantity": 1}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,5\n", [gift])
    assert (out["Order_Fulfillment_Status"] == "Not Fulfillable").all()


def _frame(order_numbers):
    """A post-rules frame: order 1001 has A, a NO_SKU line and a GIFT bonus."""
    return pd.DataFrame({
        "Order_Number": order_numbers,
        "SKU": ["A", "NO_SKU", "GIFT"],
        "Has_SKU": [True, False, True],
        "Quantity": [1, 1, 1],
        "Stock": [5, None, 0],
        "Final_Stock": [4, None, 0],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Fulfillable"],
        "System_note": ["", "Cannot fulfill: NO_SKU [NO_SKU]", ""],
        "Internal_Tags": ["[]", "[]", add_tag("[]", "rule_added_product")],
    })


def test_settle_keeps_a_no_sku_line_held_and_matches_numeric_orders():
    stock = pd.DataFrame({"SKU": ["A", "GIFT"], "Stock": [5, 2], "Product_Name": ["Alpha", "Gift"]})
    out = core._settle_rule_changes(_frame([1001, 1001, 1001]), stock, CONFIG)
    assert out["Order_Fulfillment_Status"].tolist() == ["Fulfillable", "Not Fulfillable", "Fulfillable"]
    assert out["Final_Stock"].tolist()[2] == 1
```

Check the `_frame` NO_SKU row against what `analysis` actually produces for a NO_SKU line: the `SKU` value, the `System_note` text, and `Stock`/`Final_Stock` being NaN. Adjust the fixture to match, and keep the point of the test: the NO_SKU line stays Not Fulfillable and the order ships.

- [ ] **Step 2: Run them and confirm they fail.** Expected: the audit tests and `test_rule_settle.py` FAIL. `_settle_rule_changes` doesn't exist yet.

- [ ] **Step 3: Implement.** Call site in `_run_analysis_and_rules`:

```python
        engine = RuleEngine(rules)
        final_df = engine.apply(final_df)
        final_df = _settle_rule_changes(final_df, stock_df, config)
```

The function goes after `_run_analysis_and_rules`:

```python
def _settle_rule_changes(final_df, stock_df, config):
    """Correct stock after the rules ran on a simulated frame (ADR 0013).

    1. Bonus lines (ADD_PRODUCT, tagged rule_added_product) take their SKU's
       opening stock from the stock file; an unlisted SKU has 0 (D7).
    2. Every fulfillable order with a bonus line gives up its draw and claims
       it again, whole, in the simulation's priority order (D6). One the
       stock can't cover is held with the run's own reason (D1, D8).
    3. Stock left is re-derived, which also returns the stock of every order
       a SET_STATUS rule held (D4). No other order is promoted.
    """
    from .stock_ledger import (
        FULFILLABLE, NOT_FULFILLABLE, append_blocker, claim_detail,
        fulfillable_orders, with_stock_left,
    )
    from .tag_manager import parse_tags

    if final_df is None or final_df.empty or "Order_Number" not in final_df.columns:
        return final_df

    bonus = (
        final_df["Internal_Tags"].apply(lambda t: "rule_added_product" in parse_tags(t))
        if "Internal_Tags" in final_df.columns
        else pd.Series(False, index=final_df.index)
    )
    if bonus.any() and {"SKU", "Stock", "Final_Stock"} <= set(final_df.columns):
        stock = analysis.stock_with_internal_columns(stock_df, config.get("column_mappings", {}))
        opening = pd.to_numeric(stock["Stock"], errors="coerce").groupby(stock["SKU"]).sum()
        skus = final_df.loc[bonus, "SKU"]
        final_df.loc[bonus, "Stock"] = skus.map(opening).fillna(0).to_numpy()
        final_df.loc[bonus, "Final_Stock"] = final_df.loc[bonus, "Stock"]
        if "Has_SKU" in final_df.columns:
            final_df.loc[bonus, "Has_SKU"] = True
        if "Product_Name" in stock.columns and "Warehouse_Name" in final_df.columns:
            names = stock.drop_duplicates("SKU").set_index("SKU")["Product_Name"]
            listed = skus.map(names)
            final_df.loc[bonus, "Warehouse_Name"] = listed.where(
                listed.notna(), final_df.loc[bonus, "Warehouse_Name"])

        keys = final_df["Order_Number"].astype(str).str.strip()
        bonus_orders = set(keys[bonus]) & fulfillable_orders(final_df)
        if bonus_orders:
            priority = analysis._prioritize_orders(
                final_df[~bonus], mode=config.get("analysis_mode", "multi_first"))
            ordered = [o for o in priority["Order_Number"] if str(o).strip() in bonus_orders]
            in_play = keys.isin(bonus_orders)
            before = final_df.loc[in_play, "Order_Fulfillment_Status"].copy()
            final_df.loc[in_play, "Order_Fulfillment_Status"] = NOT_FULFILLABLE
            covered, lacking = claim_detail(final_df, ordered)
            back = in_play & keys.isin({str(o).strip() for o in covered})
            final_df.loc[back, "Order_Fulfillment_Status"] = before[back[in_play]]
            for order, parts in lacking.items():
                rows = keys == str(order).strip()
                for sku, need, have in parts:
                    part = (f"{sku}: Out of stock" if have <= 0 else
                            f"{sku}: Insufficient stock (need {int(need)}, have {int(have)})")
                    if "System_note" in final_df.columns:
                        final_df.loc[rows, "System_note"] = final_df.loc[rows, "System_note"].apply(
                            lambda n, part=part: append_blocker(n, part))

    return with_stock_left(final_df)
```

`FULFILLABLE` is only needed if you restore by constant. Restoring `before` is the point, because it keeps a NO_SKU line held, so drop the unused import and let ruff confirm. If `before[back[in_play]]` misaligns (label mismatch), restore with `final_df.loc[back, col] = before.loc[back[back].index]`, and let Review Focus 1's test decide.

- [ ] **Step 4: Run** `tests/test_rule_settle.py tests/audit/test_03_rule_engine.py tests/test_stock_ledger.py tests/test_core.py`. Expected: PASS. If a `tests/test_core*` test that runs rules now sees different `Final_Stock`, read ADR 0010's consequences. A difference caused by a rule-set status is the correction. Anything else is a bug here.
- [ ] **Step 5: Commit** `fix(core): settle stock after rules — bonus lines take stock, rule holds release it (AUDIT-03-1, -2)`.

---

### Task 9: The pane tells a rule hold from a person's hold (D8)

**Files:**
- Modify: `gui/orders_view.py:60-67` (new pattern and code set), `:142-200` (`_reason_problems`, `order_verdict`)
- Modify: `gui/web/pane.js:31-45` (`problemSentence`), `:67-68` (`verdictCopy`)
- Test: `tests/test_order_verdict.py`

**Interfaces:** Produces the verdict problem `{"code": "rule_hold", "rule": str}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_rule_hold_is_the_runs_not_a_persons():
    note = "Cannot fulfill: Held by rule: big, heavy"
    v = order_verdict("Not Fulfillable", [note, note], ["A", "B"], [True, True])
    assert v == {"state": "review", "by_hand": False,
                 "problems": [{"code": "rule_hold", "rule": "big, heavy"}]}


def test_two_rule_holds_are_two_problems():
    note = "Cannot fulfill: Held by rule: X; Held by rule: Y"
    v = order_verdict("Not Fulfillable", [note], ["A"], [True])
    assert [p["rule"] for p in v["problems"]] == ["X", "Y"]
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** In `gui/orders_view.py`:

```python
_RULE_HOLD = re.compile(r"^Held by rule: (?P<rule>.+)$")
# Codes that need a person to look, not more stock.
_DATA_CODES = {"invalid_quantity", "no_sku", "other", "rule_hold"}
```

In `_reason_problems`, before the final `else`:

```python
            elif m := _RULE_HOLD.match(part):
                problems.append({"code": "rule_hold", "rule": m["rule"]})
```

In `order_verdict`, make the dedupe key `(p["code"], p.get("sku"), p.get("text"), p.get("rule"))`.

In `gui/web/pane.js`, `problemSentence`, before the fallback:

```js
  if (p.code === "rule_hold") return "Rule “" + p.rule + "” held this order.";
```

In `verdictCopy`, immediately before `if (!v.by_hand) return …`:

```js
  if (!v.by_hand && (v.problems || []).some((p) => p.code === "rule_hold")) {
    return { role: "warning", title: "Held by a rule", source: RUN_SOURCE,
      text: sentences + " Change the rule, or mark the order fulfillable if it should ship." };
  }
```

- [ ] **Step 4: Run** `tests/test_order_verdict.py`, plus any test file that covers `orders_view`/`order_payload` (look for them in `tests/`). Expected: PASS. Then run `node --check gui/web/pane.js` if `node` is on PATH. If it isn't, re-read the edit for syntax.
- [ ] **Step 5: Commit** `feat(pane): an order a rule held reads 'Held by a rule', not 'set by a person'`.

---

### Task 10: Gate

- [ ] **Step 1:** `grep -n "xfail" tests/audit/test_03_rule_engine.py` finds no remaining marker.
- [ ] **Step 2:** Run the full suite in the background: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no`. Expected: every test passes. All 16 xfail cases in `tests/audit/test_03_rule_engine.py` are gone, so the suite's xfail count drops by 16 (from 17 on `origin/main`).
- [ ] **Step 3:** `.venv/bin/ruff check .` is clean.
- [ ] **Step 4:** `graphify update .`
- [ ] **Step 5:** Push the branch with `/usr/bin/git push -u origin phase14-bundle5-rule-engine`. Update `state.md` to `next_stage: C`.

## Self-review notes (for Stage C)

- Spec §2 → Tasks 5, 7, 8. §3 → Tasks 1–3. §4 → Tasks 5, 9. §5 → Tasks 4, 6. §6 seams → one test step per task.
- `append_blocker` lives in `stock_ledger` because reason codes describe order status. `rules.py` and `core.py` both import it, and `orders_view` parses its output.
- `claim`'s one caller (`gui/actions_handler.py:1483`) is untouched. It still gets `(covered, skipped)`.
