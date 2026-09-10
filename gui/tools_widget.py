"""The Tools destination: Reference labels and Barcode labels as two cards.

Side by side from 1180px of page width -- at 1366 the page is 1310, and two
637px cards with 12px gaps and margins are exactly that -- and stacked below
it, by flipping the one row's direction. Never a QStackedLayout: that would
build each tool twice.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QScrollArea, QVBoxLayout, QWidget

from gui.barcode_generator_widget import BarcodeGeneratorWidget
from gui.components import Card
from gui.reference_labels_widget import ReferenceLabelsWidget

_STACK_BELOW = 1180


class ToolsWidget(QWidget):
    """The Tools page: two tool cards in one row that stacks when narrow."""

    def __init__(self, main_window, parent=None):
        """
        Initialize Tools widget.

        Args:
            main_window: MainWindow instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self._init_ui()

    def _init_ui(self):
        """Two cards in one row, inside a vertical-only scroll area."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        content = QWidget()
        page = QVBoxLayout(content)
        page.setContentsMargins(12, 12, 12, 12)
        page.setSpacing(0)

        self.cards_row = QBoxLayout(QBoxLayout.LeftToRight)
        self.cards_row.setSpacing(12)

        self.reference_labels_widget = ReferenceLabelsWidget(self.mw)
        self.barcode_generator_widget = BarcodeGeneratorWidget(self.mw)
        for widget in (self.reference_labels_widget, self.barcode_generator_widget):
            card = Card(margins=(16, 16, 16, 16), spacing=12)
            card.add_widget(widget)
            self.cards_row.addWidget(card, 1)

        page.addLayout(self.cards_row)
        # Extra page height goes here, not into the cards: side by side they
        # already share the taller one's height, and stacked each keeps its own.
        page.addStretch(1)

        self.scroll.setWidget(content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_width(self.width())

    def _apply_width(self, width: int) -> None:
        direction = (
            QBoxLayout.TopToBottom if width < _STACK_BELOW else QBoxLayout.LeftToRight
        )
        if self.cards_row.direction() != direction:
            self.cards_row.setDirection(direction)
