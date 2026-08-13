# Mappings UI + Stock Lot-Column Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Stock CSV mapping able to hold `Expiry_Date` and `Batch` without a Save destroying them, and rebuild the mapping UI as two focused nav pages whose column inputs can be filled from a real CSV's headers.

**Architecture:** Seven tasks, defect-first. Tasks 1-4 are data-integrity and backend work that can be verified without looking at a pixel; tasks 5-7 rebuild the UI on top. The widget keeps its class name and public API throughout so each task leaves the suite green.

**Tech Stack:** PySide6, pandas, pytest. Windows-only in production, developed on Linux with `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-08-13-mappings-ui-design.md`

## Global Constraints

- **Run the gate before finishing:** `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared`. Baseline on this branch is **523 tests passing**.
- **Use `.venv/bin/python`**, never bare `python` or `python3` — neither is on PATH on this machine. `./scripts/setup_venv.sh` if `.venv` is missing.
- **Never hand-edit `shared/`.** Nothing in this plan touches it.
- **No hardcoded colors** in stylesheets — use `get_theme_manager().get_current_theme()` tokens. This change *removes* a `color: red`; it must not add one.
- **No UI calls from background threads.** Nothing in this plan is threaded.
- `Position` is **out of scope** by explicit user decision. Do not add it.
- Keep `_LOT_COLUMN_DEFAULTS` in `shopify_tool/analysis.py`. It is the back-compat path for configs that already lost their mapping.
- Internal field names are exact strings and are load-bearing: `Expiry_Date` and `Batch` are what `_build_fifo_lots()` looks for (`shopify_tool/analysis.py:96-97`). Not `Lot`, not `Expiry`.

---

### Task 1: `read_csv_headers()` in csv_utils

Backend helper the header-loading button (Task 7) needs. No Qt, so it is tested directly.

**Files:**
- Modify: `shopify_tool/csv_utils.py` (add after `detect_csv_delimiter`, which ends at line 121)
- Test: `tests/test_csv_utils.py`

**Interfaces:**
- Consumes: `detect_csv_delimiter(file_path, encoding) -> tuple[str, str]`, already in this module at line 30.
- Produces: `read_csv_headers(file_path: str, encoding: str = "utf-8-sig") -> list[str]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_csv_utils.py`:

```python
def test_read_csv_headers_semicolon_delimited(tmp_path):
    csv = tmp_path / "stock.csv"
    csv.write_text(
        "Артикул;Наличност;Годност;Партида\nSKU1;10;261230;L42\n",
        encoding="utf-8",
    )
    assert read_csv_headers(str(csv)) == ["Артикул", "Наличност", "Годност", "Партида"]


def test_read_csv_headers_comma_delimited(tmp_path):
    csv = tmp_path / "orders.csv"
    csv.write_text("Name,Lineitem sku,Lineitem quantity\n#1001,ABC,2\n", encoding="utf-8")
    assert read_csv_headers(str(csv)) == ["Name", "Lineitem sku", "Lineitem quantity"]


def test_read_csv_headers_does_not_read_rows(tmp_path):
    """nrows=0 keeps this cheap on a large stock export over a network share."""
    csv = tmp_path / "big.csv"
    rows = "\n".join(f"SKU{i};{i}" for i in range(5000))
    csv.write_text(f"Артикул;Наличност\n{rows}\n", encoding="utf-8")
    assert read_csv_headers(str(csv)) == ["Артикул", "Наличност"]
```

Add `read_csv_headers` to the existing import of `shopify_tool.csv_utils` at the top of the file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_csv_utils.py -k read_csv_headers -v`
Expected: FAIL — `ImportError: cannot import name 'read_csv_headers'`

- [ ] **Step 3: Write the implementation**

In `shopify_tool/csv_utils.py`, directly after `detect_csv_delimiter`:

```python
def read_csv_headers(file_path: str, encoding: str = 'utf-8-sig') -> list[str]:
    """Return a CSV's column names without loading any of its rows.

    Delimiter comes from detect_csv_delimiter's fallback chain rather than a
    configured value, so the settings pages that call this need no delimiter
    plumbing. nrows=0 reads the header line only, which matters on a large
    stock export sitting on a network share.

    Args:
        file_path: Path to the CSV file.
        encoding: File encoding (default: utf-8-sig).

    Returns:
        List of column names, in file order.
    """
    delimiter, _method = detect_csv_delimiter(file_path, encoding)
    return list(
        pd.read_csv(file_path, sep=delimiter, encoding=encoding, nrows=0).columns
    )
```

`pandas` is already imported in this module.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_csv_utils.py -v`
Expected: PASS, including the pre-existing cases.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/csv_utils.py tests/test_csv_utils.py
git commit -m "feat(csv): read_csv_headers() reads a CSV's header row only"
```

---

### Task 2: Stop dropping mappings the widget has no row for

The defect. `get_mappings()` can only emit internal names in `required_fields + optional_fields`, so anything else in the client's config is erased on Save.

**Files:**
- Modify: `gui/column_mapping_widget.py:170-188` (`get_mappings`)
- Modify: `tests/conftest.py:163` (fixture stock mapping)
- Test: `tests/test_settings_page_mappings.py`

**Interfaces:**
- Produces: `ColumnMappingWidget.get_mappings() -> dict` — unchanged signature, changed contract: entries whose internal name is not managed by this widget are carried through untouched.

- [ ] **Step 1: Widen the shared fixture so the existing guard can see the bug**

In `tests/conftest.py`, change line 163 from:

```python
            "stock": {"Article": "SKU", "Available": "Stock"},
```

to:

```python
            "stock": {
                "Article": "SKU",
                "Available": "Stock",
                "Годност": "Expiry_Date",
                "Партида": "Batch",
            },
```

`test_no_page_silently_drops_a_field` (`tests/test_settings_roundtrip.py:40`) already
compares each page's `collect()` to a pre-collect deepcopy. It never caught this because
the fixture had nothing droppable in it.

- [ ] **Step 2: Write the failing unit test**

Append to `tests/test_settings_page_mappings.py`:

```python
def test_get_mappings_preserves_an_internal_name_it_has_no_row_for(qapp):
    """A field missing from required/optional must not delete the client's
    mapping for it. Regression: stock_optional listed only Product_Name, so
    one Save destroyed the Expiry_Date and Batch mappings the default config
    ships with -- and with them, FIFO lot allocation."""
    widget = ColumnMappingWidget(
        mapping_type="stock",
        current_mappings={"Article": "SKU", "Available": "Stock", "Годност": "Expiry_Date"},
        required_fields=["SKU", "Stock"],
        optional_fields=[],  # deliberately does not manage Expiry_Date
    )
    assert widget.get_mappings() == {
        "Article": "SKU",
        "Available": "Stock",
        "Годност": "Expiry_Date",
    }


def test_get_mappings_still_removes_a_cleared_managed_field(qapp):
    """Carrying unmanaged entries through must not resurrect a field the user
    deliberately cleared."""
    widget = ColumnMappingWidget(
        mapping_type="stock",
        current_mappings={"Article": "SKU", "Name": "Product_Name"},
        required_fields=["SKU"],
        optional_fields=["Product_Name"],
    )
    widget.csv_column_inputs["Product_Name"].setText("")
    assert widget.get_mappings() == {"Article": "SKU"}
```

Add to the imports at the top of the file:

```python
from gui.column_mapping_widget import ColumnMappingWidget
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py tests/test_settings_roundtrip.py -v`
Expected: `test_get_mappings_preserves_an_internal_name_it_has_no_row_for` FAILS (`Годност` missing from the result) and `test_no_page_silently_drops_a_field` FAILS on section `column_mappings`. `test_get_mappings_still_removes_a_cleared_managed_field` passes already — it is the guard against over-correcting in Step 4.

- [ ] **Step 4: Write the implementation**

Replace `get_mappings` in `gui/column_mapping_widget.py`:

```python
    def get_mappings(self):
        """Get current mappings from UI.

        Entries for internal names this widget has no row for are carried
        through untouched. Without that, a field missing from
        required_fields/optional_fields is silently deleted from the client's
        config on every save -- which is exactly what happened to the
        Expiry_Date and Batch mappings that drive FIFO lot allocation.

        A *managed* field left blank is still removed: its old entry was
        never carried over, so clearing a box does delete the mapping.

        Returns:
            dict: Dictionary of {csv_column_name: internal_name}
        """
        managed = set(self.required_fields) | set(self.optional_fields)
        mappings = {
            csv_column: internal_name
            for csv_column, internal_name in self.current_mappings.items()
            if internal_name not in managed
        }

        for internal_name in self.required_fields + self.optional_fields:
            input_widget = self.csv_column_inputs.get(internal_name)
            if input_widget:
                csv_column = input_widget.text().strip()
                if csv_column:  # Only add non-empty mappings
                    mappings[csv_column] = internal_name

        return mappings
```

Note for Task 5: `.text()` becomes `.currentText()` when the inputs become editable
combo boxes. Left correct for the widget as it exists right now.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py tests/test_settings_roundtrip.py -v`
Expected: PASS, all of them.

- [ ] **Step 6: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
Expected: 525 passed (523 baseline + 2 new).

- [ ] **Step 7: Commit**

```bash
git add gui/column_mapping_widget.py tests/conftest.py tests/test_settings_page_mappings.py
git commit -m "fix(settings): saving no longer deletes stock mappings the UI has no row for"
```

---

### Task 3: Expiry_Date and Batch become editable rows

Task 2 stops them being destroyed. This makes them editable, which is the ticket.

**Files:**
- Modify: `gui/settings/mappings.py:66-67` (`stock_required` / `stock_optional`)
- Test: `tests/test_settings_page_mappings.py`

**Interfaces:**
- Consumes: `ColumnMappingWidget(mapping_type, current_mappings, required_fields, optional_fields)` and its `csv_column_inputs: dict[str, QWidget]`.
- Produces: `MappingsPage.stock_mapping_widget` now has inputs keyed `"Expiry_Date"` and `"Batch"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings_page_mappings.py`:

```python
def test_stock_page_offers_rows_for_the_lot_tracking_fields(qapp):
    """Expiry_Date and Batch drive _build_fifo_lots(); before this they were
    in the default client config with no way to see or edit them."""
    page = MappingsPage(valid_column_mappings(), {})
    inputs = page.stock_mapping_widget.csv_column_inputs
    assert "Expiry_Date" in inputs
    assert "Batch" in inputs


def test_stock_lot_mappings_round_trip_through_the_page(qapp):
    column_mappings = valid_column_mappings()
    column_mappings["stock"] = {
        "Article": "SKU",
        "Available": "Stock",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }
    page = MappingsPage(column_mappings, {})

    assert page.collect()["column_mappings"]["stock"] == {
        "Article": "SKU",
        "Available": "Stock",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }
```

The second test is the one that matters: `"Exp date"`/`"Lot"` are *not* the Bulgarian
headers `_LOT_COLUMN_DEFAULTS` rescues, so this is the case that was permanently broken.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -v`
Expected: `test_stock_page_offers_rows_for_the_lot_tracking_fields` FAILS with `assert 'Expiry_Date' in {...}`. `test_stock_lot_mappings_round_trip_through_the_page` PASSES already, courtesy of Task 2 — it stays as the guard that the fields survive both mechanisms.

- [ ] **Step 3: Write the implementation**

In `gui/settings/mappings.py`, replace lines 65-67:

```python
        # Define required and optional fields for stock
        stock_required = ["SKU", "Stock"]
        stock_optional = ["Product_Name"]
```

with:

```python
        # Define required and optional fields for stock.
        # Expiry_Date and Batch are the exact internal names _build_fifo_lots()
        # looks for (shopify_tool/analysis.py:96-97) -- renaming them here
        # silently turns FIFO lot allocation off.
        stock_required = ["SKU", "Stock"]
        stock_optional = ["Product_Name", "Expiry_Date", "Batch"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/settings/mappings.py tests/test_settings_page_mappings.py
git commit -m "feat(settings): expose Expiry_Date and Batch in the Stock CSV mapping"
```

---

### Task 4: Don't inject a lot default for an internal name already mapped

`analysis.py` back-fills `Годност`/`Партида` whenever those *CSV header keys* are absent.
Now that a client can map `Exp date → Expiry_Date` in the UI, that test is wrong: it
injects a second CSV header claiming the same internal name.

**Files:**
- Modify: `shopify_tool/analysis.py:216-221`
- Test: `tests/test_analysis.py`

**Interfaces:**
- Consumes: `_LOT_COLUMN_DEFAULTS` (module constant, `analysis.py:14`).
- Produces: no signature change; behavioural change inside `_clean_and_prepare_data`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis.py`:

```python
def test_lot_defaults_are_not_injected_when_the_internal_name_is_already_mapped():
    """A client who maps their own expiry header in Settings must not also get
    the Bulgarian default injected -- that is two CSV headers claiming one
    internal name."""
    from shopify_tool.analysis import _LOT_COLUMN_DEFAULTS, _resolve_stock_mappings

    resolved = _resolve_stock_mappings({"Article": "SKU", "Exp date": "Expiry_Date"})

    assert resolved["Exp date"] == "Expiry_Date"
    assert "Годност" not in resolved
    # Batch is still unmapped, so its default is still injected.
    assert resolved["Партида"] == "Batch"
    assert _LOT_COLUMN_DEFAULTS == {"Годност": "Expiry_Date", "Партида": "Batch"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_analysis.py -k lot_defaults -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_stock_mappings'`

- [ ] **Step 3: Write the implementation**

In `shopify_tool/analysis.py`, add after `_LOT_COLUMN_DEFAULTS` (line 14):

```python
def _resolve_stock_mappings(stock_mappings: dict[str, str]) -> dict[str, str]:
    """Back-fill lot column defaults that the config does not already cover.

    Lot tracking works for clients whose configs pre-date the Stock mapping UI
    without a config migration. A default is skipped when its CSV header is
    already mapped, or when its *internal* name is -- otherwise a client who
    maps "Exp date" -> Expiry_Date also gets "Годност" -> Expiry_Date, i.e.
    two CSV headers claiming one internal field.

    ponytail: this back-fill is only needed until existing configs have been
    re-saved through the fixed Mappings UI -- drop it, and the constant, once
    that has happened.
    """
    mapped_internals = set(stock_mappings.values())
    missing = {
        csv_col: internal
        for csv_col, internal in _LOT_COLUMN_DEFAULTS.items()
        if csv_col not in stock_mappings and internal not in mapped_internals
    }
    return {**stock_mappings, **missing} if missing else stock_mappings
```

Then replace lines 216-221 (the inline injection):

```python
    # Inject lot column defaults for any keys not already in the config mapping.
    # This ensures lot tracking works for existing clients whose configs pre-date
    # this feature without requiring a config migration or UI change.
    missing = {k: v for k, v in _LOT_COLUMN_DEFAULTS.items() if k not in stock_mappings}
    if missing:
        stock_mappings = {**stock_mappings, **missing}
```

with:

```python
    stock_mappings = _resolve_stock_mappings(stock_mappings)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_analysis.py -v`
Expected: PASS, including the existing lot-tracking cases — the extraction is behaviour-preserving for every input where no internal name is doubly mapped.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/analysis.py tests/test_analysis.py
git commit -m "fix(analysis): skip a lot default whose internal name is already mapped"
```

---

### Task 5: Rebuild the mapping row

Everything so far is invisible. This is the "better UI" half: drop the twelve repeated
`"Your CSV Column:"` labels, the `→` arrows, the trailing `*` column and the inner
`QScrollArea` that gives the page its second scrollbar.

**Files:**
- Modify: `gui/column_mapping_widget.py` (replace `_setup_ui` and `_create_mapping_row`; update `get_mappings`, `validate_mappings`, `set_mappings` for the new input type)
- Test: `tests/test_settings_page_mappings.py`

**Interfaces:**
- Consumes: `FormSection(title, description="")` with `.add_row(label, widget, tooltip="") -> QLabel` and `.add_widget(widget)` from `gui/components/form_section.py`.
- Produces:
  - `ColumnMappingWidget.csv_column_inputs: dict[str, QComboBox]` — was `dict[str, QLineEdit]`. Editable combo boxes; read with `.currentText()`, write with `.setCurrentText()`.
  - `ColumnMappingWidget.set_available_headers(headers: list[str]) -> None` — new, used by Task 7.
  - `get_mappings()`, `validate_mappings()`, `set_mappings()`, `mappings_changed` unchanged in name and signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings_page_mappings.py`:

```python
from PySide6.QtWidgets import QComboBox, QScrollArea


def test_mapping_inputs_are_editable_combo_boxes(qapp):
    page = MappingsPage(valid_column_mappings(), {})
    sku_input = page.orders_mapping_widget.csv_column_inputs["SKU"]
    assert isinstance(sku_input, QComboBox)
    assert sku_input.isEditable()
    assert sku_input.currentText() == "Lineitem sku"


def test_set_available_headers_offers_them_on_every_row_without_losing_text(qapp):
    page = MappingsPage(valid_column_mappings(), {})
    widget = page.orders_mapping_widget

    widget.set_available_headers(["Name", "Lineitem sku", "Some other column"])

    sku_input = widget.csv_column_inputs["SKU"]
    assert [sku_input.itemText(i) for i in range(sku_input.count())] == [
        "Name",
        "Lineitem sku",
        "Some other column",
    ]
    assert sku_input.currentText() == "Lineitem sku", "typed/configured text must survive"


def test_the_widget_has_no_scroll_area_of_its_own(qapp):
    """The page already scrolls. A second QScrollArea inside it clips the
    Stock block to a few rows and produces two scrollbars side by side."""
    page = MappingsPage(valid_column_mappings(), {})
    assert page.orders_mapping_widget.findChildren(QScrollArea) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -v`
Expected: all three FAIL — the inputs are `QLineEdit`, `set_available_headers` does not exist, and the widget holds a `QScrollArea`.

- [ ] **Step 3: Rewrite the widget's UI half**

In `gui/column_mapping_widget.py`, replace the imports:

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget

from gui.components.form_section import FormSection
```

`Qt`, `QGroupBox`, `QHBoxLayout`, `QLabel`, `QLineEdit`, `QScrollArea`, `font_css` and
`get_theme_manager` all become unused — remove them, `ruff` will fail otherwise.

Replace `_setup_ui` and `_create_mapping_row` with:

```python
    def _setup_ui(self):
        """Setup the UI layout.

        No QScrollArea here: the settings page already scrolls, and nesting a
        second one clips this widget to a few rows. One FormSection per group;
        the internal field name is the row label, so the per-row
        "Your CSV Column:" label and the -> arrow both go.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.required_fields:
            required_section = FormSection("Required")
            for internal_name in self.required_fields:
                self._add_mapping_row(required_section, internal_name, required=True)
            layout.addWidget(required_section)

        if self.optional_fields:
            optional_section = FormSection("Optional")
            for internal_name in self.optional_fields:
                self._add_mapping_row(optional_section, internal_name, required=False)
            layout.addWidget(optional_section)

    def _add_mapping_row(self, section, internal_name, required=False):
        """Add one internal-field row to `section`.

        Args:
            section (FormSection): The section to append the row to.
            internal_name (str): The internal field name (e.g. "Order_Number").
            required (bool): Whether this field is required.
        """
        csv_input = QComboBox()
        csv_input.setEditable(True)
        csv_input.setInsertPolicy(QComboBox.NoInsert)
        csv_input.lineEdit().setPlaceholderText("Enter column name...")
        csv_input.setCurrentText(self.internal_to_csv.get(internal_name, ""))
        csv_input.currentTextChanged.connect(lambda: self.mappings_changed.emit())

        self.csv_column_inputs[internal_name] = csv_input
        section.add_row(
            f"{internal_name} *" if required else internal_name,
            csv_input,
            tooltip=self.FIELD_TOOLTIPS.get(
                internal_name,
                "Required — the save is blocked until this is mapped."
                if required
                else "",
            ),
        )
```

Add the tooltip table as a class attribute, directly under `mappings_changed`:

```python
    # Only fields whose effect is not obvious from the name. A warehouse
    # operator setting up lot tracking has no other way to learn what these do.
    FIELD_TOOLTIPS: ClassVar[dict[str, str]] = {
        "Expiry_Date": (
            "Optional. When mapped, stock is allocated oldest-expiry-first (FIFO) "
            "and each packing list row shows the lot it came from.\n"
            "Understood formats: YYMMDD, YYYYMMDD, DDMMYY, MMYY."
        ),
        "Batch": (
            "Optional. Lot or batch number. Shown per lot on packing lists, and "
            "used to keep separate deliveries of the same SKU apart."
        ),
    }
```

with `from typing import ClassVar` at the top.

- [ ] **Step 4: Switch the three readers to the combo box API**

In the same file, `get_mappings` (rewritten in Task 2) — change:

```python
                csv_column = input_widget.text().strip()
```

to:

```python
                csv_column = input_widget.currentText().strip()
```

In `validate_mappings`, change:

```python
            csv_column = self.csv_column_inputs[internal_name].text().strip()
```

to:

```python
            csv_column = self.csv_column_inputs[internal_name].currentText().strip()
```

In `set_mappings`, change:

```python
            input_widget.setText(csv_column)
```

to:

```python
            input_widget.setCurrentText(csv_column)
```

- [ ] **Step 5: Add `set_available_headers`**

Append to the class:

```python
    def set_available_headers(self, headers):
        """Offer `headers` as dropdown options on every row.

        The text already in each box is preserved -- a configured mapping
        whose column is absent from the file the user just picked must not be
        wiped by looking at that file. A header already used by another row is
        still offered; validate_mappings() catches the duplicate on Save,
        which is where that error belongs.

        Args:
            headers (list): Column names read from a CSV.
        """
        for input_widget in self.csv_column_inputs.values():
            current = input_widget.currentText()
            input_widget.clear()
            input_widget.addItems(headers)
            input_widget.setCurrentText(current)
```

`clear()` on an editable `QComboBox` also clears its line edit, which is why `current` is
read first and restored after.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py tests/test_settings_roundtrip.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite and the linter**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest && .venv/bin/ruff check . --exclude shared`
Expected: all pass, ruff clean. If ruff reports unused imports in `column_mapping_widget.py`, Step 3's import cleanup was incomplete.

- [ ] **Step 8: Commit**

```bash
git add gui/column_mapping_widget.py tests/test_settings_page_mappings.py
git commit -m "refactor(settings): rebuild mapping rows on FormSection, drop the nested scroll area"
```

---

### Task 6: Split Mappings into Orders and Stock nav pages

**Files:**
- Modify: `gui/settings/mappings.py` (whole file — `MappingsPage` becomes two classes)
- Modify: `gui/settings/window.py:59` (nav group) and `:150-156` (page registration)
- Test: `tests/test_settings_page_mappings.py`, `tests/test_settings_roundtrip.py`

**Interfaces:**
- Consumes: `SettingsPage` (`gui/settings/base.py`), `ColumnMappingWidget` incl. `set_available_headers` from Task 5.
- Produces:
  - `OrdersMappingPage(column_mappings: dict, courier_mappings: dict, parent=None)` — attributes `orders_mapping_widget`, `courier_mapping_widgets`, method `add_courier_mapping_row`, `_delete_courier_row`. `collect()` returns `{"column_mappings": ..., "courier_mappings": ...}`.
  - `StockMappingPage(column_mappings: dict, parent=None)` — attribute `stock_mapping_widget`. `collect()` returns `{"column_mappings": ...}`.
  - `MappingsPage` is **gone**. Both classes live in `gui/settings/mappings.py`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_settings_page_mappings.py`'s imports and add these; every existing
`MappingsPage(...)` call in the file becomes the matching new class (the courier tests
move to `OrdersMappingPage`, the stock tests to `StockMappingPage`, and
`test_mappings_page_round_trips_valid_mappings` splits in two).

```python
def test_both_pages_collect_into_one_live_column_mappings_dict(qapp):
    """Two pages now own one config key. Each must write only its own sub-key
    in place -- a clear() or a freshly built dict in either one wipes the
    other's work, and _pages order decides who loses."""
    column_mappings = valid_column_mappings()
    orders_page = OrdersMappingPage(column_mappings, {})
    stock_page = StockMappingPage(column_mappings)

    stock_page.collect()
    orders_page.collect()

    assert column_mappings["orders"]["Lineitem sku"] == "SKU"
    assert column_mappings["stock"]["Article"] == "SKU"
    assert column_mappings["version"] == 2


def test_collect_order_does_not_matter(qapp):
    column_mappings = valid_column_mappings()
    orders_page = OrdersMappingPage(column_mappings, {})
    stock_page = StockMappingPage(column_mappings)

    orders_page.collect()
    result = stock_page.collect()["column_mappings"]

    assert set(result) == {"version", "orders", "stock"}
    assert result["orders"] and result["stock"]


def test_stock_page_collect_emits_every_stock_key_it_was_built_with(qapp):
    """Key coverage for the live-dict blind spot: collect() returns the same
    object the page was constructed with, so the roundtrip guard in
    test_settings_roundtrip.py cannot see a dropped sub-key here. Detach
    first, then assert on what collect() actively writes."""
    column_mappings = valid_column_mappings()
    column_mappings["stock"] = {
        "Article": "SKU",
        "Available": "Stock",
        "Name": "Product_Name",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }
    page = StockMappingPage(column_mappings)

    page.column_mappings = {}  # detach from the live dict
    written = page.collect()["column_mappings"]["stock"]

    assert set(written.values()) == {"SKU", "Stock", "Product_Name", "Expiry_Date", "Batch"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -v`
Expected: FAIL — `ImportError: cannot import name 'OrdersMappingPage'`

- [ ] **Step 3: Split the page**

Rewrite `gui/settings/mappings.py`. `OrdersMappingPage` keeps the courier block verbatim
(`add_courier_mapping_row`, `_delete_courier_row` and their imports move with it);
`StockMappingPage` is the stock half.

```python
"""Column mappings, split one page per CSV: orders (plus courier name
mappings, which resolve an orders column) and stock."""

from typing import ClassVar

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.column_mapping_widget import ColumnMappingWidget
from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage
from gui.theme_manager import get_theme_manager, set_button_role


class _MappingPageBase(SettingsPage):
    """Shared scaffolding: one scroll area, one column-mapping widget.

    Both pages hold the SAME live config_data["column_mappings"] dict and
    write only their own sub-key into it, in place. Never clear() it and
    never rebuild it -- whichever page collect()s second would wipe the
    other's sub-key, and _pages order would silently decide which.
    """

    MAPPING_TYPE = ""
    TITLE = ""
    DESCRIPTION = ""
    # ClassVar, not a bare annotation: ruff's RUF012 rejects a mutable class
    # attribute without it, and window.py already uses this for the same reason.
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    OPTIONAL_FIELDS: ClassVar[list[str]] = []

    def __init__(self, column_mappings: dict, parent=None):
        super().__init__(parent)
        self.column_mappings = column_mappings

        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)

        box = FormSection(self.TITLE, self.DESCRIPTION)
        self.mapping_widget = ColumnMappingWidget(
            mapping_type=self.MAPPING_TYPE,
            current_mappings=column_mappings.get(self.MAPPING_TYPE, {}),
            required_fields=self.REQUIRED_FIELDS,
            optional_fields=self.OPTIONAL_FIELDS,
        )
        box.add_widget(self.mapping_widget)
        self.scroll_layout.addWidget(box)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

    def validate(self) -> tuple[bool, list[str]]:
        ok, error = self.mapping_widget.validate_mappings()
        if not ok:
            return False, [f"{self.TITLE} is invalid:\n{error}"]
        return True, []

    def _collect_column_mappings(self) -> dict:
        """Write this page's sub-key into the live dict and return it."""
        self.column_mappings["version"] = 2
        self.column_mappings[self.MAPPING_TYPE] = self.mapping_widget.get_mappings()
        return self.column_mappings


class OrdersMappingPage(_MappingPageBase):
    """Orders CSV columns, plus the courier name mappings that resolve the
    Shipping_Method values those columns carry."""

    MAPPING_TYPE = "orders"
    TITLE = "Orders CSV Column Mapping"
    DESCRIPTION = "Map your CSV column names to internal fields for the ORDERS file."
    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "Order_Number", "SKU", "Quantity", "Shipping_Method",
    ]
    OPTIONAL_FIELDS: ClassVar[list[str]] = [
        "Product_Name", "Shipping_Country", "Tags", "Notes", "Total_Price", "Subtotal",
    ]

    def __init__(self, column_mappings: dict, courier_mappings: dict, parent=None):
        super().__init__(column_mappings, parent)
        self.courier_mappings = courier_mappings
        self.courier_mapping_widgets = []
        self.orders_mapping_widget = self.mapping_widget  # name used by tests/callers

        courier_box = FormSection(
            "Courier Mappings",
            "Map different shipping provider names to standardized courier codes. "
            "You can specify multiple patterns (comma-separated) for each courier.",
        )
        self.courier_mappings_container = QWidget()
        self.courier_mappings_layout = QVBoxLayout(self.courier_mappings_container)
        self.courier_mappings_layout.setContentsMargins(0, 0, 0, 0)
        courier_box.add_widget(self.courier_mappings_container)

        add_courier_btn = QPushButton("+ Add Courier Mapping")
        set_button_role(add_courier_btn, "secondary")
        add_courier_btn.clicked.connect(lambda: self.add_courier_mapping_row())
        add_courier_btn.setMaximumWidth(200)
        courier_box.add_widget(add_courier_btn)

        self.scroll_layout.addWidget(courier_box)
        self.scroll_layout.addStretch()

        if isinstance(courier_mappings, dict):
            for courier_code, mapping_data in courier_mappings.items():
                if isinstance(mapping_data, dict):
                    patterns = mapping_data.get("patterns", [])
                    self.add_courier_mapping_row(courier_code, ", ".join(patterns) if patterns else "")

        if not courier_mappings:
            self.add_courier_mapping_row()

    def collect(self) -> dict:
        new_couriers = {}
        for row_refs in self.courier_mapping_widgets:
            courier_code = row_refs["courier_code"].text().strip()
            patterns_str = row_refs["patterns"].text().strip()
            if courier_code and patterns_str:
                patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
                new_couriers[courier_code] = {"patterns": patterns, "case_sensitive": False}

        # Same live-dict contract as column_mappings: clear-and-refill in
        # place so a deleted courier code does not survive the shell's merge.
        self.courier_mappings.clear()
        self.courier_mappings.update(new_couriers)

        return {
            "column_mappings": self._collect_column_mappings(),
            "courier_mappings": self.courier_mappings,
        }
```

`add_courier_mapping_row` and `_delete_courier_row` move onto `OrdersMappingPage`
**unchanged** from `mappings.py:121-176` — copy them verbatim, including the
`accent_red` stylesheet and its comment.

```python
class StockMappingPage(_MappingPageBase):
    """Stock CSV columns, including the two that drive FIFO lot allocation."""

    MAPPING_TYPE = "stock"
    TITLE = "Stock CSV Column Mapping"
    DESCRIPTION = "Map your CSV column names to internal fields for the STOCK file."
    REQUIRED_FIELDS: ClassVar[list[str]] = ["SKU", "Stock"]
    # Expiry_Date and Batch are the exact internal names _build_fifo_lots()
    # looks for (shopify_tool/analysis.py:96-97) -- renaming them here
    # silently turns FIFO lot allocation off.
    OPTIONAL_FIELDS: ClassVar[list[str]] = ["Product_Name", "Expiry_Date", "Batch"]

    def __init__(self, column_mappings: dict, parent=None):
        super().__init__(column_mappings, parent)
        self.stock_mapping_widget = self.mapping_widget  # name used by tests/callers
        self.scroll_layout.addStretch()

    def collect(self) -> dict:
        return {"column_mappings": self._collect_column_mappings()}
```

- [ ] **Step 4: Register both pages in the window**

In `gui/settings/window.py`, change the import at line 24:

```python
from gui.settings.mappings import OrdersMappingPage, StockMappingPage
```

Change the nav group at line 59:

```python
        ("Data", ["General", "Orders Mapping", "Stock Mapping", "Column Config"]),
```

Replace the registration at lines 150-156:

```python
        self._add_page(
            OrdersMappingPage(
                self.config_data.get("column_mappings", {}),
                self.config_data.get("courier_mappings", {}),
            ),
            "Orders Mapping",
        )
        self._add_page(
            StockMappingPage(self.config_data.get("column_mappings", {})),
            "Stock Mapping",
        )
```

No nav migration is needed: `_restore_nav_selection` matches by name and falls back to
the first selectable row when the stored name is gone (`window.py:221-233`), so a user
whose last page was `"Mappings"` lands on General.

- [ ] **Step 5: Update the roundtrip test's page-count expectation**

`test_window_registers_every_page` (`tests/test_settings_roundtrip.py:18`) asserts on the
registration order. Replace its list:

```python
def test_window_registers_every_page(window):
    assert list(window._page_index_by_name) == [
        "General", "Rules", "Packing Lists", "Stock Exports",
        "Orders Mapping", "Stock Mapping",
        "Sets", "Weight", "Tag Categories", "Column Config",
    ]
```

The order is registration order, not nav order — `OrdersMappingPage` and
`StockMappingPage` are registered where the single `MappingsPage` call used to be.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py tests/test_settings_roundtrip.py -v`
Expected: PASS.

- [ ] **Step 7: Verify the key-coverage test actually bites**

Temporarily change `StockMappingPage.OPTIONAL_FIELDS` to `["Product_Name"]` and run:

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -k emits_every_stock_key -v`
Expected: FAIL. If it passes, the test is not detached from the live dict and is comparing an object to itself — fix it before continuing. **Revert the temporary change.**

- [ ] **Step 8: Run the full suite and the linter**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest && .venv/bin/ruff check . --exclude shared`
Expected: all pass, ruff clean.

- [ ] **Step 9: Commit**

```bash
git add gui/settings/mappings.py gui/settings/window.py tests/
git commit -m "refactor(settings): split Mappings into Orders and Stock nav pages"
```

---

### Task 7: "Load headers from CSV…"

**Files:**
- Modify: `gui/settings/mappings.py` (`_MappingPageBase`)
- Test: `tests/test_settings_page_mappings.py`

**Interfaces:**
- Consumes: `read_csv_headers(file_path, encoding="utf-8-sig") -> list[str]` (Task 1); `ColumnMappingWidget.set_available_headers(headers)` (Task 5).
- Produces: `_MappingPageBase._load_headers_from_csv()` on both pages, plus a `load_headers_btn` attribute.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings_page_mappings.py`:

```python
def test_load_headers_fills_every_row_from_the_chosen_file(qapp, tmp_path, monkeypatch):
    csv = tmp_path / "stock.csv"
    csv.write_text("Article;Available;Exp date;Lot\nA1;5;261230;L7\n", encoding="utf-8")

    page = StockMappingPage(valid_column_mappings())
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(csv), ""),
    )

    page._load_headers_from_csv()

    sku_input = page.stock_mapping_widget.csv_column_inputs["SKU"]
    assert [sku_input.itemText(i) for i in range(sku_input.count())] == [
        "Article", "Available", "Exp date", "Lot",
    ]
    assert sku_input.currentText() == "Article", "the configured mapping must survive"


def test_load_headers_cancelled_leaves_the_inputs_alone(qapp, monkeypatch):
    page = StockMappingPage(valid_column_mappings())
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName", lambda *a, **k: ("", "")
    )

    page._load_headers_from_csv()

    sku_input = page.stock_mapping_widget.csv_column_inputs["SKU"]
    assert sku_input.count() == 0
    assert sku_input.currentText() == "Article"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -k load_headers -v`
Expected: FAIL — `AttributeError: 'StockMappingPage' object has no attribute '_load_headers_from_csv'`

- [ ] **Step 3: Write the implementation**

In `gui/settings/mappings.py`, extend the imports:

```python
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from shopify_tool.csv_utils import read_csv_headers
```

In `_MappingPageBase.__init__`, immediately after `box = FormSection(...)` and before
`box.add_widget(self.mapping_widget)`:

```python
        self.load_headers_btn = QPushButton("Load headers from CSV...")
        set_button_role(self.load_headers_btn, "secondary")
        self.load_headers_btn.setMaximumWidth(220)
        self.load_headers_btn.setToolTip(
            "Pick your CSV to fill each field's dropdown with its real column "
            "names. Nothing you have already typed is changed."
        )
        self.load_headers_btn.clicked.connect(self._load_headers_from_csv)
        box.add_widget(self.load_headers_btn)
```

Add the handler to `_MappingPageBase`:

```python
    def _load_headers_from_csv(self):
        """Offer a chosen CSV's column names as dropdown options on every row.

        Reads the header line only, and detects the delimiter itself, so this
        does not depend on the delimiter the General page currently shows --
        which may hold an edit the user has not saved yet.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.MAPPING_TYPE.capitalize()} CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            headers = read_csv_headers(file_path)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Could Not Read CSV",
                f"Failed to read column names from this file:\n\n{e!s}",
            )
            return

        if not headers:
            QMessageBox.warning(
                self, "No Columns Found", "That file has no column headers."
            )
            return

        self.mapping_widget.set_available_headers(headers)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_mappings.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest && .venv/bin/ruff check . --exclude shared`
Expected: full suite green, ruff clean.

- [ ] **Step 6: Refresh the knowledge graph**

Run: `graphify update .`

Per this repo's `CLAUDE.md` — a stale graph silently returns wrong answers about
`shared/` ownership and theme delegation. `graphify-out/` is gitignored; nothing to
commit from this step.

- [ ] **Step 7: Commit**

```bash
git add gui/settings/mappings.py tests/test_settings_page_mappings.py
git commit -m "feat(settings): load real CSV headers into the mapping dropdowns"
```

---

## Notes for the implementer

**Task ordering is deliberate.** Tasks 2-4 fix the defect and can ship on their own if the
UI work stalls; tasks 5-7 are the visible half. Do not reorder — Task 5 changes the input
widget type that Tasks 2 and 3 write tests against, and it updates those call sites as
part of its own step list.

**One churn point, accepted:** Task 2 writes `.text()` and Task 5 changes it to
`.currentText()`. That is the price of landing the data-loss fix before the UI rewrite,
and it is one line in each of three methods.

**The live-dict contract is the trap in this change.** Two pages now own
`config_data["column_mappings"]`. `test_no_page_silently_drops_a_field` cannot see a
dropped sub-key when `collect()` returns the same object the page was built from — that
is why Task 6 Step 7 mutation-checks the key-coverage test by hand. This is the same
blind spot the Settings Hub review found in `GeneralPage` and `WeightPage`; do not skip
the check.

**Windows visual verification is not possible here.** Development is on Linux; the app is
Windows-only in production. The screenshots this design was built from came from the user.
Leave the visual check to them and say so in the PR.
