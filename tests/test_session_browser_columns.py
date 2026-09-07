"""Columns, groups and archived visibility in the Session Browser.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle6-session-browser-design.md
"""
from datetime import datetime
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from gui.session_browser_widget import SessionBrowserWidget
from gui.theme_manager import get_density_profile
from shared.theme import theme_notifier
from shopify_tool.session_lifecycle import display_status

HEADERS = ["Session", "Age", "Status", "Orders", "Items",
           "Blocked", "Packing", "Comment"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def browser(qapp):
    widget = SessionBrowserWidget(Mock(), parent=None)
    widget.current_client_id = "M"
    # Synchronous, so a refresh triggered mid-test (e.g. clearing filters)
    # resolves before the assertion runs, instead of racing a real QThread.
    widget.USE_ASYNC = False
    return widget


def _session(name, status="active", lists=(), progress=None, **overrides):
    data = {
        "session_name": name,
        "session_path": f"/srv/{name}",
        "status": status,
        "created_at": "2026-08-27T14:02:00",
        "comments": "",
        "statistics": {
            "packing_lists": list(lists),
            "total_orders": 3,
            "total_items": 9,
        },
        "packing_progress": progress or {},
    }
    data.update(overrides)
    return data


@pytest.fixture
def calm_sessions():
    """Fully packed and closed out -- neither needs attention."""
    return [
        _session("alpha", status="completed", lists=["a"],
                 progress={"a": {"status": "completed"}}),
        _session("beta", status="completed", lists=["a", "b"],
                 progress={"a": {"status": "completed"}, "b": {"status": "completed"}}),
    ]


@pytest.fixture
def two_group_sessions():
    """One paused (needs attention), one closed out (does not)."""
    return [
        _session("stuck", lists=["a", "b"],
                 progress={"a": {"status": "completed"}, "b": {"status": "paused"}}),
        _session("fine", status="completed", lists=["a"],
                 progress={"a": {"status": "completed"}}),
    ]


@pytest.fixture
def commented_session():
    return _session("s1", comments="short pick, ask Dana")


@pytest.fixture
def sessions_with_archived():
    return [
        _session("live", status="completed", lists=["a"],
                 progress={"a": {"status": "completed"}}),
        _session("gone1", status="archived"),
        _session("gone2", status="archived"),
        _session("gone3", status="archived"),
    ]


def _column_text(browser, header):
    tree = browser.sessions_tree
    col = next(
        c for c in range(tree.columnCount())
        if tree.headerItem().text(c) == header
    )
    return [
        tree.topLevelItem(g).child(i).text(col)
        for g in range(tree.topLevelItemCount())
        for i in range(tree.topLevelItem(g).childCount())
    ]


def _names(browser):
    return _column_text(browser, "Session")


class TestColumnsAndGroups:
    def test_the_eight_headers(self, browser):
        tree = browser.sessions_tree
        assert tree.columnCount() == 8
        assert [tree.headerItem().text(c) for c in range(8)] == HEADERS

    def test_packing_lists_count_is_gone(self, browser):
        # It was the denominator of Packing. One fact, one column.
        assert "Packing Lists" not in [
            browser.sessions_tree.headerItem().text(c) for c in range(8)
        ]

    def test_two_groups_in_order(self, browser, two_group_sessions):
        browser.sessions_data = two_group_sessions
        browser._populate_tree()
        tree = browser.sessions_tree
        assert tree.topLevelItemCount() == 2
        assert tree.topLevelItem(0).text(0).startswith("Needs attention")
        assert tree.topLevelItem(1).text(0).startswith("Everything else")

    def test_an_empty_group_is_hidden(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser._populate_tree()
        assert browser.sessions_tree.topLevelItemCount() == 1
        assert browser.sessions_tree.topLevelItem(0).text(0).startswith("Everything else")

    def test_blocked_is_blank_at_zero_and_at_none(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert item.text(5) == ""

    def test_the_comment_column_carries_the_text(self, browser, commented_session):
        browser.sessions_data = [commented_session]
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert item.text(7) == commented_session["comments"]

    def test_the_name_cell_has_no_icon(self, browser, commented_session):
        browser.sessions_data = [commented_session]
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert item.icon(0).isNull()


class TestPackingColumn:
    def test_shows_packed_over_total(self, browser):
        browser.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"a": {"status": "completed"}})
        ]
        browser._populate_tree()
        assert _column_text(browser, "Packing") == ["1/2"]

    def test_session_with_no_packing_lists_shows_a_dash(self, browser):
        browser.sessions_data = [_session("s1")]
        browser._populate_tree()
        assert _column_text(browser, "Packing") == ["—"]

    def test_full_session_key_reads_as_complete(self, browser):
        browser.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"full_session": {"status": "completed"}})
        ]
        browser._populate_tree()
        assert _column_text(browser, "Packing") == ["2/2"]


class TestArchivedVisibility:
    def test_archived_sessions_are_hidden_by_default(self, browser):
        browser.sessions_data = [_session("keep"), _session("gone", status="archived")]
        browser._populate_tree()
        assert _names(browser) == ["keep"]

    def test_show_archived_toggle_reveals_them(self, browser):
        browser.sessions_data = [_session("keep"), _session("gone", status="archived")]
        browser.archive_toggle.click()
        assert sorted(_names(browser)) == ["gone", "keep"]

    def test_explicit_archived_status_filter_shows_them_with_toggle_off(self, browser):
        # The status filter is server-side: that path returns only archived
        # rows, so hiding them would leave the user staring at an empty tree.
        # Signal blocked: setCurrentText alone would fire currentTextChanged
        # -> _apply_filter -> a real background refresh against this test's
        # unconfigured Mock session_manager, which is not what this test
        # means to exercise.
        browser.status_filter.blockSignals(True)
        browser.status_filter.setCurrentText("Archived")
        browser.status_filter.blockSignals(False)
        browser.sessions_data = [_session("gone", status="archived")]
        browser._populate_tree()
        assert _names(browser) == ["gone"]


def test_manual_status_edit_is_recorded_as_manual(browser):
    browser._on_status_changed("/some/session", "Abandoned")
    browser.session_manager.update_session_status.assert_called_once_with(
        "/some/session", "abandoned", manual=True
    )


def test_display_status_is_reachable_from_the_module(calm_sessions):
    # Sanity check that the fixture data actually reads as "closed out" --
    # if this ever fails, the grouping tests above are exercising the wrong
    # thing and would otherwise fail confusingly.
    import datetime as _dt

    now = _dt.datetime.now().astimezone()
    assert all(display_status(s, now) == "completed" for s in calm_sessions)


class TestEmptyStates:
    def test_no_sessions_at_all_offers_a_new_session(self, browser):
        browser.current_client_id = "M"
        browser.sessions_data = []
        browser._populate_tree()
        assert browser._empty_reason() == "nothing"
        assert not browser.sessions_tree.isVisibleTo(browser)
        assert browser.empty_panel.button.text() == "New session"

    def test_a_filter_that_hides_everything_offers_to_clear_it(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser.filter_bar.search_field.setText("tuesday")
        browser._populate_tree()
        assert browser._empty_reason() == "filtered"
        assert browser.empty_panel.button.text() == "Clear filters"

    def test_clearing_the_filters_brings_the_rows_back(self, browser, calm_sessions):
        browser.session_manager.list_client_sessions.return_value = calm_sessions
        browser.sessions_data = calm_sessions
        browser.filter_bar.search_field.setText("tuesday")
        browser._populate_tree()
        browser.empty_panel.button.click()
        assert browser.filter_bar.search_field.text() == ""
        assert browser._empty_reason() is None
        assert browser.sessions_tree.isVisibleTo(browser)

    def test_rows_present_means_no_panel(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser._populate_tree()
        assert browser._empty_reason() is None
        assert browser.empty_panel is None or not browser.empty_panel.isVisible()


class TestArchiveFooter:
    def test_no_archived_sessions_means_no_line(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser._populate_tree()
        assert not browser.archive_line.isVisibleTo(browser)

    def test_the_line_counts_the_archived_sessions(self, browser, sessions_with_archived):
        browser.sessions_data = sessions_with_archived
        browser._populate_tree()
        assert browser.archive_line.isVisibleTo(browser)
        assert browser.archive_count.text() == "3 archived"
        assert browser.archive_toggle.text() == "Show"

    def test_showing_them_flips_the_verb_and_keeps_the_count(
        self, browser, sessions_with_archived
    ):
        browser.sessions_data = sessions_with_archived
        browser._populate_tree()
        browser.archive_toggle.click()
        assert browser.archive_toggle.text() == "Hide"
        assert browser.archive_count.text() == "3 archived"

    def test_the_old_toggle_button_is_gone(self, browser):
        assert not hasattr(browser, "show_archived_btn")

    def test_a_middot_separates_the_count_from_the_verb(self, browser,
                                                        sessions_with_archived):
        browser.sessions_data = sessions_with_archived
        browser._populate_tree()
        labels = browser.archive_line.findChildren(QLabel)
        assert "·" in [label.text() for label in labels]


@pytest.fixture
def sessions_across_time():
    """Four sessions whose names sort in the opposite order to their dates."""
    return [
        _session("weekish", created_at="2026-08-20T09:00:00"),
        _session("oldest", created_at="2026-02-01T09:00:00"),
        _session("newest", created_at="2026-09-04T09:00:00"),
        _session("mid", created_at="2026-08-25T09:00:00"),
    ]


class TestRowOrder:
    """Spec section 7: "Default sort stays created-descending"."""

    def test_the_default_order_is_newest_first(self, browser, sessions_across_time):
        browser.sessions_data = sessions_across_time
        browser._populate_tree()
        assert _names(browser) == ["newest", "mid", "weekish", "oldest"]

    def test_sorting_age_ascending_is_oldest_first(self, browser, sessions_across_time):
        browser.sessions_data = sessions_across_time
        browser._populate_tree()
        browser.sessions_tree.sortItems(1, Qt.AscendingOrder)
        assert _names(browser) == ["oldest", "weekish", "mid", "newest"]

    def test_the_groups_keep_their_order_under_a_descending_sort(
        self, browser, two_group_sessions
    ):
        browser.sessions_data = two_group_sessions
        browser._populate_tree()
        browser.sessions_tree.sortItems(0, Qt.DescendingOrder)
        tree = browser.sessions_tree
        headings = [
            tree.topLevelItem(i).text(0).split("  ")[0]
            for i in range(tree.topLevelItemCount())
        ]
        assert headings == ["Needs attention", "Everything else"]


class TestRowPresentation:
    def test_an_active_session_is_labelled_active_not_in_progress(self, browser):
        # Spec section 4's label table, and the word the status filter above
        # the tree already uses for the same stored status.
        browser.sessions_data = [
            _session("s1", lists=["a", "b"],
                     progress={"a": {"status": "completed"}},
                     last_updated=datetime.now().astimezone().isoformat())
        ]
        browser._populate_tree()
        assert _column_text(browser, "Status") == ["Active"]

    def test_blocked_is_right_aligned(self, browser):
        browser.sessions_data = [_session("s1", not_fulfillable_orders=4)]
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert item.textAlignment(5) & Qt.AlignRight

    def test_the_row_height_follows_the_density_profile(self, browser, calm_sessions):
        browser.sessions_data = calm_sessions
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert item.sizeHint(0).height() == get_density_profile().row_height

    def test_a_long_comment_survives_in_the_row_tooltip(self, browser):
        # Spec section 6.3: the column elides, the tooltip does not.
        text = "short pick, ask Dana before releasing the rest of the pallet"
        browser.sessions_data = [_session("s1", comments=text)]
        browser._populate_tree()
        item = browser.sessions_tree.topLevelItem(0).child(0)
        assert f"Comment: {text}" in item.toolTip(0)


def test_a_theme_toggle_rebuilds_the_rows_that_baked_theme_colours_in(
    browser, sessions_with_archived
):
    # ADR 0003: _build_row bakes the archive tint, the blocked tint and the
    # abandoned dimming into its items, and a baked colour does not follow a
    # toggle -- so the rows have to be rebuilt off the signal.
    browser.sessions_data = sessions_with_archived
    browser._populate_tree()
    before = _names(browser)
    browser.sessions_tree.clear()
    theme_notifier.changed.emit("dark")
    assert _names(browser) == before
