"""Item delegates that paint the Session Browser's status and packing cells.

A delegate, not a cell widget. Putting a StatusChip (a QLabel) in the cell
would reinstate exactly what 1e removes: a child widget covering the cell, so
clicks never reach the row and hover events move the selection.

Spec: docs/superpowers/specs/2026-08-28-phase8.7-1e-session-browser-design.md
"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.theme_manager import get_theme_manager

# Item-data roles. Qt.UserRole itself is already taken on this table: column 0
# carries the session path, column 6 the packing ratio.
ROLE_TOKEN = Qt.UserRole + 1     # str -- theme token name for the status
ROLE_MANUAL = Qt.UserRole + 2    # bool -- status_manually_set

# Spec section 3. `archived` amends the parent spec's section 4 table, which
# had no key for it.
STATUS_ROLES: dict[str, str] = {
    "active": "status_info",
    "completed": "status_success",
    "abandoned": "status_danger",
    "archived": "text_secondary",
}


def chip_colors(role: str, theme) -> tuple[str, str]:
    """`(foreground, tint)` for a status role.

    The same two lines shared/theme.py's StatusChip.set_status uses. Copied
    rather than shared: hoisting a helper into shared/theme.py means authoring
    it in packing-tool and running scripts/sync_shared.py, which drags a second
    repo into a single-screen cycle for two lines. 8.9 gives packing-tool its
    own painted status column -- that is the second call site and the moment to
    hoist. Until then a test asserts this stays equal to StatusChip's result.
    """
    return getattr(theme, role), getattr(theme, f"{role}_bg", theme.surface_sunken)


class SessionStatusDelegate(QStyledItemDelegate):
    """Paints the Status cell as a dot plus label, or as a tinted pill.

    Which form appears is authorship, not state: "colour carries urgency, tint
    carries authorship". A person who set the status by hand gets a plain dot;
    a status session_lifecycle derived gets a tinted chip.
    """

    def form(self, role: str, manual: bool) -> tuple[str, str, str]:
        """`(kind, fg, tint)` -- pure, so the rule is testable without painting."""
        fg, tint = chip_colors(role, get_theme_manager().get_current_theme())
        return ("dot" if manual else "chip"), fg, tint

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""                      # the row background, not the label
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        role = index.data(ROLE_TOKEN)
        if not role:
            return
        kind, fg, tint = self.form(role, bool(index.data(ROLE_MANUAL)))
        theme = get_theme_manager().get_current_theme()

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        rect = option.rect.adjusted(8, 0, -8, 0)
        metrics = painter.fontMetrics()

        if kind == "dot":
            diameter = 8
            painter.setBrush(QColor(fg))
            painter.drawEllipse(
                rect.left(), rect.center().y() - diameter // 2, diameter, diameter
            )
            painter.setPen(QColor(theme.text))
            painter.drawText(
                rect.adjusted(diameter + 6, 0, 0, 0),
                Qt.AlignVCenter | Qt.AlignLeft,
                text,
            )
        else:
            height = metrics.height() + 4
            pill = QRect(
                rect.left(),
                rect.center().y() - height // 2,
                min(metrics.horizontalAdvance(text) + 16, rect.width()),
                height,
            )
            painter.setBrush(QColor(tint))
            painter.drawRoundedRect(pill, height / 2, height / 2)
            painter.setPen(QColor(fg))
            painter.drawText(pill, Qt.AlignCenter, text)

        painter.restore()
