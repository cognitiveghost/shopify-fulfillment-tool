"""Good news that never blocks.

The toast route (9.25): something worked and there is nothing to decide. One
toast per window, on the window that raised it; the newest replaces the
oldest, and a badge counts a fast run of them.

No fade: the brief allows "at most" 150ms, and a toast you can click before it
has arrived is worse than none.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.1
"""

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QWidget,
)

from shared.theme import current_tokens, font_css, on_theme_changed, set_button_role


class Toast(QFrame):
    """One transient message at the bottom-right of its host window."""

    DURATION_MS = 4000
    BADGE_AT = 3
    MARGIN = 16
    MAX_WIDTH = 360
    ROLES = ("success", "info")

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("toast")
        self.setAccessibleName("Notification")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._host = host
        self._count = 0
        self._role = "success"
        self._on_action: Callable[[], None] | None = None

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self.badge = QLabel(self)
        self.badge.setObjectName("toastBadge")
        self.badge.setVisible(False)
        self.button = QPushButton(self)
        set_button_role(self.button, "ghost")
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setVisible(False)
        self.button.clicked.connect(self._run_action)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        row.addWidget(self._label, 1)
        row.addWidget(self.badge)
        row.addWidget(self.button)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DURATION_MS)
        self.timer.timeout.connect(self.dismiss)

        host.installEventFilter(self)
        self.hide()
        on_theme_changed(self, self._restyle)

    @classmethod
    def for_window(cls, window: QWidget) -> "Toast | None":
        return next((c for c in window.children() if isinstance(c, cls)), None)

    def text(self) -> str:
        return self._label.text()

    def count(self) -> int:
        return self._count

    def show_message(
        self,
        text: str,
        *,
        role: str = "success",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
    ) -> None:
        if role not in self.ROLES:
            raise ValueError(
                f"A toast is {self.ROLES}; a failure goes to the error banner"
            )
        self._count = self._count + 1 if not self.isHidden() else 1
        self._role = role
        self._label.setText(text)
        self.badge.setText(str(self._count))
        self.badge.setVisible(self._count >= self.BADGE_AT)
        self._on_action = on_action
        self.button.setText(action_text)
        self.button.setVisible(bool(action_text))
        self._restyle(current_tokens())
        self.show()
        self.raise_()
        self._place()
        self.timer.start()

    def dismiss(self) -> None:
        self.timer.stop()
        self.hide()
        self._count = 0
        self._on_action = None

    def _run_action(self) -> None:
        # Dismiss first: a toast the action raises (Undo's result) must survive.
        action = self._on_action
        self.dismiss()
        if action is not None:
            action()

    def _place(self) -> None:
        host = self._host
        bottom = host.height()
        if isinstance(host, QMainWindow):
            bar = host.statusBar()
            if not bar.isHidden():
                bottom -= bar.height()
        width = max(0, min(self.MAX_WIDTH, host.width() - 2 * self.MARGIN))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(
            host.width() - width - self.MARGIN, bottom - self.height() - self.MARGIN
        )

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self._host
            and event.type() == QEvent.Type.Resize
            and not self.isHidden()
        ):
            self._place()
        return False

    def enterEvent(self, event) -> None:
        self.timer.stop()  # an Undo has to be reachable
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self.isHidden():
            self.timer.start()
        super().leaveEvent(event)

    def _restyle(self, tokens) -> None:
        edge = getattr(tokens, f"status_{self._role}")
        self.setStyleSheet(
            f"QFrame#toast {{ background-color: {tokens.surface_overlay};"
            f" border: 1px solid {tokens.border}; border-left: 3px solid {edge};"
            f" border-radius: {tokens.radius_md}px; }}"
            f" QFrame#toast QLabel {{ {font_css('body')} color: {tokens.text};"
            f" background: transparent; border: none; }}"
            f" QFrame#toast QLabel#toastBadge {{ {font_css('caption')}"
            f" color: {tokens.text_secondary}; }}"
        )


def toast(
    source: QWidget,
    text: str,
    *,
    role: str = "success",
    action_text: str = "",
    on_action: Callable[[], None] | None = None,
) -> Toast:
    """Show `text` on the window `source` belongs to. After a dialog's accept(),
    pass the dialog's parent: the dialog is closing."""
    if not isinstance(source, QWidget):
        raise TypeError(f"toast() needs a QWidget source, not {type(source).__name__}")
    host = source.window()
    shown = Toast.for_window(host) or Toast(host)
    shown.show_message(text, role=role, action_text=action_text, on_action=on_action)
    return shown
