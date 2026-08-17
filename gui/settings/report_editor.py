"""One report's editor, shared by both report kinds.

PackingListsPage and StockExportsPage each carried their own copy of this
widget and differed only in the exclude-SKUs field. The two differences that
remain -- exclude SKUs and the column picker -- are packing-list only and
switch on `kind`.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from gui.settings.fields import (
    REPORT_FILTER_OPERATORS,
    add_filter_row,
    report_filter_fields,
)
from gui.theme_manager import set_button_role
from shopify_tool.report_filters import normalize_operator

PACKING_LISTS = "packing_lists"
STOCK_EXPORTS = "stock_exports"


class ReportEditor(QGroupBox):
    """Editor for a single packing-list or stock-export config."""

    def __init__(self, kind, config=None, analysis_df=None, parent=None):
        super().__init__(parent)
        if kind not in (PACKING_LISTS, STOCK_EXPORTS):
            raise ValueError(f"Unknown report kind: {kind}")
        self.kind = kind
        self.analysis_df = analysis_df
        self.filters = []

        if not isinstance(config, dict):
            config = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(config.get("name", ""))
        self.filename_edit = QLineEdit(config.get("output_filename", ""))
        form.addRow("Name:", self.name_edit)
        form.addRow("Output Filename:", self.filename_edit)

        self.exclude_skus_edit = None
        self.columns_list = None
        if kind == PACKING_LISTS:
            self.exclude_skus_edit = QLineEdit(",".join(config.get("exclude_skus", [])))
            form.addRow("Exclude SKUs (comma-separated):", self.exclude_skus_edit)
        layout.addLayout(form)

        filters_box = QGroupBox("Filters")
        filters_box_layout = QVBoxLayout(filters_box)
        self.filters_layout = QVBoxLayout()
        filters_box_layout.addLayout(self.filters_layout)
        add_filter_btn = QPushButton("Add Filter")
        set_button_role(add_filter_btn, "secondary")
        add_filter_btn.clicked.connect(self._add_filter)
        filters_box_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        layout.addWidget(filters_box)

        if kind == PACKING_LISTS:
            columns_box = QGroupBox("Columns to display")
            columns_layout = QVBoxLayout(columns_box)
            hint = QLabel("Leave all unchecked to use the default layout.")
            hint.setWordWrap(True)
            columns_layout.addWidget(hint)
            self.columns_list = QListWidget()
            # An unbounded QListWidget inside the settings page's scroll area
            # collapses to about two visible rows.
            self.columns_list.setMinimumHeight(160)
            chosen = config.get("columns") or []
            # Same rule as the filter field combo: offer the union, never
            # just the sourced list. _chosen_columns can only return what has
            # an item, so a saved column missing from the offered list is
            # dropped on the next save -- and the offered list is the short
            # static fallback until an analysis has been run. Warehouse_Name
            # is a default packing-list column that is not in it.
            offered = report_filter_fields(analysis_df)
            offered += [name for name in chosen if name not in offered]
            for name in offered:
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if name in chosen else Qt.Unchecked)
                self.columns_list.addItem(item)
            columns_layout.addWidget(self.columns_list)
            # ponytail: checkbox list gives column choice but not arbitrary
            # column order -- the saved order is the picker's. Add Move Up /
            # Move Down buttons (see ColumnConfigPanel, which already does
            # exactly this) if a user asks to reorder printed columns.
            layout.addWidget(columns_box)

        self.delete_button = QPushButton("Delete")
        set_button_role(self.delete_button, "secondary")
        layout.addWidget(self.delete_button, 0, Qt.AlignRight)

        for f_config in config.get("filters", []):
            self._add_filter(f_config)

    def _add_filter(self, f_config=None):
        # Normalise the stored operator before it reaches the combo box.
        # add_filter_row does op_combo.setCurrentText(stored), and on a
        # non-editable QComboBox that is a silent no-op when the string is not
        # in the list -- leaving index 0, "equals". A saved "!=" or "not in"
        # filter would therefore render as "equals" and be written back that
        # way on the next save, inverting the filter against live client
        # configs. Verified: setCurrentText("!=") leaves the combo on "equals".
        if isinstance(f_config, dict):
            f_config = {**f_config, "operator": normalize_operator(f_config.get("operator"))}
        else:
            f_config = None

        add_filter_row(
            {"filters_layout": self.filters_layout, "filters": self.filters},
            report_filter_fields(self.analysis_df),
            REPORT_FILTER_OPERATORS,
            self.analysis_df,
            f_config,
        )

    def _chosen_columns(self):
        """The ticked columns, in list order. Empty means "default layout"."""
        if self.columns_list is None:
            return []
        return [
            self.columns_list.item(i).text()
            for i in range(self.columns_list.count())
            if self.columns_list.item(i).checkState() == Qt.Checked
        ]

    def collect(self) -> dict:
        """This report's config dict.

        Packing-list-only keys are omitted entirely for stock exports rather
        than written as empty -- a stock export config that grew an
        exclude_skus key would be silently carried into the saved profile.
        """
        filters = []
        for f in self.filters:
            value_widget = f.get("value_widget")
            if isinstance(value_widget, QComboBox):
                val = value_widget.currentText()
            elif value_widget is not None:
                val = value_widget.text()
            else:
                val = ""
            filters.append({
                "field": f["field"].currentText(),
                "operator": f["op"].currentText(),
                "value": val,
            })

        config = {
            "name": self.name_edit.text(),
            "output_filename": self.filename_edit.text(),
            "filters": filters,
        }

        if self.kind == PACKING_LISTS:
            raw = self.exclude_skus_edit.text().strip()
            config["exclude_skus"] = [s.strip() for s in raw.split(",") if s.strip()]
            chosen = self._chosen_columns()
            if chosen:
                config["columns"] = chosen

        return config
