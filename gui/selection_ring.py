"""The two end caps that close a selected row's ring.

`QTableView::item` styles *cells*, so a QSS left or right border would repeat
at every column boundary -- which is why the shipped selection is two
horizontal rules, open at both ends, and why the status edge on a
selected-and-blocked row reads as part of the selection.

The horizontal sides stay in QSS, where they already work. Each cell paints
only the caps it owns, at its own option.rect, so nothing depends on how
QTableView clips one cell against another and the caps meet the QSS borders
exactly -- same rect, same width.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §4
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from gui.theme_manager import get_theme_manager

# Matches the 2px selection_border top and bottom in build_stylesheet's
# QTableView::item:selected rule. Both name theme.selection_border.
RING_WIDTH = 2


def _edge_visible_column(header, forward: bool) -> int | None:
    """Logical index of the leftmost (or rightmost) column the user can see.

    Visual order, not logical: a user who drags a column to the front must
    still get the cap on the left of the row. Hidden columns are walked past,
    which is normally zero iterations.
    """
    if header is None:
        return None
    order = range(header.count()) if forward else range(header.count() - 1, -1, -1)
    for visual in order:
        logical = header.logicalIndex(visual)
        if not header.isSectionHidden(logical):
            return logical
    return None


def first_visible_column(header) -> int | None:
    return _edge_visible_column(header, forward=True)


def last_visible_column(header) -> int | None:
    return _edge_visible_column(header, forward=False)


def caps(header, column: int) -> tuple[bool, bool]:
    """`(left, right)` -- which end caps this column owns. Pure and testable."""
    if header is None:
        return (False, False)
    return (first_visible_column(header) == column,
            last_visible_column(header) == column)


def header_of(option):
    """The horizontal header behind this cell, or None for a non-table view."""
    widget = option.widget
    return widget.horizontalHeader() if hasattr(widget, "horizontalHeader") else None


def paint_selection_ring(painter, option, index) -> None:
    """Paint this cell's slice of the selected row's ring. A no-op otherwise.

    Call it after the base item is drawn, so the caps land on top of the QSS
    background rather than under it.
    """
    if not (option.state & QStyle.State_Selected):
        return
    left, right = caps(header_of(option), index.column())
    if not (left or right):
        return

    color = QColor(get_theme_manager().get_current_theme().selection_border)
    rect = option.rect
    painter.save()
    if left:
        painter.fillRect(rect.x(), rect.y(), RING_WIDTH, rect.height(), color)
    if right:
        painter.fillRect(
            rect.right() - RING_WIDTH + 1, rect.y(), RING_WIDTH, rect.height(), color
        )
    painter.restore()


class SelectionRingDelegate(QStyledItemDelegate):
    """The default delegate for a table whose other columns have none.

    setItemDelegateForColumn still wins where a column has its own delegate;
    this one closes the ring on all the columns that do not.
    """

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        paint_selection_ring(painter, option, index)
