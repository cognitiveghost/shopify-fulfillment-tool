"""EN | BG: the PC's language, applied on restart (ADR 0021).

Styled by the sidebar that hosts it, like its theme segment: the sidebar's
sheet names #LanguageSegment next to #ThemeSegment.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from shared import update_flow
from shared.i18n import LANGUAGES, _
from shared.relaunch import cancel, on_quit, relaunch_argv


class LanguageSegment(QFrame):
    # ponytail: a segment of codes; a dropdown when there are more than three languages.
    languageRequested = Signal(str)

    def __init__(self, parent=None, *, height: int = 24):
        super().__init__(parent)
        self.setObjectName("LanguageSegment")
        self.setFixedHeight(height)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        self._current = ""
        for code, name in LANGUAGES.items():
            button = QToolButton(self)
            button.setText(code.upper())
            button.setToolTip(name)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            group.addButton(button)
            row.addWidget(button)
            button.clicked.connect(lambda _c=False, c=code: self._clicked(c))
            self.buttons[code] = button

    def set_language(self, code: str) -> None:
        self._current = code
        if code in self.buttons:
            self.buttons[code].setChecked(True)

    def _clicked(self, code: str) -> None:
        if code != self._current:
            self.languageRequested.emit(code)


def switch_language(window: QWidget, settings: QSettings, code: str) -> bool:
    settings.setValue("language", code)
    if not update_flow.ask(window, title=_("Restart to switch language?"),
                           body=_("The new language applies after a restart."),
                           verb=_("Restart now")):
        return False
    on_quit(relaunch_argv())
    if not window.close():  # vetoed: a later, ordinary close must not restart
        cancel()
    return True
