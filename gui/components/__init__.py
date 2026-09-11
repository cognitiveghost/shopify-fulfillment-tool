"""Shared UI components. See docs/superpowers/specs/2026-08-12-component-library-design.md."""

from gui.components.card import Card
from gui.components.commandbar import BarState, CommandBar
from gui.components.confirm_dialog import ConfirmDialog
from gui.components.elided_label import ElidedLabel
from gui.components.error_banner import ErrorBanner, show_error
from gui.components.file_slot import FileSlot
from gui.components.filterbar import FilterBar
from gui.components.form_section import FormSection, row_widget
from gui.components.inline_message import InlineMessage
from gui.components.overflow import OverflowMenu, overflow_button
from gui.components.print_options import PrintOptions
from gui.components.radio_card import RadioCard
from gui.components.selectionbar import ContextualSelectionBar
from gui.components.state_panel import StatePanel
from gui.components.toast import Toast, toast
from shared.navrail import NavRail

__all__ = [
    "BarState",
    "Card",
    "CommandBar",
    "ConfirmDialog",
    "ContextualSelectionBar",
    "ElidedLabel",
    "ErrorBanner",
    "FileSlot",
    "FilterBar",
    "FormSection",
    "InlineMessage",
    "NavRail",
    "OverflowMenu",
    "PrintOptions",
    "RadioCard",
    "StatePanel",
    "Toast",
    "overflow_button",
    "row_widget",
    "show_error",
    "toast",
]
