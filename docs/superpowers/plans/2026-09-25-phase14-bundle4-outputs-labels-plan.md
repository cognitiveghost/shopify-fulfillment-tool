# Phase 14 Bundle 4: outputs and labels. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, in this session (the runner forbids fanning out). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the ten AUDIT-04 findings, and timestamp stock-export filenames, keeping earlier versions in `old/`.

**Architecture:** Each fix goes into the module that owns the behaviour. `report_filters` owns SKU exclusion, `packing_lists` the list order, `barcode_processor` label records and label PDF names, `stock_export` export filenames and writes, and `pdf_processor` reference matching and the run summary. `gui/actions_handler._generate_single_report` and the two widgets only call these functions and show their results.

**Tech Stack:** Python 3, pandas, PySide6, xlwt/xlsxwriter, blabel + WeasyPrint, pypdf, pikepdf, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-phase14-bundle4-outputs-labels-design.md`. Read it first: its decision table (D1–D5) is binding. Background is in `docs/audit/04-outputs.md`.

## Global Constraints

- Work in worktree `.claude/worktrees/phase14-bundle4-outputs-labels`, branch `phase14-bundle4-outputs-labels`. Never `cd` out of it.
- git: `/usr/bin/git`, one plain git command per Bash call. Commit with `/usr/bin/git commit -F <abs path in $CLAUDE_JOB_DIR/tmp>`. Every commit message ends with the `Co-Authored-By` line from the session's attribution reminder.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no <target>`. If `.venv` is missing, run `ln -s /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.venv .venv`. The full suite takes ~4 min, so run it in the background.
- Never edit `shared/`. Nothing in this plan needs it.
- No hardcoded colours: use `get_theme_manager().get_current_theme().status_warning`.
- Audit proof tests live in `tests/audit/test_04_outputs.py`. **Remove a test's `@pytest.mark.xfail(...)` line in the same task that fixes it**. `strict=True` means an xfail that starts passing fails the suite.
- Stock-export stamp format: `<stem>_YYYY-MM-DD_HHMM.xls`, local time (`datetime.now().astimezone()`). Earlier versions move to `<dir>/old/`.
- Packing-list filenames do **not** change (Packing Tool keys lists by filename stem).
- Keep the unmarked "verified correct" tests in `tests/audit/test_04_outputs.py` passing, especially `test_barcode_value_is_the_order_number_unchanged` and `test_postone_id_beats_the_name_fallback`.

## Review Focus

1. **A report name containing regex characters** (`ALL (DHL)+.xls`): `prepare_export_path` must `re.escape` the stem, and must not move files of a report whose name only starts with the same stem (`ALL_DHL.xls` beside `ALL.xls`). Pinned in Task 7.
2. **A same-minute re-export**: the stamped name already exists. It moves to `old/` and the new file is written; neither step raises. Pinned in Task 7.
3. **Bulgarian/Cyrillic names in the name fallback**: `Иван Петров` must not match a page for `Иван Петрова`. Python `\w` is Unicode-aware on `str`, and the test proves it. Pinned in Task 10.
4. **Removing an empty list whose XLSX is open in Excel** (Windows `PermissionError` on unlink): the operator gets the "close it" error, not "old files were removed". Pinned in Task 3.
5. **`exclude_skus` given as `"07, 8 ,"` or containing NaN SKUs in the frame**: parsing strips, drops blanks, and NaN SKUs are kept (never excluded). Pinned in Task 1.

---

### Task 1: One SKU exclusion for XLSX and JSON (AUDIT-04-4)

**Files:**
- Modify: `shopify_tool/report_filters.py` (add function at end)
- Modify: `shopify_tool/packing_lists.py:113-138` (replace inline exclusion)
- Modify: `gui/actions_handler.py:729-798` (drop both string parsers and the `isin` copy)
- Test: `tests/test_report_filters_exclude.py` (create), `tests/audit/test_04_outputs.py`

**Interfaces:**
- Produces: `report_filters.exclude_skus(df: pd.DataFrame, skus) -> pd.DataFrame` where `skus` is `list | str | None`, and `report_filters.parse_sku_list(skus) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report_filters_exclude.py
import pandas as pd

from shopify_tool.report_filters import exclude_skus, parse_sku_list


def test_parse_sku_list_accepts_a_string_or_a_list():
    assert parse_sku_list("07, 8 ,") == ["07", "8"]
    assert parse_sku_list([" 07 ", "", None, 8]) == ["07", "8"]
    assert parse_sku_list(None) == []
    assert parse_sku_list(42) == []


def test_exclude_skus_matches_like_the_xlsx_always_did():
    df = pd.DataFrame({"SKU": ["7", "7.0", "B", None]})
    kept = exclude_skus(df, "07")
    assert kept["SKU"].tolist() == ["B", None]


def test_exclude_skus_with_nothing_to_exclude_returns_the_frame_unchanged():
    df = pd.DataFrame({"SKU": ["A"]})
    assert exclude_skus(df, []).equals(df)
```

- [ ] **Step 2: Run to confirm failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no tests/test_report_filters_exclude.py`
Expected: ImportError, `cannot import name 'exclude_skus'`.

- [ ] **Step 3: Implement in `report_filters.py`**

```python
def parse_sku_list(skus):
    """exclude_skus from a report config: a list, or comma-separated text
    typed into settings. Values are stripped; blanks dropped."""
    if isinstance(skus, str):
        skus = skus.split(",")
    elif not isinstance(skus, list):
        return []
    return [str(s).strip() for s in skus if s is not None and str(s).strip()]


def exclude_skus(df, skus):
    """Drops the rows whose SKU is excluded. The packing list XLSX and the
    JSON for Packing Tool both call this, so they can't disagree
    (AUDIT-04-4). SKUs compare through normalize_sku_for_matching, so "07"
    also excludes 7 and "7.0". A row with no SKU is never excluded."""
    wanted = parse_sku_list(skus)
    if not wanted or df is None or df.empty or "SKU" not in df.columns:
        return df
    from shopify_tool.csv_utils import normalize_sku_for_matching

    targets = {normalize_sku_for_matching(s) for s in wanted}
    has_sku = df["SKU"].notna()
    normalized = df["SKU"].where(has_sku, "").astype(str).map(normalize_sku_for_matching)
    return df[~(has_sku & normalized.isin(targets))]
```

Check `csv_utils.normalize_sku_for_matching("")` does not raise. If it does, map only `df.loc[has_sku, "SKU"]`.

- [ ] **Step 4: Use it in `create_packing_list`**

Replace the whole `if exclude_skus and not filtered_orders.empty:` block (lines ~113–138, all the `[EXCLUDE_SKUS]` logging included) with:

```python
        before = len(filtered_orders)
        filtered_orders = exclude_skus_from(filtered_orders, exclude_skus)
        if len(filtered_orders) != before:
            logger.info(f"exclude_skus removed {before - len(filtered_orders)} rows")
```

and change the import line to
`from shopify_tool.report_filters import apply_report_filters, exclude_skus as exclude_skus_from, fulfillable_only`
(the parameter is already called `exclude_skus`). Drop the now-unused `normalize_sku_for_matching` import if ruff flags it.

- [ ] **Step 5: Use it in `_generate_single_report`**

In the `packing_lists` branch, delete the `isinstance(exclude_skus, str)` parsing (lines ~735–748) and pass `exclude_skus=report_config.get("exclude_skus")` straight to `create_packing_list`. In the JSON block, replace the `exclude_skus_list` parsing and the `json_df = ...isin` block with:

```python
                    json_df = report_filters.exclude_skus(
                        filtered_df, report_config.get("exclude_skus")
                    )
```

Add `from shopify_tool import report_filters` to the handler's imports if it is not there (check the existing `from shopify_tool import ...` line).

- [ ] **Step 6: Remove the xfail on `test_packing_list_json_excludes_the_same_skus_as_the_xlsx`, then run**

Run: `... pytest ... tests/test_report_filters_exclude.py tests/audit/test_04_outputs.py tests/test_packing_lists*.py`
Expected: all pass (the other AUDIT-04 tests still xfail).

- [ ] **Step 7: Commit** as "AUDIT-04-4: one SKU exclusion for the packing list XLSX and JSON".

---

### Task 2: Label numbers follow the packing list (owner decision 1)

**Files:**
- Modify: `shopify_tool/packing_lists.py:161-168` (extract the sort)
- Modify: `gui/barcode_generator_widget.py:430-438` (use it)
- Test: `tests/test_packing_list_order.py` (create)

**Interfaces:**
- Produces: `packing_lists.sort_for_packing_list(df: pd.DataFrame) -> pd.DataFrame`. It sorts by courier priority (DHL 0, PostOne 1, DPD 2, else 3), then `order_number_sort_key`, then `SKU` when present. It returns a copy without helper columns and with the original index (the caller resets it).

- [ ] **Step 1: Failing test**

```python
# tests/test_packing_list_order.py
import pandas as pd

from shopify_tool.barcode_processor import generate_barcodes_batch
from shopify_tool.packing_lists import create_packing_list, sort_for_packing_list


def _frame():
    return pd.DataFrame({
        "Order_Number": ["#3", "#1", "#2", "#10"],
        "SKU": ["A", "A", "A", "A"],
        "Quantity": [1, 1, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable"] * 4,
        "Shipping_Provider": ["DPD", "PostOne", "DHL", "DHL"],
        "Destination_Country": ["BG"] * 4,
        "Warehouse_Name": ["W"] * 4,
        "Internal_Tags": ["[]"] * 4,
    })


def test_sort_is_courier_then_numeric_order_number():
    assert sort_for_packing_list(_frame())["Order_Number"].tolist() == ["#2", "#10", "#1", "#3"]


def test_label_numbers_follow_the_packing_list(tmp_path):
    df = _frame()
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    listed = pd.read_excel(tmp_path / "p.xlsx", dtype={"Order_Number": str})["Order_Number"].tolist()
    orders = sort_for_packing_list(df.assign(item_count=1)).reset_index(drop=True)
    labels = generate_barcodes_batch(orders)
    assert [r["order_number"] for r in sorted(labels, key=lambda r: r["sequential_num"])] == listed
```

- [ ] **Step 2: Run, expect ImportError** on `sort_for_packing_list`.

- [ ] **Step 3: Implement** in `packing_lists.py` (module level, above `create_packing_list`):

```python
_COURIER_PRIORITY = {"DHL": 0, "PostOne": 1, "DPD": 2}


def sort_for_packing_list(df):
    """The packing list's row order: courier (DHL, PostOne, DPD, then the
    rest), then numeric order number ("#9" before "#10"), then SKU. The
    barcode tab numbers its labels in this same order, so label #N is the
    N-th order on the list."""
    keyed = df.assign(
        _courier=df["Shipping_Provider"].map(_COURIER_PRIORITY).fillna(3),
        _order=df["Order_Number"].apply(order_number_sort_key),
    )
    by = ["_courier", "_order"] + (["SKU"] if "SKU" in df.columns else [])
    return keyed.sort_values(by=by, kind="stable").drop(columns=["_courier", "_order"])
```

In `create_packing_list`, replace the `provider_map` … `sorted_list = sorted_list.drop(columns=["_order_sort"])` lines with `sorted_list = sort_for_packing_list(filtered_orders)`. The old code left a `sort_priority` column behind. Grep `sort_priority` in the repo; nothing should read it.

- [ ] **Step 4: Use it in the barcode worker.** In `_generate_barcodes_worker`, replace the `_order_sort` block with:

```python
        from shopify_tool.packing_lists import sort_for_packing_list

        unique_orders = sort_for_packing_list(unique_orders).reset_index(drop=True)
```

Also drop the `order_number_sort_key` import there, and change the log line to `"Numbering labels in packing-list order"`.

- [ ] **Step 5: Run** `tests/test_packing_list_order.py tests/audit/test_04_outputs.py tests/test_barcode*.py`. Expected: pass. `test_packing_list_is_in_numeric_order_number_order` must still pass, since all its rows are DHL.

- [ ] **Step 6: Commit** as "Label numbers follow the packing list order (audit 04 owner decision)".

---

### Task 3: An empty list removes its old files; regenerating a list drops its label PDFs (AUDIT-04-3, AUDIT-04-12)

**Files:**
- Modify: `shopify_tool/packing_lists.py` (`create_packing_list` returns an order count)
- Modify: `shopify_tool/barcode_processor.py` (label PDF name helpers + `invalidate_label_pdfs`)
- Modify: `gui/barcode_generator_widget.py:359,479,491,520,524,564,584` (use the name helpers)
- Modify: `gui/actions_handler.py:_generate_single_report`
- Modify: `shopify_tool/core.py:1492-1504` (the core packing-list path)
- Test: `tests/test_label_pdf_invalidation.py` (create), `tests/audit/test_04_outputs.py`

**Interfaces:**
- Produces:
  - `create_packing_list(...) -> int`: the number of orders written, 0 when nothing matched. Nothing is written on 0.
  - `barcode_processor.barcode_pdf_path(barcodes_dir: Path, list_stem: str) -> Path` gives `barcodes_dir / f"{list_stem}_barcodes.pdf"`.
  - `barcode_processor.qr_pdf_path(barcodes_dir: Path, list_stem: str) -> Path` gives `barcodes_dir / f"{list_stem}_qr_labels.pdf"`.
  - `barcode_processor.invalidate_label_pdfs(session_path, list_stem: str) -> list[Path]` deletes both PDFs under `Path(session_path) / "barcodes" / list_stem` and returns the ones it deleted. OS errors propagate.

- [ ] **Step 1: Failing tests**

```python
# tests/test_label_pdf_invalidation.py
from unittest.mock import MagicMock

import pandas as pd
import pytest

from gui.actions_handler import ActionsHandler
from shopify_tool.barcode_processor import invalidate_label_pdfs


def _config():
    return {"name": "ALL", "output_filename": "ALL.xlsx", "filters": []}


def _df(status="Fulfillable"):
    return pd.DataFrame({
        "Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
        "Order_Fulfillment_Status": [status], "Shipping_Provider": ["DHL"],
        "Destination_Country": ["BG"], "Warehouse_Name": ["W"],
        "Product_Name": ["P"], "Internal_Tags": ["[]"],
    })


def _handler(df):
    mw = MagicMock()
    mw.analysis_results_df = df
    mw.session_path = None
    return ActionsHandler(mw)


def test_invalidate_deletes_both_label_pdfs_and_nothing_else(tmp_path):
    d = tmp_path / "barcodes" / "ALL"
    d.mkdir(parents=True)
    for name in ("ALL_barcodes.pdf", "ALL_qr_labels.pdf", "keep.txt"):
        (d / name).write_bytes(b"x")
    removed = invalidate_label_pdfs(tmp_path, "ALL")
    assert sorted(p.name for p in removed) == ["ALL_barcodes.pdf", "ALL_qr_labels.pdf"]
    assert [p.name for p in d.iterdir()] == ["keep.txt"]


def test_invalidate_without_a_barcodes_folder_is_a_no_op(tmp_path):
    assert invalidate_label_pdfs(tmp_path, "ALL") == []


def test_regenerating_a_list_drops_its_label_pdfs(tmp_path):
    d = tmp_path / "barcodes" / "ALL"
    d.mkdir(parents=True)
    (d / "ALL_barcodes.pdf").write_bytes(b"old")
    _handler(_df())._generate_single_report("packing_lists", _config(), tmp_path)
    assert not (d / "ALL_barcodes.pdf").exists()
    assert (tmp_path / "packing_lists" / "ALL.xlsx").exists()


def test_empty_list_says_so_instead_of_report_saved(tmp_path):
    h = _handler(_df())
    h._generate_single_report("packing_lists", _config(), tmp_path)
    h.mw.analysis_results_df = _df("Not Fulfillable")
    h._generate_single_report("packing_lists", _config(), tmp_path)
    msg = h.mw.statusBar.return_value.showMessage.call_args[0][0]
    assert msg == "No orders matched ALL; its old files were removed"


def test_empty_list_with_its_file_open_reports_the_lock(tmp_path, monkeypatch):
    # Review Focus 4: Excel holding ALL.xlsx open on Windows.
    import gui.actions_handler as ah
    from pathlib import Path

    h = _handler(_df())
    h._generate_single_report("packing_lists", _config(), tmp_path)
    h.mw.analysis_results_df = _df("Not Fulfillable")
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.suffix == ".xlsx":
            raise PermissionError(13, "in use", str(self))
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)
    shown = MagicMock()
    monkeypatch.setattr(ah, "show_error", shown)
    h._generate_single_report("packing_lists", _config(), tmp_path)
    assert "ALL.xlsx is open in another program" in shown.call_args[0][2]
```

- [ ] **Step 2: Run, expect ImportError** on `invalidate_label_pdfs`.

- [ ] **Step 3: `barcode_processor.py`.** Add these after the exception classes:

```python
def barcode_pdf_path(barcodes_dir: Path, list_stem: str) -> Path:
    return Path(barcodes_dir) / f"{list_stem}_barcodes.pdf"


def qr_pdf_path(barcodes_dir: Path, list_stem: str) -> Path:
    return Path(barcodes_dir) / f"{list_stem}_qr_labels.pdf"


def invalidate_label_pdfs(session_path, list_stem: str) -> list[Path]:
    """Deletes a packing list's barcode and QR label PDFs. Called whenever
    the list is regenerated: a PDF left from before could label orders the
    new list no longer holds (AUDIT-04-12)."""
    barcodes_dir = Path(session_path) / "barcodes" / list_stem
    removed = []
    for path in (barcode_pdf_path(barcodes_dir, list_stem), qr_pdf_path(barcodes_dir, list_stem)):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed
```

In `gui/barcode_generator_widget.py`, replace every `self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf"` with `barcode_pdf_path(self.barcodes_dir, self.current_packing_list)`, and every `..._qr_labels.pdf` with `qr_pdf_path(...)`. That's 7 sites; line 359 uses `output_path`, and `_generate_*_from_results` build `pdf_filename`. Import both from `shopify_tool.barcode_processor`.

- [ ] **Step 4: `create_packing_list` returns a count.** Change the empty branch to `return 0`. After the `with pd.ExcelWriter(...)` block, add `return int(sorted_list["Order_Number"].nunique())`. Update the docstring with a `Returns:` line: "int: orders written; 0 means nothing matched and no file was written".

- [ ] **Step 5: `_generate_single_report`.** In the `packing_lists` branch:

```python
                written = packing_lists.create_packing_list(...)  # same kwargs as Task 1
                barcode_processor.invalidate_label_pdfs(session_path, Path(base_filename).stem)
                json_path = output_dir / base_filename.replace(".xlsx", ".json")
                if not written:
                    Path(output_file).unlink(missing_ok=True)
                    json_path.unlink(missing_ok=True)
                    removed_empty = True
```

Wrap the existing JSON block in `if written:` (drop its inner `if not json_df.empty` / "Skipping JSON" else branch; `written > 0` already guarantees rows). Initialise `removed_empty = False` next to `packaging_file = None`. At the status message:

```python
            if removed_empty:
                self.mw.statusBar().showMessage(
                    f"No orders matched {report_name}; its old files were removed", 5000
                )
            else:
                ...existing "Report saved" lines...
```

Add a `PermissionError` handler **before** the generic `except Exception:` at the end of the method. Task 6 reuses it:

```python
        except PermissionError as e:
            self.log.exception(f"Failed to generate report '{report_name}'")
            locked = Path(e.filename).name if e.filename else "The file"
            show_error(
                self.mw,
                f"{report_name!r} wasn't generated",
                f"{locked} is open in another program. Close it, then generate again.",
            )
```

`Path` is imported inside the method (`from pathlib import Path`); move that import to module level if it isn't used before the `except`. Import `barcode_processor` from `shopify_tool`.

- [ ] **Step 6: `core.py` packing-list path.** Capture `written = packing_lists.create_packing_list(...)`. Before the `os.path.exists` check:

```python
        if not written:
            Path(output_file).unlink(missing_ok=True)
            return False, f"No orders matched '{report_name}'; no packing list was written."
```

- [ ] **Step 7: Remove the xfail on `test_regenerating_an_empty_packing_list_replaces_the_old_files`, then run**
`tests/test_label_pdf_invalidation.py tests/audit/test_04_outputs.py tests/test_core.py tests/test_barcode*.py`. Expected: pass.

- [ ] **Step 8: Commit** as "AUDIT-04-3, -12: an empty list removes its old files; regenerating a list drops its label PDFs".

---

### Task 4: Every label gets a page (AUDIT-04-1)

**Files:**
- Modify: `requirements.txt:52` area
- Modify: `shopify_tool/barcode_processor.py` (`generate_barcodes_batch` tag line; both `generate_*_labels_pdf`)
- Test: `tests/audit/test_04_outputs.py`

- [ ] **Step 1: Remove the xfail markers** on `test_orders_without_internal_tags_are_labelled_na`, `test_label_pdf_with_missing_pages_is_an_error`, `test_requirements_pin_a_weasyprint_that_keeps_every_label`, and the conditional ones on `test_barcode_pdf_has_a_page_for_every_label` and `test_qr_pdf_has_a_page_for_every_label`. Delete the `WEASYPRINT_DROPS_PAGES` constant and its comment block, and the now-unused `import weasyprint` if ruff flags it. Run the file and expect the three unconditional ones to FAIL.

- [ ] **Step 2: requirements.txt.** Under the blabel line, add:
`weasyprint>=70           # 69.x drops every label after one with an empty field (AUDIT-04-1)`

- [ ] **Step 3: Tag.** In `generate_barcodes_batch`, change `"tag": format_tags_for_barcode(tag) if tag else "N/A",` to `"tag": format_tags_for_barcode(tag) or "N/A",`.

- [ ] **Step 4: Page check.** Add this module-level helper:

```python
def _check_page_count(pdf_bytes: bytes, expected: int) -> None:
    """Raises unless the rendered PDF has one page per label. A renderer
    that drops pages (WeasyPrint 69) must fail loudly, not print short."""
    from io import BytesIO

    import pypdf

    pages = len(pypdf.PdfReader(BytesIO(pdf_bytes)).pages)
    if pages != expected:
        raise BarcodeGenerationError(f"Label PDF has {pages} pages for {expected} labels")
```

In both renderers, call `_check_page_count(pdf_bytes, len(records))` right after `pdf_bytes = writer.write_labels(...)` and before `output_pdf.write_bytes`. It sits inside the `try`, so the existing `except Exception as e: raise BarcodeGenerationError(...) from e` re-wraps it; that is acceptable, since the test expects `BarcodeGenerationError`.

- [ ] **Step 5: Run** `tests/audit/test_04_outputs.py tests/test_barcode_processor.py`. Expected: pass. The venv should already have WeasyPrint ≥70; check with `.venv/bin/python -c "import weasyprint; print(weasyprint.__version__)"`. If it shows 69.x, run `.venv/bin/pip install "weasyprint>=70"` and note it in state.md, because the venv is shared with the main checkout.

- [ ] **Step 6: Commit** as "AUDIT-04-1: untagged orders are labelled N/A, a short label PDF is an error, pin WeasyPrint >=70".

---

### Task 5: Refuse order numbers that can't have a distinct barcode (AUDIT-04-5, D2)

**Files:**
- Modify: `shopify_tool/barcode_processor.py:66` (`sanitize_order_number`), and the end of `generate_barcodes_batch`
- Test: `tests/test_barcode_processor.py` (append), `tests/audit/test_04_outputs.py`

- [ ] **Step 1: Failing tests** (append to `tests/test_barcode_processor.py`):

```python
def test_non_ascii_order_number_is_refused():
    import pytest
    from shopify_tool.barcode_processor import InvalidOrderNumberError, sanitize_order_number

    with pytest.raises(InvalidOrderNumberError):
        sanitize_order_number("#Поръчка1")


def test_colliding_orders_all_fail_and_name_each_other():
    import pandas as pd
    from shopify_tool.barcode_processor import generate_barcodes_batch

    orders = pd.DataFrame({
        "Order_Number": ["#1001/2", "#10012", "#7"], "Shipping_Provider": "DHL",
        "Destination_Country": "BG", "Internal_Tags": "[]", "item_count": 1,
    })
    by_order = {r["order_number"]: r for r in generate_barcodes_batch(orders)}
    assert by_order["#7"]["success"]
    assert not by_order["#1001/2"]["success"] and not by_order["#10012"]["success"]
    assert "#10012" in by_order["#1001/2"]["error"]
    assert by_order["#1001/2"]["safe_order_number"] is None
```

Also remove the xfail on `test_distinct_orders_never_share_a_barcode_value`. Run and expect the new tests to FAIL.

- [ ] **Step 2: `sanitize_order_number`.** Before the `clean = ...` line, insert:

```python
    if not order_number.isascii():
        raise InvalidOrderNumberError(
            f"Order number '{order_number}' has characters a Code-128 barcode can't carry"
        )
```

Leave the existing `clean = ...` filter as is. Once non-ASCII is refused, `isalnum()` only admits ASCII.

- [ ] **Step 3: Collisions.** Before the final `logger.info("Batch preparation complete ...")` in `generate_barcodes_batch`:

```python
    # Distinct order numbers that encode to one value would scan as each
    # other, here and in Packing Tool, which normalises harder still.
    # Refuse all of them rather than let a scan pick one (AUDIT-04-5).
    by_value: dict[str, list[dict]] = {}
    for r in results:
        if r["success"]:
            by_value.setdefault(r["safe_order_number"], []).append(r)
    for value, group in by_value.items():
        if len(group) < 2:
            continue
        for r in group:
            others = ", ".join(o["order_number"] for o in group if o is not r)
            r.update(success=False, safe_order_number=None,
                     error=f"Barcode value {value} would also scan as {others}")
            logger.error(f"Order {r['order_number']}: {r['error']}")
```

- [ ] **Step 4: Run** `tests/test_barcode_processor.py tests/audit/test_04_outputs.py`. Expected: pass, including `test_barcode_value_is_the_order_number_unchanged`. If an existing sanitize test in `tests/test_barcode_processor.py` asserted that a non-ASCII input is cleaned rather than refused, update it to expect `InvalidOrderNumberError` and say so in the commit message.

- [ ] **Step 5: Commit** as "AUDIT-04-5: refuse order numbers that would share a barcode value".

---

### Task 6: A failed stock export is an error, and never a half file (AUDIT-04-2)

**Files:**
- Modify: `shopify_tool/stock_export.py:147-162` (`_write_xls`), and `:334` (the final `except`)
- Test: `tests/test_stock_export.py` (append), `tests/audit/test_04_outputs.py`

**Interfaces:**
- Produces: `create_stock_export` raises on any failure (return values unchanged otherwise). `_write_xls` is atomic.

- [ ] **Step 1: Failing tests** (append to `tests/test_stock_export.py`):

```python
def test_failed_xls_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    import os
    import pandas as pd
    from shopify_tool import stock_export

    target = tmp_path / "e.xls"
    target.write_bytes(b"previous")

    def boom(src, dst):
        raise OSError("network dropped")

    monkeypatch.setattr(os, "replace", boom)
    df = pd.DataFrame({"Артикул": ["A"], stock_export.QTY_COL: [1]})
    import pytest
    with pytest.raises(OSError):
        stock_export._write_xls(df, str(target))
    assert target.read_bytes() == b"previous"
    assert [p.name for p in tmp_path.iterdir()] == ["e.xls"]  # temp file cleaned up
```

Remove the xfail on `test_stock_export_write_failure_is_not_silent`. Run and expect both to FAIL.

- [ ] **Step 2: Atomic `_write_xls`.** Replace the final `workbook.save(output_file)` with:

```python
    import io
    import os
    import tempfile

    buf = io.BytesIO()
    workbook.save(buf)
    # Temp file + replace: a write that fails part-way (the share drops, the
    # ERP holds the file) never leaves a half-written export to import.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(output_file)), suffix=".xls.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(buf.getvalue())
        os.replace(tmp, output_file)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

Here `os.replace` is looked up on the `os` module at call time, so the monkeypatch hits it. Don't `from os import replace`.

- [ ] **Step 3: Re-raise.** Change the last `except Exception:` block of `create_stock_export` to:

```python
    except Exception:
        logger.exception(f"Error while creating stock export '{report_name}'")
        raise
```

Update the docstring's Returns/Raises. `core.create_stock_export_report` already maps exceptions to `(False, msg)`, and `_generate_single_report` gets the `PermissionError` handler from Task 3.

- [ ] **Step 4: Run** `tests/test_stock_export.py tests/audit/test_04_outputs.py tests/test_core.py`. Expected: pass. If an existing test asserted `create_stock_export(...) is None` on a failure, change it to `pytest.raises` and say so in the commit message.

- [ ] **Step 5: Commit** as "AUDIT-04-2: a failed stock export raises and never leaves a half file".

---

### Task 7: Timestamped stock-export filenames, earlier versions to old/ (D4, D5)

**Files:**
- Modify: `shopify_tool/stock_export.py` (new `prepare_export_path`)
- Modify: `gui/actions_handler.py:698-717` (default name, call site)
- Modify: `shopify_tool/core.py:1591-1628` (call site, session list entry)
- Test: `tests/test_stock_export_names.py` (create)

**Interfaces:**
- Consumes: `_packaging_path` (existing).
- Produces: `stock_export.prepare_export_path(base_path: str, now: datetime | None = None) -> str`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_stock_export_names.py
import os
from datetime import datetime
from pathlib import Path

import pytest

from shopify_tool.stock_export import prepare_export_path

NOW = datetime(2026, 9, 25, 14, 5)


def touch(d, *names):
    for n in names:
        (d / n).write_bytes(b"x")


def test_name_is_stem_date_and_minute(tmp_path):
    out = prepare_export_path(str(tmp_path / "ALL_ORDERS_ALMADERM.xls"), NOW)
    assert Path(out).name == "ALL_ORDERS_ALMADERM_2026-09-25_1405.xls"


def test_a_legacy_datestamp_in_the_stem_is_replaced(tmp_path):
    out = prepare_export_path(str(tmp_path / "ALL_2026-09-24.xls"), NOW)
    assert Path(out).name == "ALL_2026-09-25_1405.xls"


def test_every_earlier_version_moves_to_old(tmp_path):
    touch(tmp_path, "ALL.xls", "ALL_2026-09-24.xls", "ALL_2026-09-24_0900.xls",
          "ALL_2026-09-24_0900_packaging.xls", "ALL_DHL.xls", "notes.txt")
    prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
    assert sorted(p.name for p in (tmp_path / "old").iterdir()) == [
        "ALL.xls", "ALL_2026-09-24.xls", "ALL_2026-09-24_0900.xls",
        "ALL_2026-09-24_0900_packaging.xls"]
    # Review Focus 1: another report sharing the prefix stays.
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["ALL_DHL.xls", "notes.txt"]


def test_regex_characters_in_the_name_are_literal(tmp_path):
    touch(tmp_path, "ALL (DHL)+.xls", "ALL (DHL)+_2026-09-24_0900.xls", "ALL DHL.xls")
    out = prepare_export_path(str(tmp_path / "ALL (DHL)+.xls"), NOW)
    assert Path(out).name == "ALL (DHL)+_2026-09-25_1405.xls"
    assert sorted(p.name for p in (tmp_path / "old").iterdir()) == [
        "ALL (DHL)+.xls", "ALL (DHL)+_2026-09-24_0900.xls"]


def test_same_minute_re_export_archives_the_first(tmp_path):
    # Review Focus 2.
    touch(tmp_path, "ALL_2026-09-25_1405.xls")
    (tmp_path / "old").mkdir()
    touch(tmp_path / "old", "ALL_2026-09-25_1405.xls")
    out = prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
    assert not Path(out).exists()
    assert (tmp_path / "old" / "ALL_2026-09-25_1405.xls").exists()


def test_a_locked_earlier_version_raises(tmp_path, monkeypatch):
    touch(tmp_path, "ALL.xls")

    def locked(src, dst):
        raise PermissionError(13, "in use", src)

    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(PermissionError):
        prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
```

Run and expect ImportError.

- [ ] **Step 2: Implement** in `stock_export.py`:

```python
_DATESTAMP_SUFFIX = re.compile(r"_\d{4}-\d{2}-\d{2}$")


def prepare_export_path(base_path, now=None):
    """The file a new export of this report goes to: <stem>_YYYY-MM-DD_HHMM.xls
    beside the configured name. Every earlier version of the same report,
    and its packaging file, is moved to old/ first, so the folder only ever
    holds one current export and importing it can't write stock off twice.
    A move that fails (the ERP holds the file) raises, and nothing new is
    written."""
    base = Path(base_path)
    stem = _DATESTAMP_SUFFIX.sub("", base.stem)
    stamp = (now or datetime.now().astimezone()).strftime("%Y-%m-%d_%H%M")
    earlier = re.compile(
        rf"^{re.escape(stem)}(_\d{{4}}-\d{{2}}-\d{{2}}(_\d{{4}})?)?(_packaging)?\.xls$",
        re.IGNORECASE,
    )
    if base.parent.is_dir():
        versions = [p for p in base.parent.iterdir() if p.is_file() and earlier.match(p.name)]
        if versions:
            old = base.parent / "old"
            old.mkdir(exist_ok=True)
            for p in versions:
                os.replace(p, old / p.name)
                logger.info(f"Moved earlier export {p.name} to old/")
    return str(base.with_name(f"{stem}_{stamp}.xls"))
```

Add the imports the module lacks (`os`, `re`, `from datetime import datetime`, `Path`); check the top of the file first. `os.replace` must be called as `os.replace` so the test's monkeypatch hits it.

- [ ] **Step 3: Call sites.**
  - `_generate_single_report`: the default stock-export name becomes `f"{report_name}.xls"` (drop `datestamp`). After `output_file = str(output_dir / base_filename)`, add:
    ```python
            if report_type == "stock_exports":
                output_file = stock_export.prepare_export_path(output_file)
    ```
    The status bar already uses `os.path.basename(output_file)`.
  - `core.create_stock_export_report`: after `output_filename` is decided (both branches), set `output_filename = stock_export.prepare_export_path(output_filename)`. In the session-list append, use `os.path.basename(output_filename)` instead of `original_filename`.

- [ ] **Step 4: Run** `tests/test_stock_export_names.py tests/test_stock_export.py tests/test_core.py tests/audit/test_04_outputs.py tests/test_generate_reports_dialog.py`. Expected: pass. Any existing test that asserted the exact `<name>_YYYY-MM-DD.xls` or `<configured>.xls` path in `stock_exports/` must now glob `"<stem>_*.xls"`. Update it and name it in the commit message.

- [ ] **Step 5: Commit** as "Stock exports carry a timestamp in their name; earlier versions move to old/".

---

### Task 8: Configured columns apply with lot tracking (AUDIT-04-10)

**Files:**
- Modify: `shopify_tool/packing_lists.py` (the `if has_lot_details:` / `else:` column selection)
- Test: `tests/audit/test_04_outputs.py`, `tests/test_packing_list_order.py` (append)

- [ ] **Step 1: Failing test** (append to `tests/test_packing_list_order.py`), and remove the xfail on `test_configured_columns_apply_with_lot_tracking`:

```python
def test_lot_columns_follow_quantity_in_a_configured_layout(tmp_path):
    df = _frame().head(1)
    df["Lot_Details"] = [[{"qty_allocated": 1, "expiry": "2027-01", "batch": "L1"}]]
    create_packing_list(df, str(tmp_path / "p.xlsx"), columns=["Order_Number", "Quantity", "SKU"])
    assert pd.read_excel(tmp_path / "p.xlsx").columns.tolist() == [
        "Order_Number", "Quantity", "Lot_Expiry", "Lot_Batch", "SKU"]
```

- [ ] **Step 2: Implement.** Restructure the column choice so the configured-columns logic is shared. Compute `default_columns` for the no-lot case as today, and the lot default as today's `columns_for_print` list. Then:

```python
        lot_default = [...today's lot list...]
        plain_default = [...today's default_columns...]
        default_columns = lot_default if has_lot_details else plain_default
        if columns:
            wanted = list(columns)
            if has_lot_details:
                missing_lot = [c for c in ("Lot_Expiry", "Lot_Batch") if c not in wanted]
                at = wanted.index("Quantity") + 1 if "Quantity" in wanted else len(wanted)
                wanted[at:at] = missing_lot
            available = {*sorted_list.columns, "Repeat"}
            columns_for_print = [c for c in wanted if c in available]
            ...existing missing-column warning and empty fallback to default_columns...
        else:
            columns_for_print = default_columns
```

The lot expansion and the Destination_Country dedup still happen in the `has_lot_details` branch before this. Only the column choice moves below it.

- [ ] **Step 3: Run** `tests/test_packing_list_order.py tests/audit/test_04_outputs.py tests/test_packing_lists*.py`. Expected: pass.

- [ ] **Step 4: Commit** as "AUDIT-04-10: configured packing-list columns apply with lot tracking".

---

### Task 9: Order_Min_Box docs tell the truth (owner decision 2)

**Files:**
- Modify: `shopify_tool/weight_calculator.py:1-13` (module docstring), `:24` (`UNKNOWN_DIMS` comment), `:171-180` (`find_min_box_for_order`), `:257-266` (`enrich_dataframe_with_weights`)
- Test: `tests/test_weight_calculator.py` (append)

- [ ] **Step 1: Pin test.** Build the `weight_config` the way the existing tests in `tests/test_weight_calculator.py` do (read one first; copy its products/boxes shape exactly). Use one SKU with dimensions that fits box `S`, and one SKU with none. Assert `find_min_box_for_order(order_df, cfg) == "S"`. Add a second assertion: an order of only the unsized SKU returns `UNKNOWN_DIMS`. This should pass immediately, since it pins current behaviour.

- [ ] **Step 2: Docs.**
  - `UNKNOWN_DIMS` comment: `# no item in the order has dimensions configured (or there are no products)`.
  - `find_min_box_for_order` Returns: replace the UNKNOWN_DIMS line with: `- UNKNOWN_DIMS if no item has dimensions configured. Items without dimensions are otherwise ignored, and the box is chosen from the items that have them (owner decision, audit 04 §5).`
  - `enrich_dataframe_with_weights` Order_Min_Box line: append `; items without dimensions are ignored`.
  - Module docstring: add a line, `Items with no configured dimensions are ignored for box selection; UNKNOWN_DIMS only when none have dimensions.`

- [ ] **Step 3: Run** `tests/test_weight_calculator.py`, then **commit** as "Order_Min_Box: docs match the behaviour the owner kept; pin it".

---

### Task 10: The name fallback matches one customer or none (AUDIT-04-7)

**Files:**
- Modify: `shopify_tool/pdf_processor.py:290-370` (`load_csv_mapping`), `:443-460` (step 3 of `match_reference`)
- Test: `tests/test_reference_matching.py` (create), `tests/audit/test_04_outputs.py`

**Interfaces:**
- Produces: `mapping["by_name"]: dict[str, list[dict]]`, a normalized name → the distinct `{ref, name}` packs; `mapping["refs"]: set[str]`, every non-empty REF in the CSV (used by Task 11). Name matches return `verified: False, method: "name"`.

- [ ] **Step 1: Failing tests.** Remove the xfails on `test_name_fallback_picks_the_exact_customer` and `test_name_fallback_refuses_an_ambiguous_name`, then:

```python
# tests/test_reference_matching.py
import csv

from shopify_tool.pdf_processor import load_csv_mapping, match_reference


def mapping_for(tmp_path, rows):
    p = tmp_path / "m.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["postone", "tracking", "ref", "c3", "c4", "c5", "name"])
        for ref, name in rows:
            w.writerow(["", "", ref, "", "", "", name])
    return load_csv_mapping(p)


def test_cyrillic_name_does_not_match_a_longer_name(tmp_path):
    # Review Focus 3.
    m = mapping_for(tmp_path, [("100", "Иван Петров"), ("200", "Иван Петрова")])
    assert match_reference("Получател:\nИван Петрова\nСофия", m)["ref"] == "200"


def test_longest_nested_name_wins(tmp_path):
    m = mapping_for(tmp_path, [("100", "Ann Leeson"), ("200", "Ann Leeson Smith")])
    assert match_reference("To: Ann Leeson Smith", m)["ref"] == "200"


def test_two_unrelated_names_on_one_page_match_neither(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("200", "Petar Georgiev")])
    assert match_reference("From Maria Ivanova to Petar Georgiev", m) is None


def test_a_repeated_row_is_not_ambiguous(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("100", "Maria Ivanova")])
    assert match_reference("Maria Ivanova", m)["ref"] == "100"


def test_name_match_is_unverified(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova")])
    assert match_reference("Maria Ivanova", m)["verified"] is False


def test_mapping_lists_every_reference(tmp_path):
    m = mapping_for(tmp_path, [("100", "Maria Ivanova"), ("", "No Ref"), ("200", "B B")])
    assert m["refs"] == {"100", "200"}
```

Run and expect failures.

- [ ] **Step 2: `load_csv_mapping`.** Add `'refs': set()` to `mappings`. In the row loop:

```python
                if ref_num:
                    mappings['refs'].add(ref_num)
                if client_name:
                    packs = mappings['by_name'].setdefault(normalize_text(client_name), [])
                    if all(p['ref'] != ref_num for p in packs):
                        packs.append(data_pack)
```

`mappings` is created once, outside the encoding loop, and a failed encoding attempt can leave partial rows behind. Move the `mappings = {...}` initialisation **inside** the `for encoding in encodings:` loop so every attempt starts clean. Update the docstring's `by_name` line and add `refs`.

- [ ] **Step 3: `match_reference` step 3.** Replace the name loop with:

```python
    # Step 3: Name fallback. Only whole-word matches count, a name inside a
    # longer matching name gives way to it, and the page matches only if one
    # name is left and it carries one REF. Anything else would guess
    # between customers (AUDIT-04-7).
    page_text_norm = normalize_text(page_text)
    found = [
        name for name in mapping['by_name']
        if len(name) > 5 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", page_text_norm)
    ]
    found = [n for n in found if not any(n != o and n in o for o in found)]
    if len(found) == 1 and len(mapping['by_name'][found[0]]) == 1:
        data = mapping['by_name'][found[0]][0]
        logger.debug(f"Matched by Name: {found[0]} → {data['ref']} (unverified)")
        return {'ref': data['ref'], 'verified': False, 'method': 'name'}
    if found:
        logger.info(f"Name fallback refused, ambiguous: {found}")
    return None
```

- [ ] **Step 4: Run** `tests/test_reference_matching.py tests/audit/test_04_outputs.py tests/test_pdf_processor*.py`. Expected: pass. Grep the tests for `by_name` and update any that read it as a dict of packs.

- [ ] **Step 5: Commit** as "AUDIT-04-7: the name fallback matches exactly one customer or none".

---

### Task 11: The reference run reports what it couldn't place (AUDIT-04-8, -9, -11)

**Files:**
- Modify: `shopify_tool/pdf_processor.py`: `process_reference_labels` (matching loop, stamping loop, return dict), `sort_pages_by_reference`, new `reference_sort_key` and `reference_run_warning`
- Modify: `gui/reference_labels_widget.py:424-458` (`_on_processing_complete`)
- Test: `tests/test_reference_matching.py` (append), `tests/audit/test_04_outputs.py`

**Interfaces:**
- Consumes: `mapping["refs"]` (Task 10).
- Produces:
  - `pdf_processor.reference_sort_key(ref: str) -> tuple`: numeric-shaped (`^#?\d+$`) gives `(0, int, ref)`; anything else gives `(1, 0, ref)`.
  - Result dict gains `duplicate_refs: list[str]`, `missing_refs: list[str]` (both sorted by `reference_sort_key`), and `name_matched: int`. `matched` means pages actually stamped.
  - `pdf_processor.reference_run_warning(result: dict) -> str | None`.

- [ ] **Step 1: Failing tests.** Remove the xfails on `test_reference_run_reports_a_reference_on_two_pages`, `test_reference_run_reports_a_reference_without_a_page`, `test_unstamped_page_is_not_counted_as_matched` and `test_tracking_shaped_reference_sorts_after_numeric_references`. Append:

```python
from shopify_tool.pdf_processor import reference_run_warning, reference_sort_key


def test_numeric_refs_sort_by_value_and_others_after():
    refs = ["HW1ABC", "#10", "9", "#100", "ABC"]
    assert sorted(refs, key=reference_sort_key) == ["9", "#10", "#100", "ABC", "HW1ABC"]


def test_warning_names_duplicates_and_missing():
    result = {"duplicate_refs": ["100"], "missing_refs": ["200", "300"]}
    assert reference_run_warning(result) == (
        "Check before printing: REF 100 is on more than one page; no page for REF 200, 300.")


def test_warning_caps_long_lists():
    result = {"duplicate_refs": [], "missing_refs": [str(i) for i in range(1, 9)]}
    assert reference_run_warning(result) == (
        "Check before printing: no page for REF 1, 2, 3, 4, 5 (+3 more).")


def test_no_warning_for_a_clean_run():
    assert reference_run_warning({"duplicate_refs": [], "missing_refs": []}) is None
```

- [ ] **Step 2: Sort key + sort.**

```python
def reference_sort_key(ref) -> tuple:
    """Numeric-shaped REFs ("#107", "42") by value, then every other REF
    alphabetically. A tracking-shaped REF has digits inside it, but they
    are not its number (AUDIT-04-11)."""
    ref = str(ref)
    m = re.fullmatch(r"#?(\d+)", ref)
    return (0, int(m.group(1)), ref) if m else (1, 0, ref)
```

In `sort_pages_by_reference`, replace `get_sort_key` with `matched_pages.sort(key=lambda p: (*reference_sort_key(p['ref']), p['original_order']))`.

- [ ] **Step 3: Count what was stamped.** In `process_reference_labels`, drop the `matched += 1` / `unmatched += 1` counting from the matching loop (keep the debug logs), and store `'method': ref_data['method'] if ref_data else None` in each page dict. Rewrite the stamping loop:

```python
        stamped_refs = []
        name_matched = 0
        for page_data in sorted_pages:
            page, ref = page_data['page'], page_data['ref']
            if ref:
                try:
                    _stamp_reference(out, page, ref)
                    stamped_refs.append(ref)
                    name_matched += page_data['method'] == 'name'
                    continue
                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}; page kept unstamped")
            out.pages.append(page)
        matched = len(stamped_refs)
        unmatched = total_pages - matched
        counts = Counter(stamped_refs)
        duplicate_refs = sorted((r for r, n in counts.items() if n > 1), key=reference_sort_key)
        missing_refs = sorted(mapping['refs'] - set(counts), key=reference_sort_key)
```

Move the `logger.info(f"Matching complete: ...")` line below this. Add `from collections import Counter`. Add `'duplicate_refs'`, `'missing_refs'` and `'name_matched'` to the returned dict.

- [ ] **Step 4: Warning text.**

```python
def _ref_list(refs, cap=5):
    shown = ", ".join(refs[:cap])
    return shown + (f" (+{len(refs) - cap} more)" if len(refs) > cap else "")


def reference_run_warning(result) -> str | None:
    """The inline warning for a run that needs checking before printing,
    or None. Duplicate and missing REFs both mean a parcel may get the
    wrong label or none (AUDIT-04-8)."""
    parts = []
    if result.get("duplicate_refs"):
        parts.append(f"REF {_ref_list(result['duplicate_refs'])} is on more than one page")
    if result.get("missing_refs"):
        parts.append(f"no page for REF {_ref_list(result['missing_refs'])}")
    return f"Check before printing: {'; '.join(parts)}." if parts else None
```



- [ ] **Step 5: Widget.** In `_on_processing_complete`, after `self.print_btn.setEnabled(True)`:

```python
        warning = reference_run_warning(result)
        theme = get_theme_manager().get_current_theme()
        if warning:
            self.status_label.setText(warning)
            self.status_label.setStyleSheet(f"color: {theme.status_warning}; font-weight: bold;")
        else:
            self.status_label.setText("Processing complete!")
            self.status_label.setStyleSheet(f"color: {theme.status_success}; font-weight: bold;")
            by_name = result.get("name_matched", 0)
            toast(
                self,
                f"Processed {Path(result['output_file']).name} "
                f"({result['matched']} matched, {result['unmatched']} unmatched"
                + (f", {by_name} matched by name only" if by_name else "")
                + ").",
            )
```

This replaces the old unconditional status/toast lines. Keep the log line, auto-open and the signal. Import `reference_run_warning` from `shopify_tool.pdf_processor`. Check that the label wraps (`setWordWrap(True)`) where it is created; add it if not.

- [ ] **Step 6: Run** `tests/test_reference_matching.py tests/audit/test_04_outputs.py tests/test_pdf_processor*.py tests/test_reference_labels*.py`. Expected: pass, including `test_reference_run_sorts_pages_by_reference_and_keeps_every_page`.

- [ ] **Step 7: Commit** as "AUDIT-04-8, -9, -11: the reference run reports duplicate and missing REFs, counts only stamped pages, sorts REFs by shape".

---

### Task 12: Gate

- [ ] `grep -n "xfail" tests/audit/test_04_outputs.py`: expect **no** output.
- [ ] Full suite in the background: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q --color=no`. Expected: all pass. The xfailed count drops by 14 (the unconditional AUDIT-04 markers), from 33 to 19.
- [ ] `.venv/bin/ruff check .`: clean.
- [ ] `graphify update .`
- [ ] Update `state.md` for Stage C (`next_stage: C`), with the pass/xfail counts.
- [ ] Push the branch: `/usr/bin/git push -u origin phase14-bundle4-outputs-labels`.
