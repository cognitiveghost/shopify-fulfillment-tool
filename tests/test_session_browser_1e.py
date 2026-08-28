"""Phase 8.7 / 1e -- Session Browser presentation.

Spec: docs/superpowers/specs/2026-08-28-phase8.7-1e-session-browser-design.md
"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.session_row_delegates import (
    STATUS_ROLES,
    SessionStatusDelegate,
    chip_colors,
)
from gui.theme_manager import get_theme_manager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestStatusRoles:
    def test_every_session_status_maps_to_a_token(self, qapp):
        theme = get_theme_manager().get_current_theme()
        assert set(STATUS_ROLES) == {"active", "completed", "abandoned", "archived"}
        for role in STATUS_ROLES.values():
            assert isinstance(getattr(theme, role), str)

    def test_archived_falls_back_to_surface_sunken_for_its_tint(self, qapp):
        # text_secondary has no _bg partner; StatusChip documents the same
        # fallback. Resolving it must not raise.
        theme = get_theme_manager().get_current_theme()
        _fg, tint = chip_colors(STATUS_ROLES["archived"], theme)
        assert tint == theme.surface_sunken

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    @pytest.mark.parametrize("status", ["active", "completed", "abandoned", "archived"])
    def test_the_delegate_resolves_what_status_chip_resolves(self, qapp, theme_name, status):
        # The delegate copies StatusChip's two-line colour rule instead of
        # embedding a QLabel in a cell (spec section 3). This is the guard that
        # fails the build if the copy ever drifts.
        from shared.theme import StatusChip

        manager = get_theme_manager()
        manager.set_theme(theme_name)
        theme = manager.get_current_theme()
        role = STATUS_ROLES[status]

        chip = StatusChip(role, status.capitalize(), theme)
        sheet = chip.styleSheet()
        fg, tint = chip_colors(role, theme)

        assert f"color: {fg}" in sheet
        assert f"background-color: {tint}" in sheet


class TestAuthorshipPicksTheForm:
    def test_a_human_set_status_is_a_dot(self, qapp):
        kind, _fg, _tint = SessionStatusDelegate().form("status_info", manual=True)
        assert kind == "dot"

    def test_a_derived_status_is_a_tinted_chip(self, qapp):
        kind, _fg, tint = SessionStatusDelegate().form("status_info", manual=False)
        assert kind == "chip"
        assert tint == get_theme_manager().get_current_theme().status_info_bg
