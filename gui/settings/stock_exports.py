"""Pre-configured stock export reports."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.settings.fields import FILTER_OPERATORS, FILTERABLE_COLUMNS, add_filter_row
from gui.theme_manager import set_button_role


class StockExportsPage(SettingsPage):
    """Stock export reports, stored under config_data["stock_export_configs"]."""

    def __init__(self, configs: list, analysis_df, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self.stock_export_widgets = []

        main_layout = QVBoxLayout(self)
        add_btn = QPushButton("Add New Stock Export")
        set_button_role(add_btn, "secondary")
        add_btn.clicked.connect(self.add_stock_export_widget)
        main_layout.addWidget(add_btn, 0, Qt.AlignLeft)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.stock_exports_layout = QVBoxLayout(scroll_content)
        self.stock_exports_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        for se_config in configs:
            self.add_stock_export_widget(se_config)

    def add_stock_export_widget(self, config=None):
        """Adds a new group of widgets for a single stock export configuration.

        Args:
            config (dict, optional): The configuration for a pre-existing
                stock export. If None, creates a new, blank one.
        """
        if not isinstance(config, dict):
            config = {"name": "", "output_filename": "", "filters": []}
        se_box = QGroupBox()
        se_layout = QVBoxLayout(se_box)
        form_layout = QFormLayout()
        name_edit = QLineEdit(config.get("name", ""))
        filename_edit = QLineEdit(config.get("output_filename", ""))
        form_layout.addRow("Name:", name_edit)
        form_layout.addRow("Output Filename:", filename_edit)
        se_layout.addLayout(form_layout)
        filters_box = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_box)
        filters_rows_layout = QVBoxLayout()
        filters_layout.addLayout(filters_rows_layout)
        add_filter_btn = QPushButton("Add Filter")
        set_button_role(add_filter_btn, "secondary")
        filters_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        se_layout.addWidget(filters_box)
        delete_btn = QPushButton("Delete Stock Export")
        set_button_role(delete_btn, "secondary")
        se_layout.addWidget(delete_btn, 0, Qt.AlignRight)
        self.stock_exports_layout.addWidget(se_box)
        widget_refs = {
            "group_box": se_box,
            "name": name_edit,
            "filename": filename_edit,
            "filters_layout": filters_rows_layout,
            "filters": [],
        }
        self.stock_export_widgets.append(widget_refs)
        add_filter_btn.clicked.connect(
            lambda: add_filter_row(widget_refs, FILTERABLE_COLUMNS, FILTER_OPERATORS, self.analysis_df)
        )
        delete_btn.clicked.connect(lambda: self._delete_stock_export_widget(widget_refs))
        for f_config in config.get("filters", []):
            add_filter_row(widget_refs, FILTERABLE_COLUMNS, FILTER_OPERATORS, self.analysis_df, f_config)

    def _delete_stock_export_widget(self, widget_refs):
        widget_refs["group_box"].deleteLater()
        self.stock_export_widgets.remove(widget_refs)

    def collect(self) -> dict:
        new_stock_exports = []
        for se_w in self.stock_export_widgets:
            filters = []
            for f in se_w["filters"]:
                value_widget = f.get("value_widget")
                val = ""
                if value_widget:
                    if isinstance(value_widget, QComboBox):
                        val = value_widget.currentText()
                    else:
                        val = value_widget.text()

                filters.append({
                    "field": f["field"].currentText(),
                    "operator": f["op"].currentText(),
                    "value": val,
                })

            new_stock_exports.append({
                "name": se_w["name"].text(),
                "output_filename": se_w["filename"].text(),
                "filters": filters,
            })

        return {"stock_export_configs": new_stock_exports}
