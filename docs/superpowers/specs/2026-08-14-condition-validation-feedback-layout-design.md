# Condition validation feedback — layout design

**Date:** 2026-08-14
**Status:** approved for implementation
**Ticket:** Todoist `6hGfgP9C7355Gm83` — "Fix: rule condition validation feedback is
unreadable (wrong layout)" (Phase 6, p3)
**Deferred out of:** PR #275

---

## 1. The report

> "incorrect REGEX doesn't flash"

The user types an invalid regular expression into a rule condition and sees no usable
error.

## 2. What is actually wrong

The validation *logic* is fine, and was verified headlessly before this design: an
invalid pattern does set the red border on the `QLineEdit`, does produce the text
`"Invalid regex syntax"`, and the 500 ms debounce timer does fire.

**The message is placed where nobody can read it.** In `gui/settings/rules.py`,
`condition_refs["value_layout"]` is the condition row's `QHBoxLayout` — the name says
"value" but the object is the whole row. `_show_validation_feedback()` calls
`addWidget(feedback_label)` on it, so the message is appended as the *last horizontal
cell* of the row, to the right of the "X" delete button, squeezed into whatever width is
left, word-wrapped (`setWordWrap(True)`) and carrying a `margin-top: 2px` styled for a
vertical layout it is not in.

Confirmed on the current tip of `main` (`d7059cb`) with a headless probe:

```
row layout children: ['WheelIgnoreComboBox', 'WheelIgnoreComboBox',
                      'QLineEdit', 'QPushButton', 'QLabel']
layout class: QHBoxLayout
label index in row: 4 of 5
text: 'Invalid regex syntax'
```

The label is index 4 — after the delete button. The same probe confirms the
`_check_field_resolvable()` "this condition will never match" message lands in exactly
the same dead spot.

## 3. Decision

**Wrap each condition row in a `QVBoxLayout`: the row on top, one feedback label
beneath it, full width.**

Two supporting decisions fall out of that:

### 3.1 The row owns its feedback label for its whole lifetime

Today the label is created lazily inside `_show_validation_feedback()` and destroyed in
`_on_rule_condition_changed()` (`deleteLater()` + `del`) every time the value widget is
swapped. That churn exists only because the label was parented to the value row.

Once the label lives in the outer vertical layout it has no reason to be rebuilt.
Create it once in `add_condition_row()`, hidden; clear and hide it on an operator change
instead of deleting it. This removes two blocks of code and replaces "does the label
exist?" with a flat invariant: **every condition row has exactly one feedback label**.

A hidden `QLabel` is excluded from its layout, so a row with no message keeps its
current height — no reserved blank line, and the row grows only while a message is up.
Rows shifting when a message appears is normal form-validation behaviour and is
preferred here over permanently reserving a line per condition.

### 3.2 Feedback must not depend on a value widget existing

`_show_validation_feedback()` currently opens with:

```python
value_widget = condition_refs.get("value_widget")
if not value_widget:
    return
```

That guard exists to style the value widget's border, but it gates the *message* too.
It is a landmine: `_check_field_resolvable()` reports a field the engine can never
evaluate, which is a statement about the field combo and has nothing to do with the
value widget. A row with no value widget would silently swallow it.

The guard does not misfire today — see §5 — but the whole point of this change is that
the message belongs to the row, not to the value widget. Guard only the border styling.

### 3.3 Rename `value_layout` → `row_layout`

The misleading name is the direct cause of the bug: a previous author read
`value_layout` and reasonably assumed appending to it put the widget under the value
field. Two call sites after the fix. Rename it.

## 4. Alternatives rejected

| Alternative | Why not |
|---|---|
| Show the message as a tooltip on the value widget | The complaint is that the feedback is not noticed. Hiding it behind a hover makes that strictly worse. |
| One shared message area per rule card | Loses attribution — a rule with four conditions cannot say *which* one is broken. |
| Leave the label in the row but give it a stretch factor / minimum width | Still competes with three widgets and a button for one line of horizontal space, and long messages ("'item_count' is not available on an article rule…") need a full-width line. |
| Reserve a permanent blank line under every row | Costs a line of vertical space per condition, forever, to avoid a shift the user only sees while typing an invalid value. |

## 5. Adjacent findings — deliberately out of scope

Both were found while verifying this design. Neither is a regression and neither belongs
in this change.

**A. The "hide the value widget" branch for empty-checks is dead code.**
`gui/settings/fields.py` offers the operators `"is empty"` / `"is not empty"` (spaces),
but `_on_rule_condition_changed()` tests `op in ["is_empty", "is_not_empty"]`
(underscores), so the branch never runs and an empty-check condition still shows a
pointless value box. **Not a correctness bug:** `shopify_tool/rules.py` maps
`"is empty"` → `_op_is_empty`, so saved rules evaluate correctly. It is cosmetic, it
predates this ticket, and fixing it would widen this diff and its test matrix. Worth its
own small ticket.

Note the interaction: because that branch is dead, `value_widget` is never `None` in
practice today, which is why the §3.2 guard has not yet bitten anyone. Whoever fixes
finding A must not reintroduce the coupling — §3.2 is what makes that fix safe.

**B. Hardcoded validation tint colours.** `_show_validation_feedback()` hardcodes
`#ffebee` / `#fff3e0` backgrounds and `#1A1A1A` text, against the repo's no-hardcoded-
colours rule. This is already marked with a `ponytail:` comment explaining the
trade-off (two call sites, not worth new `ThemeTokens` fields). Left as-is.

## 6. Scope

**In:** `gui/settings/rules.py` — `add_condition_row()`,
`_on_rule_condition_changed()`, `_show_validation_feedback()`. Tests in
`tests/test_rules_page.py`.

**Out:** the rule engine, the Rule Test dialog, the two findings in §5, and any change
to *what* the validators say — only *where* it is shown changes.

## 7. How we will know it worked

- The feedback label is not a child of the condition row's `QHBoxLayout`.
- It sits below the row in the wrapper's `QVBoxLayout`, at full row width.
- An unresolvable-field message appears even for a condition with no value widget.
- Changing the operator drops a stale message from the previous operator.
- `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` pass.
