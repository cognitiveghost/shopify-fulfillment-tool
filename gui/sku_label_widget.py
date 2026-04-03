"""
SKU Label Widget - Tab for scanning barcodes and printing SKU PDF labels.

Workflow:
  1. User scans a barcode (or types and presses Enter)
  2. App looks up the SKU from the barcode mapping
  3. Fulfillable quantity from the current session is pre-filled
  4. User adjusts copy count if needed, selects printer, and prints
  5. After successful print the form auto-clears for the next scan
"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QSpinBox, QComboBox, QFormLayout,
    QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QThreadPool

from gui.worker import Worker
from gui.theme_manager import get_theme_manager
from shopify_tool.sku_label_manager import SKULabelManager

logger = logging.getLogger(__name__)

_NO_PRINTERS = "(no printers found)"
_READY_MSG = "Ready — scan a product"
_NO_CLIENT_MSG = "No active client — load a session first"


class SKULabelWidget(QWidget):
    """Tab widget for barcode-scan-to-print labeling workflow."""

    def __init__(self, main_window, parent=None):
        """
        Initialize SKU Label widget.

        Args:
            main_window: MainWindow instance for accessing session data and config
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self._manager: SKULabelManager | None = None
        self._current_sku: str | None = None

        self._init_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        """Build the layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        layout.addWidget(self._create_scan_section())
        layout.addWidget(self._create_result_section())
        layout.addWidget(self._create_print_section())
        layout.addStretch()

    def _create_scan_section(self) -> QGroupBox:
        """Barcode input section."""
        group = QGroupBox("Barcode Scan")
        layout = QVBoxLayout(group)

        theme = get_theme_manager().get_current_theme()

        input_row = QHBoxLayout()
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type barcode and press Enter...")
        self.barcode_input.setMinimumHeight(36)
        self.barcode_input.setStyleSheet("font-size: 13px;")
        input_row.addWidget(self.barcode_input, 1)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.setToolTip("Reset form and return focus to barcode input")
        input_row.addWidget(self.clear_btn)

        layout.addLayout(input_row)

        self.scan_status_label = QLabel(_READY_MSG)
        self.scan_status_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        layout.addWidget(self.scan_status_label)

        return group

    def _create_result_section(self) -> QGroupBox:
        """Resolved SKU info section."""
        group = QGroupBox("Resolved SKU")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        theme = get_theme_manager().get_current_theme()

        self.sku_value_label = QLabel("—")
        self.sku_value_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        form.addRow("SKU:", self.sku_value_label)

        self.fulfillable_value_label = QLabel("—")
        self.fulfillable_value_label.setStyleSheet(
            f"font-size: 13px; color: {theme.text_secondary};"
        )
        form.addRow("Fulfillable (session):", self.fulfillable_value_label)

        return group

    def _create_print_section(self) -> QGroupBox:
        """Print controls section."""
        group = QGroupBox("Print")
        layout = QVBoxLayout(group)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.copies_spinbox = QSpinBox()
        self.copies_spinbox.setRange(1, 999)
        self.copies_spinbox.setValue(1)
        self.copies_spinbox.setMinimumWidth(100)
        form.addRow("Copies:", self.copies_spinbox)

        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumWidth(250)
        self.printer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form.addRow("Printer:", self.printer_combo)

        layout.addLayout(form)

        self.print_btn = QPushButton("Print Label")
        self.print_btn.setMinimumHeight(44)
        self.print_btn.setStyleSheet(
            "QPushButton {"
            "  font-size: 15px; font-weight: bold;"
            "  background-color: #4CAF50; color: white; border-radius: 5px;"
            "}"
            "QPushButton:hover { background-color: #45a049; }"
            "QPushButton:disabled { background-color: #888; color: #ccc; }"
        )
        self.print_btn.setEnabled(False)
        layout.addWidget(self.print_btn)

        self.print_status_label = QLabel("")
        self.print_status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.print_status_label)

        return group

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.barcode_input.returnPressed.connect(self._on_barcode_submitted)
        self.print_btn.clicked.connect(self._on_print_clicked)
        self.clear_btn.clicked.connect(self._on_clear_clicked)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event):
        """Refresh state when tab becomes visible."""
        super().showEvent(event)
        self._refresh_manager()
        self._refresh_printers()
        self.barcode_input.setFocus()

    # ------------------------------------------------------------------
    # State Management
    # ------------------------------------------------------------------

    def _refresh_manager(self):
        """Rebuild the SKULabelManager from the current client config."""
        if not hasattr(self.mw, "active_profile_config") or not self.mw.active_profile_config:
            self._manager = None
            self._set_scan_status(_NO_CLIENT_MSG, error=True)
            return

        config = self.mw.active_profile_config.get("sku_label_config", {})
        self._manager = SKULabelManager(config)

        # Restore saved default printer
        saved_printer = config.get("default_printer", "")
        if saved_printer:
            idx = self.printer_combo.findText(saved_printer)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

        self._set_scan_status(_READY_MSG)

    def _refresh_printers(self):
        """Populate printer combo from available Windows printers."""
        try:
            from PySide6.QtPrintSupport import QPrinterInfo

            current = self.printer_combo.currentText()
            self.printer_combo.clear()

            printers = QPrinterInfo.availablePrinters()
            if not printers:
                self.printer_combo.addItem(_NO_PRINTERS)
                return

            default_name = QPrinterInfo.defaultPrinter().printerName()
            for pi in printers:
                self.printer_combo.addItem(pi.printerName())

            # Restore previous selection or system default
            idx = self.printer_combo.findText(current) if current else -1
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)
            elif default_name:
                idx = self.printer_combo.findText(default_name)
                if idx >= 0:
                    self.printer_combo.setCurrentIndex(idx)

        except Exception:
            logger.exception("Failed to enumerate printers")

    # ------------------------------------------------------------------
    # Scan Handling
    # ------------------------------------------------------------------

    def _on_barcode_submitted(self):
        """Handle barcode scan / Enter key press."""
        raw = self.barcode_input.text().strip()
        if not raw:
            return

        if self._manager is None:
            self._set_scan_status(_NO_CLIENT_MSG, error=True)
            return

        result = self._manager.lookup_by_barcode(raw)
        if result is None:
            self._set_scan_status(f"Barcode not found: {raw}", error=True)
            self.barcode_input.selectAll()
            self._clear_product_info()
            return

        sku = result["sku"]
        self._current_sku = sku

        # Update product info
        self.sku_value_label.setText(sku)

        # Fulfillable qty from session
        analysis_df = getattr(self.mw, "analysis_results_df", None)
        qty = self._manager.lookup_fulfillable_qty(sku, analysis_df)
        self.fulfillable_value_label.setText(str(qty))
        self.copies_spinbox.setValue(qty)

        # Enable printing
        self.print_btn.setEnabled(True)
        self.print_status_label.setText("")
        self._set_scan_status(f"Found: {sku}")

        # Clear input for next scan
        self.barcode_input.clear()

    # ------------------------------------------------------------------
    # Print Handling
    # ------------------------------------------------------------------

    def _on_print_clicked(self):
        """Start background print job."""
        if self._current_sku is None or self._manager is None:
            return

        printer_name = self.printer_combo.currentText()
        if not printer_name or printer_name == _NO_PRINTERS:
            QMessageBox.warning(self, "No Printer Selected", "Please select a printer.")
            return

        sku = self._current_sku
        copies = self.copies_spinbox.value()
        copy_word = "copy" if copies == 1 else "copies"

        self.print_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._set_print_status(f"Printing {copies} {copy_word} for {sku}...")

        worker = Worker(self._manager.print_label, sku, copies, printer_name)
        worker.signals.result.connect(self._on_print_result)
        worker.signals.error.connect(self._on_print_error)
        worker.signals.finished.connect(self._on_print_finished)
        QThreadPool.globalInstance().start(worker)

    def _on_print_result(self, result: dict):
        """Handle print job result."""
        if result["success"]:
            pages = result["pages_printed"]
            self._set_print_status(f"Printed {pages} page(s) successfully.", success=True)
            logger.info("Print success: %d pages for SKU '%s'", pages, self._current_sku)
            # Auto-clear after successful print
            self._on_clear_clicked()
        else:
            err = result.get("error", "Unknown error")
            self._set_print_status(f"Error: {err}", error=True)
            QMessageBox.critical(
                self,
                "Print Error",
                f"Failed to print label:\n\n{err}",
            )

    def _on_print_error(self, error_info: tuple):
        """Handle unexpected Worker exception."""
        _, value, _ = error_info
        self._set_print_status(f"Error: {value}", error=True)
        QMessageBox.critical(
            self,
            "Print Error",
            f"Unexpected error:\n\n{value}",
        )
        logger.error("Unexpected print worker error: %s", value)

    def _on_print_finished(self):
        """Re-enable controls after print job completes."""
        self.print_btn.setEnabled(self._current_sku is not None)
        self.clear_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Clear / Reset
    # ------------------------------------------------------------------

    def _on_clear_clicked(self):
        """Reset the form and return focus to barcode input."""
        self._current_sku = None
        self.barcode_input.clear()
        self._clear_product_info()
        self.copies_spinbox.setValue(1)
        self.print_btn.setEnabled(False)
        self.print_status_label.setText("")
        self._set_scan_status(_READY_MSG)
        self.barcode_input.setFocus()

    def _clear_product_info(self):
        """Clear resolved SKU info panel."""
        self.sku_value_label.setText("—")
        self.fulfillable_value_label.setText("—")

    # ------------------------------------------------------------------
    # Status Helpers
    # ------------------------------------------------------------------

    def _set_scan_status(self, text: str, *, error: bool = False):
        theme = get_theme_manager().get_current_theme()
        color = "#e53935" if error else theme.text_secondary
        self.scan_status_label.setText(text)
        self.scan_status_label.setStyleSheet(f"color: {color}; font-style: italic;")

    def _set_print_status(self, text: str, *, success: bool = False, error: bool = False):
        if success:
            color = "#43a047"
        elif error:
            color = "#e53935"
        else:
            theme = get_theme_manager().get_current_theme()
            color = theme.text_secondary
        self.print_status_label.setText(text)
        self.print_status_label.setStyleSheet(f"color: {color};")
