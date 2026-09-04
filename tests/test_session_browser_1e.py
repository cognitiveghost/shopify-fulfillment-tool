"""Phase 8.7 / 1e -- Session Browser presentation.

Spec: docs/superpowers/specs/2026-08-28-phase8.7-1e-session-browser-design.md
"""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from gui.session_row_delegates import (
    STATUS_ROLES,
    PackingProgressDelegate,
    SessionStatusDelegate,
)
from gui.theme_manager import get_theme_manager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestStatusRoles:
    def test_every_session_status_maps_to_a_token_and_its_liveness(self, qapp):
        theme = get_theme_manager().get_current_theme()
        assert set(STATUS_ROLES) == {"active", "completed", "abandoned", "archived"}
        for role, _live in STATUS_ROLES.values():
            assert isinstance(getattr(theme, role), str)

    def test_archived_falls_back_to_surface_sunken_for_its_tint(self, qapp):
        # text_secondary has no _bg partner; StatusChip documents the same
        # fallback. Resolving it must not raise.
        from shared.theme import status_style

        theme = get_theme_manager().get_current_theme()
        role, _live = STATUS_ROLES["archived"]
        # Force live=True: the fallback is about the missing _bg partner, not
        # about archived's own (resting) liveness, which would mask it with
        # fill=None regardless of the fallback.
        style = status_style(role, theme, live=True)
        assert style.fill == theme.surface_sunken

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    @pytest.mark.parametrize("status", ["active", "completed", "abandoned", "archived"])
    @pytest.mark.parametrize("manual", [False, True])
    def test_the_delegate_and_the_chip_resolve_the_same_style(
        self, qapp, theme_name, status, manual
    ):
        # The delegate and StatusChip both resolve status_style() now (spec
        # section 3) instead of each carrying its own copy of the rule. This
        # is the guard that fails the build if they ever drift apart -- it
        # reads StatusChip's actual resolved style, not a second call to
        # status_style() that would pass by construction.
        from shared.theme import StatusChip, status_style

        manager = get_theme_manager()
        manager.set_theme(theme_name)
        theme = manager.get_current_theme()
        role, live = STATUS_ROLES[status]

        chip = StatusChip(role, status.capitalize(), theme, live=live, manual=manual)
        assert chip._style == status_style(role, theme, live=live, manual=manual)


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
from shared.theme import current_theme_name, set_current


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


class TestSelectionBar:
    def test_it_is_hidden_until_something_is_selected(self, browser):
        browser.sessions_data = [_session("s1")]
        browser._populate_table()
        assert not browser.selection_bar.isVisibleTo(browser)

    def test_one_row_enables_open_but_not_combined_export(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2")]
        browser._populate_table()
        browser.sessions_table.selectRow(0)
        assert browser.open_btn.isEnabled()
        assert not browser.combined_export_btn.isEnabled()
        assert browser.comment_btn.isEnabled()

    def test_two_rows_enable_combined_export_and_disable_the_comment(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2")]
        browser._populate_table()
        browser.sessions_table.selectAll()
        assert browser.combined_export_btn.isEnabled()
        assert not browser.comment_btn.isEnabled()

    def test_status_applies_to_every_selected_row(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2"), _session("s3")]
        browser._populate_table()
        browser.sessions_table.selectAll()
        browser.refresh_sessions = Mock()

        browser._apply_status_to_selection("Archived")

        calls = browser.session_manager.update_session_status.call_args_list
        assert len(calls) == 3
        assert all(c.kwargs["manual"] is True for c in calls)
        assert {c.args[1] for c in calls} == {"archived"}
        browser.refresh_sessions.assert_called_once()

    def test_the_comment_action_writes_through_the_existing_path(self, browser, monkeypatch):
        from PySide6.QtWidgets import QInputDialog

        browser.sessions_data = [_session("s1")]
        browser._populate_table()
        browser.sessions_table.selectRow(0)
        monkeypatch.setattr(
            QInputDialog, "getMultiLineText", lambda *a, **k: ("late courier", True)
        )
        browser.refresh_sessions = Mock()

        browser._edit_comment_for_selection()

        browser.session_manager.update_session_info.assert_called_once_with(
            "/srv/s1", {"comments": "late courier"}
        )

    def test_cancelling_the_comment_dialog_writes_nothing(self, browser, monkeypatch):
        from PySide6.QtWidgets import QInputDialog

        browser.sessions_data = [_session("s1")]
        browser._populate_table()
        browser.sessions_table.selectRow(0)
        monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("", False))

        browser._edit_comment_for_selection()

        browser.session_manager.update_session_info.assert_not_called()


class TestFilterRow:
    def test_search_narrows_rows_without_hitting_the_file_server(self, browser):
        browser.sessions_data = [_session("alpha"), _session("beta"), _session("alphabet")]
        browser._populate_table()
        assert browser.sessions_table.rowCount() == 3

        browser.filter_bar.search_field.setText("alpha")

        assert browser.sessions_table.rowCount() == 2
        browser.session_manager.list_client_sessions.assert_not_called()

    def test_search_is_case_insensitive(self, browser):
        browser.sessions_data = [_session("Alpha"), _session("beta")]
        browser._populate_table()
        browser.filter_bar.search_field.setText("ALPHA")
        assert browser.sessions_table.rowCount() == 1

    def test_the_count_says_how_many_of_how_many(self, browser):
        browser.sessions_data = [_session("alpha"), _session("beta")]
        browser._populate_table()
        assert browser.filter_bar.count_label.text() == "2 sessions"
        browser.filter_bar.search_field.setText("alpha")
        assert browser.filter_bar.count_label.text() == "1 of 2 sessions"

    def test_there_is_no_group_box(self, browser):
        from PySide6.QtWidgets import QGroupBox

        # Regions separate by elevation and space, not by a border drawing a
        # label the NavRail destination already shows.
        assert browser.findChildren(QGroupBox) == []


def test_row_height_follows_the_density_profile(qapp):
    from gui.theme_manager import get_density, get_density_profile, set_density

    original = get_density()
    try:
        for name in ("desk", "floor"):
            set_density(name)
            widget = SessionBrowserWidget(Mock(), parent=None)
            assert (
                widget.sessions_table.verticalHeader().defaultSectionSize()
                == get_density_profile().row_height
            )
    finally:
        set_density(original)


class TestASelectedRowStaysReadable:
    """Was two workarounds; is now one property of the theme.

    Selection is selection_bg with a selection_border ring, and every
    foreground a delegate can draw is validated against selection_bg by
    validate_theme. So the delegate needs no selected-state branch at all --
    that is what deleted label_color() and the backing disc.
    """

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    def test_every_painted_foreground_clears_aa_on_a_selected_row(
        self, qapp, theme_name
    ):
        from shared.theme import contrast_ratio

        manager = get_theme_manager()
        before = manager.get_current_theme().name
        try:
            manager.set_theme(theme_name)
            theme = manager.get_current_theme()
            painted = [theme.text] + [
                getattr(theme, role) for role, _live in STATUS_ROLES.values()
            ]
            for fg in painted:
                ratio = contrast_ratio(fg, theme.selection_bg)
                assert ratio >= 4.5, f"{theme_name}: {fg} on selection_bg = {ratio:.2f}"
        finally:
            manager.set_theme(before)

    def test_the_selected_state_helper_is_gone(self):
        # An interface fact, not a substring scan of the source: label_color()
        # existed only to swap in on_accent on a selected row, and the ring
        # removes the reason for it. Sibling delegates elsewhere in the app may
        # still legitimately read State_Selected, so this asserts the helper is
        # gone rather than that the phrase is absent.
        from gui import session_row_delegates

        assert not hasattr(session_row_delegates, "label_color")


class TestTheDelegatesActuallyPaint:
    """paint() had no coverage at all: offscreen widgets that are never shown
    never repaint, so the painting code shipped without ever being executed."""

    @pytest.fixture(autouse=True)
    def _restore_theme(self):
        manager = get_theme_manager()
        before = manager.get_current_theme().name
        yield
        manager.set_theme(before)

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    @pytest.mark.parametrize("selected", [False, True])
    @pytest.mark.parametrize("manual", [False, True])
    def test_status_delegate_paints(self, qapp, theme_name, selected, manual):
        get_theme_manager().set_theme(theme_name)

        table = QTableWidget(1, 1)
        item = QTableWidgetItem("Active")
        item.setData(ROLE_TOKEN, "status_info")
        item.setData(ROLE_MANUAL, manual)
        table.setItem(0, 0, item)

        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 130, 28)
        option.state = QStyle.State_Enabled
        if selected:
            option.state |= QStyle.State_Selected

        pixmap = QPixmap(130, 28)
        painter = QPainter(pixmap)
        try:
            SessionStatusDelegate(table).paint(
                painter, option, table.model().index(0, 0)
            )
        finally:
            painter.end()

    @pytest.mark.parametrize("theme_name", ["light", "dark"])
    @pytest.mark.parametrize("ratio", [-1.0, 0.0, 0.5, 1.0, None])
    def test_packing_delegate_paints(self, qapp, theme_name, ratio):
        get_theme_manager().set_theme(theme_name)

        table = QTableWidget(1, 1)
        item = QTableWidgetItem("2/4")
        item.setData(Qt.UserRole, ratio)
        table.setItem(0, 0, item)

        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 130, 28)
        option.state = QStyle.State_Enabled | QStyle.State_Selected

        pixmap = QPixmap(130, 28)
        painter = QPainter(pixmap)
        try:
            PackingProgressDelegate(table).paint(
                painter, option, table.model().index(0, 0)
            )
        finally:
            painter.end()


def test_a_theme_toggle_redraws_the_markers_without_dropping_the_selection(browser):
    """The comment marker is a QIcon snapshot, so a toggle has to redraw it --
    but re-populating the table to get there would clear the row the person
    who flipped the theme had selected."""
    browser.sessions_data = [_session("s1", comments="x"), _session("s2")]
    browser._populate_table()
    table = browser.sessions_table
    marked = next(r for r in range(table.rowCount()) if table.item(r, 0).text() == "s1")
    table.setCurrentCell(marked, 0)
    before = table.item(marked, 0).icon().cacheKey()

    other = 1 - marked

    was = current_theme_name()
    try:
        set_current("dark" if was != "dark" else "light")
        assert table.currentRow() == marked
        assert table.item(marked, 0).icon().cacheKey() != before
        assert table.item(other, 0).icon().isNull()
    finally:
        set_current(was or "light")
