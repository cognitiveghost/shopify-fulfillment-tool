"""
Reference Labels Widget - PDF processing for reference numbers.

Features:
- File selection (PDF + CSV)
- Background processing with progress tracking
- Error handling
"""

import logging
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.components import (
    ElidedLabel,
    FormSection,
    InlineMessage,
    PrintOptions,
    row_widget,
    show_error,
    toast,
)
from gui.components.print_options import LABEL_WIDTH
from gui.pdf_printing import load_print_settings, print_pdf
from gui.theme_manager import get_theme_manager
from gui.worker import Worker


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
        self.last_output_pdf = None

        self._init_ui()
        self._connect_signals()
        self._update_output_dir()

        # Connect internal progress signal
        self._progress_update.connect(self._update_progress_ui)

    def _init_ui(self):
        """One card's content: inputs, print options, then status and actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._create_inputs_section())

        # Courier PDFs' own page size can't be trusted (the same batch mixes
        # pages from ~98x147mm up to 152x102mm depending on courier) -- raw
        # ZPL has no driver to fit that to the physical label, so it prints
        # shrunk with blank margin instead of filling it. Set both to the
        # loaded label's real size to fit every page to it; 0 (default)
        # keeps the old behavior of using each page's own size as-is.
        self.print_options = PrintOptions(
            "reference_labels",
            label_size_tooltip=(
                "Physical label size as loaded in the printer, e.g. 152.4 x 101.6 "
                "for 6x4in shipping labels. 0 disables fitting and uses each "
                "page's own PDF size."
            ),
        )
        layout.addWidget(self.print_options)

        # Side by side, the taller card sets the row height; this stretch keeps
        # both action rows on one baseline.
        layout.addStretch()
        layout.addLayout(self._create_action_area())

    def _create_inputs_section(self):
        """The two input files, where the output goes, and whether to open it."""
        theme = get_theme_manager().get_current_theme()
        section = FormSection(
            "Reference labels",
            "Stamps each courier label with its order's reference number.",
            label_width=LABEL_WIDTH,
        )

        self.select_pdf_btn = QPushButton("Select PDF…")
        self.select_pdf_btn.setToolTip("Select the PDF file containing courier labels")
        self.pdf_label = ElidedLabel("No file chosen")
        self.pdf_label.setStyleSheet(
            f"color: {theme.text_secondary}; font-style: italic;"
        )
        section.add_row(
            "Labels PDF",
            row_widget(self.select_pdf_btn, self.pdf_label, stretch=self.pdf_label),
        )

        self.select_csv_btn = QPushButton("Select CSV…")
        self.select_csv_btn.setToolTip(
            "Select the CSV file with PostOne ID → Reference Number mapping"
        )
        self.csv_label = ElidedLabel("No file chosen")
        self.csv_label.setStyleSheet(
            f"color: {theme.text_secondary}; font-style: italic;"
        )
        section.add_row(
            "Mapping CSV",
            row_widget(self.select_csv_btn, self.csv_label, stretch=self.csv_label),
        )

        self.output_dir_label = ElidedLabel()
        self.change_dir_btn = QPushButton("Change…")
        self.change_dir_btn.setToolTip("Change output directory")
        section.add_row(
            "Output folder",
            row_widget(
                self.output_dir_label,
                self.change_dir_btn,
                stretch=self.output_dir_label,
            ),
        )

        self.auto_open_checkbox = QCheckBox("Open the PDF when it's ready")
        self.auto_open_checkbox.setChecked(True)
        section.add_row("", self.auto_open_checkbox)

        return section

    def _create_action_area(self):
        """Progress and status, then the actions, right-aligned."""
        area = QVBoxLayout()
        area.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        area.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        area.addWidget(self.status_label)

        self.print_btn = QPushButton("Print…")
        self.print_btn.setEnabled(False)

        # Its role (primary or secondary) is ToolsWidget's to set: the page has
        # one primary, and it moves to whichever card can run.
        self.process_btn = QPushButton("Process Labels")
        self.process_btn.setEnabled(False)
        self.process_btn.setToolTip("Process PDF with reference numbers")

        self.validation_error = InlineMessage(self)
        area.addWidget(self.validation_error)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.process_btn)
        area.addLayout(buttons)

        return area

    def _connect_signals(self):
        """Connect signals and slots."""
        self.select_pdf_btn.clicked.connect(self._select_pdf)
        self.select_csv_btn.clicked.connect(self._select_csv)
        self.process_btn.clicked.connect(self._process_pdf)
        self.change_dir_btn.clicked.connect(self._change_output_dir)
        self.print_btn.clicked.connect(self._on_print_clicked)

        # Connect to MainWindow session change
        # Note: session_changed might not exist yet, so we'll also check in showEvent
        if hasattr(self.mw, "session_changed"):
            self.mw.session_changed.connect(self._on_session_changed)

    def _select_pdf(self):
        """Open file dialog to select PDF file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF Labels File", "", "PDF Files (*.pdf)"
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
            self, "Select CSV Mapping File", "", "CSV Files (*.csv);;All Files (*.*)"
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
            str(self.output_dir) if self.output_dir else "",
        )

        if dir_path:
            self.output_dir = Path(dir_path)
            self.output_dir_label.setText(str(self.output_dir))
            self.log.info(f"Output directory changed: {dir_path}")

    def _update_process_button(self):
        """Enable/disable process button based on file selection."""
        self.validation_error.clear()  # the inputs it named have changed
        has_both_files = bool(self.pdf_path and self.csv_path)
        has_output = bool(self.output_dir)

        self.process_btn.setEnabled(has_both_files and has_output)

        if has_both_files and has_output:
            theme = get_theme_manager().get_current_theme()
            self.status_label.setText("Ready to process")
            self.status_label.setStyleSheet(
                f"color: {theme.status_success}; font-weight: bold;"
            )
        elif not has_output:
            theme = get_theme_manager().get_current_theme()
            self.status_label.setText("No session selected")
            self.status_label.setStyleSheet(f"color: {theme.status_warning};")
        else:
            self.status_label.setText("Waiting for files...")
            theme = get_theme_manager().get_current_theme()
            self.status_label.setStyleSheet(f"color: {theme.text_secondary};")

    def _update_output_dir(self):
        """Update output directory based on current session."""
        if not self.mw.session_path:
            self.output_dir = None
            self.output_dir_label.setText("Open a session to save labels into it")
            theme = get_theme_manager().get_current_theme()
            self.output_dir_label.setStyleSheet(
                f"color: {theme.text_secondary}; font-style: italic;"
            )
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

            self.log.info(f"Output directory set: {self.output_dir}")

        except Exception:
            self.log.exception("Failed to set output directory")
            self.output_dir = None
            self.output_dir_label.setText(
                "Can't reach this session's folder. Check the server connection."
            )
            theme = get_theme_manager().get_current_theme()
            self.output_dir_label.setStyleSheet(f"color: {theme.status_danger};")

        self._update_process_button()

    def _validate_inputs(self):
        """
        Validate inputs before processing.

        Returns:
            bool: True if inputs are valid
        """
        self.validation_error.clear()
        errors = []

        # Validate PDF
        if not self.pdf_path:
            errors.append("PDF file not selected")
        elif not Path(self.pdf_path).exists():
            errors.append(f"PDF file not found: {self.pdf_path}")
        elif Path(self.pdf_path).suffix.lower() != ".pdf":
            errors.append("Selected file is not a PDF")

        # Validate CSV
        if not self.csv_path:
            errors.append("CSV file not selected")
        elif not Path(self.csv_path).exists():
            errors.append(f"CSV file not found: {self.csv_path}")
        elif Path(self.csv_path).suffix.lower() != ".csv":
            errors.append("Selected file is not a CSV")

        # Validate output directory
        if not self.output_dir:
            errors.append("Output directory not set (no session selected)")
        elif not self.output_dir.exists():
            errors.append(f"Output directory does not exist: {self.output_dir}")

        if errors:
            self.validation_error.show_message(
                "Can't process yet: " + "; ".join(errors)
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
        self.status_label.setText("Processing...")
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(f"color: {theme.status_info};")

        self.log.info(f"Starting PDF processing: {self.pdf_path}")

        # Create worker
        worker = Worker(
            self._process_pdf_worker, self.pdf_path, self.csv_path, str(self.output_dir)
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
            progress_callback=progress_callback,
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
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(
            f"color: {theme.status_success}; font-weight: bold;"
        )

        self.last_output_pdf = Path(result["output_file"])
        self.print_btn.setEnabled(True)

        self.log.info(
            f"PDF processing complete: {result['matched']} matched, "
            f"{result['unmatched']} unmatched"
        )

        # Show success message
        toast(
            self,
            f"Processed {Path(result['output_file']).name} "
            f"({result['matched']} matched, {result['unmatched']} unmatched).",
        )

        # Auto-open if checkbox enabled
        if self.auto_open_checkbox.isChecked():
            self._open_pdf(result["output_file"])

        # Emit signal
        self.processing_complete.emit(result)

    def _on_processing_error(self, error_info):
        """
        Handle processing error.

        Args:
            error_info: Tuple of (exc_type, exc_value, traceback_str)
        """
        _exctype, value, traceback_str = error_info

        self.status_label.setText("Processing failed")
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(
            f"color: {theme.status_danger}; font-weight: bold;"
        )

        self.log.error(f"PDF processing failed: {value}\n{traceback_str}")

        # Map errors to user-friendly messages
        from shopify_tool.pdf_processor import (
            InvalidCSVError,
            InvalidPDFError,
            MappingError,
        )

        if isinstance(value, InvalidPDFError):
            what_to_do = (
                "The PDF couldn't be read. Check that it isn't damaged, "
                "then process it again."
            )
        elif isinstance(value, InvalidCSVError):
            what_to_do = (
                "The CSV isn't in the expected format. Expected columns: "
                "PostOne ID (0), Tracking (1), Reference (2), Name (6)."
            )
        elif isinstance(value, MappingError):
            what_to_do = (
                "Some pages didn't match a row in the CSV. Check the CSV "
                "mapping file, then process it again."
            )
        else:
            what_to_do = "Details are in Logs."

        show_error(self, "The PDF wasn't processed", what_to_do)

    def _on_processing_finished(self):
        """Re-enable UI after processing completes or fails."""
        self.process_btn.setEnabled(True)
        self.select_pdf_btn.setEnabled(True)
        self.select_csv_btn.setEnabled(True)
        self.change_dir_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)

    def _open_pdf(self, file_path):
        """
        Open PDF file with default application.

        Args:
            file_path: Path to PDF file
        """
        url = QUrl.fromLocalFile(str(file_path))
        if not QDesktopServices.openUrl(url):
            self.log.warning(f"Failed to open PDF: {file_path}")
            show_error(self, "The PDF didn't open", f"Open it manually: {file_path}")
        else:
            self.log.info(f"Opened PDF: {file_path}")

    def _on_print_clicked(self):
        print_pdf(self, self.last_output_pdf, load_print_settings("reference_labels"))

    def _on_session_changed(self):
        """Handle session change event."""
        self._update_output_dir()

    def showEvent(self, event):
        """Handle widget show event - update output directory when tab becomes visible."""
        super().showEvent(event)
        # Update output directory when tab becomes visible
        # This ensures we pick up the current session even if it was set before widget creation
        self._update_output_dir()
