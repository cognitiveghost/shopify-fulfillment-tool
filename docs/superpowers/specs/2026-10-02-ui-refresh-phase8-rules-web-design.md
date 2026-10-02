# UI refresh phase 8: Rules and Test rule on the web tier

**Task:** "UI refresh phase 8: Client settings on the web tier: Rules and Test rule". Brief:
`docs/design/ui-refresh/roadmap.md`, phase 8. Depends on phase 7 (merged, #361).
**Path:** architectural. It replaces the largest Qt settings editor (`gui/settings/rules.py`, 1,530 lines) and the
Qt test window (`gui/rule_test_dialog.py`) with a draft, a web page and a pure test runner, and adds an
on/off flag to the stored rule.
**Mockup followed:** `docs/design/ui-refresh/mockups/client-settings.html`, states Rules, Rules empty and Test rule,
both themes. The mockup draws the list and Test only; the rule view (§5.4) is designed here on the page anatomy
phase 7 built. Every departure is in §10.
**Joins:** the settings document phase 7 built. Its spec (`2026-10-02-ui-refresh-phase7-settings-web-design.md`)
holds the page contract, the draft pattern, the wire rules, the footer, Save and the close guard; this spec only
adds to them. Read it first. Baseline on a clean checkout of `origin/main` (62bc88e), measured 2026-10-02 in the cloud
session: 3190 passed, 0 failed; `ruff check .` clean.

## 1. What this task delivers

1. Rules as a fourth page of the settings document: a list (§5.2), an empty state (§5.3), a rule view that edits
   one rule (§5.4), and Test rule as a dialog drawn in the page (§5.5).
2. `RulesDraft` (`gui/settings/rules_draft.py`), which holds the rules, takes every edit, and words every
   sentence the page draws (§4).
3. `run_rule_test` (`gui/settings/rule_test.py`), a pure function that runs one rule against the analysis and
   words the result (§6), called on a worker by the web host.
4. An on/off switch per rule, stored as `"enabled": false` and honoured by the engine (§3.3).
5. Reordering by drag and by arrows, inside a level (§5.2.3).
6. One new theme token, `scrim` (§5.5). `shared/` changes: Packing Tool gets it at its next sync and needs no work.
7. Deleted: `gui/settings/rules.py`, `gui/rule_test_dialog.py`, and the Qt-only tests for them (§9).
8. Docs: roadmap (phase 8 as built), `CONTEXT.md` (§11).

Sets, Weight, Reports and Tag categories keep their Qt widgets.

## 2. Owner's decisions (2026-10-02)

| Question | Answer |
|---|---|
| Where a rule is edited (the mockup's ⋯ menu says "Edit, duplicate, delete" but draws no editor) | A rule view: Edit replaces the list with one rule's page, and a Back link returns to the list |
| How the list shows that every article rule runs before every order rule | Two titled groups in one card, Article rules then Order rules, numbered within each; moving stays inside the group |
| Drag to reorder | Built, as well as the up and down arrows |
| One PR or two | One PR. The plan puts Test rule last |

**What the code does that the mockup does not know** (the facts behind the design):

- `RuleEngine.execution_order` runs every article rule before every order rule; within a level, by `priority`.
  The Qt page lists rules in that order and saves `priority` as list position + 1. Up/down skips to the nearest
  rule of the same level.
- A stored rule is `{name, priority, level, steps: [{match, conditions: [{field, operator, value}],
  actions: [{type, ...}]}]}`. An old rule has `conditions`/`match`/`actions` at its root and no `steps`.
- A step with no conditions matches nothing, on either level (`rules.py`, both evaluators).
- Rules have no on/off flag today. Nothing but `core.py` (one `RuleEngine(rules)` call) and the test dialog runs
  them.
- `condition_error` (`gui/rule_validator.py`) is the one check Save refuses today: regex, range, list and
  numeric values. A date was never checked, because a `QDateEdit` cannot hold a bad one.
- A condition whose field the engine cannot resolve is flagged red but saved ("will never match").
- The test dialog runs the rule on about 100 rows cut at an order boundary, and says the analysis "already has
  your saved rules applied".
- Three action types are retired but still run (`LEGACY_ACTION_TYPES`); a rule using one round-trips and is
  flagged.

## 3. Architecture

```
SettingsWindow (QDialog, Qt frame)
 └─ page stack
     ├─ SettingsWebHost ── one QWebEngineView   General, Orders mapping, Stock mapping, Rules
     └─ ReportsPage, SetsPage, WeightPage, _TagCategoriesPage   unchanged

RulesDraft.view() ──► SettingsBridge.state ──► settings.js render()
settings.js ──► bridge.edit(action, args) ──► RulesDraft.apply() ──► push, host.edited
settings.js ──► bridge.testRule(id) ──► host: Worker(run_rule_test) ──► draft.set_test(result) ──► push
```

- Everything phase 7 says about drafts holds: the draft imports no Qt, owns every value and every sentence, and
  `view()` is the whole state. The page's own state is which menu is open, the drag in progress and the
  filter text (§5.2.4).
- **Which view shows** (list or one rule) and the Test dialog's state are the draft's, not the page's, because
  Python words them. They are not values: `snapshot()` leaves them out.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/settings/rules_draft.py` (new) | `RulesDraft`, the action and operator vocabularies' labels, every sentence of §4.6. No Qt import |
| `gui/settings/rule_test.py` (new) | `run_rule_test(rule, df, session) -> dict` and the frame alignment moved from the Qt dialog (§6). No Qt import |
| `gui/settings/vocab.py` (new) | `CONDITION_OPERATORS`, `ACTION_TYPES`, `LEGACY_ACTION_TYPES`, moved from `fields.py`, which re-exports them. No Qt import |
| `gui/settings/contract.py` | `reveal(key) -> bool`, default False (§4.5) |
| `gui/settings/bridge.py` | Two slots and one signal (§3.2) |
| `gui/settings/web_host.py` | `reveal` before `focus_problem`; the Test worker (§7) |
| `gui/settings/window.py` | Builds `RulesDraft`; `"Rules": "rules"` in `WEB_PAGE_KEYS`; takes `session_name` |
| `gui/actions_handler.py` | Passes `session_name` (the open session folder's name, or `None`) |
| `gui/web/settings.js`, `settings.css` | The Rules page (§5) |
| `gui/web/kit.css`, `tests/web/kit_sheet.html` | `.dialog` and `.drop-line` (§5.6) |
| `gui/rule_validator.py` | `condition_error` checks the three date operators (§4.4) |
| `shopify_tool/rules.py` | `RuleEngine.__init__` drops rules whose `enabled` is `False` (§3.3) |
| `shared/theme.py` | The `scrim` token, a CSS value in both themes (§5.5) |
| `CONTEXT.md` | §11 |
| Deleted | `gui/settings/rules.py`, `gui/rule_test_dialog.py` |

`gui/settings/fields.py` keeps `CONDITION_OPERATORS`, `ACTION_TYPES` and `LEGACY_ACTION_TYPES`; the draft imports
them from there (that module imports Qt widgets, so the draft imports the three lists only through a new Qt-free
module: move the three lists to `gui/settings/vocab.py` and re-export them from `fields.py`, so every existing
import keeps working).

### 3.2 `SettingsBridge` additions

Add each member to the phase 7 spec's catalogue (§3.3 there) and to this table before the code.

| member | direction | meaning |
|---|---|---|
| `testRule(id)` → `testRequested(str)` | JS → Python | Run Test on the rule with this id (§4.1) |
| `closeTest()` → `testClosed()` | JS → Python | The Test dialog's Close, ✕ or Esc |

Every rule edit goes through the existing `edit(action, args)`.

### 3.3 The on/off flag

- Stored on the rule: `"enabled": false` when off. Turning a rule on removes the key, unless the stored rule
  carried `"enabled": true`, which is then kept as `true`. A rule opened and saved untouched is written back
  as it was read (the round-trip test's promise).
- `RuleEngine.__init__` drops every rule whose `enabled` is `False` (exactly `False`; a missing key is on)
  before normalising, and logs how many it dropped at info level. One place, so the analysis and any other
  caller agree.
- Test runs the rule as edited **with the key removed**: testing an off rule shows what it would do when on.

## 4. `RulesDraft(rules, analysis_df, tag_categories, client, session)`

`rules` is the live `config_data["rules"]` list. `analysis_df` may be empty. `session` is the session's folder
name or `None`.

### 4.1 What it holds

- `self._rules`: the stored rule dicts in `execution_order`, each normalised to `steps` (an old rule's root
  `conditions`/`match`/`actions` move into `steps[0]` and the root keys are removed, as the Qt page did). Every
  other key a rule carries is kept and written back: edits change dicts in place.
- An id per rule: `"r1"`, `"r2"`, … in load order, then new ones counting on. Ids are the page's handle on a
  rule across reorders; they are never saved. Held in a parallel list, not in the dict.
- `self.open`: the id of the rule the rule view shows, or `None` for the list.
- `self.test`: the Test dialog's state (§4.7), or `None`.
- `fields(level)`: today's `get_available_rule_fields` (order-level fields, then the common article fields, then
  every other analysis column not starting `_`), as `[(group label, [field, …]), …]`.
- `values(field)`: `get_unique_column_values(analysis_df, field)`, first 200. Computed when a value menu is
  open only (§5.4.3).
- `tags`: today's `get_configured_tags` over `tag_categories`.

`collect()` writes `config_data["rules"]` **in place** (clear and refill the live list) with each rule's
`priority` set to its position + 1 across the whole list, article rules first. `snapshot()` is
`json.dumps(collect())` over the rules alone. `mark_clean` and the rest are the contract's.

### 4.2 The edit actions

Same rules as phase 7 §3.4: strings and booleans only, a wrong shape or an unknown value is dropped and returns
False, an index travels as a string. `id` is a rule id; `s`, `c`, `a` are step, condition and action indexes.

| action | args | effect |
|---|---|---|
| `rule_add` | `[]` | Appends `{"name": "New rule", "level": "article", "steps": [{"match": "ALL", "conditions": [], "actions": []}]}` to the article group and opens it |
| `rule_open` | `[id]` | Shows the rule view for `id` |
| `rule_close` | `[]` | Back to the list. Returns True (the view changed) |
| `rule_toggle` | `[id, on]` | §3.3 |
| `rule_move` | `[id, to]` | `to` is the target position **inside the rule's level group** (`"0"` first). Drag and the arrows both send it |
| `rule_duplicate` | `[id]` | A deep copy named `{name} (copy)`, `enabled` kept, placed right after the original. Stays on the list |
| `rule_delete` | `[id]` | Removed. From the rule view, back to the list. No confirm: Cancel and the close guard undo it |
| `rule_name` | `[id, text]` | Kept as typed |
| `rule_level` | `[id, level]` | `"article"` or `"order"`. Moves the rule to the end of the other group. Conditions keep their fields, whatever the new level offers (§4.4 flags them) |
| `step_add` | `[id]` | Appends an empty step |
| `step_remove` | `[id, s]` | Not step 0 |
| `step_match` | `[id, s, match]` | `"ALL"` or `"ANY"` |
| `cond_add` | `[id, s]` | `{"field": first field of the level, "operator": "equals", "value": ""}` |
| `cond_field` | `[id, s, c, field]` | Any string: a stored field the list lacks stays choosable (§5.4.3) |
| `cond_operator` | `[id, s, c, op]` | One of `CONDITION_OPERATORS`. A valueless operator (`is empty`, `is not empty`) sets `value` to `""` |
| `cond_value` | `[id, s, c, text]` | Kept as typed |
| `cond_remove` | `[id, s, c]` | |
| `act_add` | `[id, s]` | `{"type": "ADD_INTERNAL_TAG", "value": ""}` |
| `act_type` | `[id, s, a, type]` | One of `ACTION_TYPES`, or the row's own stored type. Replaces the action with that type's defaults (§4.3) |
| `act_param` | `[id, s, a, name, text]` | `name` is one of the type's parameters (§4.3). Kept as typed; `quantity` is converted on collect |
| `act_remove` | `[id, s, a]` | |
| `values_for` | `[id, s, c]` | Fills the rule view's `values` with that condition's column values (first 200) and returns True. Any other edit clears it |

### 4.3 Action types

| type | label in the menu | parameters, in order (name: control) | defaults |
|---|---|---|---|
| `ADD_INTERNAL_TAG` | Add internal tag | `value`: text with a menu of the configured tags | `""` |
| `REMOVE_INTERNAL_TAG` | Remove internal tag | `value`: as above | `""` |
| `SET_STATUS` | Hold the order | none drawn; `value` is always `NOT_FULFILLABLE` | `NOT_FULFILLABLE` |
| `COPY_FIELD` | Copy a field | `source`: field menu; `target`: text | first field, `""` |
| `CALCULATE` | Calculate | `operation`: menu add/subtract/multiply/divide; `field1`, `field2`: field menus; `target`: text | `add`, first field ×2, `""` |
| `ALERT_NOTIFICATION` | Alert | `message`: text; `severity`: segmented info/warning/error | `""`, `info` |
| `ADD_PRODUCT` | Add a product | `sku`: mono text; `quantity`: mono text, whole number 1–9999 | `""`, `"1"` |
| `ADD_TAG`, `ADD_ORDER_TAG`, `SET_MULTI_TAGS` (legacy) | the type as stored | `value` (and `SET_MULTI_TAGS`' stored `tags` list shown joined by `, `, written back as `value`, as today) | not offered for a new row |

A stored action of a type in neither list keeps every key; the row shows its type and no parameters, and the type
menu offers it as the row's own.

`collect()` writes `quantity` as an `int`. A `SET_STATUS` with any other stored value is written as
`NOT_FULFILLABLE`, as today.

### 4.4 Problems and the blocker

A **problem** is shown under its control and blocks the save. A **warning** is shown and does not.

| What | Kind | Sentence |
|---|---|---|
| A rule's name is empty after stripping | problem | Name this rule. |
| `condition_error(op, value)` returns a message | problem | that message |
| A date operator's value that `_parse_date_safe` cannot read (new in `condition_error`) | problem | Type a date: YYYY-MM-DD, DD/MM/YYYY or DD.MM.YYYY. |
| `ADD_PRODUCT` with an empty `sku` | problem | Type the SKU to add. |
| `ADD_PRODUCT` `quantity` not a whole number 1–9999 | problem | Type a whole number from 1 to 9999. |
| A condition's field the level cannot resolve (today's `_check_field_resolvable`, same three branches) | warning | “{field}” isn't available on an {article/order} rule, so this condition never matches. |
| A legacy action type | warning | Writes the Status_Note text column, not tags. Replace it with {one Add internal tag per tag / Add internal tag} to add a real tag. |
| A step with no conditions | warning | A step with no conditions matches nothing. |

`blocker()`: for the first rule (list order) with a problem, `Fix “{name}”` (or `Name rule {n}` where the name
is empty, `n` its number in its group). `blocker_key()`: that problem's control key (§5.7).
`validate()` returns one line per problem, `Rule “{name}”, step {s}, condition {c}: {sentence}` (today's
wording for conditions; `action {a}` for actions; `Rule {n}: Name this rule.` for a name).

### 4.5 `reveal(key)` (added to `PageContract`)

`PageContract.reveal(key) -> bool` returns False. `RulesDraft.reveal(key)` opens the rule a `rule:{id}:…` key
belongs to (sets `open`, closes Test) and returns True when that changed the view. `SettingsWebHost.focus_problem`
calls `drafts[current].reveal(key)` and pushes when it returns True, then emits `problemFocusRequested(key)`;
the page already holds a focus request until the state that draws the control arrives (phase 7 §6.3).

### 4.6 `view()`

The page head, as phase 7 §4.5, then `"rules"`:

```python
"rules": {
    "mode": "list" | "rule" | "empty",
    "count": "3 rules · 2 on",
    "groups": [   # list mode; a group with no rule is left out
        {"level": "article", "title": "Article rules",
         "text": "Run first, on each order line.",
         "rules": [
            {"id": "r1", "num": "01", "name": "VIP priority", "on": True,
             "problem": False,                 # True: the row carries the alert mark
             "steps": [                        # one summary per step
                {"lead": "When",               # "When" for step 1, "Then check" after
                 "conds": [{"join": "", "field": "Tags", "op": "contains", "value": "VIP"}],   # join: "and"/"or"
                 "acts": [{"join": "", "verb": "Add internal tag", "value": "priority"}],
                 "none": ""}],                 # "No conditions" / "No actions", when a side is empty
             "can_up": False, "can_down": True,
             "test": {"enabled": True, "title": ""}},   # title: why it is disabled (§4.7)
         ]},
        {"level": "order", "title": "Order rules", "text": "Run after, on each whole order.", "rules": [...]},
    ],
    "empty": {"title": "No rules yet",
              "text": "Rules change orders after the analysis, e.g. tag VIP orders.",
              "action": "Add rule"},
    "rule": {...},        # rule mode, §5.4
    "test": {...} | None, # §4.7
}
```

`action` in the page head is "Add rule" in list mode, "" in empty and rule modes. The rule view's head is a
breadcrumb, not the page title (§5.4.1): `title` stays "Rules" and `crumb` is the rule's name or "Unnamed rule".

**Summary words.** A field is shown as stored. An operator is shown as stored. A valueless operator has no
value chip. A value longer than 40 characters is cut with "…". An action's verb is its menu label (§4.3); its
value chip is the main parameter: `value`, `target` for Copy and Calculate (`{source} → {target}`,
`{field1} {op} {field2} → {target}`), `message` for Alert, `{sku} × {quantity}` for Add a product, nothing for
Hold the order. Join word: "and" under ALL, "or" under ANY.

**Sentences** (`{client}` is the client id, `{session}` the session name):

| Where | Text |
|---|---|
| Page subtitle | Change orders after the analysis. Rules run top to bottom. |
| Count, list head | `{n} rule(s) · {m} on` |
| Filter placeholder | Filter by name |
| No filter hits | No rules named “{filter}”. (drawn by the page from its own filter text: the one sentence the page words, because the filter is the page's state) |
| Article group | Article rules — Run first, on each order line. |
| Order group | Order rules — Run after, on each whole order. |
| Test disabled, no analysis | Run an analysis first: Test runs the rule against it. |
| Test disabled, no condition | Add a condition to test this rule. |
| Test disabled, a problem | Fix this rule's problems to test it. |
| Rule view, name hint | Shown in the list and in Logs. |
| Rule view, level hint, article | Each order line is checked on its own. Article rules run before order rules. |
| Rule view, level hint, order | The whole order is checked at once, with order fields such as item_count. |
| Step head, step 1 | Step 1 |
| Step head, later | Step {s} — checks what step {s−1} matched (article) / runs only if step {s−1} matched (order) |
| Match line | Run the actions when {all/any} of these are true |
| Off badge | Off |
| Toggle titles | Turn off / Turn on |
| Move titles | Move up / Move down; grip: Drag to reorder |

### 4.7 Test (§6 runs it)

`testRequested(id)` from the page: the host checks `draft.can_test(id)` (an analysis exists, the rule has a
condition and no problem), sets `draft.test = {"id": id, "running": True}`, pushes, and starts the worker on a
deep copy of the rule as edited (`enabled` removed) and `analysis_df`. The result arrives as
`draft.set_test(result)`; an error as `draft.set_test_error()`. A result for a test that was closed, or for another
rule than the one now under test, is dropped (the host keeps a run counter).

```python
"test": {"name": "VIP priority", "running": False,
         "intro": "Runs this rule, as edited, against the analysis in", "session": "2026-09-30_1",
         "outro": ", which already has the saved rules applied. Orders aren't changed.",
         "count": "14", "count_text": "of 312 orders match",
         "rows": [{"order": "#10482", "why": "Tags: VIP, repeat", "change": "+ priority"}],
         "more": "and 9 more",           # "" when every match is listed
         "added": "",                    # "2 lines added" when Add a product added lines
         "empty": "",                    # "No order matches this rule." when count is 0
         "error": ""}                    # "The test didn't finish. Details are in Logs."
```

With no session name, `intro` is "Runs this rule, as edited, against the current analysis" and `session` is "".
While running, the dialog shows "Testing…" in place of the count and rows. The count text is plural-aware:
"1 of 312 orders matches".

## 5. The page

### 5.1 Frame

Phase 7's `.settings-page` column and page head. The Rules page is drawn when `state.rules` is present, by a new
`rulesPage(r)` in `settings.js`; the render's `menuStillOpens` and key rules extend to it.

### 5.2 The list (mode `list`)

One card (`section.card`, `data-card="rules"`).

1. **Card head row**, padding `12px 16px`: a `.input` 260px wide with the search glyph and "Filter by name";
   a spacer; the count in secondary.
2. **A group**: a title row (`.card-head` with "Article rules" and its text), then one row per rule.
3. **A rule row**, grid `20px 32px minmax(0,1fr) auto`, gap 12px, padding `12px 16px`, `--border-subtle` rule
   above, `align-items: start`:
   - the grip (six-dot glyph, `--text-disabled`, `cursor: grab`, title "Drag to reorder");
   - the kit's `.switch` (`role="switch"`, `aria-checked`, title Turn off / Turn on);
   - the body: a line with the number (9pt mono secondary), the name (bold; secondary when off), the Off badge
     (`.badge.neutral`) when off, and the alert glyph in `--status-danger` with the title "Needs attention" when
     `problem`; then one or two summary lines per step: a 36px label ("When" / "Then", 9pt bold secondary), the
     parts separated by the join word in secondary, a field in bold, a value in a `.code` chip (22px, mono). A
     step after the first leads with "Then check". An off rule's summary is drawn in `--text-secondary` (the style
     lint flags `opacity`, so the mockup's 0.6 opacity becomes the secondary colour);
   - the actions: "Test…" (`.btn.secondary.compact`; disabled with its title from §4.6), Move up and Move down
     (`.btn.ghost.compact.icon`, chevron glyphs; disabled at the group's ends), and ⋯ (`.btn.ghost.compact.icon`,
     title "Edit, duplicate, delete") opening a menu: Edit, Duplicate, a separator, Delete (`.menu-item.danger`).
   - A click on the name also opens the rule (it is a `.btn.link`-styled button without the underline).
4. **No filter hits**: a row in secondary, `No rules named “{filter}”.` Filtering hides rows only; the groups'
   titles hide when they have no row showing.

#### 5.2.1 Reordering

- **Arrows** send `rule_move [id, pos±1]` within the group.
- **Keyboard**: Alt+Up / Alt+Down on any control inside a rule row moves it; focus stays on the same control.
- **Drag**: HTML5 drag on the grip only (`draggable="true"` on the grip; the row is the drag image), as
  `gui/web/columns.js` does for columns. While dragging, the page keeps `drag = {id, level}`; a `dragover` on a row
  of the same group sets `data-drop="before|after"` on it by the pointer's half, drawn as a 2px `.drop-line` in
  `--focus-ring` at that edge; a row of the other group shows no line and refuses the drop (`dropEffect =
  "none"`). On `drop`, the page sends `rule_move [id, to]` with `to` worked out from the target row's position in
  its group and the side; dropping on itself sends nothing. `dragend` clears every mark. No transform, no
  transition (style lint).
- While the filter has text, the grip and arrows are disabled (title "Clear the filter to reorder"): a move among
  hidden rows would be invisible.

#### 5.2.2 The page's own state

`view.filter` (the filter text, kept across renders and pages, cleared when the dialog's page changes away from
Rules), `view.drag`, and the open menu (`rule-menu:{id}`).

### 5.3 The empty state (mode `empty`)

One card with the kit's `.state`: a 40px raised tile holding the list glyph (the mockup's path), "No rules yet"
at 12pt bold, the sentence in secondary (max 360px), and "Add rule" as `.btn.primary` with the plus glyph. The
page head has no action.

### 5.4 The rule view (mode `rule`)

`state.rules.rule`:

```python
{"id": "r3", "name": "VIP priority", "name_problem": "", "level": "article",
 "level_hint": str, "levels": [{"value": "article", "label": "Article", "checked": True}, {"value": "order", ...}],
 "on": True, "test": {"enabled": True, "title": ""},
 "steps": [{"title": "Step 1", "can_remove": False, "match": "ALL", "match_text": str, "warning": "",
            "conditions": [{"field": "Tags", "field_missing": False, "operator": "contains",
                            "value": "VIP", "has_value": True, "placeholder": "Value",
                            "value_menu": False,          # True: a menu of the column's values is offered
                            "problem": "", "warning": "", "hint": ""}],   # hint: "3 items" for a list operator
            "actions": [{"type": "ADD_INTERNAL_TAG", "label": "Add internal tag", "legacy": False,
                         "params": [{"name": "value", "kind": "text" | "mono" | "field" | "choice" | "segmented",
                                     "value": "priority", "placeholder": "Tag", "options": [...],
                                     "suggest": True}],   # suggest: the configured tags' menu
                         "problem": "", "warning": ""}]}],
 "fields": [{"group": "Order-level fields", "items": ["item_count", ...]}, ...],   # for the field menus
 "operators": [...],                       # CONDITION_OPERATORS
 "types": [{"value": "ADD_INTERNAL_TAG", "label": "Add internal tag"}, ...],
 "values": {"key": "rule:r3:s0:c1:value", "items": [...]} | None,   # the open value menu's values only
 "tags": [...]}
```

The page asks for a value menu's values with `edit("values_for", [id, s, c])` (§4.2).

#### 5.4.1 Head

The page head reads `Rules › {name}` as a breadcrumb: "Rules" is a `.btn.link` that sends `rule_close`, then a
chevron-right glyph in secondary, then the name in bold. On the right: "Test…" (`.btn.secondary`) and the
on/off `.switch` with its label ("On" / "Off"). Esc with no menu and no dialog open is the dialog's (closes
Settings through the guard), not Back: phase 7's rule that the page leaves Esc alone stands.

#### 5.4.2 The Rule card

`.card-head` "Rule", then `.card-row`s:

- **Name**: a `.field` 320px; hint or problem under it.
- **Level**: a `.segmented` radiogroup Article / Order; the hint under it.

#### 5.4.3 One card per step

`.card-head` with the step's title and, on a later step, "Remove step" (`.btn.ghost.danger.compact`) on the
right. Then:

- **Match line**, a `.card-row` with no label column: "Run the actions when" a `.segmented` All / Any "of these
  are true". With one condition or none the control is still shown.
- **When** section label (9pt bold secondary, padding `8px 16px 0`), then one row per condition on the grid
  `200px 180px minmax(0,1fr) 28px`, gap 8px, padding `6px 16px`:
  - field: a `.select` (mono value) opening a menu of the level's fields under their group labels
    (`.menu-group`), max 280px tall; a stored field the list lacks is listed first with the hint "Not available
    on this level" and the select is `.invalid`-edged only when the warning applies;
  - operator: a `.select` opening the operators;
  - value: a `.field` (mono for regex, list and range operators; placeholder per operator as today: "Value",
    "Value1, Value2, Value3", "10-100", "^SKU-\d{4}$", "YYYY-MM-DD" for the date operators). When `value_menu`
    is true, the field sits in a `.menu-anchor` with a chevron button at its right edge that opens the column's
    values (`values_for`), picking one sets the value. A valueless operator draws no field;
  - remove: `.btn.ghost.compact.icon` with ✕, title "Remove condition".
  - Under the row (grid columns 1–3): the problem, else the warning (`--status-warning` with the alert glyph),
    else the hint ("{n} items" for a list operator, worded by the draft).
  - "Add condition" (`.btn.secondary.compact`, plus glyph), padding `8px 16px`.
- **Then** section label, then one row per action on the grid `200px minmax(0,1fr) 28px`: the type `.select`,
  then the parameters on one line (wrapping) in the order of §4.3, separated by an arrow-right glyph where the
  Qt page had "→", and a "Qty" label before quantity; then remove. Problem or warning under it. "Add action".
- The step's warning (no conditions) sits under the When section in `--status-warning`.

After the last step card: "Add step" (`.btn.secondary`, plus glyph), left-aligned. Then, at the end of the
column, "Delete rule" (`.btn.ghost.danger`), right-aligned.

`data-key`s (§5.7) make every control findable. The render keeps focus and caret as phase 7's `morph` does.

### 5.5 Test rule (a dialog drawn in the page)

When `state.rules.test` is set, the page draws, after the column, a `.dialog-scrim` (fixed, inset 0,
`background: var(--scrim)`, grid centring, z-index above menus) holding a `.dialog` 580px wide:

- head, 48px, `--border-subtle` rule under it: "Test “{name}”" 12pt bold, and a ghost ✕ titled "Close";
- body, padding 16px, gap 12px: the intro sentence in secondary with the session in mono `--text`; the count at
  14pt bold mono and the count text beside it; a bordered table (radius 8px): a header row on `--surface-raised`
  (Order, Matched on, Change; 9pt bold secondary) on the grid `90px minmax(0,1fr) 150px`, then the rows (order
  bold mono; matched-on mono with ellipsis and its full text as the title; change mono in `--status-success`),
  then "and N more" in secondary. `added`, when set, is a line under the table. `empty` replaces the table;
  `error` replaces count and table, in `--status-danger` with the alert glyph;
- foot, `--border-subtle` rule above, padding `12px 16px`: Close (`.btn.secondary`).

`role="dialog"`, `aria-modal="true"`, `aria-labelledby` the title. On open, focus goes to Close. Tab cycles
inside the dialog (the column behind gets `inert`). Esc closes it (the page handles Esc while it is open, then
returns focus to the "Test…" that opened it). Close and ✕ send `closeTest()`.

`scrim` token: light `rgba(0,0,0,0.35)`, dark `rgba(0,0,0,0.55)`, added to the `Theme` dataclass, both theme
constructors and `_CSS_VALUE_FIELDS`, so `theme_css_vars` emits `--scrim` and `validate_theme` checks it as a CSS
value. The scrim covers the web view only: the nav and footer are Qt (§10).

### 5.6 Kit additions

| Class | What it is |
|---|---|
| `.dialog`, `.dialog-head`, `.dialog-title`, `.dialog-body`, `.dialog-foot`, `.dialog-scrim` | A modal drawn in a page: `--surface`, `--card-border`, radius 12px, `box-shadow: var(--overlay-shadow)` |
| `.drop-line` | The 2px insertion line drag draws at a row's edge (`[data-drop="before"]`/`"after"` on the row) |

Both on the kit sheet and in `tests/test_web_kit.py`. Phase 10's frame reuses `.dialog`.

### 5.7 Keys

`rules-filter`, `rule-add`, `rule-empty-add`, and per rule `rule:{id}:toggle`, `rule:{id}:name-open`,
`rule:{id}:grip`, `rule:{id}:up`, `rule:{id}:down`, `rule:{id}:test`, `rule:{id}:menu`,
`rule:{id}:menu-edit|duplicate|delete`. In the rule view: `rule-back`, `rule:{id}:name`, `rule:{id}:level-article|order`,
`rule:{id}:s{s}:match-ALL|ANY`, `rule:{id}:s{s}:c{c}:field|operator|value|values|remove`,
`rule:{id}:s{s}:a{a}:type|{param}|remove`, `rule:{id}:s{s}:cond-add|act-add|remove`, `rule:{id}:step-add`,
`rule:{id}:delete`. In Test: `test-close`, `test-x`. Ids are generated (`r7`), so keys carry no user text and
can be found with `byKey` as phase 7 does.

`blocker_key()` returns the name field's key or the problem control's key.

### 5.8 Small windows

At the dialog's 1100px minimum the column is about 860px: the condition grid fits (200 + 180 + value ≥ 300 +
28), and an action's parameters wrap. The Test dialog is `min(580px, 100% − 32px)` wide and its body scrolls
inside `max-height: calc(100% − 64px)`.

## 6. `run_rule_test(rule, df, session) -> dict` (`gui/settings/rule_test.py`)

No Qt. Runs on a worker.

1. `before = df.copy()`; `engine = RuleEngine([rule])`; `after = engine.apply(df.copy())`. The whole analysis,
   not a sample: the count is of all orders. (The 100-row cut is gone; `_whole_order_sample` is deleted.)
2. Align the frames as `RuleTestDialog._align_frames` does today (move that docstring's reasoning with it).
3. Matched orders: the `Order_Number`s of `engine.matched_rows`, in frame order. Total: `before["Order_Number"]
   .nunique()`. Added lines: `len(after) − len(before)`.
4. Per matched order, up to 5: **Matched on** is `"{field}: {value}"` for each condition field (all steps, in
   order, deduped) that is a column, read from the order's first matched row and joined with " · "; an
   order-level field is computed with the engine's own method (`getattr(engine,
   RuleEngine.ORDER_LEVEL_FIELDS[field])(order_rows)`; a method that takes more arguments is skipped). **Change**
   is worded from the diff of that order's rows: a new internal tag `+ {tag}`, a removed one `− {tag}`, the status
   to Not fulfillable `Held`, another column `{column} → {value}`, an added line `+ {sku} × {qty}`; joined with
   ", ", and "No change" when nothing differs.
5. Returns the `test` dict of §4.7 without `name`, `running` and the intro (the draft adds those).

An exception propagates: the host's worker turns it into `set_test_error()` and logs it.

## 7. `SettingsWebHost` additions

- `testRequested(id)`: as §4.7. The worker is a `gui.worker.Worker`, held on the host until it finishes (the
  phase 7 note on garbage-collected workers applies). One test at a time: a new request while one runs replaces
  it (the counter drops the old result).
- `testClosed()`: `draft.test = None`, push.
- `focus_problem(key)`: `reveal` first (§4.5).
- Leaving the Rules page (`show_page` with another key) closes Test and returns Rules to the list.

`SettingsWindow` passes `session_name` through to `RulesDraft`; `ActionsHandler.open_settings_window` passes
`Path(self.mw.session_path).name` when a session is open, else `None`. Add `session_path` to the
`SimpleNamespace` `mw` in `tests/test_actions_handler.py` if it is not there.

## 8. Errors

| What fails | What the operator sees |
|---|---|
| A rule problem (§4.4) | The message under the control, the alert on the rule's row, the nav mark, the footer's link (which opens the rule and focuses the control), Save disabled |
| A warning | The message under the control; nothing else |
| No analysis | Test… disabled with its title |
| The test raises | The dialog's error line; logged with the traceback |
| `collect()` raises, the save fails | Phase 7's, unchanged |

## 9. Deleted, moved, kept

- Deleted: `gui/settings/rules.py`, `gui/rule_test_dialog.py`, `tests/test_settings_page_rules.py`,
  `tests/test_rules_page.py`, `tests/test_rule_test_dialog.py`. Their cases move to the draft and runner tests
  (§12): field vocabularies by level, the resolvability flag's three branches, legacy type round-trip, unknown
  type round-trip, a stored field the level lacks kept, old-format rules, `execution_order` listing,
  per-level moves, the frame alignment and its added-rows case.
- `tests/audit/test_03_rule_engine.py` keeps its four invariants, rewritten against `RulesDraft` and
  `run_rule_test`: Save refuses exactly what is marked (validate ⇔ problems); Test runs what Save stores (one
  builder: the test gets `collect()`'s rule minus `priority` and `enabled`); the test reports rows the saved
  rule already tagged; the list shows execution order.
- `gui/settings/fields.py` keeps every name it exports (§3.1).
- `InlineMessage`, `WheelIgnoreComboBox` and the Qt components stay: other Qt pages use them.

## 10. Departures from the mockup

| Mockup | Built | Why |
|---|---|---|
| One list numbered 01–03, "Rules run top to bottom" | Two groups, Article rules then Order rules, numbered within each | The engine runs every article rule first (owner's decision) |
| ⋯ "Edit, duplicate, delete" with no editor drawn | A rule view with a breadcrumb back to the list | Owner's decision; the mockup leaves the editor open |
| Sample fields ("Total weight", "Country") and verbs ("Set courier to", "Set status to On hold") | The stored field names, the engine's operators, and the action types' labels (§4.3) | The mockup's are sample data; a rule can name any analysis column |
| An off rule's body at 60% opacity | Drawn in `--text-secondary` | The style lint flags `opacity` |
| The switch's knob slides (`transition: left .12s`) | No animation | ADR 0016: no transitions |
| Test: "Runs this rule, as edited, against the analysis in …. Orders aren't changed." | Adds ", which already has the saved rules applied" | The analysis has the saved rules in it already; today's dialog says so and the count depends on it |
| The scrim covers the whole settings window | It covers the web view: nav and footer stay unshaded | The frame is Qt until phase 10 (ADR 0007) |
| "Test…" always live | Disabled with a reason: no analysis, no condition, or a problem | Today's rules |
| A new rule arrives with a sample condition and action | "New rule", article, one empty step, opened in the rule view | No sample data in a profile |
| Filter is a plain box | Reorder controls disabled while it has text | A move among hidden rows would be invisible |

## 11. Docs

- `docs/design/ui-refresh/roadmap.md`: phase 8 as built, with its differences.
- `CONTEXT.md`, under Rules: **Rule off** — a rule kept in the profile that the analysis skips
  (`"enabled": false`); Test still runs it. Under the settings terms: **Rule view** — the Rules page showing one
  rule, reached by Edit; Back returns to the list. **Warning** beside Blocker: shown under a control, does not
  stop a save.
- ADR: none. The flag is a stored-format addition that old code ignores (an older build would run an off rule);
  say so in the PR.

## 12. Tests (test-first; the seams)

| File | Seam | Covers |
|---|---|---|
| `tests/test_settings_draft_rules.py` (new) | `RulesDraft`, no Qt | Load: execution order, old format, ids, unknown keys kept. Every action of §4.2 including dropped shapes and out-of-range indexes. `collect()` in place, priorities, `enabled` add/remove, quantity int, SET_STATUS forced. Snapshot ignores `open`/`test`. Problems, warnings, `blocker()`, `blocker_key()`, `validate()` lines, `reveal()`. Every sentence of §4.6. `fields(level)`, `values_for` cap 200, tags |
| `tests/test_rule_vocab.py` (new) | `gui/settings/vocab.py` | The lists equal the ones `fields.py` re-exports |
| `tests/test_rule_test_runner.py` (new) | `run_rule_test` | Count of orders and total; matched-on for a column and an order-level field; each change wording; added lines; no match; an off rule tested as on; frame alignment cases ported from `test_rule_test_dialog.py` |
| `tests/test_rules_engine_enabled.py` (new) | `RuleEngine` | An `enabled: false` rule does not run; missing key runs; `true` runs |
| `tests/test_rule_validator.py` (extend or new) | `condition_error` | The three date operators |
| `tests/test_settings_web_page.py` (extend) | The page in Chromium, fed `RulesDraft.view()` | List DOM, groups, empty state, filter and no-hits, switch, arrows, Alt+arrows, menu (Edit/Duplicate/Delete), drag (dispatch `dragstart`/`dragover`/`drop` events on the grip and rows and assert `rule_move` args; a cross-group drop sends nothing), rule view DOM per action type, value menu, focus kept while typing, Test dialog (running, result, empty, error), Esc order (menu, then dialog, then nothing), both themes from tokens |
| `tests/test_settings_web_host.py` (extend) | Host with a patched `Worker`/thread pool | testRequested → result pushed; closed test drops a late result; error path; `focus_problem` reveals a rule |
| `tests/test_settings_footer.py`, `test_settings_nav.py`, `test_settings_unsaved.py`, `test_settings_roundtrip.py`, `test_settings_entry_points.py` | The window | Rules is a web page: blocker link opens the rule; unsaved by edit; round-trip of a config with rules (old format, legacy action, unknown key, `enabled: true`) written back unchanged except today's normalisation |
| `tests/audit/test_03_rule_engine.py` | §9 | The four invariants |
| `tests/test_web_kit.py`, `tests/web/kit_sheet.html` | Kit sheet | `.dialog`, `.drop-line` |
| `tests/test_theme*.py` (wherever tokens are listed) | `shared/theme.py` | `scrim` in both themes, emitted as `--scrim` |

Round-trip normalisation, stated so the test can assert it: an old-format rule is written with `steps`; every
rule's `priority` is its position + 1; a `SET_MULTI_TAGS` `tags` list is written as `value`. Nothing else
changes.

Renders under `docs/design/ui-refresh/renders/phase8/`, each the whole dialog grabbed offscreen and looked at
before the PR: the list with three rules (one off, one order rule) light and dark; the empty state light; the
rule view with two steps and a problem light and dark; the Test dialog with a result light and dark; a drag in
progress (drop line) light.

## 13. Out of scope

- Sets, Weight, Reports, Tag categories (phase 9); the frame (phase 10).
- Friendly labels for field names; a date picker.
- Moving a rule across levels by drag (change its Level instead).
- Re-checking the analysis when a rule changes (the analysis is re-run by the operator).
- Undo for Delete beyond Cancel and the close guard.

## 14. Delivery

One PR from the branch the implementing session is given. Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m
pytest -q` and `.venv/bin/ruff check .`. The PR says: `shared/theme.py` gains the `scrim` token (Packing Tool
needs no work at its next sync); rules gain an optional `enabled` key that an older build ignores; the hand
checks on Windows (Esc, Ctrl+S, Ctrl+F with focus inside the page; drag feel).
