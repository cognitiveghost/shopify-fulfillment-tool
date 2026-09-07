"""Phase 8.7/1e and 9.19 -- Session Browser presentation.

Spec: docs/superpowers/specs/2026-08-28-phase8.7-1e-session-browser-design.md
Spec: docs/superpowers/specs/2026-09-04-phase9-bundle6-session-browser-design.md
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
    STATE_STYLES,
    PackingProgressDelegate,
    SessionStatusDelegate,
)
from gui.theme_manager import get_theme_manager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestPackingProgressDelegate:
    def test_a_ratio_becomes_a_clamped_fraction(self, qapp):
        from gui.session_row_delegates import PackingProgressDelegate

        delegate = PackingProgressDelegate()
        assert delegate.bar_fraction(0.75) == 0.75
        assert delegate.bar_fraction(1.0) == 1.0

    def test_no_packing_lists_draws_no_bar(self, qapp):
        # _SessionItem stores -1.0 for "no lists at all", which must not
        # render as an empty-but-present bar -- the cell reads a dash.
        from gui.session_row_delegates import PackingProgressDelegate

        assert PackingProgressDelegate().bar_fraction(-1.0) == 0.0
        assert PackingProgressDelegate().bar_fraction(None) == 0.0


from unittest.mock import Mock

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent

from gui.session_browser_widget import SessionBrowserWidget
from gui.session_row_delegates import ROLE_SHAPE, ROLE_TOKEN


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


def _session_items(browser):
    """Every session row (not group heading), across both groups."""
    tree = browser.sessions_tree
    return [
        tree.topLevelItem(g).child(i)
        for g in range(tree.topLevelItemCount())
        for i in range(tree.topLevelItem(g).childCount())
    ]


def _first_session_item(browser):
    return _session_items(browser)[0]


class TestNoCellWidgets:
    def test_every_row_has_no_cell_widgets(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2", status="completed")]
        browser._populate_tree()
        tree = browser.sessions_tree
        assert tree.columnCount() == 8
        for item in _session_items(browser):
            for col in range(tree.columnCount()):
                assert tree.itemWidget(item, col) is None

    def test_the_status_cell_carries_its_role_and_shape(self, browser):
        browser.sessions_data = [_session("s1", status="completed")]
        browser._populate_tree()
        item = _first_session_item(browser)
        assert item.data(2, ROLE_TOKEN) == "status_success"
        assert item.data(2, ROLE_SHAPE) == "check"

    def test_the_tooltip_reaches_the_status_cell(self, browser):
        # It did not before 1e: item(row, 2) was None because a combobox sat
        # there. Every column shares one tooltip now, so the reachability is
        # the same fact regardless of which column it's read from.
        browser.sessions_data = [_session("s1")]
        browser._populate_tree()
        tooltip = _first_session_item(browser).toolTip(2)
        assert tooltip.startswith("s1")
        assert "Status:" in tooltip


def test_hovering_does_not_move_the_selection(browser):
    # The viewport eventFilter existed only because interactive cell widgets
    # forwarded mouse-move. With no cell widgets a plain view already leaves
    # the selection alone -- this proves it before the filter is deleted.
    browser.sessions_data = [_session("s1"), _session("s2"), _session("s3")]
    browser._populate_tree()
    tree = browser.sessions_tree
    items = _session_items(browser)
    tree.setCurrentItem(items[0])
    viewport = tree.viewport()
    target_rect = tree.visualItemRect(items[2])
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPoint(target_rect.center()),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        ),
    )
    assert tree.currentItem() is items[0]


class TestSelectionBar:
    def test_it_is_hidden_until_something_is_selected(self, browser):
        browser.sessions_data = [_session("s1")]
        browser._populate_tree()
        assert not browser.selection_bar.isVisibleTo(browser)

    def test_one_row_enables_open_but_not_combined_export(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2")]
        browser._populate_tree()
        _first_session_item(browser).setSelected(True)
        assert browser.open_btn.isEnabled()
        assert not browser.combined_export_btn.isEnabled()
        assert browser.comment_btn.isEnabled()

    def test_two_rows_enable_combined_export_and_disable_the_comment(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2")]
        browser._populate_tree()
        browser.sessions_tree.selectAll()
        assert browser.combined_export_btn.isEnabled()
        assert not browser.comment_btn.isEnabled()

    def test_status_applies_to_every_selected_row(self, browser):
        browser.sessions_data = [_session("s1"), _session("s2"), _session("s3")]
        browser._populate_tree()
        browser.sessions_tree.selectAll()
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
        browser._populate_tree()
        _first_session_item(browser).setSelected(True)
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
        browser._populate_tree()
        _first_session_item(browser).setSelected(True)
        monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("", False))

        browser._edit_comment_for_selection()

        browser.session_manager.update_session_info.assert_not_called()


def _session_count(browser):
    tree = browser.sessions_tree
    return sum(
        tree.topLevelItem(g).childCount() for g in range(tree.topLevelItemCount())
    )


class TestFilterRow:
    def test_search_narrows_rows_without_hitting_the_file_server(self, browser):
        browser.sessions_data = [_session("alpha"), _session("beta"), _session("alphabet")]
        browser._populate_tree()
        assert _session_count(browser) == 3

        browser.filter_bar.search_field.setText("alpha")

        assert _session_count(browser) == 2
        browser.session_manager.list_client_sessions.assert_not_called()

    def test_search_is_case_insensitive(self, browser):
        browser.sessions_data = [_session("Alpha"), _session("beta")]
        browser._populate_tree()
        browser.filter_bar.search_field.setText("ALPHA")
        assert _session_count(browser) == 1

    def test_the_count_says_how_many_of_how_many(self, browser):
        browser.sessions_data = [_session("alpha"), _session("beta")]
        browser._populate_tree()
        assert browser.filter_bar.count_label.text() == "2 sessions"
        browser.filter_bar.search_field.setText("alpha")
        assert browser.filter_bar.count_label.text() == "1 of 2 sessions"

    def test_there_is_no_group_box(self, browser):
        from PySide6.QtWidgets import QGroupBox

        # Regions separate by elevation and space, not by a border drawing a
        # label the NavRail destination already shows.
        assert browser.findChildren(QGroupBox) == []


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
                getattr(theme, role) for role, _live, _shape in STATE_STYLES.values()
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
    @pytest.mark.parametrize("shape", ["ring", "half", "check", "tray"])
    def test_status_delegate_paints(self, qapp, theme_name, selected, shape):
        get_theme_manager().set_theme(theme_name)

        table = QTableWidget(1, 1)
        item = QTableWidgetItem("Active")
        item.setData(ROLE_TOKEN, "status_info")
        item.setData(ROLE_SHAPE, shape)
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
