# Phase 11 — Shopify tool bugfixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five defects reported against the post-#327 Windows build —
Add Product dead in a resumed session, the filter menu hidden by the selection
bar, inventory memory's false alarms, a file slot that cannot be emptied, and
packaging write-off that cannot be exported on its own.

**Architecture:** Five independent fixes in existing flows, ordered
correctness-first. Each is a root-cause fix at a single shared point, not a
patch at the reported symptom. No new modules; no change under `shared/`.

**Tech Stack:** PySide6, pandas, pytest (`QT_QPA_PLATFORM=offscreen`), xlwt,
plain CSS/JS for the Results web tier.

**Spec:** `docs/superpowers/specs/2026-09-20-phase11-shopify-bugfixes-design.md`
— read it first. It carries the diagnosis behind every task here.

## Global Constraints

- **Branch:** `worktree-phase11-bugfixes`. PR-only; never commit to `main`.
- **Run tests:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` from the
  worktree root. A single test: append `tests/test_x.py::test_name -v`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must be clean.
- `python` is **not** on `PATH`. Always `.venv/bin/python`.
- **Never edit anything under `shared/`** — it is synced from `packing-tool`
  and a local edit is silently overwritten.
- **No hardcoded colours.** Use `get_theme_manager().get_current_theme()`
  tokens (`theme.text_secondary`, `theme.border`, …), never `#666`/`gray`.
- **Editor hook gotcha:** a `PostToolUse` hook runs `ruff format` +
  `check --fix` on every Edit/Write of a `.py` file. It will **delete an import
  you add before the code that uses it exists**. Add the import and its first
  use in the same edit.
- **Version string:** do **not** bump it. This repo bumps per phase, not per
  PR, and 1.9.9.1 stands.
- After the last task, run `.venv/bin/python -m graphify update .` if
  `graphify` is on PATH (per CLAUDE.md); skip silently if it is not.

---

### Task 1: Inventory memory stops crying wolf

Spec §3. Two independent comparison bugs in `_check_inventory_anomaly` make the
"Use this stock file?" confirm fire on every single stock load.

**Files:**
- Modify: `shopify_tool/core.py` (add `inventory_total_units` next to
  `build_inventory_snapshot`, around line 958)
- Modify: `gui/file_handler.py:288-318` (`_check_inventory_anomaly`)
- Test: `tests/test_file_handler.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `shopify_tool.core.inventory_total_units(stock_df: pd.DataFrame) -> float`
  — used only within this task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_file_handler.py`. The `main_window` fixture is already
defined at the top of that file.

Add `import pandas as pd` to that file's **existing top-of-file import block**,
not above the new tests — ruff's default rules include E402, so a module-level
import further down fails the lint gate.

```python
def _memory(skus: dict, total: int) -> dict:
    return {"enabled": True, "skus": skus, "total_units": total}


def test_a_sku_listed_once_per_location_is_not_a_hundred_percent_jump(main_window):
    """The stock file lists each SKU once per warehouse location. Memory counts
    one row per SKU, so summing raw rows read as a doubling on every load."""
    handler = main_window.file_handler
    new_stock = pd.DataFrame(
        {"SKU": ["A", "A", "B", "B"], "Stock": [10, 10, 5, 5]}
    )
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 10.0, "B": 5.0}, 15)
    )
    assert is_anomaly is False, msg


def test_float_skus_from_pandas_still_match_normalised_memory(main_window):
    """pandas reads numeric SKUs as float64; memory stores normalise_sku'd
    strings. Comparing them raw made every overlap 0%."""
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": [5170.0, 5171.0], "Stock": [4, 6]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"5170": 4.0, "5171": 6.0}, 10)
    )
    assert is_anomaly is False, msg


def test_a_real_collapse_in_stock_still_asks(main_window):
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": ["A", "B"], "Stock": [1, 1]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 50.0, "B": 50.0}, 100)
    )
    assert is_anomaly is True
    assert "-98%" in msg


def test_a_genuinely_different_client_file_still_asks(main_window):
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": ["X", "Y"], "Stock": [10, 10]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 10.0, "B": 10.0}, 20)
    )
    assert is_anomaly is True
    assert "0% SKU overlap" in msg
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_handler.py -k "location or float_skus or collapse or different_client" -v`

Expected: the first two FAIL (`assert False is False` fails — an anomaly was
raised), the last two PASS already.

- [ ] **Step 3: Add the shared counter in `shopify_tool/core.py`**

Insert directly after `build_inventory_snapshot` ends (after its `return snapshot`):

```python
def inventory_total_units(stock_df: pd.DataFrame) -> float:
    """Total units in a stock frame, counted the way inventory memory counts.

    One row per SKU -- a stock file lists a SKU once per warehouse location --
    and negatives clamped to zero. Those are exactly the two rules
    build_inventory_snapshot and save_inventory_memory apply between them, so
    a freshly loaded file and a saved snapshot are only comparable when both
    sides use this. Summing raw rows instead made a SKU listed twice read as a
    100% jump on every single load.
    """
    if stock_df is None or not {"SKU", "Stock"} <= set(stock_df.columns):
        return 0.0
    per_sku = pd.to_numeric(
        stock_df.groupby("SKU")["Stock"].last(), errors="coerce"
    ).dropna()
    return float(per_sku.clip(lower=0).sum())
```

- [ ] **Step 4: Fix both comparisons in `gui/file_handler.py`**

In `_check_inventory_anomaly`, replace the `new_skus` assignment and the
`new_total` assignment. `core` is already imported in this module; add
`normalize_sku` to the existing `from shopify_tool.csv_utils import ...` line if
there is one, otherwise import it inside the function beside its use.

```python
        old_skus = set(memory["skus"])
        # Memory stores normalise_sku'd keys (profile_manager.save_inventory_memory).
        # pandas reads numeric SKUs as float64, so an un-normalised 5170.0 never
        # matched a stored "5170" and every overlap read as 0%.
        new_skus = (
            {normalize_sku(s) for s in new_stock_df["SKU"].unique()}
            if "SKU" in new_stock_df.columns
            else set()
        )
        overlap = len(old_skus & new_skus) / max(len(old_skus), 1)
```

```python
        old_total = memory.get("total_units", 0)
        new_total = core.inventory_total_units(new_stock_df)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_handler.py -v`
Expected: PASS, all of them.

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/core.py gui/file_handler.py tests/test_file_handler.py
git commit -m "Inventory memory: count the new file the way memory counts itself"
```

---

### Task 2: A resumed session remembers its input files

Spec §1. `load_existing_session` restores the analysis and nothing else, so
`stock_file_path` stays `None`, `update_ui_state` disables *Add Product to
Order*, and the Setup screen shows two empty slots for a session that ran.

**Files:**
- Modify: `gui/main_window_pyside.py` (`load_existing_session`, ~line 873)
- Modify: `gui/actions_handler.py:1136-1142` (the two silent returns)
- Modify: `gui/add_product_dialog.py:152-172` (`setup_autocompleters`)
- Test: create `tests/test_session_restore.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `MainWindow._restore_session_inputs(session_path: str) -> None` —
  used only within this task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_restore.py`:

```python
"""Opening a past session restores what it ran on, not just its results.

The bug: load_existing_session set analysis_results_df and left
stock_file_path at None, so update_ui_state disabled Add Product to Order
in a session that plainly had a stock file.
"""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    win.profile_manager.create_client_profile("acme", "Client Acme")
    win.current_client_id = "acme"
    win.current_client_config = win.profile_manager.load_shopify_config("acme")
    win.load_client_config("acme")
    yield win
    win.close()


def _session_with_inputs(win):
    """A session directory holding the two files an analysis copies into it."""
    path = win.session_manager.create_session("acme")
    input_dir = win.session_manager.get_input_dir(path)
    pd.DataFrame({"Order_Number": [1], "SKU": ["A"], "Quantity": [1]}).to_csv(
        input_dir / "orders_export.csv", index=False
    )
    pd.DataFrame({"SKU": ["A"], "Stock": [5]}).to_csv(
        input_dir / "inventory.csv", index=False
    )
    win.session_manager.update_session_info(
        path, {"orders_file": "orders_export.csv", "stock_file": "inventory.csv"}
    )
    return path


def test_restoring_a_session_points_at_the_files_it_ran_on(main_window):
    path = _session_with_inputs(main_window)
    main_window._restore_session_inputs(path)

    assert main_window.stock_file_path is not None
    assert main_window.stock_file_path.endswith("inventory.csv")
    assert main_window.orders_file_path.endswith("orders_export.csv")


def test_add_product_is_reachable_in_a_restored_session(main_window):
    path = _session_with_inputs(main_window)
    main_window.session_path = path
    main_window.analysis_results_df = pd.DataFrame(
        {"Order_Number": [1], "SKU": ["A"], "Final_Stock": [4]}
    )
    main_window._restore_session_inputs(path)
    main_window.update_ui_state()

    assert main_window.add_product_button_tab2.isEnabled() is True


def test_a_session_whose_input_files_are_gone_restores_nothing(main_window):
    path = main_window.session_manager.create_session("acme")
    main_window._restore_session_inputs(path)

    assert main_window.stock_file_path is None
    assert main_window.orders_file_path is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_restore.py -v`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute '_restore_session_inputs'`.

`SessionManager.create_session(client_id)` takes one argument and names the
directory itself (`YYYY-MM-DD_N`). `get_session_subdirectory` **raises** when
the subdirectory is absent, which is why `_restore_session_inputs` wraps
`get_input_dir` in a `try`.

- [ ] **Step 3: Add the restore method to `gui/main_window_pyside.py`**

Add this method to `MainWindow`, directly above `load_existing_session`:

```python
    def _restore_session_inputs(self, session_path: str) -> None:
        """Point the file paths and slots at the files this session ran on.

        run_full_analysis copies both inputs into <session>/input/ under fixed
        names and records them in session_info.json. Without this, a resumed
        session had results but no stock_file_path, which left Add Product to
        Order greyed out with nothing on screen saying why.
        """
        try:
            input_dir = self.session_manager.get_input_dir(session_path)
        except Exception:
            logger.exception("Could not resolve the session input directory")
            return

        info = self.session_manager.get_session_info(session_path) or {}
        for kind, default_name in (
            ("orders", "orders_export.csv"),
            ("stock", "inventory.csv"),
        ):
            recorded = info.get(f"{kind}_file") or default_name
            path = Path(input_dir) / recorded
            if not path.exists():
                continue
            setattr(self, f"{kind}_file_path", str(path))
            # validate_file drives the slot into its loaded or invalid face and
            # is the same call the file pickers make.
            self.file_handler.validate_file(kind)
        self.file_handler.check_files_ready()
```

`Path` and `logger` are already imported in this module — confirm before
adding either.

- [ ] **Step 4: Call it from `load_existing_session`**

Inside `load_existing_session`, in the `if session_info:` branch, call it before
the analysis is loaded so the slots are right either way:

```python
            if session_info:
                self._restore_session_inputs(session_path)

                # Try to load analysis data if it exists
                if self._load_session_analysis(session_path):
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_restore.py -v`
Expected: PASS.

- [ ] **Step 6: Give Add Product a failure path**

In `gui/actions_handler.py`, replace the two silent returns in
`show_add_product_dialog`. `show_error` is already imported in this module.

```python
        if (
            not hasattr(self.mw, "analysis_results_df")
            or self.mw.analysis_results_df is None
        ):
            self.log.warning("show_add_product_dialog called with no analysis data")
            show_error(
                self.mw,
                "There are no analysis results to add a product to",
                "Run the analysis first.",
            )
            return

        if not hasattr(self.mw, "stock_file_path") or not self.mw.stock_file_path:
            self.log.warning("show_add_product_dialog called with no stock file")
            show_error(
                self.mw,
                "This session's stock file couldn't be found",
                "Load a stock file in Setup, then try again.",
            )
            return
```

- [ ] **Step 7: Guard the dialog's unguarded column reads**

`AddProductDialog.__init__` runs outside the caller's `try`, so a `KeyError`
here reaches the Qt event loop and the user sees nothing happen at all. In
`gui/add_product_dialog.py`, replace the two hard indexes in
`setup_autocompleters`:

```python
    def setup_autocompleters(self):
        """Setup autocomplete for order and SKU inputs.

        Both frames are built by the caller from files on a network share, so
        a missing column is a real possibility. It used to raise out of
        __init__ into the event loop, where the dialog simply never appeared.
        """
        for frame, column, what in (
            (self.analysis_df, "Order_Number", "analysis results"),
            (self.stock_df, "SKU", "stock file"),
        ):
            if frame is None or column not in frame.columns:
                raise ValueError(f"The {what} has no {column} column")

        order_numbers = self.analysis_df["Order_Number"].astype(str).unique().tolist()
```

Then in `gui/actions_handler.py`, wrap the construction so the error is shown
rather than lost — replace the `dialog = AddProductDialog(...)` statement and
the `if dialog.exec()` that follows it:

```python
        try:
            dialog = AddProductDialog(
                parent=self.mw,
                analysis_df=self.mw.analysis_results_df,
                stock_df=stock_df,
                live_stock=live_stock,
                low_stock_threshold=self.mw.active_profile_config.get(
                    "settings", {}
                ).get("low_stock_threshold", 5),
            )
        except Exception:
            self.log.exception("Add Product dialog could not be built")
            show_error(
                self.mw, "Add Product couldn't be opened", "Details are in Logs."
            )
            return

        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            if result:
                self._add_product_to_order(result, stock_df, live_stock)
```

- [ ] **Step 8: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS. `tests/test_add_product_dialog.py` exercises the dialog — if a
case there builds it without one of the two columns, update that test to expect
`ValueError`, because that is now the contract.

- [ ] **Step 9: Commit**

```bash
git add gui/main_window_pyside.py gui/actions_handler.py gui/add_product_dialog.py tests/test_session_restore.py tests/test_add_product_dialog.py
git commit -m "Add Product: a resumed session remembers the files it ran on"
```

---

### Task 3: Packaging write-off can be exported on its own

Spec §5. Today packaging SKUs are concatenated into the product export and the
only control is a single checkbox. The owner asked for a separate `.xls`.

**Files:**
- Modify: `shopify_tool/stock_export.py:145-300` (`create_stock_export`)
- Modify: `gui/report_selection_dialog.py:269-282` and `:360-366`
- Modify: `gui/actions_handler.py:768-783`
- Modify: `shopify_tool/core.py:1591`
- Test: `tests/test_stock_export.py` (append; existing writeoff cases at :243-:295 need updating)

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `create_stock_export(..., writeoff_mode: str = "off", tag_categories=None)`
  where `writeoff_mode` is `"off" | "merged" | "separate"`, replacing
  `apply_writeoff: bool`. The report config key is `"writeoff_mode"`.

- [ ] **Step 1: Write the failing tests**

Append a new class to `tests/test_stock_export.py`. This file's idiom: tests are
methods on a `Test*` class taking `tmp_path`, data comes from the module-level
`_analysis_df(rows)` helper, and results are read back **by column index**
through `_read(path)` using the `COL_SKU` / `COL_QTY` constants at line 16 —
the ERP detects columns positionally, so nothing reads by header name. No
new imports are needed.

```python
class TestWriteoffModes:
    """Packaging write-off: out, among the product rows, or beside them."""

    CONFIG = {
        "version": 2,
        "categories": {
            "packaging": {
                "tags": ["BOX"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 1}]},
                },
            }
        },
    }

    def _df(self):
        return _analysis_df([
            {"Order_Number": "#1", "SKU": "A1", "Quantity": 2,
             "Internal_Tags": '["BOX"]'},
        ])

    def test_separate_mode_writes_packaging_to_its_own_file(self, tmp_path):
        out = tmp_path / "export.xls"
        create_stock_export(
            self._df(), str(out), writeoff_mode="separate",
            tag_categories=self.CONFIG,
        )
        packaging = tmp_path / "export_packaging.xls"
        assert packaging.exists()

        products = list(_read(out).iloc[:, COL_SKU])
        packs = list(_read(packaging).iloc[:, COL_SKU])
        assert "PKG-BOX" not in products
        assert products == ["A1"]
        assert packs == ["PKG-BOX"]

    def test_separate_mode_with_no_packaging_writes_one_file(self, tmp_path):
        out = tmp_path / "export.xls"
        create_stock_export(
            self._df(), str(out), writeoff_mode="separate", tag_categories={}
        )
        assert out.exists()
        assert not (tmp_path / "export_packaging.xls").exists()

    def test_merged_mode_keeps_both_in_one_file(self, tmp_path):
        out = tmp_path / "export.xls"
        create_stock_export(
            self._df(), str(out), writeoff_mode="merged",
            tag_categories=self.CONFIG,
        )
        assert not (tmp_path / "export_packaging.xls").exists()
        assert "PKG-BOX" in list(_read(out).iloc[:, COL_SKU])

    def test_off_mode_leaves_packaging_out_entirely(self, tmp_path):
        out = tmp_path / "export.xls"
        create_stock_export(
            self._df(), str(out), writeoff_mode="off", tag_categories=self.CONFIG,
        )
        assert not (tmp_path / "export_packaging.xls").exists()
        assert "PKG-BOX" not in list(_read(out).iloc[:, COL_SKU])
```

Also change the three existing calls at :243, :269 and :295 from
`apply_writeoff=True` to `writeoff_mode="merged"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -v`
Expected: FAIL with `TypeError: create_stock_export() got an unexpected keyword argument 'writeoff_mode'`.

- [ ] **Step 3: Extract the writer, then branch on the mode**

In `shopify_tool/stock_export.py`, lift the xlwt block (currently inline at
:280-292) into a module-level helper placed just above `create_stock_export`:

```python
def _write_xls(export_df, output_file) -> None:
    """One sheet, header row, then the rows. The warehouse system reads the
    first sheet of the file and nothing else, which is why a separate
    write-off goes in a separate file rather than a second sheet."""
    import xlwt

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")
    for col_num, value in enumerate(export_df.columns):
        sheet.write(0, col_num, value)
    # enumerate, not iterrows() index: export_df may carry a gapped index
    # (e.g. from the Quantity > 0 filter), which would skip/misplace rows.
    for row_num, (_, row) in enumerate(export_df.iterrows()):
        for col_num, value in enumerate(row):
            sheet.write(row_num + 1, col_num, value)
    workbook.save(output_file)
```

Change the signature (`apply_writeoff=False` → `writeoff_mode="off"`) and
update the docstring's `apply_writeoff` entries to describe the three modes.

Replace the `if apply_writeoff and tag_categories:` block with:

```python
        # Packaging write-off: either among the product rows or beside them.
        if writeoff_mode in ("merged", "separate") and tag_categories:
            logger.info(f"Calculating packaging materials for report '{report_name}'")
            from shopify_tool.sku_writeoff import calculate_writeoff_quantities

            writeoff_df = calculate_writeoff_quantities(filtered_items, tag_categories)

            if writeoff_df.empty:
                logger.info(
                    "No packaging materials required (no writeoff mappings triggered)"
                )
            else:
                packaging_rows = _finalize_export_df(
                    pd.DataFrame(
                        {
                            "Артикул": writeoff_df["SKU"],
                            QTY_COL: writeoff_df["Writeoff_Quantity"],
                        }
                    )
                )
                if writeoff_mode == "merged":
                    export_df = pd.concat(
                        [export_df, packaging_rows], ignore_index=True
                    )
                    logger.info(
                        f"Added {len(packaging_rows)} packaging SKUs to export "
                        f"(total: {packaging_rows[QTY_COL].sum()} units)"
                    )
                else:
                    packaging_file = _packaging_path(output_file)
                    _write_xls(packaging_rows, packaging_file)
                    logger.info(
                        f"Wrote {len(packaging_rows)} packaging SKUs to "
                        f"'{packaging_file}'"
                    )
```

And the path helper, beside `_write_xls`:

```python
def _packaging_path(output_file):
    """Sibling of the product export: export.xls -> export_packaging.xls."""
    from pathlib import Path

    p = Path(output_file)
    return str(p.with_name(f"{p.stem}_packaging{p.suffix}"))
```

Finally replace the inline save at the end of the function with
`_write_xls(export_df, output_file)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -v`
Expected: PASS.

- [ ] **Step 5: Update the three callers**

`gui/actions_handler.py`, in the `elif report_type == "stock_exports":` branch:

```python
                writeoff_mode = report_config.get("writeoff_mode", "off")
                tag_categories = self.mw.active_profile_config.get("tag_categories", {})

                stock_export.create_stock_export(
                    analysis_df=self.mw.analysis_results_df,
                    output_file=output_file,
                    report_name=report_name,
                    filters=filters,
                    writeoff_mode=writeoff_mode,
                    tag_categories=tag_categories,
                )
```

`shopify_tool/core.py:1591` — same rename:

```python
        writeoff_mode = report_config.get("writeoff_mode", "off")
```

and pass `writeoff_mode=writeoff_mode` at the `create_stock_export` call below
it. Update that function's docstring line about `'apply_writeoff'` to name
`'writeoff_mode'` and its three values.

- [ ] **Step 6: Replace the checkbox with the three choices**

In `gui/report_selection_dialog.py`, replace the `writeoff_checkbox` block:

```python
        writeoff_group = QGroupBox("Packaging write-off")
        writeoff_layout = QVBoxLayout(writeoff_group)

        self.writeoff_off = QRadioButton("Leave packaging materials out")
        self.writeoff_merged = QRadioButton("Include them in the stock export")
        self.writeoff_separate = QRadioButton("Write them to a file of their own")
        self.writeoff_off.setChecked(True)
        self.writeoff_separate.setToolTip(
            "Packaging SKUs go to <name>_packaging.xls beside the stock export, "
            "so the warehouse system imports the two separately."
        )
        for button in (
            self.writeoff_off,
            self.writeoff_merged,
            self.writeoff_separate,
        ):
            writeoff_layout.addWidget(button)

        layout.addWidget(writeoff_group)
```

Add `QRadioButton` to the existing `PySide6.QtWidgets` import line in the same
edit — the format hook strips an import whose use does not yet exist.

Then replace the entry line at :364:

```python
            if kind == "stock_exports" and hasattr(self, "writeoff_separate"):
                entry["writeoff_mode"] = (
                    "separate"
                    if self.writeoff_separate.isChecked()
                    else "merged"
                    if self.writeoff_merged.isChecked()
                    else "off"
                )
```

- [ ] **Step 7: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Run: `.venv/bin/ruff check . --exclude shared`
Expected: PASS, clean. Grep for any surviving `apply_writeoff`:
`grep -rn "apply_writeoff" --include=*.py .` should return nothing outside
`shopify_tool/sku_writeoff.py`, where `apply_writeoff_to_stock_export` is an
unrelated function name and stays.

- [ ] **Step 8: Commit**

```bash
git add shopify_tool/stock_export.py shopify_tool/core.py gui/actions_handler.py gui/report_selection_dialog.py tests/test_stock_export.py
git commit -m "Stock export: packaging write-off can go to a file of its own"
```

---

### Task 4: A file slot can be emptied

Spec §4. `FileSlot.clear()` exists and works; no button reaches it, so a wrong
file can be replaced but never removed.

**Files:**
- Modify: `gui/components/file_slot.py` (signal, two buttons)
- Modify: `gui/main_window_pyside.py:326-344` (the per-slot wiring loop)
- Modify: `gui/file_handler.py` (add `clear_file`; use it at :275)
- Test: `tests/test_file_slot.py`, `tests/test_file_handler.py` (append)

**Interfaces:**
- Consumes: nothing from Tasks 1-3.
- Produces: `FileSlot.clearRequested` (a `Signal()`), `FileSlot.clear_button`
  and `FileSlot.clear_invalid_button` (both `QPushButton`), and
  `FileHandler.clear_file(file_type: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_file_slot.py`:

```python
def test_a_loaded_slot_can_be_emptied(slot, qtbot):
    slot.set_loaded(Path("/tmp/stock.csv"), "5 rows · 2 columns matched")
    emitted = []
    slot.clearRequested.connect(lambda: emitted.append(True))
    slot.clear_button.click()
    assert emitted == [True]


def test_an_invalid_slot_can_be_emptied_too(slot):
    slot.set_invalid(Path("/tmp/stock.csv"), ["Stock"], ["SKU"])
    emitted = []
    slot.clearRequested.connect(lambda: emitted.append(True))
    slot.clear_invalid_button.click()
    assert emitted == [True]
```

Append to `tests/test_file_handler.py`:

```python
def test_clearing_a_slot_forgets_the_path_and_regates_run_analysis(
    main_window, tmp_path
):
    handler = main_window.file_handler
    orders = tmp_path / "orders.csv"
    stock = tmp_path / "stock.csv"
    orders.write_text("x")
    stock.write_text("x")
    main_window.orders_file_path = str(orders)
    main_window.stock_file_path = str(stock)
    main_window.orders_slot.set_loaded(orders, "1 row")
    main_window.stock_slot.set_loaded(stock, "1 row")
    assert handler.check_files_ready() is True

    handler.clear_file("stock")

    assert main_window.stock_file_path is None
    assert main_window.stock_slot.is_valid is False
    assert main_window.run_analysis_button.isEnabled() is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_slot.py tests/test_file_handler.py -k clear -v`
Expected: FAIL with `AttributeError: 'FileSlot' object has no attribute 'clearRequested'`.

- [ ] **Step 3: Add the signal and the two buttons**

In `gui/components/file_slot.py`, add the signal beside the others:

```python
    clearRequested = Signal()
```

In `_build_loaded`, after the `replace_button` line and before `row.addStretch()`:

```python
        self.clear_button = QPushButton("Clear", page)
        self.clear_button.setToolTip("Empty this slot without choosing another file")
        self.clear_button.clicked.connect(self.clearRequested.emit)
        row.addWidget(self.clear_button)
```

In `_build_invalid`, after the `choose_other_button` line and before
`row.addStretch()`:

```python
        self.clear_invalid_button = QPushButton("Clear", page)
        self.clear_invalid_button.setToolTip(
            "Empty this slot without choosing another file"
        )
        self.clear_invalid_button.clicked.connect(self.clearRequested.emit)
        row.addWidget(self.clear_invalid_button)
```

- [ ] **Step 4: Add `clear_file` and wire the signal**

In `gui/file_handler.py`, add beside `check_files_ready`:

```python
    def clear_file(self, file_type: str) -> None:
        """Empty one slot: forget the path, reset the widget, re-gate the run.

        slot.clear() emits `changed`, which is already connected to
        check_files_ready, so Run Analysis re-gates itself.
        """
        setattr(self.mw, f"{file_type}_file_path", None)
        getattr(self.mw, f"{file_type}_slot").clear()
        self.log.info(f"Cleared the {file_type} slot")
```

Use it at the anomaly-cancel path (currently `file_handler.py:275-277`), which
does the same three things inline:

```python
                        # Cancel: clear the stock selection
                        self.clear_file("stock")
                        return
```

In `gui/main_window_pyside.py`, inside the existing `for slot, kind in (...)`
loop, beside the other connections:

```python
            slot.clearRequested.connect(
                lambda k=kind: self.file_handler.clear_file(k)
            )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_file_slot.py tests/test_file_handler.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/components/file_slot.py gui/file_handler.py gui/main_window_pyside.py tests/test_file_slot.py tests/test_file_handler.py
git commit -m "Session setup: a loaded file slot can be cleared"
```

---

### Task 5: The Results screen gets a layer scale

Spec §2. `.menu` and `.selection-bar` both sit at `z-index: 3`, so the tie is
broken by DOM order and the selection bar covers the Add filter menu.

**Files:**
- Modify: `gui/web/results.css` (every bare `z-index`: lines 174, 252, 275, 317, 353, 375, 523, 633)
- Test: `tests/test_results_document.py` (append)

**Interfaces:**
- Consumes: nothing from Tasks 1-4.
- Produces: CSS custom properties `--z-sticky`, `--z-header`, `--z-bar`,
  `--z-popover`, `--z-toast` on `:root` in `results.css`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_results_document.py`. Add `import re` and
`from pathlib import Path` to that file's **existing top-of-file import block**
— ruff's default rules include E402, so a module-level import further down
fails the lint gate.

```python
_CSS = Path(__file__).resolve().parents[1] / "gui" / "web" / "results.css"


def _layers() -> dict:
    """The named layer scale, read out of :root."""
    text = _CSS.read_text(encoding="utf-8")
    return {
        name: int(value)
        for name, value in re.findall(r"--z-([a-z]+):\s*(\d+)", text)
    }


def test_a_popover_is_never_covered_by_the_selection_bar():
    """The Add filter menu opened underneath the selection bar because the two
    tied at z-index 3 and the bar came later in the document."""
    z = _layers()
    assert z["popover"] > z["bar"] > z["header"] > z["sticky"]
    assert z["toast"] > z["popover"]


def test_no_bare_z_index_survives_in_results_css():
    text = _CSS.read_text(encoding="utf-8")
    bare = re.findall(r"z-index:\s*(\d+)", text)
    assert bare == [], f"z-index must come from the layer scale, found {bare}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_document.py -k layer -v`
Expected: FAIL — `_layers()` returns `{}` and raises `KeyError: 'popover'`.

Note `test_no_bare_z_index_survives_in_results_css` matches the `--z-…: 5`
declarations too, because they are `z-` not `z-index:`. Confirm the regex
`z-index:\s*(\d+)` does not match a custom-property line; it does not.

- [ ] **Step 3: Declare the scale**

At the top of `gui/web/results.css`, in the existing `:root` block (or a new
one directly after the theme-vars comment if there is none):

```css
/* One layer scale for every stacked surface on this screen. Two surfaces used
   to tie at 3 -- .menu and .selection-bar -- and the tie was broken by
   document order, which put the Add filter menu underneath the bar. */
:root {
  --z-sticky: 1;
  --z-header: 2;
  --z-bar: 3;
  --z-popover: 5;
  --z-toast: 6;
}
```

- [ ] **Step 4: Replace every bare z-index**

| Line (before) | Selector | New value |
|---|---|---|
| 174 | `.menu` | `var(--z-popover)` |
| 252 | `.selection-bar` | `var(--z-bar)` |
| 275 | `.bulk-popover` | `var(--z-popover)` |
| 317 | `.toast` | `var(--z-toast)` |
| 353 | `.header` | `var(--z-header)` |
| 375 | `.rows .row.selected::after` | `var(--z-sticky)` |
| 523 | `.line.line-head` | `var(--z-sticky)` |
| 633 | `.col-group` | `var(--z-sticky)` |

Keep each line's existing trailing comment. Line numbers shift as you edit —
work bottom-up, or match on the selector.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_document.py -v`
Expected: PASS, including the existing document tests — the page still renders.

- [ ] **Step 6: Commit**

```bash
git add gui/web/results.css tests/test_results_document.py
git commit -m "Results: one layer scale, so a popover is never under the bar"
```

---

### Task 6: Gate and hand off

- [ ] **Step 1: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: every test passes. Record the count — `main` was at 1722 passed
before this branch, so the number should be that plus the tests added here.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check . --exclude shared`
Expected: clean.

- [ ] **Step 3: Refresh the knowledge graph**

Run: `graphify update .`
Skip without comment if `graphify` is not on PATH.

- [ ] **Step 4: Commit anything the gate changed and push**

```bash
git add -A
git commit -m "Phase 11: test and lint gate"
git push -u origin worktree-phase11-bugfixes
```

Do **not** open the PR — Stage C reviews first, then opens it.

---

## Out of scope (do not implement)

- **The "only 1 barcode" report** (spec §6). There is no cause in the code and
  #327 already shipped the instrumentation. Changing the `blabel` rendering
  path on a hypothesis would risk breaking a path that works.
- **Interrupting a file load in flight** (spec §4). Loading is synchronous;
  making it cancellable means moving it to a worker thread.
- **The Settings form restyle** carried over from #327 §8.
- **Anything under `shared/`.**

## Note for the reviewer

Task 2 restores `orders_file_path` as well as `stock_file_path`, which
re-enables *Run Analysis* inside a resumed session. The spec argues this is the
coherent state rather than showing two empty slots for a session that plainly
ran. If the owner would rather not have Run Analysis live in a resumed session,
dropping `"orders"` from the loop in `_restore_session_inputs` is the whole
retreat.
