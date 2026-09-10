"""The Tools destination: Reference labels and Barcode labels as two cards.

Side by side from 1180px of page width -- at 1366 the page is 1310, and two
637px cards with 12px gaps and margins are exactly that -- and stacked below
it, by flipping the one row's direction. Never a QStackedLayout: that would
build each tool twice.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md.
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QScrollArea, QVBoxLayout, QWidget

from gui.barcode_generator_widget import BarcodeGeneratorWidget
from gui.components import Card
from gui.reference_labels_widget import ReferenceLabelsWidget
from shared.theme import set_button_role

_STACK_BELOW = 1180


def primary_holder(
    reference_ready: bool, barcode_ready: bool, current: str | None
) -> str | None:
    """Which card's action is the page's one primary, if any.

    Exactly one ready card holds it. With both ready, the current holder keeps
    it, so a button never changes weight under the cursor because the *other*
    card became ready. With neither ready there is none: a disabled primary is
    a primary nobody can press.
    """
    if reference_ready and barcode_ready:
        return current or "reference"
    if reference_ready:
        return "reference"
    if barcode_ready:
        return "barcode"
    return None


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

        # Readiness is each card's own verdict -- its action button's enabled
        # state, set by logic this page does not touch. Watching EnabledChange
        # covers every path that sets it, including disable-while-running.
        self._primary = None
        self._action_buttons = {
            "reference": self.reference_labels_widget.process_btn,
            "barcode": self.barcode_generator_widget.generate_btn,
        }
        for button in self._action_buttons.values():
            button.installEventFilter(self)
        self._sync_primary()

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

    def eventFilter(self, obj, event):
        if event.type() == QEvent.EnabledChange:
            self._sync_primary()
        return super().eventFilter(obj, event)

    def _sync_primary(self) -> None:
        holder = primary_holder(
            self._action_buttons["reference"].isEnabled(),
            self._action_buttons["barcode"].isEnabled(),
            self._primary,
        )
        if holder == self._primary:
            return
        for name, button in self._action_buttons.items():
            set_button_role(button, "primary" if name == holder else "secondary")
        self._primary = holder
