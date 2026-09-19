"""A single statistic: a big value over a small label, in a bordered box."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shared.components.card import Card


class StatCard(QWidget):
    """One number and what it counts.

    Attributes:
        value_label: the big number.
        caption_label: what it counts.
    """

    def __init__(
        self, value: str, label: str, *, small: bool = False, parent=None
    ) -> None:
        super().__init__(parent)
        self._card = Card(margins=(12, 8, 12, 8), spacing=2)
        self.value_label = self._card.add_text(value, "label" if small else "display")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.caption_label = self._card.add_text(label, "caption")
        self.caption_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
