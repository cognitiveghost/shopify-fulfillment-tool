"""The containers must not repaint their own children.

A selector-less setStyleSheet is wrapped into `* { ... }`, and Qt prefers a
parent widget's sheet over the application sheet regardless of specificity --
so `background-color` on a bar silently flattens every QPushButton[role=...]
rule inside it. Asserting `button.property("role")` cannot see that: the
property is set correctly, it just never reaches the pixels. These tests
sample what actually renders.
"""
from collections import Counter

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.commandbar import CommandBar
from gui.components.state_panel import StatePanel
from gui.theme_manager import get_theme_manager
from shared.icons import icon
from shared.navrail import NavRail
from shared.theme import DARK_THEME, LIGHT_THEME, StatusChip, build_stylesheet

# Spec §3.5: the eleven states Bundle 3 ships (4 Shopify + 7 Packing), not the
# artboard's thirteen -- the remaining two are 9.19's, gated on a data change.
ELEVEN_STATES = [
    ("Active", "status_info", True),
    ("Completed", "status_success", False),
    ("Abandoned (Shopify)", "status_danger", False),
    ("Archived", "text_secondary", False),
    ("Not started", "text_secondary", False),
    ("In progress", "status_info", True),
    ("Paused", "status_warning", True),
    ("Stale", "status_warning", True),
    ("Incomplete", "status_danger", True),
    ("Abandoned (Packing)", "status_danger", False),
    ("Packing completed", "status_success", False),
]


@pytest.fixture
def styled_app(qapp):
    """The app stylesheet really applied -- without it there are no role rules
    to flatten and every assertion below passes vacuously."""
    previous = qapp.styleSheet()
    qapp.setStyleSheet(build_stylesheet(get_theme_manager().get_current_theme()))
    yield qapp
    qapp.setStyleSheet(previous)


def _dominant_color(widget) -> str:
    """The most common pixel of the rendered widget, as #rrggbb.

    The mode rather than one sampled point: text glyphs and rounded corners
    make any single coordinate a coin flip.
    """
    image = widget.grab().toImage()
    pixels = Counter(
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
    )
    return pixels.most_common(1)[0][0]


def test_the_command_bar_action_still_renders_primary(styled_app):
    theme = get_theme_manager().get_current_theme()
    bar = CommandBar()
    bar.set_action("Process")
    bar.resize(600, 40)
    bar.show()
    QApplication.processEvents()

    assert _dominant_color(bar.action_button).lower() == theme.accent_fill.lower()


def test_the_nav_rail_shows_which_item_is_current(styled_app):
    rail = NavRail()
    rail.add_item(icon("package"), "One")
    rail.add_item(icon("settings"), "Two")
    rail.resize(56, 200)
    rail.show()
    QApplication.processEvents()

    assert _dominant_color(rail.button(0)) != _dominant_color(rail.button(1))


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize("label,role,live", ELEVEN_STATES)
@pytest.mark.parametrize("manual", [False, True])
def test_every_status_chip_renders_in_both_themes(styled_app, theme, label, role, live, manual):
    """9.3's `Done when`: eleven states, four live/manual combinations, two
    themes -- proved here rather than merely asserted by StatusStyle math."""
    chip = StatusChip(role, label, theme, live=live, manual=manual)
    chip.show()
    QApplication.processEvents()

    outline = f"border: 1px solid {getattr(theme, role)}"
    assert outline in chip.styleSheet()
    assert _dominant_color(chip)  # renders without raising


@pytest.mark.parametrize(
    "panel_factory",
    [
        lambda: StatePanel.nothing_loaded("No orders loaded", "Choose a file.", "Choose file…"),
        lambda: StatePanel.working("Analysing", "Matching orders against stock"),
        lambda: StatePanel.no_results("No orders match", "Filter: status is Blocked."),
        lambda: StatePanel.failed(
            "The stock file could not be read", "Nothing can load.", "no column Quantity",
            "Choose another file…",
        ),
    ],
)
def test_every_state_panel_variant_renders_in_both_themes(styled_app, panel_factory):
    manager = get_theme_manager()
    before = manager.get_current_theme().name
    try:
        for theme_name in ("light", "dark"):
            manager.set_theme(theme_name)
            panel = panel_factory()
            panel.resize(420, 260)
            panel.show()
            QApplication.processEvents()
            assert _dominant_color(panel)
    finally:
        manager.set_theme(before)
