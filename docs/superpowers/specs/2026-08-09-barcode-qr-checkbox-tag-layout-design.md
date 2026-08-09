# Barcode Generator — QR Checkbox, Auto-Open-PDF, Tag Layout Fix (patch on D-3/D-4)

## Problem

`docs/superpowers/specs/2026-07-30-label-barcode-system-design.md` (D-3) speced removing the
Barcode Generator window's info paragraph / PNG-PDF choice / auto-open-folder checkbox, and
adding an auto-open-PDF checkbox plus an "Add QR labels" checkbox — but D-3 was never
implemented against the widget. Separately, `docs/superpowers/specs/2026-08-07-blabel-label-rendering-design.md`
implemented D-4's Code-128 label redesign and a `generate_qr_labels_pdf()` backend function
(QR payload: order number + SKU/qty lines, per D-4's original design), but that function is
still never called from the GUI — there is no way to generate a QR label today.

Reported against PR #259 (`gui/barcode_generator_widget.py`):

1. No GUI switch exists to generate QR-code labels at all.
2. The wanted QR content is simpler than D-4's original design: just the order number
   (mirroring what the Code-128 barcode already encodes), not SKU/qty line items.
3. "Auto-open barcodes folder after generation" should be removed; auto-opening the
   generated PDF should be the checkbox-controlled option instead. Today the barcode PDF is
   opened *unconditionally* in `_generate_pdf_from_results()` (no checkbox gates it at all) —
   this is also a latent behavior bug, not just a missing feature.
4. The Code-128 label's TAG field can visually overflow the physical 68mm × 38mm label when
   an order has enough tags to wrap past what `label_tools.fit_font_block()`'s 1.8mm font
   floor can fit in its cramped 14mm × 10mm box — "Tags can go out from layout if put more
   than one lane of tags."

## Goals

1. Add an "Add QR labels" checkbox (unchecked by default) to the Options section. When
   checked, generating barcodes also renders a second PDF,
   `{packing_list}_qr_labels.pdf`, in the same output folder.
2. QR payload is the order number only. The QR label is redesigned to reuse the same info
   column as the Code-128 label (seq#, courier, date, SUM, COU, TAG) — the QR code simply
   replaces the barcode image on the right side.
3. Replace "Auto-open barcodes folder after generation" with "Auto-open PDF after
   generation" (checked by default — matches today's de facto always-open behavior). When
   checked, it opens every PDF generated in that run (barcode PDF always; QR PDF too, if
   that checkbox was also checked). Remove the folder-opening behavior and
   `_open_barcodes_folder()` entirely.
4. Redesign both label templates so the TAG field gets a full-width row across the bottom of
   the label (~4x the horizontal room of the current 14mm-wide column box) instead of a
   narrow column box, and add `overflow: hidden` on the tag value box as a hard guarantee
   that content can never bleed past the label's physical bounds regardless of font-fit math.

## Non-goals

- **The D-1/D-3 "Print..." button** (in-app printing via `QPrinter`/`QPrintDialog`). Not
  requested here, and it needs a new `gui/pdf_printing.py` module (D-1) that doesn't exist
  yet. The auto-opened PDF still prints fine through the OS's own PDF viewer. Revisit as its
  own patch if wanted.
- **A shared Jinja2 partial between `barcode_label/` and `qr_label/` templates.** Checked
  `blabel.Blabel.LabelWriter`: it builds a bare `jinja2.Template(string)` with no
  `Environment`/loader configured, so `{% include %}` isn't available without adding custom
  template-loading plumbing. For two ~30-line static template files, keeping them separate
  (with duplicated markup for the shared info column) is simpler than building that
  machinery for this patch. Revisit if a third label type is ever added and the duplication
  actually hurts.
- **Reference Labels window (D-2)**, threaded printing, raw ZPL, template
  externalization — unchanged, same non-goals as the two prior specs this patches.
- **`sanitize_order_number()` / `format_tags_for_barcode()` behavior** — unchanged, still
  the shared data-prep step for both label types.
- **PDF generation threading.** Today `_generate_pdf_from_results()` (which calls
  `generate_code128_labels_pdf()`) runs synchronously on the main thread, inside
  `_on_generation_complete()` — not inside the background `Worker` like
  `generate_barcodes_batch()` is. This patch keeps that same pattern for the new QR PDF call
  (added immediately alongside the existing barcode PDF call) rather than restructuring
  threading, which isn't part of what was asked.

## Design

### A: Widget changes (`gui/barcode_generator_widget.py`)

**`_create_options_section()`:**
- Remove `self.auto_open_folder_checkbox` ("Auto-open barcodes folder after generation").
- Add `self.add_qr_checkbox` — "Add QR labels (order number)", unchecked by default.
- Add `self.auto_open_pdf_checkbox` — "Auto-open PDF after generation", checked by default.

**`_generate_pdf_from_results(self, results)`:** stop unconditionally calling
`QDesktopServices.openUrl()` after rendering — rendering and opening become separate
concerns. It still renders `{packing_list}_barcodes.pdf` and returns `True`/`False` for
success, but no longer opens anything itself.

**New `_generate_qr_pdf_from_results(self, results)`:** mirrors
`_generate_pdf_from_results()` — calls `generate_qr_labels_pdf(results, qr_pdf_path)` where
`qr_pdf_path = self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf"`, wrapped in
the same try/except-log-and-return-`False` pattern. Takes the same `results` list shape as
the barcode PDF (no separate SKU/qty collection needed — see Design B).

**`_on_generation_complete(self, results)`:** after computing `successful`/`failed` as today:
1. `pdf_generated = self._generate_pdf_from_results(successful) if successful else False`
   (unchanged).
2. `qr_pdf_generated = False`; if `successful and self.add_qr_checkbox.isChecked()`:
   `qr_pdf_generated = self._generate_qr_pdf_from_results(successful)`.
3. Failure dialog: unchanged condition (`if successful and not pdf_generated`) for the
   barcode PDF — that's the primary artifact. If QR was requested but
   `qr_pdf_generated` is `False`, append a line to the completion message noting the QR
   labels PDF failed to generate (does not block the success dialog for the primary PDF —
   QR is an optional secondary artifact).
4. Success message: append "Also generated QR labels as a PDF document." when
   `qr_pdf_generated`.
5. Auto-open: replace the old `if pdf_generated and self.auto_open_folder_checkbox.isChecked(): self._open_barcodes_folder()`
   with, when `self.auto_open_pdf_checkbox.isChecked()`: open the barcode PDF (via
   `QDesktopServices.openUrl`) if `pdf_generated`, and open the QR PDF if
   `qr_pdf_generated`. Both opens are independent — a QR failure doesn't block opening the
   successfully-generated barcode PDF.

**Remove:** `_open_barcodes_folder()` method entirely (dead once nothing calls it).

### B: Backend (`shopify_tool/barcode_processor.py`)

`generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path` changes
signature to match `generate_code128_labels_pdf()`'s `orders` shape exactly — same dicts
already produced by `generate_barcodes_batch()`: `order_number` (or `safe_order_number`,
matching how the barcode path passes it — see below), `sequential_num`, `courier`,
`country`, `tag`, `item_count`. Internally:

```python
date_str = datetime.now().astimezone().strftime("%d/%m/%y")
records = [
    {
        "order_number": order["safe_order_number"],
        "sequential_num": order["sequential_num"],
        "courier": order["courier"],
        "country": order["country"],
        "tag": order["tag"],
        "item_count": order["item_count"],
        "date_str": date_str,
    }
    for order in orders
]
```
— identical record-building to `generate_code128_labels_pdf()` (both now build the same
record shape for their respective templates; no shared helper extracted for this, per the
Non-goals note on template partials — two call sites building an identical 8-line dict
literal isn't worth a helper). QR payload becomes `label_tools.qr_code(order_number)` in the
template (Design D) — no more `sku_qty_lines` parameter, no more SKU/qty grouping.

### C: Shared label layout redesign (both `barcode_label/` and `qr_label/` `style.css`)

68mm × 38mm label, 1mm padding (66×36mm content area), restructured as two stacked rows
instead of the current single side-by-side row:

```
┌────────────────┬───────────────────┐   ~27mm tall
│ #7  seq         │  [barcode or QR]  │
│ DHL courier     │                   │
│ 09/08/26        │      #1234        │
│ ─────────────   │                   │
│ SUM: 3          │                   │
│ ─────────────   │                   │
│ COU: DE         │                   │
├─────────────────┴───────────────────┤   ~8mm tall, full 66mm width
│ TAG: GIFT+1|GIFT+2|PRIORITY|FRAGILE  │
└───────────────────────────────────────┘
```

- `.label` becomes `flex-direction: column` (was `row`) at the top level, containing a
  `.top-row` (`flex-direction: row`, the existing info-column + code-section side by side,
  height ~27mm) and a `.tag-row` (full width, height ~8mm, `overflow: hidden`).
- `.info` column drops its `TAG` field entirely (moves to `.tag-row`); its width can shrink
  slightly (was 24mm, tags no longer need to fit inside it).
- `.tag-row`: `.field-label` ("TAG:") fixed width (~9mm) + `.field-value` `flex: 1` (~55mm
  wide) + `overflow: hidden` on `.field-value`.
- `label_tools.fit_font_block()` call in the template updates its box args to match the new
  box: `box_width_mm=55, box_height_mm=7` (up from `box_width_mm=14, box_height_mm=10`) —
  same function, no code change to `label_tools.py`, just different call-site arguments.
  `max_mm`/`min_mm` (3.2/1.8) stay as-is; the bigger box means fewer orders actually need to
  shrink down to the floor in practice.
- The `overflow: hidden` on `.field-value` is the actual fix for "goes out of layout" as a
  guarantee — `fit_font_block()`'s shrink-to-min behavior reduces *how often* clipping would
  ever be needed, but no font-fit heuristic can prove zero overflow for arbitrary input, and
  a physically overflowing die-cut label is worse than a clipped one.

### D: QR label template (`qr_label/template.html`, `qr_label/style.css`)

Rebuilt to structurally mirror `barcode_label/template.html`'s new layout (Design C): same
`.top-row` (info column: seq/courier/date/SUM/COU) + `.tag-row`, with the code section now
`<img class="qr" src="{{ label_tools.qr_code(order_number) }}"/>` in place of the barcode
`<img>`, followed by the same `order_number` caption text underneath it (matching the
barcode label's existing caption convention). `qr_code()` in `label_tools.py` is unchanged —
still takes a plain string payload; it now receives `order_number` instead of a multi-line
SKU/qty payload.

## Testing

Per `AGENTS.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` must pass before merge.

- `tests/test_barcode_processor.py`: update `TestGenerateQrLabelsPdfIntegration` for the new
  `orders` shape (same fields as `TestGenerateCode128LabelsPdfIntegration`'s `_order()`
  helper) — page-count smoke test, empty-orders `ValueError`, and a payload test asserting
  `label_tools.qr_code()` receives just the (sanitized) order number, not a multi-line
  SKU/qty string.
- `tests/test_label_tools.py`: `fit_font_block()` tests already parametrize box dimensions
  generically — no signature change, existing tests pass unmodified. No new test needed
  there since the box-size change is a template call-site detail, not a `label_tools.py`
  behavior change.
- `tests/test_barcode_generator_widget.py` (existing — currently exercises
  `_on_generation_complete()` via a `_FakeWidget` stand-in): update `_FakeWidget` to drop
  `auto_open_folder_checkbox`/`_open_barcodes_folder`/`opened_folder`, add
  `auto_open_pdf_checkbox`, `add_qr_checkbox`, `_generate_qr_pdf_from_results()`, and
  `opened_pdfs` (list, tracking calls to the PDF-open path) so existing assertions
  (`assert not widget.opened_folder` etc.) become `assert not widget.opened_pdfs`. Add new
  cases: QR checkbox off → `_generate_qr_pdf_from_results` never called; QR checkbox on +
  primary PDF succeeds → QR PDF also rendered and opened (when auto-open is on); QR PDF
  render failure doesn't block the primary success dialog, just adds the failure note.
- Manual QA (unautomatable, matches prior specs' pattern): print a real batch to the
  physical Citizen CL-E300 with an order carrying 4+ tags; confirm the tag row no longer
  clips into or past the label edge. Generate a QR-labels batch and confirm a phone/scanner
  reads the order number correctly from the QR.

## Files touched

- `gui/barcode_generator_widget.py` — checkbox changes, `_generate_qr_pdf_from_results()`,
  `_on_generation_complete()` rewiring, `_open_barcodes_folder()` removed
- `shopify_tool/barcode_processor.py` — `generate_qr_labels_pdf()` signature simplified to
  match `generate_code128_labels_pdf()`'s `orders` shape
- `shopify_tool/templates/barcode_label/{template.html,style.css}` — tag field moves to a
  full-width bottom row
- `shopify_tool/templates/qr_label/{template.html,style.css}` — rebuilt to mirror the
  barcode label's info-column layout, QR replacing the barcode image
- `tests/test_barcode_processor.py` — `TestGenerateQrLabelsPdfIntegration` updated
- `tests/test_barcode_generator_widget.py` — `_FakeWidget` and assertions updated, QR
  scenarios added
- `tests/test_label_templates.py` — new; structural regression tests reading the template
  files directly (tag-row present, hard overflow guard present) so the fix can't silently
  regress even though visual correctness itself stays manual QA

## Follow-ups (not in this patch's scope)

- D-1/D-3's "Print..." button (in-app printing) — its own patch if wanted.
- Shared Jinja partial for the two label templates' common info column, if a third label
  type is ever added and duplication becomes a real maintenance cost.
