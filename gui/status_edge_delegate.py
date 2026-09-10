"""Paints a row's status as a left edge, never as a filled row.

Parcker's rule: status is an edge, a chip or a tint, never a filled row -- a
filled row cannot show *selected* and *blocked* at the same time, and the
selection ring shipped in 8.7 needs the row background to stay neutral.

The base item is drawn first, through the widget's own style, so the
stylesheet's selection ring (shared/theme.py -- selection_bg plus a 2px
selection_border top and bottom) still renders underneath the edge.

Spec: docs/superpowers/specs/2026-08-30-phase8.8b-analysis-results-chrome-design.md
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.pandas_model import ROLE_STATUS
from gui.selection_ring import (
    RING_WIDTH,
    first_visible_column,
    header_of,
    paint_selection_ring,
)
from gui.theme_manager import get_theme_manager

EDGE_WIDTH = 3


class StatusEdgeDelegate(QStyledItemDelegate):
    """A 3px bar in the row's status colour, on the leftmost visible column."""

    def edge_token(self, index) -> str | None:
        """The row's theme role token, or None. Pure: no painting, no theme."""
        return index.data(ROLE_STATUS)

    def paints_edge(self, header, column: int) -> bool:
        """True for the column the user currently sees on the left.

        Visual index, not logical, and skipping hidden columns: a user who
        drags a column to the front -- or hides the first one through the
        column manager -- must still get the edge on the left of the row.
        Shared with the selection ring so the two cannot disagree about where
        the row starts.
        """
        return header is not None and first_visible_column(header) == column

    def edge_rect(self, option):
        """Where the 3px bar goes. Pure, so the inset rule is testable.

        On a selected row the edge insets by the ring's width on the left, top
        and bottom, so it sits *inside* the selection rather than colliding
        with it -- a red edge on the ring's own left side reads as part of the
        selection, which is the fault 9.4 exists to remove.
        """
        if option.state & QStyle.State_Selected:
            return option.rect.adjusted(RING_WIDTH, RING_WIDTH, 0, -RING_WIDTH)
        return option.rect

    def _paint_with_foreground(self, painter, option, index, colour):
        """Draw the cell, then its text in the model's colour, not the QSS's.

        QStyleSheetStyle takes the text colour from the stylesheet and
        ignores the palette initStyleOption just filled in, so the only way
        to honour ForegroundRole under an application stylesheet is to let
        the style draw everything *except* the text and draw that here.
        """
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""

        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        painter.save()
        painter.setPen(colour)
        painter.setFont(opt.font)
        elided = QFontMetrics(opt.font).elidedText(text, Qt.ElideRight, rect.width())
        painter.drawText(rect, int(opt.displayAlignment), elided)
        painter.restore()

    def paint(self, painter, option, index):
        # An application stylesheet targets QTableView/QTreeView::item
        # (shared/theme.py), which hands item painting to QStyleSheetStyle.
        # That style draws its own panel and takes its colour from the QSS,
        # so a model's BackgroundRole never reaches the screen -- it arrives
        # on the option intact and is then discarded. Painting it here is
        # what makes the role mean anything. Selected rows keep the
        # stylesheet's selection colour; a tint under the ring reads as a
        # second selection.
        if not (option.state & QStyle.State_Selected):
            background = index.data(Qt.BackgroundRole)
            if background is not None:
                painter.fillRect(option.rect, QColor(background))

        foreground = index.data(Qt.ForegroundRole)
        if foreground is None:
            # The overwhelmingly common case, and the one every other view
            # takes: let the style draw the cell whole.
            super().paint(painter, option, index)
        else:
            self._paint_with_foreground(painter, option, index, QColor(foreground))

        paint_selection_ring(painter, option, index)

        # Column check first: it is a C++ visualIndex lookup, where edge_token
        # is a data() round-trip through the proxy. Only one column of N draws
        # an edge, so the cheap test skips the model call for the other N-1.
        # header_of, not a horizontalHeader() sniff: a QTreeView calls it
        # header(), so sniffing only for the table's name returned None and
        # killed the edge on every tree -- the same silent failure the
        # selection ring's own docstring records from Bundle 6.
        header = header_of(option)
        if not self.paints_edge(header, index.column()):
            return
        token = self.edge_token(index)
        if not token:
            return

        theme = get_theme_manager().get_current_theme()
        rect = self.edge_rect(option)
        painter.save()
        # Not `rect.setWidth()`: PySide6 hands back a reference to the option's
        # own field, so narrowing it would mutate the caller's const option.
        painter.fillRect(
            rect.x(), rect.y(), EDGE_WIDTH, rect.height(), QColor(getattr(theme, token))
        )
        painter.restore()
