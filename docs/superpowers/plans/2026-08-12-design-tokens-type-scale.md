# Design Tokens & Type Scale Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 55 hardcoded `font-size:` literals and 3 ad-hoc `QFont` sizings across `gui/*.py` with a 5-role type scale defined once in `gui/theme_manager.py`.

**Architecture:** A frozen `TypeStyle` dataclass and a `TYPE_SCALE` dict live in `gui/theme_manager.py` — the repo-owned seam, since `shared/theme.py` is sync-owned by `packing-tool` and `ThemeTokens` is frozen (so `dataclasses.replace()` cannot add size fields). Two helpers serve the two idioms already in the codebase: `font_css(role)` returns a QSS fragment for f-string stylesheets, `apply_font(target, role)` sets sizing on anything exposing `.font()`/`.setFont()`. Two tests act as guards — one against silent drift in `shared/theme.py`, one against future call sites bypassing the scale.

**Tech Stack:** Python 3, PySide6, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-12-design-tokens-type-scale-design.md`

## Global Constraints

- **Python is not on `PATH`.** Use `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python` and `.venv/bin/ruff`. Bare `python`/`ruff` fail with "command not found"; system `python3` has no PySide6.
- **Gate (must pass before the final commit):** `QT_QPA_PLATFORM=offscreen <venv>/python -m pytest` and `<venv>/ruff check . --exclude shared`.
- **Never edit anything under `shared/`.** It is one-way synced from `../packing-tool` and the next sync silently overwrites hand edits.
- **Never hardcode colors.** Use `theme.text_secondary`, `theme.border` etc. from `get_theme_manager().get_current_theme()`.
- **No direct commits to `main`.** This repo is PR-only, no exception for trivial changes.
- **Integer point sizes only.** Qt's QSS parser is unreliable on fractional `pt`.
- The five roles and their values are fixed by the spec: `caption` 9pt regular, `body` 10pt regular, `label` 12pt bold, `heading` 14pt bold, `display` 17pt bold.
- Run `graphify update .` after the code changes land.

## File Structure

| file | change | responsibility |
|---|---|---|
| `gui/theme_manager.py` | modify (99 lines today) | owns `TypeStyle`, `TYPE_SCALE`, `font_css`, `apply_font` alongside the existing `ThemeManager` |
| `tests/test_type_scale.py` | create | scale resolution, `apply_font` across target types, drift guard, bypass guard |
| `gui/ui_manager.py` | modify | 10 sites |
| `gui/settings_window_pyside.py` | modify | 14 QSS sites + 1 `QFont` site |
| `gui/client_settings_dialog.py` | modify | 5 sites |
| `gui/report_selection_dialog.py` | modify | 5 sites |
| `gui/rule_test_dialog.py` | modify | 5 sites |
| `gui/tag_categories_dialog.py` | modify | 3 sites |
| `gui/column_mapping_widget.py` | modify | 2 sites |
| `gui/barcode_generator_widget.py` | modify | 2 sites |
| `gui/client_card.py` | modify | 6 sites |
| `gui/client_sidebar.py` | modify | 3 QSS sites + 1 `QFont` site |
| `gui/tag_delegate.py` | modify | 1 `QFont` site |

No new modules. `gui/column_config_dialog.py:378,394` use `setBold` with **no** size and are deliberately left untouched.

---

### Task 1: The type scale and its helpers

**Files:**
- Modify: `gui/theme_manager.py` (add imports at line 8-9, add scale + helpers after the `get_theme_manager()` function at line 99)
- Test: `tests/test_type_scale.py` (create)

**Interfaces:**
- Consumes: `shared.theme.build_stylesheet`, `shared.theme.get_theme` (already imported at `gui/theme_manager.py:14`)
- Produces:
  - `TypeStyle` — frozen dataclass, fields `size_pt: int`, `bold: bool`
  - `TYPE_SCALE: dict[str, TypeStyle]` — keys `"caption"`, `"body"`, `"label"`, `"heading"`, `"display"`
  - `font_css(role: str, bold: bool | None = None) -> str`
  - `apply_font(target, role: str, bold: bool | None = None) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_type_scale.py`:

```python
"""The type scale is the single source of truth for font sizing in gui/*.py.

Two of these tests are guards rather than unit tests:
test_body_role_matches_shared_button_size catches shared/theme.py drifting
under us (it is sync-owned by packing-tool), and
test_no_hardcoded_font_sizes_outside_theme_manager stops future call sites
from bypassing the scale.
"""
import re
from pathlib import Path

import pytest
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QListWidgetItem

from gui.theme_manager import TYPE_SCALE, apply_font, font_css
from shared.theme import build_stylesheet, get_theme


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_scale_has_exactly_the_five_documented_roles():
    assert set(TYPE_SCALE) == {"caption", "body", "label", "heading", "display"}


@pytest.mark.parametrize("role,size_pt,bold", [
    ("caption", 9, False),
    ("body", 10, False),
    ("label", 12, True),
    ("heading", 14, True),
    ("display", 17, True),
])
def test_roles_resolve_to_expected_size_and_weight(role, size_pt, bold):
    assert TYPE_SCALE[role].size_pt == size_pt
    assert TYPE_SCALE[role].bold is bold


def test_font_css_emits_size_and_explicit_weight():
    assert font_css("caption") == "font-size: 9pt; font-weight: normal;"
    assert font_css("label") == "font-size: 12pt; font-weight: bold;"


def test_font_css_bold_override_wins_in_both_directions():
    assert font_css("caption", bold=True) == "font-size: 9pt; font-weight: bold;"
    assert font_css("label", bold=False) == "font-size: 12pt; font-weight: normal;"


def test_unknown_role_raises_rather_than_falling_back():
    with pytest.raises(KeyError):
        font_css("subheading")


def test_apply_font_sets_size_and_weight_on_a_widget():
    label = QLabel("x")
    apply_font(label, "heading")
    assert label.font().pointSize() == 14
    assert label.font().bold() is True


def test_apply_font_preserves_the_existing_family():
    label = QLabel("x")
    font = label.font()
    font.setFamily("Courier New")
    label.setFont(font)
    apply_font(label, "caption")
    assert label.font().family() == "Courier New"
    assert label.font().pointSize() == 9


def test_apply_font_works_on_a_list_item_and_a_painter():
    item = QListWidgetItem("x")
    apply_font(item, "caption", bold=True)
    assert item.font().pointSize() == 9
    assert item.font().bold() is True

    pixmap = QPixmap(10, 10)
    painter = QPainter(pixmap)
    try:
        apply_font(painter, "display")
        assert painter.font().pointSize() == 17
        assert painter.font().bold() is True
    finally:
        painter.end()


def test_body_role_matches_shared_button_size():
    """shared/theme.py is synced from packing-tool and can change without
    warning. If its QPushButton size stops matching the body role, buttons
    silently fall off the scale -- fail loudly instead."""
    sheet = build_stylesheet(get_theme("light"))
    match = re.search(r"QPushButton\s*\{[^}]*font-size:\s*(\d+)pt", sheet)
    assert match, "shared/theme.py no longer sets a pt font-size on QPushButton"
    assert int(match.group(1)) == TYPE_SCALE["body"].size_pt
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_type_scale.py -v`

Expected: collection error — `ImportError: cannot import name 'TYPE_SCALE' from 'gui.theme_manager'`.

- [ ] **Step 3: Implement the scale and helpers**

In `gui/theme_manager.py`, change the imports at lines 8-9 from:

```python
import logging
from typing import Optional
```

to:

```python
import logging
from dataclasses import dataclass
from typing import Optional
```

Then append to the end of the file (after `get_theme_manager()` at line 99):

```python
@dataclass(frozen=True)
class TypeStyle:
    """One rung of the type scale: a point size and a default weight."""
    size_pt: int
    bold: bool


# 1.20 modular ratio anchored on a 10pt body: 10 -> 12 -> 14.4 -> 17.28,
# rounded to integers because Qt's QSS parser is unreliable on fractional pt.
# `caption` is 9pt rather than the geometric 8.33pt -- a deliberate legibility
# floor for warehouse-floor use. See the 2026-08-12 design spec.
TYPE_SCALE: dict[str, TypeStyle] = {
    "caption": TypeStyle(9, False),   # hints, tips, feedback, dense card labels
    "body": TypeStyle(10, False),     # default text and button labels
    "label": TypeStyle(12, True),     # emphasis, sub-headers, count badges
    "heading": TypeStyle(14, True),   # dialog and section headers
    "display": TypeStyle(17, True),   # stat-card numbers
}


def font_css(role: str, bold: bool | None = None) -> str:
    """QSS fragment for f-string stylesheets, e.g. 'font-size: 12pt; font-weight: bold;'.

    Raises KeyError on an unknown role -- a typo must fail during development
    rather than silently render at some default size in production.
    """
    style = TYPE_SCALE[role]
    weight = "bold" if (style.bold if bold is None else bold) else "normal"
    return f"font-size: {style.size_pt}pt; font-weight: {weight};"


def apply_font(target, role: str, bold: bool | None = None) -> None:
    """Apply a scale role to anything exposing .font()/.setFont().

    Covers QWidget, QListWidgetItem and QPainter with one helper. Reads the
    target's existing font so the inherited family survives -- building a bare
    QFont() instead would silently drop it.
    """
    style = TYPE_SCALE[role]
    font = target.font()
    font.setPointSize(style.size_pt)
    font.setBold(style.bold if bold is None else bold)
    target.setFont(font)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_type_scale.py -v`

Expected: PASS, 13 tests (the 5-way parametrize counts as 5).

- [ ] **Step 5: Lint**

Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check gui/theme_manager.py tests/test_type_scale.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add gui/theme_manager.py tests/test_type_scale.py
git commit -m "Add TYPE_SCALE with font_css/apply_font helpers"
```

---

### Task 2: Migrate `gui/ui_manager.py`

The highest-visual-risk file — every `px` site lives here, and these are the Statistics-tab cards.

**Files:**
- Modify: `gui/ui_manager.py` (10 sites)

**Interfaces:**
- Consumes: `font_css` from Task 1

**Site map:**

| line | current | replacement role |
|---|---|---|
| 168 | `"font-weight: bold; font-size: 11pt;"` | `label` |
| 328 | `"font-size: 11pt; font-weight: bold;"` | `label` |
| 777 | `font-size: 11pt;` + `font-weight: bold;` (inside a plain triple-quoted block) | `label` |
| 1603 | `"font-size: 20px; font-weight: bold;"` | `display` |
| 1608 | `"font-size: 10px;"` | `caption` |
| 1626 | `"font-size: 20px; font-weight: bold;"` | `display` |
| 1630 | `"font-size: 11px;"` | `caption` |
| 1634 | `"font-size: 10px;"` | `caption` |
| 1659 | `f"font-size: 14px; font-weight: bold; color: white; "` | `label` |
| 1666 | `"font-size: 10px;"` | `caption` |

- [ ] **Step 1: Add the import**

This file uses a **relative** import at line 34 (unlike the rest of `gui/`, which uses absolute). Keep that style:

```python
# gui/ui_manager.py:34 — before
from .theme_manager import get_theme_manager
# after
from .theme_manager import font_css, get_theme_manager
```

- [ ] **Step 2: Migrate the simple single-line sites**

Each becomes an f-string interpolating `font_css`. Plain strings must gain an `f` prefix:

```python
# line 328 — before
title.setStyleSheet("font-size: 11pt; font-weight: bold;")
# after
title.setStyleSheet(f"{font_css('label')}")
```

```python
# line 1603 — before
value_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")
# after
value_lbl.setStyleSheet(font_css("display"))
```

Where `font_css(...)` is the *entire* stylesheet, pass it directly (no f-string wrapper) as in the 1603 example. Apply the same to lines 1608, 1626, 1630, 1634, 1666.

```python
# line 1659 — before
count_lbl.setStyleSheet(
    f"font-size: 14px; font-weight: bold; color: white; "
    f"background-color: {color}; border-radius: 8px; padding: 2px 6px;"
)
# after
count_lbl.setStyleSheet(
    f"{font_css('label')} color: white; "
    f"background-color: {color}; border-radius: 8px; padding: 2px 6px;"
)
```

- [ ] **Step 3: Migrate line 777 — the non-f-string block**

**This one has a trap.** The block at `gui/ui_manager.py:775-780` is a *plain* triple-quoted string, so converting it to an f-string requires doubling every existing brace:

```python
# before
self.mw.run_analysis_button.setStyleSheet("""
    QPushButton {
        font-size: 11pt;
        font-weight: bold;
    }
""")
# after
self.mw.run_analysis_button.setStyleSheet(f"""
    QPushButton {{
        {font_css('label')}
    }}
""")
```

- [ ] **Step 4: Verify no font-size literals remain in this file**

Run: `grep -n "font-size\|setPointSize" gui/ui_manager.py`

Expected: no output.

- [ ] **Step 5: Run the affected tests and lint**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_main_window_statistics.py tests/test_main_window_tags.py -v`
Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check gui/ui_manager.py`

Expected: PASS and `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add gui/ui_manager.py
git commit -m "Migrate ui_manager font sizes to the type scale"
```

---

### Task 3: Migrate `gui/settings_window_pyside.py`

**Files:**
- Modify: `gui/settings_window_pyside.py` (14 QSS sites + 1 `QFont` site)

**Interfaces:**
- Consumes: `font_css`, `apply_font` from Task 1

**Site map:**

| line | current | replacement role |
|---|---|---|
| 250 | `font.setPointSize(max(font.pointSize() - 1, 7))` + `font.setBold(True)` | `apply_font(header, "caption", bold=True)` |
| 533 | `font-size: 9pt` | `caption` |
| 594 | `font-weight: bold; ... font-size: 11pt` | `label` |
| 737 | `font-weight: bold; font-size: 11pt` | `label` |
| 1143 | `font-size: 9pt; margin-top: 2px;` | `caption` |
| 1154 | `font-size: 9pt` | `caption` |
| 1160 | `font-size: 9pt` | `caption` |
| 1166 | `font-size: 9pt` | `caption` |
| 1804 | `font-style: italic; font-size: 10pt` | `body` |
| 1902 | `"font-size: 14pt; font-weight: bold;"` | `heading` |
| 1957 | `font-size: 9pt; margin-top: 10px;` | `caption` |
| 2215 | `font-size: 9pt` | `caption` |
| 2367 | `font-size: 9pt` | `caption` |
| 3356 | `"font-size: 14pt; font-weight: bold;"` | `heading` |
| 3448 | `font-style: italic; font-size: 9pt; margin-top: 10px;` | `caption` |

- [ ] **Step 1: Add a module-level import**

This file uses *function-local* `from gui.theme_manager import get_theme_manager` imports in ~11 places. Do **not** thread `font_css` through all of them — `font_css` needs no theme instance. Add one module-level import next to the other `gui.` imports at the top of the file:

```python
from gui.theme_manager import apply_font, font_css
```

This cannot introduce a circular import: `gui/theme_manager.py` imports only `logging`, `dataclasses`, `typing`, `PySide6` and `shared.theme` — nothing from `gui`.

- [ ] **Step 2: Migrate the 14 QSS sites**

Pattern, keeping every non-font declaration untouched:

```python
# line 533 — before
self.rules_count_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt;")
# after
self.rules_count_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
```

```python
# line 594 — before
priority_label.setStyleSheet(f"font-weight: bold; color: {theme.accent_blue}; font-size: 11pt;")
# after
priority_label.setStyleSheet(f"{font_css('label')} color: {theme.accent_blue};")
```

```python
# line 1902 — before
header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
# after
header_label.setStyleSheet(font_css("heading"))
```

```python
# line 3448 — before
tips_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; font-size: 9pt; margin-top: 10px;")
# after
tips_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; {font_css('caption')} margin-top: 10px;")
```

Note the `font-weight: bold` at lines 594 and 737 is absorbed by the `label` role — delete the standalone declaration rather than leaving it duplicated.

- [ ] **Step 3: Migrate the nav overline at line 250**

```python
# before
header = QListWidgetItem(group_name.upper())
header.setFlags(Qt.ItemFlag.NoItemFlags)
font = header.font()
font.setPointSize(max(font.pointSize() - 1, 7))
font.setBold(True)
header.setFont(font)
# after
header = QListWidgetItem(group_name.upper())
header.setFlags(Qt.ItemFlag.NoItemFlags)
apply_font(header, "caption", bold=True)
```

This trades a relative size (one step below inherited, floored at 7pt) for the absolute `caption` 9pt — intended, per the spec's call-site mapping.

- [ ] **Step 4: Verify no font sizing literals remain in this file**

Run: `grep -n "font-size\|setPointSize" gui/settings_window_pyside.py`

Expected: no output.

- [ ] **Step 5: Run the affected tests and lint**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_settings_window_weight_quick_add.py -v`
Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check gui/settings_window_pyside.py`

Expected: PASS and `All checks passed!`.

- [ ] **Step 6: Commit**

```bash
git add gui/settings_window_pyside.py
git commit -m "Migrate settings window font sizes to the type scale"
```

---

### Task 4: Migrate the dialog files

**Files:**
- Modify: `gui/client_settings_dialog.py` (5), `gui/rule_test_dialog.py` (5), `gui/report_selection_dialog.py` (5), `gui/tag_categories_dialog.py` (3), `gui/column_mapping_widget.py` (2), `gui/barcode_generator_widget.py` (2)

**Interfaces:**
- Consumes: `font_css` from Task 1

**Site map:**

| file:line | current | replacement role |
|---|---|---|
| `client_settings_dialog.py:114` | `font-size: 10pt; padding: 10px;` | `body` |
| `client_settings_dialog.py:445` | `font-size: 9pt; padding: 10px;` | `caption` |
| `client_settings_dialog.py:490` | `font-size: 9pt; padding: 10px;` | `caption` |
| `client_settings_dialog.py:519` | `font-size: 9pt; padding: 10px;` | `caption` |
| `client_settings_dialog.py:535` | `font-size: 10pt; padding: 20px;` | `body` |
| `rule_test_dialog.py:119` | `font-weight: bold; font-size: 11pt; margin-top: 10px;` | `label` |
| `rule_test_dialog.py:132` | `font-style: italic; font-size: 9pt;` | `caption` |
| `rule_test_dialog.py:152` | `"font-size: 10pt;"` | `body` |
| `rule_test_dialog.py:173` | `font-size: 9pt; margin-top: 5px;` | `caption` |
| `rule_test_dialog.py:275` | `font-size: 14pt` inside an inline HTML `<span style=...>` | `heading` |
| `report_selection_dialog.py:111` | `font-size: 13px;` + `font-weight: bold;` | `body`, `bold=True` |
| `report_selection_dialog.py:238` | `font-weight: bold; font-size: 11pt; padding-bottom: 4px;` | `label` |
| `report_selection_dialog.py:265` | `font-size: 10pt; padding: 2px;` | `body` |
| `report_selection_dialog.py:273` | `font-size: 9pt` | `caption` |
| `report_selection_dialog.py:292` | `font-size: 13px;` + `font-weight: bold;` | `body`, `bold=True` |
| `tag_categories_dialog.py:102` | `font-weight: bold; font-size: 11pt; padding: 5px;` | `label` |
| `tag_categories_dialog.py:133` | `font-weight: bold; font-size: 11pt; padding: 5px;` | `label` |
| `tag_categories_dialog.py:738` | `font-size: 14pt; font-weight: bold; padding: 10px;` | `heading` |
| `column_mapping_widget.py:140` | `"font-size: 14pt; font-weight: bold;"` | `heading` |
| `column_mapping_widget.py:152` | `color: red; font-size: 16pt; font-weight: bold;` | `heading` |
| `barcode_generator_widget.py:123` | `font-size: 9pt; padding: 5px;` | `caption` |
| `barcode_generator_widget.py:251` | `font-size: 16px;` + `font-weight: bold;` | `label` |

- [ ] **Step 1: Add imports**

Each of these six files already has a module-level `from gui.theme_manager import get_theme_manager`. Extend it:

```python
from gui.theme_manager import font_css, get_theme_manager
```

- [ ] **Step 2: Migrate the plain `setStyleSheet` sites**

```python
# client_settings_dialog.py:445 — before
info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 10px;")
# after
info_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')} padding: 10px;")
```

```python
# column_mapping_widget.py:152 — before
required_indicator.setStyleSheet("color: red; font-size: 16pt; font-weight: bold;")
# after
required_indicator.setStyleSheet(f"color: red; {font_css('heading')}")
```

Note: `color: red` here is a pre-existing hardcoded color. It is **out of scope** for this task — do not "fix" it to a theme token; that is Track 3's concern and would widen the diff.

- [ ] **Step 3: Migrate the two multi-line QSS blocks**

`report_selection_dialog.py:105-115` and `:286-296` are already f-strings with doubled braces, so only the declaration changes:

```python
# report_selection_dialog.py:111 — before
button.setStyleSheet(f"""
    QPushButton {{
        background-color: {theme.accent_blue};
        color: white;
        padding: 10px;
        font-size: 13px;
        font-weight: bold;
        ...
# after
button.setStyleSheet(f"""
    QPushButton {{
        background-color: {theme.accent_blue};
        color: white;
        padding: 10px;
        {font_css('body', bold=True)}
        ...
```

Apply the same at `:292`. `barcode_generator_widget.py:249-256` is likewise already an f-string:

```python
# barcode_generator_widget.py:251 — before
font-size: 16px;
font-weight: bold;
# after
{font_css('label')}
```

- [ ] **Step 4: Migrate the inline HTML span at `rule_test_dialog.py:275`**

This is HTML rendered by a `QLabel`, not a stylesheet, but the same fragment is valid inline CSS:

```python
# before
summary += f"<span style='color: {theme.accent_green}; font-size: 14pt;'>{self.matched_count}</span> rows affected "
# after
summary += f"<span style='color: {theme.accent_green}; {font_css('heading')}'>{self.matched_count}</span> rows affected "
```

Note the quoting: the span attribute uses single quotes and `font_css('heading')` reuses single quotes inside the f-string expression. That is legal here — the venv runs Python 3.14.4, well past the 3.12 floor where nested same-quote f-strings became valid.

- [ ] **Step 5: Verify no font-size literals remain in these six files**

Run: `grep -n "font-size\|setPointSize" gui/client_settings_dialog.py gui/rule_test_dialog.py gui/report_selection_dialog.py gui/tag_categories_dialog.py gui/column_mapping_widget.py gui/barcode_generator_widget.py`

Expected: no output.

- [ ] **Step 6: Run the affected tests and lint**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_tag_categories_dialog.py tests/test_barcode_generator_widget.py -v`
Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check gui/`

Expected: PASS and `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add gui/client_settings_dialog.py gui/rule_test_dialog.py gui/report_selection_dialog.py gui/tag_categories_dialog.py gui/column_mapping_widget.py gui/barcode_generator_widget.py
git commit -m "Migrate dialog font sizes to the type scale"
```

---

### Task 5: Migrate the client card, sidebar and tag delegate

The one task where a mechanical sweep would introduce a bug — read Step 2 before touching `client_card.py`.

**Files:**
- Modify: `gui/client_card.py` (6), `gui/client_sidebar.py` (3 QSS + 1 `QFont`), `gui/tag_delegate.py` (1 `QFont`)

**Interfaces:**
- Consumes: `font_css`, `apply_font` from Task 1

**Site map:**

| file:line | current | replacement role |
|---|---|---|
| `client_card.py:152` | `font-size: 12pt; font-weight: bold;` (**selected** state) | `label` |
| `client_card.py:155` | `font-size: 12pt;` (**unselected** state) | `label`, `bold=False` |
| `client_card.py:158` | `font-size: 9pt` | `caption` |
| `client_card.py:159` | `font-size: 9pt` | `caption` |
| `client_card.py:163` | `font-size: 9pt; ... font-weight: bold;` | `caption`, `bold=True` |
| `client_card.py:245` | `font-size: 9pt; ... font-weight: bold;` | `caption`, `bold=True` |
| `client_sidebar.py:74` | `font.setPointSize(14)` + `font.setBold(True)` on a `QPainter` | `apply_font(painter, "heading")` |
| `client_sidebar.py:112` | `font-size: 10pt;` (in an f-string QSS block) | `body` |
| `client_sidebar.py:836` | `font-weight: bold; font-size: 11pt;` | `label` |
| `client_sidebar.py:846` | `font-size: 10pt;` (in an f-string QSS block) | `body` |
| `tag_delegate.py:53` | `font = QFont()` + `font.setPointSize(8)` | `apply_font(painter, "caption")` |

- [ ] **Step 1: Add imports**

`client_card.py:14` and `client_sidebar.py:36` both already import `get_theme_manager` absolutely — extend those lines:

```python
from gui.theme_manager import apply_font, font_css, get_theme_manager
```

`tag_delegate.py` has **no** `theme_manager` import at all. Add one after its existing `shopify_tool` import at line 7:

```python
from gui.theme_manager import apply_font
```

- [ ] **Step 2: Migrate `client_card.py` — preserve the selection indicator**

Lines 152 and 155 are the two branches of one `if selected:`. The **bold-vs-regular difference is the selection indicator** — collapsing both onto the bold `label` role would silently delete it. Keep the weights distinct:

```python
# before
if selected:
    self.name_label.setStyleSheet(f"font-size: 12pt; font-weight: bold; color: {theme.text};")
else:
    self.name_label.setStyleSheet(f"font-size: 12pt; color: {theme.text};")
# after
if selected:
    self.name_label.setStyleSheet(f"{font_css('label')} color: {theme.text};")
else:
    self.name_label.setStyleSheet(f"{font_css('label', bold=False)} color: {theme.text};")
```

The remaining four are direct:

```python
# line 158 — before
self.last_session_label.setStyleSheet(f"font-size: 9pt; color: {theme.text_secondary};")
# after
self.last_session_label.setStyleSheet(f"{font_css('caption')} color: {theme.text_secondary};")
```

```python
# lines 163 and 245 — before
self.badges_label.setStyleSheet(f"font-size: 9pt; color: {theme.accent_orange}; font-weight: bold;")
# after
self.badges_label.setStyleSheet(f"{font_css('caption', bold=True)} color: {theme.accent_orange};")
```

- [ ] **Step 3: Migrate `client_sidebar.py`**

The painted avatar initial at line 70-77 — note the redundant `painter.setFont(painter.font())` on line 72 goes away with it:

```python
# before
painter.setPen(QColor(Qt.white))
painter.setFont(painter.font())
font = painter.font()
font.setPointSize(14)
font.setBold(True)
painter.setFont(font)
painter.drawText(5, 5, 30, 30, Qt.AlignCenter, self.client_id[0].upper())
# after
painter.setPen(QColor(Qt.white))
apply_font(painter, "heading")
painter.drawText(5, 5, 30, 30, Qt.AlignCenter, self.client_id[0].upper())
```

Lines 112 and 846 sit in f-string QSS blocks that already use doubled braces — replace the `font-size: 10pt;` declaration with `{font_css('body')}`. At line 112 the block also carries a separate `font-weight: bold;`; replace both with `{font_css('body', bold=True)}`.

Line 836:

```python
# before
self.title_label.setStyleSheet(f"font-weight: bold; font-size: 11pt; color: {theme.text};")
# after
self.title_label.setStyleSheet(f"{font_css('label')} color: {theme.text};")
```

- [ ] **Step 4: Migrate `tag_delegate.py`**

Building a bare `QFont()` drops the inherited family; reading the painter's font keeps it:

```python
# before
font = QFont()
font.setPointSize(8)
painter.setFont(font)
metrics = painter.fontMetrics()
# after
apply_font(painter, "caption")
metrics = painter.fontMetrics()
```

Line 52 is `QFont`'s only use in this file, so drop it from the line 4 import — but **keep `QFontMetrics`**, which line 88 still uses:

```python
# gui/tag_delegate.py:4 — before
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
# after
from PySide6.QtGui import QColor, QFontMetrics, QPen
```

- [ ] **Step 5: Verify no font sizing literals remain in these three files**

Run: `grep -n "font-size\|setPointSize" gui/client_card.py gui/client_sidebar.py gui/tag_delegate.py`

Expected: no output.

- [ ] **Step 6: Run the affected tests and lint**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_client_sidebar_refresh.py -v`
Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check gui/`

Expected: PASS and `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add gui/client_card.py gui/client_sidebar.py gui/tag_delegate.py
git commit -m "Migrate client card, sidebar and tag delegate to the type scale"
```

---

### Task 6: Lock the scale in with a bypass guard

Every call site is migrated by now, so this guard can be absolute — no allowlist to maintain.

**Files:**
- Modify: `tests/test_type_scale.py`

**Interfaces:**
- Consumes: the fully migrated `gui/*.py` from Tasks 2-5

- [ ] **Step 1: Write the failing test**

Append to `tests/test_type_scale.py`:

```python
GUI_DIR = Path(__file__).resolve().parent.parent / "gui"


def test_no_hardcoded_font_sizes_outside_theme_manager():
    """The scale is only worth having if it cannot be bypassed. A new dialog
    that hardcodes a size turns this red instead of quietly drifting."""
    offenders = []
    for path in sorted(GUI_DIR.glob("*.py")):
        if path.name == "theme_manager.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "font-size:" in line or "setPointSize" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use theme_manager.font_css()/apply_font() instead of hardcoding sizes:\n"
        + "\n".join(offenders)
    )
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_type_scale.py::test_no_hardcoded_font_sizes_outside_theme_manager -v`

Expected: PASS. If it fails, the assertion message lists exactly which sites Tasks 2-5 missed — migrate those and re-run. Do **not** add an allowlist to make it pass.

- [ ] **Step 3: Run the full gate**

Run: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest`
Run: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared`

Expected: all tests pass — 382 on `main` at `241c6f7` plus the 14 new ones (13 from Task 1 + this guard) — and `All checks passed!`. Report the actual counts; do not claim success without the output.

- [ ] **Step 4: Update the knowledge graph**

Run: `graphify update .`

- [ ] **Step 5: Commit**

```bash
git add tests/test_type_scale.py
git commit -m "Guard against bypassing the type scale"
```

---

## Notes for the reviewer

- **This has not been seen on Windows.** Development is on Ubuntu; production is Windows 10/11 only. Sizes were chosen against Qt's 96dpi point-to-pixel math. The Statistics tab is the surface most likely to want a tweak — its cards previously used `20px`/`10px` and now use `display` 17pt / `caption` 9pt, so it will read visibly chunkier. Cards have no fixed heights (`QVBoxLayout` + `setMinimumWidth` + `setWordWrap`, inside a scroll area), so they grow rather than clip.
- Any post-merge size adjustment is a one-line edit to `TYPE_SCALE`. That is the point of centralizing it, and it does not block merging.
- The `px` → `pt` conversion is a fix, not only a cleanup: Qt treats QSS `px` as device pixels, so those sites previously ignored the Windows DPI setting while the rest of the UI honored it.
