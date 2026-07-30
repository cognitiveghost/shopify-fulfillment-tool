# Label & Barcode System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four Phase 4 backlog items (Reference Labels cleanup + Reference-Number barcode, Barcode Generator cleanup, Code-128 label redesign, optional QR labels) with in-app printing for both windows.

**Architecture:** One new shared helper (`gui/pdf_printing.py`) renders any existing PDF to a user-picked printer via `QtPdf` + `QtPrintSupport`, consumed by both windows. `barcode_processor.py`'s Code-128 rendering is factored into a reusable `render_code128_barcode()` so `pdf_processor.py`'s new Reference-Number overlay uses the same barcode drawing code instead of a second implementation. The optional QR feature is a fully separate PDF (`generate_qr_labels_pdf()`, vector-drawn via `reportlab.graphics`, never combined onto the Code-128 label) to avoid warehouse scanners picking up the wrong code from two adjacent labels. Two small dead-code removals (`reference_labels_history.py`, `barcode_history.py`) ride along since they're directly superseded/adjacent to what's being touched.

**Tech Stack:** Python, PySide6 (Qt: `QtWidgets`, `QtPdf`, `QtPrintSupport`), `reportlab` (`pdfgen.canvas`, `graphics.barcode.qr`, `graphics.renderPDF`), `pypdf`, `python-barcode`, `Pillow`, pytest + pytest-qt, ruff. No new dependencies.

## Global Constraints

- Tests run via `QT_QPA_PLATFORM=offscreen python -m pytest` (headless Qt).
- Lint via `ruff check . --exclude shared` must pass before merge.
- Never hand-edit anything under `shared/` — none of this plan's files are under `shared/`.
- No hardcoded colors in stylesheets — not applicable (no new stylesheets; existing `get_theme_manager()` usage is untouched by this plan).
- No UI calls from background threads — `print_pdf()` (Task 1) is called directly from a button click on the main thread, never from a `Worker`. QR-label generation (Task 11) runs synchronously on the main thread inside `_on_generation_complete()` (the `Worker`'s `result` signal handler), the same place `_generate_pdf_from_results()` already composites the Code-128 PDF today — not inside the background `Worker` itself. This matches the existing codebase pattern (PDF compositing has always run there, not in the worker thread) rather than introducing a new one.
- `reportlab`'s raster backend (`renderPM`) is **not usable** in this environment — it needs `rlPyCairo` or a compiled extension that isn't installed. Do not use `renderPM.drawToPIL()`/`drawToPMCanvas()` anywhere in this plan; QR rendering uses the vector path (`reportlab.graphics.renderPDF.draw()`) instead, verified working with zero new dependencies.
- No QR/barcode decode library is available in this repo's dependencies — tests that need to verify encoded payload content assert on the encoder's own input (`QrCodeWidget.value`, or the sanitized string passed to `Code128(...)`), not a round-trip decode.
- No version bump — this repo only bumps `__version__` at release time (confirmed against Phase 1/3's merged PRs, neither touched version strings).

---

## File Structure

| File | Responsibility in this plan |
|---|---|
| `gui/pdf_printing.py` (new) | `print_pdf()` + `_render_pdf_to_printer()` — shared print-to-printer helper (Task 1) |
| `shopify_tool/barcode_processor.py` | `render_code128_barcode()` extraction (Task 2); redesigned `generate_barcode_label()` layout (Task 9); new `generate_qr_labels_pdf()` (Task 10) |
| `shopify_tool/pdf_processor.py` | Reference-Number barcode overlay + page-shrink transform (Task 3) |
| `gui/reference_labels_widget.py` | Remove Processing History UI (Task 4); add Print button (Task 5) |
| `shopify_tool/reference_labels_history.py` | Deleted (Task 4) |
| `gui/barcode_generator_widget.py` | Strip clutter, PDF-only (Task 6); add auto-open-PDF checkbox + Print button (Task 8); wire "Add QR labels" + Print QR button (Task 11) |
| `shopify_tool/barcode_history.py` | Deleted (Task 7) |
| `shopify_tool/session_manager.py` | Remove `get_barcode_history_file()` (Task 7) |
| `tests/test_pdf_printing.py` (new) | Task 1 tests |
| `tests/test_barcode_processor.py` | Task 2, 9, 10 tests |
| `tests/test_pdf_processor.py` (new) | Task 3 tests |
| `tests/test_reference_labels_widget.py` (new) | Task 4, 5 tests |
| `tests/test_barcode_generator_widget.py` (new) | Task 6, 8, 11 tests |
| `tests/test_session_manager.py` | Task 7 test |

Tasks are ordered so Task 1 (print helper) and Task 2 (barcode extraction) land before anything that consumes them; each task is independently testable/committable.

---

### Task 1: `gui/pdf_printing.py` — print-to-printer helper

**Files:**
- Create: `gui/pdf_printing.py`
- Test: `tests/test_pdf_printing.py` (new)

**Interfaces:**
- Produces: `print_pdf(parent: QWidget, pdf_path: Path | str) -> bool` — opens a native printer-selection dialog; returns `True` if the user confirmed and the job rendered, `False` if they cancelled. Shows a `QMessageBox` on render failure.
- Produces (module-private, used by the test): `_render_pdf_to_printer(pdf_path: Path | str, printer: QPrinter) -> None` — raises `RuntimeError` on failure.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf_printing.py`:

```python
"""Tests for gui.pdf_printing's PDF-to-printer rendering.

print_pdf() itself pops a native QPrintDialog, which can't be driven
headlessly -- so these tests cover _render_pdf_to_printer(), the
dialog-free rendering core, by pointing a QPrinter at PdfFormat output
(no real OS printer needed) and checking the result.
"""
from pathlib import Path

import pytest
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from gui.pdf_printing import _render_pdf_to_printer


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_pdf(path: Path, page_count: int = 1) -> None:
    c = canvas.Canvas(str(path), pagesize=(68 * mm, 38 * mm))
    for i in range(page_count):
        c.drawString(10, 10, f"page {i}")
        c.showPage()
    c.save()


def _pdf_format_printer(output_path: Path) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output_path))
    return printer


def test_renders_every_page(qapp, tmp_path):
    pdf_path = tmp_path / "in.pdf"
    _make_pdf(pdf_path, page_count=3)
    out_path = tmp_path / "out.pdf"
    printer = _pdf_format_printer(out_path)

    _render_pdf_to_printer(pdf_path, printer)

    assert len(PdfReader(out_path).pages) == 3


def test_raises_on_missing_file(qapp, tmp_path):
    printer = _pdf_format_printer(tmp_path / "out.pdf")

    with pytest.raises(RuntimeError):
        _render_pdf_to_printer(tmp_path / "does-not-exist.pdf", printer)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.pdf_printing'`

- [ ] **Step 3: Implement**

Create `gui/pdf_printing.py`:

```python
"""Print an existing PDF file via a native printer-selection dialog.

Shared by gui/reference_labels_widget.py and gui/barcode_generator_widget.py
-- both windows generate a PDF and need "print it, with a printer picker"
without leaving the app. Uses PySide6's QtPdf (to load/rasterize pages) and
QtPrintSupport (native printer dialog + QPrinter) -- both ship with the
already-installed PySide6, no new dependency.
"""
import logging
from pathlib import Path

from PySide6.QtGui import QPageSize, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

logger = logging.getLogger(__name__)


def _render_pdf_to_printer(pdf_path: Path | str, printer: QPrinter) -> None:
    """Render every page of pdf_path onto printer.

    Raises:
        RuntimeError: If the PDF can't be loaded or the print job can't start.
    """
    doc = QPdfDocument()
    if doc.load(str(pdf_path)) != QPdfDocument.Error.None_:
        raise RuntimeError(f"Could not load PDF for printing: {pdf_path}")

    first_page_size = doc.pagePointSize(0)
    printer.setPageSize(QPageSize(first_page_size, QPageSize.Unit.Point))
    printer.setFullPage(True)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Could not start print job")

    try:
        for page_index in range(doc.pageCount()):
            if page_index > 0:
                printer.newPage()
            page_pt_size = doc.pagePointSize(page_index)
            dpi = printer.resolution()
            image_size = (page_pt_size * (dpi / 72.0)).toSize()
            image = doc.render(page_index, image_size)
            painter.drawImage(0, 0, image)
    finally:
        painter.end()


def print_pdf(parent: QWidget, pdf_path: Path | str) -> bool:
    """Print every page of pdf_path via a native printer-selection dialog.

    Returns:
        True if the user confirmed the dialog and the job rendered.
        False if they cancelled. Shows a QMessageBox on render failure.
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False

    try:
        _render_pdf_to_printer(pdf_path, printer)
    except Exception:
        logger.exception(f"Failed to print {pdf_path}")
        QMessageBox.critical(
            parent,
            "Print Error",
            f"Failed to print:\n{pdf_path}\n\nSee execution log for details.",
        )
        return False

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/pdf_printing.py tests/test_pdf_printing.py
git add gui/pdf_printing.py tests/test_pdf_printing.py
git commit -m "Add gui.pdf_printing.print_pdf shared printer-selection helper"
```

---

### Task 2: Extract `barcode_processor.render_code128_barcode()`

**Why this task is required:** Task 3 (Reference-Number barcode overlay) needs to draw a Code-128 barcode from `pdf_processor.py`. Rather than a second copy of the barcode-rendering steps currently inlined in `generate_barcode_label()`, extract them into a reusable function both modules call.

**Files:**
- Modify: `shopify_tool/barcode_processor.py:285-314` (inside `generate_barcode_label()`)
- Test: `tests/test_barcode_processor.py`

**Interfaces:**
- Produces: `render_code128_barcode(data: str) -> Image.Image` — renders a Code-128 barcode as a PIL Image, no text, no quiet zone, cropped to strip auto-generated text. No behavior change from what `generate_barcode_label()` did inline.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_barcode_processor.py`, after the imports (add `render_code128_barcode` to the existing `from shopify_tool.barcode_processor import (...)` block) and before `class TestSanitizeOrderNumber:`:

```python
from shopify_tool.barcode_processor import (
    InvalidOrderNumberError,
    _clamp_text_to_width,
    format_tags_for_barcode,
    generate_barcode_label,
    generate_barcodes_batch,
    load_font,
    render_code128_barcode,
    sanitize_order_number,
)


class TestRenderCode128Barcode:
    def test_returns_a_nonempty_image(self):
        img = render_code128_barcode("ORDER-001234")
        assert img.width > 0
        assert img.height > 0

    def test_different_data_produces_different_images(self):
        img_a = render_code128_barcode("AAAA")
        img_b = render_code128_barcode("ZZZZZZZZ")
        assert img_a.size != img_b.size  # different code lengths -> different rendered width
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py::TestRenderCode128Barcode -v`
Expected: FAIL with `ImportError: cannot import name 'render_code128_barcode'`

- [ ] **Step 3: Implement**

In `shopify_tool/barcode_processor.py`, add a new function after `format_tags_for_barcode()` (before the `# === MAIN BARCODE GENERATION FUNCTIONS ===` comment, currently line 220):

```python
def render_code128_barcode(data: str) -> Image.Image:
    """Render a Code-128 barcode as a PIL Image, no text, no quiet zone.

    Shared by generate_barcode_label() (order-number barcode) and
    pdf_processor.create_reference_overlay() (reference-number barcode) so
    both label types render barcodes identically.
    """
    writer = ImageWriter()
    writer.set_options({
        'module_width': 0.35,    # Bar width (mm) - increased for better scanning
        'module_height': 20.0,   # Bar height (mm) - increased for taller barcode
        'dpi': DPI,
        'quiet_zone': 0,         # No quiet zone (we add manually)
        'write_text': False,     # We add text manually
        'text': '',              # Empty text to avoid font loading
        'font_size': 0,          # Zero font size to skip font initialization
    })

    barcode_instance = Code128(data, writer=writer)

    barcode_buffer = io.BytesIO()
    barcode_instance.write(barcode_buffer)
    barcode_buffer.seek(0)

    barcode_img = Image.open(barcode_buffer)

    # CRITICAL: Crop bottom part to remove text added by barcode library
    # Even with write_text=False, some versions add text anyway
    width, height = barcode_img.size
    return barcode_img.crop((0, 0, width, int(height * 0.75)))
```

Then replace the `# === STEP 2: Generate Code-128 barcode ===` block inside `generate_barcode_label()` (lines 285-314) with:

```python
        # === STEP 2: Generate Code-128 barcode ===
        barcode_img = render_code128_barcode(safe_order_number)
```

(Everything from `# === STEP 3: Create label canvas ===` onward is unchanged — it already references `barcode_img`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -v`
Expected: PASS (all tests, including the pre-existing `TestGenerateBarcodeLabelIntegration` tests — same rendering steps, just relocated)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git add shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git commit -m "Extract barcode_processor.render_code128_barcode for reuse by pdf_processor"
```

---

### Task 3: Reference-Number barcode overlay in `pdf_processor.py`

**Files:**
- Modify: `shopify_tool/pdf_processor.py:169-189` (`process_reference_labels()` merge loop), `shopify_tool/pdf_processor.py:525-569` (`create_reference_overlay()`)
- Test: `tests/test_pdf_processor.py` (new)

**Interfaces:**
- Consumes: `barcode_processor.render_code128_barcode(data: str) -> Image.Image` (Task 2), `barcode_processor.sanitize_order_number(order_number: str) -> str` (existing).
- Produces: no new public function — `create_reference_overlay()`'s signature is unchanged, its output now also includes a barcode.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf_processor.py`:

```python
"""Tests for pdf_processor's Reference-Number barcode overlay.

Reference Labels has no Shopify order number anywhere in its pipeline --
it matches courier PDF pages to a Reference Number via CSV (PostOne ID /
Tracking / Client Name). The new barcode on each processed page encodes
that Reference Number (the only per-shipment identifier available here),
placed in a bottom strip alongside the existing "REF: X" text, with the
original page content shrunk slightly (via a pypdf scale+translate
transform) to make room -- not resized, so output pages stay the same
physical size as the input courier labels.
"""
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from shopify_tool.pdf_processor import create_reference_overlay, process_reference_labels

PAGE_WIDTH = 100 * mm
PAGE_HEIGHT = 150 * mm


def _make_courier_pdf(path: Path, pages: list[str]) -> None:
    """One page per string in `pages`; drawn as plain text (like a real
    courier label would have the tracking/PostOne text somewhere on it)."""
    c = canvas.Canvas(str(path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    for text in pages:
        c.drawString(20, PAGE_HEIGHT - 40, text)
        c.showPage()
    c.save()


def _make_mapping_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (postone_id, tracking, ref, name) -- matches load_csv_mapping's
    expected columns 0/1/2/6."""
    lines = ["header0,header1,header2,header3,header4,header5,header6"]
    for postone_id, tracking, ref, name in rows:
        lines.append(f"{postone_id},{tracking},{ref},,,,{name}")
    path.write_text("\n".join(lines), encoding="utf-8")


class TestCreateReferenceOverlay:
    def test_overlay_page_has_same_size_as_input(self):
        overlay = create_reference_overlay("REF123", 1, PAGE_WIDTH, PAGE_HEIGHT)
        overlay_page = PdfReader(overlay).pages[0]
        assert float(overlay_page.mediabox.width) == pytest.approx(PAGE_WIDTH)
        assert float(overlay_page.mediabox.height) == pytest.approx(PAGE_HEIGHT)

    def test_overlay_still_contains_ref_text(self):
        overlay = create_reference_overlay("REF123", 1, PAGE_WIDTH, PAGE_HEIGHT)
        overlay_page = PdfReader(overlay).pages[0]
        text = overlay_page.extract_text()
        assert "REF: REF123" in text


class TestProcessReferenceLabelsBarcodeOverlay:
    def test_matched_page_keeps_original_mediabox_after_shrink_and_merge(self, tmp_path):
        pdf_path = tmp_path / "labels.pdf"
        _make_courier_pdf(pdf_path, ["Shipment for R1234567890"])
        csv_path = tmp_path / "mapping.csv"
        _make_mapping_csv(csv_path, [("R1234567890", "TRACK1", "REF001", "Client A")])

        result = process_reference_labels(str(pdf_path), str(csv_path), str(tmp_path))

        assert result["matched"] == 1
        output = Path(result["output_file"])
        reader = PdfReader(output)
        assert len(reader.pages) == 1
        page = reader.pages[0]
        # Page-shrink uses add_transformation (expand=False) -- physical
        # page size (mediabox) must be unchanged even though the original
        # content is now drawn smaller within it.
        assert float(page.mediabox.width) == pytest.approx(PAGE_WIDTH)
        assert float(page.mediabox.height) == pytest.approx(PAGE_HEIGHT)

    def test_unmatched_page_is_untouched(self, tmp_path):
        pdf_path = tmp_path / "labels.pdf"
        _make_courier_pdf(pdf_path, ["No matching identifiers here"])
        csv_path = tmp_path / "mapping.csv"
        _make_mapping_csv(csv_path, [("R1234567890", "TRACK1", "REF001", "Client A")])

        result = process_reference_labels(str(pdf_path), str(csv_path), str(tmp_path))

        assert result["matched"] == 0
        assert result["unmatched"] == 1
        output = Path(result["output_file"])
        page = PdfReader(output).pages[0]
        assert float(page.mediabox.height) == pytest.approx(PAGE_HEIGHT)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v`
Expected: `test_overlay_page_has_same_size_as_input` and `test_overlay_still_contains_ref_text` PASS already (overlay creation itself isn't new). `test_matched_page_keeps_original_mediabox_after_shrink_and_merge` PASSES too at this point (mediabox is already unchanged today, since no shrink transform exists yet) — this test's real purpose is to lock in the *invariant* before the shrink logic is added; re-run after Step 3 to confirm it still holds. The behavior actually being added (barcode in the overlay) has no dedicated assertion yet because there's no barcode-decode library available (see Global Constraints) — Step 3 below implements it and Step 4 re-confirms nothing broke.

- [ ] **Step 3: Implement**

In `shopify_tool/pdf_processor.py`, replace the existing two-line `from pypdf import PdfReader, PdfWriter` / `from reportlab.pdfgen import canvas` import block with:

```python
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from shopify_tool.barcode_processor import render_code128_barcode, sanitize_order_number
```

Add a module-level constant near the top, after the exception classes:

```python
# Height (in points) reserved at the bottom of each matched page for the
# new Reference-Number barcode + existing REF/order text. Original page
# content is shrunk (not resized) to make room -- see process_reference_labels.
REF_BARCODE_STRIP_HEIGHT = 30
```

Replace `create_reference_overlay()` (lines 525-569) to add the barcode:

```python
def create_reference_overlay(
    reference_number: str,
    order_number: int,
    page_width: float,
    page_height: float
) -> BytesIO:
    """
    Create PDF overlay with reference number, order number, and a small
    Code-128 barcode encoding the reference number.

    Format: barcode row above "[order_number]. REF: [reference_number]"
    Position: Bottom strip, REF_BARCODE_STRIP_HEIGHT points tall. The
    barcode sits in its own row above the text row (not beside it) so the
    two never collide horizontally -- the REF text's x position is fixed
    and its length varies with the reference number, and real courier
    labels (commonly ~4x6in, ~288-432pt wide) don't reliably leave enough
    spare width beside that text for a barcode too.

    Args:
        reference_number: Reference number to display and encode
        order_number: Order number to display
        page_width: Page width in points
        page_height: Page height in points

    Returns:
        BytesIO: PDF overlay buffer
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # Small Code-128 barcode encoding the reference number, top row of the
    # strip -- reuses the same barcode rendering as the order-number
    # barcode (barcode_processor.render_code128_barcode), not a second
    # implementation.
    safe_ref = sanitize_order_number(reference_number)
    barcode_img = render_code128_barcode(safe_ref)
    barcode_reader = ImageReader(barcode_img)
    barcode_draw_width = 120
    barcode_draw_height = 14
    x_barcode = 10
    y_barcode = REF_BARCODE_STRIP_HEIGHT - barcode_draw_height - 2
    can.drawImage(
        barcode_reader, x_barcode, y_barcode,
        width=barcode_draw_width, height=barcode_draw_height,
        preserveAspectRatio=True, mask='auto',
    )

    # Fixed position for REF (never moves), bottom row of the strip
    x_ref = 200
    y_bottom = 3
    can.setFont("Helvetica-Bold", 10)

    # Draw REF text
    ref_text = f"REF: {reference_number}"
    can.drawString(x_ref, y_bottom, ref_text)

    # Calculate order number position (to the LEFT of REF)
    order_text = f"{order_number}."
    order_width = can.stringWidth(order_text, "Helvetica-Bold", 10)

    # Position order number to the left of REF (with 5 units spacing)
    x_order = x_ref - order_width - 5
    can.drawString(x_order, y_bottom, order_text)

    can.save()
    packet.seek(0)

    return packet
```

Replace the merge loop in `process_reference_labels()` (lines 169-189) to shrink the original page before merging:

```python
        for page_data in sorted_pages:
            page = page_data['page']
            ref = page_data['ref']

            if ref:
                ref_order_num = ref_order_map[ref]

                try:
                    page_height = float(page.mediabox.height)

                    # Add reference overlay (includes the new barcode)
                    overlay = create_reference_overlay(
                        ref,
                        ref_order_num,
                        float(page.mediabox.width),
                        page_height
                    )

                    # Shrink the original page content to make room for the
                    # overlay's bottom strip. Uses add_transformation
                    # (expand=False) so the page's physical mediabox is
                    # unchanged -- only the content within it is scaled and
                    # shifted up, matching "shrink label slightly to fit"
                    # rather than growing the printed page size.
                    scale_y = (page_height - REF_BARCODE_STRIP_HEIGHT) / page_height
                    page.add_transformation(
                        Transformation().scale(sx=1, sy=scale_y).translate(tx=0, ty=REF_BARCODE_STRIP_HEIGHT)
                    )

                    page.merge_page(PdfReader(overlay).pages[0])

                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}")

            writer.add_page(page)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v`
Expected: PASS (all tests)

Also re-run the full barcode/pdf suite to confirm the import of `barcode_processor` into `pdf_processor` didn't introduce a circular import:

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py tests/test_pdf_processor.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/pdf_processor.py tests/test_pdf_processor.py
git add shopify_tool/pdf_processor.py tests/test_pdf_processor.py
git commit -m "Add Reference-Number barcode overlay to processed Reference Labels pages"
```

---

### Task 4: Remove Reference Labels' Processing History

**Files:**
- Modify: `gui/reference_labels_widget.py`
- Delete: `shopify_tool/reference_labels_history.py`
- Test: `tests/test_reference_labels_widget.py` (new)

**Interfaces:**
- Produces: `ReferenceLabelsWidget` no longer has `history_table`, `history`, `_create_history_group()`, `_load_history()`, `_clear_history()`, `_open_history_item()` attributes/methods; no longer writes `reference_labels_history.json`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reference_labels_widget.py`:

```python
"""Tests for ReferenceLabelsWidget's window structure after removing the
Processing History UI/backend (Task 4) and adding the Print button (Task 5).

Uses a SimpleNamespace fake main_window, matching this codebase's
established pattern for widget tests (see test_client_sidebar_refresh.py,
test_session_setup_layout.py) rather than constructing the real MainWindow.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.reference_labels_widget import ReferenceLabelsWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fake_mw(tmp_path):
    session_manager = Mock()
    session_manager.get_reference_labels_dir.return_value = tmp_path
    return SimpleNamespace(session_path=str(tmp_path), session_manager=session_manager)


@pytest.fixture
def widget(qapp, fake_mw):
    w = ReferenceLabelsWidget(fake_mw)
    yield w
    w.deleteLater()


def test_history_ui_is_gone(widget):
    assert not hasattr(widget, "history_table")
    assert not hasattr(widget, "history")


def test_no_history_json_written_after_processing(widget, tmp_path, monkeypatch):
    # _on_processing_complete unconditionally shows a QMessageBox.information
    # on success -- must be patched, or QDialog.exec() blocks forever with no
    # real user to dismiss it (this codebase's established pattern, see
    # test_actions_handler.py's QMessageBox.question patches).
    monkeypatch.setattr("gui.reference_labels_widget.QMessageBox.information", lambda *a, **k: None)

    result = {
        "output_file": str(tmp_path / "out.pdf"),
        "pages_processed": 1,
        "matched": 1,
        "unmatched": 0,
        "processing_time": 0.1,
    }
    (tmp_path / "out.pdf").touch()

    widget.auto_open_checkbox.setChecked(False)  # avoid launching a real app to open the PDF
    widget._on_processing_complete(result)

    assert not (tmp_path / "reference_labels_history.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -v`
Expected: FAIL — `test_history_ui_is_gone` fails (`hasattr(widget, "history_table")` is `True` today). `test_no_history_json_written_after_processing` also fails: today's `_update_output_dir()` still constructs a real `ReferenceLabelsHistory(self.output_dir)`, and `_on_processing_complete()` still calls `self.history.add_entry(...)`, which writes `reference_labels_history.json` to `tmp_path` — so the final `assert not (...).exists()` fails.

- [ ] **Step 3: Implement**

In `gui/reference_labels_widget.py`:

Delete the import (line 35):
```python
from shopify_tool.reference_labels_history import ReferenceLabelsHistory
```

Delete the `# History manager` block in `__init__` (line 64-65):
```python
        # History manager
        self.history = None
```

In `_init_ui()`, delete the history section line (line 90):
```python
        # Section 4: History
        layout.addWidget(self._create_history_group(), 1)  # Stretch
```

Delete the entire `_create_history_group()` method (lines 179-232).

In `_connect_signals()`, delete the history double-click connection (line 240):
```python
        self.history_table.doubleClicked.connect(self._open_history_item)
```

In `_update_output_dir()`, delete the history-manager initialization block (lines 341-343):
```python
            # Initialize history manager
            self.history = ReferenceLabelsHistory(self.output_dir)
            self._load_history()
```

In `_on_processing_complete()`, delete the "Add to history" block (lines 488-499):
```python
        # Add to history
        if self.history:
            self.history.add_entry(
                input_pdf=Path(self.pdf_path).name,
                input_csv=Path(self.csv_path).name,
                output_pdf=Path(result['output_file']).name,
                pages_processed=result['pages_processed'],
                matched=result['matched'],
                unmatched=result['unmatched'],
                processing_time=result['processing_time']
            )
            self._load_history()
```

Delete the entire `_load_history()`, `_clear_history()`, and `_open_history_item()` methods (lines 576-670).

- [ ] **Step 4: Delete the backend module**

```bash
git rm shopify_tool/reference_labels_history.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Lint and commit**

```bash
ruff check gui/reference_labels_widget.py tests/test_reference_labels_widget.py
git add gui/reference_labels_widget.py tests/test_reference_labels_widget.py
git commit -m "Remove Reference Labels processing history UI and backend"
```

---

### Task 5: Add Print button to Reference Labels window

**Files:**
- Modify: `gui/reference_labels_widget.py`
- Test: `tests/test_reference_labels_widget.py`

**Interfaces:**
- Consumes: `gui.pdf_printing.print_pdf(parent: QWidget, pdf_path) -> bool` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reference_labels_widget.py`:

```python
def test_print_button_disabled_until_a_pdf_has_been_processed(widget):
    assert widget.print_btn.isEnabled() is False


def test_print_button_enabled_after_processing_completes(widget, tmp_path, monkeypatch):
    monkeypatch.setattr("gui.reference_labels_widget.QMessageBox.information", lambda *a, **k: None)
    widget.auto_open_checkbox.setChecked(False)
    output_file = tmp_path / "out.pdf"
    output_file.touch()

    widget._on_processing_complete({
        "output_file": str(output_file),
        "pages_processed": 1, "matched": 1, "unmatched": 0, "processing_time": 0.1,
    })

    assert widget.print_btn.isEnabled() is True
    assert widget.last_output_pdf == output_file


def test_print_button_click_calls_print_pdf_with_last_output(widget, tmp_path, monkeypatch):
    output_file = tmp_path / "out.pdf"
    widget.last_output_pdf = output_file
    widget.print_btn.setEnabled(True)

    captured = {}
    monkeypatch.setattr(
        "gui.reference_labels_widget.print_pdf",
        lambda parent, pdf_path: captured.update(parent=parent, pdf_path=pdf_path) or True,
    )

    widget._on_print_clicked()

    assert captured["pdf_path"] == output_file
    assert captured["parent"] is widget
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -k print -v`
Expected: FAIL — `widget.print_btn` doesn't exist (`AttributeError`)

- [ ] **Step 3: Implement**

In `gui/reference_labels_widget.py`, add the import (alongside the existing `from shopify_tool.reference_labels_history import ...` line removed in Task 4 — add this in its place):

```python
from gui.pdf_printing import print_pdf
```

In `__init__`, add tracking for the last processed PDF (next to the `self.output_dir = None` line):

```python
        # Last processed PDF (in-memory only, no history file -- see Task 4)
        self.last_output_pdf: Path | None = None
```

In `_create_processing_group()`, add a Print button after `self.process_btn` is added to the layout:

```python
        # Process button
        self.process_btn = QPushButton("Process Labels")
        self.process_btn.setMinimumHeight(50)
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip("Process PDF with reference numbers")
        layout.addWidget(self.process_btn)

        # Print button (enabled once a PDF has been processed)
        self.print_btn = QPushButton("Print...")
        self.print_btn.setEnabled(False)
        self.print_btn.setToolTip("Print the processed PDF with a printer picker")
        layout.addWidget(self.print_btn)
```

In `_connect_signals()`, wire the button:

```python
        self.print_btn.clicked.connect(self._on_print_clicked)
```

In `_on_processing_complete()`, after `self.processing_complete.emit(result)` at the end of the method, add:

```python
        self.last_output_pdf = Path(result['output_file'])
        self.print_btn.setEnabled(True)
```

Add a new method after `_on_processing_finished()`:

```python
    def _on_print_clicked(self):
        """Print the last processed PDF via a printer-selection dialog."""
        if not self.last_output_pdf:
            return
        print_pdf(self, self.last_output_pdf)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/reference_labels_widget.py tests/test_reference_labels_widget.py
git add gui/reference_labels_widget.py tests/test_reference_labels_widget.py
git commit -m "Add Print button to Reference Labels window"
```

---

### Task 6: Strip clutter from Barcode Generator window (PDF-only)

**Files:**
- Modify: `gui/barcode_generator_widget.py`
- Test: `tests/test_barcode_generator_widget.py` (new)

**Interfaces:**
- Produces: `BarcodeGeneratorWidget` no longer has `generate_png_checkbox`, `generate_pdf_checkbox`, `auto_open_folder_checkbox`, or the "Barcodes will be generated for..." info label. Barcode generation is always PDF-only (PNGs still generated internally, always cleaned up after).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_barcode_generator_widget.py`:

```python
"""Tests for BarcodeGeneratorWidget after removing format-choice clutter
(Task 6), adding auto-open-PDF + Print (Task 8), and wiring optional QR
labels (Task 11).

Uses a SimpleNamespace fake main_window, matching this codebase's
established widget-test pattern (see test_reference_labels_widget.py).
"""
from types import SimpleNamespace

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.barcode_generator_widget import BarcodeGeneratorWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fake_mw(tmp_path):
    return SimpleNamespace(session_path=str(tmp_path), analysis_results_df=None)


@pytest.fixture
def widget(qapp, fake_mw):
    w = BarcodeGeneratorWidget(fake_mw)
    yield w
    w.deleteLater()


def test_format_choice_and_info_clutter_removed(widget):
    assert not hasattr(widget, "generate_png_checkbox")
    assert not hasattr(widget, "generate_pdf_checkbox")
    assert not hasattr(widget, "auto_open_folder_checkbox")
    assert not hasattr(widget, "order_count_label") or "Barcodes will be generated" not in (
        getattr(widget, "info_label", None) and widget.info_label.text() or ""
    )


def _successful_results(tmp_path, n=2):
    results = []
    for i in range(n):
        f = tmp_path / f"order{i}.png"
        f.touch()
        results.append({"success": True, "file_path": f, "order_number": f"#{i}"})
    return results


def test_generation_complete_always_builds_pdf_and_cleans_up_pngs(widget, tmp_path, monkeypatch):
    widget.barcodes_dir = tmp_path
    widget.current_packing_list = "DHL_Orders"

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr("gui.barcode_generator_widget.QDesktopServices.openUrl", lambda *a, **k: True)

    captured = {}
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_barcodes_pdf",
        lambda barcode_files, pdf_path: captured.update(pdf_path=pdf_path) or pdf_path,
    )

    results = _successful_results(tmp_path)
    widget._on_generation_complete(results)

    assert captured["pdf_path"] == tmp_path / "DHL_Orders_barcodes.pdf"
    assert not any(f.exists() for f in [tmp_path / "order0.png", tmp_path / "order1.png"])
```

**Note:** this test deliberately does not touch `add_qr_checkbox` — that widget doesn't exist until Task 11, and at this point in the plan `_on_generation_complete()` doesn't reference it either. Running the full test file at this stage will show failures for the not-yet-implemented Task 8/11 tests later in the same file (`print_btn`, `add_qr_checkbox`, etc. don't exist yet) — that's expected; only this task's own tests need to be green after this task's implementation.

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k "clutter or generation_complete" -v`
Expected: FAIL — `test_format_choice_and_info_clutter_removed` fails because `generate_png_checkbox` etc. still exist; `test_generation_complete_always_builds_pdf_and_cleans_up_pngs` fails because `generate_barcodes_pdf` isn't yet monkeypatchable at `gui.barcode_generator_widget.generate_barcodes_pdf` (still a local import).

- [ ] **Step 3: Implement**

In `gui/barcode_generator_widget.py`:

Add a module-level import (alongside the existing `from gui.worker import Worker` line) — this replaces the local `from shopify_tool.barcode_processor import generate_barcodes_pdf` import currently inside `_generate_pdf_from_results()`, so the function is patchable as `gui.barcode_generator_widget.generate_barcodes_pdf` in tests, consistent with how Task 10/11 import `generate_qr_labels_pdf`:

```python
from shopify_tool.barcode_processor import generate_barcodes_pdf
```

Replace `_create_packing_list_section()`'s trailing info label block (lines 108-115) — delete it entirely:

```python
        # Info label
        info_label = QLabel(
            "Barcodes will be generated for all Fulfillable orders in the selected packing list.\n"
            "Each packing list has its own barcode folder for organization."
        )
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
```

Replace `_create_options_section()` (lines 119-154) entirely — drops the format checkboxes and auto-open-folder checkbox, keeps the output directory row (auto-open-PDF checkbox and QR checkbox are added in Tasks 8/11):

```python
    def _create_options_section(self):
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Output directory label
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output:"))
        self.output_dir_label = QLabel("No packing list selected")
        theme = get_theme_manager().get_current_theme()
        self.output_dir_label.setStyleSheet(f"font-weight: bold; color: {theme.text_secondary};")
        self.output_dir_label.setWordWrap(True)
        output_row.addWidget(self.output_dir_label, 1)
        layout.addLayout(output_row)

        return group
```

Replace `_on_generate_clicked()` (lines 333-374) — drops format validation, hardcodes "PDF" in the confirmation message:

```python
    def _on_generate_clicked(self):
        """Handle generate button click."""
        if self.filtered_orders_df is None or len(self.filtered_orders_df) == 0:
            QMessageBox.warning(
                self,
                "No Orders",
                "No orders available for barcode generation."
            )
            return

        order_count = self.filtered_orders_df['Order_Number'].nunique()

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output Format: PDF\n"
            f"Output: {self.barcodes_dir}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return
```

Replace `_on_generation_complete()` (lines 438-491) — always builds the PDF, always cleans up PNGs, drops the removed folder-auto-open checkbox reference entirely (Task 8 adds its PDF-auto-open replacement elsewhere, inside `_generate_pdf_from_results()`, not here):

```python
    def _on_generation_complete(self, results):
        """Handle successful generation."""
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        # Reset progress bar to normal mode and set to 100%
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"Complete: {len(successful)} barcodes generated"
        )
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.log.info(
            f"Barcode generation complete: {len(successful)} successful, "
            f"{len(failed)} failed"
        )

        if successful:
            self._generate_pdf_from_results(successful)
            self._cleanup_png_files(successful)

        message = f"Successfully generated {len(successful)} barcode labels as a PDF document."
        if failed:
            message += f"\n\n{len(failed)} barcodes failed to generate."

        QMessageBox.information(self, "Generation Complete", message)

        # Emit signal
        self.generation_complete.emit({
            'packing_list': self.current_packing_list,
            'successful': len(successful),
            'failed': len(failed),
            'total': len(results)
        })
```

Delete the now-unused `_open_barcodes_folder()` method (lines 559-572) — it only existed to serve the removed auto-open-folder checkbox.

In `_generate_pdf_from_results()` (lines 513-538), remove the unconditional auto-open (Task 8 re-adds it gated by a checkbox):

```python
    def _generate_pdf_from_results(self, results):
        """Generate PDF automatically after barcode generation."""
        try:
            # Convert string paths back to Path objects
            barcode_files = [Path(r['file_path']) for r in results if r.get('file_path')]

            if not barcode_files:
                return

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_barcodes_pdf(barcode_files, pdf_path)

            self.log.info(f"Auto-generated PDF: {pdf_path}")

        except Exception:
            self.log.exception("Auto PDF generation failed")
```

(`generate_barcodes_pdf` is now the module-level import added above, and `Path` is already imported at the top of this file — dropping both local imports that used to live inside this `try` block.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k "clutter or generation_complete" -v`
Expected: `test_format_choice_and_info_clutter_removed` and `test_generation_complete_always_builds_pdf_and_cleans_up_pngs` PASS. (The full file's other tests are added in Tasks 8/11 and will fail until then — that's expected.)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Strip format-choice/info clutter from Barcode Generator window, PDF-only"
```

---

### Task 7: Delete dead barcode history code

**Files:**
- Delete: `shopify_tool/barcode_history.py`
- Modify: `shopify_tool/session_manager.py:631-642` (`get_barcode_history_file()`)
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_session_manager.py`:

```python
def test_get_barcode_history_file_removed_as_dead_code(profile_manager):
    """Regression test confirming this already-unused method (and its
    module, shopify_tool/barcode_history.py) stay removed -- the Barcode
    Generator widget never wired them up (its own code comment said
    "History removed - using logs only"), and nothing else called them."""
    from shopify_tool.session_manager import SessionManager
    sm = SessionManager(profile_manager.base_path)
    assert not hasattr(sm, "get_barcode_history_file")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py::test_get_barcode_history_file_removed_as_dead_code -v`
Expected: FAIL — `hasattr(sm, "get_barcode_history_file")` is `True`

- [ ] **Step 3: Implement**

In `shopify_tool/session_manager.py`, delete `get_barcode_history_file()` (lines 631-642):

```python
    def get_barcode_history_file(self, session_path: str, packing_list_name: str) -> Path:
        """
        Get path to barcode history JSON file for specific packing list.

        Args:
            session_path: Session path
            packing_list_name: Name of packing list

        Returns:
            Path: Path to barcode_history.json
        """
        return self.get_packing_list_barcode_dir(session_path, packing_list_name) / "barcode_history.json"
```

Delete the backend module:

```bash
git rm shopify_tool/barcode_history.py
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/session_manager.py tests/test_session_manager.py
git add shopify_tool/session_manager.py tests/test_session_manager.py
git commit -m "Delete unused barcode_history.py and SessionManager.get_barcode_history_file"
```

---

### Task 8: Add auto-open-PDF checkbox + Print button to Barcode Generator

**Files:**
- Modify: `gui/barcode_generator_widget.py`
- Test: `tests/test_barcode_generator_widget.py`

**Interfaces:**
- Consumes: `gui.pdf_printing.print_pdf(parent: QWidget, pdf_path) -> bool` (Task 1).
- Produces: `self.last_barcode_pdf: Path | None`, `self.auto_open_pdf_checkbox`, `self.print_btn`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_barcode_generator_widget.py`:

```python
def test_print_button_disabled_until_a_pdf_exists(widget):
    assert widget.print_btn.isEnabled() is False


def test_generation_complete_enables_print_and_tracks_last_pdf(widget, tmp_path, monkeypatch):
    widget.barcodes_dir = tmp_path
    widget.current_packing_list = "DHL_Orders"
    widget.auto_open_pdf_checkbox.setChecked(False)

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    pdf_path = tmp_path / "DHL_Orders_barcodes.pdf"
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_barcodes_pdf",
        lambda barcode_files, out_path: out_path,
    )

    widget._on_generation_complete(_successful_results(tmp_path))

    assert widget.print_btn.isEnabled() is True
    assert widget.last_barcode_pdf == pdf_path


def test_print_button_click_calls_print_pdf(widget, tmp_path, monkeypatch):
    widget.last_barcode_pdf = tmp_path / "out.pdf"
    widget.print_btn.setEnabled(True)

    captured = {}
    monkeypatch.setattr(
        "gui.barcode_generator_widget.print_pdf",
        lambda parent, pdf_path: captured.update(pdf_path=pdf_path) or True,
    )

    widget._on_print_clicked()

    assert captured["pdf_path"] == widget.last_barcode_pdf
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k print -v`
Expected: FAIL — `widget.print_btn` doesn't exist

- [ ] **Step 3: Implement**

In `gui/barcode_generator_widget.py`, add the import:

```python
from gui.pdf_printing import print_pdf
```

In `__init__`, add tracking attributes (next to `self.barcodes_dir = None`):

```python
        # Last-generated PDFs (in-memory only -- this widget never had a
        # history file). QR is set in Task 11.
        self.last_barcode_pdf: Path | None = None
        self.last_qr_pdf: Path | None = None
```

In `_create_options_section()` (rewritten in Task 6), add the auto-open checkbox before the output directory row:

```python
        # Auto-open PDF checkbox
        self.auto_open_pdf_checkbox = QCheckBox("Auto-open PDF after generation")
        self.auto_open_pdf_checkbox.setChecked(True)
        layout.addWidget(self.auto_open_pdf_checkbox)
```

In `_create_generation_section()`, add a Print button after `self.generate_btn` is added to the layout:

```python
        # Print button (enabled once a barcode PDF exists)
        self.print_btn = QPushButton("Print...")
        self.print_btn.setEnabled(False)
        self.print_btn.setToolTip("Print the barcode PDF with a printer picker")
        layout.addWidget(self.print_btn)
```

In `_connect_signals()`, wire the button:

```python
        self.print_btn.clicked.connect(self._on_print_clicked)
```

In `_generate_pdf_from_results()`, gate the auto-open behind the new checkbox and track the path:

```python
    def _generate_pdf_from_results(self, results):
        """Generate PDF automatically after barcode generation."""
        try:
            # Convert string paths back to Path objects
            barcode_files = [Path(r['file_path']) for r in results if r.get('file_path')]

            if not barcode_files:
                return

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_barcodes_pdf(barcode_files, pdf_path)

            self.log.info(f"Auto-generated PDF: {pdf_path}")

            self.last_barcode_pdf = pdf_path
            self.print_btn.setEnabled(True)

            if self.auto_open_pdf_checkbox.isChecked():
                url = QUrl.fromLocalFile(str(pdf_path))
                QDesktopServices.openUrl(url)

        except Exception:
            self.log.exception("Auto PDF generation failed")
```

(Same drop of the two local imports as Task 6 — `generate_barcodes_pdf` and `Path` are both already available at module level.)

Add a new method after `_on_generation_finished()`:

```python
    def _on_print_clicked(self):
        """Print the last-generated barcode PDF via a printer-selection dialog."""
        if not self.last_barcode_pdf:
            return
        print_pdf(self, self.last_barcode_pdf)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k "print or clutter or generation_complete" -v`
Expected: PASS (all matching tests — Task 11's QR-specific tests don't exist in the file yet at this point in the plan)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Add auto-open-PDF checkbox and Print button to Barcode Generator window"
```

---

### Task 9: Redesign Code-128 label layout (grid-aligned info column)

**Files:**
- Modify: `shopify_tool/barcode_processor.py:65-68` (font-size constants), `shopify_tool/barcode_processor.py` (`generate_barcode_label()`'s drawing section)
- Test: `tests/test_barcode_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_barcode_processor.py`, inside `TestGenerateBarcodeLabelIntegration`:

```python
    def test_redesigned_label_still_generates_at_correct_dimensions(self, tmp_path):
        """Smoke test for the Option B layout redesign (grid-aligned info
        column, consistent margins) -- not asserting pixel content (no
        pixel-diff baseline exists for this codebase's label rendering),
        just that the label still renders at the documented physical size
        with all inputs represented somewhere without raising."""
        from shopify_tool.barcode_processor import LABEL_HEIGHT_PX, LABEL_WIDTH_PX

        result = generate_barcode_label(
            order_number="#1029392",
            sequential_num=12,
            courier="DHL",
            country="DE",
            tag='["URGENT", "GIFT+1"]',
            item_count=5,
            output_dir=tmp_path,
        )
        assert result["success"] is True
        from PIL import Image
        img = Image.open(result["file_path"])
        assert img.size == (LABEL_WIDTH_PX, LABEL_HEIGHT_PX)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k redesigned_label -v`
Expected: PASS already (dimensions don't change in the redesign) — this is expected to pass before AND after Step 3; it exists as a regression guard for the redesign, not a red/green driver for it (the redesign is a visual/layout change with no new externally-observable contract beyond "still generates at the right size" — consistent with how the original label rendering has always been tested in this file, see `TestGenerateBarcodeLabelIntegration`).

- [ ] **Step 3: Implement**

In `shopify_tool/barcode_processor.py`, replace the font-size constants (lines 65-68) — these were already unused (the function used ad-hoc inline font sizes instead), the redesign now actually uses them:

```python
# Font sizes - redesigned grid layout (Task 9)
FONT_SIZE_HEADER = 20   # Seq# + courier, same header line
FONT_SIZE_DATE = 12     # Date, secondary/muted
FONT_SIZE_GRID = 15     # SUM/COU/TAG grid label + value
```

Replace `# === STEP 4: Add text info on left side ===` through the end of the TAG section (everything between `# === STEP 4` and `# === Add order number below barcode`) with:

```python
        # === STEP 4: Add text info on left side (grid-aligned, Task 9) ===
        font_header = load_font(FONT_SIZE_HEADER, bold=True)
        font_date = load_font(FONT_SIZE_DATE, bold=False)
        font_grid_label = load_font(FONT_SIZE_GRID, bold=False)
        font_grid_value = load_font(FONT_SIZE_GRID, bold=True)
        font_tag_multiline = load_font(FONT_SIZE_GRID, bold=True)

        left_margin = 8
        y_pos = 10
        muted = (90, 90, 90)
        separator = (200, 200, 200)

        # Header row: seq# + courier on one line
        courier_display = courier[:12] if len(courier) <= 12 else courier[:9] + "..."
        draw.text((left_margin, y_pos), f"#{sequential_num}  {courier_display}", font=font_header, fill='black')
        y_pos += 26

        # Date, secondary
        draw.text((left_margin, y_pos), date_str, font=font_date, fill=muted)
        y_pos += 22

        # === Grid rows: SUM / COU (uniform row height, label + right-aligned value) ===
        grid_row_height = 34
        for label_text, value_text in [("SUM", str(item_count)), ("COU", country_display)]:
            draw.line([(left_margin, y_pos), (INFO_SECTION_WIDTH - 8, y_pos)], fill=separator, width=1)
            row_top = y_pos + 6
            draw.text((left_margin, row_top), label_text, font=font_grid_label, fill=muted)
            value_bbox = draw.textbbox((0, 0), value_text, font=font_grid_value)
            value_width = value_bbox[2] - value_bbox[0]
            draw.text((INFO_SECTION_WIDTH - 8 - value_width, row_top), value_text, font=font_grid_value, fill='black')
            y_pos += grid_row_height

        # TAG row: multiline, takes remaining space
        draw.line([(left_margin, y_pos), (INFO_SECTION_WIDTH - 8, y_pos)], fill=separator, width=1)
        tag_start_y = y_pos + 6
        draw.text((left_margin, tag_start_y), "TAG", font=font_grid_label, fill=muted)

        available_height = label_height_px - tag_start_y - 8
        available_width = INFO_SECTION_WIDTH - left_margin - 8

        if tag_display and tag_display != "N/A":
            tag_x = left_margin
            tag_y = tag_start_y + 20
            line_height = 20

            tags = [t.strip() for t in tag_display.split('|') if t.strip()]

            current_line = ""
            for single_tag in tags:
                test_line = current_line + (", " if current_line else "") + single_tag
                bbox = draw.textbbox((0, 0), test_line, font=font_tag_multiline)
                line_width = bbox[2] - bbox[0]

                if line_width <= available_width:
                    current_line = test_line
                else:
                    if current_line:
                        draw.text((tag_x, tag_y), current_line, font=font_tag_multiline, fill='black')
                        tag_y += line_height
                    current_line = _clamp_text_to_width(draw, single_tag, font_tag_multiline, available_width)

                if tag_y + line_height > tag_start_y + available_height:
                    break

            if current_line and tag_y + line_height <= tag_start_y + available_height:
                draw.text((tag_x, tag_y), current_line, font=font_tag_multiline, fill='black')
        else:
            draw.text((left_margin, tag_start_y + 20), "N/A", font=font_tag_multiline, fill='black')
```

Also make the barcode-section margins consistent (Task 9's other stated goal). Replace the STEP 3 sizing block:

```python
        # Resize barcode to fit right section (MAXIMUM size)
        barcode_target_width = BARCODE_SECTION_WIDTH - 10  # Minimal margin
        barcode_target_height = label_height_px - 55       # Space for number below

        barcode_img_resized = barcode_img.resize(
            (barcode_target_width, barcode_target_height),
            Image.Resampling.LANCZOS
        )

        # Paste barcode on right side (centered horizontally, top aligned)
        barcode_x = BARCODE_SECTION_X + 5  # Minimal margin
        barcode_y = 5  # Minimal top margin
        label_img.paste(barcode_img_resized, (barcode_x, barcode_y))
```

with:

```python
        # Resize barcode to fit right section (consistent margins, Task 9)
        BARCODE_MARGIN = 10
        barcode_target_width = BARCODE_SECTION_WIDTH - (2 * BARCODE_MARGIN)
        barcode_target_height = label_height_px - 55 - BARCODE_MARGIN  # room for order number below + top margin

        barcode_img_resized = barcode_img.resize(
            (barcode_target_width, barcode_target_height),
            Image.Resampling.LANCZOS
        )

        # Paste barcode on right side (centered horizontally, top aligned)
        barcode_x = BARCODE_SECTION_X + BARCODE_MARGIN
        barcode_y = BARCODE_MARGIN
        label_img.paste(barcode_img_resized, (barcode_x, barcode_y))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git add shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git commit -m "Redesign Code-128 label info column as a grid-aligned layout"
```

---

### Task 10: `barcode_processor.generate_qr_labels_pdf()`

**Files:**
- Modify: `shopify_tool/barcode_processor.py` (imports, new function)
- Test: `tests/test_barcode_processor.py`

**Interfaces:**
- Produces: `generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path, label_width_mm: float = LABEL_WIDTH_MM, label_height_mm: float = LABEL_HEIGHT_MM) -> Path`. Each `orders` item: `{"order_number": str, "sku_qty_lines": list[tuple[str, int]]}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_barcode_processor.py`:

```python
class TestGenerateQrLabelsPdf:
    """No QR-decode library is available in this repo's dependencies (see
    plan Global Constraints), so payload correctness is checked via the
    QrCodeWidget's own .value attribute (the string handed to the encoder),
    not a round-trip decode."""

    def test_one_page_per_order(self, tmp_path):
        from shopify_tool.barcode_processor import generate_qr_labels_pdf

        orders = [
            {"order_number": "#1001", "sku_qty_lines": [("SKU-A", 2)]},
            {"order_number": "#1002", "sku_qty_lines": [("SKU-B", 1), ("SKU-C", 3)]},
        ]
        output_pdf = tmp_path / "qr_labels.pdf"

        result = generate_qr_labels_pdf(orders, output_pdf)

        assert result == output_pdf
        assert output_pdf.exists()
        from pypdf import PdfReader
        assert len(PdfReader(output_pdf).pages) == 2

    def test_qr_payload_contains_order_number_and_sku_qty_lines(self, tmp_path, monkeypatch):
        from shopify_tool import barcode_processor

        captured_values = []
        original_widget = barcode_processor.qr.QrCodeWidget

        def spy_widget(value, **kw):
            captured_values.append(value)
            return original_widget(value, **kw)

        monkeypatch.setattr(barcode_processor.qr, "QrCodeWidget", spy_widget)

        orders = [{"order_number": "#1001", "sku_qty_lines": [("SKU-A", 2), ("SKU-B", 1)]}]
        barcode_processor.generate_qr_labels_pdf(orders, tmp_path / "qr_labels.pdf")

        assert len(captured_values) == 1
        assert "#1001" in captured_values[0]
        assert "SKU-A x 2" in captured_values[0]
        assert "SKU-B x 1" in captured_values[0]

    def test_empty_orders_raises(self, tmp_path):
        from shopify_tool.barcode_processor import generate_qr_labels_pdf

        with pytest.raises(ValueError):
            generate_qr_labels_pdf([], tmp_path / "qr_labels.pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py::TestGenerateQrLabelsPdf -v`
Expected: FAIL with `ImportError: cannot import name 'generate_qr_labels_pdf'`

- [ ] **Step 3: Implement**

In `shopify_tool/barcode_processor.py`, add imports (alongside the existing `from reportlab.lib.pagesizes import mm` / `from reportlab.pdfgen import canvas` lines):

```python
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
```

Add the new function after `generate_barcodes_pdf()` (end of file):

```python
def generate_qr_labels_pdf(
    orders: list[dict[str, Any]],
    output_pdf: Path,
    label_width_mm: float = LABEL_WIDTH_MM,
    label_height_mm: float = LABEL_HEIGHT_MM
) -> Path:
    """
    Generate a QR-only labels PDF, one page per order.

    Physically separate from the Code-128 barcode label on purpose -- two
    codes close together on one label risk a handheld warehouse scanner
    picking up the wrong one. Each page: order number (large text) + a QR
    code encoding the order number and its SKU/quantity line items, nothing
    else. Same page size as the Code-128 label, for the same label stock.

    Unlike generate_barcodes_pdf(), this does not composite PNG files --
    reportlab's raster backend (renderPM) needs an extra package that isn't
    installed here, so the QR (a vector reportlab.graphics widget) is drawn
    directly onto the PDF canvas via renderPDF.draw() instead.

    Args:
        orders: List of {"order_number": str, "sku_qty_lines": list[tuple[str, int]]}
        output_pdf: Output PDF path
        label_width_mm: Label width (default: 68mm)
        label_height_mm: Label height (default: 38mm)

    Returns:
        Path to generated PDF

    Raises:
        ValueError: If orders is empty
    """
    if not orders:
        raise ValueError("Cannot generate QR labels PDF: no orders provided")

    page_width = label_width_mm * mm
    page_height = label_height_mm * mm

    TOP_MARGIN_FOR_TEXT = 24  # points, room for the order-number text row
    BOTTOM_MARGIN = 6
    SIDE_MARGIN = 10

    c = canvas.Canvas(str(output_pdf), pagesize=(page_width, page_height))

    for order in orders:
        order_number = order["order_number"]
        sku_qty_lines = order["sku_qty_lines"]

        qr_payload = "\n".join(
            [order_number] + [f"{sku} x {qty}" for sku, qty in sku_qty_lines]
        )

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_width / 2, page_height - 16, order_number)

        widget = qr.QrCodeWidget(qr_payload)
        bounds = widget.getBounds()
        qr_native_width = bounds[2] - bounds[0]
        qr_native_height = bounds[3] - bounds[1]
        qr_target_size = min(
            page_width - (2 * SIDE_MARGIN),
            page_height - TOP_MARGIN_FOR_TEXT - BOTTOM_MARGIN,
        )
        drawing = Drawing(
            qr_target_size, qr_target_size,
            transform=[qr_target_size / qr_native_width, 0, 0, qr_target_size / qr_native_height, 0, 0],
        )
        drawing.add(widget)
        x = (page_width - qr_target_size) / 2
        renderPDF.draw(drawing, c, x, BOTTOM_MARGIN)

        c.showPage()

    c.save()

    logger.info(f"Generated QR labels PDF: {output_pdf} ({len(orders)} pages)")

    return output_pdf
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git add shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git commit -m "Add generate_qr_labels_pdf for optional, physically separate QR labels"
```

---

### Task 11: Wire "Add QR labels" checkbox + Print QR button

**Files:**
- Modify: `gui/barcode_generator_widget.py`
- Test: `tests/test_barcode_generator_widget.py`

**Interfaces:**
- Consumes: `barcode_processor.generate_qr_labels_pdf(orders, output_pdf) -> Path` (Task 10), `gui.pdf_printing.print_pdf(parent, pdf_path) -> bool` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_barcode_generator_widget.py`:

```python
def test_add_qr_checkbox_defaults_unchecked(widget):
    assert widget.add_qr_checkbox.isChecked() is False


def test_qr_pdf_generated_when_checkbox_checked(widget, tmp_path, monkeypatch):
    widget.barcodes_dir = tmp_path
    widget.current_packing_list = "DHL_Orders"
    widget.add_qr_checkbox.setChecked(True)
    widget.auto_open_pdf_checkbox.setChecked(False)
    widget.filtered_orders_df = pd.DataFrame([
        {"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 2},
        {"Order_Number": "#1001", "SKU": "SKU-B", "Quantity": 1},
    ])

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_barcodes_pdf",
        lambda barcode_files, out_path: out_path,
    )
    captured = {}
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_qr_labels_pdf",
        lambda orders, out_path: captured.update(orders=orders, out_path=out_path) or out_path,
    )

    widget._on_generation_complete(_successful_results(tmp_path))

    assert captured["orders"] == [
        {"order_number": "#1001", "sku_qty_lines": [("SKU-A", 2), ("SKU-B", 1)]}
    ]
    assert captured["out_path"] == tmp_path / "DHL_Orders_qr_labels.pdf"
    assert widget.print_qr_btn.isEnabled() is True
    assert widget.last_qr_pdf == tmp_path / "DHL_Orders_qr_labels.pdf"


def test_qr_pdf_not_generated_when_checkbox_unchecked(widget, tmp_path, monkeypatch):
    widget.barcodes_dir = tmp_path
    widget.current_packing_list = "DHL_Orders"
    widget.add_qr_checkbox.setChecked(False)
    widget.auto_open_pdf_checkbox.setChecked(False)

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_barcodes_pdf",
        lambda barcode_files, out_path: out_path,
    )
    was_called = []
    monkeypatch.setattr(
        "gui.barcode_generator_widget.generate_qr_labels_pdf",
        lambda *a, **k: was_called.append(True),
    )

    widget._on_generation_complete(_successful_results(tmp_path))

    assert not was_called
    assert widget.print_qr_btn.isEnabled() is False


def test_print_qr_button_click_calls_print_pdf(widget, tmp_path, monkeypatch):
    widget.last_qr_pdf = tmp_path / "qr.pdf"
    widget.print_qr_btn.setEnabled(True)

    captured = {}
    monkeypatch.setattr(
        "gui.barcode_generator_widget.print_pdf",
        lambda parent, pdf_path: captured.update(pdf_path=pdf_path) or True,
    )

    widget._on_print_qr_clicked()

    assert captured["pdf_path"] == widget.last_qr_pdf
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -k qr -v`
Expected: FAIL — `widget.add_qr_checkbox` doesn't exist

- [ ] **Step 3: Implement**

In `gui/barcode_generator_widget.py`, add the import:

```python
from shopify_tool.barcode_processor import generate_qr_labels_pdf
```

In `_create_options_section()`, add the checkbox after `self.auto_open_pdf_checkbox`:

```python
        # Optional QR labels (separate PDF -- see barcode_processor.generate_qr_labels_pdf)
        self.add_qr_checkbox = QCheckBox("Add QR labels (separate PDF, order contents)")
        self.add_qr_checkbox.setChecked(False)
        self.add_qr_checkbox.setToolTip(
            "Generates a second PDF: one QR code per order encoding its SKU/quantity "
            "contents, printed separately from the barcode labels."
        )
        layout.addWidget(self.add_qr_checkbox)
```

In `_create_generation_section()`, add a second Print button after `self.print_btn`:

```python
        # Print QR labels button (separate print job, enabled once a QR PDF exists)
        self.print_qr_btn = QPushButton("Print QR labels...")
        self.print_qr_btn.setEnabled(False)
        self.print_qr_btn.setToolTip("Print the QR labels PDF with a printer picker")
        layout.addWidget(self.print_qr_btn)
```

In `_connect_signals()`, wire it:

```python
        self.print_qr_btn.clicked.connect(self._on_print_qr_clicked)
```

In `_on_generation_complete()`, after the `self._generate_pdf_from_results(successful)` / `self._cleanup_png_files(successful)` calls, add the QR generation step:

```python
        if successful:
            self._generate_pdf_from_results(successful)
            self._cleanup_png_files(successful)

            if self.add_qr_checkbox.isChecked():
                self._generate_qr_labels_from_current_orders()
```

Add two new methods after `_on_print_clicked()`:

```python
    def _generate_qr_labels_from_current_orders(self):
        """Generate the optional QR-labels PDF from filtered_orders_df's
        line items (SKU + Quantity per row), grouped by order."""
        try:
            orders = []
            for order_number, group in self.filtered_orders_df.groupby('Order_Number', sort=False):
                sku_qty_lines = list(zip(group['SKU'], group['Quantity']))
                orders.append({"order_number": str(order_number), "sku_qty_lines": sku_qty_lines})

            qr_pdf_path = self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf"
            generate_qr_labels_pdf(orders, qr_pdf_path)

            self.log.info(f"Generated QR labels PDF: {qr_pdf_path}")

            self.last_qr_pdf = qr_pdf_path
            self.print_qr_btn.setEnabled(True)

        except Exception:
            self.log.exception("QR labels generation failed")

    def _on_print_qr_clicked(self):
        """Print the last-generated QR labels PDF via a printer-selection dialog."""
        if not self.last_qr_pdf:
            return
        print_pdf(self, self.last_qr_pdf)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Wire optional QR labels generation and printing into Barcode Generator"
```

---

## Final Verification

After all 11 tasks:

- [ ] Run the full suite: `QT_QPA_PLATFORM=offscreen python -m pytest -v` — expect all green.
- [ ] Run the full lint: `ruff check . --exclude shared` — expect no errors.
- [ ] Manually smoke-test in the app (per `run` skill / `python run_dev.py`):
  - Reference Labels: process a courier PDF + CSV, confirm no history table appears, click Print, confirm the native print dialog opens and a preview/print job renders correctly with the new small barcode visible in the bottom strip.
  - Barcode Generator: generate barcodes for a packing list, confirm the window shows no format checkboxes/info paragraph, confirm the PDF auto-opens (or not, per the checkbox), click Print, confirm it prints.
  - Barcode Generator: check "Add QR labels", generate again, confirm a second PDF (`..._qr_labels.pdf`) is created, click "Print QR labels...", confirm it's a separate print job from the barcode PDF.
  - Scan a real printed Code-128 label with a warehouse scanner and confirm the redesigned layout still scans correctly and reads clearly.
- [ ] `graphify update .` (per this repo's `CLAUDE.md` — stale graph gives wrong answers about this codebase's structure).
- [ ] Comment the branch/PR link on the Phase 4 epic's 4 Todoist subtasks and check them off; check off the Phase 4 parent task once all subtasks are done (per the Roadmap's READ FIRST workflow guide).
