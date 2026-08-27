"""The one-row bar across the top of every screen.

Client selector, session id, status, and exactly one primary action. "One
primary per screen" is enforced structurally: there is a single action button
and it is the only place in the component library that marks a button primary.
Replaces the sidebar of 70px client cards with a dropdown.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from gui.theme_manager import font_css, get_theme_manager, set_button_role
from shared.theme import StatusChip


class CommandBar(QWidget):
    """Emits selections and the action; owns no application state."""

    clientChanged = Signal(str)
    actionTriggered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()
        # Type-scoped, not bare: a selector-less sheet is wrapped into `* {}`
        # and a parent's sheet outranks the app's, so `background-color` here
        # would repaint every child -- flattening the button roles the app
        # stylesheet sets. Same reason for the scoping in the other containers.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {theme.surface_raised};"
            f" border-bottom: 1px solid {theme.border_subtle}; }}"
        )

        self._repopulating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self.client_selector = QComboBox(self)
        self.client_selector.currentTextChanged.connect(self._on_client_changed)
        layout.addWidget(self.client_selector)

        self.session_label = QLabel("", self)
        self.session_label.setStyleSheet(font_css("caption"))
        layout.addWidget(self.session_label)

        self.status_chip = StatusChip("text_secondary", "", theme, parent=self)
        self.status_chip.hide()   # an empty chip still paints a tinted pill
        layout.addWidget(self.status_chip)

        layout.addStretch()

        self.action_button = QPushButton("", self)
        set_button_role(self.action_button, "primary")
        self.action_button.clicked.connect(self.actionTriggered.emit)
        self.action_button.hide()
        layout.addWidget(self.action_button)

    def _on_client_changed(self, name: str) -> None:
        # Repopulating fires currentTextChanged per removal/insert; a consumer
        # reloading a client per signal would thrash the network file server.
        if not self._repopulating:
            self.clientChanged.emit(name)

    def set_clients(self, names: list[str]) -> None:
        self._repopulating = True
        try:
            self.client_selector.clear()
            self.client_selector.addItems(names)
        finally:
            self._repopulating = False

    def current_client(self) -> str:
        return self.client_selector.currentText()

    def set_session(self, text: str) -> None:
        self.session_label.setText(text)

    def set_status(self, role: str, text: str) -> None:
        self.status_chip.set_status(
            role, text, get_theme_manager().get_current_theme()
        )
        self.status_chip.setVisible(bool(text))

    def set_action(self, label: str) -> QPushButton:
        """Label and reveal the screen's single primary action."""
        self.action_button.setText(label)
        self.action_button.show()
        return self.action_button
