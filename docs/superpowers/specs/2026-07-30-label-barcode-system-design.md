# Label & Barcode System — Design

## Problem

The Todoist "Phase 4 — Label & barcode system" epic bundles four backlog items against
two windows (Reference Labels, Barcode Generator) and their backing modules
(`pdf_processor.py`, `barcode_processor.py`), with a repeated ask across all four: strip
clutter, default to PDF, add printer selection, add a QR/order-number barcode.

- **Reference Labels** processes courier-provided shipping-label PDFs (DHL/PostOne/DPD
  etc.), matching each page to a Reference Number via a CSV (PostOne ID / Tracking Number
  / Client Name). It currently shows a persistent "Processing History" table and has no
  way to print its output except opening the PDF externally.
- **Barcode Generator** generates one Code-128 label per order from the current session's
  packing list, combined into a PDF. Its window carries an info paragraph, a PNG/PDF
  format choice (PDF is already the practical default), and an auto-open-folder checkbox,
  and likewise has no in-app print path.

Two items (`sku_label_manager.py`) named in the original epic description no longer
apply — that module was deleted in Phase 1 (Reports/SKU-labels removal), guarded by
`tests/test_reports_sku_labels_removed.py`. Not touched here.

## Goals

1. Both windows can print their generated PDF directly, with a printer picker, without
   leaving the app.
2. Reference Labels window loses the Processing History clutter; each processed page
   additionally carries a small Code-128 barcode encoding its Reference Number (the only
   per-shipment identifier this pipeline has — there is no Shopify order number in this
   flow).
3. Barcode Generator window loses the info paragraph, the PNG/PDF/auto-open-folder
   choices; the Code-128 label itself gets a cleaner, more consistently laid-out info
   column and stays PDF-only.
4. Optionally (new checkbox, off by default), also generate a second, **physically
   separate** set of labels: one QR code per order encoding that order's SKU/quantity
   contents, plus the order number — its own PDF, printed as its own job.

## Non-goals

- Combining the QR code onto the same physical label as the Code-128 barcode. Rejected:
  two codes that close together risk a handheld scanner picking up the wrong one during
  warehouse fulfillment — the reason this became a separate PDF/print job instead of a
  layout tweak.
- Any structural change to Reference Labels' page-matching logic (PostOne
  ID/Tracking/Name matching in `pdf_processor.py`). Only the post-match overlay step
  changes.
- Threaded/background printing. `print_pdf()` (Section D-1) runs synchronously on the
  main thread after the print dialog closes — acceptable for label-sized PDFs and keeps
  the "no UI calls from background threads" rule trivially satisfied.
  <!-- ponytail: synchronous printing blocks the UI for the render+spool duration;
  move to a Worker if a large batch ever makes that noticeable -->
- Any change to `packing-tool` or `shared/`.
- SKU label printing / `sku_label_manager.py` — already removed in Phase 1.

## Design

### D-1: Shared print-to-printer helper

New module, `gui/pdf_printing.py`:

```python
def print_pdf(parent: QWidget, pdf_path: Path) -> bool:
    """Print every page of pdf_path via a native printer-selection dialog.

    Returns True if the user confirmed and printing completed, False if they
    cancelled the dialog. Shows a QMessageBox on failure.
    """
```

Implementation: load `pdf_path` via `PySide6.QtPdf.QPdfDocument`, create a
`PySide6.QtPrintSupport.QPrinter`, open a native `QPrintDialog(printer, parent)`; on
accept, render each page (`QPdfDocument.render()`) onto the printer via `QPainter`,
calling `printer.newPage()` between pages. Both `QtPdf` and `QtPrintSupport` ship with
the already-installed `PySide6` — no new dependency.

Both `gui/reference_labels_widget.py` and `gui/barcode_generator_widget.py` add a
"Print..." button wired to this function, enabled once a PDF exists to print.

### D-2: Reference Labels window — remove history, add Reference-Number barcode

**Window changes** (`gui/reference_labels_widget.py`):
- Delete the "Processing History" `QGroupBox`/`QTableWidget`, the double-click-to-reopen
  handler, and the `ReferenceLabelsHistory` import/usage.
- Delete `shopify_tool/reference_labels_history.py` and stop writing
  `reference_labels_history.json`.
- Window becomes 3 groups: File Selection, Output Settings (unchanged — dir picker +
  existing "Auto-open PDF after processing" checkbox), Processing (Process button,
  progress bar, status, **new "Print..." button** via D-1).
- With history gone, nothing on disk tracks "the last processed PDF" — the widget keeps
  it in memory only: `self.last_output_pdf` set in `_on_processing_complete()`, which is
  what the Print button targets and what its enabled state depends on. Reopening the tab
  in a later session with no processing done yet leaves Print disabled, same as Process
  is today before files are selected.

**Barcode overlay** (`shopify_tool/pdf_processor.py`):
`create_reference_overlay()` currently draws `"REF: {ref}"` and `"{order_num}."` as text
in a fixed bottom strip. Add a small Code-128 barcode encoding `ref` next to that text, in
the same strip, shrinking the original page content slightly to make room (per the
original ask — "allowed to shrink label slightly to fit").

To avoid a second barcode-rendering implementation, extract the Code-128 image generation
already inlined in `barcode_processor.generate_barcode_label()` (build via
`barcode.codex.Code128` + `ImageWriter`, crop the auto-generated text off the bottom) into
a shared, reusable function:

```python
# shopify_tool/barcode_processor.py
def render_code128_barcode(data: str) -> Image.Image:
    """Render a Code-128 barcode as a PIL Image, no text, no quiet zone."""
```

`generate_barcode_label()` calls this instead of inlining the same steps.
`create_reference_overlay()` (in `pdf_processor.py`) imports it, wraps the result via
`reportlab.lib.utils.ImageReader`, and draws it into the overlay canvas next to the REF
text. The original page's content is shrunk to fit above the strip using
`pypdf`'s `PageObject.add_transformation()` (uniform scale + translate) before merging the
overlay, rather than resizing the physical page — keeps the output page size unchanged
for the courier label stock.

No scanner-conflict handling needed here (confirmed) — this barcode is scanned at a
different point in the workflow (warehouse-internal sorting) than the courier's own
barcode on the same page.

### D-3: Barcode Generator window — strip clutter

`gui/barcode_generator_widget.py`:

**Remove:**
- The "Barcodes will be generated for..." info `QLabel`.
- "Auto-open barcodes folder after generation" checkbox and its behavior.
- "Generate PNG files" checkbox — PNGs remain an internal implementation detail (the PDF
  is still built by compositing them) but are now always cleaned up after the PDF is
  built; no user-facing choice.
- "Generate PDF file" checkbox — PDF generation is no longer optional.

**Add:**
- "Auto-open PDF after generation" checkbox (checked by default), replacing the folder
  auto-open — mirrors the pattern already used in Reference Labels.
- "Add QR labels" checkbox (unchecked by default) — see D-4.
- "Print..." button (D-1) for the barcode PDF, enabled once it exists; a second
  "Print QR labels..." button appears once a QR-labels PDF exists (they're genuinely
  separate print jobs, per the non-goal above). Same in-memory tracking approach as D-2
  (`self.last_barcode_pdf` / `self.last_qr_pdf`, set when generation completes) — this
  widget never had a history file to begin with.

**Dead-code cleanup (same touch, adjacent, confirmed in scope):** delete
`shopify_tool/barcode_history.py` (`BarcodeHistory` class) and
`SessionManager.get_barcode_history_file()` — both already fully unused; the widget's own
code comment notes "History removed - using logs only."

### D-4: Code-128 label redesign + new QR label

**Code-128 label redesign** (`barcode_processor.generate_barcode_label()`), addressing
font readability, spacing/margins, and barcode size/position feedback: rework the left
info column into a uniform label:value grid — consistent row height, one font size
instead of six graduated sizes, consistent separator rule weight — and make the barcode
section's margins consistent on all four sides (today's margins are inconsistent ad-hoc
pixel values). Barcode size/position stays close to current proportions — this was the
lowest-risk-to-scan-reliability option of the three layouts explored. Order number stays
large/prominent underneath, unchanged in that regard.

**New QR label** — new function in `barcode_processor.py`:

```python
def generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """Generate a QR-only labels PDF, one page per order (order number + QR of
    SKU/qty contents, nothing else), same page size (LABEL_WIDTH_MM x
    LABEL_HEIGHT_MM) as the Code-128 label, for the same label stock.

    Each order dict: {"order_number": str, "sku_qty_lines": list[tuple[str, int]]}.
    """
```

Content: order number as large text, QR code below it, nothing else. QR payload is plain
text: order number followed by one `SKU x QTY` line per line item, built via
`reportlab.graphics.barcode.qr.QrCodeWidget` (already available through the existing
`reportlab` dependency — no new library).

**Implementation note:** unlike the Code-128 path, this does *not* go through a PNG
intermediate. `reportlab`'s raster backend (`renderPM`) needs an extra backend package
(`rlPyCairo`, or a compiled C extension) that isn't installed and would be a new
dependency to add just for this. `QrCodeWidget` is a vector `reportlab.graphics` widget,
so `generate_qr_labels_pdf()` draws it straight onto a `reportlab.pdfgen.canvas.Canvas`
page via `reportlab.graphics.renderPDF.draw(drawing, canvas, x, y)` — one `canvas.Canvas`
with one page per order (`drawCentredString` for the order number, `renderPDF.draw` for
the QR, `showPage()` between orders), building the whole PDF directly. No PNG files, no
reuse of `generate_barcodes_pdf()` (that function specifically composites existing PNG
files, which don't exist in this path).

**Wiring** (`gui/barcode_generator_widget.py`, `_generate_barcodes_worker`): when "Add QR
labels" is checked, also collect each order's `(SKU, Quantity)` rows from
`filtered_orders_df` (grouped by `Order_Number`, before the existing collapse to
`unique_orders` loses line-item detail), and call `generate_qr_labels_pdf()` once with the
full list of orders to produce `{packing_list}_qr_labels.pdf` in one pass. Both PDFs land in
`barcodes/<packing_list>/`, independently printable via D-1.

## Testing

Per `AGENTS.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` must pass before merge.

- `tests/test_barcode_processor.py` (existing): extend for `render_code128_barcode()`
  (extracted helper produces the same image `generate_barcode_label()` did before, no
  behavior change), the redesigned label layout (smoke test — generates without error,
  correct output dimensions), and new `generate_qr_labels_pdf()` (valid multi-page PDF
  output, page count matches order count; no QR-decode library is available in this
  repo's dependencies, so payload correctness is asserted via `QrCodeWidget.value`
  matching the expected `SKU x QTY` formatting, not a round-trip decode).
- `tests/test_pdf_processor.py` (new — no existing coverage of this module): overlay
  barcode is present and decodable on a generated overlay page; page-content scaling
  doesn't crash across a couple of representative page sizes; existing REF-text-position
  behavior unchanged.
- New `tests/test_reference_labels_widget.py` and `tests/test_barcode_generator_widget.py`
  (matching this repo's existing `test_*_widget.py`/GUI-test convention, e.g.
  `test_session_setup_layout.py`, `test_checkbox_delegate.py`): history UI is gone;
  removed checkboxes/labels are gone; Print button enable/disable state tracks whether a
  PDF exists; QR checkbox drives whether a second PDF is produced.
- `gui/pdf_printing.py`: unit test with a `QPrinter` in preview/PDF-output mode (no real
  OS printer needed in CI) asserting `print_pdf()` doesn't raise and produces the expected
  page count — dialog interaction itself isn't testable headlessly, so this only covers
  the render path.
- Manual QA (both are new user-facing interactions, not covered by the automated
  suite): print a real multi-page PDF to an actual Windows printer for each of the two
  "Print..." buttons; confirm the two PDFs (barcode + QR) print as visually distinct,
  separately-triggerable jobs.

## Files touched

- `gui/pdf_printing.py` — new
- `gui/reference_labels_widget.py` — remove history UI, add Print button
- `gui/barcode_generator_widget.py` — remove clutter, add auto-open/QR/Print controls
- `shopify_tool/pdf_processor.py` — `create_reference_overlay()` barcode + page scaling
- `shopify_tool/barcode_processor.py` — extract `render_code128_barcode()`, redesign
  `generate_barcode_label()` layout, new `generate_qr_labels_pdf()`
- `shopify_tool/reference_labels_history.py` — deleted
- `shopify_tool/barcode_history.py` — deleted
- `shopify_tool/session_manager.py` — remove `get_barcode_history_file()`
- `tests/test_barcode_processor.py` — extended
- `tests/test_pdf_processor.py` — new
- `tests/test_reference_labels_widget.py` — new
- `tests/test_barcode_generator_widget.py` — new

## Follow-ups (not in this epic's scope)

- If a future courier or label size needs different QR-label dimensions, revisit the
  "same page size as Code-128 label" assumption in `generate_qr_label()`.
- If print jobs on large batches noticeably block the UI in practice, move `print_pdf()`
  rendering into a `Worker` (see ponytail note under Non-goals).
