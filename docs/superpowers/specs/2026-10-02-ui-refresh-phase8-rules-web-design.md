# UI refresh phase 8: Rules and Test rule on the web tier

**Task:** dev-runner run 56, Todoist 6hfx8f2H4XQGFmGM: "UI refresh phase 8: Client settings on the web tier:
Rules and Test rule". Brief: `docs/design/ui-refresh/roadmap.md`, phase 8. Depends on phase 7 (merged, #361).
**Path:** architectural. It replaces the largest Qt editor with a page of the settings document, adds a flag
to the rule schema, and changes what Test runs on.
**Mockup followed:** `docs/design/ui-refresh/mockups/client-settings.html`, states Rules, Rules empty and
Test rule, both themes. The mockup draws the list, the empty state and the Test panel. It does not draw the
editor: §5.3 is this spec's own. Every departure is in §10.

## 1. What this task delivers

1. Rules as a fourth page of the settings document (`gui/web/settings.*`): the list, the empty state and an
   editor that opens inside a rule's row (§5).
2. `RulesDraft`, which holds the rules, takes every edit and words everything the page draws (§3, §4).
3. Rule on/off: `enabled` in the rule schema, a switch per rule, and an engine that skips a rule that is off
   (§7).
4. Reordering by the up and down buttons and by dragging the row's grip (§5.5).
5. Test rule as the mockup's panel: the rule as edited, run on a copy of the whole analysis, counted in
   orders (§6).
6. One token, `scrim`, and one derived CSS variable, `--color-scheme` (§8).
7. Docs: `roadmap.md` (phase 8 as built), `CONTEXT.md` (§13).

`gui/settings/rules.py` and `gui/rule_test_dialog.py` are deleted. Sets, Weight, Reports and Tag categories
keep their Qt widgets.

## 2. Owner's decisions (2026-10-02, run 56)

| Question | Answer |
|---|---|
| Where a rule is edited (the mockup stops at "Edit") | The row opens in place: it expands into the editor under its head line, one rule open at a time |
| The on/off switch | Added. A rule gains `enabled` (missing means on); the analysis skips a rule that is off. A PC on an older version ignores the flag and runs the rule until it updates |
| What Test rule shows | The mockup's: the whole analysis, counted in orders, then Order / Matched on / Change for the first five and "and N more". Today's per-line before and after tables go |
| The design (§3 to §12) | Approved, with drag reorder: the mockup's grip works alongside up and down |

**What the code does that the mockup does not know** (the facts behind the answers):

- A rule has a level. Article rules run before order rules whatever the list order
  (`RuleEngine.execution_order`), so one list that "runs top to bottom" has to be drawn in two groups.
- A rule has steps. Each step has its own conditions, its own ALL/ANY and its own actions.
- Rules have no on/off today: every saved rule runs. `shopify_tool/core.py` is the one reader.
- Today's Test runs on a 100-line sample and counts lines. One order rule over a whole analysis takes 0.2 s
  at 300 orders, 1.3 s at 2,000 and 5 s at 10,000 (measured on a synthetic frame), so the whole-analysis test
  runs on a worker. An article rule is instant.
- The analysis the test runs on already has the saved rules applied.
- The web tier may not use `opacity`, `transition`, `transform`, a gradient or a literal colour
  (`shared/style_lint.py`, ADR 0001), so the mockup's 60 % opacity on an off row and its `rgba()` backdrop
  cannot be written as drawn.
- Rules run inside the analysis, after stock is allocated (`core.py`, ADR 0013), not after it.

## 3. Architecture

```
SettingsWindow (QDialog, Qt frame)
 └─ SettingsWebHost ── one QWebEngineView      General, Orders mapping, Stock mapping, Rules
     ├─ drafts["rules"] = RulesDraft           values, edits, sentences
     └─ run_rule_test on a Worker ──► state["test"]

RulesDraft.view() ──► SettingsBridge.state ──► settings.js render() ──► settings_rules.js
settings_rules.js ──► bridge.edit(action, args) ──► RulesDraft.apply ──► push, host.edited
settings_rules.js ──► bridge.testRule(uid) ──► host ──► Worker(run_rule_test) ──► push
```

- **Python owns every value and every sentence**, as in phase 7. That includes which rule is open and the
  filter text: both decide what `view()` lists. The page's own state is which menu is open and a drag in
  progress.
- **A rule is addressed by a uid**, a number the draft gives it when it loads or is added. It is never
  stored. Keys and edits carry the uid, so focus follows a rule through a move and a late edit cannot land
  on the wrong rule.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/settings/rules_state.py` (new) | `RulesDraft(PageContract)`, the field and action vocabularies' labels, the summary. No widget |
| `gui/settings/rule_test.py` (new) | `run_rule_test`, `running_view`, `failed_view`. No widget |
| `gui/settings/bridge.py` | `testRule`, `closeTest` |
| `gui/settings/web_host.py` | Takes `analysis_df` and `session`; runs the test; `focus_problem` reveals first |
| `gui/settings/window.py` | Builds `RulesDraft`; `"Rules"` joins `WEB_PAGE_KEYS`; takes `session_name` |
| `gui/actions_handler.py` | Passes the session's folder name |
| `gui/web/settings_rules.js` (new) | The Rules page and the Test panel. Loaded before `settings.js` |
| `gui/web/settings.js` | Calls into `settings_rules.js`; the page head's action is per page |
| `gui/web/settings.css`, `settings.html` | The Rules and Test sections; the second script tag |
| `shopify_tool/rules.py` | `RuleEngine` skips a rule whose `enabled` is false |
| `shared/theme.py` | `scrim`; `--color-scheme` |
| `gui/rule_validator.py` | Docstring only: it named `RulesPage` |
| Deleted | `gui/settings/rules.py`, `gui/rule_test_dialog.py` |

`gui/settings/fields.py` keeps `CONDITION_OPERATORS`, `ACTION_TYPES` and `LEGACY_ACTION_TYPES`; the draft
imports them from there. `shared/` gains one token and one derived variable. Packing Tool gets both at its
next sync and needs no work.

### 3.2 `SettingsBridge`: additions to the catalogue

| member | direction | meaning |
|---|---|---|
| `testRule(uid)` → `testRequested(str)` | JS → Python | Test… on that rule |
| `closeTest()` → `testClosed()` | JS → Python | The panel's ✕, Close, or Esc |

The test's result travels in `state["test"]` (§6.3). No new property.

### 3.3 The edit actions

`RulesDraft.apply(action, args) -> bool`, under phase 7's rules: strings and booleans only, an edit of any
other shape is dropped, and it returns whether anything changed. `uid`, `s`, `c`, `a` and `pos` are numbers
sent as strings. `s`, `c` and `a` are positions inside the rule: step, condition, action.

| action | args | effect |
|---|---|---|
| `filter` | `[text]` | The list shows rules whose name contains it, ignoring case, and the open rule |
| `open` | `[uid]` | Opens that rule's editor and closes any other |
| `close` | `[]` | Closes the open editor |
| `reveal` | `[key]` | Opens the rule a `data-key` belongs to. Sent by the host before `problemFocusRequested` |
| `rule_add` | `[]` | Appends an article rule named "New rule", on, with one empty step, and opens it |
| `rule_duplicate` | `[uid]` | A copy named "{name} copy" right after it |
| `rule_delete` | `[uid]` | |
| `rule_move` | `[uid, dir]` | `dir` is `"up"` or `"down"`: one place, inside its level |
| `rule_move_to` | `[uid, pos]` | To position `pos` among the rules of its level |
| `rule_enabled` | `[uid, on]` | `on` is a boolean |
| `rule_name` | `[uid, text]` | Kept as typed |
| `rule_level` | `[uid, level]` | `"article"` or `"order"`. The rule moves to the end of that level's rules |
| `step_add` | `[uid]` | Appends an empty step |
| `step_remove` | `[uid, s]` | Never step 1 |
| `step_match` | `[uid, s, match]` | `"ALL"` or `"ANY"` |
| `cond_add` | `[uid, s]` | Appends `{field: the level's first field, operator: "equals", value: ""}` |
| `cond_remove` | `[uid, s, c]` | |
| `cond_field` | `[uid, s, c, field]` | One of the fields offered for the rule's level (§4.3) |
| `cond_operator` | `[uid, s, c, operator]` | One of `CONDITION_OPERATORS`. The value is cleared when the new operator takes another kind of value (§4.4), and kept otherwise |
| `cond_value` | `[uid, s, c, text]` | |
| `action_add` | `[uid, s]` | Appends `{type: "ADD_INTERNAL_TAG", value: ""}` |
| `action_remove` | `[uid, s, a]` | |
| `action_type` | `[uid, s, a, type]` | One of `ACTION_TYPES`. The action becomes that type's default (§4.5) |
| `action_param` | `[uid, s, a, name, text]` | `name` is one of the type's parameters (§4.5). A menu parameter takes only a value it offers |

`filter`, `open`, `close` and `reveal` change what is drawn and nothing that is saved: `snapshot()` does not
see them.

## 4. The draft (`gui/settings/rules_state.py`)

`RulesDraft(rules: list, analysis_df, tag_categories: dict | None = None)`.

### 4.1 Loading

The rules are deep-copied, put in `RuleEngine.execution_order`, and normalised one by one:

- `name` is a string. `level` is `"order"` when stored so, else `"article"`. `enabled` is false only when
  stored as `False`.
- `steps` is the stored list when it has entries. Otherwise it is one step built from the root-level
  `conditions`, `match` and `actions` (the old format). The root keys go. `priority` goes: `collect()`
  writes it again.
- A step's `match` is `"ANY"` when the stored value upper-cased is `"ANY"`, else `"ALL"`, which is how the
  engine reads it.
- A condition keeps its `field`, `operator` and `value` as stored, whatever they are. An unknown operator
  or a field the level does not offer is kept and marked (§4.4), never replaced.
- An action keeps its dict, extra keys included (`ADD_PRODUCT`'s `product_name` survives a save). Three
  types are normalised as today's page does: `SET_STATUS` takes the value `NOT_FULFILLABLE`;
  `SET_MULTI_TAGS` takes `value` as text (`", ".join(tags)` when `tags` is a list) and drops `tags`;
  `ADD_PRODUCT` with no `quantity` takes 1.
- Any other key on a rule is kept.

### 4.2 `collect()`, `snapshot()`, Test

`collect()` returns `{"rules": [...]}` in list order. Each rule is written as `name`, `priority` (its
position, from 1), `level`, `enabled: False` only when it is off, `steps`, then its other keys. A rule that
is on has no `enabled` key, so a profile opened and saved with no edit is written back unchanged.

`snapshot()` is the contract's: `collect()` as JSON.

`test_config(uid)` is the same rule without `priority` and without `enabled`, or `None` when the rule cannot
be tested (§5.4). A test runs exactly what Save would store, and runs a rule that is off.

### 4.3 Fields

`rule_fields(level, analysis_df)` returns groups of `(label, [field, ...])`:

1. "Order fields": `RuleEngine.ORDER_LEVEL_FIELDS`, on an order rule only.
2. "Common fields": `Order_Number`, `Order_Type`, `SKU`, `Product_Name`, `Quantity`, `Stock`, `Final_Stock`,
   `Shipping_Provider`, `Shipping_Method`, `Destination_Country`.
3. "Other fields in this analysis": the analysis's other columns, sorted, without those that start with
   `_`. Absent with no analysis.

Copy field and Calculate offer the article list, flat, as today.

A field is *resolvable* by today's rule: it is in the level's list; or there is no analysis and it is not an
order field (the list is then a guess, and a client's own column must not be flagged).

### 4.4 Conditions: the value control and what is said under the row

| Operator | Control |
|---|---|
| `is empty`, `is not empty` | None. The stored value stays `""` |
| `date before`, `date after`, `date equals` | A date field. It shows the stored value as `YYYY-MM-DD` when the engine's `_parse_date_safe` can read it, else empty |
| `equals`, `does not equal` on a column of the analysis | A text field with that column's values as suggestions, at most 200 |
| Any other | A text field. Placeholder: `Value1, Value2, Value3` (in list, not in list), `10-100` (between, not between), `^SKU-\d{4}$` (the regex pair), else `Value` |

The three kinds are none, date and text. `cond_operator` clears the value only when the kind changes.

Under a condition row, the first that applies:

| | Text | Blocks Save |
|---|---|---|
| `rule_validator.condition_error` | Its message, unchanged | Yes |
| No field | Choose a field. Until then this condition never matches. | No |
| A field that is not resolvable | “{field}” is not a field an {article/order} rule can read, so this condition never matches. | No |
| An operator not in `CONDITION_OPERATORS` | “{operator}” is not an operator this version knows, so this condition never matches. | No |
| A date operator whose value cannot be read | Pick a date. Until then this condition never matches. | No |
| `in list`, `not in list` | {n} items (1 item) | No, a hint |

### 4.5 Actions

Stored types do not change. The page shows a label.

| Type | Label | Parameters (name: control, placeholder) | Default | Summary |
|---|---|---|---|---|
| `ADD_INTERNAL_TAG` | Add internal tag | `value`: text with the configured tags as suggestions, "Tag" | `value: ""` | Add internal tag `value` |
| `REMOVE_INTERNAL_TAG` | Remove internal tag | the same | `value: ""` | Remove internal tag `value` |
| `SET_STATUS` | Hold the order | none | `value: NOT_FULFILLABLE` | Hold the order |
| `COPY_FIELD` | Copy field | `source`: field menu; `target`: text, "Target column" | first field, `""` | Copy `source` to `target` |
| `CALCULATE` | Calculate | `field1`: field menu; `operation`: menu (plus, minus, times, divided by); `field2`: field menu; `target`: text, "Result column" | first field twice, `add`, `""` | Calculate `field1 + field2` into `target` |
| `ALERT_NOTIFICATION` | Log an alert | `message`: text, "Alert message"; `severity`: menu (Info, Warning, Error) | `""`, `info` | Log an alert `message` |
| `ADD_PRODUCT` | Add bonus line | `sku`: text, "Product SKU"; `quantity`: numeric text | `""`, `1` | Add bonus line `sku ×quantity` |
| `ADD_TAG`, `ADD_ORDER_TAG` | Add status note (retired) | `value`: text, "Value" | not offered | Add status note `value` |
| `SET_MULTI_TAGS` | Add status notes (retired) | `value`: text, "TAG1, TAG2, TAG3" | not offered | Add status notes `value` |
| Any other | The stored type | none | not offered | The stored type |

The type menu offers `ACTION_TYPES`. A row that holds another type lists it too, on that row only.
The configured tags are every tag in the tag categories, sorted, as today (`_normalize_tag_categories`).
The summary's operation signs are `+`, `−`, `×`, `÷`.

`quantity` is stored as an `int` when the text is a whole number from 1 to 9999, else as typed.

Under an action row:

| | Text | Blocks Save |
|---|---|---|
| `ADD_PRODUCT` with a quantity that is not a whole number from 1 to 9999 | Type a whole number from 1 to 9999. | Yes |
| `SET_STATUS` | Holds every line of the order and returns its stock. | No, a hint |
| `ADD_TAG`, `ADD_ORDER_TAG` | Writes the Status_Note text, not a tag. Use Add internal tag for a real tag. | No |
| `SET_MULTI_TAGS` | Writes the Status_Note text, not tags. Use one Add internal tag per tag. | No |
| Any other unknown type | This version does not know this action, so it does nothing. | No |

A field menu whose stored value is not offered lists it first, marked "Not available", and keeps it.
A condition's field menu does the same, but leaves the mark off when there is no analysis and the field is
not an order field: it may be a client's own column.

### 4.6 Blockers and `validate()`

- `blocker()`: `Fix rule “{name}”` for the first rule in list order with a row that blocks Save (`Fix rule
  {num}` when it has no name). The footer then reads "Fix rule “sizes” in Rules to save."
- `blocker_key()`: that control's `data-key`.
- `validate()`: every blocking row, as `Rule “{name}”, step {s}, condition {c}: {message}` (today's
  sentence) or `…, action {a}: {message}`.

### 4.7 `view()`: the state

```python
{
  "page": "rules", "title": "Rules",
  "subtitle": "Change orders at the end of each analysis. Rules run top to bottom.",
  "action": "Add rule",             # "" when there is no rule: the empty state has the button
  "rules": {
    "empty": {"title": "No rules yet", "action": "Add rule",
              "text": "Rules change orders at the end of each analysis, e.g. tag VIP orders."} | None,
    "filter": "", "filter_placeholder": "Filter by name", "filtering": False,
    "count": "3 rules · 2 on", "no_hits": "",
    "groups": [{
      "level": "article", "label": "Article rules", "note": "Check one order line at a time.",
      "rows": [{
        "uid": "4", "num": "01", "name": "VIP priority", "on": True, "open": False,
        "label": "VIP priority",                           # "Unnamed rule" for a rule with no name
        "switch_title": "Turn off", "badge": "",          # "Off"
        "can_up": False, "can_down": True, "can_drag": True, "move_title": "",
        "can_test": True, "test_title": "",
        "summary": [{"label": "When", "parts": [{"t": "bold", "v": "Tags"}, {"t": "text", "v": "contains"},
                                                 {"t": "chip", "v": "VIP"}]},
                    {"label": "Then", "parts": [...]}],
        "wide_labels": False,                              # a rule with two or more steps
        "problem": "",
        "editor": None,                                    # the open rule only: see below
      }],
    }],
  },
}
```

`label` and `note` are `""` on both groups unless the client has rules of both levels. A summary part's `t`
is `text`, `bold`, `chip`, `join` ("and", "or") or `muted`.

The open rule's `editor`:

```python
{
  "level": {"options": [{"value": "article", "label": "Article", "checked": True},
                        {"value": "order", "label": "Order", "checked": False}],
            "hint": "Checks one order line at a time."},
  "field_groups": [{"label": "Common fields", "fields": ["Order_Number", ...]}],
  "operators": [...],                                      # CONDITION_OPERATORS
  "action_types": [{"value": "ADD_INTERNAL_TAG", "label": "Add internal tag"}, ...],
  "steps": [{
    "title": "", "note": "", "removable": False,           # "Step 2" and its note with two or more steps
    "match": {"show": False, "options": [{"value": "ALL", "label": "All", "checked": True},
                                         {"value": "ANY", "label": "Any", "checked": False}],
              "tail": "of these match"},
    "conditions": [{"field": "Tags", "extra_field": None, "field_invalid": False,
                    "operator": "contains", "extra_operator": None,
                    "value": {"kind": "text", "text": "VIP", "placeholder": "Value", "suggestions": []},
                    "problem": "", "hint": "", "invalid": False}],
    "actions": [{"type": "ADD_INTERNAL_TAG", "label": "Add internal tag", "extra_type": None,
                 "params": [{"name": "value", "kind": "suggest", "value": "priority",
                             "placeholder": "Tag", "options": ["FRAGILE", "GIFT"], "lead": "",
                             "extra": None, "invalid": False}],
                 "problem": "", "hint": ""}],
  }],
}
```

A parameter's `kind` is `text`, `suggest`, `number`, `field` (a menu of the article fields) or `choice` (a
menu of `options`, each `{"value", "label"}`). `lead` is a word or sign drawn before it: `→`, `×` or `""`.
`extra_type` is `{"value", "label"}` for a row holding a type the menu does not offer. In the same way
`extra_field` is `{"value", "note"}` for a condition whose field the level does not offer (`note` is "Not
available" or `""`), `extra_operator` is the stored operator when it is not a known one, and a field
parameter's `extra` is its stored value when the menu does not offer it. `field_invalid` is true when the
engine cannot read the field; `invalid` on a condition or a parameter is true when its value blocks Save.

### 4.8 The sentences

| Where | Text |
|---|---|
| Subtitle | Change orders at the end of each analysis. Rules run top to bottom. |
| Empty state | No rules yet / Rules change orders at the end of each analysis, e.g. tag VIP orders. / Add rule |
| Count | {n} rules · {m} on (1 rule · 1 on) |
| A rule with no name | Unnamed rule (the row's name and the switch's label; the stored name stays empty) |
| No hits | No rules named “{filter}”. |
| Group, article | Article rules / Check one order line at a time. |
| Group, order | Order rules / Check the whole order. Run after every article rule. |
| Switch title | Turn off / Turn on |
| Grip title | Drag to reorder (with a filter on: Clear the filter to reorder) |
| Up, down titles | Move up / Move down (with a filter on: Clear the filter to reorder) |
| "…" title | Edit, duplicate, delete |
| "…" menu | Edit (Close editor, on the open rule) / Duplicate / Delete |
| Test…, no analysis | Run an analysis first. Test needs its orders. |
| Test…, no condition | Add a condition first. |
| Test…, a blocking row | Fix the marked value first. |
| Summary, no condition | No condition yet, so this rule never matches. |
| Summary, no action | No action yet. |
| Summary labels | When / Then; from step 2 on: And when / Then |
| Collapsed row's problem | Step {s}, condition {c}: {message} (with one step: Condition {c}: {message}); the same for an action |
| Level hint, article | Checks one order line at a time. |
| Level hint, order | Checks the whole order. Runs after every article rule. |
| Step note, article | Checks only the lines step {n-1} matched. |
| Step note, order | Runs only if step {n-1} matched. |
| Editor buttons | Add condition / Add action / Add step / Remove step / Done |

## 5. The page (`gui/web/settings_rules.js`, `settings.css`)

### 5.1 The list

One card. Its first line: the filter (kit `.input`, 260px, a magnifier glyph), then the count on the right
in `--text-secondary`. With rules of both levels, each group starts with a label line: the label in 9pt bold
secondary, then its note in secondary.

A row is the mockup's grid with the kit's switch in it, `20px 32px minmax(0, 1fr) auto` (the mockup's
switch is 28px, the kit's 32px), gap 12px, padding `12px 16px`, a `--border-subtle` rule above it:

- the grip: six dots, `--text-disabled`, `--text-secondary` on hover;
- the switch: kit `.switch`, `role="switch"`;
- the text: the number in 9pt mono secondary, the name in bold (a button that opens the editor), the "Off"
  badge (`.badge.neutral`); under them one summary line per When and Then. A summary's label column is 36px,
  60px on a rule with steps. A chip is 22px, mono, `--surface-raised`, `--border`, radius 6px. A chip
  longer than its line is cut with an ellipsis and carries the whole value as its title;
- the actions: Test… (`.btn.secondary.compact`, 9pt bold), up, down and "…" (24px ghost icon buttons in
  `--text-secondary`). A move button at its group's edge only greys: no dashed box.

A rule that is off draws its name and its summary in `--text-secondary`.

A collapsed row with a blocking problem shows it under the summary as a `.problem` line.

Numbers run from 01 across both groups and do not change under a filter. No hits: one line, "No rules named
“x”.". The open rule is always listed.

**Empty.** The kit's `.state` in a card: the mockup's glyph in a 40px raised tile, "No rules yet", the
sentence (max-width 360px), and a primary "Add rule" with the plus glyph. The page head has no action then.

### 5.2 Opening a rule

Clicking the name, or Edit in the "…" menu, opens the row. The name becomes a field in the head line, and
the summary gives way to the editor, which spans the text and action columns. Done, or Close editor in the
menu, or opening another rule closes it. Add rule opens the new rule with its name focused and selected.
Rules open collapsed when the dialog opens.

### 5.3 The editor

The editor is the summary with its words turned into controls: the same When and Then labels, in the same
column, with fields where the chips were.

```
(●) 02 [Heavy parcels                 ]                [Test…] ↑ ↓ ⋯
       Level  [ Article | Order ]   Checks the whole order. Runs after every article rule.
       When   [ All | Any ] of these match
              [total_quantity     ▾] [is greater than ▾] [20         ]  ✕
              [has_sku            ▾] [equals          ▾] [GIFT       ]  ✕
              + Add condition
       Then   [Add internal tag ▾] [heavy                ]              ✕
              + Add action
       + Add step                                                 [Done]
```

- Lines are a grid `44px minmax(0, 1fr)`: the label in 9pt bold secondary, then the content. 12px between
  lines, 6px between rows inside one.
- **Level:** kit `.segmented`, two segments, with its hint beside it.
- **Match:** a `.segmented` All / Any followed by "of these match". Drawn only with two or more conditions.
- **A condition row:** grid `minmax(140px, 220px) 180px minmax(0, 1fr) 28px`: the field (`.select`), the
  operator (`.select`), the value control, a ghost ✕ ("Remove condition"). The line of §4.4 sits under the
  row. A blocking value has `.invalid`. A field or operator that is kept but not offered has `.invalid` too.
- **The field menu** is grouped with `.menu-group` labels, 280px tall at most. A stored field the level does
  not offer is listed first with the hint "Not available". The operator menu is flat.
- **An action row:** the type (`.select`, 190px) and its parameters on a wrapping line, and a ghost ✕
  ("Remove action") in its own 28px column at the right, level with the type. The line of §4.5 sits under
  the row.
- **Suggestions** are an `<input list>` with a `<datalist>`; any text can be typed. **Dates** are an
  `<input type="date">`. Both popups are Chromium's own, themed by `color-scheme` (§8).
- **Steps.** With one step there is no step heading. With two or more, each step starts with a rule
  (`--border-subtle`), "Step {n}" in bold, its note in secondary, and from step 2 a ghost "Remove step" at
  the right.
- **Foot:** "Add step" (ghost, plus glyph) on the left, "Done" (secondary) on the right.

### 5.4 Test…

Disabled, with the sentence of §4.8 as its title, when there is no analysis, the rule has no condition in
any step, or it has a blocking row. Otherwise it calls `bridge.testRule(uid)`.

### 5.5 Reordering

- **Up and down** send `rule_move`. Each is disabled at its group's edge.
- **Dragging the grip.** `pointerdown` on a grip starts a drag when no filter is on and the group has more
  than one rule. While the pointer moves, the row under it shows a 2px `--focus-ring` line at the gap the
  rule would land in, among the rows of its own group only; the dragged row has the `--selection-bg` fill.
  Near the scroller's top or bottom edge (40px) the list scrolls. `pointerup` sends `rule_move_to` when the
  position changed. Esc, `pointercancel` or a new state arriving ends the drag with no edit.
- The grip is not focusable: the buttons are the keyboard's way.
- With a filter on, the grip and both buttons are disabled and titled "Clear the filter to reorder".

### 5.6 Menus, keyboard and focus

Phase 7's rules hold (§5.7 there): one menu at a time, Esc closes it and returns focus to its opener, Up and
Down walk it, Left and Right move between segments, a text field reports every `input`, and a render gives
focus back by `data-key`.

Keys: `rule-add`, `rules-filter`, `rule-{uid}` (the row), `rule-{uid}-switch`, `-name`, `-test`, `-up`,
`-down`, `-menu`, `-menu-edit`, `-menu-duplicate`, `-menu-delete`, `-level-{level}`, `-done`, `-step-add`,
`-s{s}-remove`, `-s{s}-match-{ALL|ANY}`, `-s{s}-cond-add`, `-s{s}-c{c}-field`, `-s{s}-c{c}-op`,
`-s{s}-c{c}-value`, `-s{s}-c{c}-remove`, `-s{s}-action-add`, `-s{s}-a{a}-type`, `-s{s}-a{a}-{param}`,
`-s{s}-a{a}-remove`; `test-x`, `test-close`.

Focus after an edit: Add condition and Add action focus the new row's first control; a removed row hands
focus to its step's Add button; a deleted rule hands it to the filter.

### 5.7 Small windows

At the dialog's minimum the page column is about 812px wide. The condition grid fits; the value shrinks. An
action's parameters wrap onto a second line (Calculate has four). The Test panel is 580px wide, or the
viewport less 32px.

## 6. Test rule

### 6.1 `run_rule_test(rule, df, session, limit=5) -> dict` (`gui/settings/rule_test.py`)

1. Copies `df`, builds `RuleEngine([rule])` and applies it. `df` is not changed.
2. Orders are the distinct `Order_Number` values in frame order (the row label when the frame has no such
   column). An order matches when `engine.matched_rows` is true on any of its lines.
3. For each of the first `limit` matched orders:
   - **Matched on:** one part per distinct condition field of the rule, in rule order, joined by " · ".
     A column: `{field}: {values}`, the distinct values over the order's matched lines (every line of the
     order on an order rule), joined by "; " (a value can hold commas), at most three, then "…"; an empty
     one reads "empty". A numeric order field
     (`item_count`, `total_quantity`, `unique_sku_count`, `max_quantity`, `order_volumetric_weight`): the
     number the engine computes. The other order fields (`has_sku`, `has_product`, `all_no_packaging`,
     `order_min_box`): the condition's own value. A field that is neither is left out.
   - **Change:** from the order's lines before and after, joined by ", ": `+ {tag}` and `− {tag}` for
     `Internal_Tags`; `Held` when `Order_Fulfillment_Status` became `NOT_FULFILLABLE`; `{column} → {value}`
     for any other column that changed or was created (`System_note` is left out: it carries the hold's
     reason code); `+ {SKU} ×{quantity}` for each line the rule added. Nothing: "No change".
4. Cell text comes from `gui.pandas_model.cell_display_text`.

### 6.2 The host

`SettingsWebHost(drafts, analysis_df=None, session="")`.

- `testRequested(uid)`: asks the draft for `test_config(uid)`; `None` is ignored. It shows `running_view`,
  then starts a `Worker` that returns `(token, view)`. The call inside the worker catches and logs any
  exception and returns `failed_view`, so only the `result` signal is connected, to a bound method.
- A result whose token is not the current one is dropped: the panel was closed, or another test started.
- `testClosed`, `show_page` and a new test each end the current one.
- `_push` sends `draft.view()` plus `"test"` when a panel is open.
- `focus_problem(key)` first applies `reveal`, pushes if that changed anything, then emits
  `problemFocusRequested`.

### 6.3 `state["test"]`

```python
{
  "status": "running" | "done" | "failed",
  "uid": "4",
  "title": "Test “VIP priority”",
  "intro": {"lead": "Runs this rule, as edited, against the analysis in ", "session": "2026-09-30_1",
            "tail": ". Orders aren’t changed."},
  "message": "Testing 312 orders…",        # running; failed: "The rule test didn’t finish. Details are in Logs."
  "matched": "14", "total": "of 312 orders match",
  "heads": ["Order", "Matched on", "Change"],
  "rows": [{"order": "#10482", "why": "Tags: VIP, repeat", "change": "+ priority", "changed": True}],
  "more": "and 9 more", "empty": "", "note": "",
}
```

With no session name the intro reads "…against the last analysis. Orders aren’t changed." with `session`
`""`. `total` reads "of 1 order matches" for one order. `empty` is "No order in this analysis matches."
when none does. `note` is "No change: the analysis already has the saved rules applied." when a listed row
reads "No change".

### 6.4 The panel

A `--scrim` backdrop fixed over the page area, and on it the mockup's panel: 580px, `--surface`,
`--card-border`, radius 12px, `--overlay-shadow`.

- Head, 48px: the title in 12pt bold, a ghost ✕.
- Body, 16px padding, 12px gap: the intro in secondary with the session in mono; then, when done, the count
  (the number in 14pt bold mono, then the rest) and the table: a `--border` box, radius 8px, a head row on
  `--surface-raised` in 9pt bold secondary, rows on the grid `90px minmax(0, 1fr) 150px` with a
  `--border-subtle` rule above each. Order is mono bold; Matched on is mono, one line, ellipsis; Change is
  mono in `--status-success`, or secondary when it reads "No change", one line, ellipsis, with the whole
  text as its title. Then "and N more" in secondary, and
  the note.
- Running: the message in secondary in place of the count and the table. Failed: a `.problem` line.
- Foot: a `--border-subtle` rule and Close (secondary) on the right.

The page under the panel is `inert`. Opening the panel focuses Close; closing it returns focus to the
rule's Test…. Esc closes it. A click on the backdrop does nothing.

## 7. The engine (`shopify_tool/rules.py`)

`RuleEngine.__init__` drops every rule whose `enabled` is `False` before it normalises and sorts the rest,
and logs how many it skipped. `execution_order` is unchanged: the draft orders every rule with it, off or
not. Nothing else reads the flag.

## 8. The theme (`shared/theme.py`)

- **`scrim`**: `"rgba(0,0,0,0.35)"` in both themes, the mockup's value. A CSS value, registered in
  `_CSS_VALUE_FIELDS` beside the shadows, so it reaches the web tier as `--scrim` and is checked the way
  they are.
- **`--color-scheme`**: `light` or `dark`, the theme's name, emitted by `theme_css_vars` with the derived
  variables. `settings.css` sets `color-scheme: var(--color-scheme)` on `#settings`, so the date picker and
  the suggestion list follow the theme. No other page opts in.

## 9. Errors

| What fails | What the operator sees |
|---|---|
| A value Save refuses | The line under its row, the same line on the collapsed row, the nav mark, the footer's link, Save disabled |
| A field, operator or date the engine cannot use | The line under its row. Save is not blocked: the rule is kept as written |
| The test raises | The panel: "The rule test didn’t finish. Details are in Logs." Logged with its traceback |
| No analysis | Test… disabled, with why as its title |
| An edit the draft does not know | Dropped, logged at debug level (phase 7's rule) |

## 10. Departures from the mockup

| Mockup | Built | Why |
|---|---|---|
| One list that runs top to bottom | Two labelled groups when a client has rules of both levels | Article rules always run before order rules |
| Up and down move through the whole list | They stop at the group's edge; so does a drag | The same |
| An off row's summary at 60 % opacity | Its name and summary in `--text-secondary` | The web tier may not use `opacity` (ADR 0001) |
| Field names like "Tags", "Total weight", "Country" | The analysis's own names: `Shipping_Provider`, `item_count` | The mockup's are sample data. A rule reads a column, and the name has to say which |
| "Set courier to", "Set status to On hold" | The seven real actions under plain labels (§4.5). The status action is "Hold the order" | A rule can only hold an order |
| "Change orders after the analysis." | "…at the end of each analysis." | Rules run inside the run, after stock is allocated |
| The filter and reordering together | Up, down and the grip are disabled while a filter is on | A move among hidden rows cannot be seen |
| A new rule is pre-filled with a VIP condition | It has one empty step | The mockup's is sample data |
| The Test panel dims the whole dialog | It dims the page area | The nav and the footer are Qt until phase 10. Picking another page closes the panel |
| "…the analysis in 2026-09-30_1" | The same, or "the last analysis" with no session name | |
| Change always shows a change | "No change", and a line saying why | The analysis already has the saved rules applied |
| The mockup does not draw the editor | §5.3 | Owner's decision (§2) |

## 11. What changes from today's page, on purpose

| Today | Phase 8 | Why |
|---|---|---|
| An "equals" value the analysis does not hold, a Copy field source or an operator the menu does not list is replaced on the next save | It is kept, and marked | A quiet data loss |
| A date the page cannot read becomes today's date | It is kept, with "Pick a date" under it | The same |
| A lowercase `match` (`"any"`) is saved as `ALL` | It loads as the engine reads it | The same |
| An action's extra keys (`product_name`) are dropped on save | Kept | The same |
| Changing a condition's field or operator clears its value | The value is kept unless the operator takes another kind of value | Fewer retypes |
| A regex is checked 500 ms after typing stops | On every keystroke | The check is cheap; there is no widget to rebuild |
| The value menu lists every value of the column | A text field with at most 200 suggestions | A menu of ten thousand order numbers is no menu |
| Test: a 100-line sample, counted in lines | The whole analysis, counted in orders | Owner's decision |
| Delete Rule is a red button on every card | Delete is in the "…" menu | The mockup |

Unchanged: the vocabularies; the level's field lists; what blocks Save; the retired actions round-trip and
are flagged; `SET_STATUS` always holds; the list is in run order; a move stays inside its level.

## 12. Tests (test-first; the seams)

| File | Seam | Covers |
|---|---|---|
| `tests/test_rules.py` | `RuleEngine` | A rule that is off is skipped; missing and `True` run; `execution_order` still lists it |
| `tests/test_theme_palette.py`, `test_theme_css_vars.py` | The theme | `scrim` in both themes and as `--scrim`; `--color-scheme` |
| `tests/test_settings_draft_rules.py` (new) | `RulesDraft`, no widget | Loading (run order, the old format, `match` case, the three normalised actions, kept unknowns); every action of §3.3, the dropped ones included; `collect()` round-trips the fixture config and writes `enabled` only when off; `snapshot()` ignores filter and open; fields per level; resolvable; every line of §4.4 and §4.5; `blocker()`, `blocker_key()`, `validate()`; the summary; every sentence of §4.8; moves stay inside the level; `test_config` |
| `tests/test_rule_test.py` (new) | `run_rule_test` | The counts; Matched on for a column, a numeric order field and `has_sku`; Change for each action type, a bonus line, and "No change" on an already-tagged order; more than five; none; a rule that is off still runs; the frame is not changed; `running_view`, `failed_view` |
| `tests/test_settings_bridge.py` | `SettingsBridge` | `testRule`, `closeTest` |
| `tests/test_settings_rules_page.py` (new) | The page in a real Chromium, fed views built by the draft | The list row's DOM against the mockup's grid; groups; the empty state; the filter; the switch; up and down; the "…" menu; the editor's controls per operator and per action type; typing keeps focus; a drag by synthetic pointer events sends `rule_move_to`; the Test panel in its three states, `inert`, Esc, focus; both themes read from tokens |
| `tests/test_settings_web_host.py` | `SettingsWebHost`, with the thread pool patched | A test shows running, then the result; a result after Close is dropped; `show_page` closes the panel; a raising test shows the failed view; `focus_problem` reveals |
| `tests/test_settings_rules_window.py` (new), `tests/test_actions_handler.py` | The window | Rules is a draft; its blocker in the footer and its link; the unsaved mark follows a rule edit at once; Save writes a rule that is off; `session_name` reaches the host. The existing window tests (`test_settings_footer.py`, `test_settings_roundtrip.py`, `test_settings_unsaved.py`, `test_settings_nav.py`, `test_settings_entry_points.py`) pass unchanged |
| `tests/audit/test_03_rule_engine.py` | The four tests that used the Qt page or dialog | Rewritten against the draft and `run_rule_test`, same assertions |
| Deleted | | `tests/test_rules_page.py`, `test_settings_page_rules.py`, `test_rule_test_dialog.py`: their cases move to the two new files |

Renders, saved under `docs/design/ui-refresh/renders/phase8/` and looked at before the PR, each the whole
dialog grabbed offscreen: the list with rules of both levels, one off; the empty state; a rule open; a rule
open with a blocking value; a multi-step rule open; the Test panel done; each in light, and the list, the
open rule and the Test panel in dark.

## 13. Docs

- `docs/design/ui-refresh/roadmap.md`: phase 8 as built, with its differences.
- `CONTEXT.md`, Rules: **Off rule** (kept in the profile, skipped by the analysis, still run by a rule
  test) and **Rule test** (one rule, as edited, on a copy of the open session's analysis; it counts orders
  and changes nothing).

## 14. Out of scope

- Undo for Delete. It is two clicks deep, and nothing is written until Save.
- Cancelling a running test. Closing the panel drops its result; the worker finishes by itself.
- A search box inside the field menu.
- Kit-drawn popups for the date picker and the suggestions.
- A drag between the two levels. Level is changed in the editor.
- Sets, Weight, Reports, Tag categories (phase 9) and the web frame (phase 10).

## 15. Delivery

One PR on `dr/20-ui-refresh-phase-8-client-settings-on-th`. Gate:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. The PR says that `shared/`
gains the `scrim` token and the `--color-scheme` variable and that Packing Tool needs no work, and that a PC
on an older version runs a rule that is off until it updates.
