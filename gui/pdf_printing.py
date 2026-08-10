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

from PySide6.QtCore import QSettings, QSizeF
from PySide6.QtGui import QPageSize, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QMessageBox, QWidget

from shopify_tool import label_printing

logger = logging.getLogger(__name__)

_SETTINGS = ("ShopifyFulfillmentTool", "Printing")


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


def print_pdf(parent: QWidget | None, pdf_path: Path, settings: dict) -> bool:
    """Print every page of pdf_path per settings["print_mode"].

    Returns True only if printing completed with no error. Returns False if
    the user cancelled the print dialog (driver mode only) or if printing
    failed for any other reason -- a QMessageBox is shown in the failure
    case, not the cancel case.
    """
    if settings.get("print_mode") == "raw_zpl":
        return _print_pdf_raw_zpl_mode(parent, pdf_path, settings)
    return _print_pdf_driver_mode(parent, pdf_path, driver_printer_name=settings.get("driver_printer_name", ""))


def _print_pdf_raw_zpl_mode(parent, pdf_path: Path, settings: dict) -> bool:
    target = settings.get("raw_zpl_target", "")
    if not target.strip():
        QMessageBox.warning(
            parent, "No Printer Configured",
            "Set the raw ZPL printer target in this window's Output/Options section first."
        )
        return False
    try:
        label_printing.print_pdf_raw_zpl(pdf_path, target, rotate=settings.get("raw_zpl_rotate", False))
        return True
    except (OSError, *label_printing.windows_print_errors()) as error:
        logger.exception("Raw ZPL print failed")
        QMessageBox.critical(parent, "Print Failed", f"Raw ZPL printing failed:\n\n{error}")
        return False


def _resolve_page_range(printer: QPrinter, page_count: int) -> tuple[int, int]:
    """0-indexed [first, last] page range from the print dialog's page-range
    selection, or the full document if the operator left it on "All"."""
    if printer.printRange() == QPrinter.PrintRange.PageRange:
        from_page = printer.fromPage() or 1
        to_page = printer.toPage() or page_count
        return from_page - 1, min(to_page, page_count) - 1
    return 0, page_count - 1


def _apply_default_page_size(printer: QPrinter, document: QPdfDocument) -> None:
    """Set the printer's page size to match the PDF's own first-page
    dimensions, so the print dialog opens already matching the label size
    instead of the operator manually re-entering it each time. Still
    overridable by the operator inside the dialog."""
    size_pt = document.pagePointSize(0)
    if size_pt.isEmpty():
        return
    size_mm = QSizeF(size_pt.width() / 72 * 25.4, size_pt.height() / 72 * 25.4)
    printer.setPageSize(QPageSize(size_mm, QPageSize.Unit.Millimeter))


def _print_pdf_driver_mode(
    parent, pdf_path: Path, output_path: Path | None = None, driver_printer_name: str = ""
) -> bool:
    document = QPdfDocument()
    load_error = document.load(str(pdf_path))
    if load_error != QPdfDocument.Error.None_:
        QMessageBox.critical(parent, "Print Failed", f"Could not open PDF for printing:\n\n{pdf_path}\n\n{load_error}")
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if driver_printer_name:
        printer.setPrinterName(driver_printer_name)
    _apply_default_page_size(printer, document)

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
