"""The bar that appears only when something is selected.

Replaces the eleven-button row that reads as eleven equally urgent choices --
but the replacement happens in 8.7. This builds the bar; the row is untouched.

The caller formats the sentence ("3 orders . 11 items selected") because only
the caller knows what it is counting.
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from gui.theme_manager import font_css, get_theme_manager, set_button_role


class ContextualSelectionBar(QWidget):
    """Hidden until set_selection() is given a non-empty sentence."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._apply_theme()
        get_theme_manager().theme_changed.connect(self._apply_theme)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(font_css("body"))
        layout.addWidget(self.count_label)
        layout.addStretch()

        self.hide()

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self.setStyleSheet(
            f"ContextualSelectionBar {{ background-color: {theme.surface_raised};"
            f" border-top: 1px solid {theme.border_subtle}; }}"
        )

    def set_selection(self, count_text: str) -> None:
        """Non-empty text shows the bar; "" hides it."""
        self.count_label.setText(count_text)
        self.setVisible(bool(count_text))

    def add_action(self, label: str, slot=None, role: str = "secondary") -> QPushButton:
        """Append an action button. Raises ValueError on an unknown role.

        slot is optional: a button that opens a QMenu has no clicked handler.
        """
        button = QPushButton(label, self)
        set_button_role(button, role)   # raises ValueError on a typo
        if slot is not None:
            button.clicked.connect(slot)
        self.layout().addWidget(button)
        return button
