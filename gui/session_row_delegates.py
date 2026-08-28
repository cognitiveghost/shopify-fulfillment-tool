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


def label_color(option, theme) -> str:
    """Text colour for a delegate that draws its own label.

    A selected row is painted accent_fill by shared/theme.py, and accent_fill is
    the same blue in both themes while theme.text is not -- so theme.text lands
    at 3.3:1 on a selected row in light. on_accent is the partner token.
    """
    selected = bool(option.state & QStyle.State_Selected)
    return theme.on_accent if selected else theme.text


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
            top = rect.center().y() - diameter // 2
            if opt.state & QStyle.State_Selected:
                # The dot's own colour measures ~1.05:1 against accent_fill, so
                # it needs a disc behind it to read at all. surface, not
                # on_accent: the status tokens are already validated against
                # surface (5.4:1+ both themes) whereas status_success on white
                # is only 2.8:1. The chip form needs no equivalent -- its tint
                # clears 4.3:1 on accent_fill unaided.
                painter.setBrush(QColor(theme.surface))
                painter.drawEllipse(
                    rect.left() - 2, top - 2, diameter + 4, diameter + 4
                )
            painter.setBrush(QColor(fg))
            painter.drawEllipse(rect.left(), top, diameter, diameter)
            painter.setPen(QColor(label_color(opt, theme)))
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

        painter.setPen(QColor(label_color(opt, theme)))
        painter.drawText(
            cell.adjusted(bar_width + 8, 0, 0, 0),
            Qt.AlignVCenter | Qt.AlignRight,
            text,
        )
        painter.restore()
