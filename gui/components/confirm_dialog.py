"""The one confirm: for acts that destroy data Undo cannot reach.

The accept button is the verb, so the consequence is written on the thing you
press. Cancel is the default, so a reflexive Enter destroys nothing. An
undoable act never confirms; its toast carries Undo instead.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.2
"""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from gui.theme_manager import apply_dialog_button_roles
from shared.theme import font_css

_VERBS_THAT_NAME_NO_ACT = {"ok", "yes", "confirm", "continue"}


class ConfirmDialog(QDialog):
    """Title asks the question, body states count and consequence, verb acts."""

    def __init__(self, parent, *, title: str, body: str, verb: str) -> None:
        if verb.strip().lower() in _VERBS_THAT_NAME_NO_ACT:
            raise ValueError(f"A confirm names its act; {verb!r} does not")
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        # Fonts are baked here rather than re-run on a theme change: a modal
        # lives for seconds and nothing can toggle the theme behind it.
        heading = QLabel(title, self)
        heading.setWordWrap(True)
        heading.setStyleSheet(font_css("heading"))
        layout.addWidget(heading)

        self.body_label = QLabel(body, self)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet(font_css("body"))
        layout.addWidget(self.body_label)

        self.buttons = QDialogButtonBox(self)
        self.cancel_button = self.buttons.addButton(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.verb_button = QPushButton(verb, self)
        self.buttons.addButton(self.verb_button, QDialogButtonBox.ButtonRole.AcceptRole)
        apply_dialog_button_roles(self.buttons)
        self.verb_button.setAutoDefault(False)
        self.cancel_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @classmethod
    def ask(cls, parent, *, title: str, body: str, verb: str) -> bool:
        """Show the confirm and return True only if the verb was pressed."""
        return bool(cls(parent, title=title, body=body, verb=verb).exec())
