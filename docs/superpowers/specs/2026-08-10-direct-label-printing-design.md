# Direct Label Printing (Driver + Raw ZPL) — Design

## Problem

The original Phase 4 epic design (`2026-07-30-label-barcode-system-design.md`, section D-1)
speced a shared "Print..." button for both the Reference Labels and Barcode Generator
windows, backed by a `gui/pdf_printing.py` module using `QPrintDialog`/`QtPdf`. It was never
implemented — every subsequent patch against this epic (`2026-08-07` blabel rewrite,
`2026-08-09` QR-checkbox/tag-layout fix) explicitly carried it forward as a non-goal/follow-up,
and `gui/pdf_printing.py` still does not exist. Both windows still require the operator to open
the generated PDF externally to print it.

Separately, the sibling `barcode_tool` repo (a standalone barcode/label generator for the same
warehouse) already solved direct printing to the actual hardware in use — a Citizen CL-E300
thermal label printer — via **raw ZPL**: render the label, rasterize it to a 1-bit bitmap at the
print head's native 203 DPI, convert to ZPL via `zebrafy`, and spool it to the printer's Windows
queue with the `RAW` datatype via `pywin32`, bypassing the Windows print driver entirely
(`app/core/template_renderer.py`, `app/core/zpl_print_service.py`, `app/core/print_service.py`).
This is proven working in production for that app's own labels, which are rendered by the same
blabel/WeasyPrint HTML-template pipeline `shopify_tool/barcode_processor.py` already uses (both
repos share the `68mm × 38mm` Citizen CL-E300 label format).

This spec finishes D-1's print buttons for both windows and extends the original OS-driver-only
design with raw ZPL as a second, per-machine-selectable print mode — reusing `barcode_tool`'s
proven approach rather than re-deriving it.

## Goals

1. Both Reference Labels and Barcode Generator windows can print their generated PDF(s)
   directly from the app, with no need to open the PDF externally first.
2. Two print modes, chosen by a per-machine setting: **OS driver** (native `QPrintDialog`,
   vector, works with any installed printer — this is the original D-1 design, unchanged) and
   **Raw ZPL** (direct `RAW` spool to a named Windows print queue or, on Linux dev machines, a
   device path — the `barcode_tool`-proven path for the Citizen CL-E300).
3. Barcode Generator gets two independent print actions, mirroring its existing two-PDF
   pattern: "Print..." for the Code-128 barcode PDF, "Print QR labels..." for the QR PDF
   (enabled once each PDF exists). Reference Labels gets one "Print..." action for its single
   output PDF.
4. The print-mode setting and raw-ZPL target/rotate settings are machine-local (each warehouse
   PC has its own printer), configured once, and shared by both windows' print actions — not
   duplicated per window.

## Non-goals

- **Reference Labels' "remove Processing History" / Code-128 reference-number overlay**
  (the rest of the original D-2 design). Out of scope here — this spec only adds Reference
  Labels' print button. The history table and overlay logic are untouched.
- **Threaded printing.** Both print paths run synchronously on the main thread after the
  operator confirms (driver mode: after the `QPrintDialog` closes; raw ZPL: immediately) —
  acceptable for label-sized jobs and keeps "no UI calls from background threads" trivially
  satisfied, same reasoning as the original D-1 non-goal.
  <!-- ponytail: synchronous printing blocks the UI for the render+spool duration; move to a
  Worker if a large batch ever makes that noticeable -->
- **Enumerating installed printers for the raw ZPL target.** The target is a free-text field
  (Windows print-queue name, or a device path like `/dev/usb/lp0` on Linux dev machines),
  exactly matching `barcode_tool`'s proven UI (`app/ui/settings_window.py`). No
  `QPrinterInfo`/`win32print.EnumPrinters()` picker — one more control for a value the operator
  sets once per machine and rarely changes.
- **A print-mode/printer picker for OS-driver mode.** Driver mode opens a native
  `QPrintDialog`, which already lets the operator pick a printer per print job — no separate
  "default printer" setting needed for that mode (unlike `barcode_tool`, which persists a
  default printer because it prints without a dialog in some flows; this app always shows the
  dialog in driver mode).
- **Any change to `packing-tool` or `shared/`.**
- **Any change to PDF/QR label rendering, layout, or content** — `barcode_processor.py`'s
  `generate_code128_labels_pdf()` / `generate_qr_labels_pdf()` and the blabel templates are
  unchanged; this spec only adds a way to print their existing output.

## Design

### D-1: Raw ZPL backend — `shopify_tool/label_printing.py` (new)

Ported from `barcode_tool`'s `app/core/template_renderer.py` (rasterization) and
`app/core/zpl_print_service.py` (ZPL encoding + RAW spooling), adapted to rasterize an
**already-rendered PDF file** (this app's PDFs already exist on disk after generation) instead
of re-rendering records through `blabel.LabelWriter` a second time:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from zebrafy import ZebrafyImage

# The Citizen CL-E300 print head is 203 dpi, so rasterizing at 203 maps one
# image pixel to one dot -- no resampling between here and the head. Thermal
# heads are bilevel, so the greyscale render is thresholded here (mode "1",
# no dithering) rather than left for the head to interpret.
PRINT_DPI = 203


def rasterize_pdf(pdf_path: Path, dpi: int = PRINT_DPI) -> list[Image.Image]:
    """Rasterize every page of pdf_path into a 1-bit PIL Image, one per label."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    images = []
    for page in pdf:
        bitmap = page.render(scale=dpi / 72, grayscale=True)
        images.append(bitmap.to_pil().convert("1", dither=Image.Dither.NONE))
    return images


def image_to_zpl(image: Image.Image, rotate: bool = False) -> str:
    """Convert one rasterized label to a raw ZPL job. See barcode_tool's
    zpl_print_service.py for the invert/rotate/^PW/^LL rationale -- ported
    unchanged, this app's label sizing and print head are identical."""
    if rotate:
        image = image.transpose(Image.Transpose.ROTATE_90)
    field = ZebrafyImage(image, invert=True, complete_zpl=False).to_zpl()
    return f"^XA\n^PW{image.width}\n^LL{image.height}\n{field}\n^XZ\n"


def send_raw_windows(printer_name: str, data: bytes) -> None:
    import win32print

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, ("ZPL label", "", "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def send_raw_linux(device_path: str, data: bytes) -> None:
    Path(device_path).write_bytes(data)


def print_pdf_raw_zpl(pdf_path: Path, target: str, rotate: bool = False) -> None:
    """Rasterize pdf_path and send each page as its own raw ZPL job to target
    (a Windows print-queue name, or a device path on Linux)."""
    for image in rasterize_pdf(pdf_path):
        data = image_to_zpl(image, rotate=rotate).encode("ascii")
        if sys.platform == "win32":
            send_raw_windows(target, data)
        else:
            send_raw_linux(target, data)


def windows_print_errors() -> tuple[type[Exception], ...]:
    """Exception types raised by win32print, for UI-layer except clauses."""
    try:
        import pywintypes
    except ImportError:
        return ()
    return (pywintypes.error,)
```

No new dependency for rendering — `pdf_path` is whatever `generate_code128_labels_pdf()` /
`generate_qr_labels_pdf()` / `pdf_processor.py`'s Reference Labels output already wrote to
disk. `win32print`/`pywintypes` are imported lazily inside functions (never at module import
time) so this module imports cleanly on the Linux dev machine and Linux CI.

### D-2: Print dispatcher — `gui/pdf_printing.py` (new)

```python
def print_pdf(parent: QWidget, pdf_path: Path, settings: QSettings) -> bool:
    """Print every page of pdf_path per the current print-mode setting.

    Driver mode: native QPrintDialog + QtPdf, as originally speced (D-1,
    2026-07-30) -- vector, works with any installed printer.
    Raw ZPL mode: shopify_tool.label_printing.print_pdf_raw_zpl().

    Returns True only if printing completed with no error (driver mode: user
    confirmed the dialog and every page rendered; raw ZPL: no exception was
    raised sending any page). Returns False if the user cancelled the print
    dialog (driver mode only) or if printing failed for any other reason —
    a QMessageBox is shown in the failure case, not the cancel case.
    """
```

- Reads `print_mode` (`"driver"` default, or `"raw_zpl"`) via the shared settings helpers in
  D-5.
- **Driver mode:** load `pdf_path` via `PySide6.QtPdf.QPdfDocument`, create a
  `PySide6.QtPrintSupport.QPrinter`, open a native `QPrintDialog(printer, parent)`; on accept,
  render each page (`QPdfDocument.render()`) onto the printer via `QPainter`, calling
  `printer.newPage()` between pages. Both `QtPdf` and `QtPrintSupport` ship with the
  already-installed `PySide6` — no new dependency. (Unchanged from the original D-1 design —
  never implemented, so ported here verbatim.)
- **Raw ZPL mode:** read `raw_zpl_target`/`raw_zpl_rotate` from settings; if `raw_zpl_target`
  is blank, show a `QMessageBox.warning` telling the operator to set it in Barcode Generator's
  Options box and return `False` without attempting to print. Otherwise call
  `label_printing.print_pdf_raw_zpl(pdf_path, target, rotate)` inside a
  `try`/`except (OSError, *label_printing.windows_print_errors())`, showing a `QMessageBox`
  with the exception text on failure.

Both `gui/reference_labels_widget.py` and `gui/barcode_generator_widget.py` add "Print..."
button(s) wired to this single function — no per-window print logic.

### D-3: Shared print settings — `gui/pdf_printing.py` (same module)

Per-machine settings, following the existing local-`QSettings` pattern already used for window
geometry (`gui/main_window_pyside.py`) and the file-server path
(`shared/server_connection.py`) — **not** the shared/synced `shopify_config.json` that
`gui/settings_window_pyside.py` writes, since a printer queue name is specific to the PC it's
plugged into, not the client account:

```python
_SETTINGS = ("ShopifyFulfillmentTool", "Printing")


def load_print_settings() -> dict:
    qs = QSettings(*_SETTINGS)
    return {
        "print_mode": qs.value("print_mode", "driver"),
        "raw_zpl_target": qs.value("raw_zpl_target", ""),
        "raw_zpl_rotate": qs.value("raw_zpl_rotate", False, type=bool),
    }


def save_print_settings(settings: dict) -> None:
    qs = QSettings(*_SETTINGS)
    qs.setValue("print_mode", settings["print_mode"])
    qs.setValue("raw_zpl_target", settings["raw_zpl_target"])
    qs.setValue("raw_zpl_rotate", settings["raw_zpl_rotate"])
```

### D-4: Barcode Generator changes (`gui/barcode_generator_widget.py`)

**`_create_options_section()`** (`:119-144`): add, below the existing two checkboxes, a
"Printing" sub-group — `QComboBox` (`self.print_mode_combo`: "OS driver (print dialog)" /
"Raw ZPL (direct)"), `QLineEdit` (`self.raw_zpl_target_edit`, placeholder
`"e.g. ZPL-RAW-Printer (Windows) or /dev/usb/lp0 (Linux)"`), `QCheckBox`
(`self.raw_zpl_rotate_check`, "Rotate labels 90° for raw ZPL"). The target field and rotate
checkbox are enabled only when the mode combo is set to raw ZPL
(`print_mode_combo.currentData() == "raw_zpl"`). Loaded from `load_print_settings()` on
`__init__`; each control's change signal calls a new `_save_print_settings()` that reads all
three back into `save_print_settings()`.

**`_create_generation_section()`** (`:146-187`): add `self.print_btn` ("Print...") and
`self.print_qr_btn` ("Print QR labels...") below `self.generate_btn`, both `setEnabled(False)`
initially.

**`_on_generation_complete()`** (`:409-458`): after computing `pdf_generated`/
`qr_pdf_generated`, set `self.last_barcode_pdf = self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf"` if `pdf_generated` else `None`, and likewise
`self.last_qr_pdf` for the QR PDF; then `self.print_btn.setEnabled(bool(self.last_barcode_pdf))`
and `self.print_qr_btn.setEnabled(bool(self.last_qr_pdf))`.

**New handlers:**
```python
def _on_print_clicked(self):
    from gui.pdf_printing import load_print_settings, print_pdf
    print_pdf(self, self.last_barcode_pdf, load_print_settings())

def _on_print_qr_clicked(self):
    from gui.pdf_printing import load_print_settings, print_pdf
    print_pdf(self, self.last_qr_pdf, load_print_settings())
```
Connected to `self.print_btn.clicked` / `self.print_qr_btn.clicked` in `_connect_signals()`.

### D-5: Reference Labels changes (`gui/reference_labels_widget.py`)

**`_create_processing_group()`** (`:153-177`): add `self.print_btn` ("Print...") below
`self.status_label`, `setEnabled(False)` initially.

**`_on_processing_complete()`** (`:472-518`): add `self.last_output_pdf = Path(result['output_file'])` and `self.print_btn.setEnabled(True)`, alongside the existing history/auto-open
logic (both untouched).

**New handler:**
```python
def _on_print_clicked(self):
    from gui.pdf_printing import load_print_settings, print_pdf
    print_pdf(self, self.last_output_pdf, load_print_settings())
```

### D-6: New dependencies (`requirements.txt`)

```
pypdfium2>=4.0          # PDF rasterization for raw ZPL printing
zebrafy>=1.2             # PIL Image -> ZPL conversion for raw ZPL printing
pywin32>=306; sys_platform == "win32"  # win32print RAW spooling (Windows only)
```

Exact same versions `barcode_tool` already runs in production against the same hardware — no
version discovery needed. `pywin32` is conditional on `sys_platform == "win32"` and
`label_printing.py` only imports `win32print`/`pywintypes` inside function bodies, so `pip
install` and `import shopify_tool.label_printing` both work unchanged on Linux (dev machine and
CI).

## Testing

Per `AGENTS.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` must pass before merge.

- `tests/test_label_printing.py` (new):
  - `rasterize_pdf()`: given a small fixture PDF (or a PDF produced by
    `generate_code128_labels_pdf()` in a `tmp_path`), returns one image per page, each in
    mode `"1"`.
  - `image_to_zpl()`: output starts with `^XA`, ends with `^XZ\n`, contains `^PW{width}` and
    `^LL{height}` matching the input image's dimensions; rotate=True produces a
    transposed-dimension image (width/height swapped) fed into the same assertions.
  - `send_raw_windows()`/`send_raw_linux()`: mock `win32print` (inject a fake module via
    `monkeypatch.setitem(sys.modules, "win32print", fake)`) and assert
    `StartDocPrinter`/`WritePrinter`/`EndDocPrinter` are called with the right datatype
    (`"RAW"`) and bytes; `send_raw_linux` asserts the bytes land in the target file
    (`tmp_path`-backed fake device path).
  - `windows_print_errors()`: returns `()` when `pywintypes` isn't importable (true on Linux
    CI), doesn't raise.
- `tests/test_pdf_printing.py` (new):
  - `print_pdf()` driver-mode path: unit test with a `QPrinter` in PDF-output mode (no real
    OS printer needed in CI, matches the original D-1 testing note) asserting it doesn't raise
    and produces the expected page count — dialog interaction itself isn't testable headlessly.
  - `print_pdf()` raw-ZPL-mode path: monkeypatch `label_printing.print_pdf_raw_zpl` and assert
    it's called with the settings' target/rotate; assert the blank-target guard shows a warning
    and returns `False` without calling it.
  - `load_print_settings()`/`save_print_settings()`: round-trip via a `QSettings` pointed at a
    temp/test org+app name (matching how existing `QSettings`-backed tests in this repo isolate
    state, if any exist — otherwise `monkeypatch` the `_SETTINGS` tuple).
- `tests/test_barcode_generator_widget.py` (extend the existing `_FakeWidget` pattern): Print
  buttons start disabled; become enabled exactly when their respective PDF was generated
  (mirrors the existing `pdf_render_calls`/`opened_pdfs` assertion style).
- `tests/test_reference_labels_widget.py` (new, or extend if one exists after this lands):
  Print button starts disabled, becomes enabled after `_on_processing_complete()`.
- **Manual QA** (unautomatable — matches this epic's established pattern): print a real batch
  to the physical Citizen CL-E300 in raw-ZPL mode from both windows; print to any
  Windows-driver-installed printer in driver mode from both windows; confirm rotate toggles
  orientation correctly on the physical printer.

## Files touched

- `shopify_tool/label_printing.py` — new
- `gui/pdf_printing.py` — new (dispatcher + shared print-settings helpers)
- `gui/barcode_generator_widget.py` — printing controls in Options, Print/Print-QR buttons,
  `last_barcode_pdf`/`last_qr_pdf` tracking
- `gui/reference_labels_widget.py` — Print button, `last_output_pdf` tracking
- `requirements.txt` — `pypdfium2`, `zebrafy`, `pywin32` (Windows-only)
- `tests/test_label_printing.py` — new
- `tests/test_pdf_printing.py` — new
- `tests/test_barcode_generator_widget.py` — extended
- `tests/test_reference_labels_widget.py` — new or extended

## Follow-ups (not in this spec's scope)

- Reference Labels' Processing History removal + Code-128 reference-number overlay (rest of
  the original D-2 design) — separate spec if/when picked up.
- A `win32print.EnumPrinters()`-backed dropdown for the raw ZPL target, if the free-text field
  proves error-prone in practice for warehouse staff.
- Threaded printing, if a large batch's synchronous render+spool is ever reported as a
  noticeable UI freeze (see ponytail note under Non-goals).
