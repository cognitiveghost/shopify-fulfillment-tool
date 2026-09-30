"""Keyboard shortcuts, from the command-bar overflow (phase 1 spec section 5.7).

SHORTCUTS is hand-kept; tests/test_shortcuts_dialog.py fails when a row names a
key the main window no longer binds.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from shared.theme import current_tokens

SHORTCUTS = (
    ("Ctrl+1 … Ctrl+5", "Go to Setup, Results, Browse, Logs, Tools"),
    ("Ctrl+R", "Run analysis"),
    ("Ctrl+F", "Search results"),
    ("Ctrl+Z", "Undo the last change"),
)


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        # Opened from the overflow menu each time; don't keep one per open.
        self.setAttribute(Qt.WA_DeleteOnClose)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        mono = current_tokens().font_family_mono
        for combo, action in SHORTCUTS:
            keys = QLabel(combo)
            keys.setStyleSheet(f"font-family: {mono};")
            form.addRow(keys, QLabel(action))
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
