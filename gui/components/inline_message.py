"""A problem shown where it happened.

The inline route (9.25): the message sits under the field it names, the typed
input survives, and the call site clears it when that field changes.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.4
"""

from PySide6.QtWidgets import QLabel

from shared.theme import font_css, on_theme_changed


class InlineMessage(QLabel):
    """A danger-coloured line that is hidden while it has nothing to say."""

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self.setWordWrap(True)
        self.setVisible(False)
        on_theme_changed(
            self,
            lambda tokens: self.setStyleSheet(
                f"{font_css('body')} color: {tokens.status_danger}; background: transparent;"
            ),
        )

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.setVisible(bool(text))

    def clear(self) -> None:
        self.setText("")
        self.setVisible(False)
