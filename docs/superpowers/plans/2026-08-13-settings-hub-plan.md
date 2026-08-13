# UI Design System Track 4 — Settings Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the settings package Track C extracted into a designed Hub — a `collect()` contract that cannot silently drop config, a `FormSection` component, real primary/secondary button hierarchy, and a nav that looks like a sidebar and remembers where you were.

**Architecture:** Four independent slices over `gui/settings/` and `gui/components/`. The contract change (Task 1) is the only one that touches saved data and goes first. `FormSection` (Tasks 2-4) is built against real call sites, then adopted. Button roles (Tasks 5-6) and Hub chrome (Task 7) are pure QSS layered through `gui/theme_manager.py`, the repo-owned seam — `shared/theme.py` is sync-owned by `packing-tool` and is never edited.

**Tech Stack:** Python 3, PySide6, pytest (`QT_QPA_PLATFORM=offscreen`), ruff.

**Spec:** `docs/superpowers/specs/2026-08-13-settings-hub-design.md`

## Global Constraints

- **Never hand-edit anything under `shared/`.** It is one-way synced from `../packing-tool/shared/`. Every style change in this plan goes in `gui/theme_manager.py`.
- **No hardcoded colors.** Use `theme.*` tokens (`background`, `background_elevated`, `text`, `text_secondary`, `border`, `border_subtle`, `hover`, `accent_blue`, `button_hover_light`, `button_hover_dark`, `radius`, `spacing_*`). Never `#666`, `#999`, `color: gray`.
- **No font sizes outside the type scale.** Use `font_css(role)` / `apply_font(target, role)` from `gui/theme_manager.py`. Roles: `caption` (9pt), `body` (10pt), `label` (12pt bold), `heading` (14pt bold), `display` (17pt bold). An unknown role must raise `KeyError` — that rule is set by Tracks 1-3 and every new component keeps it.
- **No UI calls from background threads.**
- **Gate before finishing:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check . --exclude shared`. `python` is not on PATH on this machine — always go through `.venv/bin/`. Run `./scripts/setup_venv.sh` once in a fresh worktree.
- **Do not move `ClientSettingsDialog` or `GroupsManagementDialog` into the Hub.** The spec explains why; it is an open question for the user, not this plan's work.
- **Commit after every task.**

---

### Task 1: `collect()` replaces instead of merging

The shell merges dict-valued sections with `dict.update()`, which can add and overwrite but never remove. Both Important findings in PR #272's review trace to that one line. Replace it with plain assignment, and make the pages that own dict sub-trees hold the *live* dict so keys they do not render are never dropped.

**Files:**
- Modify: `gui/settings/base.py` (docstring)
- Modify: `gui/settings/window.py:231-236`
- Modify: `gui/settings/general.py:18-21`, `76-84`
- Modify: `gui/settings/weight.py:30-45`, `809-...` (the `return` at the end of `collect`)
- Modify: `gui/settings/mappings.py:206-210` (comment only)
- Test: `tests/test_settings_roundtrip.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the contract every later task relies on — `SettingsPage.collect() -> dict` where each value **replaces** `config_data[key]`, and a page owning a dict sub-tree returns the live dict it was constructed with.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings_roundtrip.py`. This is the behaviour the live-dict rule buys and nothing currently proves:

```python
def test_a_key_no_page_renders_survives_a_save(qapp, no_modals, started_workers):
    """Live client configs on the server can carry keys this build's UI does
    not know about -- profile_migrations.py exists because that has happened.
    A page returning a fresh dict would drop them on every save."""
    config = settings_fixture_config()
    config["settings"]["legacy_key_no_page_renders"] = "keep me"
    config["weight_config"]["legacy_weight_key"] = 123

    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    win.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    assert win.config_data["settings"]["legacy_key_no_page_renders"] == "keep me"
    assert win.config_data["weight_config"]["legacy_weight_key"] == 123
    win.deleteLater()
```

- [ ] **Step 2: Run it and confirm it passes for the wrong reason, then prove that**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py::test_a_key_no_page_renders_survives_a_save -v`

Expected: **PASS** — today's `dict.update()` merge preserves those keys by accident. That is not proof; it is the trap. Prove the test has teeth by temporarily changing `window.py:231-236` to the unconditional assignment this task is about to make permanent:

```python
for page in self._pages:
    for key, value in page.collect().items():
        self.config_data[key] = value
```

Re-run. Expected: **FAIL** on both asserts — `GeneralPage` and `WeightPage` return fresh dicts. **Leave this assignment in place**; Steps 3-4 make the pages correct under it.

- [ ] **Step 3: Make `GeneralPage` hold the live `settings` dict**

In `gui/settings/general.py`, store the constructor's dict and update it in place:

```python
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        # Held by reference so collect() can update it in place. The shell
        # assigns collect()'s value straight over config_data[key], so a
        # fresh dict here would drop any key this page does not render.
        self._settings = settings
        main_layout = QVBoxLayout(self)
```

and:

```python
    def collect(self) -> dict:
        self._settings.update({
            "stock_csv_delimiter": self.stock_delimiter_edit.text(),
            "orders_csv_delimiter": self.orders_delimiter_edit.text(),
            "low_stock_threshold": int(self.low_stock_edit.text()),
            "repeat_detection_days": self.repeat_days_input.value(),
        })
        return {"settings": self._settings}
```

- [ ] **Step 4: Make `WeightPage` hold the live `weight_config` dict**

In `gui/settings/weight.py`, `weight_cfg` is already "whichever dict we actually used" — `weight_config` when truthy, a fresh default when not. Keep a handle to it right after line 41-45:

```python
        weight_cfg = weight_config or {
            "volumetric_divisor": 6000,
            "products": {},
            "boxes": []
        }
        # Held by reference for collect() -- see SettingsPage's contract. Note
        # this is weight_cfg, not weight_config: an empty config substitutes a
        # fresh dict above, and that substitute is the one to keep.
        self._weight_config = weight_cfg
```

Then change the `return` at the end of `collect()` (around `weight.py:873`) from building a fresh dict to updating the held one:

```python
        self._weight_config.update({
            "volumetric_divisor": divisor,
            "products": products,
            "boxes": boxes,
        })
        return {"weight_config": self._weight_config}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -v`

Expected: all PASS, including the new test and the four existing ones.

- [ ] **Step 6: Write the contract down where implementers will read it**

`gui/settings/base.py`:

```python
class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. Pages that
    persist their own data immediately (Sets, Column Config) inherit both
    defaults and contribute nothing to the window's single write.

    collect() returns {config_key: value}, and each value REPLACES
    config_data[key] outright -- the window does not merge. A page that
    owns a dict sub-tree must therefore mutate and return the live dict it
    was constructed with, so keys it does not render survive the save.
    Returning a freshly built dict silently drops them.

    collect() writing into config_data before the window assigns is safe by
    construction: save_settings() runs validate() across every page before
    calling collect() on any of them, so no page mutates during a save a
    later page will block. config_data is a deep copy, so a failed server
    write cannot reach the caller's config either.
    """
```

Replace the stale one-liner on `collect` itself:

```python
    def collect(self) -> dict:
        """The config keys this page owns. Each value replaces config_data[key]."""
        return {}
```

- [ ] **Step 7: Retarget the `MappingsPage` comment at the contract**

`gui/settings/mappings.py:206-210` describes the merge it was working around. That merge is gone. Replace those five comment lines with:

```python
        # SettingsPage's contract: the returned value replaces
        # config_data[key], so these must be the live dicts handed to
        # __init__ -- clear-and-refill in place, never a fresh dict.
```

The `clear()`/`update()` calls below it stay exactly as they are.

- [ ] **Step 8: Prove the guard tests still bite**

The discipline PR #272 established: a guard test never shown to fail is decoration. Temporarily make `GeneralPage.collect()` return `{"settings": dict(self._settings)}` (a copy).

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -v`

Expected: `test_a_key_no_page_renders_survives_a_save` FAILS. Restore, re-run, confirm green.

- [ ] **Step 9: Full gate and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add gui/settings/base.py gui/settings/window.py gui/settings/general.py gui/settings/weight.py gui/settings/mappings.py tests/test_settings_roundtrip.py
git commit -m "fix(settings): collect() replaces instead of merging

The shell's one-level dict.update() merge could add and overwrite but
never remove, which is the root cause of both Important findings in
#272's review. Pages owning a dict sub-tree now hold the live dict, so
keys they do not render survive without the merge."
```

---

### Task 2: The `FormSection` component

Track 3 deferred `FormSection` so a real page would shape its API (`2026-08-12-component-library-design.md:12-17`). The call sites now exist: a title, an optional description paragraph, and either form rows or an arbitrary child widget.

**Files:**
- Create: `gui/components/form_section.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_form_section.py`

**Interfaces:**
- Consumes: `font_css(role)` and `get_theme_manager()` from `gui/theme_manager.py`.
- Produces: `FormSection(title: str, description: str = "", parent=None)` with `.add_row(label: str, widget: QWidget, tooltip: str = "") -> QLabel` (returns the label it built) and `.add_widget(widget: QWidget) -> None`. Tasks 3 and 4 consume exactly these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_components_form_section.py`, matching the construction-test style of `tests/test_components_card.py` (no window needed):

```python
"""Construction tests for the FormSection component. No window needed."""
import pytest
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QLineEdit

from gui.components.form_section import FormSection
from gui.theme_manager import TYPE_SCALE


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


def test_title_renders_at_the_label_role():
    section = FormSection("General Settings")
    title = section.layout().itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.text() == "General Settings"
    assert f"font-size: {TYPE_SCALE['label'].size_pt}pt" in title.styleSheet()


def test_description_is_omitted_when_not_given():
    section = FormSection("General Settings")
    # title + the form body, nothing else
    assert section.layout().count() == 2


def test_description_wraps_and_renders_at_caption():
    section = FormSection("Courier Mappings", "Map provider names to codes.")
    desc = section.layout().itemAt(1).widget()
    assert desc.text() == "Map provider names to codes."
    assert desc.wordWrap() is True
    assert f"font-size: {TYPE_SCALE['caption'].size_pt}pt" in desc.styleSheet()


def test_add_row_builds_the_label_and_puts_both_in_the_form():
    section = FormSection("S")
    field = QLineEdit()
    label = section.add_row("Stock CSV Delimiter:", field)
    form = section.form
    assert isinstance(form, QFormLayout)
    assert form.rowCount() == 1
    assert form.itemAt(0, QFormLayout.LabelRole).widget() is label
    assert form.itemAt(0, QFormLayout.FieldRole).widget() is field
    assert label.text() == "Stock CSV Delimiter:"


def test_add_row_tooltip_reaches_the_label_too():
    """Hovering the label should explain the field. Today only the input
    carries the tooltip, so the explanation is invisible to anyone reading
    the form rather than clicking into it."""
    section = FormSection("S")
    field = QLineEdit()
    label = section.add_row("Low Stock Threshold:", field, tooltip="Alert below this.")
    assert label.toolTip() == "Alert below this."
    assert field.toolTip() == "Alert below this."


def test_add_row_leaves_an_existing_widget_tooltip_alone():
    section = FormSection("S")
    field = QLineEdit()
    field.setToolTip("set by the caller")
    section.add_row("X:", field)
    assert field.toolTip() == "set by the caller"


def test_add_widget_appends_below_the_form():
    section = FormSection("Courier Mappings")
    child = QLineEdit()
    section.add_widget(child)
    assert section.layout().indexOf(child) == section.layout().count() - 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_form_section.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'gui.components.form_section'`.

- [ ] **Step 3: Write the component**

Create `gui/components/form_section.py`:

```python
"""A titled settings section: heading, optional description, form rows.

Deferred here from Track 3 so real call sites would shape the API -- see
docs/superpowers/specs/2026-08-12-component-library-design.md:12-17.

Replaces two patterns at once. QGroupBox + QFormLayout in the settings
pages, where the OS group-box chrome duplicates a title the nav already
shows; and the hand-rolled font_css("heading") label written three times
(sets.py, window.py's _ColumnConfigPage, mappings.py's instructions
paragraph). One component rather than a second PageHeader type.
"""

from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QVBoxLayout, QWidget

from gui.theme_manager import font_css, get_theme_manager


class FormSection(QFrame):
    """A titled block of form rows.

    Args:
        title: Section heading, rendered at the `label` type-scale role.
        description: Optional wrapped paragraph under the title, at
            `caption` in the secondary text colour. Omitted entirely when
            empty -- an empty QLabel still takes vertical space.
    """

    def __init__(self, title: str, description: str = "", parent=None) -> None:
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.spacing_md, theme.spacing_sm, theme.spacing_md, theme.spacing_sm
        )
        layout.setSpacing(theme.spacing_xs)

        title_label = QLabel(title)
        title_label.setStyleSheet(font_css("label"))
        layout.addWidget(title_label)

        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(
                f"color: {theme.text_secondary}; {font_css('caption')}"
            )
            layout.addWidget(desc_label)

        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(theme.spacing_sm)
        layout.addLayout(self.form)

    def add_row(self, label: str, widget: QWidget, tooltip: str = "") -> QLabel:
        """Append a labelled row and return the label it built.

        The pages currently name a QLabel variable per row purely to hand it
        to addRow. The label is returned for the rare caller that needs a
        handle to it.

        `tooltip` is applied to the label as well as the widget, so hovering
        the row's text explains the field. A widget that already carries its
        own tooltip keeps it.
        """
        row_label = QLabel(label)
        if tooltip:
            row_label.setToolTip(tooltip)
            if not widget.toolTip():
                widget.setToolTip(tooltip)
        self.form.addRow(row_label, widget)
        return row_label

    def add_widget(self, widget: QWidget) -> None:
        """Append a widget below the form rows.

        Not every section that wants a title holds form rows -- the courier
        mappings section is a title over a button-and-rows column.
        """
        self.layout().addWidget(widget)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_form_section.py -v`

Expected: all 7 PASS.

- [ ] **Step 5: Export it**

`gui/components/__init__.py` currently holds only a docstring. Append:

```python
from gui.components.card import Card
from gui.components.form_section import FormSection

__all__ = ["Card", "FormSection"]
```

- [ ] **Step 6: Gate and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add gui/components/form_section.py gui/components/__init__.py tests/test_components_form_section.py
git commit -m "feat(components): add FormSection, deferred to Track 4 from Track 3"
```

---

### Task 3: Adopt `FormSection` in General and Mappings

Four `QGroupBox` sites, and the four-lines-per-field label ceremony in `general.py`.

**Files:**
- Modify: `gui/settings/general.py:20-74`
- Modify: `gui/settings/mappings.py:43-44`, `65-66`, `87-97`, `110`
- Test: `tests/test_settings_roundtrip.py` (existing tests must stay green)

**Interfaces:**
- Consumes: `FormSection(title, description="")`, `.add_row(label, widget, tooltip="")`, `.add_widget(widget)` from Task 2.
- Produces: nothing new. Widget attribute names (`self.stock_delimiter_edit`, `self.orders_delimiter_edit`, `self.low_stock_edit`, `self.repeat_days_input`, `self.orders_mapping_widget`, `self.stock_mapping_widget`, `self.courier_mappings_container`) are unchanged — `collect()` and the existing tests reference them.

- [ ] **Step 1: Confirm the safety net is green before touching anything**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -v`

Expected: all PASS. This is a pure layout change — every one of these tests must still pass at the end, unchanged. If one needs editing, the change stopped being pure and you should stop and say so.

- [ ] **Step 2: Rewrite `GeneralPage`'s body**

Replace `gui/settings/general.py` lines 20-74 (from `main_layout = QVBoxLayout(self)` through `main_layout.addStretch()`) with:

```python
        main_layout = QVBoxLayout(self)

        section = FormSection("General Settings")

        self.stock_delimiter_edit = QLineEdit(settings.get("stock_csv_delimiter", ";"))
        self.stock_delimiter_edit.setMaximumWidth(100)
        section.add_row(
            "Stock CSV Delimiter:",
            self.stock_delimiter_edit,
            tooltip=(
                "Character used to separate columns in stock CSV file.\n\n"
                "Common values:\n"
                "  • Semicolon (;) - for exports from local warehouse\n"
                "  • Comma (,) - for Shopify exports\n\n"
                "Make sure this matches your stock CSV file format."
            ),
        )

        self.orders_delimiter_edit = QLineEdit(settings.get("orders_csv_delimiter", ","))
        self.orders_delimiter_edit.setMaximumWidth(100)
        self.orders_delimiter_edit.setPlaceholderText(",")
        section.add_row(
            "Orders CSV Delimiter:",
            self.orders_delimiter_edit,
            tooltip=(
                "Character used to separate columns in orders CSV file.\n\n"
                "Common values:\n"
                "  • Comma (,) - standard Shopify exports\n"
                "  • Semicolon (;) - European Excel exports\n"
                "  • Tab (\\t) - tab-separated files\n\n"
                "The tool will auto-detect delimiter when you select a file,\n"
                "but you can override it here if needed."
            ),
        )

        self.low_stock_edit = QLineEdit(str(settings.get("low_stock_threshold", 5)))
        self.low_stock_edit.setMaximumWidth(100)
        section.add_row(
            "Low Stock Threshold:",
            self.low_stock_edit,
            tooltip=(
                "Trigger stock alerts when quantity falls below this number.\n\n"
                "Items with stock below this threshold will be marked in analysis."
            ),
        )

        self.repeat_days_input = QSpinBox()
        self.repeat_days_input.setMinimum(1)
        self.repeat_days_input.setMaximum(365)
        self.repeat_days_input.setValue(settings.get("repeat_detection_days", 1))
        section.add_row(
            "Repeat Detection Window (days):",
            self.repeat_days_input,
            tooltip=(
                "Orders fulfilled within this many days are marked as 'Repeat'.\n"
                "Default: 1 day (only yesterday's fulfillments)\n"
                "Increase for longer detection window (e.g., 7 days, 30 days)"
            ),
        )

        main_layout.addWidget(section)
        main_layout.addStretch()
```

Fix the imports at the top of the file: drop `QFormLayout`, `QGroupBox` and `QLabel` (no longer used), add `from gui.components.form_section import FormSection`. The remaining PySide6 imports are `QLineEdit`, `QSpinBox`, `QVBoxLayout`.

Note the tooltip strings are copied verbatim — including the `\\t` escape in the orders-delimiter text, which renders as a literal `\t` for the user and must not be turned into a tab.

- [ ] **Step 3: Swap the three `QGroupBox` sites in `MappingsPage`**

In `gui/settings/mappings.py`:

```python
        # line 43-44
        orders_box = FormSection("Orders CSV Column Mapping")
        # ...unchanged field/mapping setup...
        orders_box.add_widget(self.orders_mapping_widget)   # was orders_layout.addWidget
        scroll_layout.addWidget(orders_box)
```

```python
        # line 65-66
        stock_box = FormSection("Stock CSV Column Mapping")
        # ...unchanged...
        stock_box.add_widget(self.stock_mapping_widget)     # was stock_layout.addWidget
        scroll_layout.addWidget(stock_box)
```

The courier section's instructions paragraph is exactly what `description` is for — the hand-rolled `instructions2` label at lines 90-97 goes away:

```python
        courier_mappings_box = FormSection(
            "Courier Mappings",
            "Map different shipping provider names to standardized courier codes. "
            "You can specify multiple patterns (comma-separated) for each courier.",
        )

        self.courier_mappings_container = QWidget()
        self.courier_mappings_layout = QVBoxLayout(self.courier_mappings_container)
        self.courier_mappings_layout.setContentsMargins(0, 0, 0, 0)
        courier_mappings_box.add_widget(self.courier_mappings_container)

        add_courier_btn = QPushButton("+ Add Courier Mapping")
        add_courier_btn.clicked.connect(lambda: self.add_courier_mapping_row())
        courier_mappings_box.add_widget(add_courier_btn)
```

The old `courier_main_layout.addWidget(add_courier_btn, 0, Qt.AlignLeft)` had a left-align flag that `add_widget` does not take. Give the button `add_courier_btn.setMaximumWidth(200)` instead so it does not stretch the full section width.

Then fix imports: drop `QGroupBox`, and drop `QLabel`, `font_css`, `get_theme_manager` and `Qt` **only if** nothing else in the file still uses them — grep before deleting, this file is 8.5K and has more below line 120.

- [ ] **Step 4: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -v`

Expected: all PASS, `tests/test_settings_roundtrip.py` included and unmodified.

- [ ] **Step 5: Report the diff honestly**

Run: `git diff --stat gui/settings/general.py gui/settings/mappings.py`

The spec claims `FormSection` earns its keep at six sites. Four of them are here. Note in the commit message whether these two files got shorter or longer. If they got meaningfully longer, say so — that is information the user needs about whether the component was worth building, not something to hide.

- [ ] **Step 6: Gate and commit**

```bash
.venv/bin/ruff check . --exclude shared
git add gui/settings/general.py gui/settings/mappings.py
git commit -m "refactor(settings): General and Mappings use FormSection"
```

---

### Task 4: Adopt `FormSection` for the two hand-rolled headers

`SetsPage` and `_ColumnConfigPage` each build a `font_css("heading")` label by hand; one of them also builds an italic secondary-coloured description. That is `FormSection`'s title and description written out longhand.

**Files:**
- Modify: `gui/settings/sets.py:43-46`
- Modify: `gui/settings/window.py:334-363`
- Test: `tests/test_settings_roundtrip.py` (existing, must stay green)

**Interfaces:**
- Consumes: `FormSection(title, description="")` and `.add_widget(widget)` from Task 2.
- Produces: nothing. `SetsPage.set_decoders` and `_ColumnConfigPage.panel` keep their names.

- [ ] **Step 1: Replace `SetsPage`'s header**

`gui/settings/sets.py:43-46` currently reads:

```python
        # Header
        header_label = QLabel("Set/Bundle Definitions")
        header_label.setStyleSheet(font_css("heading"))
        main_layout.addWidget(header_label)
```

The search box and table below it are separate widgets in `main_layout`, so this section holds only a title. Replace with:

```python
        main_layout.addWidget(FormSection("Set/Bundle Definitions"))
```

Add `from gui.components.form_section import FormSection` to the imports. Leave `font_css` imported only if something else in the file uses it — grep first.

Note this drops the header from `heading` (14pt) to `label` (12pt), matching every other settings section. That is the point: nine pages should not each pick their own header size.

- [ ] **Step 2: Replace `_ColumnConfigPage`'s header**

`gui/settings/window.py:343-358` builds a heading label, then fetches the theme purely to colour an italic help paragraph. All of it collapses:

```python
        from gui.column_config_dialog import ColumnConfigPanel

        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(FormSection(
            "Column Configuration",
            "Configure which columns are visible in the analysis table, "
            "their order, and saved views.",
        ))

        self.panel = ColumnConfigPanel(
            main_window.table_config_manager, main_window=main_window, parent=self
        )
        layout.addWidget(self.panel)
```

Add `from gui.components.form_section import FormSection` to `window.py`'s imports. Remove the now-unused `font_css` import and the local `from gui.theme_manager import get_theme_manager` at line 348 — but check `apply_font` is still imported, `_build_settings_nav` uses it.

- [ ] **Step 3: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -v`

Expected: all PASS. `test_window_registers_every_page` in particular proves `_ColumnConfigPage` still constructs.

- [ ] **Step 4: Gate and commit**

```bash
.venv/bin/ruff check . --exclude shared
git add gui/settings/sets.py gui/settings/window.py
git commit -m "refactor(settings): Sets and Column Config headers use FormSection

Both hand-rolled a font_css('heading') label; one also hand-rolled the
italic description. Same widget, third and fourth copy."
```

---

### Task 5: The button `role` property and its stylesheet

`shared/theme.py:203-211` styles every `QPushButton` accent-blue on white. In the Rules page, "Add Rule", "Add Step", "Delete" and the window's "Save" render identically. Track 3 recorded that no `:default` rule exists and that hierarchy has to be built.

**Files:**
- Modify: `gui/theme_manager.py`
- Test: `tests/test_theme_button_roles.py` (create)

**Interfaces:**
- Consumes: `ThemeTokens` from `shared.theme`, already imported in `theme_manager.py`.
- Produces: `role_stylesheet(theme: ThemeTokens) -> str` and `set_button_role(button, role: str) -> None`, both importable from `gui.theme_manager`. Task 6 and Task 7 consume `set_button_role`; Task 7 extends `role_stylesheet`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_theme_button_roles.py`:

```python
"""The primary/secondary button hierarchy Track 3 said had to be built.

shared/theme.py paints every QPushButton accent-blue, and it is sync-owned
by packing-tool so it cannot be edited here. These rules are layered on in
gui/theme_manager.py, the repo-owned seam.
"""
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from gui.theme_manager import role_stylesheet, set_button_role
from shared.theme import get_theme


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_both_roles_have_a_rule(theme_name):
    qss = role_stylesheet(get_theme(theme_name))
    assert 'QPushButton[role="primary"]' in qss
    assert 'QPushButton[role="secondary"]' in qss


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_two_roles_do_not_render_the_same(theme_name):
    """A token that happens to resolve to the same colour in one theme is
    invisible on Linux and only shows up on the Windows machines that run
    this app."""
    theme = get_theme(theme_name)
    qss = role_stylesheet(theme)
    primary = qss.split('QPushButton[role="primary"]')[1].split("}")[0]
    secondary = qss.split('QPushButton[role="secondary"]')[1].split("}")[0]
    assert "background-color" in primary
    assert "background-color" in secondary
    assert primary != secondary


def test_set_button_role_sets_the_property():
    button = QPushButton("Save")
    set_button_role(button, "primary")
    assert button.property("role") == "primary"


def test_set_button_role_rejects_an_unknown_role():
    """Same rule Tracks 1-3 set for the type scale: a typo fails in
    development rather than silently rendering as an unstyled button."""
    button = QPushButton("Save")
    with pytest.raises(ValueError):
        set_button_role(button, "tertiary")


def test_the_suffix_is_actually_applied_to_the_app():
    from gui.theme_manager import get_theme_manager

    get_theme_manager().apply_theme()
    assert 'QPushButton[role="primary"]' in QApplication.instance().styleSheet()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_button_roles.py -v`

Expected: FAIL with `ImportError: cannot import name 'role_stylesheet'`.

- [ ] **Step 3: Add the stylesheet builder and the setter**

In `gui/theme_manager.py`, after `apply_font` at the end of the file:

```python
BUTTON_ROLES = ("primary", "secondary")


def role_stylesheet(theme: ThemeTokens) -> str:
    """QSS for the button hierarchy, appended after shared.theme's sheet.

    shared/theme.py paints every QPushButton accent-blue and is sync-owned
    by packing-tool, so it cannot be edited here -- these rules layer on in
    this module, the same seam Track 1 used for the font override.

    Deliberately opt-in: a button with no `role` property keeps exactly its
    current appearance. The opposite arrangement (neutral by default, mark
    the primaries) is fewer edits but restyles every button in the app at
    once, and this is a Windows-only app with three tracks of visual change
    not yet verified on Windows.
    """
    hover = theme.button_hover_dark if theme.name == "dark" else theme.button_hover_light
    return f"""
        QPushButton[role="primary"] {{
            background-color: {theme.accent_blue};
            color: white;
            border: 1px solid {theme.accent_blue};
            font-weight: bold;
        }}
        QPushButton[role="primary"]:hover {{ background-color: {hover}; }}

        QPushButton[role="secondary"] {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QPushButton[role="secondary"]:hover {{ background-color: {theme.hover}; }}

        QPushButton[role="primary"]:disabled, QPushButton[role="secondary"]:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}
    """


def set_button_role(button, role: str) -> None:
    """Mark a button primary or secondary.

    Qt does not restyle a widget when a dynamic property changes after the
    stylesheet was applied -- the classic trap. Every call site here sets
    the role at construction, where it would not matter, but unpolish/polish
    runs unconditionally so a later live-flipping caller cannot step in it.
    """
    if role not in BUTTON_ROLES:
        raise ValueError(f"Unknown button role {role!r}; expected one of {BUTTON_ROLES}")
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)
```

- [ ] **Step 4: Append the suffix in `apply_theme`**

`gui/theme_manager.py:74` currently reads `app.setStyleSheet(build_stylesheet(theme))`. Change to:

```python
        app.setStyleSheet(build_stylesheet(theme) + role_stylesheet(theme))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_button_roles.py -v`

Expected: all PASS.

- [ ] **Step 6: Gate and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add gui/theme_manager.py tests/test_theme_button_roles.py
git commit -m "feat(theme): opt-in primary/secondary button roles

Track 3 recorded that no :default rule exists anywhere, so hierarchy had
to be built rather than re-enabled. Layered in theme_manager because
shared/theme.py is sync-owned by packing-tool."
```

---

### Task 6: Apply the roles inside the Hub

Inside the Hub, Save should be the only accent-blue button on screen. Scope is `gui/settings/` and nothing else — the rest of the app adopts the property as its screens are touched, per Track 5's incremental rule.

**Files:**
- Modify: `tests/conftest.py`, `tests/test_settings_roundtrip.py:19-148` (fixtures move)
- Modify: `gui/settings/window.py:167-171`
- Modify: `gui/settings/rules.py`, `packing_lists.py`, `stock_exports.py`, `mappings.py`, `weight.py`, `sets.py` — action buttons only
- Test: `tests/test_settings_button_roles.py` (create)

**Interfaces:**
- Consumes: `set_button_role(button, role)` from Task 5.
- Produces: the `qapp`, `no_modals`, `started_workers` and `window` fixtures plus the `settings_fixture_config()` helper, now in `tests/conftest.py` — Task 7's tests use them too.

- [ ] **Step 1: Promote the settings fixtures into `conftest.py`**

Tasks 6 and 7 both need `SettingsWindow` fixtures that today live inside `tests/test_settings_roundtrip.py`. **Do not import them across test files** — `tests/` has no `__init__.py`, so `from tests.test_settings_roundtrip import ...` fails outright and the bare `from test_settings_roundtrip import ...` form only works by way of pytest's rootdir sys.path insertion. `conftest.py` is the mechanism pytest provides for exactly this and needs no import at all.

Cut `qapp`, `no_modals`, `settings_fixture_config`, `started_workers` and `window` (lines 19-148, including their docstrings — they explain four real gotchas and must survive the move) out of `tests/test_settings_roundtrip.py` and paste them at the end of `tests/conftest.py`. Add the imports they need to the top of `conftest.py`:

```python
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QMessageBox

from gui.settings.window import SettingsWindow
```

and extend `conftest.py`'s module docstring, which currently claims to be backend-only:

```python
"""Shared fixtures for the test suite.

Column names mirror the DEFAULT Shopify/Bulgarian-ERP mapping hardcoded in
shopify_tool.analysis._clean_and_prepare_data (used when column_mappings=None),
so fixtures exercise the exact same path production runs through.

The SettingsWindow fixtures at the bottom are here rather than in a test
module because three test files need them and `tests/` is not a package --
conftest is the only sharing mechanism that does not depend on sys.path.
"""
```

`test_settings_roundtrip.py` keeps its six test functions (five original plus the one Task 1 added). Five of them take only fixtures and need no imports beyond `copy`. The sixth — `test_a_key_no_page_renders_survives_a_save` — builds its own window, so switch it to the factory fixture rather than re-importing the helper:

```python
def test_a_key_no_page_renders_survives_a_save(
    qapp, no_modals, started_workers, make_settings_config
):
    config = make_settings_config()
    config["settings"]["legacy_key_no_page_renders"] = "keep me"
    config["weight_config"]["legacy_weight_key"] = 123

    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    ...
```

which leaves `test_settings_roundtrip.py` importing `copy`, `Mock` and `SettingsWindow`.

**`settings_fixture_config` is a plain function, not a fixture**, so pytest will *not* inject it into other test modules the way it does `window`. Task 7 needs two fresh configs inside one test, so expose it as a factory fixture alongside the function:

```python
@pytest.fixture
def make_settings_config():
    """Factory, not a value: test_settings_nav builds two windows in one test
    and each needs its own config to mutate."""
    return settings_fixture_config
```

The `window` fixture in `conftest.py` keeps calling the module-level `settings_fixture_config()` directly — they are in the same file.

- [ ] **Step 2: Verify the move changed nothing**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -v`

Expected: the same five tests, all PASS. A collection error here means an import did not come along.

- [ ] **Step 3: Write the failing test**

Create `tests/test_settings_button_roles.py`. The fixtures arrive from `conftest.py`, so there is nothing to import:

```python
"""Inside the Hub, Save is the only accent-filled button on screen."""
from PySide6.QtWidgets import QPushButton


def test_the_footer_marks_save_primary_and_cancel_secondary(window):
    assert window.save_button.property("role") == "primary"
    cancel = window.save_button.parent().buttons()[1]
    assert cancel.property("role") == "secondary"


def test_no_page_leaves_an_unmarked_button_competing_with_save(window):
    """An unmarked button still renders accent-blue, so it would read as a
    second primary action. Inside the Hub every in-page button is secondary."""
    unmarked = []
    for page in window._pages:
        for button in page.findChildren(QPushButton):
            if button.property("role") is None:
                unmarked.append(f"{type(page).__name__}: {button.text()!r}")
    assert unmarked == [], "unmarked buttons inside the Hub: " + ", ".join(unmarked)
```

- [ ] **Step 4: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_button_roles.py -v`

Expected: both FAIL — the first on `None != "primary"`, the second listing every button in the package.

- [ ] **Step 5: Mark the footer**

`gui/settings/window.py:167-171`:

```python
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        set_button_role(self.save_button, "primary")
        set_button_role(button_box.button(QDialogButtonBox.Cancel), "secondary")
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
```

Import `set_button_role` alongside the existing `apply_font, font_css` import from `gui.theme_manager`.

- [ ] **Step 6: Mark every in-page button secondary, driven by the failing test**

Do not guess the list. Run the test from Step 4 and work through the names it prints — that is the authoritative inventory, and it covers buttons created in loops (per-rule Delete, per-filter `X`) that a grep for `QPushButton(` would find but a grep for a variable name would not.

For buttons built inside row/item factories, mark them where they are constructed so every instance gets it:

```python
        delete_btn = QPushButton("X")
        set_button_role(delete_btn, "secondary")
```

`gui/settings/fields.py:151` builds the shared filter-row delete button used by both Packing Lists and Stock Exports — marking it once there covers both pages.

Re-run the test after each file and watch the list shrink.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_button_roles.py -v`

Expected: both PASS, and the second one now guards against a future page adding an unmarked button.

- [ ] **Step 8: Gate and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add gui/settings/ tests/conftest.py tests/test_settings_roundtrip.py tests/test_settings_button_roles.py
git commit -m "feat(settings): Save is the Hub's only primary button

Settings fixtures move to conftest.py so the new test files can reach
them -- tests/ is not a package, so cross-file fixture imports do not
work."
```

---

### Task 7: Nav styling and remembered page

The nav is a bare `QListWidget` at a fixed 170px — a list dropped next to the content rather than a sidebar. And with nine pages, every open lands on "General".

**Files:**
- Modify: `gui/theme_manager.py` (`role_stylesheet`)
- Modify: `gui/settings/window.py:121-124`, `189-216`
- Test: `tests/test_settings_nav.py` (create)

**Interfaces:**
- Consumes: `role_stylesheet` from Task 5, `SETTINGS_NAV_GROUPS` and `_page_index_by_name` from `window.py`.
- Produces: `SettingsWindow.NAV_SETTINGS_KEY = "settings_hub/last_page"`, and `SettingsWindow._save_nav_selection()` / `_restore_nav_selection()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_nav.py`:

```python
"""The Hub remembers which page you were on.

Nine pages and one QListWidget; the Weight and Rules pages are the ones
people return to.

Fixtures (qapp, no_modals, started_workers, window, make_settings_config)
all come from conftest.py.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings, Qt

from gui.settings.window import SettingsWindow


@pytest.fixture(autouse=True)
def clean_nav_setting():
    """QSettings is process-global and persists to disk on this machine, so
    a leftover value would leak between tests and between runs."""
    store = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
    store.remove(SettingsWindow.NAV_SETTINGS_KEY)
    yield
    store.remove(SettingsWindow.NAV_SETTINGS_KEY)


def _current_page_name(win):
    return win._settings_nav.currentItem().text()


def test_a_fresh_profile_lands_on_the_first_entry(window):
    assert _current_page_name(window) == "General"


def test_the_selected_page_is_remembered_by_name(
    qapp, no_modals, started_workers, make_settings_config
):
    first = SettingsWindow(client_id="M", client_config=make_settings_config(),
                           profile_manager=Mock())
    for row in range(first._settings_nav.count()):
        if first._settings_nav.item(row).text() == "Weight":
            first._settings_nav.setCurrentRow(row)
            break
    first.deleteLater()

    second = SettingsWindow(client_id="M", client_config=make_settings_config(),
                            profile_manager=Mock())
    assert _current_page_name(second) == "Weight"
    second.deleteLater()


def test_a_page_name_that_no_longer_exists_falls_back(
    qapp, no_modals, started_workers, make_settings_config
):
    """Nav groups have gained entries twice already. Storing a row index
    would silently point at a different page; a stale *name* must degrade to
    the first entry rather than raise or select nothing."""
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
        SettingsWindow.NAV_SETTINGS_KEY, "A Page That Was Removed"
    )

    win = SettingsWindow(client_id="M", client_config=make_settings_config(),
                         profile_manager=Mock())
    assert _current_page_name(win) == "General"
    win.deleteLater()


def test_headers_are_not_selectable_and_are_never_stored(window):
    headers = [
        window._settings_nav.item(row)
        for row in range(window._settings_nav.count())
        if not window._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
    ]
    assert [h.text() for h in headers] == ["DATA", "FULFILLMENT LOGIC", "OUTPUT", "ORGANIZATION"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_nav.py -v`

Expected: FAIL with `AttributeError: type object 'SettingsWindow' has no attribute 'NAV_SETTINGS_KEY'`.

- [ ] **Step 3: Persist and restore the selection**

In `gui/settings/window.py`, add the key as a class attribute next to `SETTINGS_NAV_GROUPS`:

```python
    # Stored by *name*, not row index: the nav groups have gained entries
    # twice already and an index would silently point at a different page.
    NAV_SETTINGS_KEY = "settings_hub/last_page"
```

Replace the "select the first real entry" tail of `_build_settings_nav` (lines 204-208) with a call to a restore helper, and add both helpers:

```python
        self._settings_nav.currentItemChanged.connect(self._on_settings_nav_changed)
        self._restore_nav_selection()

    def _first_selectable_row(self) -> int:
        for row in range(self._settings_nav.count()):
            if self._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                return row
        return -1

    def _restore_nav_selection(self) -> None:
        """Select the last-viewed page, or the first entry if it is gone."""
        wanted = QSettings("ShopifyFulfillmentTool", "FulfillmentApp").value(
            self.NAV_SETTINGS_KEY
        )
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.text() == wanted and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self._settings_nav.setCurrentRow(row)
                return
        row = self._first_selectable_row()
        if row >= 0:
            self._settings_nav.setCurrentRow(row)
```

Record the choice in the existing selection handler, which already ignores headers because they cannot become current:

```python
    def _on_settings_nav_changed(self, current, _previous):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)
            QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
                self.NAV_SETTINGS_KEY, current.text()
            )
```

Add `QSettings` to the `PySide6.QtCore` import at the top of the file (currently `from PySide6.QtCore import Qt, QThreadPool`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_nav.py -v`

Expected: all 4 PASS.

- [ ] **Step 5: Style the nav as a sidebar**

Give the nav an object name so the QSS can target it without hitting every `QListWidget` in the app. In `window.py:121`:

```python
        self._settings_nav = QListWidget()
        self._settings_nav.setObjectName("settingsNav")
```

Append to the returned string in `role_stylesheet` (`gui/theme_manager.py`), before the closing quotes:

```python
        QListWidget#settingsNav {{
            background-color: {theme.background};
            border: none;
            border-right: 1px solid {theme.border_subtle};
            outline: none;
        }}
        QListWidget#settingsNav::item {{
            padding: 6px 10px;
            border-radius: {theme.radius}px;
        }}
        QListWidget#settingsNav::item:hover {{ background-color: {theme.hover}; }}
        QListWidget#settingsNav::item:selected {{
            background-color: {theme.active_background};
            color: {theme.text};
            border-left: 2px solid {theme.accent_blue};
        }}
        QListWidget#settingsNav::item:disabled {{
            color: {theme.text_secondary};
            padding-top: 10px;
        }}
```

Group headers are already non-selectable (`Qt.ItemFlag.NoItemFlags`) and already bold `caption`, so `::item:disabled` is what colours them — the extra top padding is what separates one group from the previous group's last entry.

- [ ] **Step 6: Extend the Task 5 stylesheet test to cover the nav**

Add to `tests/test_theme_button_roles.py`:

```python
@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_settings_nav_is_styled_as_a_sidebar(theme_name):
    qss = role_stylesheet(get_theme(theme_name))
    assert "QListWidget#settingsNav" in qss
    assert "QListWidget#settingsNav::item:selected" in qss
```

- [ ] **Step 7: Full gate and commit**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
git add gui/settings/window.py gui/theme_manager.py tests/test_settings_nav.py tests/test_theme_button_roles.py
git commit -m "feat(settings): sidebar-styled nav that remembers the last page"
```

---

### Task 8: Refresh the knowledge graph

Required by this repo's `CLAUDE.md`: a stale graph returns wrong answers about `shared/` ownership and theme delegation silently, with no error.

**Files:** none tracked — `graphify-out/` is the tool's own output.

- [ ] **Step 1: Run it**

```bash
graphify update .
```

- [ ] **Step 2: Commit if the output is tracked**

```bash
git status --short graphify-out/
```

If `graphify-out/` shows changes and is not gitignored, commit them:

```bash
git add graphify-out/
git commit -m "chore: refresh knowledge graph after Track 4"
```

If it is gitignored, there is nothing to commit — say so and move on.

---

## Verification

Before the branch is considered done:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Both must be clean, and the pytest count must be **higher** than the 498 that PR #272 left — this plan adds roughly 20 tests across four new files. A count that did not move means a test file is not being collected.

## What this plan deliberately does not do

Carried from the spec so an executor does not "helpfully" add them:

- **Client Profile stays its own dialog.** Open question for the user; see the spec's reasoning. Do not fold `ClientSettingsDialog` into the Hub.
- **`GroupsManagementDialog` stays where it is.** It has no `client_id`.
- **The repeating-item `QGroupBox`es in `rules.py` / `packing_lists.py` / `stock_exports.py` stay.** They are item containers, not titled form sections. `weight.py`'s "Quick Add" box also stays.
- **No button role outside `gui/settings/`.** The mechanism is app-wide; the application of it is not.
- **`shared/theme.py` is not edited.** Ever, in this repo.
