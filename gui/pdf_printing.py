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
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
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
