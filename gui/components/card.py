"""Elevated container for the Statistics tab's stat / courier / tag tiles.

ui_manager.py hand-rolled this same QFrame + centred-label stack three times
(_make_stat_card, _make_courier_card, _make_tag_card). The differences between
them were per-instance data -- margins, minimum width, which TYPE_SCALE role
each row uses -- not three different widgets.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from gui.theme_manager import font_css


class Card(QFrame):
    """A raised panel holding a vertical stack of centred labels.

    Raised by plane, not by an outline -- Qt has no box-shadow, so elevation
    is a surface colour (F1). Styled by the `Card` rule in build_stylesheet.
    """

    def __init__(
        self,
        *,
        min_width: int = 0,
        margins: tuple[int, int, int, int] = (12, 8, 12, 8),
        spacing: int = 2,
        parent=None,
    ) -> None:
        super().__init__(parent)
        # StyledPanel + Raised draws an OS frame *underneath* the stylesheet,
        # so the card ends up outlined no matter what QSS says. F1: regions
        # separate by plane, and a border is reserved for inputs and focus.
        self.setFrameShape(QFrame.NoFrame)
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
