# Phase 9 Bundle 4 — the shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The shell gets its four command-bar states, one overflow menu for
the five controls that have no home, and a first-run screen that a launch
with an unreachable share can actually reach.

**Architecture:** `CommandBar` gains a `set_state(BarState)` that gates
whether a right-hand primary exists, while the existing `bind_action`
mechanism keeps deciding *which* button it is — two axes, one `_refresh()`.
A new `OverflowMenu` component takes the client-scoped and machine-scoped
actions off the rail footer and off the Analysis Results screen overflow.
`ProfileManager` learns to construct without a reachable share, so
`MainWindow` can open degraded and drive every control that would touch the
share from one `connectionChanged` signal.

**Tech Stack:** PySide6 (Qt 6), pytest with `QT_QPA_PLATFORM=offscreen`,
ruff. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-04-phase9-bundle4-shell-design.md` —
read it before Task 1. The plan argues from it and does not repeat its
reasoning.

## Global Constraints

- **Never hand-edit `shared/`.** It is one-way synced from `../packing-tool`.
  This plan changes exactly one `shared/` file, `navrail.py`, and it does so
  in Task 7 by editing packing-tool and running `scripts/sync_shared.py`.
  Every other task treats `shared/` as read-only.
- **Two repos, two PRs.** The packing-tool PR merges first. Check
  `gh pr list` in **both** repos when orienting — Bundle 3 lost a run to a
  Stage C that saw an empty list in one repo and concluded there were no
  open PRs.
- **No hardcoded colours.** Every colour comes from a `ThemeTokens` field.
  `tests/test_no_hardcoded_colors.py` enforces it.
- **No `font-size:` literal anywhere under `gui/`** — including inside raw
  CSS in a `.py` file. `tests/test_type_scale.py` bans the string with no
  escape hatch. Use `font_css("caption")` / `font_css("body")`.
- **Token names and roles are frozen.** Values move; names never do.
- **1366×768 is the design case.** Page width is 1310 (1366 − 56 rail),
  page height 692 (768 − 48 bar − 28 status bar).
- **Measurements:** rail 56, command bar 48, page padding 16, status bar 28.
- **Never elides, at any width:** the session ID, the status chip, the
  primary button's label, the overflow button.
- **Copy rules:** sentence case, active voice, no apologies, no exclamation
  marks. An action keeps one name through the whole flow — "Server
  connection…" is spelled identically in the empty state and in the menu.
- **PR-only.** Branch `worktree-phase9-bundle4-shell` already exists; never
  commit to `main`.
- **Gate before the PR:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m
  pytest` and `.venv/bin/ruff check . --exclude shared`. Run
  `./scripts/setup_venv.sh` first in a fresh worktree.

---

## File Structure

| File | Responsibility |
|---|---|
| `gui/components/overflow.py` | **Create.** `OverflowMenu(QMenu)` and its `QToolButton` — sections, items, an exclusive choice group, and the QSS the global sheet does not supply for `QToolButton`. |
| `gui/components/commandbar.py` | **Modify.** `BarState` enum, `set_state`, the New Session and Open-folder buttons, the overflow button, the degradation ladder. |
| `gui/components/__init__.py` | **Modify.** Export `OverflowMenu`, `BarState`. |
| `gui/ui_manager.py` | **Modify.** Delete the rail footer, wire the overflow, wrap Setup in a stack, add the status-bar chip, strip theme + client settings out of the screen overflow. |
| `gui/main_window_pyside.py` | **Modify.** `connectionChanged` signal; `_init_managers` opens degraded. |
| `shopify_tool/profile_manager.py` | **Modify.** `require_connection` keyword. |
| `tests/test_components_overflow.py` | **Create.** The menu in isolation. |
| `tests/test_commandbar_states.py` | **Create.** State × bound-button matrix, and the degradation ladder. |
| `tests/test_first_run.py` | **Create.** The whole-window test that is 9.9's `Done when`, plus the footer-deletion guard. |
| `tests/test_components_navrail.py` | **Modify.** Four `add_footer_item` tests deleted with the method. |
| `shared/navrail.py` | **Synced, never hand-edited.** Task 7. |
| `CONTEXT.md` | Already updated at Stage A — Shell, Destination, Overflow, Connection state. |

In `../packing-tool`, on its own worktree and its own PR (Task 7):

| File | Responsibility |
|---|---|
| `shared/navrail.py` | **Modify.** Delete `NavRail.add_footer_item`. |
| `tests/test_navrail.py` | **Modify.** Delete its footer test. |

---

## Task order and why

Tasks 1–3 are leaves with no dependency on each other and each ends green.
Task 4 is the startup change, which Task 5 needs. Task 6 deletes the footer
and can only run once the overflow exists. Task 7 is the whole-window test.
Task 8 is the PR.

Task 7 is the packing-tool half. It must run **after** Task 5, which removes
the only call site — deleting the method first would break this repo's suite
between two tasks for no reason.

All three of the spec's questions were answered on 2026-09-04 and the plan
below is written for the answers, with no conditional branches left in it.
The two rejected paths — keeping the modal recovery prompt, and leaving
`add_footer_item` alive in `shared/` — are not options here. If a step seems
to want one of them, re-read spec §8 rather than improvising.

---

### Task 1: `OverflowMenu`

**Files:**
- Create: `gui/components/overflow.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_overflow.py`

**Interfaces:**
- Consumes: `shared.theme.font_css`, `gui.theme_manager.get_theme_manager`,
  `shared.theme.on_theme_changed`.
- Produces:
  - `OverflowMenu(QMenu)` with
    `add_section(title: str) -> QAction`,
    `add_item(text: str, slot) -> QAction`,
    `add_choice_group(labels: list[str], current: str, slot) -> QActionGroup`
  - `overflow_button(menu: OverflowMenu, parent=None) -> QToolButton`

- [ ] **Step 1: Write the failing test**

```python
"""The command-bar overflow: two scopes, one menu."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.overflow import OverflowMenu, overflow_button


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_a_section_header_is_a_disabled_action(qapp):
    menu = OverflowMenu()
    header = menu.add_section("THIS PC")
    assert header.text() == "THIS PC"
    # Disabled, so keyboard navigation steps over it and QSS can style it as
    # a header. addSection() would hand the drawing to Qt, which cannot carry
    # the type treatment the artboard pins.
    assert not header.isEnabled()


def test_an_item_runs_its_slot(qapp):
    menu = OverflowMenu()
    calls = []
    menu.add_item("Client settings…", lambda: calls.append(1)).trigger()
    assert calls == [1]


def test_a_choice_group_is_exclusive_and_starts_on_current(qapp):
    menu = OverflowMenu()
    picked = []
    group = menu.add_choice_group(["Light", "Dark"], "Dark", picked.append)

    checked = [a for a in group.actions() if a.isChecked()]
    assert [a.text() for a in checked] == ["Dark"]

    group.actions()[0].trigger()
    assert picked == ["Light"]
    # Exclusive: picking Light unchecks Dark without a second signal.
    assert [a.text() for a in group.actions() if a.isChecked()] == ["Light"]


def test_the_menu_is_the_width_the_artboard_specifies(qapp):
    menu = OverflowMenu()
    menu.add_section("THIS PC")
    menu.add_item("Server connection…", lambda: None)
    assert menu.minimumWidth() == 284


def test_the_button_opens_on_press_not_on_a_second_click(qapp):
    from PySide6.QtWidgets import QToolButton

    menu = OverflowMenu()
    button = overflow_button(menu)
    # InstantPopup: one press opens it. MenuButtonPopup would split the
    # button into an action half and an arrow half, and there is no action.
    assert button.popupMode() == QToolButton.InstantPopup
    assert button.menu() is menu
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_overflow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.components.overflow'`

- [ ] **Step 3: Write minimal implementation**

Create `gui/components/overflow.py`:

```python
"""The menu beside an object holding what configures it.

The rail is for destinations, so anything that configures the client or this
PC lands here instead. Two sections: the client's own name, then THIS PC --
the header shows a scope a rail item never could.

No icons: seven items with seven icons is a colour chart. Section headers are
disabled QActions rather than QMenu.addSection(), because addSection hands the
drawing to Qt and the artboard pins the type treatment.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle4-shell-design.md §4
"""

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton

from gui.theme_manager import get_theme_manager
from shared.theme import font_css, on_theme_changed

MENU_WIDTH = 284
ROW_HEIGHT = 28
MARK_COLUMN = 16   # keeps labels aligned whether or not anything is ticked


class OverflowMenu(QMenu):
    """Sections of app-level actions, styled to the artboard's rungs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(MENU_WIDTH)
        self.setToolTipsVisible(True)
        # The theme switch lives inside this menu, so a one-shot stylesheet
        # would go stale the moment it is used. ADR 0003.
        on_theme_changed(self, lambda _t: self._apply_theme())

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self.setStyleSheet(
            f"QMenu {{ background-color: {theme.surface_overlay};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_md}px; padding: 4px; }}"
            f"QMenu::item {{ {font_css('body')} color: {theme.text};"
            f" height: {ROW_HEIGHT}px; padding-left: {MARK_COLUMN + 8}px;"
            f" padding-right: 12px; }}"
            f"QMenu::item:selected {{ background-color: {theme.selection_bg}; }}"
            f"QMenu::item:disabled {{ {font_css('caption')}"
            f" color: {theme.text_secondary}; }}"
            f"QMenu::indicator {{ width: {MARK_COLUMN}px; }}"
        )

    def add_section(self, title: str) -> QAction:
        """A scope header. Disabled, so it is skipped by keyboard navigation."""
        header = QAction(title, self)
        header.setEnabled(False)
        self.addAction(header)
        return header

    def add_item(self, text: str, slot) -> QAction:
        item = QAction(text, self)
        item.triggered.connect(lambda _checked=False: slot())
        self.addAction(item)
        return item

    def add_choice_group(self, labels: list[str], current: str, slot) -> QActionGroup:
        """Mutually exclusive checkable items.

        Two items rather than one toggle: "Dark mode: off" is a sentence
        nobody reads correctly the first time.
        """
        group = QActionGroup(self)
        group.setExclusive(True)
        for label in labels:
            item = QAction(label, self)
            item.setCheckable(True)
            item.setChecked(label == current)
            item.triggered.connect(lambda _c=False, name=label: slot(name))
            group.addAction(item)
            self.addAction(item)
        return group


def overflow_button(menu: OverflowMenu, parent=None) -> QToolButton:
    """The three-dot button that opens the menu on one press.

    build_stylesheet has a QPushButton rule but no QToolButton one, so the
    global `QWidget { background-color: surface }` would leave this flat with
    no border and no hover.

    ponytail: this QSS is a near-copy of ui_manager._style_results_overflow.
    Not extracted, because Bundle 12 replaces the Analysis Results screen with
    the web tier and takes that call site with it. If Bundle 12 slips past
    Bundle 10, hoist this and delete the copy there.
    """
    button = QToolButton(parent)
    button.setText("⋯")
    button.setPopupMode(QToolButton.InstantPopup)
    button.setMenu(menu)

    def restyle(_tokens=None):
        theme = get_theme_manager().get_current_theme()
        button.setStyleSheet(
            f"QToolButton {{ background-color: {theme.surface_raised};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_sm}px; padding: 2px 6px;"
            f" color: {theme.text}; }}"
            f"QToolButton:hover {{ background-color: {theme.hover}; }}"
            f"QToolButton::menu-indicator {{ image: none; }}"
        )

    on_theme_changed(button, restyle)
    return button
```

Append to `gui/components/__init__.py`'s imports and `__all__`:

```python
from .overflow import OverflowMenu, overflow_button
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_overflow.py -v`
Expected: PASS (5 tests)

If `theme.radius_sm` or `theme.selection_bg` raises `AttributeError`, grep
`shared/theme.py` for the real field name and use it — token names are
frozen, so whatever is there is correct and this plan's guess is not.

- [ ] **Step 5: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check . --exclude shared`
Expected: PASS. `tests/test_no_hardcoded_colors.py` and
`tests/test_type_scale.py` both scan this new file.

- [ ] **Step 6: Commit**

```bash
git add gui/components/overflow.py gui/components/__init__.py tests/test_components_overflow.py
git commit -m "feat(shell): OverflowMenu, the menu beside the object it configures"
```

---

### Task 2: `CommandBar.set_state` and the four states

**Files:**
- Modify: `gui/components/commandbar.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_commandbar_states.py`

**Interfaces:**
- Consumes: `OverflowMenu`, `overflow_button` (Task 1).
- Produces:
  - `BarState` — an `enum.Enum` with `NO_CLIENT`, `NO_SESSION`, `SESSION`, `RUNNING`
  - `CommandBar.set_state(state: BarState) -> None`
  - `CommandBar.newSessionRequested = Signal()`
  - `CommandBar.openFolderRequested = Signal()`
  - `CommandBar.cancelRequested = Signal()`
  - `CommandBar.overflow: OverflowMenu` (built in `__init__`, populated by `ui_manager`)
  - `CommandBar.set_progress(percent: int, phase: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
"""The command bar's four states: exactly one primary, and it moves."""

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from gui.components.commandbar import BarState, CommandBar


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(qapp):
    widget = CommandBar()
    widget.resize(1310, 48)
    yield widget
    widget.deleteLater()


def test_no_client_has_no_primary_anywhere(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.NO_CLIENT)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()


def test_no_session_puts_the_primary_beside_the_selector(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.NO_SESSION)
    assert bar.new_session_button.isVisible()
    # The screen still has a bound button; the state says there is no
    # right-hand primary yet, and the state wins.
    assert not bar.action_button.isVisible()


def test_session_puts_the_screens_own_button_on_the_right(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.SESSION)
    assert bar.action_button.isVisible()
    assert bar.action_button.text() == "Run Analysis"
    assert not bar.new_session_button.isVisible()


def test_session_with_no_bound_button_still_has_no_primary(bar):
    bar.bind_action(None)
    bar.set_state(BarState.SESSION)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()


def test_running_has_no_primary_and_cancel_takes_the_danger_role(bar):
    bar.bind_action(QPushButton("Run Analysis"))
    bar.set_state(BarState.RUNNING)
    assert not bar.action_button.isVisible()
    assert not bar.new_session_button.isVisible()
    assert bar.cancel_button.isVisible()
    assert bar.cancel_button.property("role") == "danger"


def test_binding_after_the_state_is_set_still_resolves(bar):
    # Order must not matter: ui_manager sets the state on a connection change
    # and binds on a screen change, and neither knows which ran last.
    bar.set_state(BarState.SESSION)
    bar.bind_action(QPushButton("Generate Reports"))
    assert bar.action_button.isVisible()
    assert bar.action_button.text() == "Generate Reports"


def test_open_folder_appears_only_once_a_session_exists(bar):
    bar.set_state(BarState.NO_SESSION)
    assert not bar.open_folder_button.isVisible()
    bar.set_state(BarState.SESSION)
    assert bar.open_folder_button.isVisible()


def test_the_bar_is_the_height_every_later_screen_assumes(bar):
    assert bar.height() == 48
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py -v`
Expected: FAIL — `ImportError: cannot import name 'BarState'`

- [ ] **Step 3: Write minimal implementation**

In `gui/components/commandbar.py`, add near the top:

```python
import enum

from gui.components.overflow import OverflowMenu, overflow_button

BAR_HEIGHT = 48
_CLIENT_NAME_WIDTH = 200


class BarState(enum.Enum):
    """What the bar knows about, which decides where the one primary sits.

    Orthogonal to which screen is showing: the state decides *whether* a
    right-hand primary exists, bind_action decides *which button* it is.
    Collapsing the two would leave Generate Reports with no home.
    """

    NO_CLIENT = "no_client"
    NO_SESSION = "no_session"
    SESSION = "session"
    RUNNING = "running"
```

Add these signals to `CommandBar`:

```python
    newSessionRequested = Signal()
    openFolderRequested = Signal()
    cancelRequested = Signal()
```

In `CommandBar.__init__`, after `self.client_selector` is added and before
`self.session_label`:

```python
        self.setFixedHeight(BAR_HEIGHT)
        self.client_selector.setFixedWidth(_CLIENT_NAME_WIDTH)

        self.new_session_button = QPushButton("New Session", self)
        set_button_role(self.new_session_button, "primary")
        self.new_session_button.clicked.connect(self.newSessionRequested.emit)
        self.new_session_button.hide()
        layout.addWidget(self.new_session_button)
```

Immediately after `layout.addWidget(self.session_label)`:

```python
        # Icon-only: its target is the string to its left.
        self.open_folder_button = QToolButton(self)
        self.open_folder_button.setAutoRaise(True)
        self.open_folder_button.setToolTip("Open session folder")
        self.open_folder_button.clicked.connect(self.openFolderRequested.emit)
        self.open_folder_button.hide()
        layout.addWidget(self.open_folder_button)
```

Replace the bare `layout.addStretch()` with:

```python
        self.progress_label = QLabel("", self)
        self.progress_label.setStyleSheet(font_css("caption"))
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        self._spacer = layout.addStretch()
```

After `layout.addWidget(self.action_button)`:

```python
        self.cancel_button = QPushButton("Cancel", self)
        set_button_role(self.cancel_button, "danger")
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        layout.addWidget(self.overflow_button)

        self._state = BarState.NO_CLIENT
        self._progress = (0, "")
```

Add the two methods (put `_refresh` next to `bind_action`, and call
`self._refresh()` at the end of the existing `bind_action` and `set_action`):

```python
    def set_state(self, state: BarState) -> None:
        """Which of the four situations the bar is in. See BarState."""
        self._state = state
        self._refresh()

    def set_progress(self, percent: int, phase: str) -> None:
        self._progress = (percent, phase)
        self._refresh()

    def _refresh(self) -> None:
        """Resolve state and bound button into what is actually visible.

        One method rather than two setters that each hide things: with two,
        whichever ran last won, and ui_manager calls them from a connection
        change and a screen change that do not know about each other.
        """
        state = self._state
        has_session = state in (BarState.SESSION, BarState.RUNNING)

        self.session_label.setVisible(has_session)
        self.open_folder_button.setVisible(has_session)
        self.status_chip.setVisible(has_session and bool(self.status_chip.text()))

        self.new_session_button.setVisible(state is BarState.NO_SESSION)
        self.cancel_button.setVisible(state is BarState.RUNNING)
        self.action_button.setVisible(
            state is BarState.SESSION and bool(self.action_button.text())
        )

        percent, phase = self._progress
        self.progress_label.setVisible(state is BarState.RUNNING)
        self.progress_label.setText(
            f"{phase} {percent}%" if phase else f"{percent}%"
        )
```

`StatusChip` may expose its label under a different accessor than `.text()`;
grep `shared/theme.py` for `class StatusChip` and use the real one.

Export from `gui/components/__init__.py`:

```python
from .commandbar import BarState, CommandBar
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the existing command-bar suite, which will have moved**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_commandbar.py tests/test_shell.py -v`

`tests/test_components_commandbar.py` has ~25 tests written before states
existed, several of which assert `action_button` visibility after
`set_action`. A fresh `CommandBar` is now `NO_CLIENT`, so those go from
visible to hidden.

**This is a behaviour change, not a regression.** Fix each by adding
`bar.set_state(BarState.SESSION)` to the test that needs a right-hand
primary. Do **not** default `_state` to `SESSION` to keep them green — the
first thing a launched app shows is `NO_CLIENT`, and a default that
disagrees with the app's first frame is a trap for Task 5.

- [ ] **Step 6: Commit**

```bash
git add gui/components/commandbar.py gui/components/__init__.py tests/test_commandbar_states.py tests/test_components_commandbar.py
git commit -m "feat(shell): the command bar's four states, one primary that moves"
```

---

### Task 3: The degradation ladder

**Files:**
- Modify: `gui/components/commandbar.py`
- Test: `tests/test_commandbar_states.py` (append)

**Interfaces:**
- Consumes: `BarState`, `_refresh` (Task 2).
- Produces: `CommandBar.resizeEvent` applies the ladder; nothing new is called
  from outside.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_commandbar_states.py`:

```python
# The worst realistic content: the longest client name a validated id can
# produce (20 chars, profile_manager.validate_client_id) and a session id.
_WORST_CLIENT = "CLIENT_WAREHOUSE_NTH"
_WORST_SESSION = "Session 2026-09-04_18-45-02"


def _loaded(bar):
    bar.set_clients([_WORST_CLIENT])
    bar.set_current_client(_WORST_CLIENT)
    bar.set_session(_WORST_SESSION)
    bar.set_status("status_warning", "Analysis complete")
    bar.set_action("Generate Reports")
    bar.set_state(BarState.SESSION)
    return bar


def test_the_never_truncate_four_survive_the_design_width(bar):
    _loaded(bar)
    bar.resize(1310, 48)
    QApplication.processEvents()

    assert bar.session_label.text() == _WORST_SESSION
    assert bar.action_button.text() == "Generate Reports"
    assert bar.overflow_button.isVisible()
    assert bar.status_chip.isVisible()


def test_the_client_name_is_what_gives_way_first(bar):
    _loaded(bar)
    bar.resize(700, 48)
    QApplication.processEvents()

    # Step 2 of the ladder fired; step 4 did not, because New Session is not
    # even shown in this state.
    assert bar.client_selector.width() <= 200
    assert bar.session_label.text() == _WORST_SESSION


def test_progress_keeps_the_percentage_and_drops_the_phase(bar):
    _loaded(bar)
    bar.set_state(BarState.RUNNING)
    bar.set_progress(62, "Allocating stock")
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.progress_label.text() == "Allocating stock 62%"

    bar.resize(620, 48)
    QApplication.processEvents()
    assert bar.progress_label.text() == "62%"


def test_new_session_goes_icon_only_last(bar):
    bar.set_clients([_WORST_CLIENT])
    bar.set_current_client(_WORST_CLIENT)
    bar.set_state(BarState.NO_SESSION)
    bar.resize(1310, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == "New Session"

    bar.resize(420, 48)
    QApplication.processEvents()
    assert bar.new_session_button.text() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py -k ladder or truncate or progress or icon_only -v`
Expected: FAIL — the phase name survives at 620px and New Session keeps its
label at 420px.

- [ ] **Step 3: Write minimal implementation**

In `gui/components/commandbar.py`:

```python
# The ladder, widest trigger first. Qt's own elision has no order and would
# take the session ID first because it is the longest string in the row --
# and an elided ID is a wrong ID.
_LADDER = (
    (1100, "spacer"),      # inter-group spacer collapses to 8px
    (900, "client"),       # client name elides inside its 200px
    (700, "progress"),     # progress drops the phase name, keeps the percent
    (500, "new_session"),  # New Session goes icon-only
)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_ladder(self.width())

    def _apply_ladder(self, width: int) -> None:
        fired = {name for trigger, name in _LADDER if width < trigger}

        self.layout().setSpacing(8 if "spacer" in fired else 12)

        self.client_selector.setFixedWidth(
            120 if "client" in fired else _CLIENT_NAME_WIDTH
        )

        percent, phase = self._progress
        if "progress" in fired or not phase:
            self.progress_label.setText(f"{percent}%")
        else:
            self.progress_label.setText(f"{phase} {percent}%")

        self.new_session_button.setText(
            "" if "new_session" in fired else "New Session"
        )
```

Delete the two `progress_label.setText` lines from `_refresh` and call
`self._apply_ladder(self.width())` at the end of `_refresh` instead — the
ladder is the only place that text is composed, so a state change and a
resize cannot disagree about it.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py -v`
Expected: PASS (12 tests)

If `test_the_client_name_is_what_gives_way_first` still fails because the
selector's *text* is not elided, add
`self.client_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)`
in `__init__`. A `QComboBox` elides its current text to its own width once it
is not free to grow.

- [ ] **Step 5: Commit**

```bash
git add gui/components/commandbar.py tests/test_commandbar_states.py
git commit -m "feat(shell): a fixed degradation order, and four things that never elide"
```

---

### Task 4: A launch that cannot reach the share

**Files:**
- Modify: `shopify_tool/profile_manager.py:131-142`
- Modify: `gui/main_window_pyside.py:65-152`
- Test: `tests/test_first_run.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ProfileManager(require_connection: bool = True)`
  - `MainWindow.connectionChanged = Signal(bool)`
  - `MainWindow.is_connected() -> bool`

The `while True` loop and `prompt_for_recovery_path` come out entirely. The
recovery prompt is not lost — it is what `ConnectionSettingsDialog` offers,
and Task 5 puts that dialog in the overflow and in the empty state's one
button. Spec §8 Q1.

- [ ] **Step 1: Write the failing test**

```python
"""First run: the shell with nothing configured.

Every test here points the app at a path that does not exist, which is what
an unreachable UNC share looks like from inside ProfileManager.
"""

import pytest
from PySide6.QtWidgets import QApplication

from shopify_tool.profile_manager import NetworkError, ProfileManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def unreachable(tmp_path, monkeypatch):
    """A path under a file, so mkdir cannot succeed and neither can a touch."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    path = blocker / "server"
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(path))
    return path


def test_the_default_still_refuses_to_construct(unreachable):
    # The existing contract is unchanged for every caller that does not ask.
    with pytest.raises(NetworkError):
        ProfileManager()


def test_require_connection_false_returns_a_usable_object(unreachable):
    manager = ProfileManager(require_connection=False)
    assert manager.is_network_available is False
    # Every path it publishes is still a real Path, so no call site becomes
    # None-unsafe and no None-guard is written anywhere.
    assert manager.base_path.name == "server"
    assert manager.clients_dir.parent == manager.base_path


def test_a_reachable_share_is_unaffected_by_the_keyword(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    assert ProfileManager(require_connection=False).is_network_available is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'require_connection'`

- [ ] **Step 3: Write minimal implementation**

In `shopify_tool/profile_manager.py`, change the signature to accept
`require_connection: bool = True` and replace the raise block:

```python
        self.connection_timeout = 5
        self.is_network_available = self._test_connection()

        if not self.is_network_available:
            if require_connection:
                raise NetworkError(
                    f"Cannot connect to file server at {self.base_path}\n\n"
                    f"Please check:\n"
                    f"1. Network connection\n"
                    f"2. File server is online\n"
                    f"3. Path is correct and accessible"
                )
            # The caller has a shell to render the failure in. Every path
            # above is still real, so nothing downstream becomes None -- the
            # controls that would touch the share are disabled instead, and
            # that disabling is the guard. Spec §5.1.
            logger.warning(f"Opening without a reachable server: {self.base_path}")
            return
```

Document the keyword in the class docstring's `Args:` block.

In `gui/main_window_pyside.py`, replace the `while True` block in
`_init_managers` with:

```python
        try:
            self.profile_manager = ProfileManager(require_connection=False)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize profile managers:\n{e!s}",
            )
            QApplication.quit()
            return
```

Add to the `MainWindow` class body, beside the other class attributes:

```python
    # One boolean, one signal, and every control that would touch the share is
    # driven from it. See CONTEXT.md, "Connection state".
    connectionChanged = Signal(bool)
```

and the accessor, near `load_client_config`:

```python
    def is_connected(self) -> bool:
        return bool(getattr(self.profile_manager, "is_network_available", False))
```

At the end of `__init__`, after `self.setup_logging()`:

```python
        # Emitted once the widgets exist, so every slot has something to
        # disable. Re-emitted by the Server Connection dialog on success.
        self.connectionChanged.emit(self.is_connected())
```

`prompt_for_recovery_path` is no longer imported here; remove the import so
ruff's F401 stays clean. The recovery path is still reachable — it is what
`ConnectionSettingsDialog` offers, and Task 5 puts that in the overflow.

`SessionManager`, `GroupsManager` and `TableConfigManager` all take the
manager, not the share, and construct fine against an unreachable one. If any
of them raises here, the existing `except Exception` below already catches it
— but check the log, because a constructor that touches the disk at import
time is a Task 4 bug and not a Task 7 one.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS. Any test that asserted the app quits on an unreachable share
is asserting the old contract — update it and say so in the commit body.

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/profile_manager.py gui/main_window_pyside.py tests/test_first_run.py
git commit -m "feat(shell): open degraded instead of quitting when the share is unreachable"
```

---

### Task 5: Wire the overflow, the status chip, and the Setup stack

**Files:**
- Modify: `gui/ui_manager.py` — `_create_command_bar`, `_create_tabs`,
  `_create_tab1_session_setup`, `_create_results_overflow`, `create_widgets`
- Modify: `gui/main_window_pyside.py` — `connect_signals`
- Test: `tests/test_first_run.py` (append)

**Interfaces:**
- Consumes: `OverflowMenu` (Task 1), `BarState` (Task 2),
  `connectionChanged` (Task 4), `StatePanel` (shipped in Bundle 3).
- Produces:
  - `mw.setup_stack: QStackedWidget` — page 0 the panel, page 1 the form
  - `mw.setup_state_panel: StatePanel`
  - `mw.connection_chip: StatusChip` in the status bar
  - `UIManager._on_connection_changed(connected: bool)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_first_run.py`:

```python
@pytest.fixture
def offline_window(unreachable):
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_window_opens_at_all(offline_window):
    # The contract this bundle changed: an unreachable share used to quit.
    assert offline_window.isVisible()
    assert offline_window.is_connected() is False


def test_only_setup_and_info_stay_enabled(offline_window):
    rail = offline_window.nav_rail
    enabled = [i for i in range(5) if rail.button(i).isEnabled()]
    # Disabled, never hidden: a rail that grows items as you configure the
    # app never lets you learn its shape.
    assert enabled == [0, 3]
    assert all(rail.button(i).isVisible() for i in range(5))


def test_setup_shows_the_panel_and_names_the_path(offline_window, unreachable):
    assert offline_window.setup_stack.currentIndex() == 0
    texts = [
        child.text()
        for child in offline_window.setup_state_panel.findChildren(type(
            offline_window.setup_state_panel.card
        ).__mro__[0])
    ]
    panel_text = offline_window.setup_state_panel.findChildren(object)
    rendered = " ".join(
        w.text() for w in offline_window.setup_state_panel.findChildren(
            __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel
        )
    )
    assert "can't reach the fulfilment server" in rendered
    assert str(unreachable) in rendered
    assert "!" not in rendered            # errors do not exclaim
    assert "sorry" not in rendered.lower()  # and do not apologise


def test_the_one_accent_pixel_is_the_way_out(offline_window):
    button = offline_window.setup_state_panel.button
    assert button.text() == "Server connection…"
    assert button.property("role") == "primary"


def test_the_status_bar_says_so_too(offline_window):
    chip = offline_window.connection_chip
    assert chip.isVisible()
    assert "unreachable" in chip.text().lower()


def test_the_rail_has_five_items_and_no_footer(offline_window):
    from PySide6.QtWidgets import QToolButton

    rail = offline_window.nav_rail
    assert len(rail.findChildren(QToolButton)) == 5
    assert not hasattr(offline_window, "connection_btn")
```

Simplify `test_setup_shows_the_panel_and_names_the_path` to just the
`QLabel` join when you write it for real — the first two statements in it are
scaffolding this plan could not resolve without the widget in front of it.

```python
def test_setup_shows_the_panel_and_names_the_path(offline_window, unreachable):
    from PySide6.QtWidgets import QLabel

    assert offline_window.setup_stack.currentIndex() == 0
    rendered = " ".join(
        label.text()
        for label in offline_window.setup_state_panel.findChildren(QLabel)
    )
    assert "can't reach the fulfilment server" in rendered
    assert str(unreachable) in rendered
    assert "!" not in rendered
    assert "sorry" not in rendered.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute 'setup_stack'`

- [ ] **Step 3a: Populate the overflow**

In `gui/ui_manager.py`, extend `_create_command_bar`:

```python
        bar.newSessionRequested.connect(
            lambda: self.mw.actions_handler.create_new_session()
        )
        bar.openFolderRequested.connect(self._open_session_folder)
        self._populate_overflow(bar)
        return bar

    def _populate_overflow(self, bar) -> None:
        """The client's own scope, then this PC. Spec §4.1.

        Rebuilt on a client change, because the first section's header is the
        client's name and a stale header points at the wrong profile.
        """
        menu = bar.overflow
        menu.clear()

        client = self.mw.current_client_id or "No client"
        menu.add_section(client)
        item = menu.add_item(
            "Client settings…",
            lambda: self.mw.actions_handler.open_settings_window(),
        )
        item.setEnabled(bool(self.mw.current_client_id))

        menu.add_section("THIS PC")
        menu.add_item("Server connection…", self._open_connection_settings)

        current = "Dark" if get_theme_manager().is_dark_theme() else "Light"
        menu.add_choice_group(
            ["Light", "Dark"],
            current,
            lambda name: get_theme_manager().set_theme(name.lower()),
        )
```

`_open_connection_settings` keeps its body but re-emits afterwards, so the
dialog is the second thing that can change connection state:

```python
    def _open_connection_settings(self):
        """Open the Server Connection settings dialog.

        Re-checks afterwards: this dialog is the only way back from a
        degraded launch, so the shell has to hear about a success.
        """
        ConnectionSettingsDialog(
            self.mw, "ShopifyTool", "FULFILLMENT_SERVER_PATH", PROD_SERVER_PATH
        ).exec()
        self.mw.profile_manager.is_network_available = (
            self.mw.profile_manager._test_connection()
        )
        self.mw.connectionChanged.emit(self.mw.is_connected())
```

- [ ] **Step 3b: Delete the rail footer**

In `_create_tabs`, delete the three lines that build `mw.connection_btn` and
its tooltip and connection. Delete `"connection_btn": "settings",` from
`_BUTTON_ICONS`. Delete entry `2` from `_SCREEN_ACTIONS` and add
`new_session_btn` to the unconditional hide beside the other screen actions —
Bundle 5 removes the widget; this bundle only stops drawing it.

- [ ] **Step 3c: Strip the screen overflow**

In `_create_results_overflow`, delete `self.mw.settings_button_tab2`, the
`menu.addSeparator()` below Undo, `self.mw.theme_toggle_btn`, its
`on_theme_changed` line, and the `_update_theme_button_text` and
`_on_theme_toggle_clicked` methods. Both actions now live in the command-bar
overflow; keeping them here would make theme the second duplicated action,
and Server Connection is meant to be the only one.

Update `tests/test_analysis_results_1b_chrome.py:133` — it asserts on
`theme_toggle_btn`. Move the assertion to the command-bar overflow's choice
group, or drop it if the surrounding test is about the screen's chrome only.

- [ ] **Step 3d: The Setup stack**

At the end of `_create_tab1_session_setup`, wrap what it returns:

```python
        from PySide6.QtWidgets import QStackedWidget

        from gui.components.state_panel import StatePanel

        stack = QStackedWidget()
        self.mw.setup_state_panel = StatePanel.failed(
            "This PC can't reach the fulfilment server",
            "Clients, stock files and past sessions all live on the server. "
            "Until this PC reaches it, there is nothing to set up.",
            str(self.mw.profile_manager.base_path),
            "Server connection…",
        )
        self.mw.setup_state_panel.button.clicked.connect(
            self._open_connection_settings
        )
        stack.addWidget(self.mw.setup_state_panel)   # page 0
        stack.addWidget(widget)                      # page 1, the form
        self.mw.setup_stack = stack
        return stack
```

`widget` is whatever the method currently returns — read the last line before
editing and keep the name.

- [ ] **Step 3e: The status-bar chip and the one slot**

At the end of `create_widgets`, replacing `showMessage("Ready")`:

```python
        self.mw.statusBar().setFixedHeight(28)
        self.mw.connection_chip = StatusChip(
            "status_success", "Server connected",
            get_theme_manager().get_current_theme(), parent=self.mw,
        )
        self.mw.statusBar().addPermanentWidget(self.mw.connection_chip)

        self.mw.connectionChanged.connect(self._on_connection_changed)
```

and the slot:

```python
    _OFFLINE_RAIL_ITEMS = (1, 2, 4)   # Results, Browse, Tools

    def _on_connection_changed(self, connected: bool) -> None:
        """The one signal that drives every control which touches the share.

        The disabling is the guard, not decoration on top of one: no call site
        below carries a None-check, because none of them is reachable while
        this is False. Spec §5.1.
        """
        for index in self._OFFLINE_RAIL_ITEMS:
            self.mw.nav_rail.button(index).setEnabled(connected)
        if not connected:
            self.mw.nav_rail.set_current(0)

        self.mw.setup_stack.setCurrentIndex(1 if connected else 0)

        # Resting when connected -- nothing to act on. Live when not.
        # Hollow either way: the system derived it, no person set it.
        self.mw.connection_chip.set_status(
            "status_success" if connected else "status_danger",
            "Server connected" if connected else "Server unreachable",
            get_theme_manager().get_current_theme(),
            live=not connected,
            manual=False,
        )

        if not connected:
            self.mw.command_bar.set_state(BarState.NO_CLIENT)
```

Check `StatusChip.set_status`'s real signature in `shared/theme.py` before
writing this — Bundle 3 added `live` and `manual` and the parameter order is
whatever it shipped as, not whatever this plan guessed.

- [ ] **Step 3f: Drive the state from the app**

In `gui/main_window_pyside.py`'s `connect_signals`, alongside the existing
client wiring:

```python
        self.command_bar.clientChanged.connect(
            lambda _c: self.ui_manager._populate_overflow(self.command_bar)
        )
```

and set the state wherever the app already knows it changed. The three sites
are: `load_client_config` (→ `NO_SESSION`), wherever `session_path` is
assigned after a session is created (→ `SESSION`), and
`_analysis_running` being set and cleared (→ `RUNNING` / back to `SESSION`).
Grep `_analysis_running` — it is already a single flag with two write sites,
which is why the state machine can hang off it rather than needing one of its
own.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check . --exclude shared`

- [ ] **Step 6: Commit**

```bash
git add gui/ui_manager.py gui/main_window_pyside.py tests/test_first_run.py tests/test_analysis_results_1b_chrome.py
git commit -m "feat(shell): one overflow, one connection signal, no rail footer"
```

---

### Task 6: The second beat, and the shell's measurements

**Files:**
- Modify: `gui/ui_manager.py` — `_on_connection_changed`, `_create_tab1_session_setup`
- Test: `tests/test_first_run.py` (append), `tests/test_shell.py` (append)

**Interfaces:**
- Consumes: everything from Task 5.
- Produces: `UIManager._refresh_setup_panel()` — swaps the panel between its
  two forms. No third layout.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_first_run.py`:

```python
@pytest.fixture
def online_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_a_reachable_share_with_no_clients_asks_for_one(online_window):
    from PySide6.QtWidgets import QLabel

    assert online_window.is_connected() is True
    assert online_window.setup_stack.currentIndex() == 0
    rendered = " ".join(
        label.text()
        for label in online_window.setup_state_panel.findChildren(QLabel)
    )
    assert "Choose a client to begin" in rendered


def test_the_second_beat_has_no_accent_pixel_of_its_own(online_window):
    # The action is the selector, which takes focus; the primary reappears in
    # the command bar as New Session once a client exists. No third layout.
    assert online_window.setup_state_panel.button is None
    assert online_window.command_bar.client_selector.hasFocus()


def test_every_rail_item_is_enabled_once_the_share_answers(online_window):
    rail = online_window.nav_rail
    assert all(rail.button(i).isEnabled() for i in range(5))
```

Append to `tests/test_shell.py`:

```python
def test_the_shell_leaves_the_page_the_size_later_screens_assume(main_window):
    """1366x768 minus rail 56, command bar 48 and status bar 28."""
    main_window.resize(1366, 768)
    QApplication.processEvents()

    assert main_window.nav_rail.width() == 56
    assert main_window.command_bar.height() == 48
    assert main_window.statusBar().height() == 28

    page = main_window.width() - main_window.nav_rail.width()
    assert page == 1310
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py tests/test_shell.py -v`
Expected: FAIL — the connected window shows page 1 with no client, and the
panel still says the share is unreachable.

- [ ] **Step 3: Write minimal implementation**

Replace the fixed `StatePanel` construction in `_create_tab1_session_setup`
with an empty page-0 container the swap fills, and add:

```python
    def _refresh_setup_panel(self) -> None:
        """Page 0's two forms. Connection first, then client. No third one.

        A new panel each time rather than mutating one: StatePanel's four
        constructors differ in whether they have a button at all, and a
        widget that grows and loses a button is two widgets wearing one name.
        """
        if not self.mw.is_connected():
            panel = StatePanel.failed(
                "This PC can't reach the fulfilment server",
                "Clients, stock files and past sessions all live on the "
                "server. Until this PC reaches it, there is nothing to set up.",
                str(self.mw.profile_manager.base_path),
                "Server connection…",
            )
            panel.button.clicked.connect(self._open_connection_settings)
        else:
            panel = StatePanel.nothing_loaded(
                "Choose a client to begin",
                "Pick a client in the bar above. Sessions, stock and reports "
                "all belong to one client.",
                "",
            )
            self.mw.command_bar.client_selector.setFocus()

        old = self.mw.setup_stack.widget(0)
        self.mw.setup_stack.insertWidget(0, panel)
        self.mw.setup_stack.removeWidget(old)
        old.deleteLater()
        self.mw.setup_state_panel = panel
```

`StatePanel.nothing_loaded` requires `action_text`; passing `""` leaves
`panel.button` as `None`, which is what the second beat wants. If its
signature makes `action_text` positional-required with no empty-string path,
call `StatePanel(title, cause)` directly — the classmethod is a convenience,
not a gate.

In `_on_connection_changed`, replace the `setCurrentIndex` line with:

```python
        self._refresh_setup_panel()
        self.mw.setup_stack.setCurrentIndex(
            1 if connected and self.mw.current_client_id else 0
        )
```

and call the same two lines from `load_client_config`'s tail, so choosing a
client moves the stack to the form.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_first_run.py tests/test_shell.py -v`
Expected: PASS

`test_the_second_beat_has_no_accent_pixel_of_its_own` asserts focus, which is
unreliable on an offscreen platform if the window never activated. If it
flakes, call `online_window.activateWindow()` in the fixture before
`processEvents()`; if it still flakes, assert
`command_bar.client_selector.focusPolicy() != Qt.NoFocus` and that
`_refresh_setup_panel` called `setFocus` (spy on it), rather than deleting
the claim.

- [ ] **Step 5: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check . --exclude shared`

- [ ] **Step 6: Commit**

```bash
git add gui/ui_manager.py tests/test_first_run.py tests/test_shell.py
git commit -m "feat(shell): first run's second beat, and the page size later screens assume"
```

---

### Task 7: Delete `add_footer_item` from `shared/` (the packing-tool half)

**Files (in `../packing-tool`, a separate worktree — see Step 1):**
- Modify: `shared/navrail.py` — delete `NavRail.add_footer_item`
- Modify: `tests/test_navrail.py:63` — delete the footer test

**Files (here, after the sync):**
- Modify: `shared/navrail.py` — written by `scripts/sync_shared.py`, never by hand

**Interfaces:**
- Consumes: Task 5 Step 3b, which removed this repo's only call site.
- Produces: nothing. This task removes API; it adds none.

**Why this is a second PR.** `shared/` is owned by `packing-tool` and is
one-way synced. A `shared/` file edited in this repo is silently overwritten
by the next sync, so the deletion has to be authored there. Spec §4.4, §8 Q2.

- [ ] **Step 1: Create the packing-tool worktree**

This bundle's shopify worktree already exists. packing-tool needs its own,
and it has **no `scripts/setup_venv.sh`** — unlike this repo, its worktrees
need `.venv` linked by hand or every pytest call fails with "command not
found". Both facts cost Bundle 3 real time.

```bash
cd /home/cognitiveghost/Desktop/Projects/packing-tool
git worktree add .claude/worktrees/phase9-bundle4-shell -b worktree-phase9-bundle4-shell
ln -s /home/cognitiveghost/Desktop/Projects/packing-tool/.venv \
      .claude/worktrees/phase9-bundle4-shell/.venv
```

- [ ] **Step 2: Delete packing-tool's footer test and watch it fail**

In the packing-tool worktree, delete the test at `tests/test_navrail.py:63`
that calls `rail.add_footer_item(QIcon(), "Server")` — read the whole test
function first and delete it entirely, not just the line.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_navrail.py -v`
Expected: PASS, with one fewer test than before. This is the inverse of the
usual red-green order because the deliverable *is* a deletion: the test that
proves the change is the one that stops existing, and what must stay green is
everything else.

- [ ] **Step 3: Delete the method**

In the packing-tool worktree, delete `NavRail.add_footer_item` from
`shared/navrail.py` — the whole method including its docstring, which
explains why a footer item was deliberately outside the exclusive group.
That reasoning dies with the method; the rail is for destinations now.

- [ ] **Step 4: Run packing-tool's suite and lint**

Run, from the packing-tool worktree:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: PASS. If anything else in packing-tool referenced the method, it
did not at the time this plan was written — grep `add_footer_item` across
that repo before assuming a failure is unrelated.

- [ ] **Step 5: Commit and open the packing-tool PR**

```bash
git add shared/navrail.py tests/test_navrail.py
git commit -m "refactor(navrail): drop add_footer_item, the rail is for destinations"
git push -u origin worktree-phase9-bundle4-shell
gh pr create --draft --title "Phase 9.8 (packing-tool half): the rail loses its footer slot" --body-file <path>
```

The PR body must say that shopify's Bundle 4 PR is the consumer, that the
method was dead in both apps, and that the rule is "the rail is for
destinations" — a reviewer seeing only a deletion cannot otherwise tell
whether something was lost.

- [ ] **Step 6: Sync back into this repo**

**Pass the packing-tool worktree path, not the packing-tool repo root.** The
repo root resolves to `main`'s `shared/`, syncs it with no error, and the
deletion silently does not arrive. This is the single most expensive trap in
a two-repo bundle and it cost Bundle 3 a run.

```bash
.venv/bin/python scripts/sync_shared.py \
  /home/cognitiveghost/Desktop/Projects/packing-tool/.claude/worktrees/phase9-bundle4-shell
grep -c add_footer_item shared/navrail.py   # must print 0
```

- [ ] **Step 7: Prove the method is gone from this repo too**

Append to `tests/test_first_run.py`:

```python
def test_the_rail_cannot_grow_a_footer_again():
    """The rail is for destinations, so there is no API for anything else.

    tests/test_components_navrail.py held four tests for add_footer_item;
    they were deleted with the method. This asserts the deletion rather than
    the behaviour, because the behaviour no longer exists to assert.
    """
    from shared.navrail import NavRail

    assert not hasattr(NavRail, "add_footer_item")
```

Delete the four `add_footer_item` tests in
`tests/test_components_navrail.py` (around lines 81–130) — read each in full
and remove the whole function, not the calling line.

- [ ] **Step 8: Run the gate and commit the sync**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check . --exclude shared`
Expected: PASS.

```bash
git add shared/navrail.py tests/test_first_run.py tests/test_components_navrail.py
git commit -m "chore(shared): sync navrail without add_footer_item"
```

---

### Task 8: Gate, docs, and the PR

**Files:**
- Modify: `README.md:3`, `gui_main.py:11`, `shopify_tool/__init__.py:7` — only
  if the repo owner is cutting a version with this bundle; otherwise skip.
- Create: `docs/adr/0004-opening-without-a-reachable-server.md`

- [ ] **Step 1: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check . --exclude shared`
Expected: PASS, both. Record the test count in the PR body.

- [ ] **Step 2: Write ADR 0004**

The startup contract change qualifies on all three of the repo's tests: it is
hard to reverse (every control is now gated on `connection_state`), it is
surprising without context (a future reader asks why `ProfileManager` has a
`require_connection` keyword), and it was a real trade-off — fail-fast
modal-or-quit is a legitimate design and was the shipped one.

Write `docs/adr/0004-opening-without-a-reachable-server.md` following the
shape of `docs/adr/0003-theme-restyling-is-a-closure-not-a-repolish.md`.
State the rejected option (fail fast) and the argument that the disabled
controls, not a scatter of null checks, are the guard.

- [ ] **Step 3: Run graphify**

Per `CLAUDE.md`, `graphify update .` must run in the **main checkout** — the
Bash guard refuses it from a worktree. Note it as owed in the PR body and in
`state.md` if it cannot run here.

- [ ] **Step 4: Open the PR**

The body must carry, or a reviewer will ask for each:

- the startup-contract change and a link to ADR 0004
- the two departures from the artboards: section headers are not mono until
  9.11, and S4 is built as a startup change rather than a layout (spec §9)
- what left the Analysis Results screen overflow, and why (spec §4.2)
- the three decisions from spec §8, and that the shopify-only footer option
  was recommended and overruled — a reviewer should not re-open it
- the test count from Step 1
- the packing-tool PR link, and that it **merges first**

```bash
git push -u origin worktree-phase9-bundle4-shell
gh pr create --draft --title "Phase 9 Bundle 4: the shell" --body-file <path>
```

---

## Self-Review

**Spec coverage.** §3 anatomy → Tasks 2, 6. §3.1–3.2 four states → Task 2.
§3.3 degradation → Task 3. §4 overflow → Tasks 1, 5. §4.1 the five controls →
Tasks 2 (New Session, Open folder), 5 (the other three). §4.2 what leaves the
screen overflow → Task 5 Step 3c. §4.3 the indicator → Task 5 Step 3e. §4.4
rail footer → Task 5 Step 3b (the call site) and Task 7 (the method). §5.1
degraded launch → Task 4. §5.2 the two forms → Tasks 5, 6. §5.3 the
duplicated action → covered by both call sites using the identical string,
asserted in Task 5. §6 the five seams → Tasks 1, 3, 1, 4, 5 respectively. §7
decisions → carried in the code comments each task writes. §8 the three
answers → Task 4 (Q1), Task 7 (Q2), Task 5 Step 3e (Q3). §9 departures →
Task 8's PR body.

**No branches left.** Every "if the owner answered…" note is gone, replaced
by the decided path. A step that appears to offer a choice between the modal
prompt and a degraded launch, or between deleting `add_footer_item` and
leaving it, is a plan bug — spec §8 has the answers.

**Placeholders.** None. Three places name a signature this plan could not
read (`StatusChip.set_status`, `StatePanel.nothing_loaded`'s `action_text`,
`theme.radius_sm`) — each says explicitly to grep the real one and that the
shipped name wins over this plan's guess. That is an instruction, not a TODO.

**Type consistency.** `BarState` is spelled the same in Tasks 2, 3 and 5.
`connectionChanged` / `is_connected` / `_on_connection_changed` are spelled
the same in Tasks 4, 5 and 6. `setup_stack` / `setup_state_panel` /
`_refresh_setup_panel` are consistent across Tasks 5 and 6.
`_populate_overflow` takes `bar` in both its definition (Task 5, Step 3a) and
its caller (Task 5, Step 3f).
