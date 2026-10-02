# UI refresh phase 8: Rules and Test rule on the web tier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task
> in one session (stage B runs no subagents). Steps use checkbox (`- [ ]`) syntax. Tick each task's boxes in this
> file in the commit that finishes the task.

**Goal:** Replace the Qt Rules page and the Qt rule test window with a Rules page in the settings web document
(list, empty state, rule view, drag and arrows, on/off) and a Test rule dialog drawn in the page.

**Architecture:** A Qt-free `RulesDraft` holds the rules and words everything; `settings.js` draws its `view()`
and reports edits through the phase 7 bridge. `run_rule_test` is a pure function the web host runs on a worker.
The engine skips rules stored with `"enabled": false`.

**Tech Stack:** Python 3.14, PySide6 (QtWebEngine, QWebChannel), pandas, vanilla JS/CSS, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-refresh-phase8-rules-web-design.md` (read it whole first; § refs
below are to it). It builds on `docs/superpowers/specs/2026-10-02-ui-refresh-phase7-settings-web-design.md`.
Gotchas: `docs/design/ui-refresh/handoff.md`.

## Global Constraints

- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.
- **Baseline** (clean `origin/main` 62bc88e, cloud session, 2026-10-02): **3190 passed, 0 failed**, 1 warning,
  ~7.5 min; ruff clean. `tests/test_label_printing.py::TestImageToZpl` passes here (it fails on the dev VM only).
- Drafts and `rule_test.py` and `vocab.py` import no Qt (a test imports each module with Qt blocked, as
  `tests/test_settings_draft_general.py` does for `page_state` — copy its approach if it has one, else assert
  `"PySide6" not in sys.modules` after a fresh `importlib` in a subprocess).
- The page sends strings and booleans only; indexes travel as strings; ids are `r1`, `r2`, … (§4.1).
- Python words every sentence. The one exception: the no-filter-hits line (§4.6).
- No `transform`, `transition`, `rotate:`, `scale:`, `opacity:` in web assets (style lint). No hardcoded colours.
- Copy is exactly §4.6 and §4.3; curly quotes “ ” and the ellipsis … as written there.
- `CLAUDE.md`: theme tokens only; no UI calls from worker threads; `ruff` DTZ (no naive dates).
- Run `graphify update .` after code changes if the tool is installed; skip silently if it is not.

## Review Focus

1. **User text with markup or quotes** (a rule named `<b>"VIP"</b>`, a value `a&b`): must render as text,
   round-trip unchanged, and never break a key. Pinned in Task 4 and Task 9.
2. **Malformed stored rules** (a rule that is not a dict, missing `level`, `steps: None`, a condition missing
   `value`, an action with no `type`): the page must open, keep what it cannot draw, and save it back. Pinned in
   Task 4.
3. **A late Test result** (Test, then close it, change page, or test another rule before the worker returns):
   the stale result must be dropped. Pinned in Task 13.
4. **An analysis without `Order_Number`, or with NaN cells** in matched rows: Test must count rows as orders
   gracefully and word NaN as empty, not crash. Pinned in Task 12.
5. **A column with thousands of distinct values** behind a value menu: capped at 200, no freeze. Pinned in
   Task 5.

---

### Task 1: Engine on/off and date validation

**Files:**
- Modify: `shopify_tool/rules.py` (`RuleEngine.__init__`)
- Modify: `gui/rule_validator.py` (`condition_error`)
- Test: `tests/test_rules_engine_enabled.py` (new), `tests/test_rule_validator_dates.py` (new)

**Interfaces:** Produces: `RuleEngine(rules)` ignores rules with `rule.get("enabled") is False`;
`condition_error("date before"|"date after"|"date equals", value)` returns
`"Type a date: YYYY-MM-DD, DD/MM/YYYY or DD.MM.YYYY."` when `_parse_date_safe(value)` is None, else None.

- [ ] **Step 1: Write the failing tests**

```python
def _df():
    return pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Internal_Tags": ["[]"]})
RULE = {"name": "t", "level": "article", "steps": [{"match": "ALL",
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "actions": [{"type": "ADD_INTERNAL_TAG", "value": "x"}]}]}

def test_a_rule_turned_off_does_not_run():
    out = RuleEngine([{**RULE, "enabled": False}]).apply(_df())
    assert "x" not in out.loc[0, "Internal_Tags"]

@pytest.mark.parametrize("extra", [{}, {"enabled": True}])
def test_a_rule_on_or_without_the_flag_runs(extra):
    out = RuleEngine([{**RULE, **extra}]).apply(_df())
    assert "x" in out.loc[0, "Internal_Tags"]

@pytest.mark.parametrize("op", ["date before", "date after", "date equals"])
def test_an_unreadable_date_is_an_error(op):
    assert condition_error(op, "31/31/2024") == "Type a date: YYYY-MM-DD, DD/MM/YYYY or DD.MM.YYYY."
    assert condition_error(op, "") == "Type a date: YYYY-MM-DD, DD/MM/YYYY or DD.MM.YYYY."
    assert condition_error(op, "2024-01-30") is None
    assert condition_error(op, "2026-01-14 18:56:50 +0200") is None
```

- [ ] **Step 2: Run them; expect FAIL** — `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_rules_engine_enabled.py tests/test_rule_validator_dates.py`
- [ ] **Step 3: Implement.** In `__init__`, filter after the deep copy and before normalising; log
  `f"[RULE ENGINE] {n} rule(s) turned off, skipped"` at info when n > 0. If all are off, `self.rules = []`.
  In `condition_error`, a branch for the three date operators using `validate_date`'s parse (not its message).
- [ ] **Step 4: Run them; expect PASS**, plus `tests/test_rules.py tests/audit/test_03_rule_engine.py` still pass.
- [ ] **Step 5: Commit** `Rules: an off rule is skipped; dates are validated`.

### Task 2: The `scrim` token

**Files:**
- Modify: `shared/theme.py` (`Theme` field `scrim: str`, both constructors, `_CSS_VALUE_FIELDS`)
- Test: `tests/test_theme_palette.py` (the expected-values table), `tests/test_theme_css_vars.py`

**Interfaces:** Produces CSS var `--scrim`: light `rgba(0,0,0,0.35)`, dark `rgba(0,0,0,0.55)`.

- [ ] **Step 1:** Add `"scrim": ("rgba(0,0,0,0.35)", "rgba(0,0,0,0.55)")` to the palette table in
  `tests/test_theme_palette.py` (beside `overlay_shadow`) and `assert decls["--scrim"] == theme.scrim` beside the
  `--overlay-shadow` assertion in `tests/test_theme_css_vars.py`.
- [ ] **Step 2:** Run both files; expect FAIL.
- [ ] **Step 3:** Add the field after `overlay_shadow`, both values, and `"scrim"` to `_CSS_VALUE_FIELDS`.
- [ ] **Step 4:** Run `tests/test_theme_palette.py tests/test_theme_css_vars.py tests/test_style_lint.py`; PASS.
- [ ] **Step 5: Commit** `Theme: scrim token for dialogs drawn in a page`.

### Task 3: Qt-free rule vocabularies

**Files:**
- Create: `gui/settings/vocab.py` — `CONDITION_OPERATORS`, `ACTION_TYPES`, `LEGACY_ACTION_TYPES` moved verbatim
  with their comments.
- Modify: `gui/settings/fields.py` — `from gui.settings.vocab import ACTION_TYPES, CONDITION_OPERATORS, LEGACY_ACTION_TYPES`
  (keep `REPORT_FILTER_OPERATORS = list(CONDITION_OPERATORS)`); add them to `__all__` or a `# noqa: F401` so ruff keeps the re-export.
- Test: `tests/test_rule_vocab.py` (new)

- [ ] **Step 1:** Test: `from gui.settings import fields, vocab`; the three lists are the same objects; `vocab`
  imports no PySide6 (run `python -c "import gui.settings.vocab, sys; assert not any(m.startswith('PySide6') for m in sys.modules)"` via `subprocess` with `.venv` python).
- [ ] **Step 2:** Run; FAIL. **Step 3:** Move. **Step 4:** Run it and `tests/test_settings_page_reports.py`; PASS.
- [ ] **Step 5: Commit** `Settings: rule vocabularies in a Qt-free module`.

### Task 4: `RulesDraft` — load, collect, the list

**Files:**
- Create: `gui/settings/rules_draft.py`
- Test: `tests/test_settings_draft_rules.py` (new; this task and Tasks 5–6 add to it)

**Interfaces:**
- Consumes: `PageContract` (`gui/settings/contract.py`), `_shaped` pattern from `page_state.py` (copy it or import
  it), `RuleEngine.execution_order`, `get_unique_column_values` (`shopify_tool.core`), vocab (Task 3).
- Produces:
  ```python
  class RulesDraft(PageContract):
      def __init__(self, rules: list, analysis_df, tag_categories: dict | None, client: str, session: str | None): ...
      open: str | None            # rule view id
      test: dict | None           # Test state (Task 13)
      def apply(self, action: str, args) -> bool: ...
      def view(self) -> dict: ...
      def collect(self) -> dict: ...   # {"rules": <the live list, refilled>}
      def snapshot(self) -> str: ...
      def ids(self) -> list[str]: ...  # in list order, for tests
      def rule(self, rule_id: str) -> dict: ...
  ```
- Constants exported for tests: `SUBTITLE`, `EMPTY_TITLE`, `EMPTY_TEXT`, `GROUP_TEXT = {"article": ..., "order": ...}`.

Actions in this task: `rule_add`, `rule_open`, `rule_close`, `rule_toggle`, `rule_move`, `rule_duplicate`,
`rule_delete` (§4.2). View: list and empty modes (§4.6) including the step summaries and `can_up`/`can_down`;
`test` in the row is `{"enabled": False, "title": <no analysis sentence>}` for now when `analysis_df` is empty,
else `{"enabled": True, "title": ""}` (Task 6 adds the other reasons).

- [ ] **Step 1: Write the failing tests** (each one function; data built inline):
  - `test_rules_load_in_execution_order` — `[order p1, article p2, article p1]` → names article p1, article p2, order p1; ids `["r1","r2","r3"]`.
  - `test_an_old_format_rule_is_held_as_one_step` — root `conditions/match/actions` → `rule(id)["steps"] == [{...}]` and no root keys; collect writes `steps`.
  - `test_keys_the_page_does_not_draw_survive` — a rule with `"owner": "ops"` and a step with `"note": 1` round-trip through `collect()`.
  - `test_malformed_entries_are_kept_not_dropped` — `rules=["junk", {"name": "x"}, {"name": "y", "steps": None}]`: draft builds, `view()` works, `collect()["rules"]` still contains `"junk"` unchanged at the end and both dicts (missing level reads article; `steps: None` held as one empty step).
  - `test_collect_refills_the_live_list_with_priorities` — `collect()["rules"] is rules`; priorities 1..n in list order, article first.
  - `test_untouched_rules_collect_unchanged_except_normalisation` — a modern rule list with priorities 1..n collects equal to a deep copy of the input.
  - `test_toggle_off_stores_false_and_on_removes_it` / `test_toggle_on_keeps_a_stored_true` (§3.3).
  - `test_move_stays_inside_the_level` — `rule_move [id, "0"]` on the 2nd article rule makes it first; a `to` past the group end or negative is dropped (False); moving an order rule never puts it among article rules.
  - `test_duplicate_is_placed_after_and_named_copy` — `{name} (copy)`, new id, deep copy (editing the copy leaves the original).
  - `test_add_appends_an_article_rule_and_opens_it` — §4.2 shape; `draft.open == new id`; `view()["rules"]["mode"] == "rule"`.
  - `test_delete_from_the_rule_view_returns_to_the_list`.
  - `test_open_and_close` — `rule_open` unknown id → False; `rule_close` → True and mode `list`.
  - `test_wrong_shapes_are_dropped` — parametrize `("rule_toggle", ["r1"])`, `("rule_toggle", ["r1", "true"])`, `("rule_move", ["r1", 0])`, `("nope", [])` → False and `snapshot()` unchanged.
  - `test_snapshot_ignores_the_open_rule_and_test` — `open`/`test` changes leave `snapshot()` equal and `is_dirty()` False after `mark_clean()`.
  - `test_view_list` — exact dict for one article rule `Tags contains VIP → ADD_INTERNAL_TAG priority`: group title "Article rules", text `GROUP_TEXT["article"]` = "Run first, on each order line.", num "01", step lead "When", conds `[{"join": "", "field": "Tags", "op": "contains", "value": "VIP"}]`, acts `[{"join": "", "verb": "Add internal tag", "value": "priority"}]`, count "1 rule · 1 on".
  - `test_view_summary_words` — ANY joins "or"; second step lead "Then check"; `is empty` has no value; 41-char value cut to 40 + "…"; COPY `"{source} → {target}"`; CALCULATE `"{field1} {op} {field2} → {target}"`; ADD_PRODUCT `"{sku} × {quantity}"`; SET_STATUS verb "Hold the order", value ""; empty sides give `none` "No conditions"/"No actions".
  - `test_view_empty` — `mode == "empty"`, page head `action == ""`, empty block exactly §4.6.
  - `test_count_plural` — "1 rule · 0 on", "2 rules · 1 on".
  - `test_markup_is_data` — name `<b>"VIP"</b>` comes back in `view()` unchanged (the page escapes; Task 9 asserts the DOM).
- [ ] **Step 2: Run; expect FAIL** (`ModuleNotFoundError`).
- [ ] **Step 3: Implement** `RulesDraft` in `gui/settings/rules_draft.py`. Hold `self._live = rules` (the list
  object), `self._rules` (sorted, normalised dicts — entries that are not dicts are kept aside in
  `self._opaque` and appended unchanged at the end of `collect()`), `self._ids`. Page head:
  `{"page": "rules", "title": "Rules", "subtitle": SUBTITLE, "action": "Add rule" | "", "crumb": ""}`.
- [ ] **Step 4: Run; expect PASS.** Also `ruff check gui/settings/rules_draft.py`.
- [ ] **Step 5: Commit** `Rules draft: load, save and the list`.

### Task 5: `RulesDraft` — the rule view

**Files:** Modify `gui/settings/rules_draft.py`; Test `tests/test_settings_draft_rules.py`.

**Interfaces:** Produces the remaining §4.2 actions (`rule_name`, `rule_level`, `step_*`, `cond_*`, `act_*`,
`values_for`), `fields(level) -> list[tuple[str, list[str]]]`, `tags() -> list[str]`, and
`view()["rules"]["rule"]` exactly as §5.4 (with `hint` on conditions). Group labels: "Order-level fields",
"Common article fields", "Other available fields". Placeholders per operator: `in list`/`not in list`
"Value1, Value2, Value3"; `between`/`not between` "10-100"; regex "^SKU-\d{4}$"; date operators "YYYY-MM-DD";
else "Value". `value_menu` is True when the operator is `equals`/`does not equal` and the field is an
`analysis_df` column. Param `kind`s: `text`, `mono` (sku, quantity, target), `field`, `choice` (operation),
`segmented` (severity), with `suggest: True` on internal-tag values.

- [ ] **Step 1: Write the failing tests:**
  - `test_fields_by_level` — order level starts with `("Order-level fields", list(RuleEngine.ORDER_LEVEL_FIELDS))`; article has no order-level group; analysis columns not starting `_` and not common go in "Other available fields", sorted; empty df → no third group.
  - `test_cond_edits` — add (field = first field of level, `equals`, `""`), field, operator (valueless clears value), value, remove; index out of range → False.
  - `test_a_stored_field_the_level_lacks_is_kept` — `cond_field` with any string is accepted; view marks `field_missing` and the warning text (Task 6 owns the sentence; here assert `field_missing is True`).
  - `test_rule_level_moves_the_rule_to_the_end_of_the_other_group`.
  - `test_step_add_remove_match` — step 0 cannot be removed; `step_match` only `ALL`/`ANY`.
  - `test_act_type_resets_to_defaults` — parametrize every row of §4.3's defaults; ADD_PRODUCT quantity `"1"` in the view and `1` (int) in `collect()`; SET_STATUS collects `NOT_FULFILLABLE` whatever was stored.
  - `test_act_type_refuses_legacy_for_a_new_row_but_keeps_the_rows_own` — a stored `ADD_TAG` row can be set back to `ADD_TAG`; another row cannot be set to it.
  - `test_unknown_action_type_round_trips` — `{"type": "FUTURE", "x": 1}` collects unchanged; view has `params == []`.
  - `test_set_multi_tags_list_is_shown_joined_and_written_as_value` — `{"type": "SET_MULTI_TAGS", "tags": ["A","B"]}` → param value `"A, B"`; collect writes `value: "A, B"` and no `tags`.
  - `test_act_param_only_known_names` — `act_param [id,"0","0","nope","x"]` → False.
  - `test_values_for_caps_at_200_and_clears_on_next_edit` — df with 5,000 distinct SKUs → `len(items) == 200`; key `"rule:r1:s0:c0:value"`; a following `cond_value` clears `values` to None.
  - `test_tags_come_from_tag_categories` — v2 categories with tags → sorted, deduped.
  - `test_rule_view_shape` — a full `view()["rules"]["rule"]` for a two-step rule, compared to a literal dict (step 2 title "Step 2 — checks what step 1 matched" on article, "Step 2 — runs only if step 1 matched" on order; match_text "Run the actions when all of these are true"; level hints §4.6).
- [ ] **Step 2: Run; FAIL.** **Step 3: Implement.** **Step 4: Run; PASS.**
- [ ] **Step 5: Commit** `Rules draft: the rule view and its edits`.

### Task 6: Problems, warnings, blocker, reveal

**Files:** Modify `gui/settings/rules_draft.py`, `gui/settings/contract.py` (`reveal`); Test
`tests/test_settings_draft_rules.py`, `tests/test_settings_page_contract.py`.

**Interfaces:** Produces `PageContract.reveal(key: str) -> bool` (False); `RulesDraft.blocker()`,
`blocker_key()`, `validate()`, `reveal(key)`, `can_test(rule_id) -> bool`, and the row/rule-view `test`
`{"enabled", "title"}` with the §4.6 reasons in this order: no analysis, no condition, a problem.
Sentences exactly §4.4.

- [ ] **Step 1: Write the failing tests:**
  - `test_problems_and_their_keys` — parametrize: empty name → key `rule:r1:name`, sentence "Name this rule."; bad regex → `rule:r1:s0:c0:value` and `condition_error`'s message; bad date (Task 1); ADD_PRODUCT empty sku → `rule:r1:s0:a0:sku` "Type the SKU to add."; quantity `"0"`, `"1.5"`, `"10000"`, `"x"` → `rule:r1:s0:a0:quantity` "Type a whole number from 1 to 9999.".
  - `test_blocker_names_the_first_rule_with_a_problem` — `Fix “VIP”`; empty name → `Name rule 2` (2 = its number in its group); `blocker_key()` that control; no problem → None and "".
  - `test_warnings_do_not_block` — unresolvable field (the three branches of the old `_check_field_resolvable`: in the offered list → none; empty df and not an order-level field → none; empty df and an order-level field on an article rule → warning; df loaded and absent → warning) with the sentence “{field}” isn't available on an article rule, so this condition never matches.; legacy action sentence for `SET_MULTI_TAGS` ("one Add internal tag per tag") and `ADD_TAG` ("Add internal tag"); step with no conditions "A step with no conditions matches nothing."; `blocker()` is None for all.
  - `test_validate_lines` — `Rule “VIP”, step 1, condition 2: <msg>`; `Rule “VIP”, step 1, action 1: Type the SKU to add.`; `Rule 1: Name this rule.`; `validate()` ok ⇔ no problems (the AUDIT-03-5 invariant).
  - `test_row_carries_problem_flag`.
  - `test_reveal_opens_the_rule_of_a_key` — `reveal("rule:r2:s0:c0:value")` → True, `open == "r2"`, `test is None`; same again → False; `reveal("threshold")` → False; `PageContract().reveal("x") is False`.
  - `test_test_button_reasons` — empty df; no conditions; a problem; else enabled.
- [ ] **Step 2: FAIL. Step 3: Implement** (problems computed per call; cheap). **Step 4: PASS.**
- [ ] **Step 5: Commit** `Rules draft: problems, warnings and the blocker`.

### Task 7: Kit — `.dialog` and `.drop-line`

**Files:** Modify `gui/web/kit.css`, `tests/web/kit_sheet.html`, `tests/test_web_kit.py`.

**Interfaces:** Produces classes `.dialog-scrim` (fixed, inset 0, `background: var(--scrim)`, `display: grid;
place-items: center`, z-index above `.menu`), `.dialog` (`width: min(580px, 100% - 32px)`, `max-height: calc(100% -
64px)`, flex column, `--surface`, `1px solid var(--card-border)`, radius 12px, `box-shadow: var(--overlay-shadow)`),
`.dialog-head` (48px, padding `0 12px 0 16px`, rule under), `.dialog-title` (12pt bold), `.dialog-body` (padding
16px, gap 12px, `overflow: auto`), `.dialog-foot` (flex end, gap 8px, padding `12px 16px`, rule above);
`[data-drop="before"] > .drop-line` / `"after"` — a `.drop-line` is an absolutely positioned 2px bar in
`--focus-ring` at the row's top or bottom edge (the row is `position: relative`).

- [ ] **Step 1:** Draw a dialog (title, body text, Close) and two rows with a drop mark on the kit sheet; in
  `tests/test_web_kit.py` assert computed styles: scrim background equals the theme's `scrim` in both themes, dialog
  radius `12px`, box-shadow equals `overlay_shadow` (light) / `none` (dark), drop line height `2px` and its colour
  the `focus_ring` token. Follow the existing kit tests' helpers.
- [ ] **Step 2:** FAIL. **Step 3:** CSS. **Step 4:** PASS with `tests/test_style_lint.py`.
- [ ] **Step 5: Commit** `Web kit: dialog and drop line`.

### Task 8: Page — the list, the empty state

**Files:** Modify `gui/web/settings.js`, `gui/web/settings.css`; Test `tests/test_settings_web_page.py`.

**Interfaces:** Consumes `view()` (Tasks 4–6). Sends: `edit("rule_add", [])`, `edit("rule_open", [id])`,
`edit("rule_toggle", [id, bool])`, `edit("rule_move", [id, String(pos)])`, `edit("rule_duplicate", [id])`,
`edit("rule_delete", [id])`, `testRule(id)` (Task 13 adds the slot; until then guard `if (bridge.testRule)`).
The head action button gets `data-act="rule-add"` on the Rules page (today `head()` hardwires `read`): give the
page head's action a `data-act` from the page (`read` for mappings, `rule-add` for rules).

Draw §5.2 and §5.3 with keys §5.7. Glyphs to add to `GLYPH`: `grip` (six dots as circles — use a `<circle>`
variant of `svg()`), `search`, `more`, `chevronUp` `m18 15-6-6-6 6`, `chevronRight` `m9 18 6-6-6-6`, `list` (the
mockup's empty-state paths). Filter: `view.filter`, matched case-insensitively on the name; groups with no visible
row hide; disabled reorder controls with title "Clear the filter to reorder". Alt+Up/Down inside a row sends
`rule_move` and refocuses the same key after the render. The ⋯ menu (`rule-menu:{id}`) follows phase 7's menu
rules (one open, outside click, Esc, arrows); `menuStillOpens` learns `rule-menu:`.

- [ ] **Step 1: Write the failing tests** (use the file's `page`, `_show`, `_wired`, `_text(s)`, `_count`,
  `_click` helpers; build drafts with a small `rules_draft(rules, df=None)` helper):
  - `test_rules_list_draws_two_groups` — counts of `[data-group]` rows, titles, numbers "01","02" per group, count text.
  - `test_an_off_rule_has_the_badge_and_secondary_text` — `.badge` "Off"; summary colour equals `text_secondary`.
  - `test_summary_parts` — field bold, value in `.code`, join word.
  - `test_markup_in_a_name_is_text` — name `<b>"VIP"</b>` → `textContent` equals it, no `b` element inside the row.
  - `test_switch_sends_toggle` — click → `("rule_toggle", ["r1", False])`.
  - `test_arrows_send_moves_and_are_disabled_at_ends`.
  - `test_alt_arrow_moves_and_keeps_focus`.
  - `test_menu_edit_duplicate_delete` — each sends its action; Esc closes the menu and focuses ⋯.
  - `test_name_click_opens_the_rule`.
  - `test_filter_hides_rows_and_says_no_hits` — "No rules named “zz”."; reorder controls disabled while filtering.
  - `test_empty_state` — title, text, primary "Add rule" sends `rule_add`; page head has no action.
  - `test_head_add_rule_sends_rule_add`.
  - `test_test_button_disabled_title` — with an empty df the title is the no-analysis sentence.
  - `test_rules_list_both_themes_read_tokens` — row rule colour equals `border_subtle` in light and dark.
- [ ] **Step 2:** FAIL. **Step 3:** Implement `rulesPage(r)` → `rulesList(r)` / `rulesEmpty(r)`; CSS grid
  `20px 32px minmax(0,1fr) auto`. **Step 4:** PASS; run the whole file (phase 7's page tests must still pass).
- [ ] **Step 5: Commit** `Settings page: the rules list`.

### Task 9: Page — drag to reorder

**Files:** Modify `gui/web/settings.js`, `gui/web/settings.css`; Test `tests/test_settings_web_page.py`.

**Interfaces:** Sends `edit("rule_move", [id, String(to)])`. `view.drag = {id, level}` while dragging.

Algorithm (the tests do not determine it): rows carry `data-rule`, `data-level`, `data-pos` (position in group).
On `dragover` of a same-level row: `side = event.clientY < rect.top + rect.height / 2 ? "before" : "after"`; set
`data-drop=side` on it only (clear others); `preventDefault()`. Other level: `dropEffect = "none"`, no mark.
On `drop`: `from = pos of dragged`, `t = target pos + (side === "after" ? 1 : 0)`, `to = t > from ? t - 1 : t`;
send only if `to !== from`. `dragend`/`drop` clear all marks and `view.drag`. Grip `draggable="true"`; on
`dragstart` call `event.dataTransfer.setDragImage(row, 16, 16)` and `setData("text/plain", id)`. Grip disabled
(no `draggable`) while filtering.

- [ ] **Step 1: Tests** (dispatch real `DragEvent`s from JS with a shared `new DataTransfer()`, as
  `tests/test_results_bridge.py` or the columns tests do — reuse their helper if one exists):
  - `test_drag_down_one_sends_the_new_position` — drag r1 onto r2's lower half → `("rule_move", ["r1", "1"])`.
  - `test_drag_up_to_the_top` — r3 onto r1's upper half → `["r3", "0"]`.
  - `test_drop_on_itself_sends_nothing`.
  - `test_cross_group_drop_sends_nothing_and_draws_no_line`.
  - `test_drop_line_marks_the_side_then_clears` — `data-drop` is `"after"` during, absent after `dragend`.
  - `test_grip_is_not_draggable_while_filtering`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5: Commit** `Settings page: drag rules to reorder`.

### Task 10: Page — the rule view

**Files:** Modify `gui/web/settings.js`, `gui/web/settings.css`; Test `tests/test_settings_web_page.py`.

**Interfaces:** Sends `rule_close`, `rule_name`, `rule_level`, `rule_toggle`, `step_add`, `step_remove`,
`step_match`, `cond_add/field/operator/value/remove`, `act_add/type/param/remove`, `values_for`, `rule_delete`,
`testRule(id)`, with `id`, `s`, `c`, `a` as strings. Text fields report on every `input` (phase 7 rule); `morph`
keeps the caret. Menus: field (grouped, max-height 280px, a missing stored field listed first with "Not available
on this level"), operator, action type, action field params, operation; value menu opens after `values_for`
arrives (`view.pending` pattern: set `view.menu` to the value key and send `values_for`; the menu draws when
`state.rules.rule.values.key` matches). Internal-tag values get a suggestion menu from `tags`. Severity is a
`.segmented`.

- [ ] **Step 1: Tests:**
  - `test_rule_view_head_is_a_breadcrumb` — "Rules" link sends `rule_close`; name shown; Test… and switch present.
  - `test_rule_card_name_and_level` — typing sends `rule_name` per keystroke and focus stays (`document.activeElement.dataset.key == "rule:r1:name"` after 3 renders); level segment sends `rule_level`.
  - `test_condition_row_controls` — field menu groups and items; picking sends `cond_field`; operator menu; value typing; remove.
  - `test_valueless_operator_draws_no_value_field`.
  - `test_value_menu_asks_for_values_then_picks` — chevron click sends `values_for`; after a state with `values`, the menu lists them; picking sends `cond_value`.
  - `test_each_action_type_draws_its_params` — parametrize §4.3 rows: param keys present, Qty label before quantity, SET_STATUS draws none.
  - `test_problem_and_warning_lines` — problem in `--status-danger` with `role="alert"`; warning in `--status-warning`; hint for a list operator.
  - `test_step_cards` — Remove step only on step 2+; Add step, Add condition, Add action send theirs; "Delete rule" sends `rule_delete`.
  - `test_footer_link_focuses_a_control_in_the_rule_view` — push a list state, emit `problemFocusRequested("rule:r1:s0:c0:value")`, then push the rule view: the value field is focused (the phase 7 hold).
  - `test_rule_view_both_themes` — card background reads `surface` per theme.
- [ ] **Step 2:** FAIL. **Step 3:** Implement `ruleView(rv)` and its CSS (grids §5.4.3). **Step 4:** PASS.
- [ ] **Step 5: Commit** `Settings page: the rule view`.

### Task 11: The window — Rules joins the web host; the Qt page goes

**Files:**
- Modify: `gui/settings/window.py` (import `RulesDraft`; drop `RulesPage`; `WEB_PAGE_KEYS["Rules"] = "rules"`; new
  `session_name=None` kwarg; build `RulesDraft(self.config_data["rules"], self.analysis_df,
  self.config_data.get("tag_categories", {}), client, session_name)` into `drafts["rules"]`;
  `self._add_page(drafts["rules"], "Rules", self._web_host)`).
- Modify: `gui/settings/web_host.py` (`focus_problem` calls `reveal` first and pushes when it returns True;
  `show_page` to a key other than `"rules"` sets the rules draft's `open = None` and `test = None` — do it via a
  `RulesDraft.leave()` method).
- Modify: `gui/actions_handler.py` (`session_name=Path(self.mw.session_path).name if self.mw.session_path else None`).
- Delete: `gui/settings/rules.py`, `tests/test_settings_page_rules.py`, `tests/test_rules_page.py` (their cases
  are in Tasks 4–6; check each test there has a counterpart before deleting and add any missing one to
  `tests/test_settings_draft_rules.py`).
- Modify tests: `tests/test_settings_nav.py`, `test_settings_unsaved.py`, `test_settings_roundtrip.py`,
  `test_settings_footer.py`, `test_settings_entry_points.py`, `test_settings_button_roles.py`,
  `tests/test_settings_web_host.py`, `tests/test_actions_handler.py`, and the RulesPage cases of
  `tests/audit/test_03_rule_engine.py` (`test_rules_page_refuses_to_save_an_invalid_rule`,
  `test_rules_page_shows_rules_in_execution_order` → against `RulesDraft`).

- [ ] **Step 1: Tests:**
  - `test_rules_is_a_web_page` (nav) — selecting Rules shows the host and the bridge state's `page == "rules"`.
  - `test_a_rule_edit_marks_rules_unsaved_at_once` (unsaved) — `host.bridge.edit("rule_toggle", ["r1", False])` → Rules in the footer summary without waiting for the poll.
  - `test_the_blocker_link_opens_the_rule` (footer) — a rule with a bad regex: footer reads `Fix “X” in Rules to save.`; activating the link selects Rules, `draft.open == "r1"`.
  - `test_rules_round_trip` (roundtrip) — config with an old-format rule, a legacy `SET_MULTI_TAGS` with `tags`, an unknown key, `enabled: true`: saved untouched equals the input after exactly the §12 normalisation.
  - `test_session_name_reaches_the_rules_draft` (actions handler, `session_path=str(tmp_path/"session_1")`) — the window's rules draft has `session == "session_1"`.
  - `test_leaving_rules_returns_it_to_the_list` (host).
- [ ] **Step 2:** FAIL. **Step 3:** Implement and delete. **Step 4:** Run every `tests/test_settings_*.py`,
  `tests/test_actions_handler.py`, `tests/audit/test_03_rule_engine.py`; PASS. `ruff check .`.
- [ ] **Step 5: Commit** `Settings: Rules on the web tier; the Qt Rules page goes`.

### Task 12: `run_rule_test`

**Files:**
- Create: `gui/settings/rule_test.py`
- Delete: `gui/rule_test_dialog.py`, `tests/test_rule_test_dialog.py` (port its alignment cases first)
- Modify: `tests/audit/test_03_rule_engine.py` (`test_rule_test_dialog_reports_rows_the_saved_rule_already_tagged`,
  `test_rule_test_config_keeps_add_product_quantity` → against `run_rule_test` and `RulesDraft.test_rule(id)`)
- Test: `tests/test_rule_test_runner.py` (new)

**Interfaces:** Produces `run_rule_test(rule: dict, df: pd.DataFrame) -> dict` returning
`{"count": str, "count_text": str, "rows": [{"order", "why", "change"}], "more": str, "added": str, "empty": str}`
(§4.7 minus `name`, `running`, `intro`, `session`, `outro`, `error`), and `RulesDraft.test_rule(id) -> dict` (the
rule as `collect()` would store it, minus `priority` and `enabled`) — Test and Save build the rule the same way
(AUDIT-03-10).

- [ ] **Step 1: Tests:**
  - `test_counts_orders_not_rows` — 3 orders / 5 rows, rule matches 2 lines of one order → `count "1"`, `count_text "of 3 orders matches"`; 2 orders → "of 3 orders match".
  - `test_matched_on_columns_and_order_fields` — `Tags: VIP · SKU: A`; an order rule on `item_count` shows `item_count: 2`.
  - `test_change_words` — internal tag added `+ priority`, removed `− old`, held `Held`, a column `Status_Note → x`, an added line `+ BONUS × 1` with `added "1 line added"`; no change `No change`.
  - `test_first_five_then_more` — 7 matching orders → 5 rows, `more "and 2 more"`.
  - `test_no_match` — `empty "No order matches this rule."`, rows [].
  - `test_no_order_number_column_counts_rows_as_orders` — Review Focus 4: df without `Order_Number`: each row is one order, labelled by its row number `#1`, `#2`.
  - `test_nan_cells_word_as_empty` — a NaN in a matched-on column reads `Tags: ` and no crash.
  - `test_reports_rows_the_saved_rule_already_tagged` (audit invariant, ported).
  - the alignment cases from `tests/test_rule_test_dialog.py` (CALCULATE new column, ADD_PRODUCT appended rows).
- [ ] **Step 2:** FAIL. **Step 3:** Implement per §6 (the alignment moves with its docstring). **Step 4:** PASS.
- [ ] **Step 5: Commit** `Rules: a Qt-free rule test runner; the Qt test window goes`.

### Task 13: Bridge and host — running Test

**Files:** Modify `gui/settings/bridge.py`, `gui/settings/web_host.py`, `gui/settings/rules_draft.py`; Test
`tests/test_settings_bridge.py`, `tests/test_settings_web_host.py`, `tests/test_settings_draft_rules.py`; add the
two members to the phase 7 spec's catalogue table (§3.3 there).

**Interfaces:**
- `SettingsBridge`: `testRequested = Signal(str)`, `testClosed = Signal()`, `@Slot(str) testRule(id)`,
  `@Slot() closeTest()`.
- `RulesDraft`: `start_test(id) -> bool` (sets `test = {"id", "running": True}` when `can_test`), `set_test(id,
  result: dict)`, `set_test_error(id)`, `close_test()`; `view()["rules"]["test"]` per §4.7, with intro/session/outro
  and `error "The test didn't finish. Details are in Logs."`, `None` when closed.
- `SettingsWebHost`: on `testRequested(id)`: `if draft.start_test(id)`: push, `self._test_run += 1`, start
  `Worker(run_rule_test, draft.test_rule(id), self._rules_df.copy())` on `QThreadPool.globalInstance()`, keep it on
  `self._test_worker`; result/error slots check the run number and that `draft.test` is still for that id, then
  `set_test`/`set_test_error` (+ `logger.error(..., exc_info=...)`) and push. `testClosed` → `close_test()`, push.

- [ ] **Step 1: Tests:** bridge slots emit; draft `start_test` refuses when `can_test` is False; view while running
  (`running True`, no count); view with a result (intro with and without a session: "Runs this rule, as edited,
  against the analysis in" + session, or "…against the current analysis" with `session ""`); host with
  `QThreadPool.start` monkeypatched to run the worker synchronously (`worker.run()`): result pushed; **Review
  Focus 3**: close before the result → stays closed; second request for another rule → first result dropped;
  `show_page("general")` before the result → dropped; an exception → error line pushed and logged.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5: Commit** `Settings: Test runs on a worker`.

### Task 14: Page — the Test dialog

**Files:** Modify `gui/web/settings.js`, `gui/web/settings.css`; Test `tests/test_settings_web_page.py`.

**Interfaces:** Consumes `state.rules.test`; sends `bridge.testRule(id)` from both Test… buttons and
`bridge.closeTest()` from Close, ✕ and Esc. Uses the kit `.dialog*` (Task 7).

Draw §5.5. Set `inert` on `.settings-page` while open; focus Close on open; Tab cycles (Close ↔ ✕); Esc order in
`onKey`: open menu first, then the dialog, else leave it to the Qt dialog. On close return focus to the
`rule:{id}:test` key (list) or the rule view's Test….

- [ ] **Step 1: Tests:** running shows "Testing…"; a result draws count, count text, 5 rows, "and N more", added
  line; empty; error in danger colour with `role="alert"`; Close/✕/Esc each call `closeTest` (spy via
  `_wired`-style hook on `testClosed`); Esc with a menu open closes only the menu; the page behind is `inert`;
  scrim background equals the `scrim` token in both themes; focus returns to Test….
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5: Commit** `Settings page: Test rule dialog`.

### Task 15: Docs, renders, the gate

**Files:** `docs/design/ui-refresh/roadmap.md`, `CONTEXT.md`, `docs/design/ui-refresh/renders/phase8/*.png`,
`docs/design/ui-refresh/handoff.md` (append `### Stage B` under `## Phase 8`).

- [ ] **Step 1:** Roadmap: phase 8 heading "(built in …)" with spec and plan lines and a "Built as listed below,
  with these differences." paragraph (whatever differs from the spec). `CONTEXT.md`: §11's three terms.
- [ ] **Step 2:** Renders per spec §12 with a script in the scratchpad (not committed): `QT_QPA_PLATFORM=offscreen`,
  `apply_theme()`, restore the stored theme after `set_theme()`, open `SettingsWindow` on Rules with a fixture
  config and a small analysis frame, wait for the page's `data-renders`, `window.grab()` → PNG. Look at every PNG.
- [ ] **Step 3:** Full gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.
  Expect ≥ 3190 + the new tests − the deleted Qt tests, 0 failed. Record the counts in the handoff.
- [ ] **Step 4: Commit** `Docs: phase 8 as built; renders` and push.
