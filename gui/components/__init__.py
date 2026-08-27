"""Shared UI components. See docs/superpowers/specs/2026-08-12-component-library-design.md."""

from gui.components.card import Card
from gui.components.form_section import FormSection
from gui.components.navrail import NavRail
from gui.components.selectionbar import ContextualSelectionBar
from gui.components.statcard import KpiStrip, StatCard

__all__ = [
    "Card",
    "ContextualSelectionBar",
    "FormSection",
    "KpiStrip",
    "NavRail",
    "StatCard",
]
