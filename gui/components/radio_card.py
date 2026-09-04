"""A radio button that states the consequence of choosing it.

Replaces the Analysis mode combo on Session Setup. The choice is made once
a day by a warehouse supervisor who should not have to ask a colleague what
"multi-item-first" means, so the option carries its own explanation rather
than hiding it in a tooltip nobody hovers.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QRadioButton, QVBoxLayout

from gui.theme_manager import font_css, get_theme_manager


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
        super().__init__(title, parent)
        theme = get_theme_manager().get_current_theme()

        self.title_text = title
        self.description_text = description

        self.setStyleSheet(font_css("label"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._INDENT, theme.spacing_lg, theme.spacing_sm, theme.spacing_sm
        )
        layout.setSpacing(0)

        self._description = QLabel(description, self)
        self._description.setWordWrap(True)
        self._description.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        # Clicks on the description must still choose the option -- a
        # transparent label forwards them to the radio button underneath.
        self._description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._description)

    def sizeHint(self) -> QSize:
        # QRadioButton's own sizeHint ignores the description below its
        # text -- the layout's hint is what actually fits both lines.
        return self.layout().sizeHint().expandedTo(super().sizeHint())
