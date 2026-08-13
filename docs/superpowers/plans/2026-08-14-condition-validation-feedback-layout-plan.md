# Condition Validation Feedback Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Do not** use `subagent-driven-development` on this repo — the roadmap runner works
> in-session by design (see `~/automation/claude-roadmap-runner/prompt.md`).

**Goal:** Move a rule condition's validation message out of the horizontal condition row
— where it lands to the right of the delete button and is unreadable — onto a full-width
line beneath the row.

**Architecture:** Each condition row's `QWidget` currently hosts the row's
`QHBoxLayout` directly. Wrap it: the widget gets a `QVBoxLayout` holding the existing
row layout on top and one long-lived, initially hidden `QLabel` beneath. The label is
created once with the row instead of being built and destroyed on every value-widget
swap, and it stops depending on a value widget existing.

**Tech Stack:** PySide6 (Qt Widgets), pytest + pytest-qt (`qtbot`), pandas.

**Spec:** `docs/superpowers/specs/2026-08-14-condition-validation-feedback-layout-design.md`

## Global Constraints

- **Only `gui/settings/rules.py` and `tests/test_rules_page.py` change.** No engine
  changes, no Rule Test dialog changes, no new files.
- **Never hand-edit anything under `shared/`** — it is one-way synced from
  `../packing-tool`.
- **No hardcoded colours in stylesheets** — use `theme.*` tokens via
  `get_theme_manager().get_current_theme()`. The one exception is the pre-existing
  validation-tint literals (`#ffebee`, `#fff3e0`, `#1A1A1A`), which already carry a
  `ponytail:` comment; carry that comment forward unchanged, do not add new literals.
- **Two findings are explicitly out of scope** (design doc §5): the dead
  `"is_empty"` vs `"is empty"` operator branch, and the hardcoded tint colours.
  Do not fix either in this branch.
- **Gate before finishing** (both must be clean):
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  .venv/bin/ruff check . --exclude shared
  ```
  `python` and `ruff` are not on `PATH` on this machine — always go through
  `.venv/bin/`. Run `./scripts/setup_venv.sh` first in a fresh worktree.
- **Branch:** `worktree-validation-feedback-layout`. No direct commits to `main`; this
  repo is PR-only.
- Run `graphify update .` after the code changes land.

---

### Task 1: The feedback label moves below the condition row

The structural fix. The row's `QWidget` gains a vertical wrapper; the feedback label
becomes a permanent child of that wrapper, created with the row and reused for its
lifetime instead of being deleted and rebuilt whenever the value widget is swapped.
`condition_refs["value_layout"]` is renamed to `row_layout` — the misleading name is
what caused the bug (design doc §3.3).

**Files:**
- Modify: `gui/settings/rules.py` — `add_condition_row()` (~677-687),
  `_on_rule_condition_changed()` (~725-728 and ~800),
  `_show_validation_feedback()` (~927-935)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `condition_refs["row_layout"]` (`QHBoxLayout`, replaces the key
  `"value_layout"`) and `condition_refs["feedback_label"]` (`QLabel`, always present
  from row construction onward, never deleted before the row itself). Task 2 relies on
  `"feedback_label"` being unconditionally present.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_page.py` (the module already imports `pandas as pd`,
`pytest`, and `RulesPage`, and defines the `analysis_df` fixture):

```python
class TestValidationFeedbackPlacement:
    """The message has to land somewhere the user can actually read it."""

    @staticmethod
    def _rule(field="SKU", operator="matches regex", value="["):
        return {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": field, "operator": operator, "value": value}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    @staticmethod
    def _condition(page):
        return page.rule_widgets[0]["steps"][0]["conditions"][0]

    def test_message_sits_below_the_row_not_inside_it(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)

        page._perform_validation(cond)

        label = cond["feedback_label"]
        assert label.text() == "Invalid regex syntax"
        # Not one more cell in the horizontal row, past the delete button.
        assert cond["row_layout"].indexOf(label) == -1
        outer = cond["widget"].layout()
        assert outer.itemAt(0).layout() is cond["row_layout"]
        assert outer.itemAt(1).widget() is label

    def test_changing_the_operator_drops_a_stale_message(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)
        page._perform_validation(cond)
        assert cond["feedback_label"].text()

        cond["op"].setCurrentText("contains")

        assert cond["feedback_label"].text() == ""
        assert cond["feedback_label"].isHidden()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_rules_page.py::TestValidationFeedbackPlacement -v
```

Expected: both FAIL with `KeyError`. The first on `cond["row_layout"]` (the key is still
called `value_layout`); the second on `cond["feedback_label"]` after the operator
change, because the current code deletes the label and the dict entry with it.

- [ ] **Step 3: Wrap the row and give it a permanent label**

In `add_condition_row()`, replace:

```python
        row_widget = QWidget()
        row_widget.setLayout(row_layout)

        condition_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "value_layout": row_layout,
            "level_combo": rule_widget_refs.get("level_combo"),
        }
```

with:

```python
        # The row goes inside a vertical wrapper so its validation message can
        # have a full-width line of its own underneath, instead of being
        # appended as one more horizontal cell past the delete button. The
        # wrapper takes over the row's padding -- a nested layout gets none of
        # its own -- so the row's geometry is unchanged.
        row_widget = QWidget()
        outer_layout = QVBoxLayout(row_widget)
        outer_layout.setSpacing(2)
        row_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addLayout(row_layout)

        # One feedback label per condition row, alive for the row's whole
        # lifetime. A hidden label is skipped by the layout, so a row with
        # nothing to say keeps exactly its old height.
        feedback_label = QLabel()
        feedback_label.setWordWrap(True)
        feedback_label.hide()
        outer_layout.addWidget(feedback_label)

        condition_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "row_layout": row_layout,
            "feedback_label": feedback_label,
            "level_combo": rule_widget_refs.get("level_combo"),
        }
```

Notes for the implementer:

- `QVBoxLayout` and `QLabel` are already imported at the top of the file — do not add
  imports.
- **Do not set the wrapper's contents margins.** Qt derives a widget-installed layout's
  margins from the style on install and on reparent, and it does so per widget, not per
  layout class — so the new `QVBoxLayout` ends up with exactly the 9,9,9,9 the
  `QHBoxLayout` has today (measured on the real page). Setting them explicitly is what
  would change the geometry. A layout nested with `addLayout` gets no style margins, so
  the explicit zero on `row_layout` documents the 0,0,0,0 it already has rather than
  changing anything.
- `setSpacing(2)` replaces the dead `margin-top: 2px` from the old label stylesheet
  (dead because `_show_validation_feedback` overwrote that stylesheet on first show).
- Do not move `row_layout.addWidget(delete_btn)` or the
  `_on_rule_condition_changed(...)` call that follow — the value widget is inserted at
  index 2 and depends on that ordering.

- [ ] **Step 4: Stop deleting the label on every operator change**

In `_on_rule_condition_changed()`, replace:

```python
        # Clean up validation feedback before removing widget
        if "feedback_label" in condition_refs:
            condition_refs["feedback_label"].deleteLater()
            del condition_refs["feedback_label"]
```

with:

```python
        # Drop any message the previous operator left behind. The label belongs
        # to the row, so it is reused rather than rebuilt.
        condition_refs["feedback_label"].clear()
        condition_refs["feedback_label"].hide()
```

Leave the `validation_timer` block that follows it untouched.

- [ ] **Step 5: Point the value-widget insert at the renamed key**

In `_on_rule_condition_changed()`, change:

```python
        condition_refs["value_layout"].insertWidget(2, new_widget, 1)
```

to:

```python
        condition_refs["row_layout"].insertWidget(2, new_widget, 1)
```

- [ ] **Step 6: Drop the lazy label construction**

In `_show_validation_feedback()`, replace:

```python
        # Create feedback label if doesn't exist
        if "feedback_label" not in condition_refs:
            feedback_label = QLabel()
            feedback_label.setWordWrap(True)
            feedback_label.setStyleSheet(f"{font_css('caption')} margin-top: 2px;")
            condition_refs["value_layout"].addWidget(feedback_label)
            condition_refs["feedback_label"] = feedback_label

        feedback_label = condition_refs["feedback_label"]
```

with:

```python
        feedback_label = condition_refs["feedback_label"]
```

Everything else in the function stays as it is for now — including the
`if not value_widget: return` guard above it, which Task 2 deals with.

- [ ] **Step 7: Confirm the old key is gone and the row's padding is unchanged**

```bash
rtk grep -rn "value_layout" gui/ tests/
```

Expected: no matches.

Then confirm the wrapper inherited the padding the row used to carry, so no condition
row visibly moved:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python -c "
import pandas as pd
from PySide6.QtWidgets import QApplication
app = QApplication([])
from gui.settings.rules import RulesPage
rule = {'name': 'r', 'level': 'article', 'steps': [{'conditions': [{'field': 'SKU', 'operator': 'equals', 'value': 'x'}], 'match': 'ALL', 'actions': [{'type': 'ADD_TAG', 'value': 'T'}]}]}
page = RulesPage([rule], pd.DataFrame({'SKU': ['x'], 'Quantity': [1]}))
cond = page.rule_widgets[0]['steps'][0]['conditions'][0]
m = cond['widget'].layout().contentsMargins()
print('wrapper margins:', m.left(), m.top(), m.right(), m.bottom())
"
```

Expected: `wrapper margins: 9 9 9 9` — the same values the row layout carried before
this change. Anything else means the margins were set explicitly somewhere; remove that.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v
```

Expected: the two new tests PASS and every pre-existing test in the file still passes.

- [ ] **Step 9: Commit**

```bash
rtk git add gui/settings/rules.py tests/test_rules_page.py
rtk git commit -m "fix(rules): show condition validation messages below the row

The feedback label was appended to the condition row's QHBoxLayout, so it
rendered to the right of the delete button in whatever width was left.
Wrap the row in a QVBoxLayout and give it one long-lived label underneath.
Renames condition_refs[\"value_layout\"] to \"row_layout\" -- the misleading
name is what put the label there in the first place."
```

---

### Task 2: Feedback stops depending on a value widget existing

`_show_validation_feedback()` returns early when there is no value widget, which gates
the *message* on something only the *border* needs. `_check_field_resolvable()` reports
a field the engine can never evaluate — a statement about the field combo — and a row
whose operator needs no value input would swallow it silently. Guard only the border.

The three near-identical styling branches collapse into a small lookup table in the
same edit; that duplication is what let the coupling hide.

**Files:**
- Modify: `gui/settings/rules.py` — `_show_validation_feedback()` (~912-960)
- Test: `tests/test_rules_page.py`

**Interfaces:**
- Consumes: `condition_refs["feedback_label"]` from Task 1 (always present).
- Produces: no new names. `_show_validation_feedback(condition_refs, status, message)`
  keeps its signature and its four statuses (`"error"`, `"warning"`, `"success"`,
  `"clear"`); any other status value is now treated as `"clear"` rather than silently
  doing nothing.

- [ ] **Step 1: Write the failing test**

Add to `TestValidationFeedbackPlacement` in `tests/test_rules_page.py`:

```python
    def test_unresolvable_field_reports_without_a_value_widget(self, qtbot, analysis_df):
        """The 'never match' message is about the field, not the value box, so a
        row with no value widget must still show it. No UI path reaches this
        state today -- the empty-check branch that would create it is dead code
        (design doc section 5, finding A) -- so the state is set directly here, to keep
        the guard from being reintroduced when that branch is fixed."""
        page = RulesPage([self._rule(field="item_count", operator="equals", value="2")], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)
        cond["feedback_label"].clear()
        cond["feedback_label"].hide()
        cond["value_widget"] = None

        assert page._check_field_resolvable(cond) is False

        assert "never match" in cond["feedback_label"].text()
        assert not cond["feedback_label"].isHidden()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_rules_page.py::TestValidationFeedbackPlacement::test_unresolvable_field_reports_without_a_value_widget -v
```

Expected: FAIL on `assert "never match" in ""` — `_show_validation_feedback` returned
early, so the label was never given text.

- [ ] **Step 3: Guard only the border**

In `_show_validation_feedback()`, replace the entire body after the docstring:

```python
        theme = get_theme_manager().get_current_theme()

        value_widget = condition_refs.get("value_widget")
        if not value_widget:
            return

        feedback_label = condition_refs["feedback_label"]

        # ponytail: literal validation-tint background colors, not worth new
        # ThemeTokens fields for ~2 call sites; revisit if more validation
        # states are added.
        if status == "error":
            value_widget.setStyleSheet(f"border: 1px solid {theme.accent_red}; background-color: #ffebee; color: #1A1A1A;")
            feedback_label.setStyleSheet(f"color: {theme.accent_red}; {font_css('caption')}")
            feedback_label.setText(f"{message}")
            feedback_label.show()

        elif status == "warning":
            value_widget.setStyleSheet(f"border: 1px solid {theme.accent_orange}; background-color: #fff3e0; color: #1A1A1A;")
            feedback_label.setStyleSheet(f"color: {theme.accent_orange}; {font_css('caption')}")
            feedback_label.setText(f"{message}")
            feedback_label.show()

        elif status == "success":
            value_widget.setStyleSheet(f"border: 1px solid {theme.accent_green};")
            feedback_label.setStyleSheet(f"color: {theme.accent_green}; {font_css('caption')}")
            feedback_label.setText(f"{message}")
            feedback_label.show()

        elif status == "clear":
            value_widget.setStyleSheet("")
            feedback_label.hide()
```

with:

```python
        theme = get_theme_manager().get_current_theme()

        # ponytail: literal validation-tint background colors, not worth new
        # ThemeTokens fields for ~2 call sites; revisit if more validation
        # states are added.
        border_css = {
            "error": f"border: 1px solid {theme.accent_red}; background-color: #ffebee; color: #1A1A1A;",
            "warning": f"border: 1px solid {theme.accent_orange}; background-color: #fff3e0; color: #1A1A1A;",
            "success": f"border: 1px solid {theme.accent_green};",
        }
        text_color = {
            "error": theme.accent_red,
            "warning": theme.accent_orange,
            "success": theme.accent_green,
        }
        if status not in text_color:
            status = "clear"

        # The message describes the condition; only the tinted border needs a
        # value widget. An operator that takes no value still has something to
        # say -- most of all that its field will never match.
        value_widget = condition_refs.get("value_widget")
        if value_widget is not None:
            value_widget.setStyleSheet(border_css.get(status, ""))

        feedback_label = condition_refs["feedback_label"]
        if status == "clear":
            feedback_label.clear()
            feedback_label.hide()
            return

        feedback_label.setStyleSheet(f"color: {text_color[status]}; {font_css('caption')}")
        feedback_label.setText(message)
        feedback_label.show()
```

Note: the docstring above this body still documents the four statuses correctly — leave
it, but if you touch it, do not claim the message requires a value widget.

- [ ] **Step 4: Run the test to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_rules_page.py -v
```

Expected: all three new tests PASS, every pre-existing test in the file still passes.

- [ ] **Step 5: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: the whole suite passes (580 tests passed on `d7059cb`, plus the 3 added here)
and ruff reports no issues. If a test outside `tests/test_rules_page.py` fails, do not
paper over it — it means something else reads the renamed key; find it and fix the
reference.

- [ ] **Step 6: Commit**

```bash
rtk git add gui/settings/rules.py tests/test_rules_page.py
rtk git commit -m "fix(rules): validation feedback no longer needs a value widget

_show_validation_feedback bailed out when there was no value widget, which
gated the message on something only the border needs -- so an unresolvable
field on a value-less condition reported nothing. Guard the border only, and
collapse the three duplicated styling branches into a lookup table."
```

- [ ] **Step 7: Refresh the knowledge graph**

```bash
graphify update .
```

Commit the result only if it produces a tracked diff.

---

## Verification before calling this done

- [ ] `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` — full suite green, output
      pasted into the completion note. No "should pass" claims without the run.
- [ ] `.venv/bin/ruff check . --exclude shared` — clean.
- [ ] `rtk grep -rn "value_layout" gui/ tests/` — no matches.
- [ ] `rtk git diff origin/main --stat` — only `gui/settings/rules.py`,
      `tests/test_rules_page.py`, and the two docs files. Nothing under `shared/`.
- [ ] Neither out-of-scope finding from design doc §5 was "helpfully" fixed.
