# Audit 03: rule engine

Scope: `shopify_tool/rules.py`, `shopify_tool/tag_manager.py` (tag writes),
`gui/rule_validator.py`, `gui/rule_test_dialog.py`, `gui/settings/rules.py`
(the Rules page that builds, validates and saves rules),
`shopify_tool/profile_migrations.py`, and the call site `core.py:896`.
`groups_manager.py` was read. It holds client groups, not rule logic, so
nothing in it is audited here. Proof tests: `tests/audit/test_03_rule_engine.py`.

## 1. Verdict

**Yes for the rules the three clients use today. No for the rest of the
engine.** All 10 production rules are order-level `ADD_INTERNAL_TAG` rules
built from `has_sku` regexes, `order_min_box` and `total_quantity`.
Replaying them over all 39 sessions (1,052 orders) gives exactly the tags each
session saved, with 0 differences, and the tests below pin that behaviour.
Everything outside that path has defects. Two of them are critical but
latent:

- An order-level rule that sets a status holds only the order's first line.
  The other lines still go to the packing list.
- `ADD_PRODUCT` adds lines that skip the stock check.

Three high findings can hit any client the day someone writes a new rule:

- `contains` reads its value as a regex.
- An invalid pattern in `does not match regex` matches every order.
- Save stores rules that the validator has marked in red.

Do not add `SET_STATUS`, `ADD_PRODUCT`, `contains`, date or negative-regex
rules until AUDIT-03-1 to -5 are fixed.

**What "correct" means here.** `CONTEXT.md` has no rule-engine entries, and no
ADR covers the engine. Correctness was therefore taken from three places: the
engine's docstrings, the Rules page tooltips, and the one invariant every
other audit relies on. That invariant: an order ships whole or not at all, and
stock is never promised twice. No business-rule question needed the owner.
Where two parts of the engine disagree (AUDIT-03-7, -11), the tests assert
that they agree. They do not pick which meaning is right.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-03-1 | critical (latent) | Order-level `SET_STATUS` changes only the order's first line | `rules.py:868` | `test_order_level_set_status_holds_the_whole_order` | confirmed |
| AUDIT-03-2 | critical (latent) | `ADD_PRODUCT` lines skip the stock simulation: always Fulfillable, stock never read or reduced | `rules.py:1248`, `rules.py:776`, `core.py:896` | `test_add_product_cannot_promise_more_stock_than_exists`, `test_add_product_is_counted_in_final_stock` | confirmed |
| AUDIT-03-3 | high | `contains` / `does not contain` read their value as a regex | `rules.py:117` | `test_contains_is_literal`, `test_contains_with_a_bracket_does_not_crash_the_run` | confirmed |
| AUDIT-03-4 | high | An invalid pattern in `does not match regex` matches every row | `rules.py:629` | `test_invalid_negative_regex_matches_nothing` | confirmed |
| AUDIT-03-5 | high | Save accepts rules the validator marks as errors | `gui/settings/base.py:34` (the Rules page has no `validate`) | `test_rules_page_refuses_to_save_an_invalid_rule` | confirmed |
| AUDIT-03-6 | high (latent) | Date operators cannot parse Shopify's `Created at` timestamps | `rules.py:219` | `test_date_operators_read_shopify_timestamps` | confirmed |
| AUDIT-03-7 | high (latent) | On order rules, negation means "some line" for a line field and "no line" for `has_sku` | `rules.py:1345` | `test_negative_operator_means_the_same_on_sku_and_has_sku` | confirmed |
| AUDIT-03-8 | low | Rule test previews an input the real run never sees | `gui/rule_test_dialog.py:204`, `gui/settings/rules.py:1182` | `test_rule_test_dialog_reports_rows_the_saved_rule_already_tagged` | confirmed |
| AUDIT-03-9 | low | Range validator and engine disagree on reversed and negative ranges | `gui/rule_validator.py:113` | `test_range_validator_agrees_with_engine` | confirmed |
| AUDIT-03-10 | low | Rule test drops `ADD_PRODUCT`'s quantity | `gui/settings/rules.py:1230` | `test_rule_test_config_keeps_add_product_quantity` | confirmed |
| AUDIT-03-11 | low | Lowercase `"match": "all"` is ALL on article rules and ANY on order rules | `rules.py:1353` | `test_lowercase_match_all_is_all_on_order_rules` | confirmed |
| AUDIT-03-12 | low | Rules page shows list order, the engine runs priority order | `gui/settings/rules.py:92` | `test_rules_page_shows_rules_in_execution_order` | confirmed |

"Latent" means no production rule triggers it today. All 10 production rules
are order-level `ADD_INTERNAL_TAG` rules, and no client maps a date column.

## 3. Findings in detail

### AUDIT-03-1 — Order-level SET_STATUS holds one line of the order (critical, latent)

**What goes wrong.** On an order-level rule, only `ADD_TAG` and
`ADD_ORDER_TAG` are written to every line. Every other action, `SET_STATUS`
included, is written to the order's first line only (`rules.py:864-888`).
`ADD_INTERNAL_TAG` survives this because it widens its own mask to the whole
order. `SET_STATUS` does not.

**Scenario.** A client adds "hold orders of 7+ items": order-level,
`total_quantity >= 7`, `SET_STATUS Not Fulfillable`. Order #1 has lines A×4
and B×3. After the rule, line A is Not Fulfillable and line B is still
Fulfillable. `fulfillable_only()` feeds every report and the Packing Tool
hand-off, so line B is picked and shipped on its own. Its stock was also
already reserved by the simulation, which ran before the rules
(`core.py:851` then `core.py:896`).

**Root cause.** The "apply to first row" bucket was built so that
`ADD_PRODUCT` adds one bonus per order. Every other action type fell into the
same bucket.

**Production evidence.** 0 exposure: no client has a `SET_STATUS` rule.

### AUDIT-03-2 — ADD_PRODUCT skips the stock simulation (critical, latent)

**What goes wrong.** Rules run after the fulfilment simulation, and the rows
`ADD_PRODUCT` creates are appended after every rule has run. A bonus line:

- copies its status from the line that triggered it, so it is Fulfillable
  whenever the order is, whatever the bonus SKU's stock;
- takes `Stock`/`Final_Stock` from the first *order line* with that SKU, or
  0 when no order has it. The stock file is never consulted;
- never reduces `Final_Stock` for the units it gives away.

**Scenario.** Rule: "every order with A gets 1 × GIFT". The stock file holds
1 GIFT. Two orders contain A, so two GIFT lines are created, both Fulfillable,
and 2 are promised from a stock of 1. With 5 in stock, both lines still show
`Final_Stock` 0 instead of 3. Write-off and stock export count the lines (they
sum Fulfillable quantities), so those two are right. The `Final_Stock` column,
and inventory memory built from it, are wrong.

**Root cause.** `ADD_PRODUCT` is an order *mutation*, but it runs as a
post-simulation tag step (`core.py:851` simulation, `core.py:896` rules).

**Production evidence.** 0 exposure: no client has an `ADD_PRODUCT` rule.

### AUDIT-03-3 — `contains` is a regex (high)

**What goes wrong.** `_op_contains` calls `Series.str.contains(value)`, whose
default is `regex=True` (`rules.py:117`, and the same in `does not contain`).
The UI offers `contains` as plain text. Separate regex operators exist for
patterns.

**Scenario.** `Product_Name contains "Mask + Box"` never matches "Mask + Box
Set", because `+` is a quantifier. `contains "."` matches every row.
`contains "("` raises `re.PatternError`. That aborts `engine.apply`, and with
it the whole analysis run, until someone edits the rule.

**Production evidence.** 0 exposure today: no production rule uses
`contains`. Production SKUs contain `-` and product names contain `+` and
brackets, so the first new `contains` rule is likely to hit it.

### AUDIT-03-4 — Invalid negative regex matches everything (high)

**What goes wrong.** An invalid pattern makes `matches regex` return
all-False, which is safe. `does not match regex` is that result negated
(`rules.py:629`), so the same invalid pattern matches every row. The
`not in list` and `not between` operators guard against this case. The regex
operator does not.

**Scenario.** An ALMADERM-style `has_sku does not match regex "^(01|05"`
(one missing bracket) tags every order in the session. The validator marks
the field red, but see AUDIT-03-5.

**Production evidence.** 0 exposure: both production negative-regex patterns
compile.

### AUDIT-03-5 — Save ignores validation errors (high)

**What goes wrong.** The Rules page shows red feedback for an invalid regex,
list, range or number. It has no `validate()`, so the settings window's
save gate (`window.py:583`) uses the base class, which always passes. Every
invalid rule is saved and runs. Each then either matches nothing silently or,
with AUDIT-03-4, matches everything.

**Production evidence.** All 10 production conditions are valid.

### AUDIT-03-6 — Date operators cannot read Shopify timestamps (high, latent)

**What goes wrong.** `_parse_date_safe` accepts exactly `%Y-%m-%d`,
`%d/%m/%Y` or `%d.%m.%Y` (`rules.py:219`). Shopify's `Created at` is
`2026-01-14 18:56:50 +0200`, which fails all three. The date operators treat
an unparseable cell as no match, so every date rule on `Created_At` matches
nothing, silently. The Rules page tooltip and `validate_date`'s docstring both
promise that timestamps work.

**Production evidence.** 0 exposure: no production mapping includes a date
column. The built-in default mapping does map `Created at` → `Created_At`
(`analysis.py:249`), so a new client gets the column but the date rules still
do not work on it.

### AUDIT-03-7 — Negation means two things on order rules (high, latent)

**What goes wrong.** On an order-level rule, a plain line field such as `SKU`
matches if *any* line satisfies the operator (`rules.py:1345`). For `does not
equal`, that means "some line is not X". `has_sku` treats negative operators
as "no line is X" (`rules.py:1458`). The same order with lines A and GIFT is
tagged `NO_GIFT` by `SKU does not equal GIFT` and not by `has_sku does not
equal GIFT`. The Rules page offers both fields on order rules.

**Fix note.** The test only asserts that the two agree. The owner should
decide the meaning. The `has_sku` meaning ("no line") is what a person writing
the rule almost certainly expects.

**Production evidence.** Production negations all go through `has_sku`, whose
behaviour is verified below.

### AUDIT-03-8 — Rule test previews the wrong input (low)

The dialog runs the *same* `RuleEngine.apply` as the real run, which answers
the audit question about a shared code path. It runs it on a different input,
though:

- It receives `analysis_results_df`, which every saved rule has already
  modified. An existing tag rule therefore reports "0 rows affected".
- It keeps only the first 100 rows, so an order-level rule can see half an
  order (not separately tested).
- It runs the rule alone, without the rules that run before it.

### AUDIT-03-9 — Range validator disagrees with the engine (low)

`100-10` gets a yellow warning but is saved. The engine rejects it, so
`between` and `not between` both match nothing. `-10-0` gets a red error,
although the engine accepts it.

### AUDIT-03-10 — Rule test drops ADD_PRODUCT quantity (low)

`_build_rule_config_from_widgets` reads combo boxes and line edits only. It
skips the quantity spin box, so the test runs with the engine default of 1.
Save (`collect`) does read the quantity.

### AUDIT-03-11 — `match` case differs by level (low)

The article path uppercases `match`. The order path compares it to `"ALL"`
as written, so a hand-edited `"all"` behaves as ANY on order rules. The UI
always writes `ALL`/`ANY`, so only hand-edited configs are affected.

### AUDIT-03-12 — Rules page order is not execution order (low)

The engine sorts by `priority`. The page lists rules in file order, numbers
them in that order, and rewrites `priority` from it on save. A hand-edited
config with priorities out of file order runs in one order but is shown in
another, and changes meaning on the next save. All 33 production configs and
backups have priorities in file order.

## 4. Verified correct

| what | test |
|---|---|
| The ALMADERM rule shape (positive and negative `has_sku` regex, `order_min_box`, multi-step gates, `total_quantity`) tags exactly the intended orders, and order tags cover every line | `test_production_shaped_order_rules_tag_the_right_orders` |
| Applying the rules twice equals applying them once (tag writes dedupe) | `test_applying_rules_twice_equals_applying_once` |
| HERBAR's `>= 7` / `<= 6` bands are exclusive and cover every order | `test_total_quantity_bands_are_exhaustive_and_exclusive` |
| WATERDROP's `order_min_box equals` is exact and leaves unlisted boxes untagged | `test_order_min_box_equals_is_exact` |
| A condition the engine cannot resolve fails its ALL step; it is not dropped | `test_unresolvable_condition_blocks_an_all_step` |
| A lower priority number runs first, and a later rule sees an earlier rule's writes | `test_priority_order_and_chaining` |
| Old single-step rules (root `conditions`/`actions`, no `priority`) keep their meaning | `test_legacy_single_step_rule_keeps_its_meaning` |

**Migrations.** `profile_migrations.py` has no rule migration. Old rule
formats are normalised when they are read (`RuleEngine._normalize_steps`,
`_normalize_priorities`) and by the Rules page loader. Both preserve meaning:
see the legacy test, with the exceptions in AUDIT-03-11 and -12.

**Operator semantics as they stand** (not findings, but a fix cycle should
know them):

- `equals`, `starts with`, `ends with` and the regex operators are
  case-sensitive.
- `contains`, `in list` and `not in list` are case-insensitive, and the list
  operators trim spaces.
- `is empty` does not count whitespace-only cells as empty.
- Every negative operator matches blank cells.
- Article rules always run before order rules, whatever their priority. The
  Rules page numbers each level separately, so this matches what it shows.

**Production replay.** Every session in `alma/`, `Sessions/herbar/` and
`Sessions/wt/` was re-run with its client's current config: 39 sessions,
1,052 orders. The resulting rule tags match the saved
`fulfillment_analysis.xlsx` for 1,052 of 1,052 orders. The rule sets are
identical across all 33 config backups, so none of this comes from config
drift. Per rule:

- **ALMADERM** (718 orders). "BOX+ANY" tags 131. "BOX ONLY" tags 587.
  "MASK ONLY" tags 0: every order with a mask SKU in this data also has a box
  SKU, which was checked directly against the SKUs. That is the data, not the
  engine. Separately, `REGULAR_BOX` is written by two rules with different
  meanings. "BOX ONLY" writes it whatever the box size, and "BOX+ANY" step 2
  writes it only when the minimum box is `REGULAR_BOX`. This is a config
  choice, but the tag cannot be trusted as a box size.
- **HERBAR** (270 orders). 29 LARGE and 241 REGULAR. The bands are exclusive
  and exhaustive.
- **WATERDROP** (64 orders). XS 21, S 32, M 3, L 3, XL 0. 5 orders get no box
  tag because their minimum box is `UNKNOWN_DIMS` or `NO_BOX_FITS`. That is a
  config coverage gap, not an engine defect.

No rule matches everything. The only rule that conflicts is the double use of
`REGULAR_BOX` above.

## 5. Not covered

- **`groups_manager.py`**: named in the task, but it manages client groups and
  has no rule logic.
- **Legacy actions** `ADD_TAG`, `ADD_ORDER_TAG`, `SET_MULTI_TAGS`, `COPY_FIELD`,
  `CALCULATE` and `ALERT_NOTIFICATION` were read but not tested one by one.
  None is used in production, and the first three are no longer offered in
  the UI. On order rules, `COPY_FIELD`, `CALCULATE` and `SET_MULTI_TAGS` share
  AUDIT-03-1's first-line-only write.
- **The test dialog's 100-row cut** splitting an order is described in
  AUDIT-03-8 but not separately tested.
- **Report filters** (`report_filters.py`) reuse the operator vocabulary but
  are Audit 04's scope.
