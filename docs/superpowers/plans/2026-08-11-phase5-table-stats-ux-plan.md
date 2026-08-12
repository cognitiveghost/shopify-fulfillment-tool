# Phase 5 — Table & Stats UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship the three independent Phase 5 UI cleanups (Todoist `6h8v49wj4M3cFxJV`) scoped in `docs/superpowers/specs/2026-08-11-phase5-table-stats-ux-design.md`: a grouped Manage Table Columns list, two small Statistics-tab fixes, and a simplified Add Product to Order dialog.

**Architecture:** No new subsystems — each item is a targeted edit to an existing widget file, following the design doc's code-verified findings. Items are independent; tasks can be done and PR'd in any order, but this plan sequences them Item 1 → Item 2 → Item 3 to match the design doc.

**Tech Stack:** PySide6 (`QListWidget`, `QTableWidget`, `QFormLayout`), pytest with `QT_QPA_PLATFORM=offscreen`.

## Global Constraints

- No hardcoded colors — use `get_theme_manager().get_current_theme()` tokens (per this repo's `CLAUDE.md`). The two `# ponytail:`-marked literal-color blocks already in `add_product_dialog.py` (warning/info tint backgrounds) are pre-existing and out of scope for this plan — leave them as-is except where a task explicitly touches that code.
- No UI calls from background threads — not applicable here, none of these three items touch threading.
- Run `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` before each commit that touches code (per `AGENTS.md` / this repo's `CLAUDE.md`).
- Run `graphify update .` after the final commit of this plan (per this repo's `CLAUDE.md` — a stale graph gives wrong answers about file relationships).

---

## Task 1: Manage Table Columns — group the column list by category with display names

**Files:**
- Modify: `gui/column_config_dialog.py` (module-level constants + `ColumnConfigPanel._load_columns`, `_on_search_changed`, `_on_item_changed`, `_on_move_up`, `_on_move_down`, `_on_show_all`, `_on_hide_all`, `_get_config_from_ui`)
- Test: `tests/test_column_config_dialog.py` (new)

**Interfaces:**
- Consumes: `gui.table_config_manager.TableConfig` (existing — `visible_columns: dict[str, bool]`, `column_order: list[str]`, `locked_columns: list[str]`).
- Produces: module-level `COLUMN_CATEGORIES: dict[str, str]`, `COLUMN_DISPLAY_NAMES: dict[str, str]`, `CATEGORY_ORDER: list[str]`, `_CATEGORY_HEADER_MARKER: str` in `gui/column_config_dialog.py`, consumed only within that file. Every `QListWidgetItem` in `self.column_list` now carries the **raw** column name (or `_CATEGORY_HEADER_MARKER` for header rows) in `item.data(Qt.UserRole)` — `item.text()` is now a **display** string only. Any future code touching `self.column_list` must read `item.data(Qt.UserRole)`, not `item.text()`.

Currently `ColumnConfigPanel._load_columns` (`gui/column_config_dialog.py:255-292`) builds a flat, ungrouped `QListWidget` where each item's `text()` *is* the raw DataFrame column name (e.g. `Order_Fulfillment_Status`), and every other method in the class (`_on_item_changed`, `_on_move_up`, `_on_move_down`, `_get_config_from_ui`) reads that same `item.text()` back out as the column name. This task inserts non-checkable, bold category header rows between groups and swaps the checkable items' visible text for a friendlier display name — which means `item.text()` can no longer double as the raw column name. Every one of those call sites must switch to `item.data(Qt.UserRole)` in the same change, or they'll silently start writing display-name strings into `TableConfig.column_order`/`visible_columns` instead of real column names.

- [x] **Step 1: Write the failing test**

Create `tests/test_column_config_dialog.py`:

```python
"""Regression test: Manage Table Columns list must group columns under
category header rows (grouped-list redesign, Phase 5 Item 1) without
breaking the underlying visible/order round-trip. Root cause risk: switching
list items to show display names instead of raw column names would break
every call site that read item.text() as the column name -- this locks in
item.data(Qt.UserRole) as the source of truth instead.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.column_config_dialog import ColumnConfigPanel, _CATEGORY_HEADER_MARKER
from gui.table_config_manager import TableConfig


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _make_panel(columns, locked_columns=None):
    config = TableConfig(
        visible_columns={col: True for col in columns},
        column_order=columns,
        locked_columns=locked_columns if locked_columns is not None else ["Order_Number"],
    )
    tcm = Mock()
    tcm.get_current_config.return_value = config
    tcm.get_current_view_name.return_value = "Default"
    tcm.list_views.return_value = ["Default"]
    tcm.pm.load_client_config.return_value = {}
    main_window = Mock()
    main_window.current_client_id = "TESTCLIENT"
    main_window.analysis_results_df = None
    return ColumnConfigPanel(tcm, main_window=main_window)


def test_columns_are_grouped_under_category_headers():
    panel = _make_panel(["Order_Number", "SKU", "Fulfillable", "Tags"])

    categories_seen = [
        panel.column_list.item(i).text()
        for i in range(panel.column_list.count())
        if panel.column_list.item(i).data(Qt.UserRole) == _CATEGORY_HEADER_MARKER
    ]

    assert categories_seen == ["Order Info", "Product Info", "Fulfillment", "Tags & Lot"]


def test_get_config_from_ui_skips_header_rows():
    panel = _make_panel(["Order_Number", "SKU", "Fulfillable"])

    config = panel._get_config_from_ui()

    assert set(config.column_order) == {"Order_Number", "SKU", "Fulfillable"}
    assert _CATEGORY_HEADER_MARKER not in config.column_order


def test_move_up_is_blocked_at_the_top_of_a_category_group():
    panel = _make_panel(["SKU", "Product_Name"])  # both "Product Info"

    # row 0 = "Product Info" header, row 1 = SKU, row 2 = Product_Name.
    # Product_Name moving up swaps with SKU -- allowed.
    panel.column_list.setCurrentRow(2)
    panel._on_move_up()
    assert panel.column_list.item(1).data(Qt.UserRole) == "Product_Name"

    # Now at row 1, directly under the header -- moving up again must no-op
    # instead of swapping with the header row.
    panel._on_move_up()
    assert panel.column_list.item(1).data(Qt.UserRole) == "Product_Name"


def test_move_up_is_blocked_above_a_locked_column(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    panel = _make_panel(["Order_Number", "Name"])  # both "Order Info"

    # row 0 = header, row 1 = Order_Number (locked), row 2 = Name.
    panel.column_list.setCurrentRow(2)
    panel._on_move_up()

    assert panel.column_list.item(1).data(Qt.UserRole) == "Order_Number"
    assert panel.column_list.item(2).data(Qt.UserRole) == "Name"


def test_locked_column_tooltip_still_shows_raw_name():
    panel = _make_panel(["Order_Number"])

    item = panel.column_list.item(1)  # row 0 = "Order Info" header
    assert item.data(Qt.UserRole) == "Order_Number"
    assert "Order_Number" in item.toolTip()
```

- [x] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_column_config_dialog.py -v`
Expected: FAIL — `ImportError: cannot import name '_CATEGORY_HEADER_MARKER'` (module constant doesn't exist yet).

- [x] **Step 3: Add the category/display-name lookup and import**

In `gui/column_config_dialog.py`, add the import and module-level constants right after `logger = logging.getLogger(__name__)` (line 31):

```python
from PySide6.QtGui import QColor
```
(add to the existing `from PySide6.QtCore import Qt, Signal` block's neighboring imports, i.e. a new top-level import line)

```python
_CATEGORY_HEADER_MARKER = "__category_header__"

# Category assignment for known analysis-output columns (see
# shopify_tool/core.py and shopify_tool/analysis.py for the full
# output-column list). Columns not listed here fall into "Other" rather
# than being dropped from the list.
COLUMN_CATEGORIES: dict[str, str] = {
    "Order_Number": "Order Info",
    "Name": "Order Info",
    "Order_Type": "Order Info",
    "Destination_Country": "Order Info",
    "Shipping_Method": "Order Info",
    "Shipping_Provider": "Order Info",
    "Priority": "Order Info",
    "Order_Min_Box": "Order Info",
    "Execution_Date": "Order Info",
    "Repeat": "Order Info",
    "SKU": "Product Info",
    "Product_Name": "Product Info",
    "Warehouse_Name": "Product Info",
    "Quantity": "Product Info",
    "Has_SKU": "Product Info",
    "Order_Fulfillment_Status": "Fulfillment",
    "Fulfillable": "Fulfillment",
    "Stock": "Fulfillment",
    "Final_Stock": "Fulfillment",
    "Stock_Alert": "Fulfillment",
    "Summary_Missing": "Fulfillment",
    "Summary_Present": "Fulfillment",
    "Status_Note": "Fulfillment",
    "Error": "Fulfillment",
    "System_note": "Fulfillment",
    "Notes": "Fulfillment",
    "Tags": "Tags & Lot",
    "Internal_Tags": "Tags & Lot",
    "Lot_Details": "Tags & Lot",
    "Lot_Batch": "Tags & Lot",
    "Lot_Expiry": "Tags & Lot",
    "Expiry_Date": "Tags & Lot",
}

CATEGORY_ORDER: list[str] = ["Order Info", "Product Info", "Fulfillment", "Tags & Lot", "Other"]

COLUMN_DISPLAY_NAMES: dict[str, str] = {
    "Order_Number": "Order Number",
    "Name": "Order Name",
    "Order_Type": "Order Type",
    "Destination_Country": "Destination Country",
    "Shipping_Method": "Shipping Method",
    "Shipping_Provider": "Shipping Provider",
    "Priority": "Priority",
    "Order_Min_Box": "Min Box",
    "Execution_Date": "Execution Date",
    "Repeat": "Repeat Order",
    "SKU": "SKU",
    "Product_Name": "Product Name",
    "Warehouse_Name": "Warehouse Name",
    "Quantity": "Quantity",
    "Has_SKU": "Has SKU",
    "Order_Fulfillment_Status": "Fulfillment Status",
    "Fulfillable": "Fulfillable",
    "Stock": "Stock",
    "Final_Stock": "Final Stock",
    "Stock_Alert": "Stock Alert",
    "Summary_Missing": "Missing Summary",
    "Summary_Present": "Present Summary",
    "Status_Note": "Status Note",
    "Error": "Error",
    "System_note": "System Note",
    "Notes": "Notes",
    "Tags": "Tags",
    "Internal_Tags": "Internal Tags",
    "Lot_Details": "Lot Details",
    "Lot_Batch": "Lot Batch",
    "Lot_Expiry": "Lot Expiry",
    "Expiry_Date": "Expiry Date",
}


def _column_display_name(col_name: str) -> str:
    return COLUMN_DISPLAY_NAMES.get(col_name, col_name)


def _column_category(col_name: str) -> str:
    return COLUMN_CATEGORIES.get(col_name, "Other")
```

- [x] **Step 4: Rewrite `_load_columns` to group by category**

Replace `ColumnConfigPanel._load_columns` (`gui/column_config_dialog.py:255-292`) with:

```python
    def _load_columns(self, config):
        """Load columns into the list widget, grouped under category headers."""
        self.column_list.clear()
        self._current_columns = []

        if hasattr(self.parent_window, 'analysis_results_df') and \
           self.parent_window.analysis_results_df is not None:
            df = self.parent_window.analysis_results_df
            all_columns = df.columns.tolist()
        else:
            all_columns = config.column_order if config.column_order else list(config.visible_columns.keys())

        if config.column_order:
            ordered_columns = [col for col in config.column_order if col in all_columns]
            for col in all_columns:
                if col not in ordered_columns:
                    ordered_columns.append(col)
            columns = ordered_columns
        else:
            columns = all_columns

        grouped: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
        for col_name in columns:
            grouped[_column_category(col_name)].append(col_name)

        theme = get_theme_manager().get_current_theme()

        for category in CATEGORY_ORDER:
            cols_in_category = grouped[category]
            if not cols_in_category:
                continue

            header_item = QListWidgetItem(category)
            header_item.setFlags(Qt.NoItemFlags)
            header_item.setData(Qt.UserRole, _CATEGORY_HEADER_MARKER)
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            header_item.setForeground(QColor(theme.text_secondary))
            self.column_list.addItem(header_item)

            for col_name in cols_in_category:
                item = QListWidgetItem(_column_display_name(col_name))
                item.setData(Qt.UserRole, col_name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

                is_visible = config.visible_columns.get(col_name, True)
                item.setCheckState(Qt.Checked if is_visible else Qt.Unchecked)

                if col_name in config.locked_columns:
                    item.setToolTip(f"{col_name} (locked column, always visible and first)")
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                else:
                    item.setToolTip(col_name)

                self.column_list.addItem(item)
                self._current_columns.append(col_name)

        self._update_button_states()
```

- [x] **Step 5: Update `_on_search_changed` to read raw names and hide headers while filtering**

Replace `_on_search_changed` (`gui/column_config_dialog.py:294-305`) with:

```python
    def _on_search_changed(self, text: str):
        """Handle search text change."""
        text = text.lower()

        for i in range(self.column_list.count()):
            item = self.column_list.item(i)

            if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
                # ponytail: headers just hide/show with any active filter
                # rather than tracking per-group match counts -- upgrade to
                # "hide only if the whole group is filtered out" if a user
                # reports it's confusing to lose the grouping while typing.
                item.setHidden(bool(text))
                continue

            column_name = item.data(Qt.UserRole)
            item.setHidden(text not in column_name.lower())
```

- [x] **Step 6: Update `_on_item_changed` to skip headers and read raw names**

Replace the body of `_on_item_changed` (`gui/column_config_dialog.py:307-324`) — add a header guard right after the `_is_loading` check, and switch `item.text()` to `item.data(Qt.UserRole)`:

```python
    def _on_item_changed(self, item: QListWidgetItem):
        """Handle item check state change."""
        if self._is_loading:
            return

        if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
            return

        column_name = item.data(Qt.UserRole)
        config = self.table_config_manager.get_current_config()

        if column_name in config.locked_columns and item.checkState() == Qt.Unchecked:
            self._is_loading = True
            item.setCheckState(Qt.Checked)
            self._is_loading = False

            QMessageBox.warning(
                self,
                "Cannot Hide Column",
                f"Column '{column_name}' is locked and cannot be hidden."
            )
```

- [x] **Step 7: Rewrite `_on_move_up`/`_on_move_down` to respect group boundaries and read raw names**

Replace `_on_move_up` (`gui/column_config_dialog.py:326-358`) with:

```python
    def _on_move_up(self):
        """Move selected column up in the order (within its category group)."""
        current_row = self.column_list.currentRow()
        if current_row <= 0:
            return

        item = self.column_list.currentItem()
        if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
            return

        above_item = self.column_list.item(current_row - 1)
        if above_item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
            return  # already first in its category group

        config = self.table_config_manager.get_current_config()
        column_name = item.data(Qt.UserRole)

        if column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Column '{column_name}' is locked and cannot be moved."
            )
            return

        above_column_name = above_item.data(Qt.UserRole)
        if above_column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Cannot move above locked column '{above_column_name}'."
            )
            return

        item = self.column_list.takeItem(current_row)
        self.column_list.insertItem(current_row - 1, item)
        self.column_list.setCurrentRow(current_row - 1)

        self._current_columns.insert(current_row - 1, self._current_columns.pop(current_row))
```

Replace `_on_move_down` (`gui/column_config_dialog.py:360-390`) with:

```python
    def _on_move_down(self):
        """Move selected column down in the order (within its category group)."""
        current_row = self.column_list.currentRow()
        if current_row < 0 or current_row >= self.column_list.count() - 1:
            return

        item = self.column_list.currentItem()
        if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
            return

        below_item = self.column_list.item(current_row + 1)
        if below_item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
            return  # already last in its category group

        config = self.table_config_manager.get_current_config()
        column_name = item.data(Qt.UserRole)

        if column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Column '{column_name}' is locked and cannot be moved."
            )
            return

        below_column_name = below_item.data(Qt.UserRole)
        if below_column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Cannot move below locked column '{below_column_name}'."
            )
            return

        item = self.column_list.takeItem(current_row)
        self.column_list.insertItem(current_row + 1, item)
        self.column_list.setCurrentRow(current_row + 1)

        self._current_columns.insert(current_row + 1, self._current_columns.pop(current_row))
```

This drops the old hardcoded `current_row == 1`/`current_row == 0` special cases (which assumed `Order_Number` always sat at literal row 0 — no longer true once a header row precedes it) in favor of a general "can't swap across a locked column" rule that works regardless of row offsets.

- [x] **Step 8: Update `_on_show_all`/`_on_hide_all` to skip headers and read raw names**

Replace `_on_show_all` (`gui/column_config_dialog.py:392-402`) with:

```python
    def _on_show_all(self):
        """Show all columns and disable auto-hide."""
        self._is_loading = True
        try:
            for i in range(self.column_list.count()):
                item = self.column_list.item(i)
                if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
                    continue
                item.setCheckState(Qt.Checked)
        finally:
            self._is_loading = False

        self.auto_hide_checkbox.setChecked(False)
```

Replace `_on_hide_all` (`gui/column_config_dialog.py:404-419`) with:

```python
    def _on_hide_all(self):
        """Hide all columns (except locked ones)."""
        config = self.table_config_manager.get_current_config()

        self._is_loading = True
        try:
            for i in range(self.column_list.count()):
                item = self.column_list.item(i)
                if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
                    continue
                column_name = item.data(Qt.UserRole)

                if column_name in config.locked_columns:
                    continue

                item.setCheckState(Qt.Unchecked)
        finally:
            self._is_loading = False
```

- [x] **Step 9: Update `_get_config_from_ui` to skip headers and read raw names**

Replace the item-iteration loop in `_get_config_from_ui` (`gui/column_config_dialog.py:637-665`, the `for i in range(self.column_list.count()):` block) with:

```python
        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            if item.data(Qt.UserRole) == _CATEGORY_HEADER_MARKER:
                continue
            column_name = item.data(Qt.UserRole)
            is_visible = item.checkState() == Qt.Checked

            visible_columns[column_name] = is_visible
            column_order.append(column_name)
```

(the rest of the method — building and returning the `TableConfig` — is unchanged)

- [x] **Step 10: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_column_config_dialog.py -v`
Expected: PASS (5 tests)

- [x] **Step 11: Run the full suite and lint, then commit**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest` — expect all pre-existing tests still pass (no other file reads `column_list` internals — confirmed via `grep -rn "\.column_list\b" gui/ --include="*.py"` returning only `column_config_dialog.py` itself).
Run: `ruff check gui/column_config_dialog.py tests/test_column_config_dialog.py`

```bash
git add gui/column_config_dialog.py tests/test_column_config_dialog.py
git commit -m "Group Manage Table Columns list by category with display names"
```

---

## Task 2: Manage Table Columns — fold the two `client_config.json` writes into one

**Files:**
- Modify: `gui/table_config_manager.py:161-210` (`TableConfigManager.save_config`)
- Modify: `gui/column_config_dialog.py:567-635` (`ColumnConfigPanel.apply_config`)
- Test: `tests/test_table_config_manager.py` (new)

**Interfaces:**
- Consumes: `shopify_tool.profile_manager.ProfileManager.load_client_config`/`save_client_config` (existing, unchanged signatures).
- Produces: `TableConfigManager.save_config(client_id, config, view_name="Default", additional_columns=None)` — new optional 4th parameter. When provided (not `None`), the additional-columns list is written into the same `client_config.json` read-modify-write as the view, instead of a second one.

Today, `ColumnConfigPanel.apply_config()` (`gui/column_config_dialog.py:567-635`) calls `table_config_manager.save_config()` (one read-modify-write of `client_config.json`), then — if there's any additional-columns state — does a **second**, independent `self.table_config_manager.pm.load_client_config(...)` / `.save_client_config(...)` pair for the `additional_columns` key. Over a UNC file share that's two network round trips on every "Apply" click instead of one. This task moves the `additional_columns` write inside `TableConfigManager.save_config`'s existing read-modify-write.

- [x] **Step 1: Write the failing test**

Create `tests/test_table_config_manager.py`:

```python
"""Regression test: applying column config must persist to client_config.json
in a single write, not two separate read-modify-write round trips (one for
the view, one for additional_columns) -- each was its own UNC-share round
trip on every Apply click.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.table_config_manager import TableConfig, TableConfigManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_save_config_writes_view_and_additional_columns_in_one_call(profile_manager):
    profile_manager.create_client_profile("TESTCLIENT", "Test Client")
    tcm = TableConfigManager(main_window=Mock(), profile_manager=profile_manager)

    save_spy = Mock(wraps=profile_manager.save_client_config)
    profile_manager.save_client_config = save_spy

    config = TableConfig(visible_columns={"SKU": True}, column_order=["SKU"])
    additional_columns = [{"csv_name": "Extra", "internal_name": "extra", "enabled": True}]

    tcm.save_config("TESTCLIENT", config, "Default", additional_columns=additional_columns)

    assert save_spy.call_count == 1

    saved = profile_manager.load_client_config("TESTCLIENT")
    table_view = saved["ui_settings"]["table_view"]
    assert table_view["views"]["Default"]["column_order"] == ["SKU"]
    assert table_view["additional_columns"] == additional_columns


def test_save_config_without_additional_columns_leaves_existing_value_untouched(profile_manager):
    profile_manager.create_client_profile("TESTCLIENT", "Test Client")
    tcm = TableConfigManager(main_window=Mock(), profile_manager=profile_manager)

    seed = [{"csv_name": "Extra", "internal_name": "extra", "enabled": True}]
    tcm.save_config("TESTCLIENT", TableConfig(), "Default", additional_columns=seed)

    tcm.save_config("TESTCLIENT", TableConfig(visible_columns={"SKU": True}), "Default")

    saved = profile_manager.load_client_config("TESTCLIENT")
    assert saved["ui_settings"]["table_view"]["additional_columns"] == seed
```

- [x] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_table_config_manager.py -v`
Expected: FAIL — `TypeError: save_config() got an unexpected keyword argument 'additional_columns'`

- [x] **Step 3: Add the `additional_columns` parameter to `save_config`**

Replace `TableConfigManager.save_config` (`gui/table_config_manager.py:161-210`) with:

```python
    def save_config(
        self,
        client_id: str,
        config: TableConfig,
        view_name: str = "Default",
        additional_columns: list[dict] | None = None,
    ):
        """Save table configuration for a client.

        Args:
            client_id: Client ID to save config for
            config: TableConfig to save
            view_name: Name of the view to save (default: "Default")
            additional_columns: Optional "Additional CSV Columns" config to
                persist in the same write. Pass None to leave whatever's
                already stored untouched.

        Raises:
            Exception: If config saving fails (logs error)
        """
        try:
            # Load full client config
            client_config = self.pm.load_client_config(client_id)

            # Ensure ui_settings.table_view structure exists
            if "ui_settings" not in client_config:
                client_config["ui_settings"] = {}
            if "table_view" not in client_config["ui_settings"]:
                client_config["ui_settings"]["table_view"] = {
                    "version": 1,
                    "active_view": view_name,
                    "views": {}
                }

            table_view_settings = client_config["ui_settings"]["table_view"]

            # Ensure views dict exists
            if "views" not in table_view_settings:
                table_view_settings["views"] = {}

            # Save view data
            table_view_settings["views"][view_name] = config.to_dict()

            # Update active view
            table_view_settings["active_view"] = view_name

            if additional_columns is not None:
                table_view_settings["additional_columns"] = additional_columns

            # Persist to file (single read-modify-write for both view and
            # additional_columns, instead of a second round trip)
            self.pm.save_client_config(client_id, client_config)

            # Update cached config if this is the current client
            if client_id == self._current_client_id:
                self._current_config = config
                self._current_view_name = view_name

            logger.debug(f"Saved table view '{view_name}' for CLIENT_{client_id}")

        except Exception:
            logger.exception(f"Failed to save table config for CLIENT_{client_id}")
            raise
```

- [x] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_table_config_manager.py -v`
Expected: PASS (2 tests)

- [x] **Step 5: Update `apply_config` to use the single-write call and drop the second read-modify-write**

Replace `ColumnConfigPanel.apply_config` (`gui/column_config_dialog.py:567-635`) with:

```python
    def apply_config(self):
        """Apply the current configuration (save + update table view)."""
        try:
            config = self._get_config_from_ui()

            if hasattr(self.parent_window, 'current_client_id') and self.parent_window.current_client_id:
                client_id = self.parent_window.current_client_id
                view_name = self.view_combo.currentText() or "Default"

                additional_columns = None
                if hasattr(self, 'additional_columns_config') and self.additional_columns_config:
                    logger.debug("Syncing UI checkbox states to config before saving...")
                    self._sync_ui_to_config()
                    additional_columns = self.additional_columns_config

                self.table_config_manager.save_config(
                    client_id, config, view_name, additional_columns=additional_columns
                )

                if additional_columns is not None:
                    enabled_cols = [col for col in additional_columns if col.get('enabled', False)]
                    disabled_cols = [col for col in additional_columns if not col.get('enabled', False)]
                    logger.debug(f"Saved additional columns config: {len(additional_columns)} columns")
                    logger.debug(f"  Enabled: {len(enabled_cols)} - {[col['csv_name'] for col in enabled_cols]}")
                    logger.debug(f"  Disabled: {len(disabled_cols)}")
                    logger.info(
                        f"Saved additional columns: {len(enabled_cols)} enabled "
                        f"({', '.join([col['csv_name'] for col in enabled_cols])})"
                    )

                if hasattr(self.parent_window, 'tableView') and \
                   hasattr(self.parent_window, 'analysis_results_df') and \
                   self.parent_window.analysis_results_df is not None:
                    self.table_config_manager.apply_config_to_view(
                        self.parent_window.tableView,
                        self.parent_window.analysis_results_df
                    )

                logger.info("Column configuration applied successfully")

                if additional_columns and any(col.get('enabled', False) for col in additional_columns):
                    QMessageBox.information(
                        self,
                        "Configuration Saved",
                        "Table configuration has been saved.\n\n"
                        "Note: If you changed additional columns, you must re-run the analysis "
                        "to see the changes in the results table."
                    )

                self.config_applied.emit()

            else:
                QMessageBox.warning(
                    self,
                    "No Client Selected",
                    "Please select a client before applying configuration."
                )

        except Exception as e:
            logger.exception("Failed to apply configuration")
            QMessageBox.critical(
                self,
                "Apply Failed",
                f"Failed to apply configuration: {e!s}"
            )
```

- [x] **Step 6: Run the full suite and lint, then commit**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Run: `ruff check gui/table_config_manager.py gui/column_config_dialog.py tests/test_table_config_manager.py`

```bash
git add gui/table_config_manager.py gui/column_config_dialog.py tests/test_table_config_manager.py
git commit -m "Fold column-config Apply into a single client_config.json write"
```

---

## Task 3: Statistics tab — delete dead `create_statistics_tab` method

**Files:**
- Modify: `gui/ui_manager.py:825-856` (delete `UIManager.create_statistics_tab`)

**Interfaces:**
- Consumes: none.
- Produces: none — pure deletion, `_create_statistics_subtab` (the method actually wired to the Statistics tab, `gui/ui_manager.py:1705`) is untouched.

`UIManager.create_statistics_tab` (`gui/ui_manager.py:825-856`) is a superseded, older `QGridLayout`-based statistics-tab builder with zero call sites anywhere in the codebase — confirmed by `grep -rn "create_statistics_tab\b" --include="*.py" .` matching only its own `def` line. It was replaced by `_create_statistics_subtab` back in PR #221 and never deleted. No test is needed for a pure dead-code deletion (nothing calls it, so nothing can regress) — the full suite passing is the verification.

- [x] **Step 1: Confirm zero call sites**

Run: `grep -rn "create_statistics_tab\b" --include="*.py" .`
Expected: exactly one match — `gui/ui_manager.py:825:    def create_statistics_tab(self, tab_widget):` (the definition itself, no callers).

- [x] **Step 2: Delete the method**

Delete lines 825-856 of `gui/ui_manager.py` (the entire `def create_statistics_tab(self, tab_widget):` method, from its `def` line up to and including the blank line right before `def set_ui_busy(self, is_busy):`).

- [x] **Step 3: Confirm it's gone and the suite still passes**

Run: `grep -rn "create_statistics_tab\b" --include="*.py" .`
Expected: no matches.

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: same pass count as before this task (no test referenced the deleted method).

Run: `ruff check gui/ui_manager.py`

- [x] **Step 4: Commit**

```bash
git add gui/ui_manager.py
git commit -m "Delete dead create_statistics_tab (superseded by _create_statistics_subtab since #221)"
```

---

## Task 4: Statistics tab — sort + filter the SKU Summary table

**Files:**
- Modify: `gui/ui_manager.py:1817-1837` (`UIManager._create_statistics_subtab`, the "SKU Summary" section)
- Modify: `gui/main_window_pyside.py:1304-1333` (`MainWindow.update_statistics_tab`, the "SKU table" section) — add a new `_on_sku_search_changed` method
- Test: `tests/test_main_window_statistics.py` (new)

**Interfaces:**
- Consumes: `self.mw.sku_table` (existing `QTableWidget`, 6 columns: `#, SKU, Product, Total Qty, Fulfillable, Not Fulfillable`).
- Produces: `self.mw.sku_search_input` (new `QLineEdit`), `MainWindow._on_sku_search_changed(self, text: str) -> None` (new method, filters `self.sku_table` rows by substring match against columns 1 (SKU) and 2 (Product)).

The SKU Summary `QTableWidget` (`gui/ui_manager.py:1817-1837`) has no sorting and no filter — for a client with a large catalog this is the one real gap the design doc found in an otherwise-already-redesigned Statistics tab (the courier/session-totals/tag-breakdown cards shipped in PR #221). `QTableWidget.setSortingEnabled(True)` gets click-to-sort for free. A filter box needs one new `QLineEdit` above the table and a handler that hides non-matching rows.

**Gotcha this task must handle:** once `setSortingEnabled(True)` is set, Qt re-sorts the table after every `insertRow`/`setItem` call, so `update_statistics_tab`'s populate loop (which uses a running `row_idx` counter to address rows) would silently write values into the wrong (just-resorted) row. Sorting must be disabled for the duration of the populate loop and re-enabled after.

- [x] **Step 1: Write the failing test**

Create `tests/test_main_window_statistics.py`:

```python
"""Regression test: SKU Summary table search box filters by SKU or product
substring (Phase 5 Item 2's "add sort/filter to the SKU table" gap).
"""
import pytest
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from gui.main_window_pyside import MainWindow


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _make_sku_table(rows):
    table = QTableWidget()
    table.setColumnCount(3)
    for row_idx, (sku, product) in enumerate(rows):
        table.insertRow(row_idx)
        table.setItem(row_idx, 1, QTableWidgetItem(sku))
        table.setItem(row_idx, 2, QTableWidgetItem(product))
    return table


class _FakeMainWindow:
    def __init__(self, table):
        self.sku_table = table


def test_sku_search_hides_non_matching_rows():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "gadget")

    assert table.isRowHidden(0) is True
    assert table.isRowHidden(1) is False


def test_sku_search_matches_by_sku_too():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "sku-a")

    assert table.isRowHidden(0) is False
    assert table.isRowHidden(1) is True


def test_empty_search_shows_all_rows():
    table = _make_sku_table([("SKU-A", "Widget A"), ("SKU-B", "Gadget B")])
    mw = _FakeMainWindow(table)

    MainWindow._on_sku_search_changed(mw, "")

    assert table.isRowHidden(0) is False
    assert table.isRowHidden(1) is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_statistics.py -v`
Expected: FAIL — `AttributeError: type object 'MainWindow' has no attribute '_on_sku_search_changed'`

- [x] **Step 3: Add the search box and enable sorting in `_create_statistics_subtab`**

In `gui/ui_manager.py`, replace the "SKU Summary" block (`gui/ui_manager.py:1817-1837`) with:

```python
        # ── 5. SKU Summary ─────────────────────────────────────────────────
        sku_group = QGroupBox("SKU Summary")
        sku_layout = QVBoxLayout(sku_group)
        sku_layout.setContentsMargins(8, 8, 8, 8)

        self.mw.sku_search_input = QLineEdit()
        self.mw.sku_search_input.setPlaceholderText("Filter by SKU or product...")
        self.mw.sku_search_input.textChanged.connect(self.mw._on_sku_search_changed)
        sku_layout.addWidget(self.mw.sku_search_input)

        self.mw.sku_table = QTableWidget()
        self.mw.sku_table.setColumnCount(6)
        self.mw.sku_table.setHorizontalHeaderLabels(
            ["#", "SKU", "Product", "Total Qty", "Fulfillable", "Not Fulfillable"]
        )
        self.mw.sku_table.horizontalHeader().setStretchLastSection(False)
        self.mw.sku_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.mw.sku_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mw.sku_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mw.sku_table.setAlternatingRowColors(True)
        self.mw.sku_table.verticalHeader().setVisible(False)
        self.mw.sku_table.setSortingEnabled(True)
        self.mw.sku_table.setMinimumHeight(200)
        sku_layout.addWidget(self.mw.sku_table)
        layout.addWidget(sku_group, 1)
```

(`QLineEdit` and `QHeaderView` are already imported at the top of `gui/ui_manager.py` — no import changes needed there.)

- [x] **Step 4: Guard the populate loop against sorting, and add the filter handler**

In `gui/main_window_pyside.py`, replace the "SKU table" block inside `update_statistics_tab` (`gui/main_window_pyside.py:1304-1333`) with:

```python
        # === 4. SKU table ===
        if hasattr(self, "sku_table"):
            self.sku_table.setSortingEnabled(False)
            self.sku_table.setRowCount(0)
            sku_summary = self.analysis_stats.get("sku_summary") or []
            for row_idx, sku_data in enumerate(sku_summary):
                self.sku_table.insertRow(row_idx)

                num_item = QTableWidgetItem(str(row_idx + 1))
                num_item.setTextAlignment(Qt.AlignCenter)
                self.sku_table.setItem(row_idx, 0, num_item)

                self.sku_table.setItem(
                    row_idx, 1, QTableWidgetItem(str(sku_data.get("SKU", "N/A")))
                )

                product = sku_data.get("Warehouse_Name", "")
                if not product or (hasattr(pd, "isna") and pd.isna(product)):
                    product = sku_data.get("Product_Name", "N/A")
                self.sku_table.setItem(row_idx, 2, QTableWidgetItem(str(product)))

                for col_idx, key in enumerate(
                    ["Total_Quantity", "Fulfillable_Items", "Not_Fulfillable_Items"],
                    start=3,
                ):
                    val_item = QTableWidgetItem(str(sku_data.get(key, 0)))
                    val_item.setTextAlignment(Qt.AlignCenter)
                    self.sku_table.setItem(row_idx, col_idx, val_item)

            self.sku_table.resizeColumnToContents(0)
            self.sku_table.resizeColumnToContents(1)
            self.sku_table.setSortingEnabled(True)
            if hasattr(self, "sku_search_input"):
                self.sku_search_input.clear()

    def _on_sku_search_changed(self, text: str):
        """Filter the SKU Summary table by SKU/product substring."""
        text = text.strip().lower()
        for row in range(self.sku_table.rowCount()):
            sku_item = self.sku_table.item(row, 1)
            product_item = self.sku_table.item(row, 2)
            sku_text = sku_item.text().lower() if sku_item else ""
            product_text = product_item.text().lower() if product_item else ""
            matches = not text or text in sku_text or text in product_text
            self.sku_table.setRowHidden(row, not matches)
```

(`_on_sku_search_changed` is a new method placed directly after `update_statistics_tab` — mind the indentation, both are `MainWindow` methods at the same nesting level.)

Also add `self.sku_table.setRowCount(0)` staying as-is in `_clear_statistics_view` (`gui/main_window_pyside.py:1355-1356`) — no change needed there, clearing rows with sorting left enabled is harmless (no populate loop involved).

- [x] **Step 5: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_statistics.py -v`
Expected: PASS (3 tests)

- [x] **Step 6: Run the full suite and lint, then commit**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Run: `ruff check gui/ui_manager.py gui/main_window_pyside.py tests/test_main_window_statistics.py`

```bash
git add gui/ui_manager.py gui/main_window_pyside.py tests/test_main_window_statistics.py
git commit -m "Add sort + SKU/product filter to the Statistics SKU Summary table"
```

---

## Task 5: Add Product to Order dialog — drop the info box, consolidate to one form

**Files:**
- Modify: `gui/add_product_dialog.py`
- Test: `tests/test_add_product_dialog.py` (new)

**Interfaces:**
- Consumes: nothing new — `AddProductDialog.__init__(self, parent, analysis_df, stock_df, live_stock)` signature is unchanged.
- Produces: same public surface as before (`order_input`, `sku_input`, `quantity_spin`, `order_status_label`, `product_info_label`, `warning_box`, `add_btn`, `_validate()`, `_on_add_clicked()`, `get_result()`) — `info_box` and the three `_create_*_section` helper methods are removed, nothing outside this file referenced them (`grep -rn "_create_order_section\|_create_product_section\|_create_quantity_section\|_create_info_box\|\.info_box\b"` outside `gui/add_product_dialog.py` returns no matches).

The design doc's backend trace confirmed the info box's claims are accurate but redundant with the method's own docstring — safe to remove. The three `QGroupBox` sections collapse into one `QFormLayout`, dropping ~120 lines of repeated `QGroupBox`/`QVBoxLayout`/label-repeating-the-groupbox-title boilerplate. The hardcoded `resize(500, 500)` is dropped in favor of `setMinimumWidth(420)` plus Qt's own layout-driven `sizeHint()` — with the info box and two extra group boxes gone, the dialog needs meaningfully less vertical space, and there's no principled fixed number to replace 500 with (this is a judgment call, not the design doc calling out a specific replacement value).

- [x] **Step 1: Write the failing test**

Create `tests/test_add_product_dialog.py`:

```python
"""Regression test: Add Product to Order dialog drops the static info box
and consolidates its three QGroupBox sections into one QFormLayout (Phase 5
Item 3) -- the live status labels and stock-warning box keep working
unchanged since the backend behavior they describe wasn't touched.
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from gui.add_product_dialog import AddProductDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog():
    analysis_df = pd.DataFrame([
        {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"},
    ])
    stock_df = pd.DataFrame([
        {"SKU": "SKU-A", "Product_Name": "Widget A"},
    ])
    live_stock = {"SKU-A": 2}
    return AddProductDialog(None, analysis_df, stock_df, live_stock)


def test_info_box_and_group_boxes_are_gone(dialog):
    assert not hasattr(dialog, "info_box")
    assert dialog.findChildren(QGroupBox) == []


def test_order_status_label_still_updates(dialog):
    dialog.order_input.setText("1001")
    assert "Order found" in dialog.order_status_label.text()


def test_low_stock_warning_still_shows(dialog):
    dialog.sku_input.setText("SKU-A")
    assert dialog.warning_box.isVisible()
    assert "low stock" in dialog.warning_box.text().lower()
```

- [x] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_add_product_dialog.py -v`
Expected: FAIL — `test_info_box_and_group_boxes_are_gone` fails (`hasattr(dialog, "info_box")` is `True`, and `findChildren(QGroupBox)` returns 3 group boxes).

- [x] **Step 3: Rewrite `setup_ui` around a single `QFormLayout`, and drop the removed helpers**

In `gui/add_product_dialog.py`, change the import block (lines 15-27) — remove `QGroupBox`, add `QFormLayout`:

```python
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
```

Replace `setup_ui` (`gui/add_product_dialog.py:60-86`) with:

```python
    def setup_ui(self):
        """Setup dialog UI components."""
        self.setWindowTitle("Add Product to Order")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        self._build_form(form_layout)
        layout.addLayout(form_layout)

        self.warning_box = self._create_warning_box()
        self.warning_box.setVisible(False)
        layout.addWidget(self.warning_box)

        layout.addWidget(self._create_buttons())
```

Replace `_create_order_section`, `_create_product_section`, and `_create_quantity_section` (`gui/add_product_dialog.py:88-137`) with a single `_build_form` method:

```python
    def _build_form(self, form_layout: QFormLayout):
        """Populate the order/SKU/quantity form rows."""
        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("Type order number... (e.g., 1001)")
        self.order_input.textChanged.connect(self._on_order_changed)
        form_layout.addRow("Order Number:", self.order_input)

        self.order_status_label = QLabel("")
        form_layout.addRow("", self.order_status_label)

        self.sku_input = QLineEdit()
        self.sku_input.setPlaceholderText("Type SKU... (e.g., SKU-HAT)")
        self.sku_input.textChanged.connect(self._on_sku_changed)
        form_layout.addRow("Product SKU:", self.sku_input)

        self.product_info_label = QLabel("")
        form_layout.addRow("", self.product_info_label)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(9999)
        self.quantity_spin.setValue(1)
        form_layout.addRow("Quantity:", self.quantity_spin)
```

Delete `_create_info_box` (`gui/add_product_dialog.py:157-181`) entirely — nothing else calls it after Step 3's `setup_ui` rewrite stops referencing it.

`_create_warning_box`, `_create_buttons`, `setup_autocompleters`, `_on_order_changed`, `_on_sku_changed`, `_on_add_clicked`, `_validate`, and `get_result` are all unchanged — they only reference `order_input`, `sku_input`, `quantity_spin`, `order_status_label`, `product_info_label`, and `warning_box`, all of which still exist with the same names.

- [x] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_add_product_dialog.py -v`
Expected: PASS (3 tests)

- [x] **Step 5: Run the full suite and lint, then commit**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Run: `ruff check gui/add_product_dialog.py tests/test_add_product_dialog.py`

```bash
git add gui/add_product_dialog.py tests/test_add_product_dialog.py
git commit -m "Simplify Add Product to Order dialog to one QFormLayout, drop info box"
```

---

## Self-Review

**Spec coverage:**
- Item 1 (Manage Table Columns: grouping, display names, backend single-write) → Tasks 1 and 2.
- Item 2 (Statistics tab: dead code, sort/filter) → Tasks 3 and 4.
- Item 3 (Add Product to Order: remove info box, QFormLayout, resize) → Task 5.
- Testing section's per-item guidance (round-trip test for Item 1's write path, sort-enabled/filter test for Item 2, `_validate`/`_on_add_clicked`-adjacent test for Item 3) → covered by each task's test file.

**Placeholder scan:** no TBD/"add appropriate handling"/bare references — every step has real code, real file:line anchors, and real run commands.

**Type consistency:** `TableConfigManager.save_config`'s new `additional_columns` parameter name and `None`-default match between Task 2's implementation and its caller update in the same task. `MainWindow._on_sku_search_changed(self, text: str)` signature matches both its `textChanged.connect(self.mw._on_sku_search_changed)` wiring in Task 4 Step 3 and its test calls in Task 4 Step 1. `_CATEGORY_HEADER_MARKER`/`COLUMN_CATEGORIES`/`COLUMN_DISPLAY_NAMES`/`CATEGORY_ORDER` names are consistent between Task 1's constants (Step 3) and every consumer (Steps 4-9) and test (Step 1).
