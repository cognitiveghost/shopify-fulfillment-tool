# Phase 14 Bundle 5: rule engine — design

**Todoist:** `6hcgpvFvX3JvG2F3` (7 subtasks). **Audit:** `docs/audit/03-rule-engine.md`
(read §3 for each finding). **Proof tests:** `tests/audit/test_03_rule_engine.py`.
**ADR:** 0013 (new), 0010 (stock ledger, binding). **Glossary:** `CONTEXT.md` § Rules.

Classification: bounded. These are fixes to existing flows in `rules.py`, `core.py`,
`stock_ledger.py`, the Rules settings page, the rule test dialog and the order
verdict. There's no new subsystem and no mockup. The UI changes are one picker and
one line of pane copy.

## 1. Decisions

| # | Decision | Who |
|---|---|---|
| D1 | **AUDIT-03-2:** if a bonus line's stock can't be covered, the whole order becomes Not Fulfillable. | owner, 2026-09-25 |
| D2 | **AUDIT-03-7:** a negative operator on an order rule means *no line* matches the positive form. This applies to every line field, as it already does for `has_sku`. | owner, 2026-09-25 |
| D3 | **SET_STATUS can only hold.** Its value is a fixed "Not Fulfillable" picker. The engine skips any other value (for example `Fulfillable` or a typo) and logs a warning. | owner, 2026-09-26 |
| D4 | **Freed stock goes back to Stock left.** When a rule holds an order, its stock is released, but no other order is promoted. The manual hold behaves the same way. | owner, 2026-09-26 |
| D5 | A hold widens to the whole order, on article and order rules alike. It reuses `tag_manager.expand_to_order_rows`, the same widening `ADD_INTERNAL_TAG` uses. | agent |
| D6 | When bonus stock is short, orders get their bonus in the simulation's own priority order (`analysis._prioritize_orders` with the config's `analysis_mode`). | agent |
| D7 | A bonus SKU the stock file doesn't list counts as 0 in stock, so the order is held. This is how the simulation treats an unlisted SKU ("Out of stock"). | agent |
| D8 | A rule hold records a reason code, `Held by rule: <name>`, so the pane shows **Held by a rule** and not "On hold — set by a person". A bonus hold records the simulation's own `Out of stock` / `Insufficient stock (need n, have m)` string. | agent |
| D9 | A timestamp with an offset is compared by the date as written, which is the shop's local date. The offset is ignored. | agent |
| D10 | The rule test counts rows the rule **matched**, as the engine reports them, not rows whose values changed. It cuts its sample at an order boundary. It says it runs on the last analysis, which already has the saved rules applied. | agent |
| D11 | Save and Test build the rule config through one function. The Rules page lists rules in the engine's execution order. | agent |

Decisions D5–D11 are reversible and were taken without the owner. Each one is the
behaviour the rest of the engine or UI already has.

## 2. The stock side (AUDIT-03-1, AUDIT-03-2)

Rules still run after the simulation (ADR 0013). A new step,
`core._settle_rule_changes(final_df, stock_df, config)`, runs right after
`engine.apply` in `_run_analysis_and_rules`, and only when there are rules:

1. **Bonus lines.** These are rows whose `Internal_Tags` carry `rule_added_product`.
   The step sets:
   - `Stock` and `Final_Stock` to the SKU's opening stock, which is the stock
     file summed per SKU via `analysis.stock_with_internal_columns`. An unlisted
     SKU gets 0 (D7).
   - `Has_SKU = True`.
   - `Warehouse_Name` from the stock file, the same lookup
     `_merge_results_to_dataframe` uses, when the SKU is listed.
2. **Re-claim.** Take the orders that are fulfillable under R1
   (`stock_ledger.fulfillable_orders`) and have a bonus line. Set them Not
   Fulfillable, then call `stock_ledger.claim_detail` with them in priority
   order (D6). Covered orders go back to Fulfillable. Skipped orders stay held,
   and their reason is appended to `System_note` on every line (D8, format §4).
3. `stock_ledger.with_stock_left(final_df)`. This single pass also returns
   the stock of every order a `SET_STATUS` rule held (D4).

`stock_ledger.claim_detail(df, order_numbers) -> (covered, lacking)` is new.
`lacking` is `{order_number: [(sku, need, have), ...]}`, where `have` is the
Stock left at that order's turn, floored at 0. `claim` becomes a thin wrapper
around it: `covered, list(lacking)`. Its one caller
(`gui/actions_handler.py:1483`) is unchanged.

The engine's `SET_STATUS` branch (`rules.py`, `_execute_actions`):
- skips a value other than `"Not Fulfillable"` and logs a warning (D3);
- widens `matches` with `expand_to_order_rows` (D5), which also fixes the
  first-line-only write for order rules without touching the action routing;
- appends the reason `Held by rule: <rule name>` to `System_note` (§4).
  `_execute_actions` gains a `rule_name` parameter for this.

The action routing in `apply()` (`apply_to_all` / `apply_to_first`) doesn't
change. `COPY_FIELD`, `CALCULATE` and `SET_MULTI_TAGS` keep their first-line
write, which the audit lists as not covered and no client uses.

## 3. The engine's matching (AUDIT-03-3, -4, -6, -7, -11, -12)

- **03-3:** `_op_contains` and `_op_not_contains` pass `regex=False`.
- **03-4:** `_op_does_not_match_regex` returns all-False when the pattern
  doesn't compile, the same way `not in list` and `not between` guard.
- **03-6:** `_parse_date_safe` also accepts `%Y-%m-%d %H:%M:%S %z` (Shopify CSV)
  and `%Y-%m-%dT%H:%M:%S%z` (ISO), and drops the timezone with
  `tz_localize(None)`, which keeps the wall-clock date (D9). `validate_date`
  already calls it, so the Rules page gains the same formats for free.
- **03-7:** a module constant `NEGATIVE_OPERATORS` replaces the list inside
  `_check_has_sku` (and `_check_has_product` if it has one). In
  `_evaluate_order_conditions`, a line field with a negative operator reduces
  with `.all()`, and every other operator with `.any()`.
- **03-11:** `_evaluate_order_conditions` upper-cases `match_type`.
- **03-12:** a static `RuleEngine.execution_order(rules) -> list` holds the
  priority normalisation and the stable sort. `__init__` uses it, and
  `RulesPage` orders its rules with it before building widgets. Save keeps
  rewriting `priority` from the shown order, which is now the execution order.

## 4. Reason codes and the pane

`System_note` already carries the run's blockers as
`Cannot fulfill: <part>; <part>` (`analysis.add_fulfillment_reason`). The settle
step and the engine append parts in the same format:

- If the note has no `Cannot fulfill: ` yet, append `Cannot fulfill: <part>`,
  joined with `; ` to any existing note (for example `Repeat …`).
- If it has one, append `; <part>`.
- Replace any `; ` inside a rule name with `, ` so the parser's split stays
  sound.

`gui/orders_view.py` parses a new part, `Held by rule: <name>`, as the code
`rule_hold` with key `rule`. Like the data codes, it makes the verdict state
`review`.

`gui/web/pane.js`:
- `problemSentence`: `rule_hold` → `Rule “<name>” held this order.`
- `verdictCopy`: before the generic `!v.by_hand` branch, if any problem is
  `rule_hold`, return role `warning`, title **Held by a rule**, text
  `<sentences> Change the rule, or mark the order fulfillable if it should ship.`,
  and source `RUN_SOURCE`.

A person marking a rule-held order fulfillable already gets "Marked fulfillable
by hand … Rule “X” held this order. Someone marked it fulfillable anyway."
through the existing `by_hand` path.

## 5. The Rules page and the rule test (AUDIT-03-5, -8, -9, -10, SET_STATUS picker)

- **03-9:** `validate_range` decides validity with `rules._parse_range`. A
  reversed range is an **error**: "Start is greater than end. Write the smaller
  number first, for example 10-100." A negative bound is valid. The 3-tuple
  return shape stays.
- **03-5:** `gui/rule_validator.condition_error(operator, value) -> str | None`
  returns the error message the live feedback would show in red: regex, range,
  list or number, by operator. `RulesPage.validate()` runs it over `collect()`
  and returns `(False, ["Rule “<name>”, step <n>, condition <m>: <error>", …])`.
  The settings window already refuses to save when `validate()` fails.
- **03-10:** `RulesPage._rule_config(rule_w, priority)` builds one rule, with the
  body taken from today's `collect()` plus the builder's explicit
  `QDateEdit → yyyy-MM-dd` branch. `collect()` maps it over the widgets.
  `_build_rule_config_from_widgets(refs)` returns `_rule_config(refs, …)`
  without `priority`. The proof test calls it by name, so the name stays.
- **SET_STATUS picker (D3):** the value widget is a non-editable
  `WheelIgnoreComboBox` with one item, `Not Fulfillable`. `collect` reads
  `currentText()`. A saved config with any other value loads showing
  `Not Fulfillable`.
- **03-8:** `RuleEngine.apply` records `self.matched_rows`, a boolean Series on
  the input frame's index (before bonus rows are appended). An article rule
  records every row a step's actions ran on. An order rule records every row of
  each order where at least one step matched. `RuleTestDialog`:
  - sets `matched_count = int(matched_rows.sum())`, counting existing rows
    only. Added rows are reported separately, as today. The summary percentage
    uses `matched_count`. `changed_count` and the diff-based preview stay as
    they are. `tests/test_rule_test_dialog.py::test_summary_percentage_never_exceeds_total_rows`
    changes from `matched_count == 4` to `== 2`, because the old number
    counted each matched row twice;
  - samples whole orders in frame order until at least 100 rows, never
    splitting an order;
  - adds one line under the summary: "Tested on the last analysis, which
    already has your saved rules applied."

## 6. Testing seams

| Seam | What it pins |
|---|---|
| `shopify_tool.rules._op_*`, `_parse_date_safe` | 03-3, 03-4, 03-6 (proof tests, markers removed) |
| `RuleEngine(...).apply(frame)` | 03-7, 03-11, SET_STATUS widening/skip/reason, `matched_rows` |
| `RuleEngine.execution_order` + `RulesPage` (qtbot) | 03-12, 03-5, 03-10, the picker |
| `stock_ledger.claim_detail` | the `(sku, need, have)` at each order's turn, `claim` unchanged |
| `core._run_analysis_and_rules` with CSV files (the proof test's `_run_with_bonus` shape) | 03-2 both tests; 03-1: a held order's lines are all Not Fulfillable and its SKU's `Final_Stock` includes the released units; reason text |
| `gui.orders_view.order_verdict` | `rule_hold` parsing, state `review`, `by_hand` false |
| `RuleTestDialog` (qtbot) | 03-8 proof test; the whole-order sample |

`pane.js` has no JS test harness. Its copy change is checked by reading the diff
and by the `order_verdict` test that feeds it.

## 7. Out of scope

- The first-line write of `COPY_FIELD`, `CALCULATE` and `SET_MULTI_TAGS` on
  order rules (audit §5).
- Re-offering freed stock to held orders (D4).
- The double use of `REGULAR_BOX` in ALMADERM's config. That is a config
  choice, not an engine defect.
