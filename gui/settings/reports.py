"""Packing list and stock export reports, in one settings page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.settings.report_editor import PACKING_LISTS, STOCK_EXPORTS, ReportEditor
from gui.theme_manager import set_button_role

_SECTIONS = (
    (PACKING_LISTS, "Packing Lists", "Add New Packing List", "packing_list_configs"),
    (STOCK_EXPORTS, "Stock Exports", "Add New Stock Export", "stock_export_configs"),
)


class ReportsPage(SettingsPage):
    """Owns both packing_list_configs and stock_export_configs.

    The SettingsPage contract allows one page to own several config keys; each
    value returned by collect() replaces config_data[key] outright.
    """

    def __init__(self, packing_configs, stock_configs, analysis_df=None, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self._editors = {PACKING_LISTS: [], STOCK_EXPORTS: []}
        self._layouts = {}

        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)

        for kind, title, add_label, _ in _SECTIONS:
            heading = QLabel(title)
            heading_font = heading.font()
            heading_font.setBold(True)
            heading.setFont(heading_font)
            content_layout.addWidget(heading)

            add_btn = QPushButton(add_label)
            set_button_role(add_btn, "secondary")
            add_btn.clicked.connect(lambda _checked=False, k=kind: self.add_report(k))
            content_layout.addWidget(add_btn, 0, Qt.AlignLeft)

            section_layout = QVBoxLayout()
            content_layout.addLayout(section_layout)
            self._layouts[kind] = section_layout

        for config in packing_configs or []:
            self.add_report(PACKING_LISTS, config)
        for config in stock_configs or []:
            self.add_report(STOCK_EXPORTS, config)

    def add_report(self, kind, config=None):
        """Adds one report editor to the given section."""
        editor = ReportEditor(kind, config, self.analysis_df)
        editor.delete_button.clicked.connect(
            lambda _checked=False, e=editor, k=kind: self._delete(k, e)
        )
        self._layouts[kind].addWidget(editor)
        self._editors[kind].append(editor)
        return editor

    def _delete(self, kind, editor):
        editor.deleteLater()
        self._editors[kind].remove(editor)

    def collect(self) -> dict:
        return {
            config_key: [e.collect() for e in self._editors[kind]]
            for kind, _title, _label, config_key in _SECTIONS
        }
