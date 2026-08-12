"""Elevated container for the Statistics tab's stat / courier / tag tiles.

ui_manager.py hand-rolled this same QFrame + centred-label stack three times
(_make_stat_card, _make_courier_card, _make_tag_card). The differences between
them were per-instance data -- margins, minimum width, which TYPE_SCALE role
each row uses -- not three different widgets.

gui/client_card.py is deliberately NOT built on this: it is an interactive list
item with hover/active states, a fixed height and its own border-radius QSS.
See the design doc for that call.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from gui.theme_manager import font_css


class Card(QFrame):
    """A framed panel holding a vertical stack of centred labels."""

    def __init__(
        self,
        *,
        min_width: int = 0,
        margins: tuple[int, int, int, int] = (12, 8, 12, 8),
        spacing: int = 2,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        if min_width:
            self.setMinimumWidth(min_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

    def add_text(
        self, text: str, role: str = "body", *, wrap: bool = False, css: str = ""
    ) -> QLabel:
        """Append a centred label at a TYPE_SCALE role and return it.

        The label is returned because callers keep handles to the rows they
        update live (the Statistics tab's stat_card_labels).

        `css` appends caller-specific declarations after the role's font
        rules -- it exists for the tag tile's coloured count badge. An unknown
        `role` raises KeyError out of font_css(), matching the rule Tracks 1
        and 2 set: a typo fails in development, not invisibly in production.
        """
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(wrap)
        label.setStyleSheet(f"{font_css(role)} {css}".strip())
        self.layout().addWidget(label)
        return label
