"""Checkbox delegate for bulk selection.

This module provides a custom delegate that renders a checkbox in the first
column of the Analysis Results table for bulk selection functionality.
"""

from PySide6.QtCore import QEvent, QRect
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
)


class CheckboxDelegate(QStyledItemDelegate):
    """Renders checkbox in first column for bulk selection.

    This delegate is used to draw checkboxes in the first column of the
    results table when bulk mode is active. It handles both rendering
    and click events for toggling the checkbox state.

    Attributes:
        selection_helper: Reference to SelectionHelper instance for state management
    """

    def __init__(self, selection_helper, parent=None):
        """Initialize the checkbox delegate.

        Args:
            selection_helper: SelectionHelper instance that manages checkbox state
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.selection_helper = selection_helper

    def _is_first_row_of_order(self, source_row: int) -> bool:
        """Check if this row is the first row of its order.

        Only the first row of each order shows a checkbox.
        Other rows of multi-item orders don't show checkboxes.

        Args:
            source_row: Source DataFrame row index

        Returns:
            True if this is the first row of the order
        """
        df = self.selection_helper.main_window.analysis_results_df
        if df is None or df.empty or source_row not in df.index:
            return True  # Fallback: show checkbox

        order_number = df.loc[source_row, 'Order_Number']
        # Find all rows with this order number
        order_rows = df[df['Order_Number'] == order_number].index.tolist()

        # This is the first row if it's the minimum index
        return source_row == min(order_rows)

    def paint(self, painter: QPainter, option, index):
        """Draw checkbox in cell.

        Checkbox is only drawn for the first row of each order.
        Other rows of multi-item orders show empty cells.

        Args:
            painter: QPainter instance for drawing
            option: Style options for the item
            index: Model index of the item
        """
        # Get source row index through proxy model
        model = index.model()
        if hasattr(model, 'mapToSource'):
            source_index = model.mapToSource(index)
            source_row = source_index.row()
        else:
            source_row = index.row()

        # Let the style paint the background. Not palette.highlight(): that is
        # still accent_fill (QPalette.Highlight drives text selection, and
        # packing-tool's Packer Mode derives a cell colour from it), while a
        # selected row is now selection_bg plus a selection_border ring. Filling
        # it here would punch an accent block through the row and drop this
        # cell's segment of the ring.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # Only show checkbox for the first row of each order
        if not self._is_first_row_of_order(source_row):
            return  # Don't draw checkbox for non-first rows

        # Determine checkbox state
        is_checked = self.selection_helper.is_row_checked(source_row)

        # Create checkbox style option
        checkbox_rect = self._get_checkbox_rect(option.rect)
        checkbox_option = QStyleOptionButton()
        checkbox_option.rect = checkbox_rect
        checkbox_option.palette = option.palette
        checkbox_option.state = QStyle.State_Enabled

        if is_checked:
            checkbox_option.state |= QStyle.State_On
        else:
            checkbox_option.state |= QStyle.State_Off

        # Draw checkbox. Pass the view's widget through so Qt's
        # QStyleSheetStyle (active once the app has a stylesheet, which this
        # app's theme system always applies) can resolve the themed
        # QTableView::indicator QSS rule -- without a widget it silently
        # falls back to the base style's unthemed default checkbox, which
        # rendered as a plain white box against the app's dark theme.
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(
            QStyle.CE_CheckBox,
            checkbox_option,
            painter,
            option.widget,
        )

    def editorEvent(self, event, model, option, index):
        """Handle checkbox click events.

        Only handles clicks on the first row of each order.
        Clicks on non-first rows are ignored (no checkbox there).

        Args:
            event: The event (mouse click, etc.)
            model: The data model
            option: Style options
            index: Model index of the clicked item

        Returns:
            True if event was handled, False otherwise
        """
        if event.type() == QEvent.MouseButtonRelease:
            # Check if click was within checkbox bounds
            checkbox_rect = self._get_checkbox_rect(option.rect)
            if checkbox_rect.contains(event.pos()):
                # Get source row index through proxy model
                if hasattr(model, 'mapToSource'):
                    source_index = model.mapToSource(index)
                    source_row = source_index.row()
                else:
                    source_row = index.row()

                # Only handle clicks on the first row of each order
                if not self._is_first_row_of_order(source_row):
                    return True  # Consume event but don't toggle

                # Toggle checkbox (toggles entire order via SelectionHelper)
                self.selection_helper.toggle_row(source_row)

                # Force repaint of entire table to update all rows of the order
                main_window = self.selection_helper.main_window
                if hasattr(main_window, 'tableView'):
                    main_window.tableView.viewport().update()

                # Update toolbar selection count if available
                if hasattr(main_window, '_update_bulk_toolbar_state'):
                    main_window._update_bulk_toolbar_state()

                return True

        return super().editorEvent(event, model, option, index)

    def _get_checkbox_rect(self, cell_rect: QRect) -> QRect:
        """Calculate centered checkbox rectangle within cell.

        Args:
            cell_rect: The cell rectangle

        Returns:
            QRect for the centered checkbox
        """
        checkbox_size = 20
        x = cell_rect.x() + (cell_rect.width() - checkbox_size) // 2
        y = cell_rect.y() + (cell_rect.height() - checkbox_size) // 2
        return QRect(x, y, checkbox_size, checkbox_size)

    def sizeHint(self, option, index):
        """Return preferred size for checkbox cell.

        Args:
            option: Style options
            index: Model index

        Returns:
            Preferred QSize (fixed width for checkbox column)
        """
        from PySide6.QtCore import QSize
        return QSize(30, option.rect.height())
