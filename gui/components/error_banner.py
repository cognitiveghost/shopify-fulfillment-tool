"""A failure that persists until dismissed, and says what to do.

The error banner route (9.25). It never repeats the exception: that is in
Logs (see gui/log_handler.py). On the main window it has a slot under the
command bar and an Open Logs button; in a dialog it is inserted at the top of
the dialog's layout, where Logs is out of reach.

"Dismiss" is a word because the asset library has no `x` glyph, and a glyph is
a packing-tool PR.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.3
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shared.theme import font_css, on_theme_changed, set_button_role


class ErrorBanner(QFrame):
    """Headline, what-to-do line, optional Open Logs, and Dismiss."""

    def __init__(
        self, parent=None, *, open_logs: Callable[[], None] | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("errorBanner")
        self.setAccessibleName("Error")

        self._headline = QLabel(self)
        self._headline.setObjectName("errorHeadline")
        self._headline.setWordWrap(True)
        self._what = QLabel(self)
        self._what.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._headline)
        text.addWidget(self._what)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        row.addLayout(text, 1)

        self.logs_button = None
        if open_logs is not None:
            self.logs_button = QPushButton("Open Logs", self)
            set_button_role(self.logs_button, "ghost")
            self.logs_button.clicked.connect(open_logs)
            row.addWidget(self.logs_button, 0, Qt.AlignmentFlag.AlignTop)
        self.dismiss_button = QPushButton("Dismiss", self)
        set_button_role(self.dismiss_button, "ghost")
        self.dismiss_button.clicked.connect(self.dismiss)
        row.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignTop)

        self.hide()
        on_theme_changed(self, self._restyle)

    @classmethod
    def for_window(cls, window: QWidget) -> "ErrorBanner | None":
        banner = getattr(window, "error_banner", None)
        return banner if isinstance(banner, cls) else None

    def show_error(self, headline: str, what_to_do: str) -> None:
        self._headline.setText(headline)
        self._what.setText(what_to_do)
        self.show()

    def headline(self) -> str:
        return self._headline.text()

    def what_to_do(self) -> str:
        return self._what.text()

    def dismiss(self) -> None:
        self.hide()

    def _restyle(self, tokens) -> None:
        self.setStyleSheet(
            f"QFrame#errorBanner {{ background-color: {tokens.status_danger_bg}; border: none;"
            f" border-left: 3px solid {tokens.status_danger};"
            f" border-radius: {tokens.radius_md}px; }}"
            f" QFrame#errorBanner QLabel {{ {font_css('body')} color: {tokens.text};"
            f" background: transparent; }}"
            f" QFrame#errorBanner QLabel#errorHeadline {{ {font_css('body', bold=True)} }}"
        )


def show_error(source: QWidget, headline: str, what_to_do: str) -> ErrorBanner:
    """Show a failure on the window `source` belongs to. Log it first."""
    if not isinstance(source, QWidget):
        raise TypeError(
            f"show_error() needs a QWidget source, not {type(source).__name__}"
        )
    host = source.window()
    banner = ErrorBanner.for_window(host)
    if banner is None:
        layout = host.layout()
        if not isinstance(layout, QBoxLayout):
            raise TypeError(
                f"{type(host).__name__} has no box layout to hold an error banner"
            )
        banner = ErrorBanner(host)
        layout.insertWidget(0, banner)
        host.error_banner = banner
    banner.show_error(headline, what_to_do)
    return banner
