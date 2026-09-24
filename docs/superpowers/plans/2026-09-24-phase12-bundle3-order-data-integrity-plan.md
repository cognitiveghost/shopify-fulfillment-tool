# Phase 12 Bundle 3 — Order data integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline, in this session — the runner forbids subagent fan-out). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Shopify tool from dropping, doubling, or cross-contaminating order lines between the CSV export and the packing list, and make the CSV delimiter detect itself per file.

**Architecture:** Two rules move into `shopify_tool/csv_utils.py` as deep functions: `resolve_delimiter` (Auto or override, per file) and the owning-file rule inside `merge_csv_files`. Every CSV read of a user file goes through the first; the folder merge is the second's only caller. Two cleaning fixes land in `analysis._clean_and_prepare_data`. The settings page gets a combo, and a one-shot profile migration moves every client to Auto.

**Tech Stack:** Python 3, pandas, PySide6, pytest (offscreen).

**Spec:** `docs/superpowers/specs/2026-09-24-phase12-bundle3-order-data-integrity-design.md` — read §1 (findings F1–F7), §3–§6 before starting. ADR `docs/adr/0009-delimiters-are-detected-per-file.md`. Vocabulary: `CONTEXT.md` › Session setup (**order line, folder merge, owning file, overlapping order/SKU, delimiter setting, Auto, override**). Use those words in names, comments and copy.

## Global Constraints

- Worktree: `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase12-bundle3`, branch `worktree-phase12-bundle3`. Run everything from there.
- Test command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q <path>` (`python` is not on PATH).
- Lint: `.venv/bin/ruff check . --exclude shared` must be clean.
- **Never edit `shared/`.** Never hardcode colours. No new dependencies. No `pyproject.toml`.
- **Tooling gotcha:** a `ruff-on-edit.sh` hook reformats a whole `.py` file when Edit/Write touches it. If a file you edit is not already ruff-formatted, the diff balloons. Check with `.venv/bin/ruff format --check <file>` first; if it would reformat, make the edit with a small Python script (`str.replace` + `assert`) instead of Edit.
- Git on this VM: one plain git command per Bash call; commit with `git commit -F <msgfile>` (message file in `$CLAUDE_JOB_DIR/tmp`). Commit messages end with the `Co-Authored-By` line the session reminder gives.
- The auto setting value is the string `"auto"`; fallbacks are `","` (orders) and `";"` (stock). Migration marker key: `settings["delimiter_auto_migrated"]`.
- Copy strings are fixed by spec §5; use them verbatim.

## Review Focus

1. **A folder where one file is `;` and another `,`.** Both must merge. Covered: Task 2 `test_mixed_delimiters_merge`.
2. **An orders file with no `Tags` column at all, or a profile with no `Order_Number` mapping.** The grouped fill must skip missing columns; the merge must fall back to a plain concat with a Logs warning, not crash. Covered: Task 2 `test_no_owner_key_is_a_plain_concat`, Task 5 `test_missing_optional_columns_still_clean`.
3. **A stock file with blank SKU cells.** They must still be dropped, not turned into an `""` SKU that matches nothing and pollutes stock. Covered: Task 5 `test_blank_stock_skus_are_still_dropped`.
4. **A profile hand-edited to a delimiter outside the combo list (e.g. `"::"`).** Opening and saving Settings must not change it. Covered: Task 6 `test_unknown_delimiter_survives_a_round_trip`.
5. **An override set after migration.** Reloading the profile must not reset it to Auto. Covered: Task 6 `test_marker_protects_a_later_override`.

---

### Task 1: `resolve_delimiter`

**Files:**
- Modify: `shopify_tool/csv_utils.py` (add after `detect_csv_delimiter`, ~line 120)
- Test: `tests/test_csv_utils.py` (new class `TestResolveDelimiter`)

**Interfaces:**
- Produces: `AUTO_DELIMITER: str = "auto"`, `FALLBACK_DELIMITERS: dict[str, str] = {"orders": ",", "stock": ";"}`, `resolve_delimiter(path: str, setting: str | None, kind: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
from shopify_tool.csv_utils import AUTO_DELIMITER, resolve_delimiter


class TestResolveDelimiter:
    def test_an_override_is_returned_untouched(self, tmp_path):
        f = tmp_path / "x.csv"
        f.write_text("a,b\n1,2\n", encoding="utf-8")
        assert resolve_delimiter(str(f), ";", "orders") == ";"

    @pytest.mark.parametrize("setting", [AUTO_DELIMITER, "", None])
    def test_auto_reads_the_file(self, tmp_path, setting):
        f = tmp_path / "x.csv"
        f.write_text("a;b;c\n1;2;3\n4;5;6\n", encoding="utf-8")
        assert resolve_delimiter(str(f), setting, "orders") == ";"

    def test_undetectable_falls_back_per_kind(self, tmp_path):
        f = tmp_path / "x.csv"
        f.write_text("onlyonecolumn\nvalue\n", encoding="utf-8")
        assert resolve_delimiter(str(f), AUTO_DELIMITER, "stock") == ";"
        assert resolve_delimiter(str(f), AUTO_DELIMITER, "orders") == ","
```

- [ ] **Step 2: Run, expect ImportError** — `... pytest -p no:randomly -q tests/test_csv_utils.py -k Resolve`

- [ ] **Step 3: Implement**

```python
AUTO_DELIMITER = "auto"
FALLBACK_DELIMITERS = {"orders": ",", "stock": ";"}


def resolve_delimiter(path: str, setting: str | None, kind: str) -> str:
    """The delimiter to read `path` with. An override wins; Auto detects.

    `setting` is the client's delimiter setting for `kind` ("orders" or
    "stock"): "auto" (or empty) reads the file's own delimiter, anything else
    is an override someone set on purpose (ADR 0009).
    """
    if setting and setting != AUTO_DELIMITER:
        return setting
    detected, method = detect_csv_delimiter(path)
    return FALLBACK_DELIMITERS[kind] if method == "default" else detected
```

(Verified at Stage A: a one-column file returns `(',', 'default')`, a `;` file `(';', 'sniffer')`.)

- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `csv_utils: resolve_delimiter, Auto or an override`.

---

### Task 2: `merge_csv_files` — the owning-file rule (F1, F2, F6)

**Files:**
- Modify: `shopify_tool/csv_utils.py:319-434` (`merge_csv_files`, replace wholesale)
- Test: `tests/test_csv_utils.py` class `TestMergeCsvFiles` — rewrite `test_merges_and_dedupes_on_keys` and update any other call in that class to the new signature.

**Interfaces:**
- Consumes: `resolve_delimiter(path, setting, kind)` (Task 1).
- Produces: `merge_csv_files(file_paths: list[str], delimiter_setting: str | None, kind: str, encoding: str = "utf-8-sig", dtype_dict: dict | None = None, add_source_column: bool = True, owner_key: str | None = None) -> tuple[pd.DataFrame, int]`. The int is the number of **distinct keys** skipped from non-owning files. `remove_duplicates` / `duplicate_keys` no longer exist.

- [ ] **Step 1: Write the failing tests** (helper `_touch(path, mtime)` = `os.utime(path, (mtime, mtime))`)

```python
import os


def _write(path, text, mtime):
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


class TestMergeCsvFiles:
    H = "Name,Lineitem sku,Lineitem quantity\n"

    def test_a_repeated_line_in_one_file_survives(self, tmp_path):
        """F1, the reported bug: #4148 carries SKU 501 on two real lines."""
        f = tmp_path / "a.csv"
        _write(f, self.H + "#4148,501,1\n#4148,501,1\n", 1000)
        merged, skipped = merge_csv_files([str(f)], ",", "orders", owner_key="Name")
        assert len(merged) == 2
        assert skipped == 0

    def test_an_overlapping_order_comes_whole_from_the_newest_file(self, tmp_path):
        old, new = tmp_path / "old.csv", tmp_path / "new.csv"
        _write(old, self.H + "#1,A,1\n#2,B,1\n", 1000)
        _write(new, self.H + "#2,B,1\n#2,C,1\n#3,D,1\n", 2000)
        merged, skipped = merge_csv_files(
            [str(old), str(new)], ",", "orders", owner_key="Name"
        )
        two = merged[merged["Name"] == "#2"]
        assert sorted(two["Lineitem sku"]) == ["B", "C"]
        assert set(two["_source_file"]) == {"new.csv"}
        assert sorted(merged["Name"].unique()) == ["#1", "#2", "#3"]
        assert skipped == 1

    def test_an_mtime_tie_falls_to_the_filename(self, tmp_path):
        a, b = tmp_path / "a.csv", tmp_path / "b.csv"
        _write(a, self.H + "#1,FROM_A,1\n", 1000)
        _write(b, self.H + "#1,FROM_B,1\n", 1000)
        merged, _ = merge_csv_files([str(b), str(a)], ",", "orders", owner_key="Name")
        assert merged["Lineitem sku"].tolist() == ["FROM_A"]

    def test_every_lot_row_of_a_sku_survives(self, tmp_path):
        """F2: lot-tracked stock lists a SKU once per lot."""
        f = tmp_path / "s.csv"
        _write(f, "SKU;Stock;Batch\n501;3;L1\n501;4;L2\n", 1000)
        merged, _ = merge_csv_files([str(f)], ";", "stock", owner_key="SKU")
        assert merged["Batch"].tolist() == ["L1", "L2"]

    def test_mixed_delimiters_merge(self, tmp_path):
        a, b = tmp_path / "a.csv", tmp_path / "b.csv"
        _write(a, self.H + "#1,A,1\n", 1000)
        _write(b, "Name;Lineitem sku;Lineitem quantity\n#2;B;1\n", 2000)
        merged, _ = merge_csv_files([str(a), str(b)], "auto", "orders", owner_key="Name")
        assert sorted(merged["Name"]) == ["#1", "#2"]

    def test_blank_keys_are_never_dropped(self, tmp_path):
        a, b = tmp_path / "a.csv", tmp_path / "b.csv"
        _write(a, self.H + ",A,1\n", 1000)
        _write(b, self.H + ",A,1\n", 2000)
        merged, skipped = merge_csv_files([str(a), str(b)], ",", "orders", owner_key="Name")
        assert len(merged) == 2
        assert skipped == 0

    def test_no_owner_key_is_a_plain_concat(self, tmp_path):
        a, b = tmp_path / "a.csv", tmp_path / "b.csv"
        _write(a, self.H + "#1,A,1\n", 1000)
        _write(b, self.H + "#1,A,1\n", 2000)
        merged, skipped = merge_csv_files([str(a), str(b)], ",", "orders", owner_key=None)
        assert len(merged) == 2
        assert skipped == 0

    def test_empty_file_list_raises(self):
        with pytest.raises(ValueError):
            merge_csv_files([], ",", "orders")
```

Keep any other existing test in the class, updating only its call to the new signature/return tuple.

- [ ] **Step 2: Run, expect failures** — `-k MergeCsvFiles`.

- [ ] **Step 3: Implement** (replace the whole function; keep `CSVLoadError` handling)

```python
def merge_csv_files(
    file_paths: list[str],
    delimiter_setting: str | None,
    kind: str,
    encoding: str = "utf-8-sig",
    dtype_dict: dict | None = None,
    add_source_column: bool = True,
    owner_key: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """Merge a folder's CSVs into one frame under the owning-file rule.

    Each key (`owner_key`'s value: an order number, or a SKU) is owned by the
    newest file containing it -- modified time, ties by filename. Every row of
    the owning file is kept; the key's rows in other files are skipped. A row
    is never dropped for repeating another row in the same file: an order may
    carry one SKU on several real lines (CONTEXT.md: order line).

    Returns the merged frame (newest file first) and how many distinct keys
    were skipped from non-owning files.
    """
    if not file_paths:
        raise ValueError("No files provided for merging")

    ranked = sorted(
        file_paths, key=lambda p: (-os.path.getmtime(p), os.path.basename(p))
    )
    frames = []
    owned: set = set()
    skipped: set = set()
    for filepath in ranked:
        try:
            df = pd.read_csv(
                filepath,
                delimiter=resolve_delimiter(filepath, delimiter_setting, kind),
                encoding=encoding,
                dtype=dtype_dict,
            )
        except Exception as e:
            logger.exception(f"✗ Failed to load {os.path.basename(filepath)}")
            raise CSVLoadError(f"Failed to load {os.path.basename(filepath)}: {e}") from e

        if owner_key and owner_key in df.columns:
            keys = df[owner_key]
            taken = keys.notna() & keys.isin(owned)
            skipped.update(keys[taken])
            df = df[~taken]
            owned.update(keys.dropna())
        elif owner_key:
            logger.warning(f"{os.path.basename(filepath)} has no '{owner_key}' column")

        if add_source_column:
            df = df.assign(_source_file=os.path.basename(filepath))
        frames.append(df)
        logger.info(f"✓ Loaded {len(df)} rows from {os.path.basename(filepath)}")

    merged = pd.concat(frames, ignore_index=True)
    if skipped:
        logger.info(f"Skipped {len(skipped)} overlapping {owner_key} values from older files")
    return merged, len(skipped)
```

Note `owned.update` runs **after** filtering the file against the previous `owned`, so a key repeated inside one file is never compared with itself.

- [ ] **Step 4: Run, expect PASS.** Also run `rg -n "merge_csv_files" --type py` — the only production caller is `gui/file_handler.py` (fixed in Task 4); it will be broken until then, so do not run the full suite between Task 2 and Task 4.
- [ ] **Step 5: Commit** — `csv_utils: folder merge keeps each key from its owning file (F1, F2, F6)`.

---

### Task 3: Every analysis-side read resolves its delimiter (F7, part 1)

**Files:**
- Modify: `shopify_tool/core.py` `_load_and_validate_files` (~l.515–670): the three `pd.read_csv` calls (stock ~l.562, orders ~l.604, orders-only ~l.655).
- Modify: `gui/actions_handler.py` ~l.1162–1169 (stock re-read).
- Modify: `gui/settings/weight.py:549` (`_weight_import_skus_from_stock_csv`).
- Modify: `gui/actions_handler.py` ~l.154–159: defaults `";"`/`","` → `AUTO_DELIMITER`.
- Test: `tests/test_core.py` (new test next to the `_run` helper class; reuse its `_ORDERS_MAPPING` and the `get_persistent_data_path` monkeypatch pattern shown at ~l.235).

**Interfaces:**
- Consumes: `resolve_delimiter`, `AUTO_DELIMITER` (Task 1).
- `run_full_analysis` keeps its signature; `stock_delimiter` / `orders_delimiter` now carry the **setting** (`"auto"` or an override).

- [ ] **Step 1: Failing test** — a `;`-separated orders file and a `,` stock file, called with `"auto", "auto"`, must succeed:

```python
def test_auto_reads_each_file_with_its_own_delimiter(self, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "get_persistent_data_path", lambda _n: tmp_path / "h.csv")
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name;Lineitem sku;Lineitem quantity;Shipping Method\n#1;A1;1;Standard\n",
        encoding="utf-8",
    )
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул,Име,Наличност\nA1,Widget,5\n", encoding="utf-8")
    ok, msg, final_df, _ = core.run_full_analysis(
        str(stock), str(orders), str(tmp_path / "out"), "auto", "auto",
        {
            "settings": {"repeat_detection_days": 1},
            "column_mappings": {
                "orders": _ORDERS_MAPPING,
                "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
            },
        },
    )
    assert ok, msg
    assert final_df["Order_Number"].tolist() == ["#1"]
```

(Place it as a method of the same test class as `_run` if that class carries fixtures; otherwise as a module-level function with the same body minus `self`.)

- [ ] **Step 2: Run, expect FAIL** (orders parsed as one column).
- [ ] **Step 3: Implement.** In each of the three core reads:

```python
delimiter=resolve_delimiter(stock_file_path, stock_delimiter, "stock"),
# and
delimiter=resolve_delimiter(orders_file_path, orders_delimiter, "orders"),
```

Import at the top of core: `from shopify_tool.csv_utils import resolve_delimiter` (check core's existing import style for csv_utils and follow it). Keep the `ParserError` messages, but print the resolved delimiter: bind it to a local first (`stock_sep = resolve_delimiter(...)`) and use that local in both `read_csv` and the error text.

actions_handler stock re-read:

```python
setting = self.mw.active_profile_config.get("settings", {}).get("stock_csv_delimiter")
stock_df = pd.read_csv(
    self.mw.stock_file_path,
    delimiter=resolve_delimiter(self.mw.stock_file_path, setting, "stock"),
    encoding="utf-8-sig",
)
```

actions_handler ~l.154–159: `.get("stock_csv_delimiter", AUTO_DELIMITER)` and `.get("orders_csv_delimiter", AUTO_DELIMITER)`.

weight.py:549: `df = pd.read_csv(file_path, sep=resolve_delimiter(file_path, self.stock_csv_delimiter, "stock"), dtype=str)`.

- [ ] **Step 4: Run** `tests/test_core.py tests/test_actions_handler*.py tests/test_settings*weight*.py` (whatever exists; `ls tests | rg -i weight`). Expect PASS.
- [ ] **Step 5: Commit** — `Analysis reads resolve the delimiter per file (F7)`.

---

### Task 4: FileHandler — slots, folder merge, copy (F1 wiring, F5, F7 part 2)

**Files:**
- Modify: `gui/file_handler.py`
  - delete `_FOLDER_REMOVE_DUPLICATES` (l.19) and its comment lines mentioning it; keep `_FOLDER_SCAN_RECURSIVE`.
  - `select_orders_file` (~l.44–120) and `select_stock_file` (~l.150–215): replace the detect/try/except/toast block with one resolved delimiter; delete the toast.
  - delete `_save_default_delimiter` (~l.122–148).
  - `validate_file` (~l.325–420): orders currently hardcodes `delimiter = ","`, stock reads the setting — both resolve.
  - `validate_multiple_files` (~l.640–700): replace the inline `detect_csv_delimiter` with `resolve_delimiter`, delete the dead `config.get(...)` statement.
  - `show_file_preview` (~l.715–760): new copy.
  - `merge_and_save_files` (~l.762–870): new call, write sep, return tuple.
  - folder branch (~l.543–565): use the tuple; new summary.
- Test: `tests/test_file_handler.py`.

**Interfaces:**
- Consumes: `resolve_delimiter`, `AUTO_DELIMITER` (Task 1); `merge_csv_files(...) -> (df, skipped)` (Task 2).
- Produces: `FileHandler._delimiter_for(self, kind: str, path: str) -> str` and `FileHandler.merge_and_save_files(file_paths, file_type, original_folder) -> tuple[str, int, int]` = `(merged_path, row_count, skipped_keys)`.

- [ ] **Step 1: Failing tests.** Delete `test_a_delimiter_mismatch_loads_with_the_detected_one_and_offers_to_save_it` and `test_a_failed_delimiter_save_tells_the_user` (the behaviour is removed by ADR 0009). Add:

```python
def test_a_semicolon_orders_file_loads_under_auto_without_a_toast(
    main_window, tmp_path, monkeypatch
):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name;Lineitem sku;Lineitem quantity;Shipping Method\n#1;A1;2;Standard\n"
    )
    main_window.active_profile_config.setdefault("settings", {})["orders_csv_delimiter"] = "auto"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(orders), ""))
    toasts = Mock()
    monkeypatch.setattr("gui.file_handler.toast", toasts)

    main_window.file_handler.select_orders_file()

    toasts.assert_not_called()
    assert main_window.orders_slot.is_valid is True


def test_a_folder_merge_keeps_repeat_lines_and_reports_overlaps(
    main_window, tmp_path, monkeypatch
):
    folder = tmp_path / "exports"
    folder.mkdir()
    header = "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
    old, new = folder / "a.csv", folder / "b.csv"
    old.write_text(header + "#4148,501,1,Standard\n#4148,501,1,\n#9,X,1,Standard\n")
    new.write_text(header + "#9,X,1,Standard\n")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    monkeypatch.setattr(main_window.file_handler, "show_file_preview", lambda *a, **k: True)

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    text = main_window.orders_slot._loaded_summary.text()
    assert "2 files merged" in text
    assert "3 rows" in text
    assert "1 overlapping order skipped" in text
    merged = pd.read_csv(main_window.orders_file_path)
    assert (merged["Name"] == "#4148").sum() == 2


def test_the_merged_file_is_written_with_the_override(main_window, tmp_path):
    header = "Name;Lineitem sku;Lineitem quantity;Shipping Method\n"
    f = tmp_path / "a.csv"
    f.write_text(header + "#1;A1;1;Standard\n")
    main_window.active_profile_config.setdefault("settings", {})["orders_csv_delimiter"] = ";"

    path, rows, skipped = main_window.file_handler.merge_and_save_files(
        [str(f)], "orders", str(tmp_path)
    )

    assert open(path, encoding="utf-8-sig").readline().count(";") == 4
    assert (rows, skipped) == (1, 0)
```

Check the existing `main_window` fixture (top of the file) for how `active_profile_config` and `column_mappings` are set up; if the orders mapping is not the Shopify default, adjust the header in these tests to the columns the fixture maps. Add `import os` / `import pandas as pd` if missing. The existing `test_a_dropped_folder_merges_its_csvs_into_the_slot` should keep passing unchanged (2 rows, no overlaps → no skipped segment).

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Implement.**

Helper on `FileHandler`:

```python
def _delimiter_for(self, kind: str, path: str) -> str:
    """The delimiter `path` is read with: the client's override, or Auto."""
    settings = (self.mw.active_profile_config or {}).get("settings", {})
    return resolve_delimiter(path, settings.get(f"{kind}_csv_delimiter"), kind)
```

`select_orders_file`: after `self.log.info(f"Orders file selected: ...")`, replace everything up to `# Load and store original orders DataFrame` with `delimiter = self._delimiter_for("orders", filepath)`. Same for `select_stock_file` up to `# Try to load CSV with determined delimiter` (`"stock"`). The stock error message keeps `{delimiter!r}` but reads "Check the stock delimiter in Settings › General (it read {delimiter!r}), then choose the file again." Update both docstrings: drop "prompts user if detected delimiter differs".

`validate_file`: orders branch `delimiter = self._delimiter_for("orders", path)`; stock branch `delimiter = self._delimiter_for("stock", path)`. `path` is assigned just above in each branch; move the delimiter line after the `if not path: return` guard if needed so `resolve_delimiter` never gets `None`.

`validate_multiple_files`: `file_delimiter = self._delimiter_for(file_type, filepath)`.

`show_file_preview`: replace the `_FOLDER_REMOVE_DUPLICATES` block with

```python
thing = "An order" if file_type == "orders" else "A SKU"
msg += f"{thing} found in more than one file is taken from the newest file.\n\n"
```

`merge_and_save_files`: keep the dtype discovery; replace the duplicate-key discovery with an owner key, then

```python
owner_key = next(
    (c for c, n in mappings.items() if n == ("Order_Number" if file_type == "orders" else "SKU")),
    None,
)
if owner_key is None:
    self.log.warning(f"No column mapped as the {file_type} key; merging without the owning-file rule")
setting = config.get("settings", {}).get(f"{file_type}_csv_delimiter")
merged_df, skipped = merge_csv_files(
    file_paths, setting, file_type, dtype_dict=dtype_dict,
    add_source_column=True, owner_key=owner_key,
)
...
sep = "," if not setting or setting == AUTO_DELIMITER else setting
merged_df.to_csv(merged_path, index=False, encoding="utf-8-sig", sep=sep)
return str(merged_path), len(merged_df), skipped
```

(`mappings` = `column_mappings.get(file_type, {})`; the per-kind delimiter/`sku_col_name` code it replaces goes.)

Folder branch:

```python
merged_path, rows, skipped = self.merge_and_save_files(valid_files, file_type, folder_path)
...
summary = f"{len(valid_files)} files merged · " + f"{rows:,} rows".replace(",", " ")
if skipped:
    noun = "order" if file_type == "orders" else "SKU"
    summary += f" · {skipped} overlapping {noun}{'' if skipped == 1 else 's'} skipped"
if invalid_files:
    summary += f" · {len(invalid_files)} skipped"
```

Remove now-unused imports (`toast` only if nothing else in the file uses it — `rg -n "toast\(" gui/file_handler.py`; `detect_csv_delimiter` imports).

- [ ] **Step 4: Run** `tests/test_file_handler.py tests/test_csv_utils.py`, then the **full suite** (the Task 2 breakage is now fixed). Expect PASS.
- [ ] **Step 5: Commit** — `FileHandler: Auto delimiter everywhere, owning-file merge, honest summary (F1, F5, F7)`.

---

### Task 5: Analysis cleaning — fills stay inside the order, stock SKUs normalize first (F3, F4)

**Files:**
- Modify: `shopify_tool/analysis.py` `_clean_and_prepare_data` — the fill block (~l.297–325) and the start of stock cleaning (~l.444, before `if not lot_columns_present:`).
- Test: `tests/test_analysis.py` (new tests; follow the file's existing import of `_clean_and_prepare_data` / `run_analysis` if present).

**Interfaces:** none new.

- [ ] **Step 1: Failing tests**

```python
import io

import pandas as pd

from shopify_tool.analysis import _clean_and_prepare_data, run_analysis

_MAPS = {
    "orders": {
        "Name": "Order_Number", "Lineitem sku": "SKU", "Lineitem quantity": "Quantity",
        "Tags": "Tags", "Shipping Method": "Shipping_Method",
    },
    "stock": {"SKU": "SKU", "Stock": "Stock"},
}
_ORDERS = (
    "Name,Lineitem sku,Lineitem quantity,Tags,Shipping Method\n"
    "#4148,501,1,vip,DHL\n#4148,501,1,,\n#4149,777,2,,\n"
)


def _orders():
    return pd.read_csv(io.StringIO(_ORDERS), dtype={"Lineitem sku": str})


def _stock(text):
    return pd.read_csv(io.StringIO(text), sep=";", dtype={"SKU": str})


def test_an_untagged_order_does_not_inherit_the_previous_orders_tags_or_courier():
    """F3: #4149 used to come out tagged 'vip' and shipped by DHL."""
    orders, _, _ = _clean_and_prepare_data(_orders(), _stock("SKU;Stock\n501;5\n777;5\n"), _MAPS)
    by_order = orders.set_index("Order_Number")
    assert pd.isna(by_order.loc["#4149", "Tags"])
    assert pd.isna(by_order.loc["#4149", "Shipping_Method"])
    assert (orders[orders["Order_Number"] == "#4148"]["Shipping_Method"] == "DHL").all()


def test_stock_sku_variants_collapse_to_one_sku():
    """F4: '501 ' and '501.0' are one SKU, normalized before dedupe."""
    _, stock, _ = _clean_and_prepare_data(_orders(), _stock("SKU;Stock\n501 ;5\n501.0;3\n777;1\n"), _MAPS)
    assert stock["SKU"].tolist().count("501") == 1


def test_blank_stock_skus_are_still_dropped():
    _, stock, _ = _clean_and_prepare_data(_orders(), _stock("SKU;Stock\n;9\n501;5\n"), _MAPS)
    assert "" not in stock["SKU"].tolist()
    assert stock["SKU"].notna().all()


def test_missing_optional_columns_still_clean():
    bare = pd.read_csv(
        io.StringIO("Name,Lineitem sku,Lineitem quantity\n#1,A,1\n"),
        dtype={"Lineitem sku": str},
    )
    orders, _, _ = _clean_and_prepare_data(bare, _stock("SKU;Stock\nA;1\n"), _MAPS)
    assert len(orders) == 1


def test_every_order_line_in_is_one_line_out():
    """Invariant: without set decoders, analysis never adds or drops a line."""
    stock = _stock("SKU;Stock\n501 ;5\n501.0;3\n777;9\n")
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    final = run_analysis(stock, _orders(), history, _MAPS)[0]
    assert final.groupby("Order_Number").size().to_dict() == {"#4148": 2, "#4149": 1}
```

If `run_analysis`'s return shape differs from `[0] == final_df`, read its docstring (analysis.py ~l.1373) and index accordingly.

- [ ] **Step 2: Run, expect the first, second and last to FAIL.**

- [ ] **Step 3: Implement.** Replace the bare fills:

```python
    # Shopify writes order-level fields on an order's first line only. Fill
    # within the order, never from the one above it: an order with no tags or
    # no shipping method must not inherit the previous order's (F3).
    order_level = [
        "Shipping_Method", "Shipping_Country", "Total_Price", "Subtotal", "Tags",
        "Customer", "Created_At",
    ]
    if additional_columns_config:
        order_level += [
            col["internal_name"]
            for col in additional_columns_config
            if col.get("is_order_level", False) and col.get("enabled", True)
        ]
    for col in order_level:
        if col in orders_df.columns:
            orders_df[col] = orders_df.groupby("Order_Number")[col].ffill()
```

This replaces: the five `if "X" in orders_df.columns: orders_df["X"] = orders_df["X"].ffill()` lines, the existing `for col in ("Customer", "Created_At")` loop and its comment, and the `# Forward-fill additional order-level columns from config` block. Keep `orders_df["Order_Number"] = orders_df["Order_Number"].ffill()` exactly as is, before this block.

At the start of stock cleaning, right after the `missing_stock_cols` check and before `stock_lot_cols = ...`:

```python
    # Normalize before any dedupe or aggregation: "501 " and "501.0" are one
    # SKU, and deduping first let both through to double every order line
    # the merge matched against them (F4). Blank SKUs stay blank so dropna
    # still drops them -- normalize_sku(NaN) would return "".
    stock_df = stock_df.copy()
    has_sku = stock_df["SKU"].notna()
    stock_df.loc[has_sku, "SKU"] = stock_df.loc[has_sku, "SKU"].map(normalize_sku)
```

Then delete the now-redundant later normalizations: `stock_clean_df["SKU"] = stock_clean_df["SKU"].apply(normalize_sku)` in both branches, and change `fifo_lots = {normalize_sku(k): v for k, v in fifo_lots.items()}` block to plain `fifo_lots = _build_fifo_lots(stock_df)` (keys are already normalized). If `stock_df["SKU"]` may be non-string (ints) and `normalize_sku` expects any type — it does (it handles floats) — no cast is needed.

- [ ] **Step 4: Run** `tests/test_analysis.py tests/test_core.py`, then the full suite. Expect PASS. If an existing test asserted cross-order fill behaviour, it pinned F3; update it to the within-order expectation and say so in the commit body.
- [ ] **Step 5: Commit** — `analysis: order-level fills stay in the order; stock SKUs normalize first (F3, F4)`.

---

### Task 6: Settings combo, migration, new-client defaults (ADR 0009)

**Files:**
- Modify: `gui/settings/general.py` (both delimiter `QLineEdit`s → `QComboBox`).
- Modify: `shopify_tool/profile_migrations.py` (new `migrate_delimiters_to_auto`).
- Modify: `shopify_tool/profile_manager.py` (~l.31–37 import, ~l.573 call + `or` chain ~l.583; new-client defaults ~l.443–444).
- Modify: `gui/settings/window.py` ~l.156 (settings fallback dict).
- Test: `tests/test_settings_page_general.py`, `tests/test_profile_migrations.py` (create if absent: `ls tests | rg -i migration`).

**Interfaces:**
- Consumes: `AUTO_DELIMITER` (Task 1).
- Produces: `migrate_delimiters_to_auto(client_id: str, config: dict) -> bool`.

- [ ] **Step 1: Failing tests**

Settings page (update `test_general_page_falls_back_to_defaults` to expect `"auto"` for both delimiters; keep the other two tests):

```python
def test_auto_and_tab_round_trip(qapp):
    settings = {**sample_settings(), "stock_csv_delimiter": "auto", "orders_csv_delimiter": "\t"}
    expected = dict(settings)
    assert GeneralPage(settings).collect() == {"settings": expected}


def test_unknown_delimiter_survives_a_round_trip(qapp):
    settings = {**sample_settings(), "orders_csv_delimiter": "::"}
    expected = dict(settings)
    assert GeneralPage(settings).collect() == {"settings": expected}


def test_delimiters_are_offered_as_a_list(qapp):
    page = GeneralPage({})
    assert page.orders_delimiter_combo.itemData(0) == "auto"
    assert [page.orders_delimiter_combo.itemData(i) for i in range(5)] == ["auto", ",", ";", "\t", "|"]
```

Migration:

```python
from shopify_tool.profile_migrations import migrate_delimiters_to_auto


def test_existing_delimiters_become_auto_once():
    config = {"settings": {"stock_csv_delimiter": ";", "orders_csv_delimiter": ","}}
    assert migrate_delimiters_to_auto("ACME", config) is True
    assert config["settings"]["stock_csv_delimiter"] == "auto"
    assert config["settings"]["orders_csv_delimiter"] == "auto"
    assert config["settings"]["delimiter_auto_migrated"] is True


def test_marker_protects_a_later_override():
    config = {"settings": {"stock_csv_delimiter": ";", "orders_csv_delimiter": "auto",
                           "delimiter_auto_migrated": True}}
    assert migrate_delimiters_to_auto("ACME", config) is False
    assert config["settings"]["stock_csv_delimiter"] == ";"


def test_a_config_without_settings_gets_them():
    config = {}
    assert migrate_delimiters_to_auto("ACME", config) is True
    assert config["settings"]["orders_csv_delimiter"] == "auto"
```

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Implement.**

`profile_migrations.py` (append; it may not import csv_utils — use the literal `"auto"` there with a comment pointing to `csv_utils.AUTO_DELIMITER`, to avoid a new import edge, or import it if csv_utils has no import back into profile code: check with `rg -n "^from|^import" shopify_tool/csv_utils.py`):

```python
def migrate_delimiters_to_auto(client_id: str, config: dict) -> bool:
    """Move a profile's CSV delimiters to Auto, once (ADR 0009).

    Stored delimiters were defaults nobody picked. After this runs the
    marker stays set, so an override chosen later is never reset.
    """
    settings = config.setdefault("settings", {})
    if settings.get("delimiter_auto_migrated"):
        return False
    settings["stock_csv_delimiter"] = "auto"
    settings["orders_csv_delimiter"] = "auto"
    settings["delimiter_auto_migrated"] = True
    logger.info(f"Delimiters set to Auto for CLIENT_{client_id}")
    return True
```

`profile_manager.py`: import it beside `migrate_delimiter_config_v1_to_v2`; add `migrated_auto_delimiters = migrate_delimiters_to_auto(client_id, config)` right after the `migrate_delimiter_config_v1_to_v2` call, and `or migrated_auto_delimiters` to the save condition. New-client defaults (~l.443): `"stock_csv_delimiter": "auto", "orders_csv_delimiter": "auto", "delimiter_auto_migrated": True`. `gui/settings/window.py` ~l.156: `"stock_csv_delimiter": "auto"`.

`general.py`:

```python
_DELIMITERS = [
    ("Auto — detect per file", "auto"),
    ("Comma  ,", ","),
    ("Semicolon  ;", ";"),
    ("Tab", "\t"),
    ("Pipe  |", "|"),
]
_DELIMITER_TOOLTIP = (
    "Auto reads each file's own delimiter.\n"
    "Pick a character only for a client whose files Auto reads wrong."
)


def _delimiter_combo(value: str) -> QComboBox:
    combo = QComboBox()
    for label, data in _DELIMITERS:
        combo.addItem(label, data)
    index = combo.findData(value)
    if index < 0:  # hand-edited value: keep it rather than rewrite it on save
        combo.addItem(repr(value), value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)
    return combo
```

In `__init__`: `self.stock_delimiter_combo = _delimiter_combo(settings.get("stock_csv_delimiter", "auto"))` and the orders equivalent; `section.add_row("Stock CSV Delimiter:", self.stock_delimiter_combo, tooltip=_DELIMITER_TOOLTIP)` (same for orders). Drop `setMaximumWidth(100)` for the combos (the Auto label needs room); do not add colours or stylesheets. In `collect()`: `self.stock_delimiter_combo.currentData()` / `self.orders_delimiter_combo.currentData()`. Import `QComboBox`. `rg -n "delimiter_edit" gui tests` — update any other reference (e.g. `gui/settings/window.py:265` reads the config, not the widget; leave it unless it reads `*_delimiter_edit`).

- [ ] **Step 4: Run** the two test files, then the full suite. Expect PASS.
- [ ] **Step 5: Commit** — `Settings: delimiter is Auto or an override; profiles migrate to Auto once (ADR 0009)`.

---

### Task 7: Finish

- [ ] Full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q` — all pass; record the count.
- [ ] `.venv/bin/ruff check . --exclude shared` — clean.
- [ ] Re-run the Stage A repro as a sanity check (it lives outside the repo and may be gone; the Task 2/5 tests cover it — skip if absent): `/home/gloopy/.claude/jobs/eced6b35/tmp/repro.py`.
- [ ] `rg -n "remove_duplicates|duplicate_keys|_FOLDER_REMOVE_DUPLICATES|_save_default_delimiter|Save as default" gui shopify_tool tests` — no hits.
- [ ] `graphify update .`
- [ ] Commit anything left; push `worktree-phase12-bundle3`. No PR — Stage C opens it.
