"""The 56px vertical navigation rail that replaces the tab bar.

Owns selection state and emits an index -- it knows nothing about tabs,
stacks or pages. 8.6 connects currentChanged to whatever it replaces, and
ships the rail with the existing labels verbatim: structure and labels never
change in the same release.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.icons import icon
from gui.theme_manager import font_css, get_theme_manager

RAIL_WIDTH = 56


class NavRail(QWidget):
    """A vertical stack of icon-over-label buttons, one of them checked."""

    currentChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(RAIL_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        theme = get_theme_manager().get_current_theme()
        # No border: the rail is separated by its own darker plane, not a line.
        self.setStyleSheet(f"background-color: {theme.surface_sunken}; border: none;")

        self._buttons: list[QToolButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        # Not read from self._group.checkedId(): by the time a clicked() slot
        # runs, Qt has already flipped the exclusive group's checked button,
        # so that state can no longer tell a genuine change from a re-click.
        self._current = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        layout.addStretch()
        self._layout = layout

    def add_item(self, icon_name: str, label: str) -> int:
        """Append an item and return its index. Unknown glyph raises KeyError."""
        button = QToolButton(self)
        button.setIcon(icon(icon_name))          # raises KeyError on a typo
        button.setText(label)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFixedWidth(RAIL_WIDTH)
        button.setStyleSheet(font_css("caption"))

        index = len(self._buttons)
        self._buttons.append(button)
        self._group.addButton(button, index)
        self._layout.insertWidget(index, button)
        button.clicked.connect(lambda _checked, i=index: self.set_current(i))

        if index == 0:
            button.setChecked(True)
            self._current = 0
        return index

    def button(self, index: int) -> QToolButton:
        return self._buttons[index]

    def current_index(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if not 0 <= index < len(self._buttons):
            raise IndexError(f"NavRail has no item at index {index}")
        self._buttons[index].setChecked(True)
        if index == self._current:
            return
        self._current = index
        self.currentChanged.emit(index)
