"""
Barcode Generator Widget - Generate warehouse barcode labels from packing lists.

Features:
- Select packing list to generate barcodes for
- Shows order count preview
- Background generation with progress tracking
- History table with thumbnails
- Open barcodes folder
- Export to PDF
"""

import logging
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.pdf_printing import (
    load_print_settings,
    print_pdf,
    save_print_settings,
)
from gui.theme_manager import font_css, get_theme_manager
from gui.worker import Worker


class BarcodeGeneratorWidget(QWidget):
    """Widget for generating barcode labels from packing lists."""

    # Signal emitted when generation completes
    generation_complete = Signal(dict)

    def __init__(self, main_window, parent=None):
        """
        Initialize Barcode Generator widget.

        Args:
            main_window: MainWindow instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self.log = logging.getLogger(__name__)

        # Current state
        self.current_packing_list = None
        self.filtered_orders_df = None
        self.barcodes_dir = None
        self.last_barcode_pdf = None
        self.last_qr_pdf = None

        self._init_ui()
        self._connect_signals()
        self._update_state()

    def _init_ui(self):
        """Initialize UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Section 1: Packing List Selection
        layout.addWidget(self._create_packing_list_section())

        # Section 2: Options
        layout.addWidget(self._create_options_section())

        # Section 3: Generation
        layout.addWidget(self._create_generation_section())

        # Spacer to push content to top
        layout.addStretch()

    def _create_packing_list_section(self):
        """Create packing list selection section."""
        group = QGroupBox("Packing List Selection")
        layout = QVBoxLayout(group)

        # Packing list dropdown
        list_row = QHBoxLayout()
        list_row.addWidget(QLabel("Select Packing List:"))

        self.packing_list_combo = QComboBox()
        self.packing_list_combo.setMinimumWidth(250)
        list_row.addWidget(self.packing_list_combo, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.setToolTip("Refresh packing lists")
        refresh_btn.clicked.connect(self._refresh_packing_lists)
        list_row.addWidget(refresh_btn)

        layout.addLayout(list_row)

        # Order count preview
        self.order_count_label = QLabel("No packing list selected")
        theme = get_theme_manager().get_current_theme()
        self.order_count_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; padding: 5px;")
        layout.addWidget(self.order_count_label)

        # Info label
        info_label = QLabel(
            "Barcodes will be generated for all Fulfillable orders in the selected packing list.\n"
            "Each packing list has its own barcode folder for organization."
        )
        info_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')} padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return group

    def _create_options_section(self):
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Add QR labels checkbox
        self.add_qr_checkbox = QCheckBox("Add QR labels (order number)")
        self.add_qr_checkbox.setChecked(False)
        layout.addWidget(self.add_qr_checkbox)

        # Auto-open PDF checkbox
        self.auto_open_pdf_checkbox = QCheckBox("Auto-open PDF after generation")
        self.auto_open_pdf_checkbox.setChecked(True)
        layout.addWidget(self.auto_open_pdf_checkbox)

        # Output directory label
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output:"))
        self.output_dir_label = QLabel("No packing list selected")
        theme = get_theme_manager().get_current_theme()
        self.output_dir_label.setStyleSheet(f"font-weight: bold; color: {theme.text_secondary};")
        self.output_dir_label.setWordWrap(True)
        output_row.addWidget(self.output_dir_label, 1)
        layout.addLayout(output_row)

        # Printing (raw ZPL target/rotate only relevant when that mode is selected)
        print_settings = load_print_settings("barcode_generator")

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

        # This flow's own template is always authored at 68x38mm, so fitting
        # is mostly a safety net here (unlike Reference Labels, where the
        # source PDF's page size is a courier's and can't be trusted) -- set
        # it to match whatever label stock is actually loaded if it ever
        # changes. 0 (default) keeps using the template's own page size.
        label_size_row = QHBoxLayout()
        label_size_row.addWidget(QLabel("Fit to label size (mm):"))
        self.raw_zpl_label_width_spin = QDoubleSpinBox()
        self.raw_zpl_label_width_spin.setRange(0.0, 500.0)
        self.raw_zpl_label_width_spin.setDecimals(1)
        self.raw_zpl_label_width_spin.setSpecialValueText("(use PDF page size)")
        self.raw_zpl_label_width_spin.setValue(print_settings["raw_zpl_label_width_mm"])
        self.raw_zpl_label_width_spin.setToolTip(
            "Physical label width as loaded in the printer, e.g. 68 for this "
            "flow's default label stock. 0 disables fitting and uses the "
            "generated PDF's own page size."
        )
        label_size_row.addWidget(self.raw_zpl_label_width_spin)
        label_size_row.addWidget(QLabel("x"))
        self.raw_zpl_label_height_spin = QDoubleSpinBox()
        self.raw_zpl_label_height_spin.setRange(0.0, 500.0)
        self.raw_zpl_label_height_spin.setDecimals(1)
        self.raw_zpl_label_height_spin.setSpecialValueText("(use PDF page size)")
        self.raw_zpl_label_height_spin.setValue(print_settings["raw_zpl_label_height_mm"])
        self.raw_zpl_label_height_spin.setToolTip(self.raw_zpl_label_width_spin.toolTip())
        label_size_row.addWidget(self.raw_zpl_label_height_spin)
        layout.addLayout(label_size_row)

        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Default printer (driver mode):"))
        self.driver_printer_combo = QComboBox()
        self.driver_printer_combo.addItem("(Windows default)", "")
        for info in QPrinterInfo.availablePrinters():
            self.driver_printer_combo.addItem(info.printerName(), info.printerName())
        printer_index = self.driver_printer_combo.findData(print_settings["driver_printer_name"])
        if printer_index >= 0:
            self.driver_printer_combo.setCurrentIndex(printer_index)
        printer_row.addWidget(self.driver_printer_combo, 1)
        layout.addLayout(printer_row)

        def _update_zpl_controls_enabled():
            is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
            self.raw_zpl_target_edit.setEnabled(is_zpl)
            self.raw_zpl_rotate_check.setEnabled(is_zpl)
            self.raw_zpl_label_width_spin.setEnabled(is_zpl)
            self.raw_zpl_label_height_spin.setEnabled(is_zpl)
            self.driver_printer_combo.setEnabled(not is_zpl)

        _update_zpl_controls_enabled()
        self.print_mode_combo.currentIndexChanged.connect(_update_zpl_controls_enabled)
        self.print_mode_combo.currentIndexChanged.connect(self._save_print_settings)
        self.raw_zpl_target_edit.editingFinished.connect(self._save_print_settings)
        self.raw_zpl_rotate_check.toggled.connect(self._save_print_settings)
        self.raw_zpl_label_width_spin.editingFinished.connect(self._save_print_settings)
        self.raw_zpl_label_height_spin.editingFinished.connect(self._save_print_settings)
        self.driver_printer_combo.currentIndexChanged.connect(self._save_print_settings)

        return group

    def _create_generation_section(self):
        """Create generation section."""
        group = QGroupBox("Generate Barcodes")
        layout = QVBoxLayout(group)

        # Generate button
        self.generate_btn = QPushButton("Generate Barcode Labels")
        self.generate_btn.setMinimumHeight(50)
        theme = get_theme_manager().get_current_theme()
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                {font_css('label')}
                background-color: {theme.status_success};
                color: {theme.on_accent};
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {theme.status_success};
            }}
            QPushButton:disabled {{
                background-color: {theme.border};
                color: {theme.text_secondary};
            }}
        """)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_btn)

        self.print_btn = QPushButton("Print...")
        self.print_btn.setEnabled(False)
        layout.addWidget(self.print_btn)

        self.print_qr_btn = QPushButton("Print QR labels...")
        self.print_qr_btn.setEnabled(False)
        layout.addWidget(self.print_qr_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Select a packing list to begin")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.status_label)

        return group


    def showEvent(self, event):
        """Override showEvent to refresh packing lists when tab becomes visible."""
        super().showEvent(event)
        # Auto-refresh packing lists when user switches to this tab
        if self.mw.session_path:
            self._refresh_packing_lists()
            self.log.debug("Auto-refreshed packing lists on tab switch")

    def _connect_signals(self):
        """Connect signals and slots."""
        self.packing_list_combo.currentIndexChanged.connect(self._on_packing_list_changed)
        self.print_btn.clicked.connect(self._on_print_clicked)
        self.print_qr_btn.clicked.connect(self._on_print_qr_clicked)

    def _update_state(self):
        """Update widget state based on current session."""
        if not self.mw.session_path:
            self.packing_list_combo.clear()
            self.order_count_label.setText("No session selected")
            self.output_dir_label.setText("No session selected")
            self.status_label.setText("No session selected")
            self.generate_btn.setEnabled(False)
            return

        # Refresh packing lists
        self._refresh_packing_lists()

    def _refresh_packing_lists(self):
        """Refresh available packing lists from session."""
        if not self.mw.session_path:
            return

        self.packing_list_combo.clear()

        # Scan packing_lists directory for generated lists
        packing_lists_dir = Path(self.mw.session_path) / "packing_lists"

        if not packing_lists_dir.exists():
            self.order_count_label.setText("No packing lists found")
            self.log.warning(f"Packing lists directory not found: {packing_lists_dir}")
            return

        # Find all .xlsx files (packing lists are Excel files)
        # Note: .json files are also created but we only need .xlsx for UI
        packing_files = list(packing_lists_dir.glob("*.xlsx"))

        if not packing_files:
            self.order_count_label.setText("No packing lists generated yet")
            self.log.info("No packing list files found in session")
            return

        # Get unique packing list names (avoid duplicates from .xlsx/.json)
        unique_names = {}
        for file in sorted(packing_files):
            # Remove file extension for display name
            display_name = file.stem
            if display_name not in unique_names:
                unique_names[display_name] = file

        # Add to combo box
        for display_name, file_path in sorted(unique_names.items()):
            self.packing_list_combo.addItem(display_name, file_path)

        self.log.info(f"Found {len(unique_names)} unique packing lists")

    def _on_packing_list_changed(self, index):
        """Handle packing list selection change."""
        if index < 0:
            self.current_packing_list = None
            self.filtered_orders_df = None
            self.barcodes_dir = None

            self.order_count_label.setText("No packing list selected")
            self.output_dir_label.setText("No packing list selected")
            self.generate_btn.setEnabled(False)
            return

        # Get selected packing list name and file path
        packing_list_name = self.packing_list_combo.currentText()
        packing_list_file = self.packing_list_combo.currentData()
        self.current_packing_list = packing_list_name

        self.log.info(f"Selected packing list: {packing_list_name}")

        if not hasattr(self.mw, 'analysis_results_df') or self.mw.analysis_results_df is None:
            self.order_count_label.setText("No analysis data loaded")
            self.log.warning("No analysis results DataFrame available")
            return

        # Read packing list Excel file to get order numbers
        try:
            packing_list_df = pd.read_excel(packing_list_file)

            # Get unique order numbers from packing list
            if 'Order_Number' not in packing_list_df.columns:
                self.order_count_label.setText("Invalid packing list format (missing Order_Number)")
                self.log.error(f"Packing list missing Order_Number column: {packing_list_file}")
                return

            packing_list_orders = set(packing_list_df['Order_Number'].unique())

            # Filter analysis results to only orders in this packing list
            # AND that are Fulfillable
            filtered_df = self.mw.analysis_results_df[
                (self.mw.analysis_results_df['Order_Number'].isin(packing_list_orders)) &
                (self.mw.analysis_results_df['Order_Fulfillment_Status'] == 'Fulfillable')
            ].copy()

            self.filtered_orders_df = filtered_df

            # Get unique order count
            order_count = filtered_df['Order_Number'].nunique()

            self.order_count_label.setText(f"{order_count} orders ready for barcode generation")

        except Exception as e:
            self.order_count_label.setText(f"Error reading packing list: {e!s}")
            self.log.exception(f"Failed to read packing list {packing_list_file}")
            return

        # Setup output directory
        session_path = Path(self.mw.session_path)
        self.barcodes_dir = session_path / "barcodes" / packing_list_name
        self.barcodes_dir.mkdir(parents=True, exist_ok=True)

        self.output_dir_label.setText(str(self.barcodes_dir))

        # Setup history manager
        self.barcodes_dir / "barcode_history.json"        # History removed - using logs only

        # Enable generation if we have orders
        self.generate_btn.setEnabled(order_count > 0)

        self.log.info(f"Ready to generate {order_count} barcodes for {packing_list_name}")

    def _on_generate_clicked(self):
        """Handle generate button click."""
        if self.filtered_orders_df is None or len(self.filtered_orders_df) == 0:
            QMessageBox.warning(
                self,
                "No Orders",
                "No orders available for barcode generation."
            )
            return

        # Confirm generation
        order_count = self.filtered_orders_df['Order_Number'].nunique()

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output: {self.barcodes_dir}",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Disable UI during generation
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        # Set indeterminate progress (busy indicator) to avoid thread safety issues
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.status_label.setText(f"Generating {order_count} barcode labels...")
        self.status_label.setStyleSheet("")

        # Start generation in background
        worker = Worker(self._generate_barcodes_worker)
        worker.signals.result.connect(self._on_generation_complete)
        worker.signals.error.connect(self._on_generation_error)
        worker.signals.finished.connect(self._on_generation_finished)

        QThreadPool.globalInstance().start(worker)

        self.log.info(f"Started barcode generation for {order_count} orders")

    def _generate_barcodes_worker(self):
        """Worker function for barcode generation."""
        from shopify_tool.barcode_processor import generate_barcodes_batch
        from shopify_tool.csv_utils import order_number_sort_key

        # Filter to unique orders and calculate item count (total quantity of products)
        unique_orders = self.filtered_orders_df.groupby('Order_Number').first().reset_index()

        # Calculate actual item count (sum of Quantity column for each order)
        item_counts = self.filtered_orders_df.groupby('Order_Number')['Quantity'].sum().to_dict()

        # Add item_count column to unique_orders (total quantity of products)
        unique_orders['item_count'] = unique_orders['Order_Number'].map(item_counts)

        # Merge tags from ALL rows of each order (not just the first row).
        # Internal_Tags is a serialized list (JSON string or native list),
        # not flat comma-separated text -- use tag_manager's parser/merger
        # rather than splitting the string ourselves, which corrupts
        # multi-tag/multi-row values into something format_tags_for_barcode
        # can't parse and leaks the raw literal onto the printed label.
        if 'Internal_Tags' in self.filtered_orders_df.columns:
            from shopify_tool.tag_manager import merge_tags

            merged_tags = {}
            for order_num, group in self.filtered_orders_df.groupby('Order_Number', sort=False):
                merged_tags[order_num] = merge_tags(group['Internal_Tags'].dropna().tolist())
            unique_orders['Internal_Tags'] = unique_orders['Order_Number'].map(merged_tags)

        # Sort by natural order so sequential numbering (idx+1) matches numeric order
        unique_orders['_order_sort'] = unique_orders['Order_Number'].apply(order_number_sort_key)
        unique_orders = unique_orders.sort_values('_order_sort').drop(columns=['_order_sort']).reset_index(drop=True)

        self.log.info("Using independent sequential numbering (1, 2, 3...) in natural order")

        # Prepare barcode records with independent numbering per packing list
        results = generate_barcodes_batch(
            df=unique_orders,
            sequential_map=None,  # Independent per-generation numbering
            progress_callback=None  # No progress updates from worker thread
        )

        return results

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
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(f"color: {theme.status_success}; font-weight: bold;")

        self.log.info(
            f"Barcode generation complete: {len(successful)} successful, "
            f"{len(failed)} failed"
        )

        pdf_generated = self._generate_pdf_from_results(successful) if successful else False

        self.last_barcode_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf" if pdf_generated else None
        )
        self.print_btn.setEnabled(bool(self.last_barcode_pdf))

        want_qr = bool(successful) and self.add_qr_checkbox.isChecked()
        qr_pdf_generated = self._generate_qr_pdf_from_results(successful) if want_qr else False

        self.last_qr_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf" if qr_pdf_generated else None
        )
        self.print_qr_btn.setEnabled(bool(self.last_qr_pdf))

        if successful and not pdf_generated:
            QMessageBox.critical(
                self,
                "PDF Generation Failed",
                f"{len(successful)} barcodes were validated, but rendering the "
                "PDF failed.\n\nSee execution log for details."
            )
        else:
            message = f"Successfully generated {len(successful)} barcode labels as a PDF document."

            if want_qr:
                if qr_pdf_generated:
                    message += "\n\nAlso generated QR labels as a PDF document."
                else:
                    message += "\n\nQR labels PDF failed to generate. See execution log for details."

            if failed:
                message += f"\n\n{len(failed)} barcodes failed to generate."

            QMessageBox.information(self, "Generation Complete", message)

        # Auto-open generated PDFs if enabled
        if self.auto_open_pdf_checkbox.isChecked():
            if pdf_generated:
                self._open_pdf(self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf")
            if qr_pdf_generated:
                self._open_pdf(self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf")

        # Emit signal
        self.generation_complete.emit({
            'packing_list': self.current_packing_list,
            'successful': len(successful),
            'failed': len(failed),
            'total': len(results)
        })

    def _on_generation_error(self, error_info):
        """Handle generation error."""
        _exctype, value, traceback_str = error_info

        self.status_label.setText("Generation failed")
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(f"color: {theme.status_danger}; font-weight: bold;")

        self.log.error(f"Barcode generation failed: {value}\n{traceback_str}")

        QMessageBox.critical(
            self,
            "Generation Error",
            f"Barcode generation failed:\n\n{value}\n\n"
            "See execution log for details."
        )

    def _on_generation_finished(self):
        """Re-enable UI after generation."""
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)

    def _generate_pdf_from_results(self, results):
        """Generate the barcode labels PDF from prepared order records.

        Returns True on success, False if rendering failed.
        """
        try:
            from shopify_tool.barcode_processor import generate_code128_labels_pdf

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_code128_labels_pdf(results, pdf_path)

            self.log.info(f"Generated PDF: {pdf_path}")
            return True

        except Exception:
            self.log.exception("PDF generation failed")
            return False

    def _generate_qr_pdf_from_results(self, results):
        """Generate the QR labels PDF from prepared order records.

        Returns True on success, False if rendering failed.
        """
        try:
            from shopify_tool.barcode_processor import generate_qr_labels_pdf

            pdf_filename = f"{self.current_packing_list}_qr_labels.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_qr_labels_pdf(results, pdf_path)

            self.log.info(f"Generated QR labels PDF: {pdf_path}")
            return True

        except Exception:
            self.log.exception("QR labels PDF generation failed")
            return False

    def _open_pdf(self, pdf_path):
        """Open a generated PDF in the OS default viewer."""
        url = QUrl.fromLocalFile(str(pdf_path))
        QDesktopServices.openUrl(url)

    def _save_print_settings(self):
        save_print_settings("barcode_generator", {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
            "raw_zpl_label_width_mm": self.raw_zpl_label_width_spin.value(),
            "raw_zpl_label_height_mm": self.raw_zpl_label_height_spin.value(),
            "driver_printer_name": self.driver_printer_combo.currentData(),
        })

    def _on_print_clicked(self):
        print_pdf(self, self.last_barcode_pdf, load_print_settings("barcode_generator"))

    def _on_print_qr_clicked(self):
        print_pdf(self, self.last_qr_pdf, load_print_settings("barcode_generator"))

