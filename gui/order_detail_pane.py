"""The right-hand pane: everything about the order the table row stands for.

The table went from one row per SKU line to one row per order, so the lines had
to go somewhere. They go here, together with the tag panel that was already
keyed to one selected order and only ever toggled into view. See
``docs/superpowers/specs/2026-08-30-analysis-results-1b-design.md`` section 5.
"""

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui.pandas_model import PandasModel
from gui.status_edge_delegate import StatusEdgeDelegate
from gui.tag_management_panel import TagManagementPanel
from gui.theme_manager import font_css, get_theme_manager


class OrderDetailPane(QWidget):
    """Shows the current order. Not the multi-selection -- one order."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._order_number = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.header_label = QLabel("No order selected")
        self.header_label.setStyleSheet(font_css("display_xl"))
        layout.addWidget(self.header_label)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        self.blocker_label = QLabel("")
        self.blocker_label.setWordWrap(True)
        self.blocker_label.hide()
        layout.addWidget(self.blocker_label)

        self.lines_table = QTableView()
        self.lines_table.setSelectionBehavior(QTableView.SelectRows)
        self.lines_table.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.lines_table.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.lines_table.verticalHeader().hide()
        self.lines_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lines_table.setItemDelegate(StatusEdgeDelegate(self.lines_table))
        layout.addWidget(self.lines_table, 1)

        self.tag_panel = TagManagementPanel(self)
        layout.addWidget(self.tag_panel)

        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        layout.addWidget(self.notes_label)

        self._apply_theme()
        get_theme_manager().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        theme = theme or get_theme_manager().get_current_theme()
        self.meta_label.setStyleSheet(
            f"{font_css('caption')} color: {theme.text_secondary};"
        )
        self.notes_label.setStyleSheet(
            f"{font_css('caption')} color: {theme.text_secondary};"
        )
        self.blocker_label.setStyleSheet(
            f"{font_css('body')} color: {theme.status_danger};"
            f" background-color: {theme.status_danger_bg};"
            " padding: 6px; border-radius: 4px;"
        )

    @staticmethod
    def _text(row: pd.Series, column: str) -> str:
        value = row.get(column, "")
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value)

    def set_order(self, order_number, order_row: pd.Series, lines: pd.DataFrame) -> None:
        """Show one order. ``order_row`` is a row of the order frame."""
        self._order_number = order_number
        self.header_label.setText(str(order_number))

        meta = [
            self._text(order_row, "Order_Fulfillment_Status"),
            self._text(order_row, "Shipping_Provider"),
            self._text(order_row, "Destination_Country"),
            self._text(order_row, "Shipping_Method"),
        ]
        self.meta_label.setText("  ·  ".join(part for part in meta if part))

        blocker = self._text(order_row, "Blocker")
        self.blocker_label.setText(blocker)
        self.blocker_label.setVisible(bool(blocker))

        self.lines_table.setModel(PandasModel(lines, self.lines_table))
        self.lines_table.resizeColumnsToContents()

        notes = self._text(order_row, "Notes")
        self.notes_label.setText(notes)
        self.notes_label.setVisible(bool(notes))

        self.tag_panel.set_selected_order(
            order_number, self._text(order_row, "Internal_Tags") or "[]"
        )

    def clear(self) -> None:
        self._order_number = None
        self.header_label.setText("No order selected")
        self.meta_label.setText("")
        self.blocker_label.setText("")
        self.blocker_label.hide()
        self.notes_label.setText("")
        self.lines_table.setModel(None)
        self.tag_panel.set_selected_order(None, "[]")
