# Phase 9 Bundle 5 — Session Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task, in this session. Do **not** use
> subagent-driven-development — the roadmap runner works in-session by
> design. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Session Setup screen's four group boxes, splitter and
recent-sessions strip with one card of three rows, move Resume into a new
command-bar session picker, and make the `AddProductDialog` low-stock warning
read the client's configured threshold.

**Architecture:** Two new app-local components (`FileSlot`, `RadioCard`) and
two one-method extensions to existing ones (`Card.add_widget`,
`FormSection(label_width=…)`). `FileSlot` takes ownership of file validity,
which today is stored as the string `"✓"` inside a `QLabel` and read back by
`FileHandler.check_files_ready`. The Setup page is then rebuilt from those
components and ~9 obsolete builder methods are deleted.

**Tech Stack:** Python 3, PySide6 (Qt 6), pytest + pytest-qt, ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-phase9-bundle5-session-setup-design.md`
— read it before Task 1. It carries the reasoning; this plan carries the
steps.

## Global Constraints

- **Windows-only product, Linux dev machine.** Run everything through the
  repo venv: `.venv/bin/python`. `python` and `ruff` are not on `PATH`.
  Tests need `QT_QPA_PLATFORM=offscreen`.
- **Never hand-edit `shared/`.** It is synced one-way from `../packing-tool`.
  Nothing in this bundle needs a `shared/` change; if you think it does,
  stop and say so.
- **No hardcoded colours.** Every colour comes from
  `get_theme_manager().get_current_theme()`. No `#666`, no `gray`.
- **Token names are frozen** (Phase 9 parent). Use existing tokens:
  `surface_raised`, `border`, `text_secondary`, `status_danger`,
  `status_danger_bg`, `spacing_xs|sm|md|lg` (4/8/12/16), `radius_md` (6).
- **Type roles** are `caption` / `body` / `label` / `heading` via
  `font_css(role)` from `gui.theme_manager`. An unknown role raises.
- **Copy rules:** sentence case, no all-caps labels, no colons on row
  labels, active voice, errors state the consequence before the cause.
- **PR-only.** Branch `worktree-phase9-bundle5-session-setup` is already
  checked out. Never commit to `main`.
- **Gate before the PR:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m
  pytest` fully green, and `.venv/bin/ruff check . --exclude shared` clean.
- **After merge (not now):** `graphify update .`

---

### Task 1: `Card.add_widget` and `FormSection(label_width=…)`

The two existing components gain the one thing each lacks. `Card` today only
takes centred text (`add_text`); `FormSection` today has no way to pin its
label column.

**Files:**
- Modify: `gui/components/card.py`
- Modify: `gui/components/form_section.py`
- Test: `tests/test_components_setup_card.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Card.add_widget(widget: QWidget) -> None`
  - `FormSection(title: str, description: str = "", *, label_width: int = 0, parent=None)`
  - `FormSection.add_row(label, widget, tooltip="") -> QLabel` — unchanged
    signature; when `label_width` is non-zero the returned label is fixed to
    that width.

- [ ] **Step 1: Write the failing test**

Create `tests/test_components_setup_card.py`:

```python
"""Card and FormSection gain the two things the setup card needs.

Card could only take centred text; FormSection could not pin its label
column, which is what the 208px gutter in Bundle 5's setup card is.
"""

from PySide6.QtWidgets import QLabel, QLineEdit

from gui.components import Card, FormSection


def test_card_takes_an_arbitrary_widget(qapp):
    card = Card()
    child = QLabel("not centred")
    card.add_widget(child)
    assert child.parent() is card
    assert card.layout().indexOf(child) != -1


def test_form_section_pins_its_label_column(qapp):
    section = FormSection("", label_width=208)
    label = section.add_row("Session name", QLineEdit())
    assert label.width() == 208
    assert label.minimumWidth() == 208
    assert label.maximumWidth() == 208


def test_form_section_without_label_width_leaves_labels_free(qapp):
    section = FormSection("")
    label = section.add_row("Session name", QLineEdit())
    assert label.maximumWidth() > 208
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_setup_card.py -v
```

Expected: FAIL — `Card` has no attribute `add_widget`, and `FormSection`
takes no `label_width`.

If `qapp` is not a known fixture, check `tests/conftest.py` for the
project's Qt application fixture name and use that instead — do not add a
new one.

- [ ] **Step 3: Implement**

In `gui/components/card.py`, append to `Card`:

```python
    def add_widget(self, widget: QWidget) -> None:
        """Append a widget as-is, without the centring add_text applies.

        The setup card holds a form, not a stack of centred numbers.
        """
        self.layout().addWidget(widget)
```

Add `QWidget` to the `PySide6.QtWidgets` import line in that file.

In `gui/components/form_section.py`, change the constructor signature to:

```python
    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        label_width: int = 0,
        parent=None,
    ) -> None:
```

Immediately after `self.form.setSpacing(theme.spacing_sm)` add:

```python
        # A pinned label column is what the setup card's "208px gutter" is:
        # QFormLayout already lays each row out as label + field, so fixing
        # the label's width and letting the field grow gives that geometry
        # without a second row idiom in the app.
        self._label_width = label_width
        if label_width:
            self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            self.form.setRowWrapPolicy(QFormLayout.DontWrapRows)
```

and in `add_row`, immediately after `row_label = QLabel(label)`:

```python
        if self._label_width:
            row_label.setFixedWidth(self._label_width)
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_setup_card.py -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -k "form_section or component" -v
```

Expected: PASS, and no existing `FormSection` caller breaks — `label_width`
is keyword-only with a zero default, so the settings pages are untouched.

- [ ] **Step 5: Commit**

```bash
git add gui/components/card.py gui/components/form_section.py tests/test_components_setup_card.py
git commit -m "feat(components): Card.add_widget and FormSection label gutter"
```

---

### Task 2: `RadioCard`

A radio button that explains its option, replacing `analysis_mode_combo`.

**Files:**
- Create: `gui/components/radio_card.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_radio_card.py` (create)

**Interfaces:**
- Consumes: `Card.add_widget` is not used here.
- Produces: `RadioCard(title: str, description: str, parent=None)` — a
  `QRadioButton` subclass. `.title_text` and `.description_text` are the
  strings it was given. Behaves as a normal `QRadioButton` for
  `QButtonGroup`, `isChecked()`, `setChecked()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_components_radio_card.py`:

```python
"""RadioCard: a radio button that says what choosing it does.

The combo it replaces made a supervisor read two words and guess what
"multi-item-first" meant.
"""

from PySide6.QtWidgets import QButtonGroup

from gui.components import RadioCard


def test_radio_card_keeps_its_strings(qapp):
    card = RadioCard("Multi-item first", "Fills orders that can go out whole.")
    assert card.title_text == "Multi-item first"
    assert card.description_text == "Fills orders that can go out whole."


def test_radio_card_is_a_radio_button(qapp):
    a = RadioCard("Multi-item first", "one")
    b = RadioCard("Oldest first", "two")
    group = QButtonGroup()
    group.addButton(a)
    group.addButton(b)

    a.setChecked(True)
    assert a.isChecked()
    b.setChecked(True)
    assert b.isChecked()
    assert not a.isChecked()


def test_radio_card_description_wraps(qapp):
    card = RadioCard("Oldest first", "x " * 60)
    assert card._description.wordWrap()


def test_radio_card_is_taller_than_a_bare_radio(qapp):
    card = RadioCard("Oldest first", "A description that occupies its own line.")
    assert card.sizeHint().height() > 30
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_radio_card.py -v
```

Expected: FAIL — `cannot import name 'RadioCard'`.

- [ ] **Step 3: Implement**

Create `gui/components/radio_card.py`:

```python
"""A radio button that states the consequence of choosing it.

Replaces the Analysis mode combo on Session Setup. The choice is made once
a day by a warehouse supervisor who should not have to ask a colleague what
"multi-item-first" means, so the option carries its own explanation rather
than hiding it in a tooltip nobody hovers.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QRadioButton, QVBoxLayout

from gui.theme_manager import font_css, get_theme_manager


class RadioCard(QRadioButton):
    """A radio button with a title and a wrapped description beneath it.

    The description is a child QLabel laid out below the button's own text,
    indented past the indicator so it reads as belonging to the option. The
    button's own text stays empty: giving QRadioButton two lines of text is
    what a QLabel is for, and an empty text keeps the indicator's vertical
    alignment on the first line where the title is.
    """

    _INDENT = 22  # indicator width + its spacing, so the description lines up

    def __init__(self, title: str, description: str, parent=None) -> None:
        super().__init__(title, parent)
        theme = get_theme_manager().get_current_theme()

        self.title_text = title
        self.description_text = description

        self.setStyleSheet(font_css("label"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._INDENT, theme.spacing_lg, theme.spacing_sm, theme.spacing_sm
        )
        layout.setSpacing(0)

        self._description = QLabel(description, self)
        self._description.setWordWrap(True)
        self._description.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        # Clicks on the description must still choose the option -- a
        # transparent label forwards them to the radio button underneath.
        self._description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._description)
```

Register it in `gui/components/__init__.py`: add
`from gui.components.radio_card import RadioCard` with the other imports and
`"RadioCard",` in `__all__`, both in alphabetical position.

- [ ] **Step 4: Run and confirm pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_radio_card.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/components/radio_card.py gui/components/__init__.py tests/test_components_radio_card.py
git commit -m "feat(components): RadioCard, a radio that states its consequence"
```

---

### Task 3: `FileSlot`

The widget that owns a file's validity. This is the task the rest of the
bundle depends on — read spec §4 before starting.

**Files:**
- Create: `gui/components/file_slot.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_file_slot.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:

```python
class FileSlot(QFrame):
    changed = Signal()                 # emitted on every state transition
    chooseFileRequested = Signal()     # the "Choose file…" button / drop-less route
    chooseFolderRequested = Signal()
    mapColumnsRequested = Signal()     # the invalid state's first recovery action
    pathDropped = Signal(str)          # a file or folder was dropped on the slot

    def __init__(self, title: str, hint: str, parent=None) -> None: ...

    path: Path | None
    is_valid: bool
    missing_columns: list[str]
    present_columns: list[str]

    def set_loaded(self, path: Path | str, summary: str) -> None: ...
    def set_invalid(
        self, path: Path | str, missing: list[str], present: list[str]
    ) -> None: ...
    def clear(self) -> None: ...

    # widgets later tasks address by name
    choose_button: QPushButton         # visible in the empty state
    map_columns_button: QPushButton    # visible in the invalid state
    choose_other_button: QPushButton   # visible in the invalid state
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_file_slot.py`:

```python
"""FileSlot owns whether a file is usable.

Before Bundle 5 that fact lived in a QLabel containing the string "✓",
which FileHandler.check_files_ready read back to decide whether Run
Analysis could be enabled.
"""

from pathlib import Path

import pytest

from gui.components import FileSlot


@pytest.fixture
def slot(qapp):
    return FileSlot("Orders file", "Drop the Shopify orders export here")


def test_a_new_slot_is_empty_and_not_valid(slot):
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.missing_columns == []
    assert slot.choose_button.isVisible() or not slot.isVisible()


def test_loading_a_file_makes_the_slot_valid(slot):
    slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows · 4 columns matched")
    assert slot.path == Path("/tmp/orders.csv")
    assert slot.is_valid is True
    assert slot.missing_columns == []


def test_an_invalid_file_is_not_valid_and_keeps_its_missing_columns(slot):
    slot.set_invalid(
        Path("/tmp/stock.csv"), ["Stock"], ["Артикул", "Име", "Цена"]
    )
    assert slot.path == Path("/tmp/stock.csv")
    assert slot.is_valid is False
    assert slot.missing_columns == ["Stock"]
    assert slot.present_columns == ["Артикул", "Име", "Цена"]


def test_the_invalid_state_offers_both_ways_out(slot):
    slot.set_invalid(Path("/tmp/stock.csv"), ["Stock"], ["Артикул"])
    assert slot.map_columns_button.isEnabled()
    assert slot.choose_other_button.isEnabled()


def test_the_error_names_the_consequence_before_the_cause(slot):
    slot.set_invalid(Path("/tmp/stock.csv"), ["Stock"], ["Артикул"])
    text = slot.error_text()
    assert text.index("Nothing can be allocated") < text.index("Stock")
    assert "stock.csv" in text
    assert "Артикул" in text


def test_clearing_returns_the_slot_to_empty(slot):
    slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows")
    slot.clear()
    assert slot.path is None
    assert slot.is_valid is False


def test_every_transition_emits_changed(slot, qtbot):
    with qtbot.waitSignal(slot.changed):
        slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows")
    with qtbot.waitSignal(slot.changed):
        slot.set_invalid(Path("/tmp/orders.csv"), ["SKU"], ["Name"])
    with qtbot.waitSignal(slot.changed):
        slot.clear()
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_slot.py -v
```

Expected: FAIL — `cannot import name 'FileSlot'`.

- [ ] **Step 3: Implement**

Create `gui/components/file_slot.py`:

```python
"""One input file: where it is, and whether it can be used.

Before this widget, a file's validity was the string "✓" rendered into a
QLabel, and its missing columns lived only in that label's tooltip.
FileHandler.check_files_ready read the check mark back to decide whether
Run Analysis could be enabled. FileSlot holds those facts as data, and the
three states the file can be in as one widget instead of seven.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from gui.theme_manager import font_css, get_theme_manager

_EMPTY, _LOADED, _INVALID = 0, 1, 2


class FileSlot(QFrame):
    """A file's three states in one widget: empty, loaded, invalid.

    The invalid state replaces the loaded card in place rather than opening
    a message box: a dismissed modal leaves no trace of which file is
    wrong, and the person who has to fix it is looking at this screen.
    """

    changed = Signal()
    chooseFileRequested = Signal()
    chooseFolderRequested = Signal()
    mapColumnsRequested = Signal()
    pathDropped = Signal(str)

    def __init__(self, title: str, hint: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self.path: Path | None = None
        self.is_valid = False
        self.missing_columns: list[str] = []
        self.present_columns: list[str] = []

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._build_empty(hint))
        self._stack.addWidget(self._build_loaded())
        self._stack.addWidget(self._build_invalid())
        self._apply_theme()
        self._stack.setCurrentIndex(_EMPTY)

    # ---- the three faces -------------------------------------------------

    def _build_empty(self, hint: str) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotEmpty")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        self._hint = QLabel(hint, page)
        self._hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint)

        row = QHBoxLayout()
        row.setAlignment(Qt.AlignCenter)
        self.choose_button = QPushButton("Choose file…", page)
        self.choose_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.choose_button)
        self.choose_folder_button = QPushButton("Choose folder…", page)
        self.choose_folder_button.clicked.connect(self.chooseFolderRequested.emit)
        row.addWidget(self.choose_folder_button)
        layout.addLayout(row)
        return page

    def _build_loaded(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotLoaded")
        layout = QVBoxLayout(page)

        self._loaded_name = QLabel("", page)
        layout.addWidget(self._loaded_name)
        self._loaded_summary = QLabel("", page)
        layout.addWidget(self._loaded_summary)

        row = QHBoxLayout()
        self.replace_button = QPushButton("Choose a different file", page)
        self.replace_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.replace_button)
        row.addStretch()
        layout.addLayout(row)
        return page

    def _build_invalid(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotInvalid")
        layout = QVBoxLayout(page)

        self._error_headline = QLabel("", page)
        layout.addWidget(self._error_headline)
        self._error_body = QLabel("", page)
        self._error_body.setWordWrap(True)
        layout.addWidget(self._error_body)

        row = QHBoxLayout()
        self.map_columns_button = QPushButton("Map columns…", page)
        self.map_columns_button.clicked.connect(self.mapColumnsRequested.emit)
        row.addWidget(self.map_columns_button)
        self.choose_other_button = QPushButton("Choose a different file", page)
        self.choose_other_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.choose_other_button)
        row.addStretch()
        layout.addLayout(row)
        return page

    # ---- state -----------------------------------------------------------

    def set_loaded(self, path, summary: str) -> None:
        self.path = Path(path)
        self.is_valid = True
        self.missing_columns = []
        self.present_columns = []
        self._loaded_name.setText(self.path.name)
        self._loaded_summary.setText(summary)
        self._stack.setCurrentIndex(_LOADED)
        self.changed.emit()

    def set_invalid(self, path, missing: list[str], present: list[str]) -> None:
        self.path = Path(path)
        self.is_valid = False
        self.missing_columns = list(missing)
        self.present_columns = list(present)
        self._error_headline.setText("Nothing can be allocated from this file")
        self._error_body.setText(self._body_text())
        self._stack.setCurrentIndex(_INVALID)
        self.changed.emit()

    def clear(self) -> None:
        self.path = None
        self.is_valid = False
        self.missing_columns = []
        self.present_columns = []
        self._stack.setCurrentIndex(_EMPTY)
        self.changed.emit()

    def error_text(self) -> str:
        """Headline plus body, as one string -- what the tests assert on."""
        return f"{self._error_headline.text()}\n{self._error_body.text()}"

    def _body_text(self) -> str:
        name = self.path.name if self.path else "This file"
        missing = ", ".join(self.missing_columns)
        present = ", ".join(self.present_columns)
        return (
            f"{name} has no column mapped to {missing}. "
            f"Analysis needs one to know what is on hand. "
            f"The file's columns are: {present}."
        )

    # ---- drop ------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.pathDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()

    # ---- theme -----------------------------------------------------------

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self._hint.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        self._loaded_name.setStyleSheet(font_css("body"))
        self._loaded_summary.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        self._error_headline.setStyleSheet(
            f"color: {theme.status_danger}; {font_css('label')}"
        )
        self._error_body.setStyleSheet(font_css("caption"))
        self.setStyleSheet(f"""
            QWidget#FileSlotEmpty {{
                border: 2px dashed {theme.border};
                border-radius: {theme.radius_md}px;
                min-height: 96px;
            }}
            QWidget#FileSlotLoaded {{
                border: 1px solid {theme.border};
                border-radius: {theme.radius_md}px;
            }}
            QWidget#FileSlotInvalid {{
                border: 1px solid {theme.status_danger};
                border-radius: {theme.radius_md}px;
                background-color: {theme.status_danger_bg};
            }}
        """)
```

Wire the theme refresh next to the other components' pattern: add

```python
from shared.theme import on_theme_changed
```

and at the end of `__init__`:

```python
        on_theme_changed(self, lambda _t=None: self._apply_theme())
```

Register in `gui/components/__init__.py`: `from gui.components.file_slot
import FileSlot` and `"FileSlot",` in `__all__`.

- [ ] **Step 4: Run and confirm pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_slot.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add gui/components/file_slot.py gui/components/__init__.py tests/test_file_slot.py
git commit -m "feat(components): FileSlot owns a file's validity"
```

---

### Task 4: the command bar's session picker

`session_label` becomes a menu button. Read spec §6 — this extends Bundle
4's frozen four-state contract, so the state table in the test is the
contract.

**Files:**
- Modify: `gui/components/commandbar.py:157-159` and its `_refresh`/state code
- Modify: `tests/test_commandbar_states.py`
- Test: `tests/test_commandbar_states.py`

**Interfaces:**
- Consumes: nothing.
- Produces on `CommandBar`:
  - `session_button: QToolButton` (replaces `session_label`)
  - `session_menu: QMenu`
  - `sessionChosen = Signal(str)` — emits the session path
  - `browseAllRequested = Signal()`
  - `set_recent_sessions(items: list[tuple[str, str]]) -> None` where each
    item is `(display_name, session_path)`, most recent first, capped at 5
    by the caller
  - `set_session_text(text: str) -> None` — replaces every existing
    `session_label.setText(...)` call site

- [ ] **Step 1: Write the failing test**

Append to `tests/test_commandbar_states.py`:

```python
def test_the_session_button_reads_open_recent_with_no_session(qapp):
    from gui.components import BarState, CommandBar

    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1")])
    bar.set_state(BarState.NO_SESSION)
    assert bar.session_button.isVisible() or not bar.isVisible()
    assert bar.session_button.text() == "Open recent"
    assert bar.session_button.isEnabled()


def test_the_session_button_is_disabled_when_the_client_has_no_sessions(qapp):
    from gui.components import BarState, CommandBar

    bar = CommandBar()
    bar.set_recent_sessions([])
    bar.set_state(BarState.NO_SESSION)
    assert not bar.session_button.isEnabled()


def test_the_session_id_is_never_elided(qapp):
    from gui.components import BarState, CommandBar

    bar = CommandBar()
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.SESSION)
    assert bar.session_button.text() == "2026-09-04_tuesday-restock"
    assert bar.session_button.maximumWidth() >= 16777215


def test_the_picker_is_disabled_while_a_run_holds_the_turn(qapp):
    from gui.components import BarState, CommandBar

    bar = CommandBar()
    bar.set_session_text("2026-09-04_tuesday-restock")
    bar.set_state(BarState.RUNNING)
    assert bar.session_button.text() == "2026-09-04_tuesday-restock"
    assert not bar.session_button.isEnabled()


def test_choosing_a_session_emits_its_path(qapp, qtbot):
    from gui.components import CommandBar

    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1"), ("Monday", "/s/2")])
    actions = [a for a in bar.session_menu.actions() if a.data()]
    with qtbot.waitSignal(bar.sessionChosen) as caught:
        actions[0].trigger()
    assert caught.args == ["/s/1"]


def test_the_menu_ends_with_a_route_to_the_browser(qapp, qtbot):
    from gui.components import CommandBar

    bar = CommandBar()
    bar.set_recent_sessions([("Tuesday restock", "/s/1")])
    last = bar.session_menu.actions()[-1]
    assert "Browse all sessions" in last.text()
    with qtbot.waitSignal(bar.browseAllRequested):
        last.trigger()
```

Match the import style already used at the top of that file — if it imports
`CommandBar` once at module level, use that instead of the per-test imports
above.

- [ ] **Step 2: Run and confirm failure**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py -v
```

Expected: FAIL — `CommandBar` has no `session_button`.

- [ ] **Step 3: Implement**

In `gui/components/commandbar.py`, add the two signals beside the existing
ones:

```python
    sessionChosen = Signal(str)
    browseAllRequested = Signal()
```

Replace lines 157–159 (`self.session_label = QLabel(...)` and its
`addWidget`) with:

```python
        # A menu button, not a label: the recent-sessions strip Bundle 5
        # deletes from the Setup page was the only route back to yesterday's
        # work, and navigation belongs in the shell. Bundle 4 §3.3 forbids
        # eliding the session ID at any width, so no maximum width is set
        # and the style is TextBesideIcon with no icon.
        self.session_button = QToolButton(self)
        self.session_button.setAutoRaise(True)
        self.session_button.setPopupMode(QToolButton.InstantPopup)
        self.session_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.session_button.setStyleSheet(font_css("caption"))
        self.session_menu = QMenu(self.session_button)
        self.session_button.setMenu(self.session_menu)
        layout.addWidget(self.session_button)
        self._recent: list[tuple[str, str]] = []
        self._session_text = ""
```

Add `QMenu` and `QToolButton` to the widgets import if not already present
(`QToolButton` is — `open_folder_button` uses it).

Add the two methods:

```python
    def set_recent_sessions(self, items: list[tuple[str, str]]) -> None:
        """Fill the picker. `items` is (display name, session path), newest
        first — the caller caps the list, because how many sessions are
        "recent" is the screen's decision, not the bar's."""
        self._recent = list(items)
        self.session_menu.clear()
        for name, path in self._recent:
            action = self.session_menu.addAction(name)
            action.setData(path)
            action.triggered.connect(
                lambda _checked=False, p=path: self.sessionChosen.emit(p)
            )
        if self._recent:
            self.session_menu.addSeparator()
        browse = self.session_menu.addAction("Browse all sessions…\tCtrl+3")
        browse.triggered.connect(lambda _checked=False: self.browseAllRequested.emit())
        self._refresh()

    def set_session_text(self, text: str) -> None:
        self._session_text = text
        self._refresh()
```

In `_refresh()`, replace whatever currently shows/hides `session_label`
with:

```python
        if self._state is BarState.NO_CLIENT:
            self.session_button.hide()
        else:
            self.session_button.show()
            if self._state is BarState.NO_SESSION:
                self.session_button.setText("Open recent")
                self.session_button.setEnabled(bool(self._recent))
            else:
                self.session_button.setText(self._session_text)
                self.session_button.setEnabled(self._state is BarState.SESSION)
```

Then find every remaining `session_label` reference in the repo and route
it through `set_session_text`:

```bash
rtk grep -rn "session_label" gui/ tests/
```

`ui_manager.py`'s `_create_command_bar` keeps `update_session_info_label()`
working — change the attribute it writes, not the method's name.

- [ ] **Step 4: Run and confirm pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_commandbar_states.py tests/test_components_commandbar.py tests/test_shell.py -v
```

Expected: PASS. If `test_components_commandbar.py` asserts on
`session_label`, update it to `session_button` — the widget moved, the
contract did not.

- [ ] **Step 5: Commit**

```bash
git add gui/components/commandbar.py gui/ui_manager.py tests/
git commit -m "feat(commandbar): the session id becomes a picker"
```

---

### Task 5: `FileHandler` reads slots, not check marks

The root-cause half of the bundle. Do this **before** rebuilding the page,
so the page has something correct to attach to.

**Files:**
- Modify: `gui/file_handler.py:350-460` (`validate_file`, `check_files_ready`)
- Test: `tests/test_file_handler.py`

**Interfaces:**
- Consumes: `FileSlot` from Task 3.
- Produces: `mw.orders_slot` and `mw.stock_slot` are the two `FileSlot`
  instances Task 6 creates; `FileHandler` addresses them by those names.
  `validate_file(file_type)` no longer writes to any label.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_file_handler.py` (match the file's existing fixtures for
`mw` / client config — do not invent new ones):

```python
def test_check_files_ready_reads_the_slots_not_a_check_mark(main_window, tmp_path):
    """The bug this replaces: validity was the string "✓" in a QLabel."""
    handler = main_window.file_handler
    orders = tmp_path / "orders.csv"
    stock = tmp_path / "stock.csv"
    orders.write_text("x")
    stock.write_text("x")

    main_window.orders_slot.set_loaded(orders, "1 row")
    main_window.stock_slot.set_loaded(stock, "1 row")
    assert handler.check_files_ready() is True

    main_window.stock_slot.set_invalid(stock, ["Stock"], ["SKU"])
    assert handler.check_files_ready() is False


def test_a_stock_file_missing_its_quantity_column_puts_the_slot_in_error(
    main_window, tmp_path
):
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул;Име;Цена\nA1;Widget;9.99\n")
    main_window.stock_file_path = str(stock)

    main_window.file_handler.validate_file("stock")

    slot = main_window.stock_slot
    assert slot.is_valid is False
    assert slot.missing_columns
    assert slot.map_columns_button.isEnabled()
    assert slot.choose_other_button.isEnabled()
    assert "Nothing can be allocated" in slot.error_text()
```

- [ ] **Step 2: Run and confirm failure**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_handler.py -v
```

Expected: FAIL — `main_window` has no `orders_slot` yet. That is correct:
Task 6 creates them. To keep this task independently runnable, add the two
slots to the main window **in this task**, in
`UIManager._create_tab1_session_setup`, before the full page rebuild:

```python
        from gui.components import FileSlot

        self.mw.orders_slot = FileSlot(
            "Orders file", "Drop the Shopify orders export here"
        )
        self.mw.stock_slot = FileSlot("Stock file", "Drop the stock export here")
```

- [ ] **Step 3: Implement**

In `validate_file`, replace the whole `theme = ...` / `if is_valid:` /
`else:` block at the end with:

```python
        slot = (
            self.mw.orders_slot if file_type == "orders" else self.mw.stock_slot
        )
        if is_valid:
            slot.set_loaded(path, self._summary_for(path, required_cols))
            self.log.info(f"'{file_type}' file is valid.")
        else:
            present = core.read_csv_headers(path, delimiter)
            slot.set_invalid(path, missing_cols, present)
            self.log.warning(
                f"'{file_type}' file is invalid. Missing columns: "
                f"{', '.join(missing_cols)}"
            )
```

and delete the now-unused `label = self.mw.*_file_status_label` assignments
in both branches of the `if file_type == "orders":` block above.

Add the summary helper to `FileHandler`:

```python
    def _summary_for(self, path, required_cols: list[str]) -> str:
        """"1 842 rows · 4 columns matched" -- what the loaded slot shows.

        A row count is the one number that tells a supervisor they picked
        this morning's export and not last Friday's.
        """
        rows = core.count_csv_rows(path)
        return f"{rows:,} rows · {len(required_cols)} columns matched".replace(
            ",", " "
        )
```

If `core.read_csv_headers` and `core.count_csv_rows` do not exist, add them
to `shopify_tool/core.py` beside `validate_csv_headers`, which already opens
the file and reads its header row — reuse its delimiter and encoding
handling rather than writing a second CSV reader:

```python
def read_csv_headers(file_path, delimiter=",") -> list[str]:
    """The column names a CSV actually has. Used to tell someone which
    columns are there when the one they need is not."""
    ...


def count_csv_rows(file_path, delimiter=",") -> int:
    """Data rows, excluding the header."""
    ...
```

Write a test for each in `tests/test_core.py` before implementing them
(same red/green cycle), including the empty-file and header-only cases.

Then replace `check_files_ready`'s first two statements with:

```python
        orders_ok = self.mw.orders_slot.is_valid
        stock_ok = self.mw.stock_slot.is_valid
```

leaving the rest of the method as it is.

- [ ] **Step 4: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -v
```

Expected: the file-handler tests pass. Some setup-layout tests will still
fail — Task 6 rewrites them. Note which, and move on.

- [ ] **Step 5: Commit**

```bash
git add gui/file_handler.py gui/ui_manager.py shopify_tool/core.py tests/
git commit -m "fix(setup): file validity is data, not a check mark in a label"
```

---

### Task 6: rebuild the Setup page

The deletion task. Read spec §3 and §7 — §7 is the exact list.

**Files:**
- Modify: `gui/ui_manager.py` — `_create_tab1_session_setup`,
  `_create_session_setup_panel`, and delete the nine builders in spec §7
- Modify: `gui/main_window_pyside.py:231-232, 264-267, 341, 353-362, 643-647, 676-691`
- Rewrite: `tests/test_session_setup_layout.py`
- Modify: `docs/superpowers/specs/2026-08-23-session-setup-layout-design.md`
  (add a superseded note at the head, do not delete the file)

**Interfaces:**
- Consumes: `Card.add_widget`, `FormSection(label_width=208)`, `RadioCard`,
  `FileSlot`, `CommandBar.set_recent_sessions`.
- Produces: `mw.session_name_edit: QLineEdit`, `mw.orders_slot`,
  `mw.stock_slot`, `mw.strategy_group: QButtonGroup`,
  `mw.strategy_multi_item: RadioCard`, `mw.strategy_fifo: RadioCard`, and a
  `MainWindow.analysis_mode_combo` shim property returning
  `"Multi-item first"` or `"FIFO (oldest first)"` so `actions_handler`'s
  existing read site is untouched.

- [ ] **Step 1: Write the failing test**

Replace the whole body of `tests/test_session_setup_layout.py` with:

```python
"""Session Setup is one card of three rows.

Bundle 5 deleted the splitter, the scroll area and the recent-sessions
strip. The constraints the previous version of this file protected — a
706px column floor, a fixed recent-list height — belonged to a layout that
no longer exists.
"""

from PySide6.QtWidgets import QScrollArea, QSplitter

from gui.components import Card, FileSlot, RadioCard


def test_the_setup_page_holds_exactly_one_card(main_window):
    page = main_window.setup_stack.widget(1)
    assert len(page.findChildren(Card)) == 1


def test_the_card_fits_above_480px(main_window):
    page = main_window.setup_stack.widget(1)
    card = page.findChildren(Card)[0]
    assert card.sizeHint().height() <= 480


def test_nothing_on_the_setup_page_scrolls(main_window):
    page = main_window.setup_stack.widget(1)
    assert page.findChildren(QScrollArea) == []
    assert page.findChildren(QSplitter) == []


def test_the_page_has_two_file_slots(main_window):
    page = main_window.setup_stack.widget(1)
    assert len(page.findChildren(FileSlot)) == 2


def test_the_strategy_is_two_radio_cards_not_a_combo(main_window):
    page = main_window.setup_stack.widget(1)
    cards = page.findChildren(RadioCard)
    assert len(cards) == 2
    assert {c.title_text for c in cards} == {"Multi-item first", "Oldest first"}
    assert all(c.description_text for c in cards)


def test_the_recent_sessions_strip_is_gone(main_window):
    assert not hasattr(main_window, "recent_sessions_list")


def test_the_shell_controls_are_not_duplicated_on_the_page(main_window):
    for gone in (
        "new_session_btn",
        "settings_button",
        "generate_reports_button",
        "open_session_folder_button",
        "add_product_button",
    ):
        assert not hasattr(main_window, gone), f"{gone} still on the page"


def test_the_label_gutter_is_208(main_window):
    from gui.components import FormSection

    page = main_window.setup_stack.widget(1)
    section = page.findChildren(FormSection)[0]
    label = section.form.itemAt(0, section.form.LabelRole).widget()
    assert label.width() == 208


def test_the_session_name_field_takes_focus_first(main_window):
    page = main_window.setup_stack.widget(1)
    assert main_window.session_name_edit in page.findChildren(type(main_window.session_name_edit))
    assert main_window.session_name_edit.focusPolicy() != 0
```

- [ ] **Step 2: Run and confirm failure**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_setup_layout.py -v
```

Expected: FAIL on every case.

- [ ] **Step 3: Implement the new page**

Replace `_create_tab1_session_setup` and `_create_session_setup_panel` with
one builder:

```python
    def _create_tab1_session_setup(self):
        """Session Setup: one card, three rows, above a state-panel page 0.

        Four group boxes, a splitter and a recent-sessions strip became one
        card in Bundle 5. Run Analysis is not a row -- Bundle 4 made it this
        screen's command-bar primary (_SCREEN_ACTIONS[0]), and drawing it
        again here would be the fourth duplicate this screen just deleted.
        """
        from PySide6.QtWidgets import QButtonGroup, QStackedWidget

        from gui.components import Card, FileSlot, FormSection, RadioCard

        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)

        card = Card(margins=(16, 16, 16, 16), spacing=8)
        card.setMaximumWidth(_SETUP_CARD_MAX_WIDTH)

        section = FormSection("", label_width=_SETUP_LABEL_GUTTER)

        self.mw.session_name_edit = QLineEdit()
        self.mw.session_name_edit.setPlaceholderText("Tuesday restock")
        section.add_row("Session name", self.mw.session_name_edit)

        self.mw.orders_slot = FileSlot(
            "Orders file", "Drop the Shopify orders export here"
        )
        section.add_row("Orders file", self.mw.orders_slot)

        self.mw.stock_slot = FileSlot("Stock file", "Drop the stock export here")
        section.add_row("Stock file", self.mw.stock_slot)

        section.add_row("Allocation", self._create_strategy_picker(QButtonGroup))

        card.add_widget(section)
        outer.addWidget(card)
        outer.addStretch()

        stack = QStackedWidget()
        stack.addWidget(QWidget())    # page 0, replaced by _refresh_setup_panel
        stack.addWidget(tab)          # page 1, the card
        self.mw.setup_stack = stack
        self._refresh_setup_panel()
        return stack

    def _create_strategy_picker(self, QButtonGroup):
        """The two allocation strategies, each stating its consequence."""
        from gui.components import RadioCard

        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)

        self.mw.strategy_multi_item = RadioCard(
            "Multi-item first",
            "Fills orders that can go out whole before it fills partial "
            "ones. More complete orders leave the warehouse; a few old "
            "orders wait for stock.",
        )
        self.mw.strategy_fifo = RadioCard(
            "Oldest first",
            "Fills strictly by order date, whatever the order contains. No "
            "order waits behind a newer one; more orders leave part-filled.",
        )
        self.mw.strategy_multi_item.setChecked(True)

        group = QButtonGroup(holder)
        group.addButton(self.mw.strategy_multi_item)
        group.addButton(self.mw.strategy_fifo)
        self.mw.strategy_group = group

        layout.addWidget(self.mw.strategy_multi_item)
        layout.addWidget(self.mw.strategy_fifo)
        return holder
```

Add near the other layout constants at the top of `ui_manager.py`, and
**delete** `_SETUP_COLUMN_SLACK`, `_RECENT_PANEL_MAX_WIDTH` and
`_RECENT_SESSIONS_ROWS`:

```python
# The setup card. 208 is the label gutter W1 specifies; the 840 cap stops a
# three-row form stretching to the page's full 1310, which turns a gutter
# into a horizon.
_SETUP_LABEL_GUTTER = 208
_SETUP_CARD_MAX_WIDTH = 840
```

Delete these methods entirely: `_create_session_setup_panel`,
`_create_session_browser_panel`, `_on_recent_session_double_clicked`,
`refresh_recent_sessions`, `_recent_list_height` (module-level function),
`_create_session_management_section`, `_create_files_group`,
`_create_orders_file_section`, `_create_stock_file_section`,
`on_orders_mode_changed`, `on_stock_mode_changed`, `_create_reports_group`,
`_open_session_folder`, `_create_main_actions_group`,
`_create_client_selector_group`.

`_open_session_folder`'s body moves to wherever the command bar's
`openFolderRequested` is already handled — check `_create_command_bar`
first; if the bar's signal is already connected to a handler, delete the
`ui_manager` copy outright rather than moving it.

Delete the `self.mw.new_session_btn.hide()` line and its comment in the
constructor, and remove `run_analysis_button`'s entry handling only if the
button itself is gone — it is **not**: `_SCREEN_ACTIONS[0]` still binds it
into the command bar. Keep `mw.run_analysis_button` as a hidden `QPushButton`
created in `_create_tab1_session_setup`:

```python
        # The screen's primary, bound into the command bar by _SCREEN_ACTIONS.
        # Never rendered here -- Bundle 4 hides it.
        self.mw.run_analysis_button = QPushButton("Run analysis", tab)
        self.mw.run_analysis_button.setEnabled(False)
        self.mw.run_analysis_button.hide()
```

Add the shim property to `MainWindow` in `gui/main_window_pyside.py`:

```python
    @property
    def analysis_mode_combo(self):
        """Kept so actions_handler's existing read site is untouched.

        Bundle 5 replaced the combo with two RadioCards; this returns the
        same two strings currentText() used to.
        """
        class _Shim:
            def __init__(self, mw):
                self._mw = mw

            def currentText(self) -> str:
                return (
                    "Multi-item first"
                    if self._mw.strategy_multi_item.isChecked()
                    else "FIFO (oldest first)"
                )

        return _Shim(self)
```

Confirm the exact strings against `actions_handler`'s read site before
writing this — search for `analysis_mode_combo` and match what it compares
against, character for character.

- [ ] **Step 4: Delete the dead wiring in `main_window_pyside.py`**

Remove every reference to the five deleted widgets (`new_session_btn`,
`settings_button`, `generate_reports_button`, `open_session_folder_button`,
`add_product_button`) at the line ranges in **Files** above, including the
`hasattr` guards around them. Do not touch `generate_reports_button_tab2`,
`add_product_button_tab2` or `settings_button_tab2` — those are the Results
screen's, and they stay.

Then wire the picker and the slots:

```python
        self.command_bar.sessionChosen.connect(self.on_session_selected)
        self.command_bar.browseAllRequested.connect(
            lambda: self.main_tabs.setCurrentIndex(2)
        )
        for slot, kind in (
            (self.orders_slot, "orders"),
            (self.stock_slot, "stock"),
        ):
            slot.chooseFileRequested.connect(
                lambda _=False, k=kind: self.file_handler.select_file(k)
            )
            slot.pathDropped.connect(
                lambda p, k=kind: self.file_handler.accept_dropped_path(k, p)
            )
            slot.mapColumnsRequested.connect(
                lambda _=False: self.actions_handler.open_settings_window("mappings")
            )
            slot.changed.connect(self.file_handler.check_files_ready)
```

Check each of those handler names against the real methods in
`gui/file_handler.py` and `gui/actions_handler.py` and use the real ones.
`accept_dropped_path` does not exist yet — add it to `FileHandler` as the
drop entry point that sets `mw.orders_file_path` / `mw.stock_file_path` and
then calls `validate_file`, reusing whatever the file-dialog path already
does after a selection.

Replace the `refresh_recent_sessions(client_id)` call site with:

```python
        self.command_bar.set_recent_sessions(
            [
                (info.get("session_name", "?"), info.get("session_path"))
                for info in self.session_manager.list_client_sessions(client_id)[:5]
            ]
        )
```

- [ ] **Step 5: Run the whole suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -v
```

Expected: PASS. Every remaining failure is a test asserting on a widget
this task deleted — update the assertion to the new home, never re-add the
widget. `tests/test_screen_primary_actions.py:75` asserts
`new_session_btn.isHidden()`; that button no longer exists, so the
assertion becomes `not hasattr(main_window, "new_session_btn")`.

- [ ] **Step 6: Note the superseded spec**

At the top of
`docs/superpowers/specs/2026-08-23-session-setup-layout-design.md`, under
the title, add:

```markdown
> **Superseded by Bundle 5** (2026-09-04,
> `2026-09-04-phase9-bundle5-session-setup-design.md`). The splitter, the
> scroll area and the 706px column floor this document solves belong to a
> layout that no longer exists. Kept for the reasoning, not the shape.
```

- [ ] **Step 7: Commit**

```bash
git add gui/ui_manager.py gui/main_window_pyside.py gui/file_handler.py tests/ docs/
git commit -m "feat(setup): four group boxes become one card of three rows"
```

---

### Task 7: `AddProductDialog` reads the client's low-stock threshold

The bundle's quick fix. Spec §9. Independent of Tasks 1–6 — do it last so a
green suite is a green suite.

**Files:**
- Modify: `gui/add_product_dialog.py:60` (constructor) and `:226`
- Modify: `gui/actions_handler.py:1279-1284` (the one caller)
- Test: `tests/test_add_product_dialog.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AddProductDialog(parent, analysis_df, stock_df, live_stock,
  low_stock_threshold: int = 5)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_add_product_dialog.py`, following the file's existing
fixtures:

```python
def test_the_low_stock_warning_follows_the_client_threshold(
    qapp, analysis_df, stock_df
):
    """The bug: the dialog hard-coded 5, so a client who set 12 saw no
    warning at 11 units."""
    live_stock = {"SKU-1": 11}
    dlg = AddProductDialog(
        None, analysis_df, stock_df, live_stock, low_stock_threshold=12
    )
    dlg.sku_input.setText("SKU-1")
    assert dlg.warning_box.isVisible()
    assert "low stock" in dlg.warning_box.text().lower()


def test_stock_at_the_threshold_is_not_low(qapp, analysis_df, stock_df):
    dlg = AddProductDialog(
        None, analysis_df, stock_df, {"SKU-1": 12}, low_stock_threshold=12
    )
    dlg.sku_input.setText("SKU-1")
    assert not dlg.warning_box.isVisible()


def test_zero_stock_still_warns_when_the_threshold_is_zero(
    qapp, analysis_df, stock_df
):
    """Zero stock and low stock are different sentences."""
    dlg = AddProductDialog(
        None, analysis_df, stock_df, {"SKU-1": 0}, low_stock_threshold=0
    )
    dlg.sku_input.setText("SKU-1")
    assert dlg.warning_box.isVisible()
    assert "0 stock" in dlg.warning_box.text()
```

Check the SKU field's real attribute name in `_build_form` before writing
`sku_input`, and use whatever it actually is.

- [ ] **Step 2: Run and confirm failure**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_add_product_dialog.py -v
```

Expected: FAIL — `__init__` takes no `low_stock_threshold`.

- [ ] **Step 3: Implement**

`gui/add_product_dialog.py`:

```python
    def __init__(
        self, parent, analysis_df, stock_df, live_stock, low_stock_threshold=5
    ):
        super().__init__(parent)

        self.analysis_df = analysis_df
        self.stock_df = stock_df
        self.live_stock = live_stock  # Current stock tracking dict
        # The client's own setting, edited on Settings > General. The 5 is
        # only the fallback for a config written before the setting existed
        # -- it used to be hardcoded here, so every client who changed it
        # saw the wrong warning.
        self.low_stock_threshold = low_stock_threshold
        self.result = None
```

Line 226 becomes:

```python
        elif current_stock < self.low_stock_threshold:
```

`gui/actions_handler.py`, at the `AddProductDialog(...)` call:

```python
        client_config = self.mw.profile_manager.load_shopify_config(
            self.mw.current_client_id
        )
        dialog = AddProductDialog(
            parent=self.mw,
            analysis_df=self.mw.analysis_results_df,
            stock_df=stock_df,
            live_stock=live_stock,
            low_stock_threshold=(
                (client_config or {}).get("settings", {}).get(
                    "low_stock_threshold", 5
                )
            ),
        )
```

If `self.mw.current_client_config` is already loaded and fresh at this
point in the method, read it from there instead of a second disk load —
check the surrounding lines before adding the `load_shopify_config` call.

- [ ] **Step 4: Check every caller**

```bash
rtk grep -rn "AddProductDialog(" gui/ tests/
```

Expected: one production caller plus the test file. The default keeps both
test call sites compiling. If a second production caller exists, it gets
the threshold too — a fix that leaves a sibling caller broken is not a fix.

- [ ] **Step 5: Run and confirm pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_add_product_dialog.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/add_product_dialog.py gui/actions_handler.py tests/test_add_product_dialog.py
git commit -m "fix(add-product): the low-stock warning follows the client setting"
```

---

### Task 8: the gate

- [ ] **Step 1: Full suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Expected: all green. The baseline before this bundle was **1224 passed**;
this bundle deletes some setup-layout cases and adds more than it deletes,
so expect a higher number, never a lower one with failures hidden by
deletions. If a test was deleted, say which and why in the PR body.

- [ ] **Step 2: Lint**

```bash
.venv/bin/ruff check . --exclude shared
```

Expected: clean. Watch for imports left behind by the nine deleted builders
— `QSplitter`, `QScrollArea`, `QGroupBox`, `QListWidget`, `QListWidgetItem`,
`QFontMetrics`, `WheelIgnoreComboBox` may all now be unused in
`ui_manager.py`.

- [ ] **Step 3: Smoke the app**

```bash
.venv/bin/python run_dev.py
```

Check by eye: the card renders at 1366×768 without scrolling, dropping a
CSV on a slot loads it, a stock file with no quantity column shows the
inline error with both buttons, and the command bar's session button opens
its menu.

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "chore: Bundle 5 gate"
git push -u origin worktree-phase9-bundle5-session-setup
```

Do **not** open the PR. Stage C reviews first and opens it.

---

## Self-review notes

Spec coverage: §3 → Tasks 1, 6. §4 → Tasks 3, 5. §5 → Tasks 2, 6. §6 →
Task 4. §7 → Task 6. §8 copy → Tasks 2, 3, 6. §9 → Task 7. §12 test seams →
Tasks 1–7, one per seam.

Two places where the plan tells the implementer to check the codebase rather
than trusting the plan, because the plan's author could not see them without
running the app: the exact `analysis_mode_combo` comparison strings in
`actions_handler` (Task 6 Step 3), and the SKU field's attribute name in
`AddProductDialog._build_form` (Task 7 Step 1). Both are named, both are one
`grep` away, and getting either wrong fails loudly rather than silently.

`core.read_csv_headers` / `core.count_csv_rows` (Task 5) may already exist
under other names — check `shopify_tool/core.py` before adding them.
