"""
SKU Label Manager - Business logic for SKU label lookup and PDF printing.

Maps barcodes → SKUs → PDF label files. Handles label printing via
QPrinter + QPdfDocument (PySide6) or Windows Shell. Designed to run in Worker threads.
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
            "default_printer": "",
            "print_backend": "qt"   # "qt" (supersampling) | "shell" (Windows native)
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
        self._print_backend: str = config.get("print_backend", "qt")
        # Optional label size override in mm — used when the printer driver reports
        # an incorrect page size. Format: {"width": 62.0, "height": 100.0} or {}
        _lsz = config.get("label_size_mm", {})
        w = float(_lsz.get("width", 0) or 0)
        h = float(_lsz.get("height", 0) or 0)
        self._label_size_mm: tuple[float, float] | None = (w, h) if w > 0 and h > 0 else None
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

    @property
    def print_backend(self) -> str:
        """Active print backend: 'qt' or 'shell'."""
        return self._print_backend

    @print_backend.setter
    def print_backend(self, value: str):
        if value in ("qt", "shell"):
            self._print_backend = value
        else:
            logger.warning("Unknown print backend '%s', keeping '%s'", value, self._print_backend)

    @property
    def label_size_mm(self) -> tuple[float, float] | None:
        """Label size override as (width_mm, height_mm), or None to auto-detect from PDF."""
        return self._label_size_mm

    @label_size_mm.setter
    def label_size_mm(self, value: tuple[float, float] | None):
        self._label_size_mm = value

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

        if self._print_backend == "shell":
            return self._print_label_shell(pdf_path, copies, printer_name, sku)
        return self._print_label_qt(pdf_path, copies, printer_name, sku)

    # ------------------------------------------------------------------
    # Qt backend — supersampling for improved print quality
    # ------------------------------------------------------------------

    def _print_label_qt(self, pdf_path: str, copies: int, printer_name: str, sku: str) -> dict:
        """
        Print via QPrinter + QPdfDocument with 2× supersampling.

        Uses printer.pageRect(DevicePixel) as the authoritative target size — this
        matches the driver's configured label dimensions exactly. Renders the PDF at
        2× that size then downsamples with smooth interpolation (supersampling).

        If the driver reports an incorrect page size, set label_size_mm in config to
        override it before QPainter starts.
        """
        from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtGui import QPainter, QPageSize, QPageLayout, QImage
        from PySide6.QtCore import QSize, QSizeF, QMarginsF, Qt

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

        printer = QPrinter(target_info)
        printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
        printer.setCopyCount(copies)  # driver handles copies natively — no render loop needed

        # Override page size if the driver reports incorrect dimensions.
        # Default: derive from PDF page 0 so pageRect aligns with PDF content.
        if self._label_size_mm is not None:
            w_mm, h_mm = self._label_size_mm
        else:
            page_size_pt = doc.pagePointSize(0)
            w_mm = page_size_pt.width() / 72.0 * 25.4
            h_mm = page_size_pt.height() / 72.0 * 25.4
        printer.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter))
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        logger.debug(
            "Qt print: page size set to %.1f×%.1f mm (%s)",
            w_mm, h_mm, "config override" if self._label_size_mm else "from PDF"
        )

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
            # Force 1:1 logical-to-device-pixel mapping so drawImage has no hidden rescale.
            # By default QPainter on QPrinter uses a point-based logical coordinate system
            # (1 unit = 1/72 inch), which causes Qt to stretch any image drawn at pixel sizes.
            vp = painter.viewport()
            painter.setWindow(vp)
            target_w = max(1, vp.width())
            target_h = max(1, vp.height())
            logger.debug("Qt print: viewport %d×%d px", target_w, target_h)

            for page_idx in range(page_count):
                # Render at 2× for high-quality anti-aliased source.
                image_hi = doc.render(page_idx, QSize(target_w * 2, target_h * 2))

                # Remove premultiplied alpha — QPrinter composites ARGB32_Premultiplied
                # incorrectly, causing pale/washed-out output.
                image_rgb = image_hi.convertToFormat(QImage.Format.Format_RGB32)

                # Downsample to printer DPI with smooth interpolation.
                image_scaled = image_rgb.scaled(
                    target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                )

                # Convert to 1-bit with threshold (no halftoning).
                # Thermal printers are binary (dot/no-dot). Sending a grayscale image causes
                # the driver to apply a halftone dot pattern. ThresholdDither snaps each pixel
                # to pure black or white — the driver receives 1-bit data and prints it directly.
                image_mono = image_scaled.convertToFormat(
                    QImage.Format.Format_Mono,
                    Qt.ImageConversionFlag.ThresholdDither,
                )

                painter.drawImage(0, 0, image_mono)
                pages_printed += 1

                if page_idx < page_count - 1:
                    printer.newPage()

        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Qt print error for SKU '%s'", sku)
        finally:
            painter.end()
            doc.close()

        if error_msg:
            return {"success": False, "pages_printed": pages_printed, "error": error_msg}

        logger.info(
            "Printed %d page(s) for SKU '%s' (%d cop%s) via Qt to '%s'",
            pages_printed, sku, copies, "y" if copies == 1 else "ies", printer_name,
        )
        return {"success": True, "pages_printed": pages_printed, "error": None}

    # ------------------------------------------------------------------
    # Shell backend — Windows native PDF printing (identical to manual print)
    # ------------------------------------------------------------------

    def _print_label_shell(self, pdf_path: str, copies: int, printer_name: str, sku: str) -> dict:
        """
        Print via Windows ShellExecute 'printto' verb.

        Delegates to Windows' default PDF handler (Edge, Adobe Reader, etc.) — exactly
        the same rendering path as manually opening the PDF and clicking Print.
        For copies > 1, uses pypdf to assemble a temp PDF with repeated pages.
        Fire-and-forget: returns success once the job is handed to the shell.
        """
        import ctypes
        import os
        import tempfile
        import threading
        import time

        from pypdf import PdfReader, PdfWriter

        # Build temp PDF with N copies of all pages
        tmp_path = None
        try:
            reader = PdfReader(pdf_path)
            pages = list(reader.pages)
            page_count = len(pages)
            writer = PdfWriter()
            for _ in range(copies):
                for page in pages:
                    writer.add_page(page)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                writer.write(tmp)
        except Exception as exc:
            logger.exception("Shell print: failed to build temp PDF for SKU '%s'", sku)
            return {
                "success": False,
                "pages_printed": 0,
                "error": f"Failed to prepare print file: {exc}",
            }

        # ShellExecute "printto" — Windows routes to default PDF viewer → printer
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "printto", tmp_path, f'"{printer_name}"', None, 0
            )
        except Exception as exc:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            logger.exception("ShellExecute failed for SKU '%s'", sku)
            return {"success": False, "pages_printed": 0, "error": f"ShellExecute failed: {exc}"}

        if result <= 32:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return {
                "success": False,
                "pages_printed": 0,
                "error": (
                    f"Windows Shell print failed (code {result}). "
                    "Ensure a PDF viewer (Edge, Adobe Reader) is installed."
                ),
            }

        # Schedule temp file cleanup — give PDF viewer time to spool the job
        def _cleanup():
            time.sleep(15)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()

        total_pages = page_count * copies
        logger.info(
            "Sent %d page(s) for SKU '%s' (%d cop%s) to '%s' via Windows Shell",
            total_pages, sku, copies, "y" if copies == 1 else "ies", printer_name,
        )
        return {"success": True, "pages_printed": total_pages, "error": None}
