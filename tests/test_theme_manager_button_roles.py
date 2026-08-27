"""The button hierarchy is defined once, in shared/, and re-exported here.

Existing call sites import set_button_role from gui.theme_manager. Moving the
definition must not move the import.
"""
from gui.theme_manager import BUTTON_ROLES, role_stylesheet, set_button_role
from shared.theme import DARK_THEME, build_stylesheet


def test_button_roles_are_re_exported_from_shared():
    import shared.theme

    assert BUTTON_ROLES is shared.theme.BUTTON_ROLES
    assert set_button_role is shared.theme.set_button_role


def test_role_stylesheet_no_longer_defines_button_rules():
    sheet = role_stylesheet(DARK_THEME)
    assert "QPushButton" not in sheet
    assert "QListWidget#settingsNav" in sheet


def test_the_button_rules_now_come_from_the_shared_sheet():
    shared_sheet = build_stylesheet(DARK_THEME)
    for role in BUTTON_ROLES:
        assert f'QPushButton[role="{role}"]' in shared_sheet
