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


class TestPackingProgressDelegate:
    def test_a_ratio_becomes_a_clamped_fraction(self, qapp):
        from gui.session_row_delegates import PackingProgressDelegate

        delegate = PackingProgressDelegate()
        assert delegate.bar_fraction(0.75) == 0.75
        assert delegate.bar_fraction(1.0) == 1.0

    def test_no_packing_lists_draws_no_bar(self, qapp):
        # _RatioSortItem stores -1.0 for "no lists at all", which must not
        # render as an empty-but-present bar -- the cell reads a dash.
        from gui.session_row_delegates import PackingProgressDelegate

        assert PackingProgressDelegate().bar_fraction(-1.0) == 0.0
        assert PackingProgressDelegate().bar_fraction(None) == 0.0


from unittest.mock import Mock

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent

from gui.session_browser_widget import SessionBrowserWidget
from gui.session_row_delegates import ROLE_MANUAL, ROLE_TOKEN


@pytest.fixture
def browser(qapp):
    widget = SessionBrowserWidget(Mock(), parent=None)
    widget.current_client_id = "M"
    return widget


def _session(name, **overrides):
    data = {
        "session_name": name,
        "session_path": f"/srv/{name}",
        "status": "active",
        "created_at": "2026-08-27T14:02:00",
        "comments": "",
        "statistics": {"packing_lists": [], "total_orders": 3, "total_items": 9},
        "packing_progress": {},
    }
    data.update(overrides)
    return data


class TestNoCellWidgets:
    def test_every_cell_is_a_plain_item(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2", status="completed")]
        browser._populate_table()
        table = browser.sessions_table
        assert table.columnCount() == 7
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                assert table.cellWidget(row, col) is None, (row, col)
                assert table.item(row, col) is not None, (row, col)

    def test_the_status_cell_carries_its_role_and_authorship(self, browser):
        browser.sessions_data = [
            _session("manual", status="completed", status_manually_set=True),
            _session("derived", status="completed"),
        ]
        browser._populate_table()
        by_name = {
            browser.sessions_table.item(r, 0).text(): browser.sessions_table.item(r, 2)
            for r in range(browser.sessions_table.rowCount())
        }
        assert by_name["manual"].data(ROLE_TOKEN) == "status_success"
        assert by_name["manual"].data(ROLE_MANUAL) is True
        assert by_name["derived"].data(ROLE_MANUAL) is False

    def test_the_tooltip_now_reaches_the_status_cell(self, browser):
        # It did not before: item(row, 2) was None because a combobox sat there.
        browser.sessions_data = [_session("s1")]
        browser._populate_table()
        assert "Session: s1" in browser.sessions_table.item(0, 2).toolTip()


class TestCommentMarker:
    def test_a_comment_shows_a_marker_and_stays_in_the_tooltip(self, browser):
        browser.sessions_data = [_session("s1", comments="short pick, ask Dana")]
        browser._populate_table()
        name = browser.sessions_table.item(0, 0)
        assert not name.icon().isNull()
        assert "short pick, ask Dana" in name.toolTip()

    def test_no_comment_means_no_marker(self, browser):
        browser.sessions_data = [_session("s1")]
        browser._populate_table()
        assert browser.sessions_table.item(0, 0).icon().isNull()

    def test_the_marker_does_not_touch_the_display_text(self, browser):
        # Sorting and every existing name assertion depend on this.
        browser.sessions_data = [_session("s1", comments="x")]
        browser._populate_table()
        assert browser.sessions_table.item(0, 0).text() == "s1"


def test_hovering_does_not_move_the_selection(browser):
    # The viewport eventFilter existed only because interactive cell widgets
    # forwarded mouse-move. With no cell widgets a plain QTableWidget already
    # leaves the selection alone -- this proves it before the filter is deleted.
    browser.sessions_data = [_session("s1"), _session("s2"), _session("s3")]
    browser._populate_table()
    browser.sessions_table.setCurrentCell(0, 0)
    viewport = browser.sessions_table.viewport()
    target = browser.sessions_table.visualRect(browser.sessions_table.model().index(2, 0))
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPoint(target.center()),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        ),
    )
    assert browser.sessions_table.currentRow() == 0
