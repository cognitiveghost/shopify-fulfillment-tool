# Audit 04: outputs

Scope: everything that leaves the app as a file or on paper.

- Packing lists: `shopify_tool/packing_lists.py`, plus the XLSX + JSON path in
  `gui/actions_handler.py:_generate_single_report` and `core.build_packing_order_data`.
- Stock exports: `shopify_tool/stock_export.py`.
- The shared filter: `shopify_tool/report_filters.py`.
- Reference labels: `shopify_tool/pdf_processor.py` and `gui/reference_labels_widget.py`.
- Barcode and QR labels: `shopify_tool/barcode_processor.py`, `label_tools.py`,
  `templates/`, and `gui/barcode_generator_widget.py`.
- Printing: `label_printing.py` and `gui/pdf_printing.py`.
- `weight_calculator.py`, which produces the JSON's `order_min_box`.

`barcode_history.py` and `sequential_order.py` were read. The app never
imports either: barcodes encode the order number directly, and label numbers
restart at 1 for each generation.

Proof tests are in `tests/audit/test_04_outputs.py`. The audit ran against
`origin/main` at `4b7c065`.

## 1. Verdict

**Packing lists and stock exports: yes for today's configs. Barcode labels:
yes on the current release, not on 1.9.9.5–1.9.10.2. Reference labels: only
when every page matches by PostOne ID or tracking number.**

For the lists and exports, every file in production matches its session's
analysis:

- all 35 packing lists (XLSX and JSON agree in every one);
- 34 of 36 stock exports. The other two are explained in section 3.

Those paths fail only in edge cases today's configs don't reach: an empty
list, an export file that is locked, `exclude_skus`, and orders whose lines
disagree on status.

Barcode labels had a serious gap that the current release no longer shows.
**Under WeasyPrint 69.0, an order with no internal tag ends the label PDF.**
Every label after it is missing, while the toast still reports all of them
as generated (AUDIT-04-1). Release builds 1.9.9.5 to 1.9.10.2 (10–31 August)
bundled 69.0. Builds from 1.9.10.3 onward, including the current 1.9.10.8,
bundle 70.0, which keeps every page. With 69.0, replaying the renderer over
the saved production tags, 8 of 39 sessions would lose 144 of the 185 labels
in those sessions, including 5 of 6 WATERDROP sessions.

The app's own share of the defect is still there. It hands the template an
empty tag instead of "N/A". It never checks the PDF's page count against the
labels. And it does not pin WeasyPrint, so the next build takes whatever
version is newest.

Reference labels fall back to matching a page by customer name. That fallback
is a substring match, and the first CSV row wins, so a page can get another
customer's REF. The result also reports only page counts: a REF stamped on
two pages, or a REF with no page at all, goes unmentioned (AUDIT-04-7, -8).

Every warehouse PC should be on 1.9.10.3 or later. Pin WeasyPrint to 70.0
or newer, and add the page-count check (AUDIT-04-1).

**What "correct" means here.** The definitions come from `CONTEXT.md`
(fulfillable order, label count, reference strip), the `report_filters`
docstrings (one filter serves every output), and the invariant every audit
uses: an order ships whole or not at all, and stock is never promised twice.
Every output must carry exactly the analysis's fulfillable lines, and every
label must encode exactly its own order or REF.

Two business rules were decided by the owner during the audit (section 5);
no finding depends on them. Repeat orders reaching the outputs unmarked is
already AUDIT-02-8, so it is not repeated here.

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-04-1 | high (critical on 1.9.9.5–1.9.10.2) | Under WeasyPrint 69.0, label PDFs lose every label after the first untagged order. The app sends an empty tag, never checks the page count, and doesn't pin WeasyPrint | `barcode_processor.py:114`, `:232`, `requirements.txt:52` | `test_orders_without_internal_tags_are_labelled_na`, `test_label_pdf_with_missing_pages_is_an_error`, `test_requirements_pin_a_weasyprint_that_keeps_every_label`; on 69.x also `test_barcode_pdf_has_a_page_for_every_label`, `test_qr_pdf_has_a_page_for_every_label` | confirmed |
| AUDIT-04-2 | critical | A stock export that fails to write is reported as saved, and the old file stays | `stock_export.py:334` | `test_stock_export_write_failure_is_not_silent` | confirmed |
| AUDIT-04-3 | critical (latent) | A packing list that matches no orders leaves the previous XLSX and JSON in place under "Report saved" | `packing_lists.py:140`, `gui/actions_handler.py:765` | `test_regenerating_an_empty_packing_list_replaces_the_old_files` | confirmed |
| AUDIT-04-4 | high (latent) | `exclude_skus` matches loosely in the XLSX and exactly in the JSON, so Packing Tool gets lines the picking list left out | `gui/actions_handler.py:751` vs `packing_lists.py:127` | `test_packing_list_json_excludes_the_same_skus_as_the_xlsx` | confirmed |
| AUDIT-04-5 | high (latent) | Two different order numbers can encode to the same barcode value | `barcode_processor.py:66` | `test_distinct_orders_never_share_a_barcode_value` | confirmed |
| AUDIT-04-6 | critical | Outputs include an order's fulfillable lines even when another of its SKU lines is blocked | `report_filters.py:78` | `test_packing_list_never_lists_part_of_an_order`, `test_stock_export_never_writes_off_part_of_an_order` | confirmed |
| AUDIT-04-7 | critical | Name-fallback matching is a substring match with the first CSV row winning; a shared name takes the last row's REF | `pdf_processor.py:443`, `:358` | `test_name_fallback_picks_the_exact_customer`, `test_name_fallback_refuses_an_ambiguous_name` | confirmed |
| AUDIT-04-8 | high | A reference-label run doesn't report a REF on two pages or a REF with no page | `pdf_processor.py:213` | `test_reference_run_reports_a_reference_on_two_pages`, `test_reference_run_reports_a_reference_without_a_page` | confirmed |
| AUDIT-04-9 | low | A page whose stamp failed is left unstamped but counted as matched | `pdf_processor.py:190` | `test_unstamped_page_is_not_counted_as_matched` | confirmed |
| AUDIT-04-10 | low | A packing list's configured columns are ignored when lot tracking is on | `packing_lists.py:176` | `test_configured_columns_apply_with_lot_tracking` | confirmed |
| AUDIT-04-11 | low | Tracking-shaped REFs are sorted by a digit run inside them | `pdf_processor.py:547` | `test_tracking_shaped_reference_sorts_after_numeric_references` | confirmed |
| AUDIT-04-12 | high | Barcode PDFs generated before a re-run stay beside the new packing list, with nothing marking them stale | `gui/barcode_generator_widget.py:311` | none (GUI workflow) | unproven |

"Latent" means no production client triggers it today:

- Every `exclude_skus` list is empty.
- No production order number contains a character the sanitizer strips.
- No saved list ever came out empty.

## 3. Findings in detail

### AUDIT-04-1 — Untagged orders and WeasyPrint 69.0 lose labels (high; critical on 1.9.9.5–1.9.10.2)

**What goes wrong.** For an order with no internal tags, the barcode tab
merges the tags to `"[]"`, and `format_tags_for_barcode` turns that into an
empty string (`barcode_processor.py:114`). The template renders it as an
empty `<span class="field-value">`. Under **WeasyPrint 69.0**, from that
label on, no more pages go into the document:

- Tags `A, "", A, A` give 2 pages, not 4.
- Tags `"", A, A` give 1 page.
- A tag that is only a space behaves the same. `"-"` does not.

The QR template has the same line and loses labels the same way. The toast
reports `len(successful)` records, not pages, so the operator is told every
label was generated. **WeasyPrint 70.0 keeps every page.** The same inputs
give 4, 6 and 3 pages.

**Which builds are affected.** WeasyPrint arrives through `blabel` and is
not pinned (`requirements.txt:52`), so each build takes the newest release.
The release build logs show:

| release builds | WeasyPrint | loses labels |
|---|---|---|
| 1.9.9.5 to 1.9.10.2 (10–31 August; the label templates landed in 1.9.9.5) | 69.0 | yes |
| 1.9.10.3 to 1.9.10.8 (14 September onward) | 70.0 | no |

CI also installs 70.0. A developer venv created earlier may still hold 69.0.
The page-count tests are therefore expected to fail only there.

**Scenario, on 1.9.10.2.** A packing list holds #1 (tag BOX), #2 (no tags)
and #3 (tag BOX). The barcode PDF has two pages, #1 and #2. #3 has no label,
and the screen says 3 were generated.

**Root cause.** Three defects in the app let a renderer bug through
silently:

1. **An empty tag.** A no-tag order reaches the template as `""`, not the
   `"N/A"` that `generate_barcodes_batch` intends. Its `if tag else "N/A"`
   check tests the raw `"[]"`, which is truthy, instead of the formatted
   value.
2. **No page check.** `generate_code128_labels_pdf` and
   `generate_qr_labels_pdf` never compare the page count with the number of
   records.
3. **No version pin.** Nothing stops a build from shipping 69.0.

The mechanism inside WeasyPrint 69.0 was not traced.

**Production evidence.** The saved PDFs use the old label layout and predate
this template, so they cannot show the loss. With WeasyPrint 69.0, replaying
the renderer (tag merge, natural sort, first empty tag) over each session's
saved fulfillable orders:

| client | sessions affected | labels lost / labels in those sessions |
|---|---|---|
| ALMADERM | 2 of 25 | 107 / 128 |
| HERBAR | 1 of 8 | 5 / 7 |
| WATERDROP | 5 of 6 | 32 / 50 |

Across the three clients, 14 of 823 fulfillable orders have no internal tag.
Any warehouse PC still running 1.9.9.5–1.9.10.2 loses labels at those rates.

### AUDIT-04-2 — Stock export failure reads as success (critical)

**What goes wrong.** `create_stock_export` catches every exception, logs it
and returns `None` (`stock_export.py:334`). `None` is also what a successful
export without a separate packaging file returns. The callers therefore
cannot tell the two apart:

- The Reports tab shows "Report saved: …xls".
- `core.create_stock_export_report` checks that the file exists, and a file
  from an earlier run passes that check.

**Scenario.** The operator exports, imports the file into the ERP, holds
three orders, and exports again while the ERP still has the file open. On
Windows the write fails with a permission error, and the screen says "Report
saved". The file on disk still writes off the three held orders. Importing
it miscounts stock.

**Root cause.** A write failure is swallowed in the module rather than
raised to the caller.

**Production evidence.** None in the files. The ERP holding the file open is
an operational condition the sessions don't record.

### AUDIT-04-3 — An empty list leaves the old one in place (critical, latent)

**What goes wrong.** When filters, statuses or `exclude_skus` leave no rows:

- `create_packing_list` returns without writing (`packing_lists.py:140`).
- The JSON step logs "Skipping JSON creation" (`gui/actions_handler.py:765`).

Both files from the previous generation stay. The status bar still says
"Report saved". Packing Tool loads the old JSON, which lists orders that are
now held.

**Scenario.** A list of two orders is generated, then both are held (a
stock problem, or a repeat caught late), and the list is generated again.
`ALL.json` still lists both orders, and the Packer can pack them.

**Root cause.** "No rows" is handled as "do nothing" rather than "write an
empty list" or "remove the file".

**Production evidence.** No saved list is empty, so this is latent.

### AUDIT-04-4 — XLSX and JSON exclude different SKUs (high, latent)

**What goes wrong.** The XLSX compares SKUs through
`normalize_sku_for_matching`, so `"07"` excludes `"7"` and `"7.0"`. The JSON
for Packing Tool compares raw strings with `isin` (`actions_handler.py:751`).
Neither strips spaces from a value stored as a list.

**Scenario.** `exclude_skus: ["07"]` and an order line `7`. The picking list
leaves the item out, while Packing Tool expects it to be packed.

**Root cause.** The two outputs use two copies of the exclusion logic, the
same way the filters used to (see the `report_filters` module docstring).

**Production evidence.** Every client's `exclude_skus` is empty.

### AUDIT-04-5 — Barcode value collisions (high, latent)

**What goes wrong.** `sanitize_order_number` drops every character that is
not a letter, digit, `-`, `_` or `#` (`barcode_processor.py:66`). As a
result:

- `#1001/2`, `#1001 2` and `#10012` all encode as `#10012`.
- A scan resolves to another order, or to none.
- `isalnum()` accepts non-ASCII letters, which Code-128 cannot encode, so
  one such order number fails the whole PDF render.

**Root cause.** Characters that can't be encoded are removed silently
instead of the order being refused.

**Production evidence.** None of the order numbers across the 39 sessions
contains a character that is stripped.

### AUDIT-04-6 — Part of an order ships (critical)

**What goes wrong.** Every output selects **lines** with
`Order_Fulfillment_Status == "Fulfillable"` (`report_filters.py:78`). When
an order's lines disagree, its fulfillable lines are:

- listed on the packing list;
- written off in the stock export;
- sent to Packing Tool.

Its blocked SKU lines silently drop out. A no-SKU line (a fee or custom item)
is expected to drop out. A blocked SKU line is not.

**Scenario.** Order #1 has A (fulfillable) and GIFT (out of stock, blocked).
The packing list shows #1 with only A, the stock export writes off A, and #1
ships without its gift.

**Root cause.** Status is stored per line, and the outputs trust the line
rather than the order. Lines come to disagree upstream through edits
(AUDIT-01-2, -3, -5) or an order-level `SET_STATUS` (AUDIT-03-1). The
outputs have no guard of their own.

**Production evidence.** Three sessions have orders whose lines disagree.
Two ALMADERM sessions (07-01_2 and 07-02_3) have 20 orders, all edited after
the run, where a blocked gift line sits beside fulfillable lines. A list
generated from their saved state would ship those 20 orders without the
gift. HERBAR 07-16_2's 2 mixed orders are no-SKU lines, the expected case.

### AUDIT-04-7 — Name fallback can stamp another customer's REF (critical)

**What goes wrong.** When a page has no known PostOne ID or tracking number,
`match_reference` takes the **first** CSV name that appears anywhere in the
page text (`pdf_processor.py:443`). Two consequences:

- "Ivan Petrov" (earlier in the CSV) matches the page for "Ivan Petrova".
- Two customers with the same name share one `by_name` entry, and the later
  row overwrites the earlier one (`:358`). Both pages get the same REF.

Either match is reported with `verified: True`.

**Scenario.** The page for Ivan Petrova is stamped with Ivan Petrov's REF.
Her label goes on his parcel.

**Root cause.** Substring containment is used as identity, and ambiguous
names are not detected.

**Production evidence.** HERBAR 2026-07-22_1 has one REF stamped on two
pages. The two pages carry different tracking numbers, and only one has a
PostOne ID. The input CSV was not kept, so it cannot be shown whether this
was one customer's two parcels or a name-fallback mismatch. This instance is
**unproven**.

### AUDIT-04-8 — Missing and duplicated REFs are not reported (high)

**What goes wrong.** The run returns only `matched` and `unmatched` page
counts (`pdf_processor.py:213`). The screen never learns about:

- a REF from the CSV with no page (a courier label that never arrived);
- a REF stamped on more than one page.

**Scenario.** The courier PDF is missing one page. The run reports "40
matched, 0 unmatched", and the missing parcel is found only when an order
has no label at the packing bench.

**Production evidence.** Six processed PDFs with 119 pages: 117 were
stamped, and one REF appears twice (AUDIT-04-7).

### AUDIT-04-9, -10, -11 (low)

- **AUDIT-04-9.** When stamping a matched page fails, the page is appended
  unstamped but still counted in `matched` (`pdf_processor.py:190`).
- **AUDIT-04-10.** With lot tracking on, a packing list's `columns` setting
  is ignored in favour of the fixed lot layout (`packing_lists.py:176`).
- **AUDIT-04-11.** REFs are sorted by their first digit run
  (`pdf_processor.py:547`). A tracking-shaped REF such as `HW1ABC…` sorts as
  `1` and lands among, or ahead of, the numeric REFs. In production, 5
  tracking-shaped REFs across 4 of 6 PDFs are placed this way.

### AUDIT-04-12 — Stale barcode PDFs (high, unproven)

**What goes wrong.** The barcodes folder for a packing list keeps whatever
PDF was generated last. Re-running the analysis or regenerating the list
leaves that PDF in place and does not mark it.

**Production evidence.** In HERBAR 2026-07-17_2 the barcode PDF was
generated about 70 minutes before a re-run and a regenerated packing list.
Two of its labels are for orders the new analysis holds, and the new list
doesn't contain them.

**Why unproven.** The staleness is a workflow across the Qt tabs, not a
function that can be called in a unit test.

## 4. Verified correct

| what | how | test |
|---|---|---|
| Packing list XLSX and JSON carry exactly the fulfillable lines, with the same quantities and correct header totals; blocked orders are excluded | synthetic session | `test_packing_list_xlsx_and_json_carry_exactly_the_fulfillable_lines` |
| Packing list order is numeric, so `#9` comes before `#10` and `#100` | synthetic | `test_packing_list_is_in_numeric_order_number_order` |
| Lot rows keep the order's quantity when an order repeats a SKU line | synthetic | `test_packing_list_lot_rows_keep_the_order_quantity` |
| Stock export per-SKU totals equal the fulfillable quantities, with blocked orders excluded | synthetic | `test_stock_export_totals_equal_fulfillable_quantities` |
| Per-lot export rows sum to the allocation, not to twice it | synthetic | `test_stock_export_lot_rows_sum_to_the_allocation` |
| The barcode value is the order number unchanged: `#`, letters, leading zeros, `-` and `_` are all kept; label numbers are 1..n | synthetic | `test_barcode_value_is_the_order_number_unchanged` |
| The reference-strip barcode encodes the REF exactly | synthetic | `test_reference_strip_barcode_encodes_the_reference_exactly` |
| A PostOne ID wins over the name fallback | synthetic | `test_postone_id_beats_the_name_fallback` |
| A run keeps every page, sorts matched pages by REF and puts unmatched pages last | synthetic PDF | `test_reference_run_sorts_pages_by_reference_and_keeps_every_page` |

Production check, run read-only over all 39 sessions:

- **Packing lists.** 35 lists: the XLSX equals its JSON in all 35, and the
  JSON header totals are right. 34 of 35 match the saved analysis line for
  line. The remaining one, ALMADERM 2026-07-01_2, was generated about 24
  hours before that session's 13 toggles and 3 bulk status changes. The
  mismatch comes from editing after generation, not from the list.
- **Stock exports.** 36 exports, 34 of which equal the fulfillable per-SKU
  sums. One is the same edited session. The other, `R36 summary.xls`, is a
  multi-session merge, not a single session's export.
- **Barcodes, old layout.** 30 PDFs with 749 pages. The 616 pages a decoder
  could read each encode exactly an order number from that session. No value
  is duplicated, and the only values outside the current list are the
  AUDIT-04-12 case. The other 133 pages use the retired layout, which the
  decoder could not read. They were not assessed further, because that
  layout is no longer produced.
- **Current layout.** Labels rendered by today's code from synthetic orders
  were decoded with zxing-cpp outside the repo. The Code-128, QR and REF
  strip values matched the input exactly, including `#`, leading zeros and
  `-`.

## 5. Not covered, and open questions

**Not covered.**

- Printing (`label_printing.py`, `gui/pdf_printing.py`) was read, not
  tested. Resizing to the label size ignores the aspect ratio, and each page
  is its own print job, so a failure part-way leaves a partial print with no
  record of which pages printed. Both are print-quality concerns, not data
  correctness, and are noted for a later pass.
- The input CSVs and courier PDFs for the reference labels were not kept, so
  matching could not be replayed against production.
- The label's SUM counts every fulfillable line of the order, including SKUs
  a list excludes. No client excludes SKUs today.

**Owner decisions (2026-09-25).** Two business rules came up during the
audit, and the owner decided both:

1. **`Order_Min_Box` keeps today's behaviour.** Items with no configured
   dimensions are ignored, and the box is picked from the items that have
   dimensions. This decides the box for 243 of 718 ALMADERM orders and 16
   of 64 WATERDROP orders. The docstring that promises `UNKNOWN_DIMS` is
   what is wrong, and it gets corrected.
2. **Barcode label #N must be the N-th order on its packing list.** Today
   labels follow order-number order, while the list sorts by courier first,
   so the two differ in the 6 of 35 lists with more than one courier. This
   is now a change to make, tracked with the fix tasks.
