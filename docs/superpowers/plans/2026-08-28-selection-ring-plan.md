# Selection Ring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Runner note:** the autonomous roadmap runner declines subagent-driven-development at Stage B and stays in-session with `superpowers:executing-plans`.

**Goal:** Replace the `accent_fill` item-view selection with the design system's 2px `selection_border` ring on `selection_bg`, in both apps, deleting the three 1e workarounds it was invented to justify.

**Architecture:** `shared/theme.py` is authored in **packing-tool** and pulled into shopify with `scripts/sync_shared.py` — so Tasks 1–4 happen in packing-tool, Task 5 syncs, and Tasks 6–7 delete shopify's now-dead workarounds. QSS styles cells, not rows, so a table row's ring is a top-and-bottom band (verified by pixel probe) while a list item gets a true four-sided ring. `QPalette` and `QMenu` keep the accent fill deliberately.

**Tech Stack:** Python 3, PySide6, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-28-selection-ring-design.md` (in shopify-fulfillment-tool; read it alongside this plan)

## Global Constraints

- **Never hand-edit shopify's `shared/`.** Author in packing-tool, then run `python scripts/sync_shared.py <packing-tool-path>` from shopify. From a worktree the sibling default does not resolve, so the path argument is **required**.
- **Never re-derive a hex.** Every value is in the spec §3 with a measured ratio.
- `python`/`ruff` are **not on PATH**. Use `.venv/bin/python` and `.venv/bin/ruff` in each repo. Run `./scripts/setup_venv.sh` first in the shopify worktree.
- Gates — shopify: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check . --exclude shared`. packing-tool: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check .`.
- The ten legacy aliases (`active_background`, `active_border`, …) are **read-only**; no new call site may read one. Use `selection_bg` / `selection_border` directly.
- Branch `worktree-selection-ring` in both repos. Never commit to `main`; never force-push.
- Both PRs merge together — shopify's deletions assume the synced `shared/theme.py`.

**Worktrees:**
- packing-tool: `~/Desktop/Projects/packing-tool/.claude/worktrees/worktree-selection-ring`
- shopify: `~/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/worktree-selection-ring`

---

### Task 1: Validate the selection plane (packing-tool)

The matrix that would have caught the original defect. It comes first so every later task is measured against it.

**Files:**
- Modify: `shared/theme.py` — `_MIN_CONTRAST_ON_PLANES` region (~line 264) and `validate_theme` (~line 339)
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validate_theme` raises `ValueError` when any of `text`, `text_secondary`, `status_info`, `status_success`, `status_warning`, `status_danger` falls below 4.5:1 on `selection_bg`, or `selection_border` below 3.0:1 on `selection_bg`. Module constant `_SELECTION_FOREGROUNDS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`:

```python
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("token", [
    "text", "text_secondary",
    "status_info", "status_success", "status_warning", "status_danger",
])
def test_foregrounds_clear_aa_on_the_selection_plane(theme, token):
    """A selected row is a background like any other plane.

    Nothing measured it while selection was accent_fill, which is how the
    status dot shipped at 1.05:1 on a selected row (spec 2026-08-28 section 1).
    """
    ratio = contrast_ratio(getattr(theme, token), theme.selection_bg)
    assert ratio >= 4.5, f"{theme.name}.{token} on selection_bg = {ratio:.2f}"


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_the_ring_reads_against_the_fill_it_encloses(theme):
    # 3.0 is WCAG's non-text minimum. Measured 4.75 light / 4.80 dark.
    ratio = contrast_ratio(theme.selection_border, theme.selection_bg)
    assert ratio >= 3.0, f"{theme.name} ring on selection_bg = {ratio:.2f}"


def test_validate_theme_rejects_a_foreground_that_fails_on_selection_bg():
    import dataclasses
    broken = dataclasses.replace(DARK_THEME, status_info=DARK_THEME.selection_bg)
    with pytest.raises(ValueError, match="selection_bg"):
        validate_theme(broken)
```

Ensure `validate_theme` is imported in that file's import block; add it if absent.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd ~/Desktop/Projects/packing-tool/.claude/worktrees/worktree-selection-ring
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k selection -v
```

Expected: the two ratio tests PASS (the tokens are already good), and
`test_validate_theme_rejects_a_foreground_that_fails_on_selection_bg` FAILS with
`DID NOT RAISE`. That failure is the one that matters — it proves the gate is missing.

- [ ] **Step 3: Add the matrix to `validate_theme`**

Add the constant next to `_STATUS_ROLES` (~line 276):

```python
# Foregrounds that can land on a selected row. Selection is selection_bg with
# a selection_border ring, so the selected row is a fifth plane -- it is just
# not a `surface_*` one, which is exactly why it escaped _SURFACE_PLANES.
_SELECTION_FOREGROUNDS = (
    "text", "text_secondary",
    "status_info", "status_success", "status_warning", "status_danger",
)
```

Then replace the existing `selected_text` block at the end of `validate_theme`:

```python
    for token in _SELECTION_FOREGROUNDS:
        ratio = contrast_ratio(getattr(theme, token), theme.selection_bg)
        if ratio < 4.5:
            raise ValueError(
                f"{theme.name}.{token} has {ratio:.2f}:1 contrast against "
                f"selection_bg, below the 4.5:1 minimum"
            )

    ring = contrast_ratio(theme.selection_border, theme.selection_bg)
    if ring < 3.0:
        raise ValueError(
            f"{theme.name}.selection_border has {ring:.2f}:1 contrast against "
            f"selection_bg, below the 3.0:1 minimum"
        )
```

The old two-line `selected_text` check is subsumed by `"text"` in the tuple — delete it rather than leaving both.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/theme.py tests/test_theme.py
git commit -m "theme: validate every foreground against selection_bg

The selected row is a plane like any other, but it is not a surface_*
one, so it escaped the _SURFACE_PLANES matrix entirely. That is how the
1e status dot shipped at 1.05:1 on a selected row."
```

---

### Task 2: The ring itself (packing-tool)

**Files:**
- Modify: `shared/theme.py` — `QTableView::item` rules (~line 682), `QListWidget::item` rules (~line 701)
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: Task 1's validated tokens.
- Produces: `build_stylesheet(theme)` emits `selection_bg`/`selection_border` for `QTableView::item:selected` and `QListWidget::item:selected`, and no longer emits `accent_fill` in either rule.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`:

```python
def _rule(qss: str, selector: str) -> str:
    """The declaration block for one selector, so a test asserts about the
    rule it means rather than about the whole sheet."""
    start = qss.index(selector + " {")
    return qss[start:qss.index("}", start)]


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("selector", [
    "QTableView::item:selected", "QListWidget::item:selected",
])
def test_selection_is_a_ring_and_not_an_accent_fill(theme, selector):
    rule = _rule(build_stylesheet(theme), selector)
    assert theme.selection_bg in rule
    assert theme.selection_border in rule
    assert theme.accent_fill not in rule
    assert theme.on_accent not in rule


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("selector", ["QTableView::item", "QListWidget::item"])
def test_unselected_items_reserve_the_ring_so_selecting_does_not_shift_text(
    theme, selector
):
    # Same trick as QListWidget#settingsNav::item in shopify's theme_manager.
    rule = _rule(build_stylesheet(theme), selector)
    assert "2px solid transparent" in rule


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_a_table_row_ring_is_top_and_bottom_only(theme):
    """QSS styles cells, not rows: a four-sided border on ::item would draw a
    box around every cell in the row. Top and bottom join across cell edges
    into one band. A list item is one full-width cell, so it rings fully."""
    rule = _rule(build_stylesheet(theme), "QTableView::item:selected")
    assert "border-top" in rule and "border-bottom" in rule
    assert "border:" not in rule


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_hovering_a_selected_row_does_not_erase_the_selection(theme):
    # ::item:hover follows ::item:selected at equal specificity, so without
    # this rule the later one wins and hover blanks the selection.
    qss = build_stylesheet(theme)
    assert "QTableView::item:selected:hover" in qss
    assert "QListWidget::item:selected:hover" in qss
```

Add `build_stylesheet` to the file's imports if absent.

- [ ] **Step 2: Run to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k "ring or selection_is or shift_text or hovering" -v
```

Expected: FAIL — `accent_fill` still present, no transparent counter-rule, no `:selected:hover`.

- [ ] **Step 3: Replace the rules**

In `build_stylesheet`, replace the single `QTableView::item:selected` line (~682) with:

```python
        QTableView::item {{
            border-top: 2px solid transparent;
            border-bottom: 2px solid transparent;
        }}
        QTableView::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border-top: 2px solid {theme.selection_border};
            border-bottom: 2px solid {theme.selection_border};
        }}
        QTableView::item:selected:hover {{ background-color: {theme.selection_bg}; }}
```

Keep the existing `QTableView::item:hover` line where it is, immediately after these.

Replace the `QListWidget::item:selected` line (~701) with:

```python
        QListWidget::item {{ border: 2px solid transparent; }}
        QListWidget::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border: 2px solid {theme.selection_border};
            border-radius: {r}px;
        }}
        QListWidget::item:selected:hover {{ background-color: {theme.selection_bg}; }}
```

`r` is already the local radius variable used elsewhere in this function — confirm its name at the top of `build_stylesheet` and match it.

**Do not touch** `QMenu::item:selected` (~744), the `QComboBox` `selection-background-color` (~628), or `build_palette` (~774). Spec §5 explains why: `packer_mode_widget.py:510` reads `palette.color(Highlight).lighter(180)`, which goes near-white if the palette moves to `selection_bg`.

- [ ] **Step 4: Run to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/theme.py tests/test_theme.py
git commit -m "theme: selection becomes a selection_border ring on selection_bg

QSS styles cells, not rows, so a table row's ring is a top-and-bottom
band that joins across cell edges; a list item is one cell and rings
fully. QMenu, QComboBox and QPalette keep the accent fill deliberately."
```

---

### Task 3: The chip gets an edge (packing-tool)

Without this the ring trades one defect for another: in dark, `status_info_bg` **is** `#042134` — the same value as `selection_bg` — so an "active" chip on a selected row vanishes entirely (spec §4).

**Files:**
- Modify: `shared/theme.py` — `StatusChip.set_status` (~line 459) and the class docstring (~line 427)
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: Task 2's ring.
- Produces: `StatusChip`'s `chip` variant stylesheet contains `border: 1px solid {fg}` where `fg` is the role's own token. `set_status`'s signature is unchanged.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
@pytest.mark.parametrize("role", [
    "status_info", "status_success", "status_warning", "status_danger",
    "text_secondary",
])
def test_a_chip_has_an_edge_so_its_tint_never_has_to_carry_the_shape(
    qapp, theme, role
):
    """The tint cannot be trusted against an arbitrary background.

    status_info_bg vs selection_bg measures 1.00 in dark -- identical. And
    text_secondary has no _bg partner at all, so it falls back to
    surface_sunken at 1.05 against surface. One outline in the role's own
    foreground covers both, and the foreground is validated on every plane.
    """
    chip = StatusChip(role, "Active", theme)
    assert f"border: 1px solid {getattr(theme, role)}" in chip.styleSheet()
```

`StatusChip` and a `qapp` fixture are needed; follow whatever this file already does for widget tests (see `tests/test_shared_theme_buttons.py` if `tests/test_theme.py` has no `qapp` fixture, and import it the same way).

- [ ] **Step 2: Run to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k chip_has_an_edge -v
```

Expected: FAIL — the current stylesheet says `border: none`.

- [ ] **Step 3: Add the edge**

In `set_status`, replace the `chip`-variant stylesheet:

```python
        tint = getattr(theme, f"{role}_bg", theme.surface_sunken)
        self.setStyleSheet(
            f"background-color: {tint}; color: {fg}; "
            f"border: 1px solid {fg}; border-radius: {theme.radius}px; "
            f"padding: 2px 8px;"
        )
```

Update the class docstring's second paragraph — it currently reasons that
`validate_theme` proving `status_*` against `status_*_bg` guarantees the chip's contrast.
That covers the label on its tint, never the tint on whatever the chip sits on:

```python
    Two variants. `chip` is a pill filled with the role's own tint and
    outlined in the role's own foreground. The fill alone cannot be trusted
    to carry the pill's shape: status_info_bg is identical to selection_bg in
    dark, and a role with no `<role>_bg` partner (text_secondary, for the
    "Not Started" row) falls back to surface_sunken at 1.05:1 on surface.
    The outline is validated everywhere the fill is not -- validate_theme
    proves every status_* on all four planes and on selection_bg. `edge` is a
    row/lane marker: a coloured left border on a transparent ground.
```

- [ ] **Step 4: Run to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/theme.py tests/test_theme.py
git commit -m "theme: a status chip is outlined in its own foreground

The tint cannot carry the pill's shape against an arbitrary background:
status_info_bg is identical to selection_bg in dark, and text_secondary
has no tint at all. Closes the archived-chip report too."
```

---

### Task 4: packing-tool gate, then push

**Files:** none — verification only.

- [ ] **Step 1: Run the full gate**

```bash
cd ~/Desktop/Projects/packing-tool/.claude/worktrees/worktree-selection-ring
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check .
```

Expected: all tests pass, ruff clean. `shared/style_lint.py` also guards style literals — if it objects to `1px solid {fg}`, the value is a token reference and not a literal, so read its rule before changing anything.

- [ ] **Step 2: Push the branch**

```bash
git push -u origin worktree-selection-ring
```

---

### Task 5: Sync `shared/` into shopify

**Files:**
- Modify: `shared/theme.py` (generated by the sync — never hand-edited)

- [ ] **Step 1: Set up the worktree's venv**

```bash
cd ~/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/worktree-selection-ring
./scripts/setup_venv.sh
```

- [ ] **Step 2: Run the sync**

The path argument is **required** here — from a worktree the sibling default resolves to `.claude/worktrees/packing-tool`, which does not exist.

```bash
.venv/bin/python scripts/sync_shared.py \
  ~/Desktop/Projects/packing-tool/.claude/worktrees/worktree-selection-ring
```

- [ ] **Step 3: Confirm the ring arrived**

```bash
grep -n "selection_border\|item:selected" shared/theme.py | head
```

Expected: `QTableView::item:selected` and `QListWidget::item:selected` reference
`theme.selection_border`; `QMenu::item:selected` still references `theme.accent_fill`.

- [ ] **Step 4: Commit**

```bash
git add shared/
git commit -m "sync shared/ from packing-tool: the selection ring"
```

---

### Task 6: Delete the 1e workarounds (shopify)

The payoff. Every deletion here is dead only because the ring landed.

**Files:**
- Modify: `gui/session_row_delegates.py` — `label_color()` (~line 51) and `SessionStatusDelegate.paint`'s `State_Selected` branch (~line 96), `PackingProgressDelegate.paint` (~line 175)
- Modify: `tests/test_session_browser_1e.py` — `TestASelectedRowStaysReadable` (~line 311)

**Interfaces:**
- Consumes: Task 5's synced `shared/theme.py`.
- Produces: `gui.session_row_delegates` no longer exports `label_color`. `chip_colors` and `SessionStatusDelegate.form` are unchanged.

- [ ] **Step 1: Make the tests match the new reality**

Delete the whole `TestASelectedRowStaysReadable` class (~lines 311–360, through the end of `test_the_dot_gets_a_surface_backing_disc`). It asserts `label_color` returns `on_accent` and that a backing disc exists; both are the workaround, not the requirement. Task 1's matrix covers the underlying property for every token rather than for the two that happened to break.

Replace it with:

```python
class TestASelectedRowStaysReadable:
    """Was three workarounds; is now one property of the theme.

    Selection is selection_bg with a selection_border ring, and every
    foreground a delegate can draw is validated against selection_bg by
    validate_theme. So the delegate needs no selected-state branch at all --
    that is what deleted label_color() and the backing disc.
    """

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    def test_every_painted_foreground_clears_aa_on_a_selected_row(
        self, qapp, theme_name
    ):
        from shared.theme import contrast_ratio

        manager = get_theme_manager()
        before = manager.get_current_theme().name
        try:
            manager.set_theme(theme_name)
            theme = manager.get_current_theme()
            painted = [theme.text] + [
                getattr(theme, role) for role in STATUS_ROLES.values()
            ]
            for fg in painted:
                ratio = contrast_ratio(fg, theme.selection_bg)
                assert ratio >= 4.5, f"{theme_name}: {fg} on selection_bg = {ratio:.2f}"
        finally:
            manager.set_theme(before)

    def test_the_delegate_has_no_selected_state_branch_left(self):
        import inspect

        from gui import session_row_delegates

        source = inspect.getsource(session_row_delegates)
        assert "State_Selected" not in source
        assert "label_color" not in source
```

Remove the now-unused `label_color` import from the test file's import block, and `QStyleOptionViewItem`/`QStyle` if nothing else in the file uses them (check first — other tests may).

- [ ] **Step 2: Run to verify it fails**

```bash
cd ~/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/worktree-selection-ring
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_1e.py -v
```

Expected: `test_the_delegate_has_no_selected_state_branch_left` FAILS — the branch is still there.

- [ ] **Step 3: Delete the workarounds**

In `gui/session_row_delegates.py`:

1. Delete the entire `label_color` function (its `def` line, docstring and two body lines).
2. In `SessionStatusDelegate.paint`, delete the whole `if opt.state & QStyle.State_Selected:` block inside the `if kind == "dot":` branch — the comment, the `setBrush` and the `drawEllipse`. The `dot` branch becomes:

```python
        if kind == "dot":
            diameter = 8
            top = rect.center().y() - diameter // 2
            painter.setBrush(QColor(fg))
            painter.drawEllipse(rect.left(), top, diameter, diameter)
            painter.setPen(QColor(theme.text))
            painter.drawText(
                rect.adjusted(diameter + 6, 0, 0, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                text,
            )
```

3. In the same method's `else` (chip) branch, give the pill the outline that matches Task 3's `StatusChip`, so the divergence stays intentional — replace `painter.setBrush(QColor(tint))` and its `drawRoundedRect` with:

```python
            painter.setBrush(QColor(tint))
            painter.setPen(QColor(fg))
            painter.drawRoundedRect(pill, height / 2, height / 2)
```

Note `painter.setPen(Qt.NoPen)` is set once near the top of `paint`; setting the pen here overrides it for the pill, and the following `painter.setPen(QColor(fg))` before `drawText` is then redundant but harmless — leave it, it documents intent.

4. In `PackingProgressDelegate.paint`, replace `painter.setPen(QColor(label_color(opt, theme)))` with `painter.setPen(QColor(theme.text))`.
5. Remove `QStyle` from the imports **only if** nothing else in the file uses it — `paint` still calls `style.drawControl(QStyle.CE_ItemViewItem, …)`, so it stays.

- [ ] **Step 4: Run to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_1e.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/session_row_delegates.py tests/test_session_browser_1e.py
git commit -m "1e: delete the selection workarounds the ring makes dead

The backing disc, label_color() and its two call sites existed only
because accent_fill was the same blue in both themes. On selection_bg
the dot is 4.80:1 and the label 14.74:1, both unaided."
```

---

### Task 7: Pixel-prove the band, then the shopify gate

The assertion that fails if someone later "fixes" the table ring to four sides and reintroduces per-cell boxes. Everything before this asserts about strings; this asserts about pixels.

**Files:**
- Create: `tests/test_selection_ring_renders.py`

**Interfaces:**
- Consumes: Tasks 2 and 5.
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing test**

```python
"""The selection ring is a rendered property, not a stylesheet property.

QSS styles cells. A four-sided border on QTableView::item draws a box around
every cell in the row; top-and-bottom borders join across cell edges into one
band. Only pixels can tell those apart, so this test renders.
"""
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTableWidget, QTableWidgetItem,
)

from gui.theme_manager import get_theme_manager
from shared.theme import build_stylesheet


class _BlankingDelegate(QStyledItemDelegate):
    """The gui/session_row_delegates.py pattern: blank the text, let the
    style paint the row, draw the content yourself."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)


def _hex_at(image, x, y):
    c = image.pixelColor(x, y)
    return f"#{c.red():02X}{c.green():02X}{c.blue():02X}".upper()


@pytest.fixture
def selected_row(qapp, request):
    theme = get_theme_manager().get_current_theme()
    table = QTableWidget(3, 4)
    table.setStyleSheet(build_stylesheet(theme))
    table.horizontalHeader().hide()
    table.verticalHeader().hide()
    table.setShowGrid(False)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setItemDelegateForColumn(2, _BlankingDelegate())
    for r in range(3):
        for c in range(4):
            table.setItem(r, c, QTableWidgetItem(f"r{r}c{c}"))
    table.resize(400, 120)
    table.selectRow(1)
    table.show()
    qapp.processEvents()
    image = QImage(table.size(), QImage.Format_RGB32)
    table.render(image)
    rect = table.visualRect(table.model().index(1, 0))
    return theme, image, rect


def test_the_ring_is_continuous_across_a_cell_boundary(selected_row):
    theme, image, rect = selected_row
    ring = theme.selection_border.upper()
    for x in (100, 199, 201, 300):
        assert _hex_at(image, x, rect.top() + 1) == ring, f"gap at x={x}"


def test_a_delegate_painted_column_matches_a_plain_one(selected_row):
    theme, image, rect = selected_row
    y = rect.center().y()
    assert _hex_at(image, 250, y) == _hex_at(image, 100, y)
    assert _hex_at(image, 250, y) == theme.selection_bg.upper()


def test_the_accent_fill_is_gone_from_a_selected_row(selected_row):
    theme, image, rect = selected_row
    accent = theme.accent_fill.upper()
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(0, 400, 5):
            assert _hex_at(image, x, y) != accent
```

Reuse the repo's existing `qapp` fixture — check `tests/conftest.py`; if it is defined locally in `tests/test_session_browser_1e.py` instead, move it to `conftest.py` rather than duplicating it.

- [ ] **Step 2: Run it**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring_renders.py -v
```

Expected: PASS, because Tasks 2 and 5 already landed. If a ring assertion fails at only `x=199`/`x=201`, the border went to four sides — re-read Task 2 Step 3.

- [ ] **Step 3: Run both full gates**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: all pass (939 base + 1e's 56 + the new tests), ruff clean.

- [ ] **Step 4: Update the graph**

```bash
graphify update .
```

- [ ] **Step 5: Commit and push**

```bash
git add tests/test_selection_ring_renders.py tests/conftest.py graphify-out/
git commit -m "test: pixel-prove the selection band is continuous across cells

String assertions cannot distinguish a row band from seven per-cell
boxes. This one renders and reads the pixels at the cell boundary."
git push -u origin worktree-selection-ring
```

---

## Self-Review

**Spec coverage.** §1 problem → Tasks 2, 6. §2 Qt mechanics → Task 2 Step 3, Task 7. §2.1 geometry → Task 2's transparent counter-rules. §2.2 hover → Task 2's `:selected:hover`. §3 measured contrast → Task 1. §4 chip regression → Task 3 (`StatusChip`) and Task 6 Step 3.3 (delegate). §5 what does not change → Task 2 Step 3's explicit "do not touch". §6 the change → Tasks 2, 3, 5, 6. §7 archived chip → Task 3. §8 testing → Tasks 1, 2, 3, 7. §9 risk → Global Constraints (both PRs merge together).

**Type consistency.** `_SELECTION_FOREGROUNDS` is defined in Task 1 and used nowhere else. `chip_colors` and `form` keep their signatures. `label_color` is deleted in Task 6 and referenced nowhere after. `_rule()` is a test helper defined once in Task 2 and reused by Task 2's own tests only.

**Known soft spots for the executor:**
- The pixel coordinates in Task 7 (`x=199/201`, `x=250`) assume a 400px-wide four-column table, which the fixture builds. If Qt's column widths differ on this machine, derive the boundary from `table.visualRect(...)` rather than hard-coding — the assertion is "continuous across a boundary", not "continuous at x=199".
- `tests/test_theme.py` may not have a `qapp` fixture (Task 3 needs one, since `StatusChip` is a widget). Check before writing.
