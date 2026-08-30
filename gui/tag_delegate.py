"""Custom ItemDelegate for rendering Internal_Tags as colored badges."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPen
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from gui.theme_manager import apply_font
from shopify_tool.tag_manager import get_tag_color, parse_tags


class TagDelegate(QStyledItemDelegate):
    """Delegate for rendering Internal_Tags column as colored badges."""

    def __init__(self, tag_categories, parent=None):
        super().__init__(parent)
        self.tag_categories = tag_categories

    def paint(self, painter, option, index):
        """Paint tags as colored badges while respecting row background and selection."""
        # Let the style paint the background -- it resolves the selected row
        # (selection_bg plus its share of the selection_border ring). The model
        # no longer answers BackgroundRole at all since 8.8b; letting the style
        # own the background is what keeps this cell's segment of the ring. Not palette.highlight(): that is still
        # accent_fill, which would punch an accent block through the row and
        # drop this cell's segment of the ring.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # Get tags to render
        tags_value = index.data(Qt.DisplayRole)
        tags = parse_tags(tags_value)

        if not tags:
            # No tags - just show background color
            return

        painter.save()

        # Calculate badge positions
        rect = option.rect
        x = rect.left() + 5
        y = rect.center().y()

        badge_height = 20
        padding = 8
        spacing = 4

        apply_font(painter, "caption")
        metrics = painter.fontMetrics()

        for tag in tags:
            # Get tag color
            color_hex = get_tag_color(tag, self.tag_categories)
            color = QColor(color_hex)

            # Measure text width
            text_width = metrics.horizontalAdvance(tag)

            badge_width = text_width + padding * 2

            # Check if badge fits in remaining space
            if x + badge_width > rect.right() - 5:
                # Draw "..." and stop
                painter.drawText(x, y + 5, "...")
                break

            # Draw rounded rectangle background
            badge_rect = QRect(x, y - badge_height // 2, badge_width, badge_height)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, 3, 3)

            # Draw text
            painter.setPen(QPen(Qt.white))
            text_rect = QRect(x + padding, y - badge_height // 2, text_width, badge_height)
            painter.drawText(text_rect, Qt.AlignCenter, tag)

            x += badge_width + spacing

        painter.restore()

    def sizeHint(self, option, index):
        """Return size hint for cell based on actual badge widths."""
        tags_value = index.data(Qt.DisplayRole)
        tags = parse_tags(tags_value)
        if not tags:
            return QSize(50, 30)
        font = option.font
        metrics = QFontMetrics(font)
        padding = 8
        spacing = 4
        total_width = 10  # left margin
        for tag in tags:
            total_width += metrics.horizontalAdvance(tag) + padding * 2 + spacing
        return QSize(total_width, 30)
