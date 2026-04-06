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

import os
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QProgressBar, QTableWidget, QComboBox, QCheckBox,
    QMessageBox, QTableWidgetItem, QHeaderView, QFileDialog
)
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtCore import QUrl

from gui.worker import Worker
from gui.theme_manager import get_theme_manager
from gui.pdf_printer import populate_printer_combo, print_pdf_to_printer, handle_print_worker_error
from shopify_tool.tag_manager import parse_tags


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
        self.last_pdf_path = None

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

        # Section 3: Print
        layout.addWidget(self._create_print_section())

        # Section 4: Generation
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
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return group

    def _create_options_section(self):
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Auto-open file checkbox
        self.auto_open_pdf_checkbox = QCheckBox("Auto-open PDF after generation")
        self.auto_open_pdf_checkbox.setChecked(True)
        layout.addWidget(self.auto_open_pdf_checkbox)

        # Output format options
        format_label = QLabel("Output Format:")
        format_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(format_label)

        # Generate PNG checkbox
        self.generate_png_checkbox = QCheckBox("Generate PNG files (individual barcode images)")
        self.generate_png_checkbox.setChecked(False)  # Optional, off by default
        layout.addWidget(self.generate_png_checkbox)

        # Generate PDF checkbox
        self.generate_pdf_checkbox = QCheckBox("Generate PDF file (all barcodes in one document)")
        self.generate_pdf_checkbox.setChecked(True)  # Default option
        layout.addWidget(self.generate_pdf_checkbox)

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

    def _create_print_section(self):
        """Create print controls section."""
        group = QGroupBox("Print")
        layout = QVBoxLayout(group)

        # Printer selection row
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Printer:"))
        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumWidth(200)
        printer_row.addWidget(self.printer_combo, 1)
        refresh_printers_btn = QPushButton("Refresh")
        refresh_printers_btn.setMaximumWidth(70)
        refresh_printers_btn.clicked.connect(self._refresh_printers)
        printer_row.addWidget(refresh_printers_btn)
        layout.addLayout(printer_row)

        # Auto-print checkbox
        self.auto_print_checkbox = QCheckBox("Auto-print PDF after generation")
        self.auto_print_checkbox.setChecked(False)
        layout.addWidget(self.auto_print_checkbox)

        # Manual print button
        self.print_btn = QPushButton("Print PDF")
        self.print_btn.setEnabled(False)
        self.print_btn.setToolTip("Print the last generated PDF to the selected printer")
        self.print_btn.clicked.connect(self._on_print_clicked)
        layout.addWidget(self.print_btn)

        self._refresh_printers()
        return group

    def _refresh_printers(self):
        populate_printer_combo(self.printer_combo, self.log)

    def _on_print_clicked(self):
        """Print last generated PDF to selected printer."""
        if not self.last_pdf_path or not Path(self.last_pdf_path).exists():
            QMessageBox.warning(self, "Nothing to Print", "No PDF has been generated yet.")
            return
        printer_name = self.printer_combo.currentText()
        if not printer_name or printer_name == "(no printers found)":
            QMessageBox.warning(self, "No Printer", "Please select a printer.")
            return
        self.print_btn.setEnabled(False)
        worker = Worker(self._print_pdf_worker, self.last_pdf_path, printer_name)
        worker.signals.result.connect(self._on_print_result)
        worker.signals.error.connect(self._on_print_error)
        worker.signals.finished.connect(lambda: self.print_btn.setEnabled(True))
        QThreadPool.globalInstance().start(worker)

    def _print_pdf_worker(self, pdf_path, printer_name):
        return print_pdf_to_printer(pdf_path, printer_name)

    def _on_print_result(self, result):
        """Handle print job result in main thread."""
        if result.get("success"):
            self.log.info(f"Printed {result.get('pages_printed', 0)} page(s)")
        else:
            QMessageBox.warning(self, "Print Failed", f"Print failed:\n{result.get('error', 'Unknown error')}")
            self.log.error(f"Print failed: {result.get('error')}")

    def _on_print_error(self, error_tuple):
        handle_print_worker_error(self, self.log, error_tuple)

    def _create_generation_section(self):
        """Create generation section."""
        group = QGroupBox("Generate Barcodes")
        layout = QVBoxLayout(group)

        # Generate button
        self.generate_btn = QPushButton("Generate Barcode Labels")
        self.generate_btn.setMinimumHeight(50)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: {theme.border};
                color: {theme.text_secondary};
            }
        """)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_btn)

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
            self.order_count_label.setText(f"Error reading packing list: {str(e)}")
            self.log.error(f"Failed to read packing list {packing_list_file}: {e}", exc_info=True)
            return

        # Setup output directory
        session_path = Path(self.mw.session_path)
        self.barcodes_dir = session_path / "barcodes" / packing_list_name
        self.barcodes_dir.mkdir(parents=True, exist_ok=True)

        self.output_dir_label.setText(str(self.barcodes_dir))

        # Setup history manager
        history_file = self.barcodes_dir / "barcode_history.json"        # History removed - using logs only

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

        # Validate format selection
        if not self.generate_png_checkbox.isChecked() and not self.generate_pdf_checkbox.isChecked():
            QMessageBox.warning(
                self,
                "No Format Selected",
                "Please select at least one output format (PNG or PDF)."
            )
            return

        # Confirm generation
        order_count = self.filtered_orders_df['Order_Number'].nunique()

        # Build format string
        formats = []
        if self.generate_png_checkbox.isChecked():
            formats.append("PNG")
        if self.generate_pdf_checkbox.isChecked():
            formats.append("PDF")
        format_str = " + ".join(formats)

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output Format: {format_str}\n"
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
        # Use parse_tags() to correctly handle JSON array format (["TAG1", "TAG2"])
        # and produce pipe-separated output expected by format_tags_for_barcode().
        if 'Internal_Tags' in self.filtered_orders_df.columns:
            merged_tags = {}
            for order_num, group in self.filtered_orders_df.groupby('Order_Number', sort=False):
                seen, result = set(), []
                for val in group['Internal_Tags'].dropna():
                    for tag in parse_tags(val):
                        if tag and tag not in seen:
                            seen.add(tag)
                            result.append(tag)
                merged_tags[order_num] = '|'.join(result)
            unique_orders['Internal_Tags'] = unique_orders['Order_Number'].map(merged_tags)

        # Sort by natural order so sequential numbering (idx+1) matches numeric order
        unique_orders['_order_sort'] = unique_orders['Order_Number'].apply(order_number_sort_key)
        unique_orders = unique_orders.sort_values('_order_sort').drop(columns=['_order_sort']).reset_index(drop=True)

        self.log.info("Using independent sequential numbering (1, 2, 3...) in natural order")

        # Generate barcodes with independent numbering per packing list (sequential_map=None)
        results = generate_barcodes_batch(
            df=unique_orders,
            output_dir=self.barcodes_dir,
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
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.log.info(
            f"Barcode generation complete: {len(successful)} successful, "
            f"{len(failed)} failed"
        )

        # Generate PDF if requested
        if self.generate_pdf_checkbox.isChecked() and successful:
            self._generate_pdf_from_results(successful)

        # Delete PNG files if user only wants PDF
        if self.generate_pdf_checkbox.isChecked() and not self.generate_png_checkbox.isChecked() and successful:
            self._cleanup_png_files(successful)
            self.log.info(f"Cleaned up {len(successful)} PNG files (PDF-only mode)")

        # Show summary
        formats_generated = []
        if self.generate_png_checkbox.isChecked():
            formats_generated.append("PNG files")
        if self.generate_pdf_checkbox.isChecked():
            formats_generated.append("PDF document")
        format_msg = " and ".join(formats_generated)

        message = f"Successfully generated {len(successful)} barcode labels as {format_msg}."

        if failed:
            message += f"\n\n{len(failed)} barcodes failed to generate."

        QMessageBox.information(self, "Generation Complete", message)

        # Auto-open PDF if enabled
        if self.auto_open_pdf_checkbox.isChecked() and self.last_pdf_path and Path(self.last_pdf_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_pdf_path)))

        # Auto-print if enabled
        if self.auto_print_checkbox.isChecked() and self.last_pdf_path and Path(self.last_pdf_path).exists():
            self._on_print_clicked()

        # Emit signal
        self.generation_complete.emit({
            'packing_list': self.current_packing_list,
            'successful': len(successful),
            'failed': len(failed),
            'total': len(results)
        })

    def _on_generation_error(self, error_info):
        """Handle generation error."""
        exctype, value, traceback_str = error_info

        self.status_label.setText("Generation failed")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

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
        """Generate PDF automatically after barcode generation. Stores path in self.last_pdf_path."""
        try:
            from shopify_tool.barcode_processor import generate_barcodes_pdf

            barcode_files = [Path(r['file_path']) for r in results if r.get('file_path')]
            if not barcode_files:
                return

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename
            generate_barcodes_pdf(barcode_files, pdf_path)
            self.last_pdf_path = pdf_path
            self.print_btn.setEnabled(True)
            self.log.info(f"Auto-generated PDF: {pdf_path}")
        except Exception as e:
            self.log.error(f"Auto PDF generation failed: {e}")

    def _cleanup_png_files(self, results):
        """Remove PNG files after PDF generation (PDF-only mode)."""
        try:
            from pathlib import Path

            # Delete all PNG files from results
            for result in results:
                file_path = result.get('file_path')
                if file_path:
                    png_file = Path(file_path)
                    if png_file.exists() and png_file.suffix == '.png':
                        png_file.unlink()

            self.log.info(f"Cleaned up {len(results)} PNG files (PDF-only mode)")

        except Exception as e:
            self.log.error(f"PNG cleanup failed: {e}")



