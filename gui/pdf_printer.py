"""
Shared PDF printing utilities for barcode and reference-label widgets.
"""
from pathlib import Path


def populate_printer_combo(combo, log) -> None:
    """Populate *combo* with available Windows printer names.

    Tries to preserve the previously selected printer; falls back to the
    system default.  Silently degrades if QtPrintSupport is unavailable.
    """
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        current = combo.currentText()
        combo.clear()
        printers = QPrinterInfo.availablePrinters()
        if not printers:
            combo.addItem("(no printers found)")
            return
        default_name = QPrinterInfo.defaultPrinter().printerName()
        for pi in printers:
            combo.addItem(pi.printerName())
        for candidate in (current, default_name):
            if candidate:
                idx = combo.findText(candidate)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    break
    except Exception as exc:
        log.warning(f"Failed to enumerate printers: {exc}")


def print_pdf_to_printer(pdf_path, printer_name: str) -> dict:
    """Render every page of *pdf_path* and send it to *printer_name*.

    Designed to be called from a background worker (no Qt widget access).
    Returns ``{"success": True, "pages_printed": N}`` on success or
    ``{"success": False, "error": "<message>"}`` on failure.
    """
    from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtGui import QPainter
    from PySide6.QtCore import QSize, QRectF

    # Locate the QPrinterInfo for the chosen printer so we can pass it to
    # QPrinter — this gives the native driver rather than the generic path.
    target_info = next(
        (pi for pi in QPrinterInfo.availablePrinters() if pi.printerName() == printer_name),
        None,
    )
    if target_info is None:
        return {"success": False, "error": f"Printer not found: '{printer_name}'"}

    doc = QPdfDocument(None)
    doc.load(str(pdf_path))
    page_count = doc.pageCount()
    if page_count == 0:
        doc.close()
        return {"success": False, "error": "PDF has no pages or could not be loaded"}

    printer = QPrinter(target_info)
    printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
    painter = QPainter()
    if not painter.begin(printer):
        doc.close()
        return {"success": False, "error": f"Failed to begin printing to '{printer_name}'"}

    try:
        dpi = printer.resolution()
        page_rect = printer.pageRect(QPrinter.DevicePixel)
        target_rect = QRectF(page_rect)
        for page_idx in range(page_count):
            page_size_pt = doc.pagePointSize(page_idx)
            render_w = max(1, int(page_size_pt.width() / 72.0 * dpi))
            render_h = max(1, int(page_size_pt.height() / 72.0 * dpi))
            image = doc.render(page_idx, QSize(render_w, render_h))
            painter.drawImage(target_rect, image)
            if page_idx < page_count - 1:
                printer.newPage()
        return {"success": True, "pages_printed": page_count}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        painter.end()
        doc.close()
