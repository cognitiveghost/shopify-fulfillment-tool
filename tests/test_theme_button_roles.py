"""The primary/secondary button hierarchy Track 3 said had to be built.

shared/theme.py paints every QPushButton accent-blue, and it is sync-owned
by packing-tool so it cannot be edited here. These rules are layered on in
gui/theme_manager.py, the repo-owned seam.
"""
import re

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from gui.theme_manager import role_stylesheet, set_button_role
from shared.theme import get_theme


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


def _background_color(qss: str, role: str) -> str:
    """The resolved colour of the role's base rule -- comparing whole QSS
    blocks instead would pass on `font-weight: bold` alone."""
    block = qss.split(f'QPushButton[role="{role}"]')[1].split("}")[0]
    match = re.search(r"background-color:\s*([^;]+);", block)
    assert match, f"no background-color in the {role} rule"
    return match.group(1).strip()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_both_roles_have_a_rule(theme_name):
    qss = role_stylesheet(get_theme(theme_name))
    assert 'QPushButton[role="primary"]' in qss
    assert 'QPushButton[role="secondary"]' in qss


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_two_roles_do_not_render_the_same(theme_name):
    """A token that happens to resolve to the same colour in one theme is
    invisible on Linux and only shows up on the Windows machines that run
    this app."""
    qss = role_stylesheet(get_theme(theme_name))
    primary = _background_color(qss, "primary")
    secondary = _background_color(qss, "secondary")
    assert primary != secondary, f"both roles render {primary} in the {theme_name} theme"


def test_set_button_role_sets_the_property():
    button = QPushButton("Save")
    set_button_role(button, "primary")
    assert button.property("role") == "primary"


def test_set_button_role_rejects_an_unknown_role():
    """Same rule Tracks 1-3 set for the type scale: a typo fails in
    development rather than silently rendering as an unstyled button."""
    button = QPushButton("Save")
    with pytest.raises(ValueError):
        set_button_role(button, "tertiary")


def test_the_suffix_is_actually_applied_to_the_app():
    from gui.theme_manager import get_theme_manager

    get_theme_manager().apply_theme()
    assert 'QPushButton[role="primary"]' in QApplication.instance().styleSheet()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_settings_nav_is_styled_as_a_sidebar(theme_name):
    qss = role_stylesheet(get_theme(theme_name))
    assert "QListWidget#settingsNav" in qss
    assert "QListWidget#settingsNav::item:selected" in qss
