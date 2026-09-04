# Phase 9 Bundle 3 — three components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking. Do **not** fan out to parallel subagents — this runner executes
> in-session.

**Goal:** Ship the three F-series components — one status silhouette with
three channels, a closed selection ring, and one `StatePanel` — so Bundles 4
and 6 have the pieces they are gated on.

**Architecture:** One pure function in `shared/theme.py` resolves the three
status channels for both renderers (the QSS-styled `StatusChip` and the
painted `SessionStatusDelegate`), replacing a copied two-line rule. One helper
in `gui/selection_ring.py` decides which end caps a cell owns, called from the
delegates the app installs; the QSS rule keeps drawing the ring's top and
bottom. `StatePanel` is a `QWidget` **holding** a `Card`, not subclassing one.

**Tech Stack:** PySide6 6.11, pytest, ruff. Windows 10/11 target, Ubuntu dev.

**Spec:** `docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md`
— read it first. It carries the reasoning this plan only executes, including
three open questions (§8) that each have a default written into the tasks
below.

## Global Constraints

- **`shared/` is not owned by this repo.** Tasks 1 and 2 are authored in
  `../packing-tool` and arrive here through `scripts/sync_shared.py`. Never
  hand-edit a file under `shared/` in this repo — the next sync overwrites it.
  This bundle therefore produces **two PRs**, exactly as Bundle 1 did
  (shopify #313 + packing-tool #172).
- **No hardcoded colours.** Every colour comes from a `ThemeTokens` field
  resolved by name. `#666`, `gray`, etc. fail `shared/style_lint.py`.
- **The style guards apply to raw HTML/CSS inside `.py` files too**, and
  `tests/test_type_scale.py` is stricter than `shared/style_lint.py` — it bans
  the literal string `font-size:` anywhere under `gui/`, with no escape hatch.
  Use `font_css(role)`.
- **Token names and roles are frozen.** Values move; names never do. This
  bundle adds no token.
- **No UI calls from background threads.**
- **Test command:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
  Lint: `.venv/bin/ruff check . --exclude shared`
  `python` and `ruff` are not on PATH — always go through `.venv/bin/`.
- **Branch discipline:** PR-only in both repos. Never commit to `main`.

## Worktrees

This repo's worktree already exists:
`.claude/worktrees/phase9-bundle3-components`, branch
`worktree-phase9-bundle3-components`. **Reuse it; do not create a second one.**

Tasks 1–2 need a **separate `packing-tool` worktree**. Create it at
`../packing-tool` with the matching name (`phase9-bundle3-components`) and run
`./scripts/setup_venv.sh` there. Tasks 1–2 commit and PR from that worktree;
Tasks 3–7 commit here.

---

## File Structure

**`packing-tool` (Tasks 1–2):**
- Modify `shared/theme.py` — `StatusStyle`, `status_style()`,
  `paint_status_mark()`, `StatusDot(filled=)`, `StatusChip` three channels
- Modify `tests/test_shared_theme_widgets.py` — the widget contract
- Create `tests/test_status_style.py` — the pure rule

**`shopify-fulfillment-tool` (Tasks 3–7):**
- Modify `shared/theme.py` — **by sync only**
- Modify `gui/session_row_delegates.py` — delete `chip_colors`/`form`, one
  silhouette, `STATUS_ROLES` gains live-ness
- Modify `gui/session_browser_widget.py` — writes the new item data
- Create `gui/selection_ring.py` — cap geometry + `SelectionRingDelegate`
- Modify `gui/status_edge_delegate.py` — ring caps, edge insets, shared
  first-visible-column helper
- Modify `gui/ui_manager.py` — `TagDelegate` paints the ring too
- Create `gui/components/state_panel.py` — `StatePanel`
- Modify `gui/components/__init__.py` — export it
- Create `tests/test_selection_ring.py`, `tests/test_state_panel.py`,
  `tests/test_status_channels.py`
- Modify `tests/test_session_browser_1e.py`, `tests/test_status_edge_delegate.py`

---

## Task 1: `status_style()` — the three-channel rule (packing-tool)

**Files:**
- Modify: `../packing-tool/shared/theme.py` (beside `StatusDot`, ~line 655)
- Test: `../packing-tool/tests/test_status_style.py` (create)

**Interfaces:**
- Consumes: `ThemeTokens`, `LIGHT_THEME`, `DARK_THEME` (existing)
- Produces: `StatusStyle(fg: str, fill: str | None, mark_filled: bool)`,
  `status_style(role, theme, *, live=True, manual=False) -> StatusStyle`,
  `MARK_PX = 8`, `MARK_RING_WIDTH = 1.5`,
  `paint_status_mark(painter, rect: QRectF, style: StatusStyle) -> None`

- [ ] **Step 1: Write the failing test**

Create `../packing-tool/tests/test_status_style.py`:

```python
"""The three status channels resolve in one place, for both renderers.

Spec: shopify-fulfillment-tool
docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §3.2
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, status_style

ROLES = [
    "status_info", "status_success", "status_warning",
    "status_danger", "text_secondary",
]


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize("role", ROLES)
def test_four_combinations_are_four_distinguishable_renderings(theme, role):
    seen = {
        status_style(role, theme, live=live, manual=manual)
        for live in (True, False)
        for manual in (True, False)
    }
    assert len(seen) == 4


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_resting_has_no_fill_and_live_has_the_roles_tint(theme):
    live = status_style("status_warning", theme, live=True)
    resting = status_style("status_warning", theme, live=False)
    assert live.fill == theme.status_warning_bg
    assert resting.fill is None
    assert live.fg == resting.fg == theme.status_warning


def test_mark_is_solid_for_a_person_and_hollow_for_the_system():
    assert status_style("status_info", LIGHT_THEME, manual=True).mark_filled
    assert not status_style("status_info", LIGHT_THEME, manual=False).mark_filled


def test_a_role_with_no_bg_partner_falls_back_to_surface_sunken():
    # text_secondary is the "Not Started" / "Archived" role and has no _bg.
    style = status_style("text_secondary", DARK_THEME, live=True)
    assert style.fill == DARK_THEME.surface_sunken


def test_a_typo_in_the_role_raises_where_it_is_written():
    with pytest.raises(AttributeError):
        status_style("status_sucess", LIGHT_THEME)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_style.py -v`
Expected: FAIL — `ImportError: cannot import name 'status_style'`

- [ ] **Step 3: Implement**

In `shared/theme.py`, add `NamedTuple` to the `typing` imports and
`QPen`, `QRectF` to the Qt imports (`from PySide6.QtCore import QRectF` and
`from PySide6.QtGui import QColor, QPainter, QPen`). Insert directly above
`class StatusDot`:

```python
class StatusStyle(NamedTuple):
    """How one status renders, resolved once for both renderers.

    Three independent channels. `fg` is the role's colour -- the outline, the
    mark and the label all take it. `fill` is the tint when the status is
    live (someone has to act) and None when it is resting or terminal. Mark
    is authorship: solid when a person set the status, hollow when the system
    derived it.

    Supersedes the older "tint carries authorship" rule, which left nothing to
    carry urgency. One silhouette, three channels.
    """

    fg: str
    fill: str | None
    mark_filled: bool


def status_style(
    role: str, theme: ThemeTokens, *, live: bool = True, manual: bool = False
) -> StatusStyle:
    """Resolve a role plus the two flags into the three channels.

    The one place the rule is written. StatusChip renders it as QSS and
    SessionStatusDelegate paints it, and they must not drift -- a copied
    two-line rule was tolerable, a three-channel rule with geometry is not.

    `role` is any ThemeTokens colour field, not only the four status roles:
    packing-tool's STATUS_CONFIG maps "not_started" to text_secondary. It is
    resolved with getattr, so a typo raises here rather than rendering the
    wrong colour in production.

    A role with no `<role>_bg` partner falls back to surface_sunken -- the one
    place a missing token is tolerated, and unchanged from StatusChip's
    original rule.
    """
    fg = getattr(theme, role)
    fill = getattr(theme, f"{role}_bg", theme.surface_sunken) if live else None
    return StatusStyle(fg, fill, manual)


# The chip's mark: an 8px disc or ring in the role colour. Painted, never a
# character -- nothing may depend on a font shipping a filled and a hollow
# circle that read as the same silhouette.
MARK_PX = 8
MARK_RING_WIDTH = 1.5


def paint_status_mark(painter: QPainter, rect: QRectF, style: StatusStyle) -> None:
    """Paint one mark into `rect`, an MARK_PX-square QRectF."""
    color = QColor(style.fg)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if style.mark_filled:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(rect)
    else:
        pen = QPen(color)
        pen.setWidthF(MARK_RING_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = MARK_RING_WIDTH / 2
        painter.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))
    painter.restore()
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_style.py -v`
Expected: PASS (22 tests)

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check shared/theme.py tests/test_status_style.py
git add shared/theme.py tests/test_status_style.py
git commit -m "Phase 9.3: one function resolves the three status channels"
```

---

## Task 2: `StatusDot` and `StatusChip` grow the channels (packing-tool)

**Files:**
- Modify: `../packing-tool/shared/theme.py` (`StatusDot`, `StatusChip`)
- Test: `../packing-tool/tests/test_shared_theme_widgets.py`

**Interfaces:**
- Consumes: `status_style`, `paint_status_mark`, `MARK_PX` (Task 1)
- Produces: `StatusDot(role, theme, diameter=10, parent=None, *, filled=True)`
  with `set_filled(filled: bool)`;
  `StatusChip.set_status(role, text, theme, *, live=True, manual=False)`;
  `MARK_LEFT_PX = 8`

- [ ] **Step 1: Write the failing tests**

Append to `../packing-tool/tests/test_shared_theme_widgets.py`:

```python
def test_a_live_chip_is_tinted_and_a_resting_one_is_not(qapp):
    from shared.theme import StatusChip

    live = StatusChip("status_warning", "Paused", DARK_THEME, live=True)
    resting = StatusChip("status_success", "Completed", DARK_THEME, live=False)
    assert DARK_THEME.status_warning_bg in live.styleSheet()
    assert "background-color: transparent" in resting.styleSheet()


def test_both_fill_states_keep_the_same_outline(qapp):
    from shared.theme import StatusChip

    live = StatusChip("status_info", "Active", DARK_THEME, live=True)
    resting = StatusChip("status_info", "Active", DARK_THEME, live=False)
    outline = f"border: 1px solid {DARK_THEME.status_info}"
    assert outline in live.styleSheet()
    assert outline in resting.styleSheet()


def test_the_chip_reserves_room_for_its_mark(qapp):
    from shared.theme import MARK_LEFT_PX, MARK_PX, StatusChip

    chip = StatusChip("status_info", "Active", DARK_THEME)
    assert f"padding: 2px 8px 2px {MARK_LEFT_PX + MARK_PX + 4}px" in chip.styleSheet()


def test_the_edge_variant_is_untouched_by_the_flags(qapp):
    from shared.theme import StatusChip

    edge = StatusChip("status_warning", "Paused", DARK_THEME, variant="edge",
                      live=False, manual=True)
    assert "border-left: 3px solid" in edge.styleSheet()
    assert "padding: 2px 8px;" in edge.styleSheet()


def test_a_hollow_dot_differs_from_a_solid_one(qapp):
    from shared.theme import StatusDot

    solid = StatusDot("status_success", DARK_THEME, filled=True)
    hollow = StatusDot("status_success", DARK_THEME, filled=False)
    assert solid._filled and not hollow._filled
    hollow.set_filled(True)
    assert hollow._filled


def test_todays_call_sites_are_unchanged_by_the_defaults(qapp):
    from shared.theme import StatusChip, StatusDot

    # live=True, manual=False reproduce the shipped tinted pill and solid dot,
    # so packing-tool's own screens do not move.
    chip = StatusChip("status_info", "Active", DARK_THEME)
    assert DARK_THEME.status_info_bg in chip.styleSheet()
    assert StatusDot("status_info", DARK_THEME)._filled
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shared_theme_widgets.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'live'`

- [ ] **Step 3: Implement `StatusDot`**

Replace `StatusDot.__init__` and `paintEvent` in `shared/theme.py`:

```python
    def __init__(self, role: str, theme: ThemeTokens, diameter: int = 10,
                 parent=None, *, filled: bool = True):
        super().__init__(parent)
        self._color = QColor(getattr(theme, role))
        self._diameter = diameter
        self._filled = filled
        self.setFixedSize(diameter, diameter)

    def set_filled(self, filled: bool) -> None:
        """Solid when a person set the status, hollow when the system did."""
        self._filled = filled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        style = StatusStyle(self._color.name(), None, self._filled)
        paint_status_mark(painter, QRectF(0, 0, self._diameter, self._diameter), style)
```

Then extend the class docstring with: `filled` is the **mark** channel — this
widget is the chip's mark, not a status form of its own.

- [ ] **Step 4: Implement `StatusChip`**

Add `MARK_LEFT_PX = 8` beside `CHIP_VARIANTS`. Replace `StatusChip.__init__`'s
`self.set_status(role, text, theme)` call and `set_status`:

```python
    def __init__(self, role, text, theme, variant="chip", parent=None,
                 *, live: bool = True, manual: bool = False) -> None:
        super().__init__(parent)
        if variant not in CHIP_VARIANTS:
            raise ValueError(
                f"Unknown chip variant {variant!r}; expected one of {CHIP_VARIANTS}"
            )
        self._variant = variant
        self._style = None
        self.set_status(role, text, theme, live=live, manual=manual)

    def set_status(self, role: str, text: str, theme: ThemeTokens,
                   *, live: bool = True, manual: bool = False) -> None:
        """Three channels: colour is the role, fill is live, mark is authorship.

        Keyword-only and defaulted to the shipped behaviour, so every existing
        call site keeps its tinted pill.
        """
        self._style = status_style(role, theme, live=live, manual=manual)
        self.setText(text)
        if self._variant == "edge":
            # A lane marker, not a status badge: it carries no authorship of
            # its own and takes no mark.
            self.setStyleSheet(
                f"background-color: transparent; color: {theme.text}; "
                f"border-left: 3px solid {self._style.fg}; padding: 2px 8px;"
            )
            return
        fill = self._style.fill or "transparent"
        self.setStyleSheet(
            f"background-color: {fill}; color: {self._style.fg}; "
            f"border: 1px solid {self._style.fg}; "
            f"border-radius: {theme.radius}px; "
            f"padding: 2px 8px 2px {MARK_LEFT_PX + MARK_PX + 4}px;"
        )
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._variant != "chip" or self._style is None:
            return
        painter = QPainter(self)
        top = (self.height() - MARK_PX) / 2
        paint_status_mark(
            painter, QRectF(MARK_LEFT_PX, top, MARK_PX, MARK_PX), self._style
        )
```

- [ ] **Step 5: Run the whole packing-tool suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
Expected: PASS. If `tests/test_theme.py:391`'s chip assertion fails, it is
asserting the old stylesheet string — update it to the new padding, do not
weaken it.

- [ ] **Step 6: Lint, commit, open the packing-tool PR**

```bash
.venv/bin/ruff check shared/theme.py tests/
git add shared/theme.py tests/
git commit -m "Phase 9.3: one status silhouette, three channels"
git push -u origin worktree-phase9-bundle3-components
gh pr create --title "Phase 9 Bundle 3 (packing-tool half): the status component's three channels" --body "..."
```

The PR body must say: **shared component only.** `sessions_list_widget.py`
still places a standalone `StatusDot`; converting it needs a painted delegate
and belongs to packing-tool 8.9 (spec §7). The defaults keep every
packing-tool screen pixel-identical.

**If the user answered Q2 with "convert packing-tool too":** add a task here
that replaces `sessions_list_widget.py`'s `StatusDot` cell widget with a
painted delegate modelled on this repo's `SessionStatusDelegate`, and map its
seven states through the §3.5 table. Do not ship a cell widget — it swallows
clicks and moves selection on hover.

---

## Task 3: Sync, and the delegate loses its second silhouette

**Files:**
- Modify: `shared/theme.py` (**by sync only** — never by hand)
- Modify: `gui/session_row_delegates.py:26-107`
- Modify: `gui/session_browser_widget.py:476-482`
- Test: `tests/test_status_channels.py` (create),
  `tests/test_session_browser_1e.py:36-60`

**Interfaces:**
- Consumes: `status_style`, `paint_status_mark`, `MARK_PX`, `MARK_LEFT_PX`,
  `StatusStyle` (Tasks 1–2, arriving via sync)
- Produces: `STATUS_ROLES: dict[str, tuple[str, bool]]`,
  `ROLE_LIVE = Qt.UserRole + 3`. `chip_colors()` and
  `SessionStatusDelegate.form()` no longer exist.

- [ ] **Step 1: Sync `shared/` from packing-tool**

From this worktree the sibling default resolves wrong, so pass the path:

```bash
.venv/bin/python scripts/sync_shared.py /home/cognitiveghost/Desktop/Projects/packing-tool
```

Expected: `shared/theme.py` picks up Tasks 1–2. Confirm with
`grep -n "def status_style" shared/theme.py`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_status_channels.py`:

```python
"""9.3: one silhouette, and live-ness rides with the role.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §3
"""

import pytest

from gui.session_row_delegates import STATUS_ROLES
from shared.theme import DARK_THEME, LIGHT_THEME, status_style


def test_every_shopify_status_names_a_role_and_its_liveness():
    assert STATUS_ROLES == {
        "active": ("status_info", True),
        "completed": ("status_success", False),
        "abandoned": ("status_danger", False),
        "archived": ("text_secondary", False),
    }


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize("status", sorted(STATUS_ROLES))
def test_every_status_resolves_in_both_themes(theme, status):
    role, live = STATUS_ROLES[status]
    style = status_style(role, theme, live=live)
    assert style.fg
    assert (style.fill is not None) is live


def test_the_delegate_no_longer_chooses_between_two_silhouettes():
    from gui import session_row_delegates

    assert not hasattr(session_row_delegates.SessionStatusDelegate, "form")
    assert not hasattr(session_row_delegates, "chip_colors")
```

- [ ] **Step 3: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_channels.py -v`
Expected: FAIL — `STATUS_ROLES` values are bare strings; `form` still exists.

- [ ] **Step 4: Rewrite the delegate**

In `gui/session_row_delegates.py`, replace the imports, roles and
`SessionStatusDelegate` down to (not including) `class PackingProgressDelegate`:

```python
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.selection_ring import paint_selection_ring
from gui.theme_manager import get_theme_manager
from shared.theme import MARK_LEFT_PX, MARK_PX, paint_status_mark, status_style

# Item-data roles. Qt.UserRole itself is already taken on this table: column 0
# carries the session path, column 6 the packing ratio.
ROLE_TOKEN = Qt.UserRole + 1     # str -- theme token name for the status
ROLE_MANUAL = Qt.UserRole + 2    # bool -- status_manually_set
ROLE_LIVE = Qt.UserRole + 3      # bool -- someone still has to act

# 9.3 §3.5: live-ness is data about a state, so it rides with the role rather
# than in a second table keyed by the same thing. 9.19 extends this to seven
# statuses plus archived; it owns that expansion because it is gated on the
# `blocked_orders` data change.
STATUS_ROLES: dict[str, tuple[str, bool]] = {
    "active": ("status_info", True),
    "completed": ("status_success", False),
    "abandoned": ("status_danger", False),
    "archived": ("text_secondary", False),
}


class SessionStatusDelegate(QStyledItemDelegate):
    """Paints the Status cell as one silhouette: an outlined pill, a mark, a label.

    Colour is the role, fill is live-vs-resting, and the mark is authorship --
    solid for a person, hollow for the system. Before 9.3 authorship chose
    between a bare dot and a tinted pill, which read as two components and made
    the authorship difference disappear into "the design is inconsistent".

    A delegate, not a cell widget: a QLabel in a cell covers it, so clicks
    never reach the row and hover moves the selection.
    """

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""                      # the row background, not the label
        style_ = opt.widget.style() if opt.widget else QApplication.style()
        style_.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        paint_selection_ring(painter, option, index)

        role = index.data(ROLE_TOKEN)
        if not role:
            return
        status = status_style(
            role,
            get_theme_manager().get_current_theme(),
            live=bool(index.data(ROLE_LIVE)),
            manual=bool(index.data(ROLE_MANUAL)),
        )

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(8, 0, -8, 0)
        metrics = painter.fontMetrics()
        label_left = MARK_LEFT_PX + MARK_PX + 4
        height = metrics.height() + 4
        pill = QRect(
            rect.left(),
            rect.center().y() - height // 2,
            min(label_left + metrics.horizontalAdvance(text) + 8, rect.width()),
            height,
        )
        painter.setBrush(QColor(status.fill) if status.fill else Qt.NoBrush)
        painter.setPen(QColor(status.fg))       # the outline, then the mark and label
        painter.drawRoundedRect(pill, height / 2, height / 2)
        paint_status_mark(
            painter,
            QRectF(
                pill.left() + MARK_LEFT_PX,
                pill.center().y() - MARK_PX / 2,
                MARK_PX,
                MARK_PX,
            ),
            status,
        )
        painter.drawText(
            pill.adjusted(label_left, 0, -8, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            text,
        )
        painter.restore()
```

Delete `chip_colors()` entirely, and add `paint_selection_ring(painter, option,
index)` after the `drawControl` line in `PackingProgressDelegate.paint` too.

`gui/selection_ring.py` does not exist yet — Task 4 creates it. Write Task 4
first if you prefer a green suite between tasks; the import is the only
coupling.

- [ ] **Step 5: Update the writer**

In `gui/session_browser_widget.py`, replace the three lines that set the item
data (currently ~476–482):

```python
            status = session_info.get("status", "active")
            role, live = STATUS_ROLES.get(status, ("text_secondary", False))
            status_item = QTableWidgetItem(status.capitalize())
            status_item.setData(ROLE_TOKEN, role)
            status_item.setData(ROLE_LIVE, live)
            status_item.setData(
                ROLE_MANUAL, bool(session_info.get("status_manually_set", False))
            )
```

and add `ROLE_LIVE` to the `from gui.session_row_delegates import (...)` block
at line 29.

- [ ] **Step 6: Fix the test that asserted the old copy**

`tests/test_session_browser_1e.py:36-60` asserts the delegate's `chip_colors`
equals `StatusChip`'s two lines. That contract is gone — they now share
`status_style`. Replace those tests with one that asserts the delegate and the
chip resolve the same `StatusStyle` for a given role and flags. Keep the
`text_secondary`-has-no-`_bg` case; it still matters.

- [ ] **Step 7: Run and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_channels.py tests/test_session_browser_1e.py -v
.venv/bin/ruff check gui/ tests/ --exclude shared
git add -A
git commit -m "Phase 9.3: one status silhouette in the Qt tier"
```

---

## Task 4: The selection ring's end caps

**Files:**
- Create: `gui/selection_ring.py`
- Test: `tests/test_selection_ring.py` (create)

**Interfaces:**
- Consumes: `get_theme_manager` (existing)
- Produces: `RING_WIDTH = 2`;
  `first_visible_column(header) -> int | None`;
  `last_visible_column(header) -> int | None`;
  `caps(header, column) -> tuple[bool, bool]`;
  `paint_selection_ring(painter, option, index) -> None`;
  `class SelectionRingDelegate(QStyledItemDelegate)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_selection_ring.py`:

```python
"""9.4: which end caps a cell owns. Pure, so it needs no painter.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §4
"""

import pytest
from PySide6.QtWidgets import QTableWidget

from gui.selection_ring import caps, first_visible_column, last_visible_column

_KEEPALIVE = []


def _header(columns=4, hidden=(), moves=()):
    table = QTableWidget(1, columns)
    header = table.horizontalHeader()
    for frm, to in moves:
        header.moveSection(frm, to)
    for col in hidden:
        header.setSectionHidden(col, True)
    _KEEPALIVE.append(table)
    return header


def test_the_caps_land_on_the_first_and_last_columns(qapp):
    header = _header(4)
    assert caps(header, 0) == (True, False)
    assert caps(header, 3) == (False, True)
    assert caps(header, 1) == (False, False)


def test_a_single_column_row_owns_both_caps(qapp):
    header = _header(1)
    assert caps(header, 0) == (True, True)


def test_a_hidden_last_column_hands_its_cap_to_the_one_before(qapp):
    header = _header(4, hidden=(3,))
    assert caps(header, 3) == (False, False)
    assert caps(header, 2) == (False, True)


def test_a_hidden_first_column_hands_its_cap_along(qapp):
    header = _header(4, hidden=(0,))
    assert caps(header, 0) == (False, False)
    assert caps(header, 1) == (True, False)


def test_a_dragged_column_takes_the_cap_with_it(qapp):
    # Visual index, not logical: a user who drags column 2 to the front must
    # get the cap on the left of the row.
    header = _header(4, moves=((2, 0),))
    assert caps(header, 2) == (True, False)
    assert caps(header, 0) == (False, False)


def test_no_header_means_no_caps(qapp):
    assert caps(None, 0) == (False, False)
    assert first_visible_column(None) is None
    assert last_visible_column(None) is None


def test_every_column_hidden_means_no_caps(qapp):
    header = _header(2, hidden=(0, 1))
    assert caps(header, 0) == (False, False)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.selection_ring'`

- [ ] **Step 3: Implement**

Create `gui/selection_ring.py`:

```python
"""The two end caps that close a selected row's ring.

`QTableView::item` styles *cells*, so a QSS left or right border would repeat
at every column boundary -- which is why the shipped selection is two
horizontal rules, open at both ends, and why the status edge on a
selected-and-blocked row reads as part of the selection.

The horizontal sides stay in QSS, where they already work. Each cell paints
only the caps it owns, at its own option.rect, so nothing depends on how
QTableView clips one cell against another and the caps meet the QSS borders
exactly -- same rect, same width.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §4
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from gui.theme_manager import get_theme_manager

# Matches the 2px selection_border top and bottom in build_stylesheet's
# QTableView::item:selected rule. Both name theme.selection_border.
RING_WIDTH = 2


def _edge_visible_column(header, forward: bool) -> int | None:
    """Logical index of the leftmost (or rightmost) column the user can see.

    Visual order, not logical: a user who drags a column to the front must
    still get the cap on the left of the row. Hidden columns are walked past,
    which is normally zero iterations.
    """
    if header is None:
        return None
    order = range(header.count()) if forward else range(header.count() - 1, -1, -1)
    for visual in order:
        logical = header.logicalIndex(visual)
        if not header.isSectionHidden(logical):
            return logical
    return None


def first_visible_column(header) -> int | None:
    return _edge_visible_column(header, forward=True)


def last_visible_column(header) -> int | None:
    return _edge_visible_column(header, forward=False)


def caps(header, column: int) -> tuple[bool, bool]:
    """`(left, right)` -- which end caps this column owns. Pure and testable."""
    if header is None:
        return (False, False)
    return (first_visible_column(header) == column,
            last_visible_column(header) == column)


def header_of(option):
    """The horizontal header behind this cell, or None for a non-table view."""
    widget = option.widget
    return widget.horizontalHeader() if hasattr(widget, "horizontalHeader") else None


def paint_selection_ring(painter, option, index) -> None:
    """Paint this cell's slice of the selected row's ring. A no-op otherwise.

    Call it after the base item is drawn, so the caps land on top of the QSS
    background rather than under it.
    """
    if not (option.state & QStyle.State_Selected):
        return
    left, right = caps(header_of(option), index.column())
    if not (left or right):
        return

    color = QColor(get_theme_manager().get_current_theme().selection_border)
    rect = option.rect
    painter.save()
    if left:
        painter.fillRect(rect.x(), rect.y(), RING_WIDTH, rect.height(), color)
    if right:
        painter.fillRect(
            rect.right() - RING_WIDTH + 1, rect.y(), RING_WIDTH, rect.height(), color
        )
    painter.restore()


class SelectionRingDelegate(QStyledItemDelegate):
    """The default delegate for a table whose other columns have none.

    setItemDelegateForColumn still wins where a column has its own delegate;
    this one closes the ring on all the columns that do not.
    """

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        paint_selection_ring(painter, option, index)
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check gui/selection_ring.py tests/test_selection_ring.py
git add gui/selection_ring.py tests/test_selection_ring.py
git commit -m "Phase 9.4: the end caps that close a selection ring"
```

**If the user answered Q1 with "drop the QSS rule":** additionally paint top
and bottom on every cell in `paint_selection_ring` (unconditionally, not only
on cap columns), remove the `border-top`/`border-bottom` declarations from
`QTableView::item` and `QTableView::item:selected` in `shared/theme.py` — a
**packing-tool** edit, so it joins the Task 2 PR — and install
`SelectionRingDelegate` on the twelve tables listed in spec §4.3 or accept that
they show a tint-only selection.

---

## Task 5: The status edge insets inside the ring

**Files:**
- Modify: `gui/status_edge_delegate.py`
- Modify: `gui/ui_manager.py:1006-1008` (`TagDelegate`),
  `gui/session_browser_widget.py:236`
- Test: `tests/test_status_edge_delegate.py`

**Interfaces:**
- Consumes: `RING_WIDTH`, `first_visible_column`, `paint_selection_ring` (Task 4)
- Produces: `StatusEdgeDelegate.edge_rect(option) -> QRect`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_status_edge_delegate.py`:

```python
def test_the_edge_insets_inside_the_ring_on_a_selected_row(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    from gui.selection_ring import RING_WIDTH

    delegate = StatusEdgeDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 28)

    resting = delegate.edge_rect(option)
    assert resting == QRect(0, 0, 120, 28)

    option.state |= QStyle.State_Selected
    selected = delegate.edge_rect(option)
    assert selected.left() == RING_WIDTH
    assert selected.top() == RING_WIDTH
    assert selected.bottom() == 27 - RING_WIDTH


def test_the_edge_follows_a_hidden_first_column(qapp):
    # paints_edge shares the ring's first-visible-column rule, so hiding
    # column 0 moves the edge rather than deleting it.
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(1, 3)
    header = table.horizontalHeader()
    header.setSectionHidden(0, True)
    delegate = StatusEdgeDelegate()
    assert not delegate.paints_edge(header, 0)
    assert delegate.paints_edge(header, 1)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_edge_delegate.py -v`
Expected: FAIL — `AttributeError: 'StatusEdgeDelegate' object has no attribute 'edge_rect'`

- [ ] **Step 3: Implement**

In `gui/status_edge_delegate.py`, add the imports
`from PySide6.QtWidgets import QStyle, QStyledItemDelegate` and
`from gui.selection_ring import RING_WIDTH, first_visible_column, paint_selection_ring`,
then replace `paints_edge` and `paint`:

```python
    def paints_edge(self, header, column: int) -> bool:
        """True for the column the user currently sees on the left.

        Visual index, not logical, and skipping hidden columns: a user who
        drags a column to the front -- or hides the first one through the
        column manager -- must still get the edge on the left of the row.
        Shared with the selection ring so the two cannot disagree about where
        the row starts.
        """
        return header is not None and first_visible_column(header) == column

    def edge_rect(self, option):
        """Where the 3px bar goes. Pure, so the inset rule is testable.

        On a selected row the edge insets by the ring's width on the left, top
        and bottom, so it sits *inside* the selection rather than colliding
        with it -- a red edge on the ring's own left side reads as part of the
        selection, which is the fault 9.4 exists to remove.
        """
        if option.state & QStyle.State_Selected:
            return option.rect.adjusted(RING_WIDTH, RING_WIDTH, 0, -RING_WIDTH)
        return option.rect

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        paint_selection_ring(painter, option, index)

        # Column check first: it is a C++ visualIndex lookup, where edge_token
        # is a data() round-trip through the proxy. Only one column of N draws
        # an edge, so the cheap test skips the model call for the other N-1.
        widget = option.widget
        header = widget.horizontalHeader() if hasattr(widget, "horizontalHeader") else None
        if not self.paints_edge(header, index.column()):
            return
        token = self.edge_token(index)
        if not token:
            return

        theme = get_theme_manager().get_current_theme()
        rect = self.edge_rect(option)
        painter.save()
        # Not `rect.setWidth()`: PySide6 hands back a reference to the option's
        # own field, so narrowing it would mutate the caller's const option.
        painter.fillRect(rect.x(), rect.y(), EDGE_WIDTH, rect.height(), QColor(getattr(theme, token)))
        painter.restore()
```

- [ ] **Step 4: Wire the two remaining delegates**

In `gui/ui_manager.py`, find `class TagDelegate` (installed at line ~1006) and
add `paint_selection_ring(painter, option, index)` immediately after its base
paint call, importing it from `gui.selection_ring`. `TagDelegate` overrides the
view-wide `StatusEdgeDelegate` on its column, so without this the ring has a
gap wherever that column sits.

In `gui/session_browser_widget.py`, after line 236's
`setItemDelegateForColumn` calls, add:

```python
        # Columns 2 and 6 have their own delegates and paint the ring
        # themselves; this closes it on the ones that do not.
        self.sessions_table.setItemDelegate(SelectionRingDelegate(self))
```

with `from gui.selection_ring import SelectionRingDelegate` at the top.

- [ ] **Step 5: Write the acceptance test**

Append to `tests/test_selection_ring.py` — this is the bundle's `Done when`:

```python
def test_a_selected_and_blocked_row_draws_the_ring_around_the_edge(qapp):
    """The bundle's acceptance case, asserted on geometry rather than pixels.

    A blocked row carries a status token, so StatusEdgeDelegate paints its 3px
    bar; selected, the bar must start RING_WIDTH in from the row's left, which
    is exactly where the ring's left cap ends.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    from gui.selection_ring import RING_WIDTH
    from gui.status_edge_delegate import EDGE_WIDTH, StatusEdgeDelegate

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 28)
    option.state |= QStyle.State_Selected
    edge = StatusEdgeDelegate().edge_rect(option)

    assert edge.left() == RING_WIDTH                     # starts where the cap ends
    assert edge.left() + EDGE_WIDTH <= option.rect.width() - RING_WIDTH
    assert edge.top() == RING_WIDTH and edge.height() == 28 - 2 * RING_WIDTH
```

- [ ] **Step 6: Run everything and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add -A
git commit -m "Phase 9.4: the selection ring closes and the status edge insets"
```

---

## Task 6: Zebra stays off, the sort caret stays quiet

**Files:**
- Modify: `shared/theme.py` **only if** the check in Step 2 fails (a
  packing-tool edit — fold it into the Task 2 PR)
- Test: `tests/test_selection_ring.py`

**Interfaces:**
- Consumes: nothing new
- Produces: nothing new

- [ ] **Step 1: Write the guard test**

Append to `tests/test_selection_ring.py`:

```python
def test_zebra_striping_stays_off(qapp):
    """A stripe on surface_raised is the same value as a panel, so a striped
    table stops reading as one plane. Separation is the row rhythm and a
    border_subtle gridline, not alternating fills."""
    import gui.session_browser_widget as browser
    import gui.ui_manager as ui

    for module in (browser, ui):
        source = open(module.__file__, encoding="utf-8").read()
        assert "setAlternatingRowColors(True)" not in source


def test_the_sort_caret_is_not_forced_onto_every_header(qapp):
    """Qt draws the indicator on the sorted section alone. What the artboard
    rejects is a permanent grey caret on all of them -- eight pieces of
    furniture and no information."""
    from PySide6.QtWidgets import QTableView

    view = QTableView()
    header = view.horizontalHeader()
    assert not header.isSortIndicatorShown() or header.sortIndicatorSection() >= 0
```

- [ ] **Step 2: Run it, and act only on a real failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring.py -v`

If it passes, the shipped behaviour is already right and there is nothing to
build — commit the guard and move on. If `setAlternatingRowColors(True)` turns
up, delete that call. If a caret is being forced onto unsorted headers, remove
whatever forces it.

- [ ] **Step 3: Add the hover caret**

`build_stylesheet`'s `QHeaderView::section` block gains a hover rule using the
arrow glyphs 9.0 vendored:

```python
        QHeaderView::section:hover {{
            image: url("{glyph_url('chevron-up')}");
            image-position: right;
        }}
```

This is a `shared/theme.py` edit — author it in **packing-tool** and re-sync,
folding it into the Task 2 PR. Check first that `chevron-up` is actually in
`shared/assets/` (`ls shared/assets | grep chevron`); if 9.0 did not vendor it,
**skip this step and say so in the PR** rather than adding a glyph here, since
`shared/assets/` is packing-tool's too.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Phase 9.4: zebra stays off and the sort caret stays quiet"
```

---

## Task 7: `StatePanel`

**Files:**
- Create: `gui/components/state_panel.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_state_panel.py` (create)

**Interfaces:**
- Consumes: `Card`, `font_css`, `get_theme_manager`, `set_button_role`
- Produces: `StatePanel(title, cause, *, detail="", action_text="",
  action_role="primary", parent=None)` with attributes `card`, `button`
  (`None` when there is no action), and four classmethods
  `nothing_loaded`, `working`, `no_results`, `failed`.

**Read before starting:** spec §5.4 — this component is wired into **no
screen** in this bundle. Bundle 4 (9.9) is its first real consumer and may need
the signature to change; that is expected, not a defect.

- [ ] **Step 1: Write the failing test**

Create `tests/test_state_panel.py`:

```python
"""9.6: one empty state, not forty.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §5
"""

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from gui.components.state_panel import StatePanel


def _labels(panel):
    return [w.text() for w in panel.card.findChildren(QLabel)]


def test_nothing_loaded_names_its_cause_and_offers_one_action(qapp):
    panel = StatePanel.nothing_loaded(
        "No orders loaded",
        "Choose a Shopify export to analyse.",
        "Choose file…",
    )
    assert "No orders loaded" in _labels(panel)
    assert "Choose a Shopify export to analyse." in _labels(panel)
    assert panel.button.text() == "Choose file…"
    assert panel.button.property("role") == "primary"


def test_working_names_the_step_and_offers_nothing(qapp):
    panel = StatePanel.working("Analysing", "Matching 268 orders against stock")
    assert "Matching 268 orders against stock" in _labels(panel)
    assert panel.button is None


def test_no_results_clears_filters_as_a_secondary_action(qapp):
    # The operator may actually want the empty answer, so this is not accented.
    panel = StatePanel.no_results(
        "No orders match", "Filter: courier is DPD and status is Blocked."
    )
    assert panel.button.text() == "Clear all filters"
    assert panel.button.property("role") == "secondary"


def test_failed_carries_its_detail_and_one_way_out(qapp):
    panel = StatePanel.failed(
        "The stock file could not be read",
        "Nothing can be allocated until it loads.",
        "stock_2026_09.csv: no column named Quantity",
        "Choose another file…",
    )
    assert "stock_2026_09.csv: no column named Quantity" in _labels(panel)
    assert panel.button.property("role") == "primary"


@pytest.mark.parametrize(
    "panel_factory",
    [
        lambda: StatePanel.nothing_loaded("t", "c", "a"),
        lambda: StatePanel.working("t", "s"),
        lambda: StatePanel.no_results("t", "c"),
        lambda: StatePanel.failed("t", "c", "d", "a"),
    ],
)
def test_every_variant_has_at_most_one_accent_filled_action(qapp, panel_factory):
    panel = panel_factory()
    primaries = [
        b for b in panel.findChildren(QPushButton) if b.property("role") == "primary"
    ]
    assert len(primaries) <= 1


def test_no_variant_says_no_data(qapp):
    """"No data · Nothing to display" cannot distinguish "you have not loaded
    anything" from "your filter is too tight" from "the server is unreachable"."""
    panel = StatePanel.nothing_loaded("No orders loaded", "Choose a file.", "Open…")
    assert not any("No data" in text for text in _labels(panel))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_state_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.components.state_panel'`

- [ ] **Step 3: Implement**

Create `gui/components/state_panel.py`:

```python
"""What a screen shows instead of its table when there is nothing to show.

One widget with four constructors, replacing per-screen invention. The rule
every variant obeys: name the cause, name the file or filter that caused it,
and offer the action that resolves it. No apologies, no exclamation marks.

"No data · Nothing to display" is the thing none of them may be -- that
sentence cannot tell "you have not loaded anything" from "your filter is too
tight" from "the server is unreachable".

It *holds* a Card rather than subclassing one: QSS type selectors match
className() exactly (see build_stylesheet's own note), so a subclass would
need its own selector in shared/theme.py -- a packing-tool PR for a plane this
widget can have for free by composing.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §5
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from gui.components.card import Card
from gui.theme_manager import get_theme_manager
from shared.theme import set_button_role


class StatePanel(QWidget):
    """A centred card explaining why a screen is empty, and what to do next.

    Attributes:
        card: the Card holding the text and the action.
        button: the single action, or None when the state has none.
    """

    def __init__(
        self,
        title: str,
        cause: str,
        *,
        detail: str = "",
        action_text: str = "",
        action_role: str = "primary",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.card = Card(min_width=360, margins=(24, 20, 24, 20), spacing=8)
        self.card.add_text(title, "heading", wrap=True)
        self.card.add_text(cause, "body", wrap=True)

        if detail:
            theme = get_theme_manager().get_current_theme()
            # 9.11 gives this line the one mono face; until then it is caption
            # in the secondary colour. The Qt tier has no mono family and
            # adding one is a token, which belongs to shared/ and to 9.11.
            self.card.add_text(
                detail, "caption", wrap=True, css=f"color: {theme.text_secondary};"
            )

        self.button = None
        if action_text:
            self.button = QPushButton(action_text)
            set_button_role(self.button, action_role)
            self.card.layout().addWidget(self.button, 0, Qt.AlignCenter)

        # Centring is stretches, not margins -- a margin has to be recomputed
        # for every page size the card lands on.
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self.card, 0, Qt.AlignCenter)
        outer.addStretch(1)

    @classmethod
    def nothing_loaded(cls, title, cause, action_text, parent=None):
        """Nothing has been loaded yet. One accent-filled way to load it."""
        return cls(title, cause, action_text=action_text, parent=parent)

    @classmethod
    def working(cls, title, step, parent=None):
        """Work is in flight. A named step beats a shimmer for a supervisor
        watching a network share, and Qt has no animation to shimmer with."""
        return cls(title, step, parent=parent)

    @classmethod
    def no_results(cls, title, cause, action_text="Clear all filters", parent=None):
        """A filter emptied the list. Secondary, because the operator may
        actually want the empty answer."""
        return cls(title, cause, action_text=action_text,
                   action_role="secondary", parent=parent)

    @classmethod
    def failed(cls, title, cause, detail, action_text, parent=None):
        """Something broke. State the consequence, then the cause in the
        file's own words, then the way out."""
        return cls(title, cause, detail=detail, action_text=action_text,
                   parent=parent)
```

- [ ] **Step 4: Export it**

In `gui/components/__init__.py`, add
`from gui.components.state_panel import StatePanel` and `"StatePanel"` to
`__all__`, both in alphabetical position.

- [ ] **Step 5: Run and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_state_panel.py -v
.venv/bin/ruff check gui/ tests/ --exclude shared
git add -A
git commit -m "Phase 9.6: one empty state, not forty"
```

---

## Task 8: Both themes, whole suite, PR

**Files:**
- Modify: `tests/test_components_render_roles.py`

- [ ] **Step 1: Add the render pass**

`tests/test_components_render_roles.py` already renders the component library
in both themes. Add `StatePanel` (one of each variant) and a `StatusChip` for
each of the eleven states in spec §3.5 × the four `live`/`manual`
combinations, following the file's existing pattern. This is where "in both
themes" from 9.3's `Done when` is actually proved.

- [ ] **Step 2: Run the whole suite and the linter**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Both must be clean. The suite runs in about a minute since #311.

- [ ] **Step 3: Update the graph**

```bash
graphify update .
```

Note in the PR body that this is still **owed in the main checkout** for
Bundles 1 and 2 as well — a worktree has no `graphify-out/`.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin worktree-phase9-bundle3-components
```

The PR body must carry: the packing-tool PR link (Tasks 1–2), the two
deliberate departures from the artboards (no mono yet, §5.3; zero StatePanel
call sites, §5.4), the eleven-not-thirteen state count (§3.6), and which of
spec §8's three questions the user answered.

---

## Self-review notes

- **Spec coverage.** §3 → Tasks 1–3; §4 → Tasks 4–6; §5 → Task 7; §7 → Task 2;
  §9 → the test steps throughout plus Task 8.
- **Not covered on purpose:** F5's 13-state count (§3.6, 9.19 owns the
  remaining two), F7's mono detail (§5.3, 9.11 owns the face), and wiring
  `StatePanel` into a screen (§5.4, Bundles 4 and 6 own their own).
- **Naming consistency:** `status_style` / `StatusStyle` / `paint_status_mark`
  / `MARK_PX` / `MARK_LEFT_PX` / `MARK_RING_WIDTH` in `shared/theme.py`;
  `RING_WIDTH` / `caps` / `first_visible_column` / `last_visible_column` /
  `header_of` / `paint_selection_ring` / `SelectionRingDelegate` in
  `gui/selection_ring.py`; `edge_rect` / `paints_edge` / `edge_token` on
  `StatusEdgeDelegate`.
- **Task 3 imports `gui.selection_ring`, which Task 4 creates.** Run Task 4
  first if you want a green suite at every boundary.
