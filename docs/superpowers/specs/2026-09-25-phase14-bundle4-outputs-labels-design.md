# Phase 14 Bundle 4: outputs and labels (design)

**Roadmap:** Phase 14 Audit fixes → Bundle 4 (Todoist `6hcgpvGr5MXC4fvV`).
**Source:** `docs/audit/04-outputs.md` and its proof tests in
`tests/audit/test_04_outputs.py`. Each finding's approved plan is on its
Todoist subtask. This spec records only what those plans left open, what
the owner decided on 2026-09-25, and one addition (timestamped stock-export
filenames).
**Classification:** bounded fixes to existing flows. No UI mockup: the only UI
changes are message text and one inline warning.

## Owner decisions (2026-09-25, this stage)

| # | Question | Decision |
|---|---|---|
| D1 | AUDIT-04-3: a regenerated packing list matches no orders | **Delete** the list's old XLSX and JSON. Don't write empty files |
| D2 | AUDIT-04-5: order numbers that would share a barcode value | **Refuse** the colliding orders (and any non-ASCII order number). Shopify-side only, with no Packing Tool change |
| D3 | AUDIT-04-12: stale barcode PDFs | **Delete** the list's `_barcodes.pdf` and `_qr_labels.pdf` when that list is regenerated |
| D4 | Timestamps in filenames | **Stock exports now**: `<stem>_YYYY-MM-DD_HHMM.xls`. Packing-list filenames are a separate later item, because Packing Tool keys lists by filename stem |
| D5 | Previous versions of a timestamped stock export | **Move them to `stock_exports/old/`** |

Earlier owner decisions (audit §5, still binding): label #N is the N-th order
on its packing list, and `Order_Min_Box` keeps its behaviour while its
docstrings are corrected.

## Facts that shaped the decisions

- Packing Tool reads `orders: []` without error. A missing JSON just leaves
  the list out of its list picker (`packer_logic.load_packing_list_json`).
- Packing Tool's scan lookup strips `#`, spaces, `/` and every other
  non-`[alnum-_]` character from both the scan and its order numbers
  (`packer_logic._normalize_order_number`), and keeps the last entry on a
  collision. Encoding the order number unchanged would therefore not stop a
  mis-scan. That is why D2 refuses collisions instead (the approved plan's step 3 check
  failed).
- Packing Tool keys the work folder, session metadata and resume on the
  packing list's filename stem. A timestamp in that name would make every
  regeneration a new list, which is why D4 covers exports only.
- Packing Tool never reads `session/barcodes/<list>/*.pdf`. The barcode tab
  prints only the PDF it generated in the current run.
- Production stock-export configs use fixed names (`ALL_ORDERS_ALMADERM.xls`).
  Without a configured name, the default is `<name>_YYYY-MM-DD.xls`.

## Design, by group

### Group 1: packing list, stock export, barcodes

**AUDIT-04-4, shared SKU exclusion.** Add `report_filters.exclude_skus(df, skus)`.
It accepts a list or a comma-separated string, strips the values, drops
blanks, and compares through `csv_utils.normalize_sku_for_matching`, as the
XLSX does today. `create_packing_list` and the JSON step in
`ActionsHandler._generate_single_report` both call it, and the two inline
copies and the handler's string parsing go away.

**AUDIT-04-3 (D1), empty packing list.** `create_packing_list` returns a
value that says whether it wrote anything: the number of orders written, 0
when empty. On 0, `_generate_single_report` deletes `<list>.xlsx` and
`<list>.json` (`unlink(missing_ok=True)`) and skips the JSON step. The status
bar then says `No orders matched <name>; its old files were removed` instead
of "Report saved". The session statistics step still runs, so
`packing_lists_count` drops the removed list.

**AUDIT-04-12 (D3), stale barcode PDFs.** Every packing-list generation,
empty or not, deletes `session/barcodes/<list stem>/<stem>_barcodes.pdf` and
`<stem>_qr_labels.pdf`. The helper is `invalidate_label_pdfs(session_path,
list_stem)` in `shopify_tool/barcode_processor.py`, the module that owns
those filenames, and the widget's four f-strings move onto the same two name
helpers. `_generate_single_report` calls it for packing lists.

**Label order (owner decision 1).** Move the packing list's row order into
`packing_lists.sort_for_packing_list(df)`: courier priority (DHL 0,
PostOne 1, DPD 2, other 3), then `order_number_sort_key`, then SKU. The
function returns the sorted frame without the helper columns.
`create_packing_list` and `BarcodeGeneratorWidget._generate_barcodes_worker`
both call it. The worker sorts its one-row-per-order frame, so SKU is
irrelevant there.

**AUDIT-04-1, labels.**
1. `requirements.txt`: `weasyprint>=70`, on its own line near `blabel`.
2. `generate_barcodes_batch`: `tag = format_tags_for_barcode(tag) or "N/A"`.
3. Both `generate_*_labels_pdf` count the pages of `pdf_bytes`
   (`pypdf.PdfReader(BytesIO(...))`) **before writing the file**, and raise
   `BarcodeGenerationError` naming both counts when the page count differs
   from `len(records)`. No partial PDF is written.
4. The conditional xfail on the two page-count tests goes: with the pin they
   pass everywhere.
5. Ops, outside the code: confirm every warehouse PC runs 1.9.10.3 or later.
   This goes in the PR description.

**AUDIT-04-5 (D2), barcode collisions.** `sanitize_order_number` keeps today's
character set but accepts only ASCII (`c.isascii() and (c.isalnum() or c in
"-_#")`), and raises `InvalidOrderNumberError` if the order number contains
any non-ASCII character. After building records, `generate_barcodes_batch`
groups the successful records by `safe_order_number`. Every record in a group
of 2 or more becomes `success=False` with the error `Barcode value <v> would
also scan as order(s) <others>`. The "verified correct" test
(`test_barcode_value_is_the_order_number_unchanged`) must keep passing. The
existing failure path in `_on_generation_complete` already reports failed
counts.

**AUDIT-04-2, stock export failure.** `create_stock_export` re-raises after
logging instead of returning None. `_write_xls` saves the workbook to a
`BytesIO` and writes it atomically: a temp file in the same directory, then
`os.replace`, with the temp file removed on failure. This is local to
`stock_export.py`: `shared/atomic_write` is JSON-only and not owned here, and
a second caller doesn't exist yet. `_generate_single_report` catches
`PermissionError` separately and shows `show_error(mw, "<name> wasn't
generated", "<file> is open in another program. Close it, then generate
again.")`. The generic handler stays for everything else.
`core.create_stock_export_report` already returns `(False, msg)` on exceptions.

**Timestamped stock-export filenames (D4, D5).** New function
`stock_export.prepare_export_path(base_path, now=None) -> str`:
- Takes the configured path (`<dir>/<stem>.xls`), strips a trailing
  `_YYYY-MM-DD` from the stem if present, and returns
  `<dir>/<stem>_YYYY-MM-DD_HHMM.xls` in local time.
- **Before returning**, it moves every earlier version of that report in
  `<dir>` into `<dir>/old/` (created on demand), with `os.replace` so a
  same-named file in `old/` is overwritten. "Earlier version" means a
  filename matching
  `^<re.escape(stem)>(_\d{4}-\d{2}-\d{2}(_\d{4})?)?(_packaging)?\.xls$`.
  That covers the legacy bare name, the legacy date-only name, earlier stamps
  and their packaging siblings, and not a different report whose name only
  starts with the same stem.
- A move that fails raises. The caller's `PermissionError` path then tells the
  operator to close the file, and nothing new is written, so the folder never
  holds two current exports. Moving before writing means a failed write leaves
  the main folder with no export of that report, which is safe: nothing stale
  is there to import.

Callers: `_generate_single_report`, whose default name drops its own
datestamp and becomes `<name>.xls`, and `core.create_stock_export_report`,
which appends the stamped basename to `stock_exports_generated`. The status
bar already shows the stamped name. Packing lists keep their names.

**Order_Min_Box docs (owner decision 2).** Correct the `UNKNOWN_DIMS`
comment, the `find_min_box_for_order` docstring and the
`enrich_dataframe_with_weights` docstring, plus the module docstring. They should say that items
without dimensions are ignored, the box is picked from the items that have
them, and `UNKNOWN_DIMS` means *no* item has dimensions, or there are no
products. A test pins this: one sized item plus one unsized item gives the
sized item's box.

**AUDIT-04-10, columns with lot tracking.** With lot tracking, a configured
`columns` list applies as it does without it (same availability filtering),
with `Lot_Expiry` and `Lot_Batch` inserted right after `Quantity` when
`Quantity` is printed, else appended, unless the configuration already lists
them. Without configured columns, the lot layout stays as it is.

### Group 2: reference labels (`pdf_processor`)

**AUDIT-04-7, name fallback.**
- `load_csv_mapping`: `by_name` maps a normalized name to a **list** of
  distinct refs. The mapping also gains `refs`, the set of every non-empty REF
  in the CSV, which AUDIT-04-8 needs.
- `match_reference` step 3: a candidate is a name with `len > 5` that occurs
  in the normalized page text on word boundaries
  (`(?<!\w)name(?!\w)`, `re.escape`d). Drop any candidate contained in a
  longer candidate. The page matches only if exactly one candidate remains
  and it maps to exactly one ref. Otherwise the result is `None`, and the
  page is unmatched.
- A name match returns `verified: False`, since the name is its only
  evidence. PostOne and tracking matches are unchanged.

**AUDIT-04-9, failed stamp.** Count `matched` from pages actually stamped. A
page whose stamp failed is appended unstamped, counted in `unmatched`, and
its REF is treated as not placed.

**AUDIT-04-8, missing and duplicated REFs.** The result dict gains:
- `duplicate_refs`: REFs stamped on 2 or more pages;
- `missing_refs`: `mapping["refs"]` minus the REFs stamped;
- `name_matched`: the number of pages stamped via the name fallback.

Both lists are sorted with the AUDIT-04-11 key. In
`ReferenceLabelsWidget._on_processing_complete`, when either list is
non-empty, there is no success toast. The status label (inline message
route) is drawn in `theme.status_warning` and reads:

`Check before printing: REF 100 is on more than one page; no page for REF 200, 300.`

Each clause appears only when it applies, and each list is capped at 5 REFs
plus `(+N more)`. Otherwise the toast stays as today, with
`, <n> matched by name only` appended when `name_matched > 0`. Auto-open and
the signal are unchanged.

**AUDIT-04-11, REF sort.** Numeric-shaped REFs (`^#?\d+$`) sort by their
integer value first. Every other REF sorts after them, alphabetically. Ties
keep `original_order`. Unmatched pages stay last.

## Testing seams

- The audit proof tests are the acceptance tests. Stage B removes each xfail
  marker with its fix, and every one must then pass under `strict=True`.
- New tests: `sort_for_packing_list` (a mixed-courier frame gives label
  sequence == packing-list order); `invalidate_label_pdfs`;
  `prepare_export_path` (the name shape, what it moves, the prefix-name
  safety case, and that a failed move raises); `exclude_skus` string parsing;
  the Min_Box behaviour pin; and the reference-widget warning text through a
  pure formatter function (`reference_run_warning(result) -> str | None`), so
  it's tested without Qt.
- Existing suites to re-run: `tests/test_stock_export.py`, `tests/test_core.py`
  (stock-export filename assertions), `tests/test_barcode_processor.py`,
  `tests/test_weight_calculator.py`, `tests/test_generate_reports_dialog.py`.

## Out of scope

- Timestamped packing-list filenames, and the matching Packing Tool change,
  go to a new backlog item.
- Printing aspect ratio and partial print jobs (audit §5, not covered).
- A label's SUM counting excluded SKUs (audit §5; no client excludes SKUs).
- AUDIT-04-6 shipped in Bundle 1.
