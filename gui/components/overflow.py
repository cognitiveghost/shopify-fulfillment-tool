"""The menu beside an object holding what configures it.

The rail is for destinations, so anything that configures the client or this
PC lands here instead. Two sections: the client's own name, then THIS PC --
the header shows a scope a rail item never could.

No icons: seven items with seven icons is a colour chart. Section headers are
disabled QActions rather than QMenu.addSection(), because addSection hands the
drawing to Qt and the artboard pins the type treatment.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle4-shell-design.md §4
"""

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton

from gui.theme_manager import get_theme_manager
from shared.theme import font_css, on_theme_changed

MENU_WIDTH = 284
ROW_HEIGHT = 28
MARK_COLUMN = 16   # keeps labels aligned whether or not anything is ticked


class OverflowMenu(QMenu):
    """Sections of app-level actions, styled to the artboard's rungs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(MENU_WIDTH)
        self.setToolTipsVisible(True)
        # The theme switch lives inside this menu, so a one-shot stylesheet
        # would go stale the moment it is used. ADR 0003.
        on_theme_changed(self, lambda _t: self._apply_theme())

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self.setStyleSheet(
            f"QMenu {{ background-color: {theme.surface_overlay};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_md}px; padding: 4px; }}"
            f"QMenu::item {{ {font_css('body')} color: {theme.text};"
            f" height: {ROW_HEIGHT}px; padding-left: {MARK_COLUMN + 8}px;"
            f" padding-right: 12px; }}"
            f"QMenu::item:selected {{ background-color: {theme.selection_bg}; }}"
            f"QMenu::item:disabled {{ {font_css('caption')}"
            f" color: {theme.text_secondary}; }}"
            f"QMenu::indicator {{ width: {MARK_COLUMN}px; }}"
        )

    def add_section(self, title: str) -> QAction:
        """A scope header. Disabled, so it is skipped by keyboard navigation."""
        header = QAction(title, self)
        header.setEnabled(False)
        self.addAction(header)
        return header

    def add_item(self, text: str, slot) -> QAction:
        item = QAction(text, self)
        item.triggered.connect(lambda _checked=False: slot())
        self.addAction(item)
        return item

    def add_choice_group(self, labels: list[str], current: str, slot) -> QActionGroup:
        """Mutually exclusive checkable items.

        Two items rather than one toggle: "Dark mode: off" is a sentence
        nobody reads correctly the first time.
        """
        group = QActionGroup(self)
        group.setExclusive(True)
        for label in labels:
            item = QAction(label, self)
            item.setCheckable(True)
            item.setChecked(label == current)
            item.triggered.connect(lambda _c=False, name=label: slot(name))
            group.addAction(item)
            self.addAction(item)
        return group


def overflow_button(menu: OverflowMenu, parent=None) -> QToolButton:
    """The three-dot button that opens the menu on one press.

    build_stylesheet has a QPushButton rule but no QToolButton one, so the
    global `QWidget { background-color: surface }` would leave this flat with
    no border and no hover.

    ponytail: this QSS is a near-copy of ui_manager._style_results_overflow.
    Not extracted, because Bundle 12 replaces the Analysis Results screen with
    the web tier and takes that call site with it. If Bundle 12 slips past
    Bundle 10, hoist this and delete the copy there.
    """
    button = QToolButton(parent)
    button.setText("⋯")
    button.setPopupMode(QToolButton.InstantPopup)
    button.setMenu(menu)

    def restyle(_tokens=None):
        theme = get_theme_manager().get_current_theme()
        button.setStyleSheet(
            f"QToolButton {{ background-color: {theme.surface_raised};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_sm}px; padding: 2px 6px;"
            f" color: {theme.text}; }}"
            f"QToolButton:hover {{ background-color: {theme.hover}; }}"
            f"QToolButton::menu-indicator {{ image: none; }}"
        )

    on_theme_changed(button, restyle)
    return button
