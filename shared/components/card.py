"""Elevated container holding a vertical stack of centred labels.

ui_manager.py hand-rolled this same QFrame + centred-label stack three times,
in card builders since deleted. The differences between them were
per-instance data -- margins, minimum width, which TYPE_SCALE role each row
uses -- not three different widgets.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from shared.theme import font_css, on_theme_changed


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
        update live rather than rebuilding the card.

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

    def add_widget(self, widget: QWidget) -> None:
        """Append a widget as-is, without the centring add_text applies.

        The setup card holds a form, not a stack of centred numbers.
        """
        self.layout().addWidget(widget)

    def add_row(self, label: str, value: str, *, mono: bool = False) -> QLabel:
        """Append a label/value definition-list row and return the value label.

        The shape (a caption-weight label on the left, a bold value on the
        right) had two hand-rolled copies -- OverviewTab and MetricsTab --
        before this became the one place it is built.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        label_widget = QLabel(label)
        on_theme_changed(
            label_widget,
            lambda tokens, w=label_widget: w.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        row.addWidget(label_widget)
        row.addStretch()

        value_widget = QLabel(value)
        # Re-run rather than baked: on_theme_changed also carries density
        # changes, which move font_css -- baking it leaves the value at the
        # old size while the label beside it follows.
        on_theme_changed(
            value_widget,
            lambda tokens, w=value_widget: w.setStyleSheet(
                f"{font_css('caption', bold=not mono)}"
                + (f" font-family: {tokens.font_family_mono};" if mono else "")
            ),
        )
        row.addWidget(value_widget)

        self.layout().addLayout(row)
        return value_widget
