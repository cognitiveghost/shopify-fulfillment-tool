from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox,
    QFrame, QListWidget, QListWidgetItem, QSplitter, QGroupBox, QTextEdit,
    QWidget
)
from PySide6.QtCore import Signal, Slot, Qt
from gui.theme_manager import get_theme_manager


class ReportSelectionDialog(QDialog):
    """A dialog that dynamically creates buttons for selecting a pre-configured report.

    This dialog is populated with a button for each report found in the
    application's configuration file for a given report type (e.g.,
    'packing_lists' or 'stock_exports'). When the user clicks a button, the
    dialog emits a signal containing the configuration for that specific
    report and then closes.

    Signals:
        reportSelected (dict): Emitted when a report button is clicked,
                               carrying the configuration dictionary for that
                               report.
    """

    # Signal that emits the selected report configuration when a button is clicked
    reportSelected = Signal(dict)

    def __init__(self, report_type, reports_config, parent=None):
        """Initializes the ReportSelectionDialog.

        Args:
            report_type (str): The type of reports to display (e.g.,
                "packing_lists"). Used for the window title.
            reports_config (list[dict]): A list of report configuration
                dictionaries, each used to create a button.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)

        self.setWindowTitle(f"Select {report_type.replace('_', ' ').title()}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)

        self.report_type = report_type  # Store report type
        layout = QVBoxLayout(self)

        # Add writeoff checkbox for stock_exports
        if report_type == "stock_exports":
            self.writeoff_checkbox = QCheckBox("Include Packaging Materials (SKU Writeoff)")
            self.writeoff_checkbox.setToolTip(
                "When enabled, packaging materials (based on Internal Tags) will be\n"
                "automatically added to the stock export as separate SKU lines.\n"
                "Example: Orders with 'BOX' tag will add PKG-BOX-SMALL to the export."
            )
            self.writeoff_checkbox.setChecked(False)
            layout.addWidget(self.writeoff_checkbox)

            # Add separator line
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            layout.addWidget(line)

        if not reports_config:
            no_reports_label = QLabel("No reports configured for this type.")
            theme = get_theme_manager().get_current_theme()
            no_reports_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; padding: 20px;")
            layout.addWidget(no_reports_label)
        else:
            for report_config in reports_config:
                # Create a button for each report with tooltip
                button = self._create_report_button(report_config)
                layout.addWidget(button)

        layout.addStretch()

    def _create_report_button(self, report_config):
        """Create a button for a single report with tooltip showing filters.

        Args:
            report_config (dict): Report configuration dictionary.

        Returns:
            QPushButton: Button for selecting this report.
        """
        button_text = report_config.get("name", "Unknown Report")
        button = QPushButton(button_text)
        button.clicked.connect(lambda checked=False, rc=report_config: self.on_report_button_clicked(rc))
        button.setMinimumHeight(40)

        # Create tooltip with filters information
        tooltip = self._create_tooltip_text(report_config)
        button.setToolTip(tooltip)

        theme = get_theme_manager().get_current_theme()
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_blue};
                color: white;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
                text-align: left;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {theme.button_hover_light}; }}
            QPushButton:pressed {{ background-color: {theme.button_hover_light}; }}
        """)

        return button

    def _create_tooltip_text(self, report_config):
        """Create tooltip text showing report filters.

        Args:
            report_config (dict): Report configuration dictionary.

        Returns:
            str: Formatted tooltip text with filters.
        """
        tooltip_lines = [f"<b>{report_config.get('name', 'Unknown Report')}</b>", ""]

        filters = report_config.get("filters", {})
        if filters:
            tooltip_lines.append("<b>Applied Filters:</b>")

            # Handle both dict and list formats for filters
            if isinstance(filters, dict):
                # Dictionary format: {key: value}
                for filter_key, filter_value in filters.items():
                    filter_text = self._format_filter(filter_key, filter_value)
                    tooltip_lines.append(f"• {filter_text}")
            elif isinstance(filters, list):
                # List format: [{"field": "key", "value": "val"}, ...]
                for filter_item in filters:
                    if isinstance(filter_item, dict):
                        field = filter_item.get("field", "Unknown")
                        value = filter_item.get("value", "")
                        filter_text = self._format_filter(field, value)
                        tooltip_lines.append(f"• {filter_text}")
            else:
                # Unknown format - display as string
                tooltip_lines.append(f"• {str(filters)}")
        else:
            tooltip_lines.append("<i>No filters (includes all data)</i>")

        return "<br>".join(tooltip_lines)

    def _format_filter(self, filter_key, filter_value):
        """Format a filter for display.

        Args:
            filter_key (str): The filter field name.
            filter_value: The filter value (can be str, list, etc.).

        Returns:
            str: Formatted filter string.
        """
        # Convert key to more readable format
        readable_key = filter_key.replace("_", " ").title()

        # Format value
        if isinstance(filter_value, list):
            if len(filter_value) == 1:
                return f"{readable_key}: {filter_value[0]}"
            else:
                return f"{readable_key}: {', '.join(str(v) for v in filter_value)}"
        else:
            return f"{readable_key}: {filter_value}"

    @Slot(dict)
    def on_report_button_clicked(self, report_config):
        """Handles the click of any report button.

        Emits the `reportSelected` signal with the configuration of the
        clicked report and then closes the dialog.

        Args:
            report_config (dict): The configuration dictionary associated
                with the button that was clicked.
        """
        # Inject writeoff setting into report_config if checkbox exists
        if hasattr(self, 'writeoff_checkbox'):
            report_config["apply_writeoff"] = self.writeoff_checkbox.isChecked()

        self.reportSelected.emit(report_config)
        self.accept()


class _BaseReportDialog(QDialog):
    """Base class for the new preview-enabled report dialogs."""

    reportSelected = Signal(dict)

    def __init__(self, title, reports_config, analysis_df, apply_filters_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(750, 500)
        self.reports_config = reports_config
        self.analysis_df = analysis_df
        self.apply_filters_fn = apply_filters_fn  # callable(df, filters) -> filtered_df
        self._selected_config = None

        self.theme = get_theme_manager().get_current_theme()
        self._preview_cache: dict = {}  # filters fingerprint → (num_orders, num_rows)
        self._init_ui()
        self._populate_list()

        # Select first item automatically
        if self.report_list.count() > 0:
            self.report_list.setCurrentRow(0)

    def _init_ui(self):
        """Create the two-column splitter layout. Subclasses extend this."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # ---- Left panel: report list ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)

        list_label = QLabel("Available Reports")
        list_label.setStyleSheet("font-weight: bold; font-size: 11pt; padding-bottom: 4px;")
        left_layout.addWidget(list_label)

        self.report_list = QListWidget()
        self.report_list.currentRowChanged.connect(self._on_report_selected)
        left_layout.addWidget(self.report_list)

        splitter.addWidget(left_panel)

        # ---- Right panel: preview + actions ----
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([280, 460])
        main_layout.addWidget(splitter, 1)

    def _create_right_panel(self):
        """Create the right panel. Subclasses override to add extra sections."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)

        # Preview group
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_orders_label = QLabel("Select a report to see preview")
        self.preview_orders_label.setStyleSheet("font-size: 10pt; padding: 2px;")
        preview_layout.addWidget(self.preview_orders_label)

        self.preview_filters_text = QTextEdit()
        self.preview_filters_text.setReadOnly(True)
        self.preview_filters_text.setMaximumHeight(120)
        self.preview_filters_text.setStyleSheet(
            f"background-color: {self.theme.background}; "
            f"color: {self.theme.text_secondary}; font-size: 9pt;"
        )
        preview_layout.addWidget(self.preview_filters_text)

        layout.addWidget(preview_group)

        # Subclasses add extra sections here
        self._add_extra_sections(layout)

        layout.addStretch()

        # Generate button
        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme.accent_blue};
                color: white;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {self.theme.button_hover_light}; }}
            QPushButton:pressed {{ background-color: {self.theme.button_hover_light}; }}
            QPushButton:disabled {{ background-color: {self.theme.border}; color: {self.theme.text_secondary}; }}
        """)
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        return panel

    def _add_extra_sections(self, layout):
        """Override in subclasses to add sections between preview and generate button."""
        pass

    def _populate_list(self):
        """Fill the report list from reports_config."""
        self.report_list.clear()
        for cfg in self.reports_config:
            name = cfg.get("name", "Unnamed Report")
            filters = cfg.get("filters", [])
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, cfg)
            item.setToolTip(f"Filters: {len(filters)} active" if filters else "No filters")
            self.report_list.addItem(item)

    def _on_report_selected(self, row):
        """Handle selection of a report from the list."""
        if row < 0:
            self._selected_config = None
            self.generate_btn.setEnabled(False)
            self.preview_orders_label.setText("Select a report to see preview")
            self.preview_filters_text.setPlainText("")
            return

        item = self.report_list.item(row)
        cfg = item.data(Qt.UserRole)
        self._selected_config = cfg
        self.generate_btn.setEnabled(True)
        self._update_preview(cfg)

    def _update_preview(self, cfg):
        """Compute and show preview for the selected report config."""
        filters = cfg.get("filters", [])

        # Count matching rows (cached by filter fingerprint to avoid re-filtering on every click)
        if self.analysis_df is not None and not self.analysis_df.empty and self.apply_filters_fn:
            try:
                cache_key = str(filters)
                if cache_key not in self._preview_cache:
                    filtered = self.apply_filters_fn(self.analysis_df, filters)
                    order_col = "Order_Number" if "Order_Number" in filtered.columns else (filtered.columns[0] if not filtered.empty else None)
                    num_orders = filtered[order_col].nunique() if (not filtered.empty and order_col) else 0
                    self._preview_cache[cache_key] = (num_orders, len(filtered))
                num_orders, num_rows = self._preview_cache[cache_key]
                self.preview_orders_label.setText(
                    f"Matching: {num_orders} orders · {num_rows} rows"
                )
            except Exception:
                self.preview_orders_label.setText("Preview unavailable")
        else:
            self.preview_orders_label.setText("Run analysis first to see preview")

        # Format filters description
        if filters:
            lines = []
            for f in filters:
                field = f.get("field", "?")
                op = f.get("operator", "=")
                val = f.get("value", "")
                lines.append(f"• {field} {op} {val}")
            self.preview_filters_text.setPlainText("\n".join(lines))
        else:
            self.preview_filters_text.setPlainText("(no filters — includes all data)")

    def _build_emit_config(self):
        """Build the config dict to emit. Override to inject extra fields."""
        return dict(self._selected_config)

    def _on_generate(self):
        """Emit reportSelected with the selected config and close."""
        if self._selected_config is None:
            return
        emit_config = self._build_emit_config()
        self.reportSelected.emit(emit_config)
        self.accept()


class PackingListDialog(_BaseReportDialog):
    """Two-column dialog for selecting and previewing packing list reports."""

    def __init__(self, reports_config, analysis_df, apply_filters_fn, parent=None):
        super().__init__(
            "Generate Packing List",
            reports_config,
            analysis_df,
            apply_filters_fn,
            parent
        )
        self.setWindowTitle("Generate Packing List")


class StockExportDialog(_BaseReportDialog):
    """Two-column dialog for selecting and previewing stock export reports.

    Includes an integrated Writeoff Report section replacing the old standalone button.
    """

    writeoff_requested = Signal()  # emitted when "Generate Writeoff Only" is clicked

    def __init__(self, reports_config, analysis_df, apply_filters_fn,
                 writeoff_handler=None, parent=None):
        """
        Args:
            writeoff_handler: Callable to call when "Generate Writeoff Only" is clicked.
                              If None, the button is hidden.
        """
        self._writeoff_handler = writeoff_handler
        super().__init__(
            "Generate Stock Export",
            reports_config,
            analysis_df,
            apply_filters_fn,
            parent
        )
        self.setWindowTitle("Generate Stock Export")

    def _add_extra_sections(self, layout):
        """Add the Writeoff section between preview and generate button."""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        writeoff_group = QGroupBox("Writeoff Report")
        writeoff_layout = QVBoxLayout(writeoff_group)

        self.writeoff_checkbox = QCheckBox("Include Packaging Materials in export (SKU Writeoff)")
        self.writeoff_checkbox.setToolTip(
            "When enabled, packaging materials (based on Internal Tags) will be\n"
            "automatically added to the stock export as separate SKU lines.\n"
            "Example: Orders with 'BOX' tag will add PKG-BOX-SMALL to the export."
        )
        writeoff_layout.addWidget(self.writeoff_checkbox)

        if self._writeoff_handler:
            self.writeoff_only_btn = QPushButton("Generate Writeoff Report Only")
            self.writeoff_only_btn.setMinimumHeight(36)
            theme = get_theme_manager().get_current_theme()
            self.writeoff_only_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.accent_orange};
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton:hover {{ background-color: #F57C00; }}
                QPushButton:pressed {{ background-color: #E65100; }}
            """)
            self.writeoff_only_btn.clicked.connect(self._on_writeoff_only)
            writeoff_layout.addWidget(self.writeoff_only_btn)

        layout.addWidget(writeoff_group)

    def _on_writeoff_only(self):
        """Call writeoff handler and close the dialog."""
        if self._writeoff_handler:
            self._writeoff_handler()
        self.accept()

    def _build_emit_config(self):
        """Include apply_writeoff flag in the emitted config."""
        cfg = dict(self._selected_config)
        cfg["apply_writeoff"] = self.writeoff_checkbox.isChecked() if hasattr(self, 'writeoff_checkbox') else False
        return cfg
