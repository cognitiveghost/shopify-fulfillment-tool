# After Phase 9 — Quick Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do **not** fan out to subagents — this repo's runner works in-session.

**Goal:** Stop the client-config corruption seen on the Windows share, fix inventory memory and the reported barcode/logs complaints, and clear nine UI defects read off the 2026-09-14 Windows build screenshots.

**Architecture:** Three unrelated layers. (1) `shopify_tool/` — replace two hand-rolled "safe save" implementations with the already-correct `shared/atomic_write.py`, a net deletion. (2) `gui/` PySide6 widgets — surface save failures and fix Qt-side layout/affordance defects. (3) `gui/web/` — the Results screen is HTML/CSS/JS behind `QWebEngineView` (ADR 0001), so the bulk menu and column manager fixes are JS/CSS, not Python.

**Tech Stack:** Python 3, PySide6, pandas, pytest (`QT_QPA_PLATFORM=offscreen`), vanilla JS + CSS for the Results tier.

**Spec:** `docs/superpowers/specs/2026-09-15-post-phase9-quickfixes-design.md`
**Decision record:** `docs/adr/0008-config-writes-are-atomic-not-locked.md`

## Global Constraints

- **Never hand-edit `shared/`.** It is synced one-way from `packing-tool`. `shared/atomic_write.py` is already correct — read it, call it, do not change it.
- **No hardcoded colours anywhere.** Use `theme.*` tokens in Python and `var(--token)` in CSS. `python scripts/style_lint.py` must stay clean under `gui/`. Note: `style_lint.py` misreads a JS/CSS selector like `#add-filter` as the hex colour `#add` — if it flags one, that is the known false positive, leave the selector alone.
- **No animation, `text-shadow`, or `filter: drop-shadow`** in `gui/web/` assets.
- Ship as **one PR** (user decision, spec §7 Q1). Commit per task so review can read it in order.
- Gate before the PR: `QT_QPA_PLATFORM=offscreen python -m pytest` (baseline **1749 passed** at `d070c2e`), `ruff check . --exclude shared`, `python scripts/style_lint.py`.
- Run `graphify update .` after the Python changes land.
- **Do not touch the version string.** This batch is not a release.
- Out of scope, do not drift into it: the Settings form restyle (trailing colons, label styling, field widths beyond the one full-bleed spinbox), and the barcode *generation* path itself.

---

### Task 1: Route config writes through `shared/atomic_write.py`

The headline fix. See spec §1 and ADR 0008 for why the existing code corrupts files.

**Files:**
- Modify: `shopify_tool/profile_manager.py` — delete `_save_with_windows_lock` (:900-953) and `_save_with_unix_lock` (:957-989); replace the retry loops in `save_shopify_config` (:653-710) and `save_client_config` (:1122-1175)
- Modify: `shopify_tool/groups_manager.py` — delete `_save_with_windows_lock` (:204-250) and `_save_with_unix_lock` (:252-…); replace the retry loop at :164-200
- Test: `tests/test_profile_manager.py`, `tests/test_groups_manager.py`

**Interfaces:**
- Consumes: `shared.atomic_write.atomic_write_json(path, data, *, indent=2, ensure_ascii=False, retries=3, retry_delay=0.15)` — raises the last exception if every attempt fails, returns `None` on success.
- Produces: `save_shopify_config`, `save_client_config` and `GroupsManager.save_groups` keep their existing signatures and their `bool` return. Task 2 depends on those returns being honest.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_profile_manager.py`:

```python
def test_save_shopify_config_is_atomic_and_leaves_no_temp(tmp_path, monkeypatch):
    """A shorter document must fully replace a longer one, with no .tmp left behind."""
    pm = _make_profile_manager(tmp_path)          # existing helper in this module
    pm.create_client_profile("ALMA")

    big = {"settings": {"orders_csv_delimiter": ","}, "filler": ["x"] * 500}
    assert pm.save_shopify_config("ALMA", big) is True

    small = {"settings": {"orders_csv_delimiter": ";"}}
    assert pm.save_shopify_config("ALMA", small) is True

    config_path = tmp_path / "Clients" / "CLIENT_ALMA" / "shopify_config.json"
    reloaded = json.loads(config_path.read_text(encoding="utf-8"))
    assert reloaded["settings"]["orders_csv_delimiter"] == ";"
    assert "filler" not in reloaded          # no surviving tail from the longer write
    assert list(config_path.parent.glob("*.tmp")) == []


def test_save_shopify_config_has_no_fixed_temp_name(tmp_path):
    """Two saves must not collide on one shared temp path."""
    import inspect
    src = inspect.getsource(type(_make_profile_manager(tmp_path)))
    assert 'with_suffix(".tmp")' not in src
    assert "msvcrt" not in src
    assert "shutil.move" not in src
```

If `_make_profile_manager` does not exist in that module, read the file's existing fixtures and use whatever it already uses to build a `ProfileManager` over `tmp_path` — do not invent a new fixture style.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_profile_manager.py -k atomic -v`
Expected: FAIL — `filler` survives, or a `.tmp` file remains, or the source assertions trip.

- [ ] **Step 3: Replace the save body in `save_shopify_config`**

Delete the whole `max_retries` / `for attempt in range(...)` block and its timeout check. The method keeps everything above it (the size logging, the backup call, the timestamp stamping) and ends with:

```python
        try:
            atomic_write_json(config_path, config)
        except OSError as e:
            error_msg = f"Failed to save config for CLIENT_{client_id}: {e}"
            logger.exception(error_msg)
            raise ProfileManagerError(error_msg) from e

        self._config_cache.pop(f"{self.base_path}::shopify_{client_id}", None)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Config saved for CLIENT_{client_id} in {elapsed_ms:.0f}ms"
        )
        return True
```

Add `from shared.atomic_write import atomic_write_json` to the module imports.

**Note the cache line moved out of the success branch** — it now runs on every successful write, and a failed write raises before reaching it. That is deliberate: spec §2 records that invalidating only on success left a stale entry behind.

- [ ] **Step 4: Replace the save body in `save_client_config` the same way**

Identical shape, with the client-config cache key and message:

```python
        try:
            atomic_write_json(config_path, config)
        except OSError as e:
            error_msg = f"Failed to save client config for CLIENT_{client_id}: {e}"
            logger.exception(error_msg)
            raise ProfileManagerError(error_msg) from e

        self._config_cache.pop(f"{self.base_path}::client_{client_id}", None)
        logger.info(f"Client config saved for CLIENT_{client_id}")
        return True
```

- [ ] **Step 5: Replace the save body in `groups_manager.save_groups`**

```python
        try:
            atomic_write_json(self.groups_path, groups_data)
        except OSError as e:
            error_msg = f"Failed to save groups configuration: {e}"
            logger.exception(error_msg)
            raise GroupsManagerError(error_msg) from e

        logger.info("Groups configuration saved")
        return True
```

- [ ] **Step 6: Delete the four lock helpers and their now-dead imports**

Remove `_save_with_windows_lock` and `_save_with_unix_lock` from both modules. Then remove any of `msvcrt`, `fcntl`, `shutil`, `time` that no longer have a user in the file — check with `ruff check` rather than by eye, and do not remove one that is still used elsewhere in the module.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest && ruff check . --exclude shared`
Expected: PASS, at least 1749 + 2 tests. If an existing test asserted on the "attempt n/5" log text or on the lock helpers, update it — those are assertions about the bug.

- [ ] **Step 8: Commit**

```bash
git add shopify_tool/profile_manager.py shopify_tool/groups_manager.py tests/test_profile_manager.py tests/test_groups_manager.py
git commit -m "Config writes are atomic: use shared/atomic_write, delete the lock machinery"
```

---

### Task 2: Make a failed save visible

Spec §2. Right now every caller ignores the return value and the toast fires before the write is confirmed, so a failure is invisible to the operator.

**Files:**
- Modify: `gui/file_handler.py:132-137` (`_save_default_delimiter`)
- Modify: `gui/actions_handler.py:379-386` (post-Settings reload)
- Test: `tests/test_file_handler.py` (create if absent), `tests/test_actions_handler.py`

**Interfaces:**
- Consumes: `save_shopify_config` from Task 1 — returns `True`, or raises `ProfileManagerError`.
- Produces: nothing downstream depends on this task.

- [ ] **Step 1: Write the failing test**

```python
def test_failed_delimiter_save_tells_the_user(qtbot, monkeypatch, main_window):
    """A save that raises must not leave the user believing it worked."""
    from shopify_tool.profile_manager import ProfileManagerError

    def boom(*a, **kw):
        raise ProfileManagerError("share unreachable")

    monkeypatch.setattr(main_window.profile_manager, "save_shopify_config", boom)

    seen = []
    monkeypatch.setattr("gui.file_handler.toast",
                        lambda parent, text, **kw: seen.append((text, kw.get("role"))))

    main_window.active_profile_config = {"client_id": "ALMA", "settings": {}}
    main_window.file_handler._save_default_delimiter("orders", ";", "ALMA")

    assert seen, "a failed save must raise a toast"
    assert seen[-1][1] == "error"
    assert "couldn't" in seen[-1][0].lower() or "not saved" in seen[-1][0].lower()
```

Follow the fixture style already used in `tests/test_actions_handler.py` for building `main_window` — read it first rather than inventing one.

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_file_handler.py -k failed_delimiter -v`
Expected: FAIL — the exception escapes, or no error toast is recorded.

- [ ] **Step 3: Handle the failure in `_save_default_delimiter`**

```python
        if client_id and hasattr(self.mw, "profile_manager"):
            try:
                self.mw.profile_manager.save_shopify_config(
                    client_id, self.mw.active_profile_config
                )
            except Exception:
                self.log.exception(f"Failed to save {kind} delimiter")
                toast(
                    self.mw,
                    f"The {kind} delimiter wasn't saved. Details are in Logs.",
                    role="error",
                )
                return
            self.log.info(f"Saved {kind} delimiter '{delimiter}' to config")
```

Copy follows the Phase 9 rule the spec's UI section records: say what happened and where to look, do not apologise.

- [ ] **Step 4: Guard the post-Settings reload the same way**

At `gui/actions_handler.py:381` the reload is already inside a `try`. Confirm its `except` raises a visible error rather than only logging; if it only logs, add `show_error(self.mw, "Settings couldn't be reloaded", "Details are in Logs.")`.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_file_handler.py tests/test_actions_handler.py -v
git add gui/file_handler.py gui/actions_handler.py tests/
git commit -m "A failed config save now tells the operator instead of toasting success"
```

---

### Task 3: Inventory memory covers the whole stock file

Spec §3 and §7 Q2. Today the snapshot is built from `final_df`, the analysis result, so a SKU with no orders in the run vanishes from memory.

**Files:**
- Modify: `shopify_tool/core.py` — new `build_inventory_snapshot`; `_save_results_and_reports` signature (:926-939) and its snapshot block (:1160-1190); the call site (:1339)
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `final_df` — the analysis result, with `SKU` and `Final_Stock`. `stock_df` — the loaded stock frame, with `SKU` and a stock-quantity column.
- Produces: `build_inventory_snapshot(final_df, stock_df) -> dict[str, float]`, passed to `profile_manager.save_inventory_memory` in place of the old inline expression.

**Heads-up — `stock_df` is not currently in scope where the snapshot is built.** `_save_results_and_reports` takes `stock_file_path` (a path), not the frame. `stock_df` does exist in the caller, `run_analysis`, at `:1290`/`:1334`. Step 4 threads it through; do not re-read the CSV from disk instead.

Note the two shapes `stock_df` can take: loaded from CSV it carries the config-mapped column names, but when it is reconstructed from inventory memory (`:676`) its columns are exactly `SKU`, `Product_Name`, `Stock`. The column-detection list in Step 3 must cover both.

- [ ] **Step 1: Write the failing test**

```python
def test_inventory_memory_keeps_skus_with_no_orders(tmp_path):
    """A SKU present in stock but absent from every order must still be remembered."""
    stock_df = pd.DataFrame({
        "SKU": ["A-1", "B-2", "C-3"],
        "Warehouse_Stock": [10.0, 5.0, 7.0],
        "Warehouse_Name": ["Alpha", "Beta", "Gamma"],
    })
    final_df = pd.DataFrame({          # only A-1 was ordered
        "SKU": ["A-1"],
        "Final_Stock": [6.0],
        "Warehouse_Name": ["Alpha"],
    })

    result = build_inventory_snapshot(final_df, stock_df)

    assert result == {"A-1": 6.0, "B-2": 5.0, "C-3": 7.0}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_core.py -k inventory_memory_keeps -v`
Expected: FAIL with `NameError: build_inventory_snapshot`.

- [ ] **Step 3: Extract the snapshot builder**

Add to `shopify_tool/core.py`, above the block at :1160:

```python
def build_inventory_snapshot(final_df, stock_df) -> dict:
    """Post-fulfilment stock per SKU, seeded from the whole stock file.

    Every SKU in the stock file is remembered. SKUs the run actually touched
    get their post-fulfilment Final_Stock; the rest keep their opening level.
    A SKU absent from the stock file drops out — the stock file is the truth
    for what still exists (ADR-free decision, spec section 7 Q2).
    """
    snapshot = {}

    if stock_df is not None and "SKU" in stock_df.columns:
        stock_col = next(
            (c for c in ("Warehouse_Stock", "Stock", "Quantity")
             if c in stock_df.columns),
            None,
        )
        if stock_col:
            snapshot = (
                stock_df.groupby("SKU")[stock_col]
                .last()
                .dropna()
                .apply(lambda x: max(0.0, float(x)))
                .to_dict()
            )

    if final_df is not None and {"SKU", "Final_Stock"} <= set(final_df.columns):
        snapshot.update(
            final_df.groupby("SKU")["Final_Stock"]
            .last()
            .dropna()
            .apply(lambda x: max(0.0, float(x)))
            .to_dict()
        )

    return snapshot
```

Confirm the real stock-quantity column name by reading how `stock_df` is built earlier in `core.py` — if it is none of the three guessed above, use the actual one and drop the fallback list.

- [ ] **Step 4: Thread `stock_df` into `_save_results_and_reports` and call the builder**

Add the parameter to the signature at `:926`, immediately after `final_df` so the frames stay together:

```python
def _save_results_and_reports(
    final_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    summary_present_df: pd.DataFrame,
    ...
```

Update its docstring Args block, then pass it at the call site (`:1339`):

```python
        primary_path, _ = _save_results_and_reports(
            final_df,
            stock_df,
            summary_present_df,
            ...
```

`_save_results_and_reports` is called in exactly one place — confirm with `grep -n "_save_results_and_reports(" shopify_tool/core.py` before editing, and if a test calls it directly, update that call too.

Then replace the `final_stock_dict = (...)` expression at `:1164` with:

```python
                final_stock_dict = build_inventory_snapshot(final_df, stock_df)
```

Leave the `names_dict` logic below it untouched — it already guards against wiping good names with an empty dict.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_core.py -v
git add shopify_tool/core.py tests/test_core.py
git commit -m "Inventory memory remembers every SKU in the stock file, not just the ordered ones"
```

---

### Task 4: Barcode status label + generation diagnostics

Spec §4 and §7 Q4. **Do not change the generation path** — it is not reproducibly broken. This task makes the screen honest and makes the next Windows run capture its own evidence.

**Files:**
- Modify: `gui/barcode_generator_widget.py` — around :305-330 (packing-list selection) and :450 (completion label)
- Test: `tests/test_barcode_generator_widget.py`

- [ ] **Step 1: Write the failing test**

```python
def test_status_label_clears_when_packing_list_changes(qtbot, barcode_widget):
    """A previous run's count must not linger over a newly chosen packing list."""
    barcode_widget.status_label.setText("Complete: 34 barcodes generated")

    barcode_widget._on_packing_list_changed()      # name it as the real slot is named

    assert barcode_widget.status_label.text() == ""
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k status_label_clears -v`
Expected: FAIL — the stale text survives.

- [ ] **Step 3: Clear the label on selection change**

In the packing-list selection handler (the method containing `packing_list_orders = set(...)` at :302), immediately after the `try:` opens, add:

```python
        self.status_label.setText("")
        self.status_label.setStyleSheet("")
```

- [ ] **Step 4: Log what was actually generated**

In `_on_generation_complete` (:445), alongside the existing counts, add the detail a reproduction needs:

```python
        self.log.info(
            f"Barcode generation complete for packing list "
            f"{self.packing_list_combo.currentText()!r}: "
            f"{self.filtered_orders_df['Order_Number'].nunique()} orders filtered, "
            f"{len(successful)} labels written, {len(failed)} failed"
        )
```

Use whatever the packing-list widget is actually called — read the file, do not assume `packing_list_combo`.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Barcode status label no longer shows a previous run's count; log the counts for a repro"
```

---

### Task 5: Singular copy in the Results bulk menu (B1)

Spec §5 B1. `"Remove a SKU from these 1 order"` and `"Export just these 1 to Excel"` are ungrammatical at n=1.

**Files:**
- Modify: `gui/web/bulk.js:39-41` (add helper), `:125-146` (menu labels), `:324`, `:386-387`
- Test: `tests/test_results_bulk_popover.py`

**Interfaces:**
- Produces: `theseOrders(n)` → `"this order"` for 1, `"these 3 orders"` otherwise. Used by the labels below and nowhere else yet.

- [ ] **Step 1: Write the failing test**

`tests/test_results_bulk_popover.py` already drives this menu — read how it asserts on labels and follow that style.

```python
def test_bulk_menu_reads_naturally_for_one_order(results_page):
    labels = _more_menu_labels(results_page, selected=1)   # existing helper style
    assert "Remove a SKU from this order" in labels
    assert "Export this order to Excel" in labels
    assert "these 1" not in " ".join(labels)


def test_bulk_menu_still_pluralises_for_many(results_page):
    labels = _more_menu_labels(results_page, selected=3)
    assert "Remove a SKU from these 3 orders" in labels
    assert "Export these 3 orders to Excel" in labels
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_results_bulk_popover.py -k naturally -v`
Expected: FAIL — the menu still says `these 1 order`.

- [ ] **Step 3: Add the helper**

In `gui/web/bulk.js`, next to `countedWord`:

```javascript
function theseOrders(n) {
  return n === 1 ? "this order" : "these " + countedWord(n, "order");
}
```

- [ ] **Step 4: Use it in the labels**

```javascript
    { id: "more-remove-sku", label: "Remove a SKU from " + theseOrders(n), danger: true,
      run: () => openSkuPopover("line") },
```

and for the two exports, replacing `"Export just these " + NUMBER.format(n) + " to Excel"`:

```javascript
      label: "Export " + theseOrders(n) + " to Excel",
```
```javascript
      label: "Export " + theseOrders(n) + " to CSV",
```

At `:386`, replace `"Remove a SKU from these " + countedWord(n, "order")` with `"Remove a SKU from " + theseOrders(n)`.

Leave `"Add a tag to " + orders` and `"Copy " + countedWord(n, "order number")` alone — "Add a tag to 1 order" and "Copy 1 order number" are already correct.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_results_bulk_popover.py -v
python scripts/style_lint.py
git add gui/web/bulk.js tests/test_results_bulk_popover.py
git commit -m "Bulk menu reads 'this order' at one, not 'these 1 order'"
```

---

### Task 6: Column manager meta text clipped by the scrollbar (B2)

Spec §5 B2. `pinned` and `empty` are cut off at the right edge — `.columns-scroller` overlays its scrollbar on the row's last grid column.

**Files:**
- Modify: `gui/web/results.css:610`
- Test: `tests/test_results_pane.py` or the column-manager test module that already exists — find it with `grep -rl columns tests/`

- [ ] **Step 1: Apply the fix**

```css
.columns-scroller { flex: 1; min-height: 0; overflow-y: auto; scrollbar-gutter: stable; }
```

`scrollbar-gutter: stable` is the platform's own answer here — it reserves the track so the `auto` meta column is never underneath it. Do not hand-roll padding.

- [ ] **Step 2: Check the scrollbar is themed while you are here**

The same screenshot shows a light native scrollbar inside the dark popover. If `results.css` has no `::-webkit-scrollbar` rule for `.columns-scroller`, add one using existing tokens only:

```css
.columns-scroller::-webkit-scrollbar { width: 10px; }
.columns-scroller::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 5px;
}
.columns-scroller::-webkit-scrollbar-track { background: transparent; }
```

Confirm `--border` exists in this stylesheet before using it; if the token is named differently, use the existing name.

- [ ] **Step 3: Verify and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -k column -v
python scripts/style_lint.py
git add gui/web/results.css
git commit -m "Column manager: reserve the scrollbar gutter so pinned/empty stop clipping"
```

---

### Task 7: Tools tab — clipped count label and the empty Output folder row (B3)

Spec §5 B3. `"18 orders ready for barcode generation"` renders as `"18 orders ready for"`, and the Barcode labels card shows an `Output folder` label with nothing beside it.

**Files:**
- Modify: `gui/barcode_generator_widget.py:145` and the count label around :318
- Test: `tests/test_barcode_generator_widget.py`

- [ ] **Step 1: Read the card layout first**

Read `gui/barcode_generator_widget.py` around :120-160 to see what `section.add_row` does with its second argument and why `output_dir_label` renders empty. The label is only populated at :330 once a packing list is chosen — before that it is an empty string with a stranded caption.

- [ ] **Step 2: Write the failing test**

```python
def test_output_folder_row_is_never_blank(qtbot, barcode_widget):
    """The Output folder row must say something before a packing list is chosen."""
    assert barcode_widget.output_dir_label.text().strip() != ""


def test_order_count_label_is_not_elided(qtbot, barcode_widget):
    """The count sentence must fit the width it is given."""
    barcode_widget.order_count_label.setText("18 orders ready for barcode generation")
    hint = barcode_widget.order_count_label.sizeHint().width()
    assert barcode_widget.order_count_label.minimumWidth() >= hint or \
           barcode_widget.order_count_label.wordWrap()
```

- [ ] **Step 3: Give the empty row a placeholder**

```python
        self.output_dir_label.setText("Chosen when you pick a packing list")
```

Set this where `output_dir_label` is constructed, and let :330 overwrite it. Style it with `theme.text_secondary` — never a literal grey.

- [ ] **Step 4: Stop the count label eliding**

Turn on wrapping so the sentence survives a narrow card:

```python
        self.order_count_label.setWordWrap(True)
```

If the widget is a `gui/elided_label.py` `ElidedLabel` rather than a plain `QLabel`, swap it for a plain `QLabel` with `setWordWrap(True)` — eliding is wrong for a one-line status sentence.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Tools: the Output folder row says something, and the count sentence fits"
```

---

### Task 8: Logs — tell the source switch apart from the level filter (B8)

Spec §5 B8, and the subtask "Switching between tabs in logs can confuse info displayed on screen". `Activity | Execution` (which buffer) and `All | Info | Warning | Error` (minimum level) sit in one undifferentiated row of identical buttons, with no visible checked state in the Windows build.

**Files:**
- Modify: `gui/log_viewer.py` — `_build_control_row`
- Test: `tests/test_log_viewer.py`

- [ ] **Step 1: Read `_build_control_row` before changing anything**

Both groups are `QButtonGroup`s of `QPushButton`s. Find how `set_button_role` (from `shared.theme`) is applied and whether `setCheckable(True)` / `setChecked(...)` is set on them — a checkable button with no checked styling is the likeliest cause of "no visible selection".

- [ ] **Step 2: Write the failing test**

```python
def test_source_and_level_groups_are_separated(qtbot):
    viewer = LogViewer()
    qtbot.addWidget(viewer)

    names = [w.objectName() for w in viewer.findChildren(QWidget)]
    assert "logs-source-group" in names
    assert "logs-level-group" in names


def test_the_current_source_and_level_are_visibly_checked(qtbot):
    viewer = LogViewer()
    qtbot.addWidget(viewer)

    checked = [b.text() for b in viewer.findChildren(QPushButton) if b.isChecked()]
    assert "Activity" in checked          # a source is always active
    assert any(t in checked for t in ("All", "Info", "Warning", "Error"))
```

- [ ] **Step 3: Give the two groups separate containers and a divider**

Wrap each `QButtonGroup`'s buttons in its own `QWidget` with `setObjectName("logs-source-group")` / `"logs-level-group"`, and put a 1px `QFrame` divider between them:

```python
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedWidth(1)
        theme = get_theme_manager().get_current_theme()
        divider.setStyleSheet(f"background: {theme.border}; border: none;")
```

- [ ] **Step 4: Make the checked state visible**

Ensure every button in both groups is `setCheckable(True)`, the group is `setExclusive(True)`, and the current one starts checked. Re-apply on theme change through the existing `on_theme_changed` closure in this module (ADR 0003 — restyling is a closure, not a repolish; follow the pattern already in the file).

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_log_viewer.py tests/test_log_viewer_theme.py -v
python scripts/style_lint.py
git add gui/log_viewer.py tests/test_log_viewer.py
git commit -m "Logs: the source switch and the level filter are visibly different controls"
```

---

### Task 9: Browse — the Age column truncates (B6)

Spec §5 B6. `"24d · archiv…"` is cut off.

**Files:**
- Modify: `gui/session_browser_widget.py` around :263 (column definitions) and the header sizing
- Test: `tests/test_session_browser.py` — find the real module name with `ls tests/ | grep -i session`

- [ ] **Step 1: Write the failing test**

```python
def test_age_column_fits_an_archived_label(qtbot, session_browser):
    """'24d · archived' must fit without eliding."""
    header = session_browser.table.horizontalHeader()
    age_index = _column_index(session_browser, "Age")
    metrics = session_browser.table.fontMetrics()
    needed = metrics.horizontalAdvance("24d · archived") + 16
    assert header.sectionSize(age_index) >= needed
```

- [ ] **Step 2: Run it to verify it fails, then widen the column**

Set an explicit minimum width for the Age section rather than a fixed one, so the column still participates in resizing:

```python
        header.setSectionResizeMode(age_index, QHeaderView.ResizeToContents)
```

If the table already uses `ResizeToContents` and the text still elides, the elision is coming from the delegate, not the header — check `gui/status_edge_delegate.py` and the Age renderer noted at :574.

- [ ] **Step 3: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -k session_browser -v
git add gui/session_browser_widget.py tests/
git commit -m "Browse: the Age column fits '24d · archived'"
```

---

### Task 10: Client dropdown — themed scrollbar and separated actions (B7)

Spec §5 B7. The popup mixes clients with three actions (`Refresh clients`, `New client…`, `Manage groups…`) in one flat list, and shows a native light scrollbar inside a dark popup.

**Files:**
- Modify: `gui/ui_manager.py` (the client combo is built here — confirm with `grep -n "Manage groups" gui/ui_manager.py`)
- Test: `tests/test_ui_manager.py` or the nearest existing module

- [ ] **Step 1: Write the failing test**

```python
def test_client_menu_separates_actions_from_clients(qtbot, main_window):
    combo = main_window.ui.client_combo          # use the real attribute name
    model = combo.model()
    texts = [model.item(i).text() for i in range(model.rowCount())]
    sep_index = next(i for i, t in enumerate(texts) if t == "")   # separator row
    assert sep_index < texts.index("Refresh clients")
    assert all(t != "" for t in texts[:sep_index])
```

- [ ] **Step 2: Insert a separator before the action block**

Use `QComboBox.insertSeparator(index)` — the native Qt affordance — immediately before `Refresh clients`. Do not draw a fake divider row.

- [ ] **Step 3: Theme the popup's scrollbar**

The popup view needs the app's scrollbar QSS. Apply the existing stylesheet the rest of the app uses rather than writing a new one:

```python
        combo.view().setStyleSheet(get_theme_manager().get_current_theme_stylesheet())
```

Check what `shared/theme.py` actually exposes for this and use that name — do not invent `get_current_theme_stylesheet` if it does not exist.

- [ ] **Step 4: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -k client -v
python scripts/style_lint.py
git add gui/ui_manager.py tests/
git commit -m "Client menu: a separator before the actions, and a themed scrollbar"
```

---

### Task 11: Settings — the broken bits only (B4 partial, B5)

Spec §5 B4/B5 and §7 Q5. **Scope is strictly: the clipped "Search settings" placeholder, the column list cut mid-row, the native scrollbars, and the full-bleed spinbox.** Trailing colons, label styling and general field widths are explicitly out of scope — leave them.

**Files:**
- Modify: `gui/settings/window.py` (search field), `gui/settings/general.py` (the `Repeat Detection Window (days)` spinbox), `gui/settings/reports.py` or `report_editor.py` (the columns list)
- Test: `tests/test_settings_window.py` — find the real names with `ls tests/ | grep -i settings`

- [ ] **Step 1: Write the failing tests**

```python
def test_search_placeholder_is_not_clipped(qtbot, settings_window):
    field = settings_window.search_field
    metrics = field.fontMetrics()
    needed = metrics.horizontalAdvance(field.placeholderText()) + 24
    assert field.minimumWidth() >= needed


def test_repeat_window_spinbox_is_not_full_bleed(qtbot, settings_window):
    page = settings_window.page("general")
    assert page.repeat_window_spin.maximumWidth() <= 120
```

- [ ] **Step 2: Cap the spinbox width to match its neighbours**

The three fields above it are ~100px. Give the spinbox the same treatment:

```python
        self.repeat_window_spin.setMaximumWidth(100)
```

- [ ] **Step 3: Give the search field room for its placeholder**

```python
        self.search_field.setMinimumWidth(180)
```

- [ ] **Step 4: Stop the columns list clipping mid-row**

The scroll area in the Reports pane ends flush against the row below it. Add bottom padding inside the scroll area's viewport (not a margin on the scroll area) and confirm the last row renders whole. Use `var`-free Python styling with `theme` tokens.

- [ ] **Step 5: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -k settings -v
python scripts/style_lint.py
git add gui/settings/ tests/
git commit -m "Settings: unclip the search placeholder, the spinbox width and the column list"
```

---

### Task 12: Generate Reports dialog — consistent checkboxes (B9)

Spec §5 B9. The checkboxes differ from the column manager's, and the selected `All` row renders as an edit field.

**Files:**
- Modify: `gui/report_selection_dialog.py`
- Test: `tests/test_generate_reports_dialog.py`

- [ ] **Step 1: Find why the selected row looks editable**

Read `gui/report_selection_dialog.py` and check whether the list uses `QListWidget` with an item delegate that leaves an editor open, or whether `setEditTriggers` is unset. A `QListWidget` defaults to `DoubleClicked|EditKeyPressed`; the bordered box in the screenshot is a persistent editor or a focus rect styled like one.

- [ ] **Step 2: Write the failing test**

```python
def test_report_list_is_not_editable(qtbot, reports_dialog):
    assert reports_dialog.report_list.editTriggers() == QAbstractItemView.NoEditTriggers
```

- [ ] **Step 3: Disable editing and align the checkbox style**

```python
        self.report_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
```

For the checkbox appearance, apply the same QSS the rest of the Phase 9 dialogs use — find it in `shared/theme.py` and reuse it rather than writing new rules.

- [ ] **Step 4: Run the tests and commit**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_generate_reports_dialog.py -v
python scripts/style_lint.py
git add gui/report_selection_dialog.py tests/test_generate_reports_dialog.py
git commit -m "Generate Reports: the list is not editable and the checkboxes match Phase 9"
```

---

### Task 13: Gate and open the PR

- [ ] **Step 1: Full gate**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
ruff check . --exclude shared
python scripts/style_lint.py
```

Expected: at least 1749 passing (the `d070c2e` baseline) plus the new regression tests, ruff clean, style lint clean.

- [ ] **Step 2: Refresh the graph**

```bash
graphify update .
```

- [ ] **Step 3: Open the PR as a draft**

Body must state: the atomic-write fix and ADR 0008; that inventory memory now covers the whole stock file; that the barcode *generation* path was deliberately left alone pending a reproduction, with the new diagnostics named; and the list of UI defects fixed versus the Settings restyle explicitly deferred.

---

## Notes for the executor

- Tasks 1-4 are the ones that matter. If time runs short, land those and say so in the PR — do not half-finish a UI task to tick a box.
- Several UI tasks say "read the file first". That is deliberate: the exact widget construction was not verified during planning, and a confidently wrong edit is worse than a slower correct one. The tests in each task define the contract; if the code turns out to be shaped differently, keep the test's intent and adjust the implementation.
- Screenshots referenced as "shot N" are the 12 comments on Todoist task `6hWGF3XHC9Qww8j3`, in posting order. Read them with the Todoist MCP `view-attachment` tool — plain HTTP hits a login wall.
