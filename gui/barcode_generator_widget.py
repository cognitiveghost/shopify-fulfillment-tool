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
from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.components import ElidedLabel, FormSection, PrintOptions, row_widget
from gui.components.print_options import LABEL_WIDTH
from gui.pdf_printing import load_print_settings, print_pdf
from gui.theme_manager import get_theme_manager
from gui.worker import Worker
from shared.theme import on_theme_changed


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
        """One card's content: inputs, print options, then status and actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._create_inputs_section())

        # This flow's own template is always authored at 68x38mm, so fitting
        # is mostly a safety net here (unlike Reference Labels, where the
        # source PDF's page size is a courier's and can't be trusted) -- set
        # it to match whatever label stock is actually loaded if it ever
        # changes. 0 (default) keeps using the template's own page size.
        self.print_options = PrintOptions(
            "barcode_generator",
            label_size_tooltip=(
                "Physical label size as loaded in the printer, e.g. 68 x 38 for "
                "this flow's default label stock. 0 disables fitting and uses the "
                "generated PDF's own page size."
            ),
        )
        layout.addWidget(self.print_options)

        # Side by side, the taller card sets the row height; this stretch keeps
        # both action rows on one baseline.
        layout.addStretch()
        layout.addLayout(self._create_action_area())

    def _create_inputs_section(self):
        """Which packing list, how many orders it holds, and where labels go."""
        section = FormSection(
            "Barcode labels",
            "One label for every Fulfillable order in a packing list. "
            "Each list gets its own folder.",
            label_width=LABEL_WIDTH,
        )

        self.packing_list_combo = QComboBox()
        # A long list name must not set the card's minimum width.
        self.packing_list_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.packing_list_combo.setMinimumContentsLength(20)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh packing lists")
        refresh_btn.clicked.connect(self._refresh_packing_lists)
        section.add_row(
            "Packing list",
            row_widget(
                self.packing_list_combo, refresh_btn, stretch=self.packing_list_combo
            ),
        )

        self.order_count_label = QLabel("No packing list selected")
        self.order_count_label.setWordWrap(True)
        on_theme_changed(
            self.order_count_label,
            lambda t: self.order_count_label.setStyleSheet(
                f"color: {t.text_secondary}; font-style: italic;"
            ),
        )
        section.add_row("", self.order_count_label)

        self.output_dir_label = ElidedLabel("Choose a packing list")
        on_theme_changed(
            self.output_dir_label,
            lambda t: self.output_dir_label.setStyleSheet(
                f"color: {t.text_secondary};"
            ),
        )
        section.add_row("Output folder", self.output_dir_label)

        self.add_qr_checkbox = QCheckBox("Add QR labels (order number)")
        self.add_qr_checkbox.setChecked(False)
        self.auto_open_pdf_checkbox = QCheckBox("Open the PDF when it's ready")
        self.auto_open_pdf_checkbox.setChecked(True)
        section.add_row(
            "", row_widget(self.add_qr_checkbox, self.auto_open_pdf_checkbox)
        )

        return section

    def _create_action_area(self):
        """Progress and status, then the actions, right-aligned."""
        area = QVBoxLayout()
        area.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        area.addWidget(self.progress_bar)

        self.status_label = QLabel("Select a packing list to begin")
        self.status_label.setWordWrap(True)
        area.addWidget(self.status_label)

        self.print_qr_btn = QPushButton("Print QR labels…")
        self.print_qr_btn.setEnabled(False)

        self.print_btn = QPushButton("Print…")
        self.print_btn.setEnabled(False)

        # No stylesheet: its role (primary or secondary) is ToolsWidget's to
        # set. The page has one primary, and it moves to whichever card can run.
        self.generate_btn = QPushButton("Generate Barcode Labels")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.print_qr_btn)
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.generate_btn)
        area.addLayout(buttons)

        return area

    def showEvent(self, event):
        """Override showEvent to refresh packing lists when tab becomes visible."""
        super().showEvent(event)
        # Auto-refresh packing lists when user switches to this tab
        if self.mw.session_path:
            self._refresh_packing_lists()
            self.log.debug("Auto-refreshed packing lists on tab switch")

    def _connect_signals(self):
        """Connect signals and slots."""
        self.packing_list_combo.currentIndexChanged.connect(
            self._on_packing_list_changed
        )
        self.print_btn.clicked.connect(self._on_print_clicked)
        self.print_qr_btn.clicked.connect(self._on_print_qr_clicked)

    def _update_state(self):
        """Update widget state based on current session."""
        if not self.mw.session_path:
            self.packing_list_combo.clear()
            self.order_count_label.setText("No session selected")
            self.output_dir_label.setText("Open a session to save labels into it")
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
            self.order_count_label.setText(
                "No packing lists in this session yet. Generate one from Analysis Results."
            )
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
            self.output_dir_label.setText("Choose a packing list")
            self.generate_btn.setEnabled(False)
            return

        # Get selected packing list name and file path
        packing_list_name = self.packing_list_combo.currentText()
        packing_list_file = self.packing_list_combo.currentData()
        self.current_packing_list = packing_list_name

        self.log.info(f"Selected packing list: {packing_list_name}")

        if (
            not hasattr(self.mw, "analysis_results_df")
            or self.mw.analysis_results_df is None
        ):
            self.order_count_label.setText("No analysis data loaded")
            self.log.warning("No analysis results DataFrame available")
            return

        # Read packing list Excel file to get order numbers
        try:
            packing_list_df = pd.read_excel(packing_list_file)

            # Get unique order numbers from packing list
            if "Order_Number" not in packing_list_df.columns:
                self.order_count_label.setText(
                    "Invalid packing list format (missing Order_Number)"
                )
                self.log.error(
                    f"Packing list missing Order_Number column: {packing_list_file}"
                )
                return

            packing_list_orders = set(packing_list_df["Order_Number"].unique())

            # Filter analysis results to only orders in this packing list
            # AND that are Fulfillable
            filtered_df = self.mw.analysis_results_df[
                (self.mw.analysis_results_df["Order_Number"].isin(packing_list_orders))
                & (
                    self.mw.analysis_results_df["Order_Fulfillment_Status"]
                    == "Fulfillable"
                )
            ].copy()

            self.filtered_orders_df = filtered_df

            # Get unique order count
            order_count = filtered_df["Order_Number"].nunique()

            self.order_count_label.setText(
                f"{order_count} orders ready for barcode generation"
            )

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
        self.barcodes_dir / "barcode_history.json"  # History removed - using logs only

        # Enable generation if we have orders
        self.generate_btn.setEnabled(order_count > 0)

        self.log.info(
            f"Ready to generate {order_count} barcodes for {packing_list_name}"
        )

    def _on_generate_clicked(self):
        """Handle generate button click."""
        if self.filtered_orders_df is None or len(self.filtered_orders_df) == 0:
            QMessageBox.warning(
                self, "No Orders", "No orders available for barcode generation."
            )
            return

        # Confirm generation
        order_count = self.filtered_orders_df["Order_Number"].nunique()

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output: {self.barcodes_dir}",
            QMessageBox.Yes | QMessageBox.No,
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
        unique_orders = (
            self.filtered_orders_df.groupby("Order_Number").first().reset_index()
        )

        # Calculate actual item count (sum of Quantity column for each order)
        item_counts = (
            self.filtered_orders_df.groupby("Order_Number")["Quantity"].sum().to_dict()
        )

        # Add item_count column to unique_orders (total quantity of products)
        unique_orders["item_count"] = unique_orders["Order_Number"].map(item_counts)

        # Merge tags from ALL rows of each order (not just the first row).
        # Internal_Tags is a serialized list (JSON string or native list),
        # not flat comma-separated text -- use tag_manager's parser/merger
        # rather than splitting the string ourselves, which corrupts
        # multi-tag/multi-row values into something format_tags_for_barcode
        # can't parse and leaks the raw literal onto the printed label.
        if "Internal_Tags" in self.filtered_orders_df.columns:
            from shopify_tool.tag_manager import merge_tags

            merged_tags = {}
            for order_num, group in self.filtered_orders_df.groupby(
                "Order_Number", sort=False
            ):
                merged_tags[order_num] = merge_tags(
                    group["Internal_Tags"].dropna().tolist()
                )
            unique_orders["Internal_Tags"] = unique_orders["Order_Number"].map(
                merged_tags
            )

        # Sort by natural order so sequential numbering (idx+1) matches numeric order
        unique_orders["_order_sort"] = unique_orders["Order_Number"].apply(
            order_number_sort_key
        )
        unique_orders = (
            unique_orders.sort_values("_order_sort")
            .drop(columns=["_order_sort"])
            .reset_index(drop=True)
        )

        self.log.info(
            "Using independent sequential numbering (1, 2, 3...) in natural order"
        )

        # Prepare barcode records with independent numbering per packing list
        results = generate_barcodes_batch(
            df=unique_orders,
            sequential_map=None,  # Independent per-generation numbering
            progress_callback=None,  # No progress updates from worker thread
        )

        return results

    def _on_generation_complete(self, results):
        """Handle successful generation."""
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]

        # Reset progress bar to normal mode and set to 100%
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Complete: {len(successful)} barcodes generated")
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(
            f"color: {theme.status_success}; font-weight: bold;"
        )

        self.log.info(
            f"Barcode generation complete: {len(successful)} successful, "
            f"{len(failed)} failed"
        )

        pdf_generated = (
            self._generate_pdf_from_results(successful) if successful else False
        )

        self.last_barcode_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf"
            if pdf_generated
            else None
        )
        self.print_btn.setEnabled(bool(self.last_barcode_pdf))

        want_qr = bool(successful) and self.add_qr_checkbox.isChecked()
        qr_pdf_generated = (
            self._generate_qr_pdf_from_results(successful) if want_qr else False
        )

        self.last_qr_pdf = (
            self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf"
            if qr_pdf_generated
            else None
        )
        self.print_qr_btn.setEnabled(bool(self.last_qr_pdf))

        if successful and not pdf_generated:
            QMessageBox.critical(
                self,
                "PDF Generation Failed",
                f"{len(successful)} barcodes were validated, but rendering the "
                "PDF failed.\n\nSee execution log for details.",
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
                self._open_pdf(
                    self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf"
                )
            if qr_pdf_generated:
                self._open_pdf(
                    self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf"
                )

        # Emit signal
        self.generation_complete.emit(
            {
                "packing_list": self.current_packing_list,
                "successful": len(successful),
                "failed": len(failed),
                "total": len(results),
            }
        )

    def _on_generation_error(self, error_info):
        """Handle generation error."""
        _exctype, value, traceback_str = error_info

        self.status_label.setText("Generation failed")
        theme = get_theme_manager().get_current_theme()
        self.status_label.setStyleSheet(
            f"color: {theme.status_danger}; font-weight: bold;"
        )

        self.log.error(f"Barcode generation failed: {value}\n{traceback_str}")

        QMessageBox.critical(
            self,
            "Generation Error",
            f"Barcode generation failed:\n\n{value}\n\nSee execution log for details.",
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

    def _on_print_clicked(self):
        print_pdf(self, self.last_barcode_pdf, load_print_settings("barcode_generator"))

    def _on_print_qr_clicked(self):
        print_pdf(self, self.last_qr_pdf, load_print_settings("barcode_generator"))
