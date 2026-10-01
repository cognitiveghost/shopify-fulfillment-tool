"""Shared UI components. See docs/superpowers/specs/2026-08-12-component-library-design.md."""

from gui.components.commandbar import BarState, CommandBar
from gui.components.elided_label import ElidedLabel
from gui.components.error_banner import ErrorBanner, show_error
from gui.components.form_section import FormSection, row_widget
from gui.components.inline_message import InlineMessage
from gui.components.print_options import PrintOptions
from shared.components import (
    Card,
    ConfirmDialog,
    FilterBar,
    OverflowMenu,
    StatePanel,
    Toast,
    overflow_button,
)
from shared.components import toast as _qt_toast
from shared.navrail import NavRail


def toast(source, text, *, role="success", action_text="", on_action=None):
    """Good news that never blocks, drawn where it can be seen.

    A Qt toast is a child of its window and cannot paint above a web view
    (ADR 0007). So a window that is showing a web page is asked first
    (`web_toast`) and that page draws the toast; anything else, and any toast
    that carries an action, is the Qt toast. Returns the Qt Toast, or None
    when a page drew it.
    """
    window = source.window() if hasattr(source, "window") else None
    web_toast = getattr(window, "web_toast", None)
    if web_toast is not None and not action_text and web_toast(text):
        return None
    return _qt_toast(
        source, text, role=role, action_text=action_text, on_action=on_action
    )


__all__ = [
    "BarState",
    "Card",
    "CommandBar",
    "ConfirmDialog",
    "ElidedLabel",
    "ErrorBanner",
    "FilterBar",
    "FormSection",
    "InlineMessage",
    "NavRail",
    "OverflowMenu",
    "PrintOptions",
    "StatePanel",
    "Toast",
    "overflow_button",
    "row_widget",
    "show_error",
    "toast",
]
