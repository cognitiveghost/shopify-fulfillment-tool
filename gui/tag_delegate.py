"""Custom ItemDelegate for rendering Internal_Tags as colored badges."""

import json
from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QFontMetrics

from shopify_tool.tag_manager import parse_tags, get_tag_color


class TagDelegate(QStyledItemDelegate):
    """Delegate for rendering Internal_Tags column as colored badges."""

    def __init__(self, tag_categories, parent=None):
        super().__init__(parent)
        self.tag_categories = tag_categories

    def paint(self, painter, option, index):
        """Paint tags as colored badges while respecting row background and selection."""
        # Handle selection highlight; fall back to model background color
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            bg_color = index.data(Qt.BackgroundRole)
            if bg_color:
                painter.fillRect(option.rect, bg_color)

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

        for tag in tags:
            # Get tag color
            color_hex = get_tag_color(tag, self.tag_categories)
            color = QColor(color_hex)

            # Measure text width
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            metrics = painter.fontMetrics()
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
