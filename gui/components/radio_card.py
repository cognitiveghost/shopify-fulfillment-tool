"""A radio button that states the consequence of choosing it.

Replaces the Analysis mode combo on Session Setup. The choice is made once
a day by a warehouse supervisor who should not have to ask a colleague what
"multi-item-first" means, so the option carries its own explanation rather
than hiding it in a tooltip nobody hovers.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QRadioButton, QVBoxLayout

from gui.theme_manager import font_css, get_theme_manager
from shared.theme import on_theme_changed


class RadioCard(QRadioButton):
    """A radio button with a title and a wrapped description beneath it.

    The description is a child QLabel laid out below the button's own text,
    indented past the indicator so it reads as belonging to the option. The
    button's own text stays empty: giving QRadioButton two lines of text is
    what a QLabel is for, and an empty text keeps the indicator's vertical
    alignment on the first line where the title is.
    """

    _INDENT = 22  # indicator width + its spacing, so the description lines up

    def __init__(self, title: str, description: str, parent=None) -> None:
        # Native text stays empty: the indicator needs somewhere to align
        # to, but the title itself is a QLabel below so its height is known
        # to the layout instead of guessed at from the button's own paint
        # metrics, which is what caused it to overlap the description.
        super().__init__("", parent)
        theme = get_theme_manager().get_current_theme()

        self.title_text = title
        self.description_text = description
        # Empty native text leaves the radio with no accessible name, so a
        # screen reader announces the group and not which option this is.
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._INDENT, theme.spacing_sm, theme.spacing_sm, theme.spacing_sm
        )
        layout.setSpacing(theme.spacing_xs)

        self._title = QLabel(title, self)
        # Clicks on the title/description must still choose the option -- a
        # transparent label forwards them to the radio button underneath.
        self._title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._title)

        self._description = QLabel(description, self)
        self._description.setWordWrap(True)
        self._description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._description)

        self._apply_theme()
        on_theme_changed(self, lambda _t=None: self._apply_theme())

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self._title.setStyleSheet(font_css("label"))
        self._description.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        # The native indicator centres on the whole widget by default, which
        # is fine for a one-line button but drifts down to the description
        # once a second line joins it. Pin it to the title's row instead.
        self.setStyleSheet(
            "QRadioButton::indicator { subcontrol-position: left top; "
            f"margin-top: {theme.spacing_xs}px; }}"
        )

    def sizeHint(self) -> QSize:
        # QRadioButton's own sizeHint ignores the description below its
        # text -- the layout's hint is what actually fits both lines.
        return self.layout().sizeHint().expandedTo(super().sizeHint())

    def hasHeightForWidth(self) -> bool:
        # Without this, a parent layout uses sizeHint()'s height at every
        # width -- which is the *unwrapped* description's height, far too
        # short once a narrow column (the card's 208px-gutter form) forces
        # the real text onto three lines instead of sizeHint()'s one.
        return True

    def heightForWidth(self, width: int) -> int:
        return self.layout().totalHeightForWidth(width)
