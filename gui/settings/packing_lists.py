"""Pre-configured packing list reports."""

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


class PackingListsPage(SettingsPage):
    """Packing list reports, stored under config_data["packing_list_configs"]."""

    def __init__(self, configs: list, analysis_df, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self.packing_list_widgets = []

        main_layout = QVBoxLayout(self)
        add_btn = QPushButton("Add New Packing List")
        add_btn.clicked.connect(self.add_packing_list_widget)
        main_layout.addWidget(add_btn, 0, Qt.AlignLeft)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.packing_lists_layout = QVBoxLayout(scroll_content)
        self.packing_lists_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        for pl_config in configs:
            self.add_packing_list_widget(pl_config)

    def add_packing_list_widget(self, config=None):
        """Adds a new group of widgets for a single packing list configuration.

        Args:
            config (dict, optional): The configuration for a pre-existing
                packing list. If None, creates a new, blank one.
        """
        if not isinstance(config, dict):
            config = {"name": "", "output_filename": "", "filters": [], "exclude_skus": []}
        pl_box = QGroupBox()
        pl_layout = QVBoxLayout(pl_box)
        form_layout = QFormLayout()
        name_edit = QLineEdit(config.get("name", ""))
        filename_edit = QLineEdit(config.get("output_filename", ""))
        exclude_skus_edit = QLineEdit(",".join(config.get("exclude_skus", [])))
        form_layout.addRow("Name:", name_edit)
        form_layout.addRow("Output Filename:", filename_edit)
        form_layout.addRow("Exclude SKUs (comma-separated):", exclude_skus_edit)
        pl_layout.addLayout(form_layout)
        filters_box = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_box)
        filters_rows_layout = QVBoxLayout()
        filters_layout.addLayout(filters_rows_layout)
        add_filter_btn = QPushButton("Add Filter")
        filters_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        pl_layout.addWidget(filters_box)
        delete_btn = QPushButton("Delete Packing List")
        pl_layout.addWidget(delete_btn, 0, Qt.AlignRight)
        self.packing_lists_layout.addWidget(pl_box)
        widget_refs = {
            "group_box": pl_box,
            "name": name_edit,
            "filename": filename_edit,
            "exclude_skus": exclude_skus_edit,
            "filters_layout": filters_rows_layout,
            "filters": [],
        }
        self.packing_list_widgets.append(widget_refs)
        add_filter_btn.clicked.connect(
            lambda: add_filter_row(widget_refs, FILTERABLE_COLUMNS, FILTER_OPERATORS, self.analysis_df)
        )
        delete_btn.clicked.connect(lambda: self._delete_packing_list_widget(widget_refs))
        for f_config in config.get("filters", []):
            add_filter_row(widget_refs, FILTERABLE_COLUMNS, FILTER_OPERATORS, self.analysis_df, f_config)

    def _delete_packing_list_widget(self, widget_refs):
        widget_refs["group_box"].deleteLater()
        self.packing_list_widgets.remove(widget_refs)

    def collect(self) -> dict:
        new_packing_lists = []
        for pl_w in self.packing_list_widgets:
            filters = []
            for f in pl_w["filters"]:
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

            # Parse exclude_skus from comma-separated string
            exclude_skus_text = pl_w["exclude_skus"].text().strip()
            exclude_skus = []
            if exclude_skus_text:
                exclude_skus = [s.strip() for s in exclude_skus_text.split(',') if s.strip()]

            new_packing_lists.append({
                "name": pl_w["name"].text(),
                "output_filename": pl_w["filename"].text(),
                "filters": filters,
                "exclude_skus": exclude_skus,
            })

        return {"packing_list_configs": new_packing_lists}
