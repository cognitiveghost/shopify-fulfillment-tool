"""Paints a row's status as a left edge, never as a filled row.

Parcker's rule: status is an edge, a chip or a tint, never a filled row -- a
filled row cannot show *selected* and *blocked* at the same time, and the
selection ring shipped in 8.7 needs the row background to stay neutral.

The base item is drawn first, through the widget's own style, so the
stylesheet's selection ring (shared/theme.py -- selection_bg plus a 2px
selection_border top and bottom) still renders underneath the edge.

Spec: docs/superpowers/specs/2026-08-30-phase8.8b-analysis-results-chrome-design.md
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate

from gui.pandas_model import ROLE_STATUS
from gui.theme_manager import get_theme_manager

EDGE_WIDTH = 3


class StatusEdgeDelegate(QStyledItemDelegate):
    """A 3px bar in the row's status colour, on the leftmost visible column."""

    def edge_token(self, index) -> str | None:
        """The row's theme role token, or None. Pure: no painting, no theme."""
        return index.data(ROLE_STATUS)

    def paints_edge(self, header, column: int) -> bool:
        """True for the column the user currently sees on the left.

        Visual index, not logical: a user who drags a column to the front must
        still get the edge on the left of the row.
        """
        return header is not None and header.visualIndex(column) == 0

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        # Column check first: it is a C++ visualIndex lookup, where edge_token
        # is a data() round-trip through the proxy. Only one column of N draws
        # an edge, so the cheap test skips the model call for the other N-1.
        widget = option.widget
        header = widget.horizontalHeader() if hasattr(widget, "horizontalHeader") else None
        if not self.paints_edge(header, index.column()):
            return
        token = self.edge_token(index)
        if not token:
            return

        theme = get_theme_manager().get_current_theme()
        rect = option.rect
        painter.save()
        # Not `rect.setWidth()`: PySide6 hands back a reference to the option's
        # own field, so narrowing it would mutate the caller's const option.
        painter.fillRect(rect.x(), rect.y(), EDGE_WIDTH, rect.height(), QColor(getattr(theme, token)))
        painter.restore()
