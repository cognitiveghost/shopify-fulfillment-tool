"""The KPI tile: one big numeral over one small sublabel.

Card already is this frame -- a QFrame holding centred labels at TYPE_SCALE
roles -- so StatCard subclasses it rather than hand-rolling a fourth copy of
the same stack. Only the roles are new: display_xl on the numeral, caption
below it.
"""

from PySide6.QtWidgets import QHBoxLayout, QWidget

from gui.components.card import Card


class StatCard(Card):
    """A single KPI tile. `set_value` exists because Metrics updates live."""

    def __init__(self, value: str, label: str, *, min_width: int = 0, parent=None) -> None:
        super().__init__(min_width=min_width, parent=parent)
        self.value_label = self.add_text(value, "display_xl")
        # No setter for the sublabel: what a tile counts does not change while
        # it is on screen. Add one when a screen proves otherwise.
        self.sub_label = self.add_text(label, "caption", wrap=True)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class KpiStrip(QWidget):
    """A horizontal row of StatCards. A container, not a layout algorithm."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._cards: list[StatCard] = []

    def add(self, value: str, label: str, *, min_width: int = 0) -> StatCard:
        card = StatCard(value, label, min_width=min_width, parent=self)
        self._cards.append(card)
        self.layout().addWidget(card)
        return card

    def cards(self) -> list[StatCard]:
        return list(self._cards)
