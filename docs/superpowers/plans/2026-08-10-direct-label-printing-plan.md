# Direct Label Printing (Driver + Raw ZPL) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 4's D-1 (shared print-to-printer helper, speced 2026-07-30, never
implemented) for both the Reference Labels and Barcode Generator windows, and add a raw-ZPL
print mode — proven working against the warehouse's Citizen CL-E300 thermal printer in the
sibling `barcode_tool` repo — as a per-machine-selectable alternative to OS-driver printing.

**Architecture:** A new `shopify_tool/label_printing.py` rasterizes an already-generated label
PDF to 1-bit images at 203 DPI (`pypdfium2`) and spools each page as a raw ZPL job
(`zebrafy` + `win32print` RAW datatype on Windows, a plain file write on Linux dev machines) —
ported from `barcode_tool`'s `template_renderer.py`/`zpl_print_service.py`. A new
`gui/pdf_printing.py` is the single entry point both windows call: `print_pdf(parent, pdf_path,
settings)` dispatches to either the original driver-mode design (`QPrintDialog` + `QtPdf`,
never implemented until now) or `label_printing.print_pdf_raw_zpl()`, based on a `print_mode`
setting stored in local `QSettings` (per-machine, not the shared/synced client config).
`gui/barcode_generator_widget.py` gains the settings UI (mode combo, ZPL target, rotate
checkbox) plus "Print..."/"Print QR labels..." buttons; `gui/reference_labels_widget.py` gains
one "Print..." button, reading the same settings.

**Tech Stack:** PySide6 (`QtPdf`, `QtPrintSupport`, `QSettings`), `pypdfium2` (PDF rasterization,
new dependency), `zebrafy` (image→ZPL, new dependency), `pywin32` (Windows RAW spooling, new
Windows-only dependency), pytest (`QT_QPA_PLATFORM=offscreen`), ruff.

## Global Constraints

- `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` must pass
  before merge (per `AGENTS.md`/`CLAUDE.md`).
- `win32print`/`pywintypes` must only be imported inside function bodies in
  `shopify_tool/label_printing.py`, never at module scope — this module (and anything that
  imports it) must import cleanly on Linux (dev machine, CI).
- Printer/print-mode settings are per-machine (`QSettings`), never written into
  `shopify_config.json`/the shared client-config Settings window.
- `shared/` is not touched by any task in this plan.
- Reference Labels' Processing History table and Code-128 overlay barcode are untouched — out
  of scope (see spec's Non-goals/Follow-ups).
- New dependencies (`pypdfium2`, `zebrafy`, `pywin32`) must be installed
  (`pip install -r requirements.txt`) before running this plan's new tests.

---

## Task 1: Add print-mode dependencies

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `pypdfium2`, `zebrafy`, `pywin32` importable in the dev/CI environment for Tasks 2-3.

- [ ] **Step 1: Append to `requirements.txt`**

```
# Direct Label Printing (raw ZPL for Citizen CL-E300, matches barcode_tool)
# ---------------------------------------------------------------------
pypdfium2>=4.0          # PDF rasterization for raw ZPL printing
zebrafy>=1.2             # PIL Image -> ZPL conversion for raw ZPL printing
pywin32>=306; sys_platform == "win32"  # win32print RAW spooling (Windows only)
```

- [ ] **Step 2: Install and verify import**

Run: `pip install -r requirements.txt && python -c "import pypdfium2, zebrafy"`
Expected: no `ImportError`. (`pywin32` will not install on Linux — expected, guarded by the
environment marker.)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "Add pypdfium2/zebrafy/pywin32 dependencies for direct label printing"
```

---

## Task 2: Raw ZPL backend — `shopify_tool/label_printing.py`

**Files:**
- Create: `shopify_tool/label_printing.py`
- Test: `tests/test_label_printing.py` (new)

**Interfaces:**
- Produces: `rasterize_pdf(pdf_path, dpi=PRINT_DPI) -> list[Image.Image]`,
  `image_to_zpl(image, rotate=False) -> str`, `send_raw_windows(printer_name, data)`,
  `send_raw_linux(device_path, data)`, `print_pdf_raw_zpl(pdf_path, target, rotate=False)`,
  `windows_print_errors() -> tuple[type[Exception], ...]`.
- Consumed by: Task 3's `gui/pdf_printing.py` (`print_pdf_raw_zpl`, `windows_print_errors`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_label_printing.py`:

```python
"""Tests for shopify_tool.label_printing -- raw ZPL printing for the Citizen
CL-E300, ported from barcode_tool's proven template_renderer.py /
zpl_print_service.py (see docs/superpowers/specs/2026-08-10-direct-label-printing-design.md)."""
import sys
import types

from PIL import Image

from shopify_tool import label_printing


def _make_pdf(tmp_path, pages=2):
    """A minimal multi-page PDF via reportlab (already a dependency) for
    rasterize_pdf() to read -- content doesn't matter, only page count/size."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm

    pdf_path = tmp_path / "labels.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(68 * mm, 38 * mm))
    for _ in range(pages):
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
    c.save()
    return pdf_path


class TestRasterizePdf:
    def test_returns_one_image_per_page(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=3)
        images = label_printing.rasterize_pdf(pdf_path)
        assert len(images) == 3

    def test_images_are_1bit_mode(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=1)
        images = label_printing.rasterize_pdf(pdf_path)
        assert images[0].mode == "1"

    def test_dpi_controls_pixel_dimensions(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=1)
        low = label_printing.rasterize_pdf(pdf_path, dpi=72)[0]
        high = label_printing.rasterize_pdf(pdf_path, dpi=203)[0]
        assert high.width > low.width
        assert high.height > low.height


class TestImageToZpl:
    def test_wraps_field_in_xa_xz(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image)
        assert zpl.startswith("^XA\n")
        assert zpl.endswith("^XZ\n")

    def test_pw_ll_match_image_dimensions(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image)
        assert "^PW100\n" in zpl
        assert "^LL50\n" in zpl

    def test_rotate_swaps_pw_ll(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image, rotate=True)
        assert "^PW50\n" in zpl
        assert "^LL100\n" in zpl


class TestSendRawLinux:
    def test_writes_bytes_to_device_path(self, tmp_path):
        target = tmp_path / "fake_device"
        label_printing.send_raw_linux(str(target), b"^XA...^XZ")
        assert target.read_bytes() == b"^XA...^XZ"


class TestSendRawWindows:
    def test_spools_raw_datatype_and_writes_data(self, monkeypatch):
        calls = []
        fake_win32print = types.SimpleNamespace(
            OpenPrinter=lambda name: calls.append(("open", name)) or "HANDLE",
            StartDocPrinter=lambda h, level, doc_info: calls.append(("start_doc", h, doc_info)),
            StartPagePrinter=lambda h: calls.append(("start_page", h)),
            WritePrinter=lambda h, data: calls.append(("write", h, data)),
            EndPagePrinter=lambda h: calls.append(("end_page", h)),
            EndDocPrinter=lambda h: calls.append(("end_doc", h)),
            ClosePrinter=lambda h: calls.append(("close", h)),
        )
        monkeypatch.setitem(sys.modules, "win32print", fake_win32print)

        label_printing.send_raw_windows("ZPL-RAW-Printer", b"^XA...^XZ")

        assert ("open", "ZPL-RAW-Printer") in calls
        assert calls[1] == ("start_doc", "HANDLE", ("ZPL label", "", "RAW"))
        assert ("write", "HANDLE", b"^XA...^XZ") in calls
        assert calls[-1] == ("close", "HANDLE")


class TestPrintPdfRawZpl:
    def test_sends_one_job_per_page(self, tmp_path, monkeypatch):
        pdf_path = _make_pdf(tmp_path, pages=2)
        sent = []
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(
            label_printing, "send_raw_linux", lambda target, data: sent.append((target, data))
        )
        label_printing.print_pdf_raw_zpl(pdf_path, "/dev/usb/lp0")
        assert len(sent) == 2
        assert all(target == "/dev/usb/lp0" for target, _ in sent)


class TestWindowsPrintErrors:
    def test_returns_empty_tuple_when_pywintypes_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pywintypes", None)
        assert label_printing.windows_print_errors() == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_printing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shopify_tool.label_printing'`.

- [ ] **Step 3: Create `shopify_tool/label_printing.py`**

```python
"""Raw ZPL printing for the Citizen CL-E300 thermal label printer.

Ported from barcode_tool's app/core/template_renderer.py (rasterization) and
app/core/zpl_print_service.py (ZPL encoding + RAW spooling) -- proven working
in production against the same hardware and the same 68mm x 38mm label
format this app's blabel templates already render at
(shopify_tool/barcode_processor.py). See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md.
"""
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
    # Raw ZPL talks straight to the print head - there's no driver in the
    # loop to reconcile a landscape-designed template against a
    # portrait-mounted label roll (or vice versa). rotate is an operator-set
    # fact about their specific printer's media, not derivable from the PDF.
    if rotate:
        image = image.transpose(Image.Transpose.ROTATE_90)
    # invert=True: PIL's mode "1" packs a set bit as white, but ZPL's ^GFA
    # graphic field treats a set bit as printed (black) - without this every
    # raw ZPL print comes out with barcode and background swapped.
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
    (a Windows print-queue name, or a device path on Linux dev machines)."""
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

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_printing.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/label_printing.py tests/test_label_printing.py
git commit -m "Add raw ZPL printing backend (shopify_tool/label_printing.py)"
```

---

## Task 3: Print dispatcher + settings — `gui/pdf_printing.py`

**Files:**
- Create: `gui/pdf_printing.py`
- Test: `tests/test_pdf_printing.py` (new)

**Interfaces:**
- Consumes: `shopify_tool.label_printing.print_pdf_raw_zpl()`, `.windows_print_errors()` from
  Task 2.
- Produces: `print_pdf(parent: QWidget, pdf_path: Path, settings: dict) -> bool`,
  `load_print_settings() -> dict`, `save_print_settings(settings: dict) -> None`.
- Consumed by: Task 4 and Task 5's print button handlers.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf_printing.py`:

```python
"""Tests for gui.pdf_printing -- the shared print-to-printer dispatcher
(driver mode + raw ZPL mode) both windows' Print buttons call into. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from gui import pdf_printing


@pytest.fixture
def isolated_settings(monkeypatch):
    """Point QSettings at a throwaway org/app pair so tests never touch the
    developer's real local settings."""
    monkeypatch.setattr(pdf_printing, "_SETTINGS", ("ShopifyFulfillmentToolTest", "PrintingTest"))
    yield
    QSettings(*pdf_printing._SETTINGS).clear()


class TestPrintSettingsRoundTrip:
    def test_defaults_when_nothing_saved(self, isolated_settings):
        settings = pdf_printing.load_print_settings()
        assert settings == {"print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False}

    def test_save_then_load_roundtrip(self, isolated_settings):
        pdf_printing.save_print_settings(
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True}
        )
        assert pdf_printing.load_print_settings() == {
            "print_mode": "raw_zpl",
            "raw_zpl_target": "ZPL-RAW-Printer",
            "raw_zpl_rotate": True,
        }


class TestPrintPdfRawZplMode:
    def test_blank_target_warns_and_returns_false(self, monkeypatch, tmp_path):
        warning = Mock()
        monkeypatch.setattr(QMessageBox, "warning", warning)
        called = Mock()
        monkeypatch.setattr(pdf_printing.label_printing, "print_pdf_raw_zpl", called)

        result = pdf_printing.print_pdf(
            None, tmp_path / "x.pdf", {"print_mode": "raw_zpl", "raw_zpl_target": "", "raw_zpl_rotate": False}
        )

        assert result is False
        assert warning.called
        assert not called.called

    def test_calls_print_pdf_raw_zpl_with_target_and_rotate(self, monkeypatch, tmp_path):
        called = Mock()
        monkeypatch.setattr(pdf_printing.label_printing, "print_pdf_raw_zpl", called)
        pdf_path = tmp_path / "x.pdf"

        result = pdf_printing.print_pdf(
            None, pdf_path,
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True},
        )

        assert result is True
        called.assert_called_once_with(pdf_path, "ZPL-RAW-Printer", rotate=True)

    def test_exception_shows_critical_and_returns_false(self, monkeypatch, tmp_path):
        critical = Mock()
        monkeypatch.setattr(QMessageBox, "critical", critical)
        monkeypatch.setattr(
            pdf_printing.label_printing, "print_pdf_raw_zpl",
            Mock(side_effect=OSError("printer offline")),
        )

        result = pdf_printing.print_pdf(
            None, tmp_path / "x.pdf",
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": False},
        )

        assert result is False
        assert critical.called


class TestPrintPdfDriverMode:
    def test_renders_expected_page_count_to_pdf_output(self, tmp_path):
        """No real OS printer needed: point QPrinter at PdfFormat output
        instead of a live printer, matching the original D-1 testing note."""
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        for _ in range(2):
            c.drawString(5 * mm, 5 * mm, "TEST")
            c.showPage()
        c.save()

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)

        assert result is True
        assert out_pdf.exists()
        import pypdf
        assert len(pypdf.PdfReader(str(out_pdf)).pages) == 2
```

Note: `_print_pdf_driver_mode` takes an internal `output_path` escape hatch (writes to a PDF
file instead of opening `QPrintDialog`) purely so the render path is testable headlessly,
matching the original 2026-07-30 D-1 testing note ("unit test with a `QPrinter` in
preview/PDF-output mode ... dialog interaction itself isn't testable headlessly").

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.pdf_printing'`.

- [ ] **Step 3: Create `gui/pdf_printing.py`**

```python
"""Shared print-to-printer dispatcher for the Reference Labels and Barcode
Generator windows. Two modes, chosen by a per-machine setting:

- "driver": native QPrintDialog + QtPdf (vector, any installed printer).
- "raw_zpl": shopify_tool.label_printing.print_pdf_raw_zpl() (Citizen CL-E300,
  proven in barcode_tool).

See docs/superpowers/specs/2026-08-10-direct-label-printing-design.md.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import QMessageBox, QWidget

from shopify_tool import label_printing

logger = logging.getLogger(__name__)

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


def print_pdf(parent: QWidget | None, pdf_path: Path, settings: dict) -> bool:
    """Print every page of pdf_path per settings["print_mode"].

    Returns True only if printing completed with no error. Returns False if
    the user cancelled the print dialog (driver mode only) or if printing
    failed for any other reason -- a QMessageBox is shown in the failure
    case, not the cancel case.
    """
    if settings.get("print_mode") == "raw_zpl":
        return _print_pdf_raw_zpl_mode(parent, pdf_path, settings)
    return _print_pdf_driver_mode(parent, pdf_path)


def _print_pdf_raw_zpl_mode(parent, pdf_path: Path, settings: dict) -> bool:
    target = settings.get("raw_zpl_target", "")
    if not target.strip():
        QMessageBox.warning(
            parent, "No Printer Configured",
            "Set the raw ZPL printer target in Barcode Generator's Options section first."
        )
        return False
    try:
        label_printing.print_pdf_raw_zpl(pdf_path, target, rotate=settings.get("raw_zpl_rotate", False))
        return True
    except (OSError, *label_printing.windows_print_errors()) as error:
        logger.exception("Raw ZPL print failed")
        QMessageBox.critical(parent, "Print Failed", f"Raw ZPL printing failed:\n\n{error}")
        return False


def _print_pdf_driver_mode(parent, pdf_path: Path, output_path: Path | None = None) -> bool:
    document = QPdfDocument()
    document.load(str(pdf_path))

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)

    if output_path is not None:
        # Test-only escape hatch: PDF output needs no OS printer and no
        # dialog, so the render path is coverable headlessly (see
        # tests/test_pdf_printing.py -- dialog interaction itself isn't
        # testable in CI, matching the original D-1 design's testing note).
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_path))
    else:
        dialog = QPrintDialog(printer, parent)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

    try:
        painter = QPainter(printer)
        for page in range(document.pageCount()):
            if page > 0:
                printer.newPage()
            size = document.pagePointSize(page)
            image = document.render(page, size.toSize())
            painter.drawImage(0, 0, image)
        painter.end()
        return True
    except Exception as error:
        logger.exception("Driver print failed")
        QMessageBox.critical(parent, "Print Failed", f"Printing failed:\n\n{error}")
        return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add gui/pdf_printing.py tests/test_pdf_printing.py
git commit -m "Add print dispatcher (driver + raw ZPL) and shared print settings"
```

---

## Task 4: Wire printing into Barcode Generator

**Files:**
- Modify: `gui/barcode_generator_widget.py`
- Test: `tests/test_barcode_generator_widget.py` (extend)

**Interfaces:**
- Consumes: `gui.pdf_printing.print_pdf()`, `.load_print_settings()`, `.save_print_settings()`
  from Task 3.
- Produces: `self.last_barcode_pdf`, `self.last_qr_pdf` (set in `_on_generation_complete()`),
  `self.print_btn`, `self.print_qr_btn`, printer-settings controls
  (`self.print_mode_combo`, `self.raw_zpl_target_edit`, `self.raw_zpl_rotate_check`).

- [ ] **Step 1: Extend `tests/test_barcode_generator_widget.py`'s `_FakeWidget` and add print-state assertions**

Add to `_FakeWidget.__init__` (alongside the existing `Mock()` attributes):

```python
        self.print_btn = Mock()
        self.print_qr_btn = Mock()
        self.last_barcode_pdf = None
        self.last_qr_pdf = None
```

Append new test functions:

```python
def test_successful_generation_enables_print_button_and_sets_last_pdf(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True)
    assert widget.last_barcode_pdf == Path("/fake/barcodes/PL1_barcodes.pdf")
    widget.print_btn.setEnabled.assert_called_with(True)


def test_pdf_render_failure_leaves_print_button_disabled(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=False)
    assert widget.last_barcode_pdf is None
    widget.print_btn.setEnabled.assert_called_with(False)


def test_qr_checkbox_on_enables_print_qr_button(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=True)
    assert widget.last_qr_pdf == Path("/fake/barcodes/PL1_qr_labels.pdf")
    widget.print_qr_btn.setEnabled.assert_called_with(True)


def test_qr_checkbox_off_leaves_print_qr_button_disabled(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True, add_qr=False)
    assert widget.last_qr_pdf is None
    widget.print_qr_btn.setEnabled.assert_called_with(False)
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v`
Expected: FAIL — `AttributeError` (`_on_generation_complete` doesn't yet set
`last_barcode_pdf`/`last_qr_pdf` or touch `print_btn`/`print_qr_btn`).

- [ ] **Step 3: Add printer-settings controls to `_create_options_section()` (`gui/barcode_generator_widget.py:119-144`)**

Add `QComboBox`, `QLineEdit` to the imports (`PySide6.QtWidgets`), and `from gui.pdf_printing
import load_print_settings, print_pdf, save_print_settings` near the top. Append to the method,
before `return group`:

```python
        # Printing (raw ZPL target/rotate only relevant when that mode is selected)
        print_settings = load_print_settings()

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Print mode:"))
        self.print_mode_combo = QComboBox()
        self.print_mode_combo.addItem("OS driver (print dialog)", "driver")
        self.print_mode_combo.addItem("Raw ZPL (direct)", "raw_zpl")
        mode_index = self.print_mode_combo.findData(print_settings["print_mode"])
        if mode_index >= 0:
            self.print_mode_combo.setCurrentIndex(mode_index)
        mode_row.addWidget(self.print_mode_combo, 1)
        layout.addLayout(mode_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Raw ZPL target:"))
        self.raw_zpl_target_edit = QLineEdit(print_settings["raw_zpl_target"])
        self.raw_zpl_target_edit.setPlaceholderText(
            "e.g. ZPL-RAW-Printer (Windows) or /dev/usb/lp0 (Linux)"
        )
        target_row.addWidget(self.raw_zpl_target_edit, 1)
        layout.addLayout(target_row)

        self.raw_zpl_rotate_check = QCheckBox("Rotate labels 90° for raw ZPL")
        self.raw_zpl_rotate_check.setChecked(print_settings["raw_zpl_rotate"])
        layout.addWidget(self.raw_zpl_rotate_check)

        def _update_zpl_controls_enabled():
            is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
            self.raw_zpl_target_edit.setEnabled(is_zpl)
            self.raw_zpl_rotate_check.setEnabled(is_zpl)

        _update_zpl_controls_enabled()
        self.print_mode_combo.currentIndexChanged.connect(_update_zpl_controls_enabled)
        self.print_mode_combo.currentIndexChanged.connect(self._save_print_settings)
        self.raw_zpl_target_edit.editingFinished.connect(self._save_print_settings)
        self.raw_zpl_rotate_check.toggled.connect(self._save_print_settings)
```

Add `QLineEdit` to the `PySide6.QtWidgets` import list at the top of the file.

- [ ] **Step 4: Add `_save_print_settings()` and print button handlers**

Add near `_open_pdf` (`gui/barcode_generator_widget.py:529-532`):

```python
    def _save_print_settings(self):
        save_print_settings({
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
        })

    def _on_print_clicked(self):
        print_pdf(self, self.last_barcode_pdf, load_print_settings())

    def _on_print_qr_clicked(self):
        print_pdf(self, self.last_qr_pdf, load_print_settings())
```

- [ ] **Step 5: Add Print buttons to `_create_generation_section()` (`gui/barcode_generator_widget.py:146-187`)**

After the existing `self.generate_btn` block, before the progress bar:

```python
        self.print_btn = QPushButton("Print...")
        self.print_btn.setEnabled(False)
        layout.addWidget(self.print_btn)

        self.print_qr_btn = QPushButton("Print QR labels...")
        self.print_qr_btn.setEnabled(False)
        layout.addWidget(self.print_qr_btn)
```

In `_connect_signals()`, add:

```python
        self.print_btn.clicked.connect(self._on_print_clicked)
        self.print_qr_btn.clicked.connect(self._on_print_qr_clicked)
```

- [ ] **Step 6: Update `_on_generation_complete()` (`gui/barcode_generator_widget.py:409-458`) to set `last_barcode_pdf`/`last_qr_pdf` and enable Print buttons**

Immediately after the existing `pdf_generated = ...` / `qr_pdf_generated = ...` lines:

```python
        self.last_barcode_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf" if pdf_generated else None
        )
        self.print_btn.setEnabled(bool(self.last_barcode_pdf))

        self.last_qr_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf" if qr_pdf_generated else None
        )
        self.print_qr_btn.setEnabled(bool(self.last_qr_pdf))
```

Also add `self.last_barcode_pdf = None` and `self.last_qr_pdf = None` to `__init__`
(`gui/barcode_generator_widget.py:54-57`, alongside `self.barcodes_dir = None`).

- [ ] **Step 7: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v`
Expected: PASS (11 tests).

- [ ] **Step 8: Commit**

```bash
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Wire print controls into Barcode Generator (driver + raw ZPL)"
```

---

## Task 5: Wire printing into Reference Labels

**Files:**
- Modify: `gui/reference_labels_widget.py`
- Test: `tests/test_reference_labels_widget.py` (new)

**Interfaces:**
- Consumes: `gui.pdf_printing.print_pdf()`, `.load_print_settings()` from Task 3. Reads the
  same `QSettings`-backed print-mode/target/rotate values Task 4's Barcode Generator controls
  write — no duplicate settings UI in this window.
- Produces: `self.last_output_pdf`, `self.print_btn`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reference_labels_widget.py`:

```python
"""Regression test for gui.reference_labels_widget.ReferenceLabelsWidget's
Print button -- mirrors the _FakeWidget pattern in
test_barcode_generator_widget.py. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from pathlib import Path
from unittest.mock import Mock

from gui.reference_labels_widget import ReferenceLabelsWidget


class _FakeWidget:
    def __init__(self):
        self.log = Mock()
        self.progress_bar = Mock()
        self.status_label = Mock()
        self.history = None
        self.pdf_path = "in.pdf"
        self.csv_path = "in.csv"
        self.auto_open_checkbox = Mock(isChecked=Mock(return_value=False))
        self.print_btn = Mock()
        self.processing_complete = Mock()
        self.last_output_pdf = None

    def _open_pdf(self, path):
        pass


def _result(**overrides):
    result = {
        "matched": 3, "unmatched": 0, "output_file": "/fake/out.pdf",
        "pages_processed": 3, "processing_time": 1.2,
    }
    result.update(overrides)
    return result


def test_print_button_disabled_before_processing():
    widget = _FakeWidget()
    assert widget.last_output_pdf is None


def test_processing_complete_sets_last_output_pdf_and_enables_print(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", Mock())

    widget = _FakeWidget()
    ReferenceLabelsWidget._on_processing_complete(widget, _result())

    assert widget.last_output_pdf == Path("/fake/out.pdf")
    widget.print_btn.setEnabled.assert_called_with(True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -v`
Expected: FAIL — `AttributeError` (`_on_processing_complete` doesn't yet set
`last_output_pdf` or touch `print_btn`).

- [ ] **Step 3: Add `self.last_output_pdf = None` to `__init__` (`gui/reference_labels_widget.py:59-62`)**

```python
        # File paths
        self.pdf_path = None
        self.csv_path = None
        self.output_dir = None
        self.last_output_pdf = None
```

- [ ] **Step 4: Add Print button to `_create_processing_group()` (`gui/reference_labels_widget.py:153-177`)**

After the existing `self.status_label` block, before `return group`:

```python
        self.print_btn = QPushButton("Print...")
        self.print_btn.setEnabled(False)
        layout.addWidget(self.print_btn)
```

- [ ] **Step 5: Add the click handler and wire it in `_connect_signals()` (`gui/reference_labels_widget.py:234-245`)**

Add near the top of the class, alongside other imports: `from gui.pdf_printing import
load_print_settings, print_pdf`. Add a handler method:

```python
    def _on_print_clicked(self):
        print_pdf(self, self.last_output_pdf, load_print_settings())
```

In `_connect_signals()`, add:

```python
        self.print_btn.clicked.connect(self._on_print_clicked)
```

- [ ] **Step 6: Update `_on_processing_complete()` (`gui/reference_labels_widget.py:472-518`) to set `last_output_pdf` and enable Print**

Immediately after `self.status_label.setStyleSheet(...)`:

```python
        self.last_output_pdf = Path(result['output_file'])
        self.print_btn.setEnabled(True)
```

- [ ] **Step 7: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_reference_labels_widget.py -v`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add gui/reference_labels_widget.py tests/test_reference_labels_widget.py
git commit -m "Add Print button to Reference Labels window"
```

---

## Task 6: Full verification

No code changes — this is the merge gate confirming all five tasks integrate cleanly.

- [ ] **Step 1: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: All tests pass, including every test touched or added in Tasks 1-5.

- [ ] **Step 2: Run lint**

Run: `ruff check . --exclude shared`
Expected: No errors.

- [ ] **Step 3: Manual QA (not automatable in this environment)**

Record for the user:
- Print a real batch from Barcode Generator in raw-ZPL mode to the physical Citizen CL-E300
  (both the Code-128 and QR label PDFs); confirm output matches what `barcode_tool` already
  produces on the same hardware, and that "Rotate labels 90°" actually flips orientation.
- Print a real batch from Barcode Generator in driver mode to any installed Windows printer;
  confirm the native print dialog appears and output is correct.
- Print from Reference Labels in both modes after configuring the printer settings via
  Barcode Generator's Options section (confirms the shared-settings design decision actually
  works across windows, not just within one).
- Confirm the "no printer configured" warning appears when raw-ZPL mode is selected with a
  blank target and Print is clicked.

This matches the spec's Testing section — no CI/pytest coverage exists for physical print
output or a real `QPrintDialog`.
