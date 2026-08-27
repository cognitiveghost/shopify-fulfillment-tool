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
from gui.components.navrail import NavRail
from gui.theme_manager import get_theme_manager
from shared.theme import build_stylesheet


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
    rail.add_item("package", "One")
    rail.add_item("settings", "Two")
    rail.resize(56, 200)
    rail.show()
    QApplication.processEvents()

    assert _dominant_color(rail.button(0)) != _dominant_color(rail.button(1))
