# Print Polish + Reference-Number Barcode — Design

## Problem

Manual QA of the direct-label-printing feature (`2026-08-10-direct-label-printing-design.md`,
landed in `1d8898f`) surfaced three problems:

1. **Settings collide across windows.** `gui/pdf_printing.py`'s `load_print_settings()` /
   `save_print_settings()` read and write one fixed QSettings key set. Reference Labels and
   Barcode Generator each have their own copy of the print-mode/target/rotate controls, but both
   copies point at the *same* underlying storage — setting a raw ZPL target in one window
   overwrites the other's. In practice the operator needs two different physical printers (a
   label printer for Reference Labels, a different one for Barcode Generator's Code-128/QR
   labels), which this shared storage can't represent.
2. **Driver-mode printing is broken.** `_print_pdf_driver_mode()` renders each PDF page via
   `document.render(page, document.pagePointSize(page).toSize())` — passing a *point*-sized
   (1/72") dimension where a *pixel* dimension is expected — then draws that undersized image at
   `(0, 0)` with no scaling. A 68×38mm label renders as a ~193×108px image drawn 1:1 onto the
   printer's high-resolution device canvas: a postage-stamp-sized print in the corner of the
   page, confirmed against a real print (18-label batch, driver mode, Windows). Separately, the
   print loop always iterates every page regardless of the page range the operator selects in
   the native print dialog, and there's no remembered default printer per window (every driver
   print starts from Windows' system default).
3. **Reference Labels' D-2 barcode overlay was never built.** The original epic design
   (`2026-07-30-label-barcode-system-design.md`, section D-2) specced adding a Code-128 barcode
   to each processed reference label, encoding its Reference Number, with the original page
   content shrunk slightly to make room — every subsequent patch against this epic carried it
   forward as a non-goal/follow-up. The operator wants this now: a scannable barcode on the
   label itself so a packer can scan it as an alternative identifier, without leaving the app to
   open a separate Barcode Generator PDF.

Investigation for this spec (see below) also confirmed a constraint on item 3: **Reference
Labels has no access to a real Shopify Order Number.** `process_reference_labels()` only ever
sees the courier-provided PDF plus a courier CSV (PostOne ID / Tracking Number / Reference
Number / Client Name) — tracking numbers are assigned by the courier *after* the Shopify order
export, so they were never present in any Shopify-side data (`shopify_tool/analysis.py`'s
working dataframe has no Tracking/Reference/PostOne/Client-Name column at all). The barcode this
spec adds therefore encodes the Reference Number, matching the original D-2 design's reasoning
— confirmed as the intended approach, not a fallback.

## Goals

1. Reference Labels and Barcode Generator each have fully independent print settings (mode,
   raw ZPL target, rotate, default driver printer) — configuring one never touches the other.
2. Driver-mode printing renders each label at the correct physical size, honors the page
   range the operator selects in the print dialog, and offers a real printer picker with a
   remembered per-window default.
3. Each processed Reference Labels page gets a horizontal Code-128 barcode encoding its
   Reference Number, in a reserved strip at the bottom of the page, with the original page
   content shrunk (vector transform, no rasterization) to make room without visual overlap
   or quality loss.

## Non-goals

- **Linking Reference Labels to real Shopify Order Numbers.** Confirmed infeasible with
  existing data (see Problem). Out of scope; would require either a new CSV column sourced
  externally (e.g. from the courier's export) or a Shopify-fulfillment-API round-trip — both
  separate features, not addressed here.
- **Verifying packing-tool accepts Reference Number as a scan lookup key.** This app produces
  the barcode; whether the downstream packer tool's scan flow resolves a Reference Number to
  anything useful is outside this repo and must be confirmed operationally, separately.
- **Raw ZPL target enumeration.** Unchanged from the original design — still free text (Windows
  queue name or Linux device path); only the *driver-mode* printer gets a picker, since raw ZPL
  targets aren't necessarily enumerable OS printers (e.g. `/dev/usb/lp0`).
- **Copies handling.** `printer.copyCount()` is already forwarded to the OS spooler by Qt/the
  driver once a dialog is used normally; no app-level loop is needed and none is added.
- **Threaded printing.** Still synchronous, per the original spec's non-goal (unchanged
  ponytail note carried forward: move to a Worker if a large batch is ever reported as a
  noticeable UI freeze).
- **Any change to `packing-tool` or `shared/`.**

## Design

### D-1: Per-window print settings (`gui/pdf_printing.py`)

`load_print_settings()` / `save_print_settings()` gain a required `scope: str` argument
(`"reference_labels"` or `"barcode_generator"`), prefixed onto every QSettings key:

```python
def load_print_settings(scope: str) -> dict:
    qs = QSettings(*_SETTINGS)
    return {
        "print_mode": qs.value(f"{scope}/print_mode", "driver"),
        "raw_zpl_target": qs.value(f"{scope}/raw_zpl_target", ""),
        "raw_zpl_rotate": qs.value(f"{scope}/raw_zpl_rotate", False, type=bool),
        "driver_printer_name": qs.value(f"{scope}/driver_printer_name", ""),
    }


def save_print_settings(scope: str, settings: dict) -> None:
    qs = QSettings(*_SETTINGS)
    qs.setValue(f"{scope}/print_mode", settings["print_mode"])
    qs.setValue(f"{scope}/raw_zpl_target", settings["raw_zpl_target"])
    qs.setValue(f"{scope}/raw_zpl_rotate", settings["raw_zpl_rotate"])
    qs.setValue(f"{scope}/driver_printer_name", settings["driver_printer_name"])
```

Each widget passes its own literal scope string at every call site (`_create_options_section()`
/ `_create_processing_group()`, `_save_print_settings()`, `_on_print_clicked()` /
`_on_print_qr_clicked()`).

**Simplification: delete `refresh_print_controls()` and its `showEvent()` call.** That function
exists solely to stop one window's stale controls from re-saving and clobbering a change just
made in the *other* window (PR #261 review fix) — a race that can only happen because both
windows shared one key namespace. Once each window owns its own scope, the race is structurally
impossible, so the resync-on-show mechanism has no remaining purpose. `gui/reference_labels_widget.py`
and `gui/barcode_generator_widget.py` go back to loading print settings once at construction
(Barcode Generator's `showEvent()` keeps its unrelated packing-list refresh; Reference Labels'
`showEvent()`, if it has no other purpose, is removed with it).

### D-2: Fix driver-mode printing (`gui/pdf_printing.py`)

**Render at the correct size.** Confirmed against Qt's own reference implementation (Qt for
Python's PDF-viewer example, "Print PDF Document") that the correct pattern renders into the
printer's *device-pixel* page rect, not the document's point size:

```python
def _print_pdf_driver_mode(parent, pdf_path: Path, output_path: Path | None = None) -> bool:
    document = QPdfDocument()
    load_error = document.load(str(pdf_path))
    if load_error != QPdfDocument.Error.None_:
        QMessageBox.critical(parent, "Print Failed", f"Could not open PDF for printing:\n\n{pdf_path}\n\n{load_error}")
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    _apply_default_page_size(printer, document)

    if output_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_path))
    else:
        dialog = QPrintDialog(printer, parent)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

    first_page, last_page = _resolve_page_range(printer, document.pageCount())

    try:
        painter = QPainter(printer)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        for page in range(first_page, last_page + 1):
            if page > first_page:
                printer.newPage()
            image = document.render(page, page_rect.size())
            painter.drawImage(page_rect, image)
        painter.end()
        return True
    except Exception as error:
        logger.exception("Driver print failed")
        QMessageBox.critical(parent, "Print Failed", f"Printing failed:\n\n{error}")
        return False
```

**Honor the print dialog's page range** (currently always prints every page):

```python
def _resolve_page_range(printer: QPrinter, page_count: int) -> tuple[int, int]:
    """0-indexed [first, last] page range from the print dialog's selection,
    or the full document if the operator left it on "All"."""
    if printer.printRange() == QPrinter.PrintRange.PageRange:
        from_page = printer.fromPage() or 1
        to_page = printer.toPage() or page_count
        return from_page - 1, min(to_page, page_count) - 1
    return 0, page_count - 1
```

**Default page size matching the label** (addresses the operator manually re-entering paper
dimensions each print): before opening the dialog, set the printer's page size from the PDF's
own first-page dimensions, converted from points to millimeters:

```python
def _apply_default_page_size(printer: QPrinter, document: QPdfDocument) -> None:
    size_pt = document.pagePointSize(0)
    if size_pt.isEmpty():
        return
    size_mm = QSizeF(size_pt.width() / 72 * 25.4, size_pt.height() / 72 * 25.4)
    printer.setPageSize(QPageSize(size_mm, QPageSize.Unit.Millimeter))
```

Still fully overridable by the operator inside the dialog — this only sets the starting point.

**Remembered default printer, per window.** A new `driver_printer_name` setting (D-1), backed
by a `QComboBox` populated from `QPrinterInfo.availablePrinters()` (a real picker of installed
printers — not free text, unlike the raw ZPL target, since these genuinely are enumerable OS
printers). Applied via `printer.setPrinterName(name)` before `_apply_default_page_size()` /
`QPrintDialog` construction, so the dialog opens pre-selected to the window's usual printer but
the operator can still change it. Populated once at construction (installed printers changing
mid-session is not a case worth polling for).

### D-3: Reference-Number barcode + shrink frame (`shopify_tool/pdf_processor.py`)

**Drop the per-batch counter.** `create_reference_overlay()`'s `order_number` parameter (really
`ref_order_map[ref]`, a synthetic 1/2/3... position counter, not a real order number) is
removed, along with `create_reference_order_map()` and its only call site in
`process_reference_labels()` — both become dead code once the counter is gone.

**Shrink + reserve a bottom strip.** A uniform scale (default `_CONTENT_SCALE = 0.88`,
anchored top-center) is applied to the original page's content via `pypdf`'s
`PageObject.add_transformation()` — a vector transform, not a rasterize/resize, so there's no
quality loss. This is applied in `process_reference_labels()`, immediately before merging the
overlay, so it only ever touches matched (`ref` is truthy) pages:

```python
from pypdf import Transformation

_CONTENT_SCALE = 0.88

# inside process_reference_labels(), replacing the current `if ref:` block:
if ref:
    try:
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        transform = Transformation().scale(_CONTENT_SCALE, _CONTENT_SCALE).translate(
            tx=page_width * (1 - _CONTENT_SCALE) / 2,
            ty=page_height * (1 - _CONTENT_SCALE),
        )
        page.add_transformation(transform)

        overlay = create_reference_overlay(ref, page_width, page_height)
        page.merge_page(PdfReader(overlay).pages[0])
    except Exception:
        logger.exception(f"Failed to add overlay for ref {ref}")
```

Scaling about the origin (PDF's bottom-left) shrinks content toward the bottom-left corner; the
translate then pushes it up (`ty`) and centers it horizontally (`tx`), which is what leaves the
freed space as a full-width strip at the *bottom* of the page (height `page_height * (1 -
_CONTENT_SCALE)`) plus small even margins on the left/right — the "frame" effect. Page
`mediabox` dimensions are untouched, so output pages stay the same physical size as the input
courier label stock, per the original design's constraint.

**Barcode + text in the strip.** `create_reference_overlay()` draws `"REF: {ref}"` on the left
of the strip and a horizontal Code-128 barcode (`reportlab.graphics.barcode.code128.Code128` —
already available via the existing `reportlab` dependency, vector, no new library) to its right,
both vertically centered in the strip:

```python
from reportlab.graphics.barcode import code128

def create_reference_overlay(reference_number: str, page_width: float, page_height: float) -> BytesIO:
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    strip_height = page_height * (1 - _CONTENT_SCALE)
    margin = 8

    can.setFont("Helvetica-Bold", 10)
    text = f"REF: {reference_number}"
    text_y = strip_height / 2 - 3
    can.drawString(margin, text_y, text)
    text_width = can.stringWidth(text, "Helvetica-Bold", 10)

    barcode = code128.Code128(reference_number, barHeight=strip_height * 0.6, barWidth=0.8)
    barcode.drawOn(can, margin + text_width + 12, (strip_height - barcode.height) / 2)

    can.save()
    packet.seek(0)
    return packet
```

Exact spacing constants (`margin`, `barWidth`, the `+12`/`* 0.6` fudge factors) are a starting
point tuned against a real courier PDF during implementation/manual QA, not treated as final —
courier page sizes vary, so `_CONTENT_SCALE`'s 12%-of-height strip may need adjusting once
checked against actual output.

## Testing

Per `AGENTS.md`/`CLAUDE.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and the repo's lint
step must pass before merge.

- `tests/test_pdf_printing.py` (extend): `load_print_settings("reference_labels")` and
  `load_print_settings("barcode_generator")` round-trip independently — saving one scope
  never affects the other's stored values. `_resolve_page_range()`: `PrintRange.AllPages` (or
  unset `fromPage`/`toPage`) returns the full range; `PrintRange.PageRange` with
  `fromPage=2, toPage=3` returns `(1, 2)` (0-indexed). `_apply_default_page_size()`: given a
  `QPdfDocument` loaded from a known-size fixture PDF, the printer's resulting `QPageSize`
  matches (within rounding) the fixture's mm dimensions. `_print_pdf_driver_mode()`'s existing
  PDF-output-mode test (`test_renders_expected_page_count_to_pdf_output`) gets a second
  assertion: rendered page content fills the target page rect rather than a small corner
  (compare rendered output image dimensions/bbox against the fixture's page size). Existing
  `TestRefreshPrintControls` class is deleted along with the function.
- `tests/test_barcode_generator_widget.py` / `tests/test_reference_labels_widget.py`: no changes
  needed. Both files use a `_FakeWidget` stand-in and call specific handler methods
  (`_on_generation_complete()` / `_on_processing_complete()`) as unbound methods against it —
  neither constructs the real widget's Options/Output-Settings section, so neither exercises
  `load_print_settings()`/`save_print_settings()`/the new printer combo at all. Coverage for the
  scoping and printer-picker behavior lives entirely in `tests/test_pdf_printing.py` (below) plus
  the existing CI smoke test (`CI=1 python run_dev.py`, which constructs the real widgets and
  would catch a missed call site).
- `tests/test_pdf_processor.py` (new — no existing coverage of this module): `create_reference_overlay()`
  no longer takes an order-number argument; output overlay page contains the REF text.
  No barcode-decode library is available in this repo's dependencies (`python-barcode` only
  generates), so the barcode itself is asserted structurally — that `code128.Code128` was
  constructed with the reference number as its value and drawn within the strip's bounds — not
  via round-trip decode, matching how the original 2026-07-30 spec's QR test handled the same
  constraint. Full-flow
  test: `process_reference_labels()` against a small fixture PDF + CSV produces output pages
  whose `mediabox` is unchanged from the input (shrink is a content transform, not a page-size
  change). `create_reference_order_map()` and its call site are confirmed removed (no lingering
  references).
- **Manual QA** (matches this epic's established pattern — physical printing isn't
  automatable): print a real batch in driver mode to an actual Windows-installed printer from
  both windows, confirming correct size/scale and that page-range selection in the dialog is
  honored; process a real courier PDF through Reference Labels and confirm the barcode strip
  scans correctly and doesn't visually overlap the courier's own label content; confirm setting
  a raw ZPL target/printer in one window leaves the other window's settings untouched.

## Files touched

- `gui/pdf_printing.py` — scoped settings functions, `refresh_print_controls()` removed,
  driver-mode render/page-range/page-size/default-printer fixes
- `gui/reference_labels_widget.py` — scope argument at all print-settings call sites, driver
  printer combo, `refresh_print_controls()` call removed
- `gui/barcode_generator_widget.py` — same as above
- `shopify_tool/pdf_processor.py` — `create_reference_overlay()` signature change + barcode,
  `create_reference_order_map()` removed, shrink transform added to `process_reference_labels()`
- `tests/test_pdf_printing.py` — extended, `TestRefreshPrintControls` removed
- `tests/test_barcode_generator_widget.py` / `tests/test_reference_labels_widget.py` — extended
- `tests/test_pdf_processor.py` — new

## Follow-ups (not in this spec's scope)

- If packing-tool's scan flow turns out not to accept Reference Number as a lookup key, revisit
  whether a real Order Number can be sourced (new CSV column from the courier export, or a
  Shopify fulfillment-API round-trip) — both would be new, separate specs.
- `_CONTENT_SCALE` (and the barcode strip's spacing constants) may need tuning once checked
  against real courier PDF output across the different couriers this pipeline handles
  (DHL/PostOne/DPD etc.) — noted as a starting point, not a final value, in D-3.
- A `win32print.EnumPrinters()`-backed picker for the raw ZPL target, if the free-text field
  proves error-prone in practice (carried forward from the original direct-printing spec).
