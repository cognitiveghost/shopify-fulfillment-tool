# Phase 11 — Shopify tool bugfixes

**Todoist:** parent `6hX45X8qh5QQGxQV` (Roadmap — Shopify Tool). The briefs are
the five one-line items in the *General ideas* section, filed 2026-09-18 from a
Windows build of `main` after PR #327 merged (2026-09-15):

| Todoist | Report |
|---|---|
| `6hX455GcW8f2WX6V` | fix: add product button is not working |
| `6hX45788cx9qW8VV` | fix: package writeoff should have options to generate seperatly |
| `6hX4595fqrqR32w3` | fix: add filter opens under bulck frame |
| `6hX45CXmgXxM6MVV` | fix: add cancel file loading button (clear) |
| `6hX45JVjXgPHwrFV` | inv: inventory memory always asks about 100% change, math problem? invenory memory is not simulating on final stock numbers |

A sixth item, `6hQFR68mQ7pPgrr3` ("investigate barcode single generated label
bug"), is **out of scope** — see §6.

Classification: **bounded, but wide.** Five unrelated defects in flows that all
already exist in this repo. No new subsystem, no new module. Ordered
correctness-first so review can start at the top, one PR, per the #327
precedent.

No change under `shared/`, so no `packing-tool` sync is involved.

---

## 1. Add Product to Order is dead in a resumed session

**Report:** "add product button is not working". Confirmed with the owner
2026-09-20: a stock file *had* been loaded.

### Root cause

`gui/main_window_pyside.py:873` `load_existing_session` restores
`analysis_results_df` (via `_load_session_analysis`) and nothing else about the
run's inputs. `self.stock_file_path` and `self.orders_file_path` stay `None` —
line 87 sets them to `None` at construction and line 614 nulls them on a client
switch; **no code path ever assigns them outside the two file pickers.**

`update_ui_state` (:442) then computes `has_stock = bool(self.stock_file_path)`
= `False`, and :481 disables the action:

```python
self.add_product_button_tab2.setEnabled(has_analysis and has_stock)
```

So after opening yesterday's session — results on screen, orders listed — *Add
Product to Order* in the Results overflow is permanently greyed, with its
tooltip still reading "Manually add a product to an existing order". Nothing
says why. That is the whole of the report.

Behind it sits a second failure with the same shape: were the action reachable,
`gui/actions_handler.py:1140` would `return` on the same condition after a bare
`self.log.warning(...)`. The feature has **no failure path** — every guard
returns silently.

### The fix

The session already owns its inputs. `core.py:472` copies both files into
`<session>/input/` under fixed names and records them in `session_info.json`:

```python
orders_dest = Path(input_dir) / "orders_export.csv"
stock_dest  = Path(input_dir) / "inventory.csv"
session_manager.update_session_info(
    working_path, {"orders_file": "orders_export.csv", "stock_file": "inventory.csv"})
```

`load_existing_session` restores `orders_file_path` / `stock_file_path` from
those recorded names when the files are present on disk, and drives the two
file slots through the existing `validate_file` / `check_files_ready` path so
they show the session's real inputs instead of two empty drop zones.

Then make the remaining silent paths speak:

- The two bare `return`s in `show_add_product_dialog` (:1137, :1141) become
  `show_error(...)` with the repo's "Details are in Logs." body.
- `gui/add_product_dialog.py:155,165` index `analysis_df["Order_Number"]` and
  `stock_df["SKU"]` unguarded inside `__init__`, which runs **outside** the
  caller's `try`. A missing column there raises into the Qt event loop, where
  `shared/logger.py`'s hook logs it CRITICAL and the user sees nothing happen.
  Guard both and raise a named error the caller reports.

**Assumption, flagged for review:** restoring `orders_file_path` too re-enables
*Run Analysis* inside a resumed session. That is the coherent state — the
Setup screen showing two empty slots while Add Product works would be worse —
but it is a visible behaviour change, and restoring only the stock path is a
one-line retreat if the owner objects.

### Seam to test

`load_existing_session` against a session directory containing
`input/inventory.csv`: both paths restored, both slots loaded, and
`update_ui_state` leaves `add_product_button_tab2` enabled.
`tests/test_session_lifecycle.py` is the home; `tests/test_add_product_dialog.py`
covers the missing-column guard.

---

## 2. "Add filter" opens under the selection bar

**Report:** "add filter opens under bulck frame". The bulk frame is the
**selection bar** (CONTEXT.md, Results).

### Root cause

`gui/web/results.css` gives both popup surfaces the same layer:

- `.menu` (line 170) — the Add filter dropdown — `z-index: 3`
- `.selection-bar` (line 247) — `z-index: 3`, commented "over the sticky
  .header"

Neither `.menu-anchor` (`position: relative`, no z-index) nor `.table-area`
creates a stacking context, so both participate at the root and the tie is
broken by paint order. In `gui/web/results.html`, `#filterbar` is written
**before** `#table-area`, so the selection bar wins and covers the menu that
opened above it.

`.bulk-popover` (line 273) sits at the same 3 and has the same latent problem.

### The fix

A named layer scale in `results.css`, defined once as custom properties on
`:root` and used everywhere a `z-index` currently appears as a bare number:

| Layer | Value | Surfaces |
|---|---|---|
| `--z-sticky` | 1 | `.line.line-head`, `.col-group`, `.rows .row.selected::after` |
| `--z-header` | 2 | `.header` |
| `--z-bar` | 3 | `.selection-bar` |
| `--z-popover` | 5 | `.menu`, `.bulk-popover` |
| `--z-toast` | 6 | `.toast` |

Two popups can then never tie with a bar again, and the next person adding a
surface has somewhere to put it. Bumping `.menu` alone would fix the screenshot
and leave the trap.

### Seam to test

`tests/test_results_document.py` already asserts against `results.css`. Assert
the ordering relation — popover above bar above header — not the literal
numbers.

---

## 3. Inventory memory raises a false alarm on every stock load

**Report:** "inventory memory always asks about 100% change, math problem?"

The owner's "math problem?" is correct. `gui/file_handler.py:288`
`_check_inventory_anomaly` holds **two** independent comparison bugs.

### 3a. Two totals counted differently

`profile_manager.py:709` stores memory's total as a **per-SKU** sum with
negatives dropped, over a snapshot that `core.build_inventory_snapshot` already
deduplicated with `groupby("SKU")["Stock"].last()`:

```python
"total_units": int(sum(v for v in stock_dict.values() if v > 0)),
```

The freshly-loaded file is measured as a **raw row sum**, duplicates and
negatives included:

```python
new_total = new_stock_df["Stock"].sum()
```

A stock file with two rows per SKU — which `build_inventory_snapshot`'s
`groupby(...).last()` exists precisely to handle — makes `new_total` twice
`old_total`, which prints as **"Total units changed by +100%"** on every single
load. Negative stock values skew it the other way.

**Fix:** measure the new file the way memory measures itself — group by SKU,
take `.last()`, clamp at zero, then sum. One helper, used by both sides, so
they cannot drift again.

### 3b. SKUs compared in two different alphabets

`profile_manager.py:706` normalises the keys it stores:

```python
"skus": {normalize_sku(k): float(v) for k, v in stock_dict.items()},
```

The overlap check does not normalise the other side:

```python
new_skus = set(new_stock_df["SKU"].unique())
```

`shopify_tool/csv_utils.normalize_sku` exists because pandas reads numeric SKUs
as float64 — `5170.0` against a stored `"5170"`. The intersection is empty, the
ratio is 0.0, and every load for a client with numeric SKUs gets
**"Only 0% SKU overlap with saved inventory … Wrong client file?"**.

This check runs *first* and returns early, so on such a client it masks 3a
entirely.

**Fix:** apply `normalize_sku` to the new file's SKUs before the comparison.

### Not a bug

"inventory memory is not simulating on final stock numbers" is the same
observation from the other end: the numbers the dialog quotes look wrong, so
the snapshot looks wrong. The snapshot is correct — `run_full_analysis:1392`
passes the stock frame through `analysis.stock_with_internal_columns` before
`build_inventory_snapshot` sees it, and #327's "every SKU in the stock file"
decision is implemented as CONTEXT.md describes it. Nothing to change here; it
is recorded so nobody goes looking.

### Seam to test

`_check_inventory_anomaly` has **no test at all** today. Add one in
`tests/test_file_handler.py` covering: duplicate SKU rows raise no alarm;
float64 SKUs against normalised memory raise no alarm; a genuine 50% drop still
does.

---

## 4. A loaded file slot cannot be emptied

**Report:** "add cancel file loading button (clear)". Confirmed with the owner
2026-09-20: this means clearing a chosen file, not interrupting a load in
flight. File loading is fully synchronous today; making it interruptible is a
separate, much larger change and is **out of scope**.

### Root cause

`gui/components/file_slot.py:150` already has a working `clear()`. No button
reaches it. The loaded state (:89) offers only "Choose a different file"; the
invalid state (:105) offers "Map columns…" and "Choose a different file". A
wrong file can be replaced but never removed, so a slot cannot be returned to
empty without switching clients.

### The fix

Follow the pattern the component already uses — a signal out, the handler
owns the state:

1. `FileSlot` gains `clearRequested = Signal()` and a **Clear** button on both
   the loaded and the invalid rows, beside the existing buttons.
2. `main_window_pyside.py:326`'s per-slot wiring loop gains
   `slot.clearRequested.connect(lambda k=kind: self.file_handler.clear_file(k))`.
3. `FileHandler.clear_file(kind)` nulls `mw.<kind>_file_path` and calls
   `slot.clear()` — exactly what `file_handler.py:275` already does inline for
   the anomaly-cancel path, which should then call it instead of duplicating it.

`clear()` emits `changed`, which is already connected to `check_files_ready`
(:344), so Run Analysis re-gates itself with no extra wiring.

### Seam to test

`tests/test_file_slot.py` for the button and the signal;
`tests/test_file_handler.py` for `clear_file` nulling the path and re-gating.

---

## 5. Packaging write-off as its own file

**Report:** "package writeoff should have options to generate seperatly".
Owner's decision 2026-09-20: **its own `.xls` file**, with the combined mode
kept.

### Today

`shopify_tool/stock_export.py:247` appends packaging rows into the product
export:

```python
export_df = pd.concat([export_df, packaging_rows], ignore_index=True)
```

One file, products and packaging interleaved, driven by a single boolean —
`gui/report_selection_dialog.py:272`'s "Include Packaging Materials in export
(SKU Writeoff)" checkbox, which sets `entry["apply_writeoff"]` for every
selected stock export.

### The fix

The boolean becomes a three-state choice, because "off / together / apart" is
one question with three answers, not two booleans:

- `create_stock_export` takes `writeoff_mode: "off" | "merged" | "separate"`
  in place of `apply_writeoff: bool`.
- `"separate"` writes the packaging rows to a sibling of `output_file` with
  `_packaging` before the extension, through the same `_finalize_export_df` and
  the same `xlwt` writer, and returns both paths so the caller can report them.
  No packaging rows means no second file and a log line saying so.
- `gui/report_selection_dialog.py` replaces the checkbox with the three
  options inside the existing "Writeoff Report" group box, and emits
  `entry["writeoff_mode"]`.
- `gui/actions_handler.py:770` and `shopify_tool/core.py:1591` read the new
  key. `apply_writeoff` is not persisted anywhere — it is computed per
  generation from the dialog — so it is **replaced, not deprecated**. One
  concept, one name.

A separate `.xls` rather than a second sheet: the export exists to be
swallowed by a warehouse system that reads one sheet of one file, and a second
sheet is the kind of thing an importer skips in silence.

### Seam to test

`tests/test_stock_export.py` already covers the merged path at :243–:295.
Extend it: `"separate"` writes two files with the packaging SKUs only in the
second; `"separate"` with no writeoff mappings writes one file; `"off"` is
unchanged.

---

## 6. Out of scope: the "only 1 barcode" report

Todoist `6hQFR68mQ7pPgrr3`. Deferred again, with the owner's agreement
2026-09-20, for the reason #327 §4 gave: **there is no cause in the code.**

Re-traced end to end this cycle —
`_on_packing_list_changed` (`gui/barcode_generator_widget.py:311`) filters the
analysis frame to the packing list's fulfillable orders;
`_generate_barcodes_worker` (:396) collapses it with
`groupby("Order_Number").first()`; `generate_barcodes_batch`
(`shopify_tool/barcode_processor.py:163`) appends one record per row;
`generate_code128_labels_pdf` (:232) renders them with `items_per_page=1`.
Every step is per-order. The only unexamined link is `blabel`'s `LabelWriter`
under Windows, and changing it on a hypothesis risks breaking a path that
works.

#327 shipped the instrumentation this needs. The next Windows run that
reproduces it should carry three numbers in the log, and they isolate it
immediately:

```
Barcode generation complete for packing list '…': N orders filtered, N labels written, N failed
Generated PDF: …_barcodes.pdf (N pages)
```

- filtered = 1 → the packing list or the fulfillable filter
- filtered = 18, written = 1 → `generate_barcodes_batch`
- written = 18, pages = 1 → `blabel` / the label template

The item stays in *General ideas* until those lines exist.

---

## 7. Scope

**In:** §1 session input restore + Add Product failure paths; §2 the layer
scale; §3a and §3b the two anomaly comparisons; §4 the slot Clear button;
§5 write-off as its own file.

**Out:** interrupting a load in flight (§4); any change to the barcode
generation path (§6); any change under `shared/`; the Settings form restyle
still carried over from #327 §8.

**Vocabulary:** CONTEXT.md gains **packaging write-off** — the packaging
material SKUs a run consumes, derived from internal tags, written either into
the stock export or beside it. "SKU writeoff", the current name in the tag
config and the dialog, names the config key rather than the thing.

Plan: `docs/superpowers/plans/2026-09-20-phase11-shopify-bugfixes-plan.md`.
