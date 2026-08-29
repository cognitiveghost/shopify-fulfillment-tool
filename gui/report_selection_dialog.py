from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.theme_manager import font_css, get_theme_manager, set_button_role


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
        list_label.setStyleSheet(f"{font_css('label')} padding-bottom: 4px;")
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
        self.preview_orders_label.setStyleSheet(f"{font_css('body')} padding: 2px;")
        preview_layout.addWidget(self.preview_orders_label)

        self.preview_filters_text = QTextEdit()
        self.preview_filters_text.setReadOnly(True)
        self.preview_filters_text.setMaximumHeight(120)
        self.preview_filters_text.setStyleSheet(
            f"background-color: {self.theme.surface}; "
            f"color: {self.theme.text_secondary}; {font_css('caption')}"
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
        set_button_role(self.generate_btn, "primary")
        self.generate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme.accent_fill};
                color: {self.theme.on_accent};
                {font_css('body', bold=True)}
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{ background-color: {self.theme.accent_fill_active}; }}
            QPushButton:pressed {{ background-color: {self.theme.accent_fill_active}; }}
            QPushButton:disabled {{ background-color: {self.theme.border}; color: {self.theme.text_secondary}; }}
        """)
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        return panel

    def _add_extra_sections(self, layout):
        """Override in subclasses to add sections between preview and generate button."""

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


_SECTION_HEADER_MARKER = "__section_header__"


class GenerateReportsDialog(_BaseReportDialog):
    """Multi-select dialog generating any number of packing lists and stock
    exports in one pass.

    Both kinds share one checkable list under non-selectable section header
    rows, following the header-row pattern in column_config_dialog
    (_CATEGORY_HEADER_MARKER): a row flagged Qt.NoItemFlags with a sentinel in
    Qt.UserRole so it can't be checked or selected but still renders inline.
    """

    reportsSelected = Signal(list)

    def __init__(self, packing_configs, stock_configs, analysis_df, apply_filters_fn,
                 writeoff_handler=None, parent=None):
        self._packing_configs = packing_configs or []
        self._stock_configs = stock_configs or []
        self._writeoff_handler = writeoff_handler
        self._checked_count = 0
        super().__init__(
            "Generate Reports",
            [],  # reports_config unused here -- _populate_list is overridden
            analysis_df,
            apply_filters_fn,
            parent,
        )
        self.report_list.setCurrentRow(-1)

    def _init_ui(self):
        super()._init_ui()
        self.footer_label = QLabel("0 selected")
        self.layout().addWidget(self.footer_label)

    def _add_extra_sections(self, layout):
        """Add the Writeoff section, same as StockExportDialog."""
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
                    background-color: {theme.status_warning};
                    color: {theme.on_accent};
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton:hover {{ background-color: {theme.status_warning}; }}
                QPushButton:pressed {{ background-color: {theme.status_warning}; }}
            """)
            self.writeoff_only_btn.clicked.connect(self._on_writeoff_only)
            writeoff_layout.addWidget(self.writeoff_only_btn)

        layout.addWidget(writeoff_group)

    def _on_writeoff_only(self):
        if self._writeoff_handler:
            self._writeoff_handler()
        self.accept()

    def _populate_list(self):
        """Fill the list with both kinds under section headers."""
        self.report_list.clear()
        self.generate_btn.setText("Generate Selected Reports")

        for kind, title, configs in (
            ("packing_lists", "PACKING LISTS", self._packing_configs),
            ("stock_exports", "STOCK EXPORTS", self._stock_configs),
        ):
            header_item = QListWidgetItem(title)
            header_item.setFlags(Qt.NoItemFlags)
            header_item.setData(Qt.UserRole, _SECTION_HEADER_MARKER)
            header_font = header_item.font()
            header_font.setBold(True)
            header_item.setFont(header_font)
            header_item.setForeground(QColor(self.theme.text_secondary))
            self.report_list.addItem(header_item)

            for index, cfg in enumerate(configs):
                name = cfg.get("name", "Unnamed Report")
                filters = cfg.get("filters", [])
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setData(Qt.UserRole, (kind, index, cfg))
                item.setToolTip(f"Filters: {len(filters)} active" if filters else "No filters")
                self.report_list.addItem(item)

        self.report_list.itemChanged.connect(self._on_item_changed)

    def _on_report_selected(self, row):
        """Selecting (not checking) a row updates the preview."""
        if row < 0:
            return
        item = self.report_list.item(row)
        data = item.data(Qt.UserRole)
        if data == _SECTION_HEADER_MARKER:
            return
        _kind, _index, cfg = data
        self._selected_config = cfg
        self._update_preview(cfg)

    def _on_item_changed(self, item):
        data = item.data(Qt.UserRole)
        if data == _SECTION_HEADER_MARKER:
            return
        self._checked_count = sum(
            1
            for i in range(self.report_list.count())
            if self.report_list.item(i).data(Qt.UserRole) != _SECTION_HEADER_MARKER
            and self.report_list.item(i).checkState() == Qt.Checked
        )
        self.footer_label.setText(f"{self._checked_count} selected")
        self.generate_btn.setEnabled(self._checked_count > 0)

    def set_checked(self, kind, index, checked):
        """Checks/unchecks the row for (kind, index). Used by the UI and tests."""
        for i in range(self.report_list.count()):
            item = self.report_list.item(i)
            data = item.data(Qt.UserRole)
            if data != _SECTION_HEADER_MARKER and data[0] == kind and data[1] == index:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                return

    @property
    def generate_button(self):
        return self.generate_btn

    def _on_generate(self):
        """Emit every checked report, in list order, with its report_type."""
        batch = []
        for i in range(self.report_list.count()):
            item = self.report_list.item(i)
            data = item.data(Qt.UserRole)
            if data == _SECTION_HEADER_MARKER or item.checkState() != Qt.Checked:
                continue
            kind, _index, cfg = data
            entry = {**cfg, "report_type": kind}
            if kind == "stock_exports" and hasattr(self, "writeoff_checkbox"):
                entry["apply_writeoff"] = self.writeoff_checkbox.isChecked()
            batch.append(entry)

        if not batch:
            return

        self.reportsSelected.emit(batch)
        self.accept()
