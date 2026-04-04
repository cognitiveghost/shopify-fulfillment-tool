"""
Reference Labels Widget - PDF processing for reference numbers.

Features:
- File selection (PDF + CSV)
- Background processing with progress tracking
- Processing history display
- Error handling
"""

import os
import logging
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QProgressBar, QTableWidget, QFileDialog, QCheckBox,
    QMessageBox, QTableWidgetItem, QHeaderView, QComboBox
)
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from gui.worker import Worker
from shopify_tool.reference_labels_history import ReferenceLabelsHistory

from gui.theme_manager import get_theme_manager
from gui.pdf_printer import populate_printer_combo, print_pdf_to_printer

class ReferenceLabelsWidget(QWidget):
    """Widget for processing reference labels PDFs."""

    # Signal emitted when processing completes
    processing_complete = Signal(dict)

    # Signal for progress updates (must be in main thread)
    _progress_update = Signal(int, str)

    def __init__(self, main_window, parent=None):
        """
        Initialize Reference Labels widget.

        Args:
            main_window: MainWindow instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self.log = logging.getLogger(__name__)

        # File paths
        self.pdf_path = None
        self.csv_path = None
        self.output_dir = None
        self.last_output_path = None

        # History manager
        self.history = None

        self._init_ui()
        self._connect_signals()
        self._update_output_dir()

        # Connect internal progress signal
        self._progress_update.connect(self._update_progress_ui)

    def _init_ui(self):
        """Initialize UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Section 1: File Selection
        layout.addWidget(self._create_file_selection_group())

        # Section 2: Output Settings
        layout.addWidget(self._create_output_settings_group())

        # Section 3: Processing
        layout.addWidget(self._create_processing_group())

        # Section 4: Print
        layout.addWidget(self._create_print_section())

        # Section 5: History
        layout.addWidget(self._create_history_group(), 1)  # Stretch

    def _create_file_selection_group(self):
        """Create file selection section."""
        group = QGroupBox("File Selection")
        layout = QVBoxLayout(group)

        # PDF Selection Row
        pdf_row = QHBoxLayout()
        self.select_pdf_btn = QPushButton("Select PDF Labels")
        self.select_pdf_btn.setMinimumWidth(150)
        self.select_pdf_btn.setToolTip("Select the PDF file containing courier labels")
        pdf_row.addWidget(self.select_pdf_btn)

        self.pdf_label = QLabel("No PDF selected")
        theme = get_theme_manager().get_current_theme()
        self.pdf_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        self.pdf_label.setWordWrap(True)
        pdf_row.addWidget(self.pdf_label, 1)
        layout.addLayout(pdf_row)

        # CSV Selection Row
        csv_row = QHBoxLayout()
        self.select_csv_btn = QPushButton("Select CSV Mapping")
        self.select_csv_btn.setMinimumWidth(150)
        self.select_csv_btn.setToolTip("Select the CSV file with PostOne ID → Reference Number mapping")
        csv_row.addWidget(self.select_csv_btn)

        self.csv_label = QLabel("No CSV selected")
        self.csv_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        self.csv_label.setWordWrap(True)
        csv_row.addWidget(self.csv_label, 1)
        layout.addLayout(csv_row)

        # Info label
        info_label = QLabel(
            "CSV format: PostOne ID (column 0), Tracking (column 1), "
            "Reference Number (column 2), Name (column 6)"
        )
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10px; padding: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return group

    def _create_output_settings_group(self):
        """Create output settings section."""
        group = QGroupBox("Output Settings")
        layout = QVBoxLayout(group)

        # Output directory row
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Output Directory:"))

        self.output_dir_label = QLabel()
        self.output_dir_label.setStyleSheet("font-weight: bold;")
        self.output_dir_label.setWordWrap(True)
        dir_row.addWidget(self.output_dir_label, 1)

        self.change_dir_btn = QPushButton("Change...")
        self.change_dir_btn.setToolTip("Change output directory")
        dir_row.addWidget(self.change_dir_btn)

        layout.addLayout(dir_row)

        # Auto-open checkbox
        self.auto_open_checkbox = QCheckBox("Auto-open PDF after processing")
        self.auto_open_checkbox.setChecked(True)
        layout.addWidget(self.auto_open_checkbox)

        return group

    def _create_processing_group(self):
        """Create processing section."""
        group = QGroupBox("Processing")
        layout = QVBoxLayout(group)

        # Process button
        self.process_btn = QPushButton("Process Labels")
        self.process_btn.setMinimumHeight(50)
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip("Process PDF with reference numbers")
        layout.addWidget(self.process_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("padding: 5px;")
        layout.addWidget(self.status_label)

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
        self.auto_print_checkbox = QCheckBox("Auto-print after processing")
        self.auto_print_checkbox.setChecked(False)
        layout.addWidget(self.auto_print_checkbox)

        # Manual print button
        self.print_btn = QPushButton("Print PDF")
        self.print_btn.setEnabled(False)
        self.print_btn.setToolTip("Print the last processed PDF to the selected printer")
        self.print_btn.clicked.connect(self._on_print_clicked)
        layout.addWidget(self.print_btn)

        self._refresh_printers()
        return group

    def _refresh_printers(self):
        populate_printer_combo(self.printer_combo, self.log)

    def _on_print_clicked(self):
        """Print last processed PDF to selected printer."""
        if not self.last_output_path or not Path(self.last_output_path).exists():
            QMessageBox.warning(self, "Nothing to Print", "No processed PDF is available.")
            return
        printer_name = self.printer_combo.currentText()
        if not printer_name or printer_name == "(no printers found)":
            QMessageBox.warning(self, "No Printer", "Please select a printer.")
            return
        self.print_btn.setEnabled(False)
        worker = Worker(self._print_pdf_worker, self.last_output_path, printer_name)
        worker.signals.result.connect(self._on_print_result)
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

    def _create_history_group(self):
        """Create history section."""
        group = QGroupBox("Processing History")
        layout = QVBoxLayout(group)

        # History table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "Date/Time",
            "Input PDF",
            "Pages",
            "Matched",
            "Unmatched",
            "Status"
        ])
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)

        # Set column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 150)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 70)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 80)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 90)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 100)

        layout.addWidget(self.history_table)

        # Button row
        button_row = QHBoxLayout()
        button_row.addStretch()

        clear_history_btn = QPushButton("Clear History")
        clear_history_btn.setToolTip("Clear all history entries")
        clear_history_btn.clicked.connect(self._clear_history)
        button_row.addWidget(clear_history_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Reload history from file")
        refresh_btn.clicked.connect(self._load_history)
        button_row.addWidget(refresh_btn)

        layout.addLayout(button_row)

        return group

    def _connect_signals(self):
        """Connect signals and slots."""
        self.select_pdf_btn.clicked.connect(self._select_pdf)
        self.select_csv_btn.clicked.connect(self._select_csv)
        self.process_btn.clicked.connect(self._process_pdf)
        self.change_dir_btn.clicked.connect(self._change_output_dir)
        self.history_table.doubleClicked.connect(self._open_history_item)

        # Connect to MainWindow session change
        # Note: session_changed might not exist yet, so we'll also check in showEvent
        if hasattr(self.mw, 'session_changed'):
            self.mw.session_changed.connect(self._on_session_changed)

    def _select_pdf(self):
        """Open file dialog to select PDF file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF Labels File",
            "",
            "PDF Files (*.pdf)"
        )

        if file_path:
            self.pdf_path = file_path
            file_name = Path(file_path).name
            self.pdf_label.setText(file_name)
            theme = get_theme_manager().get_current_theme()
            self.pdf_label.setStyleSheet(f"color: {theme.text}; font-weight: bold;")
            self.pdf_label.setToolTip(file_path)

            self.log.info(f"PDF selected: {file_path}")
            self._update_process_button()

    def _select_csv(self):
        """Open file dialog to select CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV Mapping File",
            "",
            "CSV Files (*.csv);;All Files (*.*)"
        )

        if file_path:
            self.csv_path = file_path
            file_name = Path(file_path).name
            self.csv_label.setText(file_name)
            theme = get_theme_manager().get_current_theme()
            self.csv_label.setStyleSheet(f"color: {theme.text}; font-weight: bold;")
            self.csv_label.setToolTip(file_path)

            self.log.info(f"CSV selected: {file_path}")
            self._update_process_button()

    def _change_output_dir(self):
        """Open directory dialog to change output directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            str(self.output_dir) if self.output_dir else ""
        )

        if dir_path:
            self.output_dir = Path(dir_path)
            self.output_dir_label.setText(str(self.output_dir))
            self.log.info(f"Output directory changed: {dir_path}")

    def _update_process_button(self):
        """Enable/disable process button based on file selection."""
        has_both_files = bool(self.pdf_path and self.csv_path)
        has_output = bool(self.output_dir)

        self.process_btn.setEnabled(has_both_files and has_output)

        if has_both_files and has_output:
            self.status_label.setText("Ready to process")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        elif not has_output:
            self.status_label.setText("No session selected")
            self.status_label.setStyleSheet("color: orange;")
        else:
            self.status_label.setText("⏳ Waiting for files...")
            theme = get_theme_manager().get_current_theme()
            self.status_label.setStyleSheet(f"color: {theme.text_secondary};")

    def _update_output_dir(self):
        """Update output directory based on current session."""
        if not self.mw.session_path:
            self.output_dir = None
            self.output_dir_label.setText("No session selected")
            theme = get_theme_manager().get_current_theme()
            self.output_dir_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
            self._update_process_button()
            return

        # Get reference_labels directory for session
        try:
            self.output_dir = self.mw.session_manager.get_reference_labels_dir(
                self.mw.session_path
            )

            # Create directory if it doesn't exist
            self.output_dir.mkdir(parents=True, exist_ok=True)

            self.output_dir_label.setText(str(self.output_dir))
            theme = get_theme_manager().get_current_theme()
            self.output_dir_label.setStyleSheet(f"color: {theme.text};")

            # Initialize history manager
            self.history = ReferenceLabelsHistory(self.output_dir)
            self._load_history()

            self.log.info(f"Output directory set: {self.output_dir}")

        except Exception as e:
            self.log.error(f"Failed to set output directory: {e}")
            self.output_dir = None
            self.output_dir_label.setText("Error accessing session directory")
            self.output_dir_label.setStyleSheet("color: red;")

        self._update_process_button()

    def _validate_inputs(self):
        """
        Validate inputs before processing.

        Returns:
            bool: True if inputs are valid
        """
        errors = []

        # Validate PDF
        if not self.pdf_path:
            errors.append("PDF file not selected")
        elif not Path(self.pdf_path).exists():
            errors.append(f"PDF file not found: {self.pdf_path}")
        elif not Path(self.pdf_path).suffix.lower() == '.pdf':
            errors.append("Selected file is not a PDF")

        # Validate CSV
        if not self.csv_path:
            errors.append("CSV file not selected")
        elif not Path(self.csv_path).exists():
            errors.append(f"CSV file not found: {self.csv_path}")
        elif not Path(self.csv_path).suffix.lower() == '.csv':
            errors.append("Selected file is not a CSV")

        # Validate output directory
        if not self.output_dir:
            errors.append("Output directory not set (no session selected)")
        elif not self.output_dir.exists():
            errors.append(f"Output directory does not exist: {self.output_dir}")

        if errors:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Cannot process:\n\n" + "\n".join(f"• {e}" for e in errors)
            )
            return False

        return True

    def _process_pdf(self):
        """Start PDF processing in background thread."""
        # Validate inputs
        if not self._validate_inputs():
            return

        # Disable UI
        self.process_btn.setEnabled(False)
        self.select_pdf_btn.setEnabled(False)
        self.select_csv_btn.setEnabled(False)
        self.change_dir_btn.setEnabled(False)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("⏳ Processing...")
        self.status_label.setStyleSheet("color: blue;")

        self.log.info(f"Starting PDF processing: {self.pdf_path}")

        # Create worker
        worker = Worker(
            self._process_pdf_worker,
            self.pdf_path,
            self.csv_path,
            str(self.output_dir)
        )

        # Connect signals
        worker.signals.result.connect(self._on_processing_complete)
        worker.signals.error.connect(self._on_processing_error)
        worker.signals.finished.connect(self._on_processing_finished)

        # Start worker
        QThreadPool.globalInstance().start(worker)

    def _process_pdf_worker(self, pdf_path, csv_path, output_dir):
        """
        Worker function - runs in background thread.

        Args:
            pdf_path: Path to input PDF
            csv_path: Path to CSV mapping
            output_dir: Output directory

        Returns:
            dict: Processing result
        """
        from shopify_tool.pdf_processor import process_reference_labels

        def progress_callback(current, total, message):
            """Update progress bar from worker thread using signals."""
            percentage = int((current / total) * 100)
            status_text = f"{message} ({current}/{total})"
            # Emit signal to update UI from main thread
            self._progress_update.emit(percentage, status_text)

        result = process_reference_labels(
            pdf_path=pdf_path,
            csv_path=csv_path,
            output_dir=output_dir,
            progress_callback=progress_callback
        )

        return result

    def _update_progress_ui(self, percentage, status_text):
        """Update progress UI elements (runs in main thread).

        Args:
            percentage: Progress percentage (0-100)
            status_text: Status message to display
        """
        self.progress_bar.setValue(percentage)
        self.status_label.setText(status_text)

    def _on_processing_complete(self, result):
        """
        Handle successful processing.

        Args:
            result: Processing result dict
        """
        self.progress_bar.setValue(100)
        self.status_label.setText("Processing complete!")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.log.info(
            f"PDF processing complete: {result['matched']} matched, "
            f"{result['unmatched']} unmatched"
        )

        # Add to history
        if self.history:
            self.history.add_entry(
                input_pdf=Path(self.pdf_path).name,
                input_csv=Path(self.csv_path).name,
                output_pdf=Path(result['output_file']).name,
                pages_processed=result['pages_processed'],
                matched=result['matched'],
                unmatched=result['unmatched'],
                processing_time=result['processing_time']
            )
            self._load_history()

        # Show success message
        QMessageBox.information(
            self,
            "Success",
            f"PDF processed successfully!\n\n"
            f"Pages processed: {result['pages_processed']}\n"
            f"Matched: {result['matched']}\n"
            f"Unmatched: {result['unmatched']}\n"
            f"Processing time: {result['processing_time']:.1f}s\n\n"
            f"Output: {Path(result['output_file']).name}"
        )

        # Track last output for print button
        self.last_output_path = result['output_file']
        self.print_btn.setEnabled(True)

        # Auto-open if checkbox enabled
        if self.auto_open_checkbox.isChecked():
            self._open_pdf(result['output_file'])

        # Auto-print if enabled
        if self.auto_print_checkbox.isChecked():
            self._on_print_clicked()

        # Emit signal
        self.processing_complete.emit(result)

    def _on_processing_error(self, error_info):
        """
        Handle processing error.

        Args:
            error_info: Tuple of (exc_type, exc_value, traceback_str)
        """
        exctype, value, traceback_str = error_info

        self.status_label.setText("Processing failed")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

        self.log.error(f"PDF processing failed: {value}\n{traceback_str}")

        # Map errors to user-friendly messages
        from shopify_tool.pdf_processor import (
            InvalidPDFError, InvalidCSVError, MappingError
        )

        if isinstance(value, InvalidPDFError):
            title = "Invalid PDF File"
            message = str(value)
            suggestion = "Please check that the PDF file is valid and not corrupted."
        elif isinstance(value, InvalidCSVError):
            title = "Invalid CSV File"
            message = str(value)
            suggestion = (
                "Please check that the CSV file has the correct format.\n"
                "Expected columns: PostOne ID (0), Tracking (1), Reference (2), Name (6)"
            )
        elif isinstance(value, MappingError):
            title = "Mapping Error"
            message = str(value)
            suggestion = "Some pages could not be matched. Check the CSV mapping file."
        else:
            title = "Processing Error"
            message = str(value)
            suggestion = "See execution log for technical details."

        QMessageBox.critical(
            self,
            title,
            f"{message}\n\n{suggestion}"
        )

    def _on_processing_finished(self):
        """Re-enable UI after processing completes or fails."""
        self.process_btn.setEnabled(True)
        self.select_pdf_btn.setEnabled(True)
        self.select_csv_btn.setEnabled(True)
        self.change_dir_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

    def _load_history(self):
        """Load processing history from file."""
        if not self.history:
            self.history_table.setRowCount(0)
            return

        entries = self.history.get_entries()

        self.history_table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            # Date/Time
            dt = datetime.fromisoformat(entry['processed_at'])
            date_item = QTableWidgetItem(dt.strftime("%Y-%m-%d %H:%M:%S"))
            self.history_table.setItem(row, 0, date_item)

            # Input PDF
            pdf_item = QTableWidgetItem(entry['input_pdf'])
            pdf_item.setToolTip(entry['output_pdf'])
            self.history_table.setItem(row, 1, pdf_item)

            # Pages
            pages_item = QTableWidgetItem(str(entry['pages_processed']))
            pages_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(row, 2, pages_item)

            # Matched
            matched_item = QTableWidgetItem(str(entry['matched']))
            matched_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(row, 3, matched_item)

            # Unmatched
            unmatched_item = QTableWidgetItem(str(entry['unmatched']))
            unmatched_item.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(row, 4, unmatched_item)

            # Status
            status = entry.get('status', 'success')
            status_item = QTableWidgetItem(status.upper())
            status_item.setTextAlignment(Qt.AlignCenter)

            if status == 'success':
                from PySide6.QtGui import QColor
                status_item.setForeground(QColor("green"))
            else:
                from PySide6.QtGui import QColor
                status_item.setForeground(QColor("red"))

            self.history_table.setItem(row, 5, status_item)

        self.log.debug(f"Loaded {len(entries)} history entries")

    def _clear_history(self):
        """Clear processing history."""
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all processing history?\n\n"
            "This will not delete the processed PDF files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.history:
                self.history.clear()
                self._load_history()
                self.log.info("History cleared")

    def _open_history_item(self, index):
        """
        Open processed PDF when history item is double-clicked.

        Args:
            index: QModelIndex of clicked item
        """
        row = index.row()

        if not self.history:
            return

        entries = self.history.get_entries()
        if row >= len(entries):
            return

        entry = entries[row]
        output_file = self.output_dir / entry['output_pdf']

        if output_file.exists():
            self._open_pdf(str(output_file))
        else:
            QMessageBox.warning(
                self,
                "File Not Found",
                f"Output PDF not found:\n{output_file}"
            )

    def _open_pdf(self, file_path):
        """
        Open PDF file with default application.

        Args:
            file_path: Path to PDF file
        """
        url = QUrl.fromLocalFile(str(file_path))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                "Cannot Open File",
                f"Failed to open PDF:\n{file_path}\n\n"
                "Please open it manually."
            )
        else:
            self.log.info(f"Opened PDF: {file_path}")

    def _on_session_changed(self):
        """Handle session change event."""
        self._update_output_dir()

    def showEvent(self, event):
        """Handle widget show event - update output directory when tab becomes visible."""
        super().showEvent(event)
        # Update output directory when tab becomes visible
        # This ensures we pick up the current session even if it was set before widget creation
        self._update_output_dir()
