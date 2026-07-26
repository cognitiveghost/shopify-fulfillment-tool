"""Custom ItemDelegate for drawing borders between order groups."""

from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from gui.theme_manager import get_theme_manager


class OrderGroupDelegate(QStyledItemDelegate):
    """
    Custom delegate that draws borders between order groups.

    Detects when Order_Number changes and draws a bold line at the bottom
    of the last row of each order to visually separate order groups.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.order_column_name = "Order_Number"

    def paint(self, painter, option, index):
        """Paint cell with border if it's the last row of an order."""

        # Call parent paint first to render the cell normally
        super().paint(painter, option, index)

        # Get model
        model = index.model()
        if model is None:
            return

        current_row = index.row()
        total_rows = model.rowCount()

        # Don't draw border on last row of table
        if current_row >= total_rows - 1:
            return

        # Try to get source model (unwrap proxy if needed)
        source_model = model
        if hasattr(model, 'sourceModel'):
            source_model = model.sourceModel()

        # Get DataFrame from source model
        if not hasattr(source_model, '_dataframe'):
            return

        df = source_model._dataframe
        if df is None or df.empty:
            return

        if self.order_column_name not in df.columns:
            return

        # Map proxy row to source row if using proxy model
        if hasattr(model, 'mapToSource'):
            source_index = model.mapToSource(index)
            source_row = source_index.row()
            next_source_index = model.mapToSource(model.index(current_row + 1, 0))
            next_source_row = next_source_index.row()
        else:
            source_row = current_row
            next_source_row = current_row + 1

        # Bounds check
        if source_row < 0 or source_row >= len(df):
            return
        if next_source_row < 0 or next_source_row >= len(df):
            return

        # Get order numbers
        try:
            current_order = df.iloc[source_row][self.order_column_name]
            next_order = df.iloc[next_source_row][self.order_column_name]
        except (IndexError, KeyError):
            return

        # Check if next row has different order number
        if current_order != next_order:
            # Draw bottom border
            painter.save()

            # Use theme border color (white in dark theme, gray in light theme)
            theme = get_theme_manager().get_current_theme()
            border_color = QColor(theme.border)
            pen = QPen(border_color, 2)  # 2px line width
            painter.setPen(pen)

            # Draw line at bottom of cell
            rect = option.rect
            painter.drawLine(
                rect.left(), rect.bottom(),
                rect.right(), rect.bottom()
            )

            painter.restore()
