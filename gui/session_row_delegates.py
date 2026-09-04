"""Item delegates that paint the Session Browser's status and packing cells.

A delegate, not a cell widget. Putting a StatusChip (a QLabel) in the cell
would reinstate exactly what 1e removes: a child widget covering the cell, so
clicks never reach the row and hover events move the selection.

Spec: docs/superpowers/specs/2026-08-28-phase8.7-1e-session-browser-design.md
"""

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.selection_ring import paint_selection_ring
from gui.theme_manager import get_theme_manager
from shared.theme import MARK_LEFT_PX, MARK_PX, paint_status_mark, status_style

# Item-data roles. Qt.UserRole itself is already taken on this table: column 0
# carries the session path, column 6 the packing ratio.
ROLE_TOKEN = Qt.UserRole + 1     # str -- theme token name for the status
ROLE_MANUAL = Qt.UserRole + 2    # bool -- status_manually_set
ROLE_LIVE = Qt.UserRole + 3      # bool -- someone still has to act

# 9.3 §3.5: live-ness is data about a state, so it rides with the role rather
# than in a second table keyed by the same thing. 9.19 extends this to seven
# statuses plus archived; it owns that expansion because it is gated on the
# `blocked_orders` data change.
STATUS_ROLES: dict[str, tuple[str, bool]] = {
    "active": ("status_info", True),
    "completed": ("status_success", False),
    "abandoned": ("status_danger", False),
    "archived": ("text_secondary", False),
}


class SessionStatusDelegate(QStyledItemDelegate):
    """Paints the Status cell as one silhouette: an outlined pill, a mark, a label.

    Colour is the role, fill is live-vs-resting, and the mark is authorship --
    solid for a person, hollow for the system. Before 9.3 authorship chose
    between a bare dot and a tinted pill, which read as two components and made
    the authorship difference disappear into "the design is inconsistent".

    A delegate, not a cell widget: a QLabel in a cell covers it, so clicks
    never reach the row and hover moves the selection.
    """

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""                      # the row background, not the label
        style_ = opt.widget.style() if opt.widget else QApplication.style()
        style_.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        paint_selection_ring(painter, option, index)

        role = index.data(ROLE_TOKEN)
        if not role:
            return
        status = status_style(
            role,
            get_theme_manager().get_current_theme(),
            live=bool(index.data(ROLE_LIVE)),
            manual=bool(index.data(ROLE_MANUAL)),
        )

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(8, 0, -8, 0)
        metrics = painter.fontMetrics()
        label_left = MARK_LEFT_PX + MARK_PX + 4
        height = metrics.height() + 4
        pill = QRect(
            rect.left(),
            rect.center().y() - height // 2,
            min(label_left + metrics.horizontalAdvance(text) + 8, rect.width()),
            height,
        )
        painter.setBrush(QColor(status.fill) if status.fill else Qt.NoBrush)
        painter.setPen(QColor(status.fg))       # the outline, then the mark and label
        painter.drawRoundedRect(pill, height / 2, height / 2)
        paint_status_mark(
            painter,
            QRectF(
                pill.left() + MARK_LEFT_PX,
                pill.center().y() - MARK_PX / 2,
                MARK_PX,
                MARK_PX,
            ),
            status,
        )
        painter.drawText(
            pill.adjusted(label_left, 0, -8, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            text,
        )
        painter.restore()


class PackingProgressDelegate(QStyledItemDelegate):
    """Draws `packed/total` as a bar beside its own text.

    The bar takes the left two thirds and the text sits to its right --
    deliberately not text-over-bar, which would put theme.text on a
    status_success fill, a pairing no contrast test covers.
    """

    def bar_fraction(self, ratio) -> float:
        """0.0 when there is nothing to show. -1.0 means "no packing lists"."""
        if not isinstance(ratio, (int, float)) or ratio < 0:
            return 0.0
        return min(1.0, float(ratio))

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        paint_selection_ring(painter, option, index)

        theme = get_theme_manager().get_current_theme()
        fraction = self.bar_fraction(index.data(Qt.UserRole))

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        cell = option.rect.adjusted(8, 0, -8, 0)
        bar_width = int(cell.width() * 0.6)

        if fraction > 0 or index.data(Qt.UserRole) == 0.0:
            track = QRect(cell.left(), cell.center().y() - 3, bar_width, 6)
            painter.setPen(Qt.NoPen)
            # Not surface_sunken: it measures 1.05:1 against surface in dark,
            # so an empty bar showed no denominator at all. border is 3.69:1.
            painter.setBrush(QColor(theme.border))
            painter.drawRoundedRect(track, 3, 3)
            filled = QRect(track)
            filled.setWidth(int(track.width() * fraction))
            if filled.width() > 0:
                painter.setBrush(QColor(theme.status_success))
                painter.drawRoundedRect(filled, 3, 3)

        painter.setPen(QColor(theme.text))
        painter.drawText(
            cell.adjusted(bar_width + 8, 0, 0, 0),
            Qt.AlignVCenter | Qt.AlignRight,
            text,
        )
        painter.restore()
