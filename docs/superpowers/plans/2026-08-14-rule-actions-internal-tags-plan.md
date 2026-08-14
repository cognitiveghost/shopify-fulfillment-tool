# Rule Actions: Internal Tags Only — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the rule editor from offering three actions that claim to add tags but actually append to a free-text note column, without changing what any already-configured rule does.

**Architecture:** The writer gets stricter, the reader stays tolerant. `ACTION_TYPES` — the editor's dropdown — loses `ADD_TAG`, `ADD_ORDER_TAG` and `SET_MULTI_TAGS`. The rule engine keeps executing all three, byte-for-byte as today. A rule already using one loads, round-trips through save unchanged, and gets an orange advisory label under its row. Alongside that: a new `REMOVE_INTERNAL_TAG` engine action, a tag-value dropdown seeded from the configured tag categories, and help text that matches the code.

**Tech Stack:** Python 3, PySide6, pandas, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-08-14-rule-actions-internal-tags-design.md`

## Global Constraints

- **Windows-only in production; developed on Ubuntu.** All Qt tests run headless: prefix every pytest invocation with `QT_QPA_PLATFORM=offscreen`.
- **Use the repo venv.** Bare `python` / `pytest` / `ruff` are not on PATH. Use `.venv/bin/python -m pytest` and `.venv/bin/ruff`. Run `./scripts/setup_venv.sh` once in a fresh worktree.
- **Never hand-edit anything under `shared/`.** Nothing in this plan touches it.
- **No hardcoded colours in stylesheets.** Use `get_theme_manager().get_current_theme()` tokens — `theme.accent_orange`, `theme.text_secondary`, etc.
- **The rule engine's behaviour for `ADD_TAG`, `ADD_ORDER_TAG` and `SET_MULTI_TAGS` must not change.** Do not add them to `deprecated_actions` (`shopify_tool/rules.py:1055`); that list *skips* actions, which would silently stop populating `Status_Note` for every client already using them.
- **No on-disk config change.** No new config key, no `profile_migrations.py` entry, no version bump. A profile written by this build must stay readable by the previous one.
- **Gate before finishing:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check . --exclude shared` must both be clean.

---

### Task 1: Engine support for `REMOVE_INTERNAL_TAG`

A rule can add an internal tag but not remove one, even though `tag_manager.remove_tag` already exists and no caller in the engine uses it. This task adds the mirror action. It is purely backend — the editor does not offer it until Task 2.

`Internal_Tags` is **order-level** stored on line-level rows, so the write must expand from the matched lines to every line of every matched order via `tag_manager.expand_to_order_rows` — exactly as `ADD_INTERNAL_TAG` does at `shopify_tool/rules.py:1075-1084`.

**Files:**
- Modify: `shopify_tool/rules.py:918-921` (`_prepare_df_for_actions`) and `shopify_tool/rules.py:1075-1084` (`_execute_actions`)
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `shopify_tool.tag_manager.remove_tag(current_tags_value, tag_to_remove) -> str` and `expand_to_order_rows(df, mask) -> pd.Series`, both already present.
- Produces: the action type string `"REMOVE_INTERNAL_TAG"`, consumed by Tasks 2, 4 and 5.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rules.py`, in the same class as `test_add_internal_tag_applies_to_every_line_of_the_matched_order` (currently ends at `:130`). The module already defines the `_df` and `_rule` helpers at `:12-22` — reuse them, do not redefine.

```python
    def test_remove_internal_tag_clears_the_tag_from_every_line_of_the_order(self):
        # Mirror of the ADD case: the rule matches only row 0, but
        # Internal_Tags is order-level, so both of order 1001's lines must
        # lose the tag -- not just the matched line.
        df = _df({
            "Order_Number": ["1001", "1001", "1002"],
            "Quantity": [5, 1, 9],
            "Internal_Tags": ['["GIFT", "FRAGILE"]', '["GIFT", "FRAGILE"]', '["GIFT"]'],
        })
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["FRAGILE"]
        assert parse_tags(out.loc[1, "Internal_Tags"]) == ["FRAGILE"]  # same order
        assert parse_tags(out.loc[2, "Internal_Tags"]) == ["GIFT"]     # unmatched order

    def test_remove_internal_tag_is_a_noop_for_an_absent_tag(self):
        df = _df({"Order_Number": ["X"], "Quantity": [1], "Internal_Tags": ['["GIFT"]']})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "NOT_THERE"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]

    def test_remove_internal_tag_creates_the_column_when_missing(self):
        # _prepare_df_for_actions must build Internal_Tags even for a
        # remove-only rule, or the read at execute time raises KeyError.
        df = _df({"Order_Number": ["X"], "Quantity": [1]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == []
```

`parse_tags` and `RuleEngine` are already imported at the top of the file (`:8-9`).

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -k remove_internal_tag -v
```

Expected: all three FAIL. The first two assert on unchanged tags (the unknown action type falls through every `elif` and does nothing); the third raises `KeyError: 'Internal_Tags'`.

- [ ] **Step 3: Add the column preparation**

In `shopify_tool/rules.py`, `_prepare_df_for_actions`, change the `ADD_INTERNAL_TAG` branch (currently `:920-921`):

```python
                    elif action_type in ("ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"):
                        needed_columns.add("Internal_Tags")
```

- [ ] **Step 4: Add the execution branch**

In `shopify_tool/rules.py`, `_execute_actions`, immediately after the `ADD_INTERNAL_TAG` branch (which ends at `:1084`) and before `elif action_type == "SET_STATUS":`:

```python
            elif action_type == "REMOVE_INTERNAL_TAG":
                # Order-level like ADD_INTERNAL_TAG -- see the note there. In an
                # order-level rule this lands in the caller's "apply to first
                # row" bucket, which is fine precisely because of this expansion.
                from shopify_tool.tag_manager import expand_to_order_rows, remove_tag

                order_mask = expand_to_order_rows(df, matches)
                current_tags = df.loc[order_mask, "Internal_Tags"]
                new_tags = current_tags.apply(lambda t, value=value: remove_tag(t, value))
                df.loc[order_mask, "Internal_Tags"] = new_tags
```

The `value=value` default-argument binding is not decoration — it pins the loop variable, matching every other lambda in this method.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules.py -v
```

Expected: the three new tests PASS and every pre-existing `test_rules.py` test still passes.

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/rules.py tests/test_rules.py
git commit -m "Phase 6 — Rule engine: add REMOVE_INTERNAL_TAG"
```

---

### Task 2: Drop the three actions from the dropdown, without rewriting saved rules

The riskiest task in this plan. Removing a name from `ACTION_TYPES` opens two silent-corruption paths, and both must close in this same commit — which is why the round-trip test is written first.

**Path (a) — the combo silently retypes the action.** `add_action_row` does `type_combo.addItems(ACTION_TYPES)` then `type_combo.setCurrentText(config.get("type", ...))` (`gui/settings/rules.py:1180-1181`). On a **non-editable** `QComboBox`, `setCurrentText` with a string that is not in the list is a **no-op** — the combo silently stays on index 0. So a rule saved as `ADD_TAG` would display `ADD_INTERNAL_TAG`, and `collect()` would write `ADD_INTERNAL_TAG` back on the next save of any unrelated setting.

**Path (b) — the value is dropped on save.** `_on_action_type_changed` (`:1234`) and `collect()` (`:1381`) both branch on literal name lists. Remove the legacy names from those lists and the row builds no value widget, so `collect()` emits `{"type": "ADD_TAG"}` with no `value` — the rule's text is gone.

The fix for (a) is a per-row combo item; the fix for (b) is simply *not* touching those two internal branch lists. Net: the only line that loses the three names is `ACTION_TYPES` itself.

**Files:**
- Modify: `gui/settings/fields.py:53-63`
- Modify: `gui/settings/rules.py:1178-1181`
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `"REMOVE_INTERNAL_TAG"` from Task 1.
- Produces: `gui.settings.fields.LEGACY_ACTION_TYPES: list[str]`, consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py`. The module already imports `RulesPage` and defines the `analysis_df` fixture at `:9-15`.

```python
class TestLegacyActionRoundTrip:
    """A rule using one of the three retired actions must survive an
    open-and-save with its type and value byte-identical. The editor flags
    it; the editor never rewrites it."""

    @pytest.mark.parametrize("legacy_type", ["ADD_TAG", "ADD_ORDER_TAG"])
    def test_legacy_action_survives_collect_untouched(self, qtbot, analysis_df, legacy_type):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": legacy_type, "value": "KEEP_ME"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action["type"] == legacy_type
        assert action["value"] == "KEEP_ME"

    def test_legacy_set_multi_tags_survives_collect_untouched(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "SET_MULTI_TAGS", "tags": ["A", "B"]}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action["type"] == "SET_MULTI_TAGS"
        assert action["value"] == "A, B"

    def test_a_new_action_row_does_not_offer_the_retired_types(self, qtbot, analysis_df):
        from gui.settings.fields import LEGACY_ACTION_TYPES

        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        page.add_rule_widget()
        rule_refs = page.rule_widgets[0]
        # add_action_row takes the *step* refs -- it appends to their
        # "actions_layout" / "actions". A blank rule always has exactly one step.
        page.add_action_row(rule_refs["steps"][0])

        combo = rule_refs["steps"][0]["actions"][-1]["type"]
        offered = {combo.itemText(i) for i in range(combo.count())}
        assert not (offered & set(LEGACY_ACTION_TYPES))
        assert "ADD_INTERNAL_TAG" in offered
        assert "REMOVE_INTERNAL_TAG" in offered

    def test_the_retired_type_is_offered_only_on_the_row_that_uses_it(self, qtbot, analysis_df):
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

        combo = page.rule_widgets[0]["steps"][0]["actions"][0]["type"]
        assert combo.currentText() == "ADD_TAG"
        assert "ADD_TAG" in {combo.itemText(i) for i in range(combo.count())}
```

Note `test_legacy_set_multi_tags_survives_collect_untouched` asserts `value == "A, B"`, not `tags == ["A", "B"]`. That is today's behaviour, not a regression this plan introduces: `_on_action_type_changed` joins a list into the line edit (`:1306-1310`) and `collect()` writes it back under `"value"` (`:1394-1395`). The engine accepts either key (`shopify_tool/rules.py:1112`). Do not "fix" this — normalising the key here is out of scope and would change on-disk config, which the Global Constraints forbid.

- [ ] **Step 2: Run the tests to verify the state before the change**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -k Legacy -v
```

Expected: the three round-trip tests PASS (this is today's behaviour, and they are the regression net for what follows), and `test_a_new_action_row_does_not_offer_the_retired_types` FAILS on `ImportError: cannot import name 'LEGACY_ACTION_TYPES'`. `test_the_retired_type_is_offered_only_on_the_row_that_uses_it` passes trivially today.

If any of the three round-trip tests fails *now*, stop — the premise of this task is wrong and the finding needs raising before continuing.

- [ ] **Step 3: Update the action-type vocabulary**

Replace `gui/settings/fields.py:53-63` with:

```python
ACTION_TYPES: list[str] = [
    "ADD_INTERNAL_TAG",
    "REMOVE_INTERNAL_TAG",
    "SET_STATUS",
    "COPY_FIELD",
    "CALCULATE",
    "ALERT_NOTIFICATION",
    "ADD_PRODUCT",
]

# Still executed by the rule engine, but no longer offered when building a
# new rule: all three append to the free-text Status_Note column despite
# their names, and the first two are the same code path. A rule already
# using one keeps working and round-trips through save unchanged; the
# editor flags it instead. See
# docs/superpowers/specs/2026-08-14-rule-actions-internal-tags-design.md.
LEGACY_ACTION_TYPES: list[str] = ["ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"]
```

`ACTION_TYPES[0]` is now `"ADD_INTERNAL_TAG"`, which is the right default for a fresh row.

**Do not touch** the `if action_type in [...]` lists inside `_on_action_type_changed` (`gui/settings/rules.py:1234`) or `collect()` (`:1381`), and do not touch either `SET_MULTI_TAGS` branch (`:1301`, `:1394`). Those are internal dispatch and must keep handling the legacy names — that is fix (b).

- [ ] **Step 4: Keep a configured legacy type selectable on its own row**

Replace `gui/settings/rules.py:1179-1181` with:

```python
        # Type dropdown
        type_combo = WheelIgnoreComboBox()
        type_combo.addItems(ACTION_TYPES)
        # A retired action type is added to this row's combo only, so the rule
        # round-trips instead of being silently retyped: setCurrentText on a
        # non-editable QComboBox is a no-op for an absent string, which would
        # leave the row showing ACTION_TYPES[0] and save that over the user's
        # rule. New rows still offer only the current types.
        configured_type = config.get("type", ACTION_TYPES[0])
        if configured_type and configured_type not in ACTION_TYPES:
            type_combo.addItem(configured_type)
        type_combo.setCurrentText(configured_type)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py tests/test_settings_page_rules.py -v
```

Expected: all PASS, including the round-trip tests that passed in Step 2 — they are the point of the exercise.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/fields.py gui/settings/rules.py tests/test_rules_page.py
git commit -m "Phase 6 — Rule editor: retire the three Status_Note actions from the dropdown"
```

---

### Task 3: Flag a legacy action on its own row

A retired action still loads and still runs, so the user needs to be told why it is no longer in the dropdown and what to replace it with. This reuses the layout pattern #278 established for condition rows: wrap the horizontal row in a vertical layout and hang a hidden, word-wrapped `QLabel` beneath it. A hidden label is skipped by the layout, so a row with nothing to say keeps exactly its current height.

The message names what the action *does* before what to do about it — the user's mental model is "this adds a tag", and correcting that is the whole point.

**Files:**
- Modify: `gui/settings/rules.py` — `add_action_row` (from `:1164`)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `LEGACY_ACTION_TYPES` from Task 2.
- Produces: `action_refs["legacy_label"]` — a `QLabel`, always present, hidden unless the row's type is legacy. Task 4 does not use it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py`:

```python
class TestLegacyActionFlag:
    def _page_with_action(self, qtbot, analysis_df, action):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [action],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)
        return page, page.rule_widgets[0]["steps"][0]["actions"][0]

    def test_legacy_action_row_explains_itself(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_TAG", "value": "T"})
        label = refs["legacy_label"]
        assert not label.isHidden()
        assert "Status_Note" in label.text()
        assert "ADD_INTERNAL_TAG" in label.text()

    def test_set_multi_tags_says_one_action_per_tag(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "SET_MULTI_TAGS", "tags": ["A", "B"]})
        assert "one ADD_INTERNAL_TAG per tag" in refs["legacy_label"].text()

    def test_current_action_row_is_not_flagged(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_INTERNAL_TAG", "value": "GIFT"})
        assert refs["legacy_label"].isHidden()
        assert refs["legacy_label"].text() == ""

    def test_switching_off_a_legacy_type_clears_the_flag(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_TAG", "value": "T"})
        refs["type"].setCurrentText("ADD_INTERNAL_TAG")
        assert refs["legacy_label"].isHidden()
```

`assert not label.isHidden()` rather than `label.isVisible()`: on an offscreen platform a widget whose window was never shown reports `isVisible() == False` regardless of its own hidden flag, so `isVisible` would pass vacuously.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -k LegacyActionFlag -v
```

Expected: all four FAIL with `KeyError: 'legacy_label'`.

- [ ] **Step 3: Wrap the row and add the label**

In `gui/settings/rules.py`, `add_action_row`. Replace the current row-widget construction (`:1190-1191`):

```python
        row_widget = QWidget()
        row_widget.setLayout(row_layout)
```

with the wrapper — mirroring the condition row at `:677-694`:

```python
        # The row goes inside a vertical wrapper so the retired-action notice
        # gets a full-width line of its own underneath, instead of being
        # squeezed in past the delete button. The wrapper takes over the row's
        # padding, so the row's geometry is unchanged.
        row_widget = QWidget()
        outer_layout = QVBoxLayout(row_widget)
        outer_layout.setSpacing(2)
        row_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addLayout(row_layout)

        # One label per action row, alive for the row's whole lifetime. Hidden
        # labels are skipped by the layout, so an unflagged row keeps its
        # current height.
        legacy_label = QLabel()
        legacy_label.setWordWrap(True)
        legacy_label.hide()
        outer_layout.addWidget(legacy_label)
```

`QVBoxLayout` and `QLabel` are already imported in this module.

- [ ] **Step 4: Publish the label and refresh it on every type change**

Add the label to the refs dict (currently `:1194-1199`):

```python
        action_refs = {
            "widget": row_widget,
            "type": type_combo,
            "param_widgets": {},
            "param_layout": row_layout,
            "legacy_label": legacy_label,
        }
```

Add the refresh helper as a new method on the class, next to `_on_action_type_changed`:

```python
    def _refresh_legacy_action_flag(self, action_refs):
        """Explain a retired action type on the row that still uses it.

        These three still run -- the engine is deliberately unchanged -- so
        this is advice, not an error. It leads with what the action really
        does, because the name says the opposite.
        """
        label = action_refs["legacy_label"]
        action_type = action_refs["type"].currentText()

        if action_type not in LEGACY_ACTION_TYPES:
            label.clear()
            label.hide()
            return

        replacement = (
            "one ADD_INTERNAL_TAG per tag"
            if action_type == "SET_MULTI_TAGS"
            else "ADD_INTERNAL_TAG"
        )
        theme = get_theme_manager().get_current_theme()
        label.setStyleSheet(f"color: {theme.accent_orange}; {font_css('caption')}")
        label.setText(
            f"Writes the Status_Note text column, not tags. "
            f"Replace with {replacement} to add a real tag."
        )
        label.show()
```

Import `LEGACY_ACTION_TYPES` alongside the existing `ACTION_TYPES` import from `gui.settings.fields` at the top of the module. `get_theme_manager` and `font_css` are already imported (see their use at `:62-63`).

Call it from `_on_action_type_changed`, as the first statement after `action_type` is read (`:1223`):

```python
        self._refresh_legacy_action_flag(action_refs)
```

`_on_action_type_changed` is already wired to `type_combo.currentTextChanged` (`:1202-1204`) and is already called once during construction (`:1207`), so both the initial state and every subsequent switch are covered by this one call site.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v
```

Expected: all PASS, including Task 2's round-trip tests.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/rules.py tests/test_rules_page.py
git commit -m "Phase 6 — Rule editor: flag rules still using a retired tag action"
```

---

### Task 4: Tag value becomes a dropdown of configured tags

`ADD_INTERNAL_TAG`'s value is a bare `QLineEdit` today, so a typo silently produces a tag that `get_tag_category` reports as `"custom"` — no category, no colour, no SKU write-off. Seed an **editable** combo from the configured tag vocabulary instead.

Editable, not fixed, for two reasons: a tag the user is about to create must stay typeable, and an unknown value loaded from config must round-trip (the same `setCurrentText` no-op trap as Task 2, path (a) — an editable combo has no such trap, since it accepts arbitrary text).

The vocabulary is a **snapshot** taken when the settings dialog opens. The Tag Categories page lives in the same dialog and can add a tag while the Rules page is open; live cross-page sync is not worth building here, and the combo being editable means nothing is actually blocked.

`SYSTEM_TAGS` (`shopify_tool/core.py:18` — `Repeat`, `Priority`, `Error`) are deliberately **not** offered: they are computed by the analyser, and listing them invites rules that fight it. Still typeable.

**Files:**
- Modify: `gui/settings/rules.py` — `RulesPage.__init__` (`:39`), `_on_action_type_changed` (`:1234-1241`), `collect()` (`:1381-1382`)
- Modify: `gui/settings/window.py:141`
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `shopify_tool.tag_manager._normalize_tag_categories(tag_categories) -> dict` (already present), `"REMOVE_INTERNAL_TAG"` from Task 1.
- Produces: `RulesPage.__init__(rules, analysis_df, tag_categories=None, parent=None)` and `RulesPage.get_configured_tags() -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py`:

```python
_TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "handling": {"label": "Handling", "color": "#FF0000",
                     "tags": ["FRAGILE", "GIFT"], "order": 1},
        "shipping": {"label": "Shipping", "color": "#00FF00",
                     "tags": ["EXPRESS"], "order": 2},
    },
}


class TestInternalTagValueCombo:
    def _refs(self, qtbot, analysis_df, action):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [action],
            }],
        }
        page = RulesPage([rule], analysis_df, tag_categories=_TAG_CATEGORIES)
        qtbot.addWidget(page)
        return page, page.rule_widgets[0]["steps"][0]["actions"][0]

    def test_configured_tags_are_offered_sorted_and_deduped(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df, tag_categories=_TAG_CATEGORIES)
        qtbot.addWidget(page)
        assert page.get_configured_tags() == ["EXPRESS", "FRAGILE", "GIFT"]

    def test_missing_tag_categories_yields_an_empty_vocabulary(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        assert page.get_configured_tags() == []

    def test_tag_value_widget_is_an_editable_combo_of_the_vocabulary(self, qtbot, analysis_df):
        page, refs = self._refs(
            qtbot, analysis_df, {"type": "ADD_INTERNAL_TAG", "value": "GIFT"})
        combo = refs["param_widgets"]["value"]
        assert combo.isEditable()
        assert {combo.itemText(i) for i in range(combo.count())} == {
            "EXPRESS", "FRAGILE", "GIFT"}
        assert combo.currentText() == "GIFT"

    def test_remove_internal_tag_gets_the_same_combo(self, qtbot, analysis_df):
        page, refs = self._refs(
            qtbot, analysis_df, {"type": "REMOVE_INTERNAL_TAG", "value": "FRAGILE"})
        assert refs["param_widgets"]["value"].currentText() == "FRAGILE"

    def test_a_tag_outside_the_vocabulary_round_trips(self, qtbot, analysis_df):
        page, refs = self._refs(
            qtbot, analysis_df, {"type": "ADD_INTERNAL_TAG", "value": "BRAND_NEW"})
        assert refs["param_widgets"]["value"].currentText() == "BRAND_NEW"
        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action == {"type": "ADD_INTERNAL_TAG", "value": "BRAND_NEW"}

    def test_set_status_keeps_its_plain_line_edit(self, qtbot, analysis_df):
        from PySide6.QtWidgets import QLineEdit

        page, refs = self._refs(
            qtbot, analysis_df, {"type": "SET_STATUS", "value": "Ready"})
        assert isinstance(refs["param_widgets"]["value"], QLineEdit)
        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action["value"] == "Ready"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -k InternalTagValueCombo -v
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'tag_categories'`.

- [ ] **Step 3: Accept and expose the vocabulary**

In `gui/settings/rules.py`, change the signature at `:39` and store the snapshot:

```python
    def __init__(self, rules: list, analysis_df, tag_categories: dict | None = None, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self.rule_widgets = []
        self._rules_config = rules
        # ponytail: a snapshot taken when the dialog opens. The Tag Categories
        # page can add a tag while this page is open and this list will not
        # see it; the combo is editable, so the tag is still typeable. Wire up
        # a signal between the two pages if that stops being good enough.
        self._tag_categories = tag_categories or {}
```

`tag_categories` is keyword-with-default so every existing two-argument `RulesPage(rules, df)` call — including the ones throughout `tests/test_rules_page.py` — keeps working with an empty vocabulary.

Add the accessor as a new method, next to `get_available_rule_fields` (`:218`):

```python
    def get_configured_tags(self) -> list[str]:
        """Every tag named by the configured tag categories, sorted and deduped.

        SYSTEM_TAGS (core.py) are deliberately excluded: the analyser owns
        them, and offering them here invites rules that fight it. The combo
        that consumes this is editable, so they remain typeable.
        """
        from shopify_tool.tag_manager import _normalize_tag_categories

        tags = set()
        for category in _normalize_tag_categories(self._tag_categories).values():
            tags.update(category.get("tags", []))
        return sorted(tags)
```

- [ ] **Step 4: Split the value-widget branch**

In `_on_action_type_changed`, replace the combined branch at `:1234-1241`:

```python
        if action_type in ["ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG", "SET_STATUS"]:
```

with two branches — the retired pair and `SET_STATUS` keep the line edit; the tag actions get the combo:

```python
        if action_type in ["ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"]:
            # Editable: an unlisted tag must stay typeable, and an unknown
            # value loaded from config must round-trip rather than snap to
            # item 0 the way a fixed combo would.
            value_combo = WheelIgnoreComboBox()
            value_combo.setEditable(True)
            value_combo.addItems(self.get_configured_tags())
            # On an editable combo the placeholder lives on the line edit --
            # QComboBox.setPlaceholderText only shows at currentIndex == -1.
            value_combo.lineEdit().setPlaceholderText("Tag")
            if initial_config:
                value_combo.setCurrentText(initial_config.get("value", ""))
            layout.insertWidget(insert_pos, value_combo, 1)
            action_refs["param_widgets"]["value"] = value_combo

        elif action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_STATUS"]:
            # Simple value field
            value_edit = QLineEdit()
            value_edit.setPlaceholderText("Value")
            if initial_config:
                value_edit.setText(initial_config.get("value", ""))
            layout.insertWidget(insert_pos, value_edit, 1)
            action_refs["param_widgets"]["value"] = value_edit
```

The two retired names stay in the second list — that is Task 2's fix (b), and dropping them here loses the rule's value on save.

- [ ] **Step 5: Split the serialization branch to match**

In `collect()`, replace `:1381-1382`:

```python
                    if action_type in ["ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG", "SET_STATUS"]:
                        act["value"] = act_refs["param_widgets"]["value"].text()
```

with:

```python
                    if action_type in ["ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"]:
                        act["value"] = act_refs["param_widgets"]["value"].currentText()

                    elif action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_STATUS"]:
                        act["value"] = act_refs["param_widgets"]["value"].text()
```

- [ ] **Step 6: Pass the vocabulary in from the settings window**

In `gui/settings/window.py:141`:

```python
        self._add_page(
            RulesPage(
                self.config_data.get("rules", []),
                self.analysis_df,
                tag_categories=self.config_data.get("tag_categories", {}),
            ),
            "Rules",
        )
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py tests/test_settings_page_rules.py -v
```

Expected: all PASS. Task 2's round-trip tests in particular still pass — `ADD_TAG` kept its `QLineEdit`, so `.text()` is still the right reader for it.

- [ ] **Step 8: Commit**

```bash
git add gui/settings/rules.py gui/settings/window.py tests/test_rules_page.py
git commit -m "Phase 6 — Rule editor: pick internal tags from the configured vocabulary"
```

---

### Task 5: Make the help text describe the code

The editor's level tooltip documents a per-row distinction between `ADD_TAG` and `ADD_ORDER_TAG` that does not exist — both land in the same bucket at `shopify_tool/rules.py:864-871`. The Rule Test dialog describes `ADD_TAG` and `ADD_INTERNAL_TAG` and says nothing about `ADD_ORDER_TAG`, `SET_MULTI_TAGS` or the new `REMOVE_INTERNAL_TAG`.

Documentation only — no behaviour changes, so no new test. The existing `tests/test_rule_test_dialog.py` covers the dialog's rendering and must stay green.

**Files:**
- Modify: `gui/settings/rules.py:397-400`
- Modify: `gui/rule_test_dialog.py:398-403`

**Interfaces:**
- Consumes: `"REMOVE_INTERNAL_TAG"` from Task 1.
- Produces: nothing.

- [ ] **Step 1: Correct the level tooltip**

In `gui/settings/rules.py`, replace the last four lines of the `level_combo` tooltip (`:397-400`):

```python
            "  → Actions behavior:\n"
            "     • ADD_TAG - applies to ALL rows (for filtering)\n"
            "     • ADD_ORDER_TAG - applies to first row only (for counting)\n"
            "     • ADD_INTERNAL_TAG - applies to ALL rows (structured tags)"
```

with:

```python
            "  → Actions:\n"
            "     • ADD_INTERNAL_TAG / REMOVE_INTERNAL_TAG - order-level\n"
            "       structured tags, applied to every row of the order\n"
            "     • all other actions - applied to the order's first row"
```

- [ ] **Step 2: Correct the Rule Test action descriptions**

In `gui/rule_test_dialog.py`, replace `:398-403`:

```python
            if action_type == "ADD_TAG":
                actions_text += " → Appends to Status_Note column"
            elif action_type == "SET_STATUS":
                actions_text += " → Sets Order_Fulfillment_Status"
            elif action_type == "ADD_INTERNAL_TAG":
                actions_text += " → Appends to Internal_Tags (JSON list)"
```

with:

```python
            if action_type in ("ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"):
                # Retired from the rule editor's dropdown but still executed;
                # the name promises a tag and the code writes free text.
                actions_text += " → Appends to Status_Note (text, not tags)"
            elif action_type == "SET_STATUS":
                actions_text += " → Sets Order_Fulfillment_Status"
            elif action_type == "ADD_INTERNAL_TAG":
                actions_text += " → Adds to Internal_Tags (JSON list, whole order)"
            elif action_type == "REMOVE_INTERNAL_TAG":
                actions_text += " → Removes from Internal_Tags (JSON list, whole order)"
```

- [ ] **Step 3: Run the affected tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rule_test_dialog.py tests/test_rules_page.py -v
```

Expected: all PASS.

- [ ] **Step 4: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: the whole suite passes (583 tests before this plan, plus the ~19 added here) and ruff is clean.

- [ ] **Step 5: Refresh the knowledge graph**

```bash
graphify update .
```

Required by CLAUDE.md after any code change — a stale graph returns wrong answers about this repo silently.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/rules.py gui/rule_test_dialog.py
git commit -m "Phase 6 — Rule help text: describe what the actions actually do"
```

---

## Self-review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 Authoring surface shrinks | Task 2, Step 3 |
| §2a Combo silently retypes | Task 2, Step 4 |
| §2b Value dropped on save | Task 2, Step 3 (do-not-touch) + Task 4, Steps 4-5 |
| §3 Legacy flag on the action row | Task 3 |
| §4 Tag value combo | Task 4 |
| §5 `REMOVE_INTERNAL_TAG` | Task 1 (engine), Task 2 Step 3 (dropdown), Task 4 (combo), Task 5 (description) |
| §6 Help text | Task 5 |
| Data model: no on-disk change | Global Constraints; no task creates a migration |
| Testing items 1-3 | Task 1 Step 1; item 3 is the existing suite, run at Task 1 Step 5 |
| Testing items 4-7 | Task 2 Step 1 (item 4), Task 3 Step 1 (items 5-6), Task 4 Step 1 (item 7) |

**Naming consistency:** `LEGACY_ACTION_TYPES` (defined Task 2 Step 3, used Task 2 Step 1 test and Task 3 Step 4), `action_refs["legacy_label"]` (defined Task 3 Step 4, used Task 3 Steps 1 and 4), `get_configured_tags()` (defined Task 4 Step 3, used Task 4 Steps 1 and 4), `_refresh_legacy_action_flag` (defined and called in Task 3 Step 4). No mismatches.

**Ordering:** Task 1 introduces `REMOVE_INTERNAL_TAG` before Task 2 puts it in the dropdown. Task 2 establishes the round-trip guarantee before Task 4 rewrites the branch that could break it. Task 3 changes `add_action_row`'s layout and Task 2 changes its combo construction — different regions of the same method; run Task 2's tests after Task 3 (Task 3 Step 5 does).
