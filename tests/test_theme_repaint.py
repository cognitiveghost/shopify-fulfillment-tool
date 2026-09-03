"""A theme toggle must reach widgets that style themselves.

53 call sites in gui/ interpolate a token into a widget stylesheet once, at
build time. Re-polishing re-applies that same stale literal -- see ADR 0003.
"""
from PySide6.QtWidgets import QLabel

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed


def test_a_converted_widget_follows_the_toggle(qapp):
    manager = get_theme_manager()
    manager.set_theme("light")

    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text};"))
    light = label.styleSheet()

    manager.set_theme("dark")
    assert label.styleSheet() != light, "widget kept the light theme's hex"


def test_a_converted_widget_follows_a_density_change(qapp):
    """15 of the 53 also interpolate font_css(), which moves with density."""
    from shared.theme import font_css

    manager = get_theme_manager()
    manager.set_density("desk")

    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(font_css("body")))
    desk = label.styleSheet()

    manager.set_density("floor")
    assert label.styleSheet() != desk, "widget kept the desk type scale"
