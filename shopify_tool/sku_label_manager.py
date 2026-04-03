"""
SKU Label Manager - Business logic for SKU label lookup and PDF printing.

Maps barcodes → SKUs → PDF label files. Handles label printing via
QPrinter + QPdfDocument (PySide6). Designed to run in Worker threads.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SKULabelManager:
    """Manages SKU-to-label mappings and PDF printing.

    Config schema (sku_label_config section):
        {
            "sku_to_label": {
                "SKU001": {
                    "barcodes": ["1234567890", "0987654321"],
                    "pdf_path": "\\\\SERVER\\Share\\Labels\\sku001.pdf"
                }
            },
            "default_printer": ""
        }
    """

    def __init__(self, config: dict):
        """
        Initialize with sku_label_config section from client config.

        Args:
            config: The sku_label_config dict from shopify_config.json
        """
        self._sku_to_label: dict = config.get("sku_to_label", {})
        self._default_printer: str = config.get("default_printer", "")
        self._barcode_index: dict[str, str] = self._build_barcode_index()

    def _build_barcode_index(self) -> dict:
        """Build reverse lookup index: barcode string → sku string."""
        index = {}
        for sku, entry in self._sku_to_label.items():
            for barcode in entry.get("barcodes", []):
                barcode = barcode.strip()
                if barcode:
                    if barcode in index:
                        logger.warning(
                            "Duplicate barcode '%s' maps to both '%s' and '%s' — using '%s'",
                            barcode, index[barcode], sku, index[barcode]
                        )
                    else:
                        index[barcode] = sku
        return index

    def lookup_by_barcode(self, barcode: str) -> dict | None:
        """
        Look up label entry by scanned barcode.

        Args:
            barcode: Scanned barcode string (stripped automatically)

        Returns:
            Dict with 'sku' and 'pdf_path', or None if not found
        """
        sku = self._barcode_index.get(barcode.strip())
        if sku is None:
            return None
        entry = self._sku_to_label.get(sku, {})
        return {
            "sku": sku,
            "pdf_path": entry.get("pdf_path", ""),
        }

    def lookup_fulfillable_qty(self, sku: str, analysis_df) -> int:
        """
        Get fulfillable quantity for a SKU from the current session analysis.

        Args:
            sku: SKU to look up
            analysis_df: Current session's analysis DataFrame (may be None)

        Returns:
            Sum of Quantity for Fulfillable rows matching this SKU, or 1 as fallback
        """
        try:
            if analysis_df is None or analysis_df.empty:
                return 1
            required_cols = {"SKU", "Order_Fulfillment_Status", "Quantity"}
            if not required_cols.issubset(analysis_df.columns):
                return 1
            mask = (
                (analysis_df["SKU"] == sku) &
                (analysis_df["Order_Fulfillment_Status"] == "Fulfillable")
            )
            qty = analysis_df.loc[mask, "Quantity"].sum()
            return int(qty) if qty > 0 else 1
        except Exception:
            logger.exception("Error looking up fulfillable qty for SKU: %s", sku)
            return 1

    def get_all_mappings(self) -> dict:
        """Return the full sku_to_label mapping dict (read-only reference)."""
        return self._sku_to_label

    @property
    def default_printer(self) -> str:
        """Saved default printer name from config."""
        return self._default_printer

    def print_label(self, sku: str, copies: int, printer_name: str) -> dict:
        """
        Print the PDF label for a SKU N times to the specified printer.

        Runs safely in a Worker (QRunnable) background thread — no UI objects created.

        Args:
            sku: SKU whose label PDF to print
            copies: Number of copies to print
            printer_name: Windows printer name as returned by QPrinterInfo

        Returns:
            Dict: {'success': bool, 'pages_printed': int, 'error': str|None}
        """
        from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QSize, QRectF

        entry = self._sku_to_label.get(sku)
        if not entry:
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"No label configured for SKU: {sku}",
            }

        pdf_path = entry.get("pdf_path", "")
        if not pdf_path or not Path(pdf_path).exists():
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"PDF file not found: {pdf_path}",
            }

        # Find the target printer by name
        target_info = None
        for pi in QPrinterInfo.availablePrinters():
            if pi.printerName() == printer_name:
                target_info = pi
                break

        if target_info is None:
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"Printer not found: '{printer_name}'",
            }

        # Load PDF document
        doc = QPdfDocument(None)
        doc.load(pdf_path)

        page_count = doc.pageCount()
        if page_count == 0:
            doc.close()
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"PDF has no pages or could not be loaded: {pdf_path}",
            }

        # Create printer and painter
        printer = QPrinter(target_info)
        printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)

        painter = QPainter()
        if not painter.begin(printer):
            doc.close()
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"Failed to begin printing to '{printer_name}'",
            }

        pages_printed = 0
        error_msg = None

        try:
            dpi = printer.resolution()
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            target_rect = QRectF(page_rect)

            for copy_idx in range(copies):
                for page_idx in range(page_count):
                    # Render PDF page to QImage at printer DPI
                    page_size_pt = doc.pagePointSize(page_idx)
                    render_w = max(1, int(page_size_pt.width() / 72.0 * dpi))
                    render_h = max(1, int(page_size_pt.height() / 72.0 * dpi))
                    image = doc.render(page_idx, QSize(render_w, render_h))

                    painter.drawImage(target_rect, image)
                    pages_printed += 1

                    is_last = (copy_idx == copies - 1) and (page_idx == page_count - 1)
                    if not is_last:
                        printer.newPage()

        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Print error for SKU '%s'", sku)
        finally:
            painter.end()
            doc.close()

        if error_msg:
            return {"success": False, "pages_printed": pages_printed, "error": error_msg}

        logger.info(
            "Printed %d page(s) for SKU '%s' (%d cop%s) to '%s'",
            pages_printed, sku, copies, "y" if copies == 1 else "ies", printer_name,
        )
        return {"success": True, "pages_printed": pages_printed, "error": None}
