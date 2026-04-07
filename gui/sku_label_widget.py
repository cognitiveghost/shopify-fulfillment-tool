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
    QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFormLayout,
    QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QThreadPool, QTimer

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

        # Debounce timer for label size saves — avoids a network write per keystroke
        self._label_size_save_timer = QTimer(self)
        self._label_size_save_timer.setSingleShot(True)
        self._label_size_save_timer.setInterval(1000)
        self._label_size_save_timer.timeout.connect(self._flush_label_size_save)

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

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Qt Supersampling", userData="qt")
        self.backend_combo.addItem("Windows Native (Shell)", userData="shell")
        self.backend_combo.setToolTip(
            "Qt Supersampling: renders at 2× DPI then downsamples — no extra software needed.\n"
            "Windows Native: uses your PDF viewer (Edge/Adobe) — identical quality to manual print."
        )
        form.addRow("Print Engine:", self.backend_combo)

        # Label size override — Qt mode only. Leave at 0×0 to auto-detect from PDF.
        size_row = QHBoxLayout()
        self.label_width_spin = QDoubleSpinBox()
        self.label_width_spin.setRange(0, 500)
        self.label_width_spin.setDecimals(1)
        self.label_width_spin.setSuffix(" mm")
        self.label_width_spin.setSpecialValueText("auto")
        self.label_width_spin.setMinimumWidth(90)
        self.label_height_spin = QDoubleSpinBox()
        self.label_height_spin.setRange(0, 500)
        self.label_height_spin.setDecimals(1)
        self.label_height_spin.setSuffix(" mm")
        self.label_height_spin.setSpecialValueText("auto")
        self.label_height_spin.setMinimumWidth(90)
        size_row.addWidget(self.label_width_spin)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.label_height_spin)
        size_row.addStretch()
        form.addRow("Label Size (Qt):", size_row)

        layout.addLayout(form)

        self.print_btn = QPushButton("Print Label")
        self.print_btn.setMinimumHeight(44)
        theme = get_theme_manager().get_current_theme()
        self.print_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size: 15px; font-weight: bold;"
            f"  background-color: {theme.accent_green}; color: white; border-radius: 5px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {theme.accent_green}; }}"
            f"QPushButton:disabled {{ background-color: {theme.border}; color: {theme.text_secondary}; }}"
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
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        self.label_width_spin.editingFinished.connect(self._on_label_size_changed)
        self.label_height_spin.editingFinished.connect(self._on_label_size_changed)

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

        # Sync backend combo to saved preference without triggering the save handler
        backend = config.get("print_backend", "qt")
        idx = self.backend_combo.findData(backend)
        self.backend_combo.blockSignals(True)
        self.backend_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.backend_combo.blockSignals(False)

        # Sync label size override fields
        lsz = config.get("label_size_mm", {}) or {}
        for spin, key in ((self.label_width_spin, "width"), (self.label_height_spin, "height")):
            spin.blockSignals(True)
            spin.setValue(float(lsz.get(key, 0) or 0))
            spin.blockSignals(False)

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

            # Priority: current in-session selection → config default → system default
            config_default = self._manager.default_printer if self._manager else ""
            for candidate in (current, config_default, default_name):
                if candidate:
                    idx = self.printer_combo.findText(candidate)
                    if idx >= 0:
                        self.printer_combo.setCurrentIndex(idx)
                        break

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
            logger.info("Print success: %d pages for SKU '%s'", pages, self._current_sku)
            self._on_clear_clicked()
            self._set_scan_status(f"Printed {pages} page(s). Ready — scan next product.")
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

    def _on_backend_changed(self, _: int):
        backend = self.backend_combo.currentData() or "qt"
        if self._manager is not None:
            self._manager.print_backend = backend
        self._save_sku_label_config("print_backend", backend)

    def _on_label_size_changed(self):
        w = self.label_width_spin.value()
        h = self.label_height_spin.value()
        if self._manager is not None:
            self._manager.label_size_mm = (w, h) if w > 0 and h > 0 else None
        # Debounce: wait 1s after last edit before writing to file server
        self._label_size_save_timer.start()

    def _flush_label_size_save(self):
        w = self.label_width_spin.value()
        h = self.label_height_spin.value()
        lsz = {"width": w, "height": h} if w > 0 and h > 0 else {}
        self._save_sku_label_config("label_size_mm", lsz)

    def _save_sku_label_config(self, key: str, value) -> None:
        """Update one key in sku_label_config and persist to file server."""
        if not hasattr(self.mw, "active_profile_config") or not self.mw.active_profile_config:
            return
        try:
            self.mw.active_profile_config.setdefault("sku_label_config", {})[key] = value
            if (
                hasattr(self.mw, "profile_manager")
                and hasattr(self.mw, "current_client_id")
                and self.mw.current_client_id
            ):
                self.mw.profile_manager.save_shopify_config(
                    self.mw.current_client_id, self.mw.active_profile_config
                )
        except Exception:
            logger.exception("Failed to save sku_label_config['%s']", key)

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
        color = theme.accent_red if error else theme.text_secondary
        self.scan_status_label.setText(text)
        self.scan_status_label.setStyleSheet(f"color: {color}; font-style: italic;")

    def _set_print_status(self, text: str, *, success: bool = False, error: bool = False):
        theme = get_theme_manager().get_current_theme()
        if success:
            color = theme.accent_green
        elif error:
            color = theme.accent_red
        else:
            color = theme.text_secondary
        self.print_status_label.setText(text)
        self.print_status_label.setStyleSheet(f"color: {color};")
