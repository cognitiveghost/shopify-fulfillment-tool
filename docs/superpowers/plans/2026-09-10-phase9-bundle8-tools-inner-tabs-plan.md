# Phase 9 Bundle 8 — Tools Loses Its Inner Tabs: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task, in this session. Do not fan out to subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Tools page's inner `QTabWidget` with two side-by-side cards that stack below 1180px. Fold each card's print options behind a row that states their current values, and let one primary button move to whichever card can run.

**Architecture:** Build bottom-up.
1. Two small layout helpers (`ElidedLabel`, `row_widget`).
2. The pure `print_summary` function.
3. The `PrintOptions` component, which replaces the 80 lines duplicated in both widgets.
4. Each widget rebuilt as card content, using the new pieces.
5. `ToolsWidget` becomes the page: layout first, then primary movement.

Every task leaves the app runnable. Tasks 4 and 5 still render inside the old tabs until Task 6 swaps the page.

**Tech Stack:** Python 3.12, PySide6 6.11.2 (`QFormLayout.setRowVisible`, `QBoxLayout.setDirection`, `QToolButton.setArrowType`), pytest, `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md`. Read it first. §9 lists the decisions this plan implements on purpose; do not "fix" them back to the brief.

## Global Constraints

- **Worktree / branch:** `.claude/worktrees/worktree-phase9-bundle8-tools-inner-tabs` on `worktree-phase9-bundle8-tools-inner-tabs`. PR-only. Never commit to `main`.
- **Never call bare `python`.** Use `.venv/bin/python`; `python` is not on PATH here. Use `/usr/bin/git` for standalone `log`/`status`/`push`.
- **Run tests as:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
- **Lint as:** `.venv/bin/python -m ruff check . --exclude shared`. After each task, remove any import the task left unused (ruff `F401`).
- **Never hand-edit anything under `shared/`.** This bundle adds no token and no icon, and never runs `scripts/sync_shared.py`.
- **No hardcoded colours.** Every colour comes from theme tokens (`get_theme_manager().get_current_theme()` or the `tokens` argument `on_theme_changed` passes).
- **Theme closures:** import `on_theme_changed` and `set_button_role` from `shared.theme`, and `get_theme_manager` from `gui.theme_manager`, as `gui/log_viewer.py` does.
- **Settings scopes are persisted keys and must not change:** `"reference_labels"` and `"barcode_generator"`.
- **`ToolsWidget._init_ui` must keep that name.** `tests/test_reports_sku_labels_removed.py` reads its source.
- **These tests must pass unmodified:** `tests/test_reference_labels_widget.py`, `tests/test_barcode_generator_widget.py` and `tests/test_reports_sku_labels_removed.py`. Every attribute their `_FakeWidget`s touch keeps its name.
- **Message-box copy is untouched.** It belongs to Bundle 9.
- **The version string is not bumped.** It stays `1.9.9.1`.
- **Write-hook quirk on this VM:** the write hook strips an import that was just added before its usage exists. Add the usage first, then the import, or write both in one edit.
- **Commit subjects** follow the Bundle 7 style: `9.22: <what changed, in plain words>`.

## File map

| File | Responsibility |
|---|---|
| Create `gui/components/elided_label.py` | `ElidedLabel`: a one-line label with zero minimum width that elides in the middle |
| Modify `gui/components/form_section.py` | Add `row_widget(*widgets, stretch=None)` |
| Create `gui/components/print_options.py` | `print_summary(settings)` and `PrintOptions` |
| Modify `gui/components/__init__.py` | Export `ElidedLabel`, `PrintOptions`, `row_widget` |
| Modify `tests/conftest.py` | `print_settings_store` fixture |
| Modify `gui/reference_labels_widget.py` | Card content; delete the group boxes and inline print block |
| Modify `gui/barcode_generator_widget.py` | Card content; delete the group boxes, inline print block and green stylesheet |
| Modify `gui/tools_widget.py` | The page (scroll area, card row, breakpoint), `primary_holder`, primary sync |
| Modify `gui/ui_manager.py` | The `_create_tab5_tools` docstring only |
| Modify `CONTEXT.md` | Printing terms |
| Create `tests/test_elided_label.py`, `tests/test_print_summary.py`, `tests/test_print_options.py`, `tests/test_tools_cards.py`, `tests/test_tools_page.py`, `tests/test_tools_theme.py` | Tests |

---

### Task 1: `ElidedLabel` and `row_widget` — form fields that never widen a card

**Files:**
- Create: `gui/components/elided_label.py`
- Modify: `gui/components/form_section.py` (append a function; add `QHBoxLayout` to the existing import)
- Modify: `gui/components/__init__.py`
- Test: `tests/test_elided_label.py`

**Interfaces:**
- Produces: `ElidedLabel(text: str = "", parent=None)`, with `.full_text() -> str`. `setText()` stores the full text and sets it as the tooltip. `minimumSizeHint().width() == 0`.
- Produces: `row_widget(*widgets: QWidget, stretch: QWidget | None = None) -> QWidget`.
- Both are importable from `gui.components`.

- [ ] **Step 1: Write the failing tests**

`tests/test_elided_label.py`:

```python
"""ElidedLabel and row_widget: the two pieces that keep a Tools card from
being widened by its own content (spec §2, "Paths elide, they do not wrap")."""

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QPushButton

from gui.components import ElidedLabel, row_widget

UNC_PATH = "\\\\192.168.88.101\\_Fulfilment_\\Sessions\\" + "Client\\" * 30 + "labels.pdf"


def test_minimum_width_is_zero_even_for_a_path_with_no_spaces(qapp):
    label = ElidedLabel(UNC_PATH)
    assert label.minimumSizeHint().width() == 0


def test_a_long_path_elides_in_the_middle_and_keeps_the_full_text(qapp):
    label = ElidedLabel(UNC_PATH)
    label.resize(240, 24)
    label.show()
    QApplication.processEvents()

    assert label.text() != UNC_PATH
    assert "…" in label.text()
    assert label.text().startswith("\\\\")
    assert label.text().endswith("pdf")
    assert label.full_text() == UNC_PATH
    assert label.toolTip() == UNC_PATH


def test_short_text_is_shown_whole(qapp):
    label = ElidedLabel("No file chosen")
    label.resize(400, 24)
    label.show()
    QApplication.processEvents()
    assert label.text() == "No file chosen"


def test_set_text_replaces_the_full_text(qapp):
    label = ElidedLabel("first")
    label.setText("second")
    assert label.full_text() == "second"
    assert label.toolTip() == "second"


def test_row_widget_gives_the_named_widget_the_stretch(qapp):
    combo, button = QComboBox(), QPushButton("Refresh")
    row = row_widget(combo, button, stretch=combo)
    layout = row.layout()
    assert layout.count() == 2
    assert layout.stretch(0) == 1
    assert layout.stretch(1) == 0
    assert layout.contentsMargins().left() == 0


def test_row_widget_packs_left_when_nothing_stretches(qapp):
    row = row_widget(QCheckBox("a"), QCheckBox("b"))
    layout = row.layout()
    assert layout.count() == 3          # two widgets and a trailing stretch
    assert layout.itemAt(2).spacerItem() is not None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_elided_label.py -v`
Expected: FAIL with `ImportError: cannot import name 'ElidedLabel' from 'gui.components'`

- [ ] **Step 3: Write `gui/components/elided_label.py`**

```python
"""A one-line label that elides instead of growing.

A word-wrapped QLabel breaks only at spaces, so a UNC session path's minimum
width is the whole path -- wide enough to push a Tools card past the
viewport. This label asks for no width at all and elides the middle of its
text to whatever width it is given, keeping both the share and the file name
visible. The full string is always the tooltip.
"""

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event) -> None:
        # A stylesheet that makes the text bold changes its width.
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width()
        shown = (
            self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, width)
            if width > 0
            else self._full
        )
        QLabel.setText(self, shown)
```

- [ ] **Step 4: Append `row_widget` to `gui/components/form_section.py`**

Change the import line to:

```python
from PySide6.QtWidgets import QFormLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
```

Append this at the end of the file, at module level, after the class:

```python
def row_widget(*widgets: QWidget, stretch: QWidget | None = None) -> QWidget:
    """Several widgets as one form field, laid out left to right.

    `stretch` takes the spare width. With none named, a trailing stretch takes
    it instead, so the row packs left rather than spreading its widgets apart.
    """
    theme = get_theme_manager().get_current_theme()
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.spacing_sm)
    for widget in widgets:
        layout.addWidget(widget, 1 if widget is stretch else 0)
    if stretch is None:
        layout.addStretch()
    return row
```

- [ ] **Step 5: Export both from `gui/components/__init__.py`**

Add `from gui.components.elided_label import ElidedLabel` after the `card` import. Change the `form_section` import to `from gui.components.form_section import FormSection, row_widget`. Add `"ElidedLabel"` and `"row_widget"` to `__all__`, keeping it sorted as the existing list is (capitalised names first, then `"overflow_button"`, `"row_widget"`).

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_elided_label.py -v`
Expected: 6 passed.

If `test_a_long_path_elides_in_the_middle…` fails only on `endswith("pdf")`, print `label.text()`. Qt's `ElideMiddle` keeps both ends, so a failure here means `_elide` ran before the resize. Fix that; do not change the assertion.

- [ ] **Step 7: Commit**

```bash
git add gui/components/elided_label.py gui/components/form_section.py gui/components/__init__.py tests/test_elided_label.py
git commit -m "9.22: paths elide instead of widening their card"
```

---

### Task 2: `print_summary` — the folded row's sentence

**Files:**
- Create: `gui/components/print_options.py` (the function only, for now)
- Test: `tests/test_print_summary.py`

**Interfaces:**
- Produces: `print_summary(settings: dict) -> str`. `settings` has the six keys `gui.pdf_printing.load_print_settings` returns: `print_mode`, `raw_zpl_target`, `raw_zpl_rotate`, `raw_zpl_label_width_mm`, `raw_zpl_label_height_mm` and `driver_printer_name`.

- [ ] **Step 1: Write the failing test**

`tests/test_print_summary.py`:

```python
"""The folded print-options row states its own values (spec §4 wording table)."""

import pytest

from gui.components.print_options import print_summary


def _settings(**overrides):
    settings = {
        "print_mode": "driver",
        "raw_zpl_target": "",
        "raw_zpl_rotate": False,
        "raw_zpl_label_width_mm": 0.0,
        "raw_zpl_label_height_mm": 0.0,
        "driver_printer_name": "",
    }
    settings.update(overrides)
    return settings


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "Prints through the print dialog to the Windows default printer"),
        (
            {"driver_printer_name": "Zebra GK420"},
            "Prints through the print dialog to Zebra GK420",
        ),
        (
            {"print_mode": "raw_zpl"},
            "Raw ZPL needs a printer target. Open to set one.",
        ),
        (
            {"print_mode": "raw_zpl", "raw_zpl_target": "   "},
            "Raw ZPL needs a printer target. Open to set one.",
        ),
        (
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW"},
            "Prints raw ZPL to ZPL-RAW at the PDF's page size",
        ),
        (
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 152.4,
                "raw_zpl_label_height_mm": 101.6,
                "raw_zpl_rotate": True,
            },
            "Prints raw ZPL to ZPL-RAW at 152.4 × 101.6 mm, rotated 90°",
        ),
        (
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 68.0,
                "raw_zpl_label_height_mm": 38.0,
            },
            "Prints raw ZPL to ZPL-RAW at 68 × 38 mm",
        ),
        (
            # One dimension alone is not a size: fitting needs both.
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 68.0,
            },
            "Prints raw ZPL to ZPL-RAW at the PDF's page size",
        ),
        (
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW", "raw_zpl_rotate": True},
            "Prints raw ZPL to ZPL-RAW at the PDF's page size, rotated 90°",
        ),
    ],
)
def test_print_summary(overrides, expected):
    assert print_summary(_settings(**overrides)) == expected


def test_driver_mode_ignores_raw_zpl_values():
    settings = _settings(raw_zpl_target="ZPL-RAW", raw_zpl_rotate=True)
    assert print_summary(settings) == (
        "Prints through the print dialog to the Windows default printer"
    )
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_print_summary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.components.print_options'`

- [ ] **Step 3: Write `gui/components/print_options.py`**

```python
"""One tool's print settings, folded behind a row that states them.

Reference labels and Barcode labels each carried the same 80-line print block,
with every control always visible and four of five greyed out by mode. This is
that block once: the controls a mode does not use are hidden rather than
disabled, and the closed fold shows the current values, so nobody opens it to
check which printer is selected.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md §4.
"""


def print_summary(settings: dict) -> str:
    """The folded row's text: the current settings as one sentence."""
    if settings.get("print_mode") == "raw_zpl":
        target = (settings.get("raw_zpl_target") or "").strip()
        if not target:
            return "Raw ZPL needs a printer target. Open to set one."
        width = settings.get("raw_zpl_label_width_mm") or 0.0
        height = settings.get("raw_zpl_label_height_mm") or 0.0
        size = f"{width:g} × {height:g} mm" if width and height else "the PDF's page size"
        text = f"Prints raw ZPL to {target} at {size}"
        if settings.get("raw_zpl_rotate"):
            text += ", rotated 90°"
        return text
    printer = settings.get("driver_printer_name") or "the Windows default printer"
    return f"Prints through the print dialog to {printer}"
```

- [ ] **Step 4: Run it and confirm it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_print_summary.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add gui/components/print_options.py tests/test_print_summary.py
git commit -m "9.22: the print options state themselves in one sentence"
```

---

### Task 3: `PrintOptions` — the fold, the rows it hides, and its saves

**Files:**
- Modify: `gui/components/print_options.py` (add the class and its imports)
- Modify: `gui/components/__init__.py` (export `PrintOptions`)
- Modify: `tests/conftest.py` (add the `print_settings_store` fixture)
- Test: `tests/test_print_options.py`

**Interfaces:**
- Consumes: `print_summary` (Task 2); `FormSection`, `row_widget` (Task 1); `load_print_settings(scope) -> dict`, `save_print_settings(scope, settings) -> None` from `gui.pdf_printing`.
- Produces: `PrintOptions(scope: str, *, label_size_tooltip: str, parent=None)`, which provides:
  - `changed` — a `Signal()`
  - `current_settings() -> dict`
  - `is_open() -> bool`
  - `set_open(open_: bool) -> None`
  - public child handles: `fold_button`, `body` (a `FormSection`), `print_mode_combo`, `driver_printer_combo`, `raw_zpl_target_edit`, `raw_zpl_label_width_spin`, `raw_zpl_label_height_spin`, `raw_zpl_rotate_check`
- Produces: the `print_settings_store` fixture, a dict keyed by scope. Tasks 4–8 use it.
- **Load-bearing:** `PrintOptions` calls `load_print_settings` and `save_print_settings` through the names imported into `gui.components.print_options`, so the fixture can monkeypatch them there.

- [ ] **Step 1: Add the fixture to `tests/conftest.py`**

Add it after the `qapp` fixture:

```python
@pytest.fixture
def print_settings_store(monkeypatch):
    """PrintOptions reads and writes QSettings("ShopifyFulfillmentTool",
    "Printing") -- the developer's real per-PC printer choice. Tests that build
    a real PrintOptions, or a widget holding one, get an in-memory store keyed
    by scope instead."""
    from gui.components import print_options

    defaults = {
        "print_mode": "driver",
        "raw_zpl_target": "",
        "raw_zpl_rotate": False,
        "raw_zpl_label_width_mm": 0.0,
        "raw_zpl_label_height_mm": 0.0,
        "driver_printer_name": "",
    }
    store = {}
    monkeypatch.setattr(
        print_options, "load_print_settings",
        lambda scope: dict(store.get(scope, defaults)),
    )
    monkeypatch.setattr(
        print_options, "save_print_settings",
        lambda scope, settings: store.__setitem__(scope, dict(settings)),
    )
    return store
```

- [ ] **Step 2: Write the failing tests**

`tests/test_print_options.py`:

```python
"""PrintOptions: closed by default, a mode hides the rows it does not use, and
every edit saves under the component's own scope (spec §4)."""

import pytest
from PySide6.QtCore import Qt

from gui.components import PrintOptions


@pytest.fixture
def options(qapp, print_settings_store):
    return PrintOptions("reference_labels", label_size_tooltip="Label size tip")


def _choose_mode(options, mode):
    options.print_mode_combo.setCurrentIndex(options.print_mode_combo.findData(mode))


def _zpl_fields(options):
    return (
        options.raw_zpl_target_edit,
        options.raw_zpl_label_width_spin.parentWidget(),  # the label-size row
        options.raw_zpl_rotate_check,
    )


def test_starts_closed_with_the_body_hidden(options):
    assert not options.is_open()
    assert options.body.isHidden()
    assert options.fold_button.arrowType() == Qt.RightArrow


def test_opening_shows_the_body_and_turns_the_arrow(options):
    options.set_open(True)
    assert options.is_open()
    assert not options.body.isHidden()
    assert options.fold_button.arrowType() == Qt.DownArrow

    options.set_open(False)
    assert options.body.isHidden()


def test_clicking_the_fold_button_opens_it(options):
    options.fold_button.click()
    assert options.is_open()
    assert not options.body.isHidden()


def test_driver_mode_shows_the_printer_row_and_hides_the_raw_zpl_rows(options):
    form = options.body.form
    assert form.isRowVisible(options.print_mode_combo)
    assert form.isRowVisible(options.driver_printer_combo)
    for field in _zpl_fields(options):
        assert not form.isRowVisible(field)


def test_raw_zpl_hides_the_driver_row(options):
    _choose_mode(options, "raw_zpl")
    form = options.body.form
    assert form.isRowVisible(options.print_mode_combo)
    assert not form.isRowVisible(options.driver_printer_combo)
    for field in _zpl_fields(options):
        assert form.isRowVisible(field)


def test_no_control_is_disabled_by_mode(options):
    controls = (options.driver_printer_combo, *_zpl_fields(options))
    for mode in ("raw_zpl", "driver"):
        _choose_mode(options, mode)
        assert all(control.isEnabled() for control in controls)


def test_an_edit_saves_under_the_scope_and_updates_the_summary(options, print_settings_store):
    _choose_mode(options, "raw_zpl")
    assert print_settings_store["reference_labels"]["print_mode"] == "raw_zpl"
    assert options.fold_button.text() == "Raw ZPL needs a printer target. Open to set one."

    options.raw_zpl_target_edit.setText("ZPL-RAW")
    options.raw_zpl_target_edit.editingFinished.emit()
    assert print_settings_store["reference_labels"]["raw_zpl_target"] == "ZPL-RAW"
    assert options.fold_button.text() == "Prints raw ZPL to ZPL-RAW at the PDF's page size"
    assert options.fold_button.toolTip() == options.fold_button.text()


def test_an_edit_emits_changed(options):
    seen = []
    options.changed.connect(lambda: seen.append(True))
    options.raw_zpl_rotate_check.setChecked(True)
    assert seen == [True]


def test_construction_loads_the_saved_settings(qapp, print_settings_store):
    print_settings_store["barcode_generator"] = {
        "print_mode": "raw_zpl",
        "raw_zpl_target": "ZPL-RAW",
        "raw_zpl_rotate": True,
        "raw_zpl_label_width_mm": 68.0,
        "raw_zpl_label_height_mm": 38.0,
        "driver_printer_name": "",
    }
    options = PrintOptions("barcode_generator", label_size_tooltip="tip")
    assert options.print_mode_combo.currentData() == "raw_zpl"
    assert options.fold_button.text() == "Prints raw ZPL to ZPL-RAW at 68 × 38 mm, rotated 90°"
    assert options.current_settings() == print_settings_store["barcode_generator"]


def test_the_label_size_tooltip_reaches_both_spins(options):
    assert options.raw_zpl_label_width_spin.toolTip() == "Label size tip"
    assert options.raw_zpl_label_height_spin.toolTip() == "Label size tip"
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_print_options.py -v`
Expected: FAIL with `ImportError: cannot import name 'PrintOptions' from 'gui.components'`

- [ ] **Step 4: Add the class to `gui/components/print_options.py`**

Insert these imports under the module docstring, above `print_summary`:

```python
from PySide6.QtCore import Qt, Signal
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.components.form_section import FormSection, row_widget
from gui.pdf_printing import load_print_settings, save_print_settings
from shared.theme import on_theme_changed

# Shared with both Tools cards so their fields and these start at one inset.
LABEL_WIDTH = 120
```

Append the class below `print_summary`:

```python
class PrintOptions(QWidget):
    """A fold button stating the settings, over the rows that change them."""

    changed = Signal()

    def __init__(self, scope: str, *, label_size_tooltip: str, parent=None) -> None:
        super().__init__(parent)
        self._scope = scope
        settings = load_print_settings(scope)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.fold_button = QToolButton(self)
        self.fold_button.setCheckable(True)
        self.fold_button.setAutoRaise(True)
        self.fold_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.fold_button.setAccessibleName("Print options")
        # Ignored: a long printer target must clip, never widen the card.
        # The tooltip carries the full text.
        self.fold_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.fold_button.toggled.connect(self.set_open)
        layout.addWidget(self.fold_button)

        self.body = FormSection("", label_width=LABEL_WIDTH)
        layout.addWidget(self.body)

        self.print_mode_combo = QComboBox()
        self.print_mode_combo.addItem("OS driver (print dialog)", "driver")
        self.print_mode_combo.addItem("Raw ZPL (direct)", "raw_zpl")
        index = self.print_mode_combo.findData(settings["print_mode"])
        if index >= 0:
            self.print_mode_combo.setCurrentIndex(index)
        self.body.add_row("Print mode", self.print_mode_combo)

        self.driver_printer_combo = QComboBox()
        self.driver_printer_combo.addItem("(Windows default)", "")
        for info in QPrinterInfo.availablePrinters():
            self.driver_printer_combo.addItem(info.printerName(), info.printerName())
        index = self.driver_printer_combo.findData(settings["driver_printer_name"])
        if index >= 0:
            self.driver_printer_combo.setCurrentIndex(index)
        self.body.add_row("Printer", self.driver_printer_combo)

        self.raw_zpl_target_edit = QLineEdit(settings["raw_zpl_target"])
        self.raw_zpl_target_edit.setPlaceholderText(
            "e.g. ZPL-RAW-Printer (Windows) or /dev/usb/lp0 (Linux)"
        )
        self.body.add_row("Raw ZPL target", self.raw_zpl_target_edit)

        self.raw_zpl_label_width_spin = self._mm_spin(
            settings["raw_zpl_label_width_mm"], label_size_tooltip
        )
        self.raw_zpl_label_height_spin = self._mm_spin(
            settings["raw_zpl_label_height_mm"], label_size_tooltip
        )
        self._label_size_row = row_widget(
            self.raw_zpl_label_width_spin, QLabel("×"), self.raw_zpl_label_height_spin
        )
        self.body.add_row("Label size (mm)", self._label_size_row)

        self.raw_zpl_rotate_check = QCheckBox("Rotate 90°")
        self.raw_zpl_rotate_check.setChecked(settings["raw_zpl_rotate"])
        self.body.add_row("", self.raw_zpl_rotate_check)

        # Connected after the values are loaded, so construction saves nothing.
        self.print_mode_combo.currentIndexChanged.connect(self._update_zpl_controls_visible)
        self.print_mode_combo.currentIndexChanged.connect(self._on_edited)
        self.raw_zpl_target_edit.editingFinished.connect(self._on_edited)
        self.raw_zpl_rotate_check.toggled.connect(self._on_edited)
        self.raw_zpl_label_width_spin.editingFinished.connect(self._on_edited)
        self.raw_zpl_label_height_spin.editingFinished.connect(self._on_edited)
        self.driver_printer_combo.currentIndexChanged.connect(self._on_edited)

        self._update_zpl_controls_visible()
        self._refresh_summary()
        self.set_open(False)
        on_theme_changed(self.fold_button, self._style_fold_button)

    @staticmethod
    def _mm_spin(value: float, tooltip: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 500.0)
        spin.setDecimals(1)
        spin.setSpecialValueText("(use PDF page size)")
        spin.setValue(value)
        spin.setToolTip(tooltip)
        return spin

    def current_settings(self) -> dict:
        """The dict save_print_settings takes, read from the controls."""
        return {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
            "raw_zpl_label_width_mm": self.raw_zpl_label_width_spin.value(),
            "raw_zpl_label_height_mm": self.raw_zpl_label_height_spin.value(),
            "driver_printer_name": self.driver_printer_combo.currentData(),
        }

    def is_open(self) -> bool:
        return self.fold_button.isChecked()

    def set_open(self, open_: bool) -> None:
        """Show or hide the rows. No animation: QSS has no transitions."""
        self.fold_button.setChecked(open_)  # no-op, and no signal, when unchanged
        self.fold_button.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.body.setVisible(open_)

    def _update_zpl_controls_visible(self, *_args) -> None:
        """Hide the rows the chosen mode does not use -- hidden, not greyed out."""
        is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
        form = self.body.form
        form.setRowVisible(self.driver_printer_combo, not is_zpl)
        form.setRowVisible(self.raw_zpl_target_edit, is_zpl)
        form.setRowVisible(self._label_size_row, is_zpl)
        form.setRowVisible(self.raw_zpl_rotate_check, is_zpl)

    def _on_edited(self, *_args) -> None:
        save_print_settings(self._scope, self.current_settings())
        self._refresh_summary()
        self.changed.emit()

    def _refresh_summary(self) -> None:
        text = print_summary(self.current_settings())
        self.fold_button.setText(text)
        self.fold_button.setToolTip(text)

    def _style_fold_button(self, tokens) -> None:
        # build_stylesheet has no QToolButton rule, and shared/ is not edited
        # here. The transparent background is load-bearing: without it the
        # global `QWidget { background-color: surface }` rule paints a surface
        # patch on the card's surface_raised plane.
        self.fold_button.setStyleSheet(
            f"""
            QToolButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: {tokens.radius}px;
                padding: 4px 6px;
                color: {tokens.text_secondary};
            }}
            QToolButton:hover {{ background-color: {tokens.hover}; color: {tokens.text}; }}
            QToolButton:focus {{ border-color: {tokens.focus_ring}; }}
            """
        )
```

- [ ] **Step 5: Export it**

In `gui/components/__init__.py`, add `from gui.components.print_options import PrintOptions` in alphabetical position (after `overflow`), and add `"PrintOptions"` to `__all__`.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_print_options.py tests/test_print_summary.py tests/test_elided_label.py -v`
Expected: all pass.

If you get a circular import, the likely cause is `gui.components` → `print_options` → `gui.pdf_printing` → something importing `gui.components`. Check with `.venv/bin/python -c "import gui.components"`. If it is circular, import `load_print_settings`/`save_print_settings` from `gui.pdf_printing` at module level in `print_options.py` anyway and break the other side of the cycle. The fixture depends on those module-level names existing.

- [ ] **Step 7: Commit**

```bash
git add gui/components/print_options.py gui/components/__init__.py tests/conftest.py tests/test_print_options.py
git commit -m "9.22: print options fold away, and a mode hides what it does not use"
```

---

### Task 4: Reference labels becomes card content

**Files:**
- Modify: `gui/reference_labels_widget.py`. Replace lines 75–265, from `def _init_ui` through the end of `_create_processing_group`. Edit `_update_output_dir` (lines 353–385). Delete `_save_print_settings` (lines 619–627).
- Test: `tests/test_tools_cards.py` (new; Task 5 appends to it)

**Interfaces:**
- Consumes: `FormSection`, `row_widget`, `ElidedLabel`, `PrintOptions`, `LABEL_WIDTH` (`from gui.components.print_options import LABEL_WIDTH`).
- Produces: `ReferenceLabelsWidget.print_options: PrintOptions`. These keep their names: `process_btn`, `print_btn`, `select_pdf_btn`, `select_csv_btn`, `change_dir_btn`, `pdf_label`, `csv_label`, `output_dir_label`, `auto_open_checkbox`, `progress_bar`, `status_label`. Task 7 reads `process_btn.isEnabled()` as this card's readiness.

- [ ] **Step 1: Write the failing tests**

`tests/test_tools_cards.py`:

```python
"""Both Tools widgets as card content: no group boxes, one PrintOptions each
under its own persisted scope (spec §3)."""

from types import SimpleNamespace

from PySide6.QtWidgets import QGroupBox

from gui.components import PrintOptions
from gui.reference_labels_widget import ReferenceLabelsWidget


def _main_window():
    # Both widgets tolerate a window with no session: no session_changed
    # signal, session_path None.
    return SimpleNamespace(session_path=None)


def test_reference_card_has_no_group_boxes(qapp, print_settings_store):
    widget = ReferenceLabelsWidget(_main_window())
    assert widget.findChildren(QGroupBox) == []


def test_reference_card_holds_one_print_options_under_its_scope(qapp, print_settings_store):
    widget = ReferenceLabelsWidget(_main_window())
    assert widget.findChildren(PrintOptions) == [widget.print_options]

    widget.print_options.raw_zpl_rotate_check.setChecked(True)
    assert print_settings_store["reference_labels"]["raw_zpl_rotate"] is True


def test_reference_card_without_a_session_says_what_to_do(qapp, print_settings_store):
    widget = ReferenceLabelsWidget(_main_window())
    assert widget.output_dir_label.full_text() == "Open a session to save labels into it"
    assert widget.pdf_label.full_text() == "No file chosen"
    assert widget.csv_label.full_text() == "No file chosen"
    assert not widget.process_btn.isEnabled()
    assert not widget.print_btn.isEnabled()


def test_reference_card_is_ready_once_both_files_and_a_folder_exist(
    qapp, print_settings_store, tmp_path
):
    widget = ReferenceLabelsWidget(_main_window())
    widget.pdf_path, widget.csv_path, widget.output_dir = "in.pdf", "in.csv", tmp_path
    widget._update_process_button()
    assert widget.process_btn.isEnabled()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_cards.py -v`
Expected: FAIL. There are `QGroupBox` children, there is no `print_options` attribute, and `output_dir_label` has no `full_text`.

- [ ] **Step 3: Replace the UI builders**

In `gui/reference_labels_widget.py`, replace everything from `    def _init_ui(self):` through the `return group` that ends `_create_processing_group`:

```python
    def _init_ui(self):
        """One card's content: inputs, print options, then status and actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._create_inputs_section())

        # Courier PDFs' own page size can't be trusted (the same batch mixes
        # pages from ~98x147mm up to 152x102mm depending on courier) -- raw
        # ZPL has no driver to fit that to the physical label, so it prints
        # shrunk with blank margin instead of filling it. Set both to the
        # loaded label's real size to fit every page to it; 0 (default)
        # keeps the old behavior of using each page's own size as-is.
        self.print_options = PrintOptions(
            "reference_labels",
            label_size_tooltip=(
                "Physical label size as loaded in the printer, e.g. 152.4 x 101.6 "
                "for 6x4in shipping labels. 0 disables fitting and uses each "
                "page's own PDF size."
            ),
        )
        layout.addWidget(self.print_options)

        # Side by side, the taller card sets the row height; this stretch keeps
        # both action rows on one baseline.
        layout.addStretch()
        layout.addLayout(self._create_action_area())

    def _create_inputs_section(self):
        """The two input files, where the output goes, and whether to open it."""
        theme = get_theme_manager().get_current_theme()
        section = FormSection(
            "Reference labels",
            "Stamps each courier label with its order's reference number.",
            label_width=LABEL_WIDTH,
        )

        self.select_pdf_btn = QPushButton("Select PDF…")
        self.select_pdf_btn.setToolTip("Select the PDF file containing courier labels")
        self.pdf_label = ElidedLabel("No file chosen")
        self.pdf_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        section.add_row(
            "Labels PDF", row_widget(self.select_pdf_btn, self.pdf_label, stretch=self.pdf_label)
        )

        self.select_csv_btn = QPushButton("Select CSV…")
        self.select_csv_btn.setToolTip(
            "Select the CSV file with PostOne ID → Reference Number mapping"
        )
        self.csv_label = ElidedLabel("No file chosen")
        self.csv_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        section.add_row(
            "Mapping CSV", row_widget(self.select_csv_btn, self.csv_label, stretch=self.csv_label)
        )

        self.output_dir_label = ElidedLabel()
        self.change_dir_btn = QPushButton("Change…")
        self.change_dir_btn.setToolTip("Change output directory")
        section.add_row(
            "Output folder",
            row_widget(self.output_dir_label, self.change_dir_btn, stretch=self.output_dir_label),
        )

        self.auto_open_checkbox = QCheckBox("Open the PDF when it's ready")
        self.auto_open_checkbox.setChecked(True)
        section.add_row("", self.auto_open_checkbox)

        return section

    def _create_action_area(self):
        """Progress and status, then the actions, right-aligned."""
        area = QVBoxLayout()
        area.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        area.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        area.addWidget(self.status_label)

        self.print_btn = QPushButton("Print…")
        self.print_btn.setEnabled(False)

        # Its role (primary or secondary) is ToolsWidget's to set: the page has
        # one primary, and it moves to whichever card can run.
        self.process_btn = QPushButton("Process Labels")
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip("Process PDF with reference numbers")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.process_btn)
        area.addLayout(buttons)

        return area
```

- [ ] **Step 4: Update the copy in `_update_output_dir`**

In `_update_output_dir`:
- Replace `self.output_dir_label.setText("No session selected")` with `self.output_dir_label.setText("Open a session to save labels into it")`.
- Replace `self.output_dir_label.setText("Error accessing session directory")` with `self.output_dir_label.setText("Can't reach this session's folder. Check the server connection.")`.

Leave every other line of the method as it is. Leave `status_label`'s `"No session selected"` in `_update_process_button` untouched.

- [ ] **Step 5: Delete the old print-settings method and fix imports**

1. Delete the whole `_save_print_settings` method. `_on_print_clicked` stays exactly as it is and still calls `load_print_settings("reference_labels")`.
2. Change the `gui.pdf_printing` import to `from gui.pdf_printing import load_print_settings, print_pdf`.
3. Add these two lines after that import:

```python
from gui.components import ElidedLabel, FormSection, PrintOptions, row_widget
from gui.components.print_options import LABEL_WIDTH
```

4. Remove the imports that are now unused: `QComboBox`, `QDoubleSpinBox`, `QGroupBox`, `QLineEdit`, `QPrinterInfo`, and `Qt` if nothing else uses it. Run ruff to confirm:

Run: `.venv/bin/python -m ruff check gui/reference_labels_widget.py`
Expected: `All checks passed!`

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_cards.py tests/test_reference_labels_widget.py -v`
Expected: all pass. `test_reference_labels_widget.py` is unmodified.

- [ ] **Step 7: Commit**

```bash
git add gui/reference_labels_widget.py tests/test_tools_cards.py
git commit -m "9.22: Reference labels loses its group boxes"
```

---

### Task 5: Barcode labels becomes card content

**Files:**
- Modify: `gui/barcode_generator_widget.py`. Replace lines 73–288, from `def _init_ui` through the end of `_create_generation_section`. Edit `_refresh_packing_lists` and `_on_packing_list_changed`. Delete `_save_print_settings` (lines 649–657).
- Test: `tests/test_tools_cards.py` (append)

**Interfaces:**
- Consumes: the same pieces as Task 4, plus `on_theme_changed` from `shared.theme`.
- Produces: `BarcodeGeneratorWidget.print_options: PrintOptions`. These keep their names: `generate_btn`, `print_btn`, `print_qr_btn`, `packing_list_combo`, `order_count_label`, `output_dir_label`, `add_qr_checkbox`, `auto_open_pdf_checkbox`, `progress_bar`, `status_label`. Task 7 reads `generate_btn.isEnabled()` as this card's readiness.

- [ ] **Step 1: Append the failing tests to `tests/test_tools_cards.py`**

Add `from gui.barcode_generator_widget import BarcodeGeneratorWidget` to the imports, then append:

```python
def test_barcode_card_has_no_group_boxes(qapp, print_settings_store):
    widget = BarcodeGeneratorWidget(_main_window())
    assert widget.findChildren(QGroupBox) == []


def test_barcode_card_holds_one_print_options_under_its_scope(qapp, print_settings_store):
    widget = BarcodeGeneratorWidget(_main_window())
    assert widget.findChildren(PrintOptions) == [widget.print_options]

    widget.print_options.raw_zpl_rotate_check.setChecked(True)
    assert print_settings_store["barcode_generator"]["raw_zpl_rotate"] is True


def test_barcode_generate_button_is_not_drawn_by_hand(qapp, print_settings_store):
    # The role system gives it its colour now (spec §5); a widget stylesheet
    # would override whatever role ToolsWidget sets.
    widget = BarcodeGeneratorWidget(_main_window())
    assert widget.generate_btn.styleSheet() == ""
    assert not widget.generate_btn.isEnabled()


def test_barcode_card_with_no_packing_list_says_what_to_do(qapp, print_settings_store):
    widget = BarcodeGeneratorWidget(_main_window())
    widget._on_packing_list_changed(-1)
    assert widget.output_dir_label.full_text() == "Choose a packing list"


def test_barcode_card_with_no_packing_lists_points_at_analysis_results(
    qapp, print_settings_store, tmp_path
):
    (tmp_path / "packing_lists").mkdir()
    widget = BarcodeGeneratorWidget(SimpleNamespace(session_path=str(tmp_path)))
    widget._refresh_packing_lists()
    assert widget.order_count_label.text() == (
        "No packing lists in this session yet. Generate one from Analysis Results."
    )
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_cards.py -v`
Expected: the five barcode tests FAIL; the Task 4 tests still pass.

- [ ] **Step 3: Replace the UI builders**

In `gui/barcode_generator_widget.py`, replace everything from `    def _init_ui(self):` through the `return group` that ends `_create_generation_section`:

```python
    def _init_ui(self):
        """One card's content: inputs, print options, then status and actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._create_inputs_section())

        # This flow's own template is always authored at 68x38mm, so fitting
        # is mostly a safety net here (unlike Reference Labels, where the
        # source PDF's page size is a courier's and can't be trusted) -- set
        # it to match whatever label stock is actually loaded if it ever
        # changes. 0 (default) keeps using the template's own page size.
        self.print_options = PrintOptions(
            "barcode_generator",
            label_size_tooltip=(
                "Physical label size as loaded in the printer, e.g. 68 x 38 for "
                "this flow's default label stock. 0 disables fitting and uses the "
                "generated PDF's own page size."
            ),
        )
        layout.addWidget(self.print_options)

        # Side by side, the taller card sets the row height; this stretch keeps
        # both action rows on one baseline.
        layout.addStretch()
        layout.addLayout(self._create_action_area())

    def _create_inputs_section(self):
        """Which packing list, how many orders it holds, and where labels go."""
        section = FormSection(
            "Barcode labels",
            "One label for every Fulfillable order in a packing list. "
            "Each list gets its own folder.",
            label_width=LABEL_WIDTH,
        )

        self.packing_list_combo = QComboBox()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh packing lists")
        refresh_btn.clicked.connect(self._refresh_packing_lists)
        section.add_row(
            "Packing list",
            row_widget(self.packing_list_combo, refresh_btn, stretch=self.packing_list_combo),
        )

        self.order_count_label = QLabel("No packing list selected")
        self.order_count_label.setWordWrap(True)
        on_theme_changed(
            self.order_count_label,
            lambda t: self.order_count_label.setStyleSheet(
                f"color: {t.text_secondary}; font-style: italic;"
            ),
        )
        section.add_row("", self.order_count_label)

        self.output_dir_label = ElidedLabel("Choose a packing list")
        on_theme_changed(
            self.output_dir_label,
            lambda t: self.output_dir_label.setStyleSheet(f"color: {t.text_secondary};"),
        )
        section.add_row("Output folder", self.output_dir_label)

        self.add_qr_checkbox = QCheckBox("Add QR labels (order number)")
        self.add_qr_checkbox.setChecked(False)
        self.auto_open_pdf_checkbox = QCheckBox("Open the PDF when it's ready")
        self.auto_open_pdf_checkbox.setChecked(True)
        section.add_row("", row_widget(self.add_qr_checkbox, self.auto_open_pdf_checkbox))

        return section

    def _create_action_area(self):
        """Progress and status, then the actions, right-aligned."""
        area = QVBoxLayout()
        area.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        area.addWidget(self.progress_bar)

        self.status_label = QLabel("Select a packing list to begin")
        self.status_label.setWordWrap(True)
        area.addWidget(self.status_label)

        self.print_qr_btn = QPushButton("Print QR labels…")
        self.print_qr_btn.setEnabled(False)

        self.print_btn = QPushButton("Print…")
        self.print_btn.setEnabled(False)

        # No stylesheet: its role (primary or secondary) is ToolsWidget's to
        # set. The page has one primary, and it moves to whichever card can run.
        self.generate_btn = QPushButton("Generate Barcode Labels")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.print_qr_btn)
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.generate_btn)
        area.addLayout(buttons)

        return area
```

- [ ] **Step 4: Update the copy**

- In `_refresh_packing_lists`, replace `self.order_count_label.setText("No packing lists generated yet")` with `self.order_count_label.setText("No packing lists in this session yet. Generate one from Analysis Results.")`.
- In `_on_packing_list_changed`, in the `if index < 0:` branch, replace `self.output_dir_label.setText("No packing list selected")` with `self.output_dir_label.setText("Choose a packing list")`. Leave `order_count_label`'s text in that branch as it is.

- [ ] **Step 5: Delete the old print-settings method and fix imports**

1. Delete the whole `_save_print_settings` method. `_on_print_clicked` and `_on_print_qr_clicked` stay exactly as they are.
2. Change the `gui.pdf_printing` import to `from gui.pdf_printing import load_print_settings, print_pdf`.
3. Add these three lines after it:

```python
from gui.components import ElidedLabel, FormSection, PrintOptions, row_widget
from gui.components.print_options import LABEL_WIDTH
from shared.theme import on_theme_changed
```

4. Remove the imports that are now unused. Candidates: `QDoubleSpinBox`, `QGroupBox`, `QLineEdit`, `QPrinterInfo`, `font_css`, `Qt`. Check each with ruff before removing it; `get_theme_manager` is still used by the status-label methods.

Run: `.venv/bin/python -m ruff check gui/barcode_generator_widget.py`
Expected: `All checks passed!`

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_cards.py tests/test_barcode_generator_widget.py -v`
Expected: all pass. `test_barcode_generator_widget.py` is unmodified.

- [ ] **Step 7: Commit**

```bash
git add gui/barcode_generator_widget.py tests/test_tools_cards.py
git commit -m "9.22: Barcode labels loses its group boxes and its hand-drawn button"
```

---

### Task 6: `ToolsWidget` becomes the page — two cards, one row, a breakpoint

**Files:**
- Modify: `gui/tools_widget.py` (rewrite the whole file)
- Modify: `gui/ui_manager.py` (the `_create_tab5_tools` docstring only)
- Test: `tests/test_tools_page.py`

**Interfaces:**
- Consumes: `Card(margins=..., spacing=...)` with `.add_widget(widget)`; `ReferenceLabelsWidget(main_window)`; `BarcodeGeneratorWidget(main_window)`.
- Produces: `ToolsWidget(main_window, parent=None)`, with these attributes:
  - `scroll: QScrollArea`
  - `cards_row: QBoxLayout`
  - `reference_labels_widget`
  - `barcode_generator_widget`
  - `_apply_width(width: int) -> None`
- Produces: the module constant `_STACK_BELOW = 1180`.
- Each widget's card is `widget.parentWidget()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_tools_page.py`:

```python
"""The Tools page: two cards side by side from 1180px of page width, stacked
below it, never a horizontal scroll (spec §2)."""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QBoxLayout, QTabWidget

from gui.components import Card
from gui.tools_widget import ToolsWidget


@pytest.fixture
def tools(qapp, print_settings_store):
    widget = ToolsWidget(SimpleNamespace(session_path=None))
    widget.show()
    return widget


def _resize(widget, width):
    widget.resize(width, 700)
    QApplication.processEvents()


def _cards(tools):
    return (
        tools.reference_labels_widget.parentWidget(),
        tools.barcode_generator_widget.parentWidget(),
    )


def test_no_inner_tabs_and_two_cards(tools):
    assert tools.findChildren(QTabWidget) == []
    reference_card, barcode_card = _cards(tools)
    assert isinstance(reference_card, Card)
    assert isinstance(barcode_card, Card)
    assert reference_card is not barcode_card


def test_side_by_side_at_the_1366_page_width_with_no_horizontal_scroll(tools):
    _resize(tools, 1310)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()

    reference_card, barcode_card = _cards(tools)
    assert reference_card.y() == barcode_card.y()
    assert reference_card.x() < barcode_card.x()
    assert reference_card.height() == barcode_card.height()


def test_side_by_side_still_fits_at_the_breakpoint(tools):
    _resize(tools, 1180)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()


def test_stacked_below_1180(tools):
    _resize(tools, 1100)
    assert tools.cards_row.direction() == QBoxLayout.TopToBottom
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()

    reference_card, barcode_card = _cards(tools)
    assert reference_card.x() == barcode_card.x()
    assert reference_card.y() < barcode_card.y()


def test_widening_again_restores_side_by_side(tools):
    _resize(tools, 1100)
    _resize(tools, 1310)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_page.py -v`
Expected: FAIL. A `QTabWidget` is found, and there is no `cards_row` attribute.

- [ ] **Step 3: Rewrite `gui/tools_widget.py`**

```python
"""The Tools destination: Reference labels and Barcode labels as two cards.

Side by side from 1180px of page width -- at 1366 the page is 1310, and two
637px cards with 12px gaps and margins are exactly that -- and stacked below
it, by flipping the one row's direction. Never a QStackedLayout: that would
build each tool twice.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QScrollArea, QVBoxLayout, QWidget

from gui.barcode_generator_widget import BarcodeGeneratorWidget
from gui.components import Card
from gui.reference_labels_widget import ReferenceLabelsWidget

_STACK_BELOW = 1180


class ToolsWidget(QWidget):
    """The Tools page: two tool cards in one row that stacks when narrow."""

    def __init__(self, main_window, parent=None):
        """
        Initialize Tools widget.

        Args:
            main_window: MainWindow instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self._init_ui()

    def _init_ui(self):
        """Two cards in one row, inside a vertical-only scroll area."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        content = QWidget()
        page = QVBoxLayout(content)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(0)

        self.cards_row = QBoxLayout(QBoxLayout.LeftToRight)
        self.cards_row.setSpacing(12)

        self.reference_labels_widget = ReferenceLabelsWidget(self.mw)
        self.barcode_generator_widget = BarcodeGeneratorWidget(self.mw)
        for widget in (self.reference_labels_widget, self.barcode_generator_widget):
            card = Card(margins=(16, 16, 16, 16), spacing=12)
            card.add_widget(widget)
            self.cards_row.addWidget(card, 1)

        page.addLayout(self.cards_row)
        # Extra page height goes here, not into the cards: side by side they
        # already share the taller one's height, and stacked each keeps its own.
        page.addStretch(1)

        self.scroll.setWidget(content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_width(self.width())

    def _apply_width(self, width: int) -> None:
        direction = (
            QBoxLayout.TopToBottom if width < _STACK_BELOW else QBoxLayout.LeftToRight
        )
        if self.cards_row.direction() != direction:
            self.cards_row.setDirection(direction)
```

- [ ] **Step 4: Update the stale docstring in `gui/ui_manager.py`**

Replace the `_create_tab5_tools` docstring (currently "Contains sub-tabs: … Barcode Generator: Placeholder for future implementation") with:

```python
        """Create Tab 5: Tools

        Reference labels and Barcode labels as two cards, side by side, that
        stack when the page is narrow. See gui/tools_widget.py.

        Returns:
            QWidget: the Tools page
        """
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_page.py tests/test_reports_sku_labels_removed.py -v`
Expected: all pass.

If `scroll.widget().width() <= viewport().width()` fails at 1180, a card's minimum width is over 572px. Find the culprit with `print(card.minimumSizeHint().width())` for each card, then walk its children. The spec's rule applies: the fix is inside the card (an `ElidedLabel`, a removed `setMinimumWidth`, a wrapped label). **Never** lower `_STACK_BELOW`, and never turn the horizontal scrollbar back on.

- [ ] **Step 6: Commit**

```bash
git add gui/tools_widget.py gui/ui_manager.py tests/test_tools_page.py
git commit -m "9.22: Tools loses its inner tabs, and the two cards stack below 1180px"
```

---

### Task 7: One primary, and it moves

**Files:**
- Modify: `gui/tools_widget.py`
- Test: `tests/test_tools_page.py` (append)

**Interfaces:**
- Consumes: `set_button_role(button, role)` from `shared.theme`. It sets the `role` property and repolishes; roles are `"primary"`, `"secondary"`, `"ghost"` and `"danger"`. Also consumes `process_btn` (Task 4) and `generate_btn` (Task 5).
- Produces: `primary_holder(reference_ready: bool, barcode_ready: bool, current: str | None) -> str | None`, at module level in `gui/tools_widget.py`. It returns `"reference"`, `"barcode"` or `None`.

- [ ] **Step 1: Append the failing tests to `tests/test_tools_page.py`**

Add `from gui.tools_widget import primary_holder` to the imports (next to the `ToolsWidget` import), then append:

```python
@pytest.mark.parametrize(
    ("reference_ready", "barcode_ready", "current", "expected"),
    [
        (True, False, None, "reference"),
        (False, True, None, "barcode"),
        (True, False, "barcode", "reference"),
        (False, True, "reference", "barcode"),
        (True, True, None, "reference"),
        (True, True, "barcode", "barcode"),
        (True, True, "reference", "reference"),
        (False, False, "reference", None),
        (False, False, None, None),
    ],
)
def test_primary_holder(reference_ready, barcode_ready, current, expected):
    assert primary_holder(reference_ready, barcode_ready, current) == expected


def _role(button):
    return button.property("role")


def test_the_primary_follows_whichever_card_can_run(qapp, print_settings_store):
    tools = ToolsWidget(SimpleNamespace(session_path=None))
    process = tools.reference_labels_widget.process_btn
    generate = tools.barcode_generator_widget.generate_btn
    assert "primary" not in (_role(process), _role(generate))

    process.setEnabled(True)
    assert _role(process) == "primary"

    generate.setEnabled(True)  # both ready: Reference keeps it
    assert _role(process) == "primary"
    assert _role(generate) != "primary"

    process.setEnabled(False)  # Reference running, or no longer ready
    assert _role(generate) == "primary"
    assert _role(process) == "secondary"

    generate.setEnabled(False)
    assert "primary" not in (_role(process), _role(generate))


def test_readiness_is_the_widgets_own_verdict(qapp, print_settings_store, tmp_path):
    tools = ToolsWidget(SimpleNamespace(session_path=None))
    reference = tools.reference_labels_widget
    reference.pdf_path, reference.csv_path, reference.output_dir = "in.pdf", "in.csv", tmp_path
    reference._update_process_button()
    assert _role(reference.process_btn) == "primary"
```

The widget is deliberately **not** shown in these two tests. `ReferenceLabelsWidget.showEvent` re-reads the session and would clear `output_dir`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_page.py -v`
Expected: FAIL with `ImportError: cannot import name 'primary_holder'`

- [ ] **Step 3: Implement**

In `gui/tools_widget.py`:
- Change `from PySide6.QtCore import Qt` to `from PySide6.QtCore import QEvent, Qt`.
- Add `from shared.theme import set_button_role` after the `gui.reference_labels_widget` import.

Add this function above `class ToolsWidget`:

```python
def primary_holder(
    reference_ready: bool, barcode_ready: bool, current: str | None
) -> str | None:
    """Which card's action is the page's one primary, if any.

    Exactly one ready card holds it. With both ready, the current holder keeps
    it, so a button never changes weight under the cursor because the *other*
    card became ready. With neither ready there is none: a disabled primary is
    a primary nobody can press.
    """
    if reference_ready and barcode_ready:
        return current or "reference"
    if reference_ready:
        return "reference"
    if barcode_ready:
        return "barcode"
    return None
```

Replace `ToolsWidget.__init__`'s last line (`self._init_ui()`) with:

```python
        self._init_ui()

        # Readiness is each card's own verdict -- its action button's enabled
        # state, set by logic this page does not touch. Watching EnabledChange
        # covers every path that sets it, including disable-while-running.
        self._primary = None
        self._action_buttons = {
            "reference": self.reference_labels_widget.process_btn,
            "barcode": self.barcode_generator_widget.generate_btn,
        }
        for button in self._action_buttons.values():
            button.installEventFilter(self)
        self._sync_primary()
```

Add these methods to the class, after `_apply_width`:

```python
    def eventFilter(self, obj, event):
        if event.type() == QEvent.EnabledChange:
            self._sync_primary()
        return super().eventFilter(obj, event)

    def _sync_primary(self) -> None:
        holder = primary_holder(
            self._action_buttons["reference"].isEnabled(),
            self._action_buttons["barcode"].isEnabled(),
            self._primary,
        )
        if holder == self._primary:
            return
        for name, button in self._action_buttons.items():
            set_button_role(button, "primary" if name == holder else "secondary")
        self._primary = holder
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_page.py -v`
Expected: all pass.

If `test_the_primary_follows…` fails on its first `process.setEnabled(True)` assertion, the event filter is not seeing `EnabledChange`. Check that the filter is installed on the buttons themselves, not on `self`, and that `isEnabled()` is read inside the filter. Qt sets `WA_Disabled` before it sends the event.

- [ ] **Step 5: Commit**

```bash
git add gui/tools_widget.py tests/test_tools_page.py
git commit -m "9.22: one primary on the Tools page, held by whichever card can run"
```

---

### Task 8: Both themes, the glossary, and the gate

**Files:**
- Test: `tests/test_tools_theme.py`
- Modify: `CONTEXT.md`

**Interfaces:**
- Consumes: everything above; `get_theme_manager()` with `.set_theme(name)`, `.apply_theme()` and `.get_current_theme()`, whose theme names are `"light"` and `"dark"`.

- [ ] **Step 1: Write the theme test**

`tests/test_tools_theme.py`:

```python
"""The fold button sits on its card's plane, in both themes.

Rendered, not asserted from the stylesheet string: the failure this guards
against is the global `QWidget { background-color: surface }` rule painting a
surface patch on a surface_raised card, and only pixels show that.
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor

from gui.theme_manager import get_theme_manager
from gui.tools_widget import ToolsWidget


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_fold_button_sits_on_the_card_plane(theme_name, qapp, print_settings_store):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    manager.apply_theme()

    tools = ToolsWidget(SimpleNamespace(session_path=None))
    tools.resize(1310, 700)
    tools.show()
    qapp.processEvents()

    widget = tools.reference_labels_widget
    card = widget.parentWidget()
    button = widget.print_options.fold_button
    image = card.grab().toImage()

    # The right end of the row: past the summary text, inside the 1px border.
    point = button.mapTo(card, QPoint(button.width() - 8, button.height() // 2))
    expected = QColor(manager.get_current_theme().surface_raised).name()
    assert image.pixelColor(point).name() == expected


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_card_is_raised_off_the_page(theme_name, qapp, print_settings_store):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    manager.apply_theme()

    tools = ToolsWidget(SimpleNamespace(session_path=None))
    tools.resize(1310, 700)
    tools.show()
    qapp.processEvents()

    card = tools.reference_labels_widget.parentWidget()
    image = card.grab().toImage()
    # Inside the card's 16px margin, clear of any child and of the rounded corner.
    assert image.pixelColor(QPoint(8, card.height() // 2)).name() == QColor(
        manager.get_current_theme().surface_raised
    ).name()
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tools_theme.py -v`
Expected: 4 passed.

If the fold-button test fails, print the sampled colour and `button.styleSheet()`:
- **The colour is the theme's `surface`:** the transparent background rule is not being applied. Check that `on_theme_changed` ran `_style_fold_button`.
- **The colour is text-coloured:** the sample landed on the summary text. Move the sample point to `button.width() - 3` and say so in the commit. Do not weaken the assertion to "any of several colours".

- [ ] **Step 3: Add the printing terms to `CONTEXT.md`**

Insert this section immediately before `## Repos`:

```markdown
## Printing

**Print mode** — how a label PDF reaches a printer: through the operating
system's print dialog (**driver**), or as raw ZPL sent straight to a printer
target (**Raw ZPL**). Chosen per tool and per PC.

**Print options** — one tool's print mode and the settings that mode needs.
Stored on the PC, not in the client profile.

**Fold** — a closed row that states the current values of the controls it
hides. It is opened to change a value, never to check one. Distinguished from
an **overflow**, which holds actions rather than values.

```

- [ ] **Step 4: Run the full gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass. The count is at least 1388 plus this bundle's new tests.

Run: `.venv/bin/python -m ruff check . --exclude shared`
Expected: `All checks passed!`

If any existing test fails, read it before changing anything. The likely candidates are tests that count primary buttons per screen, or that build a full `MainWindow` and walk into Tools. Fix the code if it breaks a stated rule. Change the test only if it encoded the old tab structure, and say so in the commit.

- [ ] **Step 5: Look at it**

Write a scratch script that is not committed, e.g. in `$CLAUDE_JOB_DIR/tmp/render_tools.py`. For each of `"light"` and `"dark"` it should:

1. Build a `ToolsWidget(SimpleNamespace(session_path=None))`.
2. Resize it to 1310×690, and show it.
3. Save `tools.grab()` to a PNG.
4. Open the fold on the Reference card, set its mode to Raw ZPL, and save a second PNG.

Monkeypatch `gui.components.print_options.load_print_settings` and `save_print_settings` the same way the fixture does, so the script does not write your real printer settings.

Read the four PNGs and check each of these:

- **Layout:** two cards side by side, with titles, descriptions and fields aligned at one inset across both cards.
- **Fold closed:** one summary line, with no printer rows showing.
- **Fold open in Raw ZPL:** target, size and rotate showing, and no Printer row.
- **Action rows:** on one baseline.
- **Surfaces:** no `surface`-coloured patch anywhere on either card.

Fix anything that fails and re-run the gate.

- [ ] **Step 6: Refresh the graph and commit**

```bash
graphify update .
git add tests/test_tools_theme.py CONTEXT.md
git commit -m "9.22: both themes, the glossary, and the gate"
/usr/bin/git push -u origin worktree-phase9-bundle8-tools-inner-tabs
```

---

## Done when

- **Cards:** both cards fit side by side at 1366×768 (a 1310 page) with no horizontal scroll (`test_side_by_side_at_the_1366_page_width_with_no_horizontal_scroll`).
- **Raw ZPL:** Raw ZPL hides the driver row (`test_raw_zpl_hides_the_driver_row`).
- **Stacking:** the stacked layout appears below 1180px (`test_stacked_below_1180`).
- **Gate:** the full suite passes, ruff is clean, `graphify update .` has run, and the branch is pushed.

## Self-review notes

- **Spec coverage:**
  - §2 page → Task 6
  - §2 eliding → Task 1
  - §3 cards and copy → Tasks 4–5
  - §4 component and wording → Tasks 2–3
  - §5 primary → Task 7
  - §6 theme → Task 3 (fold closure), Task 5 (build-time closures) and Task 8 (pixels)
  - §7 seams → one test file each
  - §8 → Done when
  - The `CONTEXT.md` glossary → Task 8
- **Deliberately not in any task:** message-box copy, event-time status-label restyling, and `shared/`. These are spec §10 out of scope.
- **Names used across tasks:**
  - `print_options`, `fold_button`, `body`, `print_mode_combo`, `driver_printer_combo`, `raw_zpl_target_edit`, `raw_zpl_label_width_spin`, `raw_zpl_label_height_spin`, `raw_zpl_rotate_check`
  - `LABEL_WIDTH`, `row_widget`, `ElidedLabel.full_text`
  - `cards_row`, `scroll`, `_apply_width`, `_STACK_BELOW`
  - `primary_holder`, `_sync_primary`, `_action_buttons`
  - `print_settings_store`
