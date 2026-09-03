"""The vertical navigation rail that replaces a tab bar.

Owns selection state and emits an index -- it knows nothing about tabs,
stacks or pages. The app connects currentChanged to whatever it replaces,
and ships the rail with the existing labels verbatim: structure and labels
never change in the same release.

Canonical source -- see
docs/superpowers/specs/2026-07-26-unified-ui-design-system-design.md.
Never hand-edit shopify-fulfillment-tool/shared/navrail.py; run
shopify-fulfillment-tool/scripts/sync_shared.py after changing this file.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from shared.theme import current_tokens, font_css, theme_notifier

# Depot's desk-density rail. An app whose labels do not fit passes its own
# width: packing-tool passes 76, because "Statistics" measures 59px against
# this width's 45.6px budget. Spec 2026-08-29 §4.
RAIL_WIDTH = 56


class NavRail(QWidget):
    """A vertical stack of icon-over-label buttons, one of them checked."""

    currentChanged = Signal(int)

    def __init__(self, parent=None, width: int = RAIL_WIDTH) -> None:
        super().__init__(parent)
        self._width = width
        self.setFixedWidth(width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._apply_theme()
        # A widget sheet outranks the app's, so baking the colours in once
        # would leave a light rail over dark pages after a theme toggle.
        theme_notifier.changed.connect(self._apply_theme)

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

    def _apply_theme(self, _name: str | None = None) -> None:
        # Takes the signal's argument and ignores it, so the same method can
        # be the slot and the constructor's direct call.
        theme = current_tokens()
        # No border: the rail is separated by its own darker plane, not a line.
        # Scoped to NavRail: a bare rule would repaint the buttons too, leaving
        # the checked item indistinguishable from the rest of the rail.
        self.setStyleSheet(
            f"NavRail {{ background-color: {theme.surface_sunken}; border: none; }}"
            f"NavRail QToolButton {{ background-color: transparent; border: none;"
            f" color: {theme.text_secondary}; }}"
            f"NavRail QToolButton:hover {{ background-color: {theme.hover}; }}"
            f"NavRail QToolButton:checked {{ background-color: {theme.surface_raised};"
            f" color: {theme.text}; }}"
        )

    def _make_button(self, glyph: QIcon, label: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(glyph)
        button.setText(label)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setAutoRaise(True)
        button.setFixedWidth(self._width)
        # ponytail: caption size is baked in once, so a density switch does not
        # resize the labels -- set_current() no-ops on an unchanged theme name,
        # so set_density() never reaches the notifier. Re-apply from a density
        # signal when 8.9 moves packing-tool to floor density.
        button.setStyleSheet(font_css("caption"))
        return button

    def add_item(self, glyph: QIcon, label: str) -> int:
        """Append a destination and return its index.

        Takes a rendered QIcon rather than a glyph name: the caller owns the
        colour, which is the active theme's at call time, and its icon("name")
        still raises KeyError on a typo, one frame earlier.
        """
        button = self._make_button(glyph, label)
        button.setCheckable(True)

        index = len(self._buttons)
        self._buttons.append(button)
        self._group.addButton(button, index)
        self._layout.insertWidget(index, button)
        button.clicked.connect(lambda _checked, i=index: self.set_current(i))

        if index == 0:
            button.setChecked(True)
            self._current = 0
        return index

    def add_footer_item(self, glyph: QIcon, label: str) -> QToolButton:
        """Append an app-level action below the destinations.

        Deliberately outside self._group and not checkable: an exclusive
        group has exactly one checked member, so a checkable gear would
        un-check the current destination and leave the rail lit nowhere
        while the page behind it had not moved.
        """
        button = self._make_button(glyph, label)
        self._layout.addWidget(button)
        return button

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
