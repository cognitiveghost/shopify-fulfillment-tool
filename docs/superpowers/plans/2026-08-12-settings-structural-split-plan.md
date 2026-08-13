# Settings Structural Split (Phase 6 Track C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `gui/settings_window_pyside.py` (3593 lines) into a `gui/settings/` package of panel objects with a uniform `collect()`/`validate()` contract, so UI Design System Track 4 has module boundaries to build a Settings Hub on.

**Architecture:** Each of the nine settings pages becomes a `SettingsPage` (a `QWidget` subclass) in its own module. `SettingsWindow` keeps only the shell — left-nav, `QStackedWidget`, and save orchestration — and on save validates then collects from each page, merging into `config_data` before the single existing background `save_shopify_config` write. The migration is **incremental**: the shell keeps a `self._pages` list and each task moves exactly one page out, deleting its inline block from `save_settings()` in the same commit. The test suite is green at every commit.

**Tech Stack:** Python 3.14, PySide6, pytest (offscreen QPA), ruff.

**Spec:** `docs/superpowers/specs/2026-08-12-settings-structural-split-design.md`

## Global Constraints

- **Python is not on `PATH`.** Always use `.venv/bin/python` and `.venv/bin/ruff`. Run `./scripts/setup_venv.sh` first in a fresh worktree.
- **Test gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` — baseline is **468 passing**. Never let it drop.
- **Lint gate:** `.venv/bin/ruff check . --exclude shared`
- **Never edit anything under `shared/`** — one-way synced from `../packing-tool`.
- **No hardcoded colors.** Use `get_theme_manager().get_current_theme()` tokens. This plan moves code; it does not introduce new styling.
- **No behavior or visual change** except the three renames in Task 11. Every page must look and act exactly as before.
- **No direct commits to `main`.** Work on branch `worktree-settings-split`; PR only.
- **Run `graphify update .`** after the implementation is complete.
- This plan is **resumable across sessions** — tasks are independently committable and ordered so that stopping after any task leaves a working tree.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `gui/settings/__init__.py` | Re-export `SettingsWindow` |
| `gui/settings/base.py` | `SettingsPage` — the `collect()`/`validate()` contract |
| `gui/settings/fields.py` | Field/operator constants + the shared filter-row builder |
| `gui/settings/general.py` | `GeneralPage` |
| `gui/settings/packing_lists.py` | `PackingListsPage` |
| `gui/settings/stock_exports.py` | `StockExportsPage` |
| `gui/settings/mappings.py` | `MappingsPage` |
| `gui/settings/sets.py` | `SetsPage` + `SetEditorDialog` |
| `gui/settings/weight.py` | `WeightPage` |
| `gui/settings/rules.py` | `RulesPage` |
| `gui/settings/window.py` | `SettingsWindow` shell |
| `shopify_tool/profile_migrations.py` | The six `_migrate_*` functions |
| `tests/test_settings_roundtrip.py` | Characterization test (the safety net) |
| `tests/test_client_profile_update.py` | Lost-update regression test |

**Deleted:** `gui/settings_window_pyside.py`, `gui/profile_manager_dialog.py`

**Modified:** `gui/actions_handler.py`, `gui/ui_manager.py`, `gui/client_settings_dialog.py`, `shopify_tool/profile_manager.py`, `tests/test_settings_window_weight_quick_add.py`

---

### Task 1: Characterization test — the safety net

Nothing moves until this is green against the **pre-split** code. A characterization test that has never passed on the old implementation proves nothing.

**Files:**
- Test: `tests/test_settings_roundtrip.py` (create)

**Interfaces:**
- Consumes: `gui.settings_window_pyside.SettingsWindow` (current location)
- Produces: `settings_fixture_config()` — a dict fixture exercising every config section. Later tasks re-import nothing from here; the test file is self-contained.

**Critical gotchas, all verified by probe on 2026-08-12 — ignore any of them and this test hangs rather than fails:**

1. `save_settings()` shows a **modal** `QMessageBox.warning` on mapping-validation failure and returns early. Unstubbed, a headless run blocks forever. Stub all four static methods.
2. `save_settings()` ends with `Worker(self.profile_manager.save_shopify_config, ...)`. A `None` profile_manager raises inside the broad `except Exception` and surfaces as another modal. Pass a `Mock`.
3. Column mappings are stored `{csv_column: internal_name}`. Orders **requires** `Order_Number`, `SKU`, `Quantity`, `Shipping_Method`; stock **requires** `SKU`, `Stock`. Miss one and validation aborts before six of seven pages are collected — the test would pass while proving almost nothing.
4. `weight_config` uses `length_cm` / `width_cm` / `height_cm` (not `l`/`w`/`h`), and boxes carry no `weight` key.

- [ ] **Step 1: Write the characterization test**

```python
"""Characterization test for SettingsWindow's config round-trip.

This is the safety net for the Track C structural split: it asserts that
building the window from a config and immediately saving returns that same
config. If a page extraction drops or renames a field, this fails.

Kept deliberately blunt -- it asserts on whole config sections rather than
individual widgets, so it keeps working as the pages move into gui/settings/.
"""
import copy
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.settings_window_pyside import SettingsWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_modals(monkeypatch):
    """Fail loudly instead of blocking forever.

    save_settings() reports validation failures through modal QMessageBox
    calls and returns early. Under the offscreen QPA platform an unstubbed
    modal hangs the test run, so every popup is recorded and dismissed.
    """
    seen = []
    for name in ("warning", "critical", "information", "question"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: seen.append((_n, a[1:3]))),
        )
    return seen


def settings_fixture_config():
    """A config touching every section save_settings() writes."""
    return {
        "settings": {
            "stock_csv_delimiter": ";",
            "orders_csv_delimiter": ",",
            "low_stock_threshold": 5,
            "repeat_detection_days": 30,
        },
        "rules": [
            {
                "name": "Flag big orders",
                "priority": 1,
                "level": "order",
                "steps": [
                    {
                        "conditions": [
                            {"field": "item_count", "operator": "is greater than", "value": "5"}
                        ],
                        "match": "ALL",
                        "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                    }
                ],
            }
        ],
        "packing_list_configs": [
            {
                "name": "Main",
                "output_filename": "main.xlsx",
                "filters": [{"field": "SKU", "operator": "contains", "value": "AB"}],
                "exclude_skus": ["X1", "X2"],
            }
        ],
        "stock_export_configs": [
            {
                "name": "Daily",
                "output_filename": "daily.csv",
                "filters": [{"field": "Tags", "operator": "==", "value": "hot"}],
            }
        ],
        # v2 mappings are {csv_column: internal_name}. Every required internal
        # field must appear or save_settings() aborts at validation.
        "column_mappings": {
            "version": 2,
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Shipping Method": "Shipping_Method",
                "Lineitem name": "Product_Name",
            },
            "stock": {"Article": "SKU", "Available": "Stock"},
        },
        "courier_mappings": {
            "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False}
        },
        "set_decoders": {},
        "weight_config": {
            "volumetric_divisor": 5000,
            "products": {
                "SKU1": {
                    "name": "Widget",
                    "length_cm": 10.0,
                    "width_cm": 5.0,
                    "height_cm": 2.0,
                    "no_packaging": False,
                }
            },
            "boxes": [
                {"name": "Small", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}
            ],
        },
        "tag_categories": {"version": 2, "categories": {}},
    }


@pytest.fixture
def started_workers(monkeypatch):
    """Intercept the background save instead of letting it run.

    save_settings() hands a Worker to QThreadPool.globalInstance().start().
    Left alone that really runs, on a real thread, racing the assertions and
    delivering a success QMessageBox through queued signals. Capturing the
    worker keeps the test deterministic and still proves the save was reached.
    """
    started = []
    # NOTE: after Task 10 this target becomes "gui.settings.window.QThreadPool".
    monkeypatch.setattr(
        "gui.settings_window_pyside.QThreadPool",
        type("Pool", (), {
            "globalInstance": staticmethod(
                lambda: type("P", (), {"start": staticmethod(started.append)})()
            )
        }),
    )
    return started


@pytest.fixture
def window(qapp, no_modals, started_workers):
    """A real SettingsWindow with the background save intercepted."""
    win = SettingsWindow(
        client_id="M",
        client_config=settings_fixture_config(),
        profile_manager=Mock(),
    )
    yield win
    win.deleteLater()


def test_window_registers_every_page(window):
    assert list(window._page_index_by_name) == [
        "General", "Rules", "Packing Lists", "Stock Exports", "Mappings",
        "Sets", "Weight", "Tag Categories", "Column Config",
    ]


def test_save_round_trips_every_config_section(window, no_modals):
    """Build from a config, save, get the same config back."""
    before = copy.deepcopy(window.config_data)

    window.save_settings()

    assert no_modals == [], f"save_settings() reported a problem: {no_modals}"
    for section in sorted(before):
        assert window.config_data[section] == before[section], (
            f"section {section!r} did not survive the round-trip"
        )


def test_save_reaches_the_background_write(window, started_workers):
    """Guards the four gotchas above: had validation aborted early,
    save_settings() would have returned before queuing any worker."""
    window.save_settings()
    assert len(started_workers) == 1
    assert window._is_saving is True
```

- [ ] **Step 2: Run it and confirm it passes on the pre-split code**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -v
```

Expected: 3 passed. **If any test fails here, stop and investigate** — a red net before any refactoring means the fixture is wrong, and fixing it later would mask a real regression.

This exact fixture and config were run against the pre-split code on 2026-08-12 and produced: all nine pages registered, zero modals, one worker queued with `_is_saving` true, and **every one of the nine config sections round-tripping byte-identical**. If your run differs, the transcription drifted from the plan — not the codebase.

- [ ] **Step 3: Run the full suite and lint**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

Expected: 471 passed (468 + 3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_settings_roundtrip.py
git commit -m "test(settings): characterize SettingsWindow config round-trip

Safety net for the Track C structural split. Verified green against the
pre-split code before anything moves."
```

---

### Task 2: Package skeleton — `SettingsPage` and shared fields

Creates the package and moves the constants. No page moves yet; `settings_window_pyside.py` imports them back so behavior is identical.

**Files:**
- Create: `gui/settings/__init__.py`, `gui/settings/base.py`, `gui/settings/fields.py`
- Modify: `gui/settings_window_pyside.py:71-129` (delete the constant blocks), `:36-41` (add import)

**Interfaces:**
- Produces:
  - `SettingsPage(QWidget)` with `collect() -> dict` and `validate() -> tuple[bool, list[str]]`
  - `fields.FILTERABLE_COLUMNS`, `FILTER_OPERATORS`, `ORDER_LEVEL_FIELDS`, `CONDITION_FIELDS`, `CONDITION_OPERATORS`, `ACTION_TYPES` — all `list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_page_contract.py
from PySide6.QtWidgets import QApplication

from gui.settings.base import SettingsPage


def test_settings_page_defaults_are_inert():
    """A page that owns no config contributes nothing and blocks nothing."""
    QApplication.instance() or QApplication([])
    page = SettingsPage()
    assert page.collect() == {}
    assert page.validate() == (True, [])
```

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_contract.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'gui.settings'`

- [ ] **Step 3: Create the package**

`gui/settings/__init__.py`:

```python
"""Settings window and its pages.

The window (window.py) owns the left-nav, the page stack and saving; each
page module owns one settings surface and exposes it through SettingsPage.
"""
```

`gui/settings/base.py`:

```python
"""The contract between SettingsWindow and its pages."""

from PySide6.QtWidgets import QWidget


class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. Pages that
    persist their own data immediately (Sets, Column Config) inherit both
    defaults and contribute nothing to the window's single write.
    """

    def collect(self) -> dict:
        """The config keys this page owns, merged into config_data on save."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). A False here blocks the save."""
        return True, []
```

- [ ] **Step 4: Move the constants into `gui/settings/fields.py`**

Cut lines 71–129 of `gui/settings_window_pyside.py` (the `FILTERABLE_COLUMNS` through `ACTION_TYPES` class attributes) into module-level constants. Drop the `ClassVar` annotations — they are module constants now:

```python
"""Field and operator vocabularies shared by the settings pages.

Imports nothing from this package: pages import from here, never the
reverse, so there is no cycle back through window.py.
"""

FILTERABLE_COLUMNS: list[str] = [
    "Order_Number",
    "Order_Type",
    "SKU",
    "Product_Name",
    "Stock_Alert",
    "Order_Fulfillment_Status",
    "Shipping_Provider",
    "Destination_Country",
    "Tags",
    "System_note",
    "Status_Note",
    "Total Price",
]

FILTER_OPERATORS: list[str] = ["==", "!=", "in", "not in", "contains"]

# Order-level fields are grouped first, with the separator rows the combo
# boxes render as non-selectable headers.
ORDER_LEVEL_FIELDS: list[str] = [
    "--- ORDER-LEVEL FIELDS ---",
    "item_count",
    "total_quantity",
    "has_sku",
    "Has_SKU",
    "--- ARTICLE-LEVEL FIELDS ---",
]

CONDITION_FIELDS: list[str] = ORDER_LEVEL_FIELDS + FILTERABLE_COLUMNS

CONDITION_OPERATORS: list[str] = [
    "equals",
    "does not equal",
    "contains",
    "does not contain",
    "is greater than",
    "is less than",
    "is greater than or equal",
    "is less than or equal",
    "starts with",
    "ends with",
    "is empty",
    "is not empty",
    "in list",
    "not in list",
    "between",
    "not between",
    "date before",
    "date after",
    "date equals",
    "matches regex",
    "does not match regex",
]

ACTION_TYPES: list[str] = [
    "ADD_TAG",
    "ADD_ORDER_TAG",
    "ADD_INTERNAL_TAG",
    "SET_STATUS",
    "COPY_FIELD",
    "CALCULATE",
    "SET_MULTI_TAGS",
    "ALERT_NOTIFICATION",
    "ADD_PRODUCT",
]
```

Then in `gui/settings_window_pyside.py`, re-bind them as class attributes so every existing `self.FILTERABLE_COLUMNS` reference keeps working untouched:

```python
from gui.settings.fields import (
    ACTION_TYPES,
    CONDITION_FIELDS,
    CONDITION_OPERATORS,
    FILTER_OPERATORS,
    FILTERABLE_COLUMNS,
    ORDER_LEVEL_FIELDS,
)

class SettingsWindow(QDialog):
    FILTERABLE_COLUMNS: ClassVar[list[str]] = FILTERABLE_COLUMNS
    FILTER_OPERATORS: ClassVar[list[str]] = FILTER_OPERATORS
    ORDER_LEVEL_FIELDS: ClassVar[list[str]] = ORDER_LEVEL_FIELDS
    CONDITION_FIELDS: ClassVar[list[str]] = CONDITION_FIELDS
    CONDITION_OPERATORS: ClassVar[list[str]] = CONDITION_OPERATORS
    ACTION_TYPES: ClassVar[list[str]] = ACTION_TYPES
```

- [ ] **Step 5: Run the tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

Expected: 472 passed. The round-trip test proves the constants still drive identical widgets.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/ gui/settings_window_pyside.py tests/test_settings_page_contract.py
git commit -m "refactor(settings): add gui/settings package with SettingsPage and shared fields"
```

---

### Task 3: Extract the General page — establishes the pattern

The smallest page (85 lines). Every later extraction follows this shape exactly, so get it right here.

**Files:**
- Create: `gui/settings/general.py`
- Modify: `gui/settings_window_pyside.py` — delete `create_general_tab` (432–515), delete the General block in `save_settings` (3040–3043), add page wiring

**Interfaces:**
- Consumes: `gui.settings.base.SettingsPage`
- Produces: `GeneralPage(settings: dict, parent=None)`; `collect() -> {"settings": {...}}` carrying `stock_csv_delimiter`, `orders_csv_delimiter`, `low_stock_threshold`, `repeat_detection_days`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_page_general.py
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.general import GeneralPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_general_page_round_trips_its_settings(qapp):
    settings = {
        "stock_csv_delimiter": "|",
        "orders_csv_delimiter": ";",
        "low_stock_threshold": 12,
        "repeat_detection_days": 30,
    }
    page = GeneralPage(settings)
    assert page.collect() == {"settings": settings}


def test_general_page_falls_back_to_defaults(qapp):
    page = GeneralPage({})
    assert page.collect()["settings"] == {
        "stock_csv_delimiter": ";",
        "orders_csv_delimiter": ",",
        "low_stock_threshold": 5,
        "repeat_detection_days": 1,
    }
```

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_general.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'gui.settings.general'`

- [ ] **Step 3: Write `gui/settings/general.py`**

Move the body of `create_general_tab` (lines 432–513) verbatim, swapping `self.config_data.get("settings", {})` for the injected `settings` dict, and `main_layout` onto the page itself. The `collect()` body is lifted from `save_settings` lines 3040–3043.

```python
"""General settings: CSV delimiters and analysis thresholds."""

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from gui.settings.base import SettingsPage


class GeneralPage(SettingsPage):
    """Delimiters and thresholds, stored under config_data["settings"]."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)

        settings_box = QGroupBox("General Settings")
        settings_layout = QFormLayout(settings_box)

        delimiter_label = QLabel("Stock CSV Delimiter:")
        self.stock_delimiter_edit = QLineEdit(settings.get("stock_csv_delimiter", ";"))
        self.stock_delimiter_edit.setMaximumWidth(100)
        self.stock_delimiter_edit.setToolTip(
            "Character used to separate columns in stock CSV file.\n\n"
            "Common values:\n"
            "  • Semicolon (;) - for exports from local warehouse\n"
            "  • Comma (,) - for Shopify exports\n\n"
            "Make sure this matches your stock CSV file format."
        )
        settings_layout.addRow(delimiter_label, self.stock_delimiter_edit)

        orders_delimiter_label = QLabel("Orders CSV Delimiter:")
        self.orders_delimiter_edit = QLineEdit(settings.get("orders_csv_delimiter", ","))
        self.orders_delimiter_edit.setMaximumWidth(100)
        self.orders_delimiter_edit.setPlaceholderText(",")
        self.orders_delimiter_edit.setToolTip(
            "Character used to separate columns in orders CSV file.\n\n"
            "Common values:\n"
            "  • Comma (,) - standard Shopify exports\n"
            "  • Semicolon (;) - European Excel exports\n"
            "  • Tab (\\t) - tab-separated files\n\n"
            "The tool will auto-detect delimiter when you select a file,\n"
            "but you can override it here if needed."
        )
        settings_layout.addRow(orders_delimiter_label, self.orders_delimiter_edit)

        threshold_label = QLabel("Low Stock Threshold:")
        self.low_stock_edit = QLineEdit(str(settings.get("low_stock_threshold", 5)))
        self.low_stock_edit.setMaximumWidth(100)
        self.low_stock_edit.setToolTip(
            "Trigger stock alerts when quantity falls below this number.\n\n"
            "Items with stock below this threshold will be marked in analysis."
        )
        settings_layout.addRow(threshold_label, self.low_stock_edit)

        repeat_days_label = QLabel("Repeat Detection Window (days):")
        self.repeat_days_input = QSpinBox()
        self.repeat_days_input.setMinimum(1)
        self.repeat_days_input.setMaximum(365)
        self.repeat_days_input.setValue(settings.get("repeat_detection_days", 1))
        self.repeat_days_input.setToolTip(
            "Orders fulfilled within this many days are marked as 'Repeat'.\n"
            "Default: 1 day (only yesterday's fulfillments)\n"
            "Increase for longer detection window (e.g., 7 days, 30 days)"
        )
        settings_layout.addRow(repeat_days_label, self.repeat_days_input)

        main_layout.addWidget(settings_box)
        main_layout.addStretch()

    def collect(self) -> dict:
        return {
            "settings": {
                "stock_csv_delimiter": self.stock_delimiter_edit.text(),
                "orders_csv_delimiter": self.orders_delimiter_edit.text(),
                "low_stock_threshold": int(self.low_stock_edit.text()),
                "repeat_detection_days": self.repeat_days_input.value(),
            }
        }
```

**Watch the `settings` sub-dict merge.** `collect()` returns a whole `settings` dict, so the shell must merge one level deep or unrelated keys under `settings` would be dropped. Step 4 handles this.

- [ ] **Step 4: Wire the page into the shell**

In `SettingsWindow.__init__`, replace the `self.create_general_tab()` call:

```python
self._pages: list[SettingsPage] = []
...
self._add_page(GeneralPage(self.config_data.get("settings", {})), "General")
```

Add the registration helper next to `_add_settings_page`:

```python
def _add_page(self, page: SettingsPage, name: str) -> None:
    """Register an extracted SettingsPage. Tracked in _pages so save_settings
    validates and collects from it; _add_settings_page still handles the
    not-yet-extracted create_*_tab pages."""
    self._pages.append(page)
    self._add_settings_page(page, name)
```

At the top of `save_settings()`, replace the deleted General block (lines 3040–3043) with the loop that every later task reuses unchanged:

```python
# Extracted pages: validate first, then collect. Pages still living in
# create_*_tab methods are handled by the inline blocks below until
# they are moved out.
for page in self._pages:
    ok, errors = page.validate()
    if not ok:
        QMessageBox.warning(self, "Invalid Settings", "\n".join(errors))
        return

for page in self._pages:
    for key, value in page.collect().items():
        if isinstance(value, dict) and isinstance(self.config_data.get(key), dict):
            self.config_data[key].update(value)
        else:
            self.config_data[key] = value
```

Delete `create_general_tab` entirely.

- [ ] **Step 5: Run the tests**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

Expected: 474 passed. The round-trip test is what proves the General page still writes the same four keys.

- [ ] **Step 6: Commit**

```bash
git add gui/settings/general.py gui/settings_window_pyside.py tests/test_settings_page_general.py
git commit -m "refactor(settings): extract GeneralPage"
```

---

### Tasks 4–9: Extract the remaining pages

**Every one of these follows Task 3 exactly**: create the module, move the `create_*_tab` body verbatim into `__init__`, move the matching `save_settings` block into `collect()`, move any validation into `validate()`, replace the `create_*_tab()` call with `self._add_page(...)`, delete the old method and its inline save block, run the gate, commit.

The shell's validate/collect loop from Task 3 Step 4 is written once and never changes.

Do them **in this order** — ascending risk, so the net is well exercised before Rules:

| Task | Page | Source lines | `save_settings` block | Constructor | `collect()` returns |
|---|---|---|---|---|---|
| 4 | `StockExportsPage` | 1669–1729 | 3154–3178 | `(configs: list, analysis_df, parent=None)` | `{"stock_export_configs": [...]}` |
| 5 | `PackingListsPage` | 1509–1572 | 3118–3149 | `(configs: list, analysis_df, parent=None)` | `{"packing_list_configs": [...]}` |
| 6 | `MappingsPage` | 1729–1892 | 3184–3233 | `(column_mappings: dict, courier_mappings: dict, parent=None)` | `{"column_mappings": {...}, "courier_mappings": {...}}` |
| 7 | `SetsPage` | 1892–2180, + `SetEditorDialog` 3379–3527 | *(none — self-saving)* | `(client_id: str, profile_manager, parent=None)` | `{}` (inherited) |
| 8 | `WeightPage` | 2180–3029 | 3238 | `(weight_config: dict, parent=None)` | `{"weight_config": {...}}` |
| 9 | `RulesPage` | 517–1509 | 3048–3113 | `(rules: list, analysis_df, parent=None)` | `{"rules": [...]}` |

Task-specific notes:

- **Task 4 & 5 (`StockExportsPage`, `PackingListsPage`)** share `add_filter_row` (1572–1626) and `_on_filter_criteria_changed` (1626–1669). Move both into `gui/settings/fields.py` as module-level functions taking the widgets they need, in **Task 4**, and have Task 5 import them. They also need `analysis_df` for `get_unique_column_values` dropdown population — pass it in, do not reach for a parent.
- **Task 6 (`MappingsPage`)** is the only page with real `validate()` content today. Move both mapping checks (3184–3200) into it, returning `(False, ["Orders column mapping is invalid:\n..."])` — the shell's loop shows the message, so drop the two inline `QMessageBox.warning` calls. Its required-field lists (`orders_required`, `stock_required` at 1747 and 1772) move with it.
- **Task 7 (`SetsPage`)** persists through `profile_manager.add_set`/`delete_set` immediately and contributes nothing to the save. It inherits both defaults — do **not** give it a `collect()`. `SetEditorDialog` moves into the same module; it is used only from here.
- **Task 8 (`WeightPage`)** is 850 lines with a nested `QTabWidget` (Products / Boxes) and eight CSV import/export methods. Move it wholesale — resist splitting Products and Boxes into separate pages, which would be a behavior change. `_weight_collect_config()` becomes `collect()`. **`tests/test_settings_window_weight_quick_add.py` must be updated in this task**: repoint its import at `gui.settings.weight.WeightPage`, and **delete the false claim** in its docstring that `SettingsWindow.__init__` "hangs under the offscreen QPA platform" — it does not (verified; see the spec). Its `__new__`-based construction can stay.
- **Task 9 (`RulesPage`)** is the biggest (990 lines: `add_rule_widget`, `_add_step_widget`, `add_condition_row`, `add_action_row`, the priority/reorder helpers, `_test_rule`, `_build_rule_config_from_widgets`, and the condition-validation helpers). All of it is self-contained once `fields.py` supplies the vocabularies. It owns `self.rule_widgets` and `self.rules_layout`. `_test_rule` opens `RuleTestDialog` — keep that import local to the module.

For each task:

- [ ] **Step 1: Write a page-level test** mirroring `tests/test_settings_page_general.py` — construct the page from a fixture slice, assert `collect()` returns it unchanged. For `SetsPage`, assert `collect() == {}` instead.
- [ ] **Step 2: Run it and watch it fail** with `ModuleNotFoundError`.
- [ ] **Step 3: Create the module** by moving the code verbatim.
- [ ] **Step 4: Wire it in** — `self._add_page(...)`, delete the old method and its inline save block.
- [ ] **Step 5: Run the gate.**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

Expected: previous count + the new page test(s), never fewer. The round-trip test failing means a field was dropped in the move — fix it before committing rather than adjusting the test.

- [ ] **Step 6: Commit** as `refactor(settings): extract <PageName>`.

---

### Task 10: Move the shell and delete the old module

**Files:**
- Create: `gui/settings/window.py`
- Delete: `gui/settings_window_pyside.py`
- Modify: `gui/settings/__init__.py`, `gui/actions_handler.py:9`, `tests/test_settings_roundtrip.py`, `tests/test_settings_window_weight_quick_add.py`

By now `settings_window_pyside.py` holds only the shell: `__init__`, `_add_settings_page`, `_add_page`, `_build_settings_nav`, `_on_settings_nav_changed`, `SETTINGS_NAV_GROUPS`, `create_tag_categories_tab`, `create_column_config_tab`, `reject`, `save_settings`, `_on_save_settings_result`, `_on_save_settings_error`.

- [ ] **Step 1: Move the file**

```bash
git mv gui/settings_window_pyside.py gui/settings/window.py
```

- [ ] **Step 2: Convert the last two pages to the contract**

`create_tag_categories_tab` and `create_column_config_tab` stay as methods (they wrap panels that already exist elsewhere), but route through the contract so the shell has no special cases left.

For Tag Categories, wrap `TagCategoriesPanel` in a thin adapter at the bottom of `gui/settings/window.py`:

```python
class _TagCategoriesPage(SettingsPage):
    """Adapter: TagCategoriesPanel already has the right shape under
    different method names, and is used standalone elsewhere -- so wrap it
    rather than rename its public API."""

    def __init__(self, tag_categories: dict, parent=None):
        super().__init__(parent)
        from gui.tag_categories_dialog import TagCategoriesPanel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        self.panel = TagCategoriesPanel(tag_categories, parent=self)
        layout.addWidget(self.panel)

    def collect(self) -> dict:
        return {"tag_categories": self.panel.get_categories()}

    def validate(self) -> tuple[bool, list[str]]:
        ok, errors = self.panel.validate_categories()
        if ok:
            return True, []
        return False, ["Tag Categories validation errors:", *[f"- {e}" for e in errors]]
```

Column Config self-saves through `table_config_manager` and contributes nothing, so its adapter inherits both defaults. **Pass the main window in explicitly** rather than calling `self.parent()` from inside a package module (spec risk note):

```python
class _ColumnConfigPage(SettingsPage):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        if main_window is None or not hasattr(main_window, "table_config_manager"):
            layout.addWidget(QLabel("Column configuration is not available in this context."))
            return

        from gui.column_config_dialog import ColumnConfigPanel

        layout.setContentsMargins(10, 10, 10, 10)
        header_label = QLabel("Column Configuration")
        header_label.setStyleSheet(font_css("heading"))
        layout.addWidget(header_label)

        theme = get_theme_manager().get_current_theme()
        help_text = QLabel(
            "Configure which columns are visible in the analysis table, "
            "their order, and saved views."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            f"color: {theme.text_secondary}; font-style: italic; margin-bottom: 6px;"
        )
        layout.addWidget(help_text)

        self.panel = ColumnConfigPanel(
            main_window.table_config_manager, main_window=main_window, parent=self
        )
        layout.addWidget(self.panel)
```

Register both via `self._add_page(...)`, delete `create_tag_categories_tab`, `create_column_config_tab`, the now-unused `_add_settings_page`, and every remaining inline block in `save_settings()`. `save_settings()` should now be just: the validate loop, the collect loop, and the background write.

- [ ] **Step 3: Update the importers**

`gui/settings/__init__.py`:

```python
from gui.settings.window import SettingsWindow

__all__ = ["SettingsWindow"]
```

`gui/actions_handler.py:9` — `from gui.settings_window_pyside import SettingsWindow` becomes `from gui.settings import SettingsWindow`. Same in both test files. Delete the `if __name__ == "__main__":` demo block at the end of `window.py` (lines 3585+) — it constructs a `SettingsWindow` with a dummy config and is superseded by the round-trip test.

- [ ] **Step 4: Confirm nothing still references the old path**

```bash
grep -rn "settings_window_pyside" --include=*.py . || echo "clean"
```

Expected: `clean`

- [ ] **Step 5: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

- [ ] **Step 6: Commit**

```bash
git add -A gui/ tests/
git commit -m "refactor(settings): move the shell to gui/settings/window.py

settings_window_pyside.py is gone; save_settings() is now just validate,
collect, write."
```

---

### Task 11: Delete dead code and fix the swapped names

**Files:**
- Delete: `gui/profile_manager_dialog.py`
- Modify: `gui/client_settings_dialog.py:368` (title), `:410-411` + `:524-539` (Advanced tab), `gui/ui_manager.py:821-822`, `:1177-1181`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_entry_points.py
"""Guards the naming fix: the button label and the dialog title must not
both say "Client Settings" again. They named different windows, which is
the confusion Phase 6 flagged."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_profile_manager_dialog_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import gui.profile_manager_dialog  # noqa: F401


def test_client_profile_dialog_has_no_placeholder_advanced_tab(qapp, monkeypatch):
    from gui.client_settings_dialog import ClientSettingsDialog

    assert not hasattr(ClientSettingsDialog, "_create_advanced_tab")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_entry_points.py -v
```

Expected: both FAIL — the module still imports and the method still exists.

- [ ] **Step 3: Delete the dead code**

```bash
git rm gui/profile_manager_dialog.py
```

Nothing constructs it, and it calls `self.parent.create_profile()` / `self.parent.active_profile_name`, neither of which exists on `MainWindow` — it would raise `AttributeError` on open.

In `gui/client_settings_dialog.py`, delete `_create_advanced_tab` (524–539) and its two registration lines (410–411). Its entire content is a label telling the user to go to the other window.

- [ ] **Step 4: Apply the renames**

| File:line | From | To |
|---|---|---|
| `client_settings_dialog.py:368` | `f"Client Settings - CLIENT_{client_id}"` | `f"Client Profile - CLIENT_{client_id}"` |
| `ui_manager.py:821` | `QPushButton("Client Settings")` | `QPushButton("Settings")` |
| `ui_manager.py:822` | `"Open the settings window"` | `"Open settings for the active client"` |
| `ui_manager.py:1177` | `QPushButton("Client Settings")` | `QPushButton("Settings")` |
| `ui_manager.py:1179-1181` | `"Open the settings window for the active client"` | `"Open settings for the active client"` |

Leave the `ClientSettingsDialog` class name alone — Track 4 will fold this dialog into the Hub as a "Client Profile" nav page, and renaming the class now is churn that gets redone.

- [ ] **Step 5: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

- [ ] **Step 6: Commit**

```bash
git add -A gui/ tests/
git commit -m "refactor(settings): delete dead ProfileManagerDialog, fix swapped window names

The button labeled 'Client Settings' opened the window titled 'Settings',
while the window titled 'Client Settings' was reached from the sidebar.
Buttons are now 'Settings'; the sidebar dialog is 'Client Profile'."
```

---

### Task 12: Extract the profile_manager migrations

**Files:**
- Create: `shopify_tool/profile_migrations.py`
- Modify: `shopify_tool/profile_manager.py:347-745` (delete), `:907`, `:976-989` (call sites)

The six `_migrate_*` methods are ~400 self-contained lines on the largest backend file (1872 lines). None of them touch `self` beyond `save_*_config` for logging context.

**Interfaces:**
- Produces, each returning `True` when it changed `config`:
  - `migrate_column_mappings_v1_to_v2(client_id: str, config: dict) -> bool`
  - `migrate_add_tag_categories(client_id: str, config: dict) -> bool`
  - `migrate_tag_categories_v1_to_v2(client_id: str, config: dict) -> bool`
  - `migrate_delimiter_config_v1_to_v2(client_id: str, config: dict) -> bool`
  - `migrate_add_weight_config(client_id: str, config: dict) -> bool`
  - `migrate_add_inventory_memory(client_id: str, config: dict) -> bool`
  - `migrate_add_ui_settings(client_id: str, config: dict) -> bool`

- [ ] **Step 1: Confirm the existing coverage is the test**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_profile_manager.py -v
```

These already exercise the migration paths through `load_*_config`. They are the regression net for this task — no new test needed, but they must stay green.

- [ ] **Step 2: Move the methods**

Cut lines 347–745 into `shopify_tool/profile_migrations.py` as module-level functions, dropping the leading underscore and the `self` parameter. Keep every log message and branch identical.

```python
"""Config migrations applied on load.

Split out of profile_manager.py, which was the largest backend file in the
repo. Each function mutates `config` in place and returns True when it
changed something -- the caller saves in that case.
"""

import logging

logger = logging.getLogger(__name__)


def migrate_column_mappings_v1_to_v2(client_id: str, config: dict) -> bool:
    ...  # body moved verbatim from ProfileManager._migrate_column_mappings_v1_to_v2
```

- [ ] **Step 3: Update the call sites**

In `load_shopify_config` (976–989) and `load_client_config` (907), call the imported functions instead of `self._migrate_*`. The `if any(...)` / save-and-return structure is unchanged.

- [ ] **Step 4: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/
git commit -m "refactor(profile_manager): extract config migrations to profile_migrations.py"
```

---

### Task 13: Fix the lost update on client_config.json

The one real bug in this track. `ClientSettingsDialog` loads all of `client_config.json` at open and writes all of it at save, so any `update_ui_settings()` landing in between — the sidebar's pin toggle or group move, which write the same file — is silently reverted.

**Files:**
- Modify: `shopify_tool/profile_manager.py` (add `update_client_profile` next to `update_ui_settings`, ~1620), `gui/client_settings_dialog.py:383` (drop unused read), `:608-637` (use the new method)
- Test: `tests/test_client_profile_update.py` (create)

**Interfaces:**
- Produces: `ProfileManager.update_client_profile(client_id: str, name: str | None = None, ui_settings: dict | None = None) -> bool`

- [ ] **Step 1: Write the failing test**

```python
"""Regression: a sidebar pin toggle during an open Client Profile dialog
must survive that dialog's save."""
import pytest

from shopify_tool.profile_manager import ProfileManager


def test_update_client_profile_preserves_concurrent_ui_changes(profile_manager):
    # The dialog opens and reads the config it will later write back.
    stale = profile_manager.load_client_config("M")
    assert stale["ui_settings"]["is_pinned"] is False

    # Meanwhile the sidebar pins the client.
    profile_manager.update_ui_settings("M", {"is_pinned": True})

    # The dialog saves only the fields it owns.
    profile_manager.update_client_profile(
        "M", name="Renamed Co", ui_settings={"custom_color": "#123456"}
    )

    after = profile_manager.load_client_config("M")
    assert after["client_name"] == "Renamed Co"
    assert after["ui_settings"]["custom_color"] == "#123456"
    assert after["ui_settings"]["is_pinned"] is True, "sidebar pin was clobbered"


def test_update_client_profile_rejects_unknown_client(profile_manager):
    from shopify_tool.profile_manager import ProfileManagerError

    with pytest.raises(ProfileManagerError):
        profile_manager.update_client_profile("NOPE", name="x")
```

Reuse the `profile_manager` fixture from `tests/test_profile_manager.py` — check `tests/conftest.py` first and lift it there if it is currently local to that module.

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_client_profile_update.py -v
```

Expected: FAIL — `AttributeError: 'ProfileManager' object has no attribute 'update_client_profile'`

- [ ] **Step 3: Add the method**

Same load-merge-save shape as `update_ui_settings` (1578–1619), still one write:

```python
def update_client_profile(
    self,
    client_id: str,
    name: str | None = None,
    ui_settings: dict[str, Any] | None = None,
) -> bool:
    """Update only the client-profile fields the caller owns.

    Loads fresh, merges the supplied keys, saves once. Callers holding a
    config they read minutes ago must go through this rather than writing
    that config back wholesale -- otherwise a pin toggle or group move made
    in between is silently reverted.

    Args:
        client_id: Client ID
        name: New client_name, or None to leave it alone
        ui_settings: Partial ui_settings to merge, or None

    Returns:
        bool: True if saved successfully

    Raises:
        ProfileManagerError: If the client doesn't exist or the save fails
    """
    config = self.load_client_config(client_id)
    if config is None:
        raise ProfileManagerError(f"Client profile not found: CLIENT_{client_id}")

    if name is not None:
        config["client_name"] = name

    if ui_settings:
        config.setdefault("ui_settings", self._get_default_ui_settings())
        config["ui_settings"].update(ui_settings)

    return self.save_client_config(client_id, config)
```

- [ ] **Step 4: Point the dialog at it**

In `gui/client_settings_dialog.py`, replace the body of `_save_and_accept` (608–637) so the `Worker` calls the new method with only the five fields the dialog owns, instead of writing back `self.config`:

```python
badges_text = self.badges_input.text().strip()
badges = [b.strip() for b in badges_text.split(",") if b.strip()] if badges_text else []

self.save_button.setEnabled(False)
self.save_button.setText("Saving...")
self._is_saving = True

worker = Worker(
    self.profile_manager.update_client_profile,
    self.client_id,
    self.client_name_input.text().strip(),
    {
        "is_pinned": self.pin_checkbox.isChecked(),
        "group_id": self.group_combo.currentData(),
        "custom_color": self.current_color,
        "custom_badges": badges,
    },
)
```

Keep the `self._save_worker = worker` strong reference and its comment — that is load-bearing for this PySide6 build.

Also delete line 383, `self.shopify_config = self.profile_manager.load_shopify_config(client_id)`. It is assigned and never read — a wasted round-trip to the file server on every open.

- [ ] **Step 5: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/profile_manager.py gui/client_settings_dialog.py tests/test_client_profile_update.py
git commit -m "fix(profile_manager): stop the Client Profile dialog clobbering concurrent ui_settings

The dialog wrote back a whole config read at open time, reverting any
sidebar pin toggle or group move made while it was open. It now merges
only the five fields it owns, through update_client_profile()."
```

---

### Task 14: Repopulate the shopify config cache after a migration

**Files:**
- Modify: `shopify_tool/profile_manager.py:991-1002`

`load_shopify_config` returns at line 1002 after running a migration without writing `_config_cache`, so the very next call re-reads from the network share. `load_client_config` already handles this correctly at 913–921.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile_manager.py`:

```python
def test_shopify_config_is_cached_after_a_migration(profile_manager, monkeypatch):
    """A migrating load must leave the cache warm, like load_client_config does."""
    ProfileManager._config_cache.clear()
    profile_manager.load_shopify_config("M")  # runs migrations, caches (or not)

    reads = []
    real_open = open

    def counting_open(path, *a, **k):
        if str(path).endswith("shopify_config.json"):
            reads.append(path)
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", counting_open)
    profile_manager.load_shopify_config("M")
    assert reads == [], "second load re-read the file instead of using the cache"
```

Import `ProfileManager` at the top of the test module if it is not already imported.

- [ ] **Step 2: Run it to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_profile_manager.py::test_shopify_config_is_cached_after_a_migration -v
```

Expected: FAIL — the second load re-reads.

If it passes immediately, the fixture's config needs no migration; add a stale key (e.g. delete `weight_config`) so `migrate_add_weight_config` fires.

- [ ] **Step 3: Apply the fix**

Replace the early `return config` at line 1002 with the same re-stat that `load_client_config` uses:

```python
if (
    migrated_mappings
    or migrated_delimiters
    or migrated_tag_categories
    or migrated_tag_categories_v2
    or migrated_weight
    or migrated_inv_memory
):
    self.save_shopify_config(client_id, config)
    logger.info(f"Config migrations completed for CLIENT_{client_id}")
    # save_shopify_config() invalidates cache_key; re-stat so this call
    # still populates the cache with the post-migration mtime.
    try:
        current_mtime = config_path.stat().st_mtime
    except OSError:
        current_mtime = None

if current_mtime is not None:
    self._config_cache[cache_key] = (copy.deepcopy(config), current_mtime)

return config
```

- [ ] **Step 4: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/profile_manager.py tests/test_profile_manager.py
git commit -m "fix(profile_manager): cache shopify config after a migrating load"
```

---

### Task 15: Update the knowledge graph and finish

- [ ] **Step 1: Confirm the whole gate is green**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/ruff check . --exclude shared
```

Expected: well above the 468 baseline, zero failures, zero lint errors.

- [ ] **Step 2: Confirm the split actually landed**

```bash
wc -l gui/settings/*.py shopify_tool/profile_manager.py
grep -rn "settings_window_pyside" --include=*.py . || echo "clean"
```

Expected: no single file near 3593 lines; `profile_manager.py` around 1470; `clean`.

- [ ] **Step 3: Update the knowledge graph** (required by CLAUDE.md)

```bash
graphify update .
```

- [ ] **Step 4: Commit anything outstanding**

```bash
git add -A
git commit -m "chore: refresh knowledge graph after the settings split"
```

---

## Notes for the executor

- **If the round-trip test goes red mid-extraction, a field was dropped in the move.** Fix the extraction, never the assertion. That test is the entire reason this refactor is safe.
- **Do not "improve" code while moving it.** Rename nothing, reorder nothing, fix no lint nits inside a moved block. A pure move keeps the diff reviewable; cleanups belong to Track 5 once the Hub exists.
- **Import direction is one-way**: pages import `base.py` and `fields.py`; nothing imports `window.py`. Keep the `RuleTestDialog`, `TagCategoriesPanel` and `ColumnConfigPanel` imports function-local as they are today — they exist to break cycles.
- **This plan is resumable.** Each task commits independently and leaves the suite green, so stopping between tasks is safe and the next session picks up at the first unchecked box.
