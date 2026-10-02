"""The Hub remembers which page you were on.

Eight pages and one QListWidget; the Weight and Rules pages are the ones
people return to.

Fixtures (qapp, no_modals, started_workers, window, make_settings_config)
all come from conftest.py.
"""

from typing import ClassVar
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStyleOptionViewItem

from gui.settings.window import SETTINGS_SEARCH_KEYWORDS, SettingsWindow


def _current_page_name(win):
    return win._settings_nav.currentItem().text()


def test_a_fresh_profile_lands_on_the_first_entry(window):
    assert _current_page_name(window) == "General"


def test_the_selected_page_is_remembered_by_name(
    qapp, no_modals, started_workers, make_settings_config
):
    first = SettingsWindow(
        client_id="M", client_config=make_settings_config(), profile_manager=Mock()
    )
    for row in range(first._settings_nav.count()):
        if first._settings_nav.item(row).text() == "Weight":
            first._settings_nav.setCurrentRow(row)
            break
    first.deleteLater()

    second = SettingsWindow(
        client_id="M", client_config=make_settings_config(), profile_manager=Mock()
    )
    assert _current_page_name(second) == "Weight"
    second.deleteLater()


def test_a_page_name_that_no_longer_exists_falls_back(
    qapp, no_modals, started_workers, make_settings_config
):
    """Nav groups have gained entries twice already. Storing a row index
    would silently point at a different page; a stale *name* must degrade to
    the first entry rather than raise or select nothing."""
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
        SettingsWindow.NAV_SETTINGS_KEY, "A Page That Was Removed"
    )

    win = SettingsWindow(
        client_id="M", client_config=make_settings_config(), profile_manager=Mock()
    )
    assert _current_page_name(win) == "General"
    win.deleteLater()


def test_group_headers_are_not_selectable(window):
    """Not selectable is also why one can never be the stored page name."""
    headers = [
        window._settings_nav.item(row)
        for row in range(window._settings_nav.count())
        if not window._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
    ]
    assert [h.text() for h in headers] == [
        "Data",
        "Fulfilment logic",
        "Output",
        "Organization",
    ]


def test_every_registered_page_is_reachable_from_the_nav(window):
    """The nav list and the page registry must name the same set.

    #288 merged the Packing Lists and Stock Exports pages into one "Reports"
    page but left SETTINGS_NAV_GROUPS naming the two old titles, so the OUTPUT
    group rendered empty and the merged page -- still in the QStackedWidget --
    had no way to be selected. _build_settings_nav's `continue` skips a nav
    name with no page, which is why nothing raised.

    Asserted in both directions: a page with no nav entry is unreachable, and
    a nav entry with no page is a silently dropped row.
    """
    nav_names = {
        window._settings_nav.item(row).text()
        for row in range(window._settings_nav.count())
        if window._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
    }
    assert nav_names == set(window._page_index_by_name)


def _headers(win):
    nav = win._settings_nav
    return {
        nav.item(r).text(): nav.item(r).isHidden()
        for r in range(nav.count())
        if nav.item(r).data(Qt.ItemDataRole.UserRole) is None
    }


def test_search_matches_a_keyword(window):
    assert window.filter_nav("box") == ["Weight"]


def test_search_matches_a_page_name_ignoring_case(window):
    assert window.filter_nav("SETS") == ["Sets"]


def test_a_group_with_no_match_hides_its_header(window):
    window.filter_nav("box")
    assert _headers(window) == {
        "Data": True,
        "Fulfilment logic": False,
        "Output": True,
        "Organization": True,
    }


def test_no_match_says_so_and_clearing_restores_every_page(window):
    assert window.filter_nav("zzz") == []
    assert not window._no_match_label.isHidden()
    assert window._no_match_label.text() == "No settings match “zzz”."
    assert len(window.filter_nav("")) == 8
    assert window._no_match_label.isHidden()


def test_search_placeholder_is_not_clipped(window):
    """Windows renders Segoe UI wider than the Linux dev font, so the width has
    to come from the font itself -- a hard number measured here would pass on
    CI and still clip on the machine the defect was reported from."""
    from gui.settings.window import NAV_SEARCH_CHROME_PX

    field = window._nav_search
    needed = (
        field.fontMetrics().horizontalAdvance(field.placeholderText())
        + NAV_SEARCH_CHROME_PX
    )
    assert field.width() >= needed


def test_the_search_field_and_the_nav_list_stay_the_same_width(window):
    """They sit in one column; a field that outgrew the list would step out of it."""
    assert window._nav_search.width() == window._settings_nav.width()


def test_enter_opens_the_first_match(window):
    window._nav_search.setText("courier")
    window._nav_search.returnPressed.emit()
    assert window._settings_nav.currentItem().text() == "Orders mapping"


def test_enter_in_search_opens_the_match_without_saving(window, started_workers):
    """QLineEdit passes Return on to the dialog, which clicks its default
    button -- Save. Emitting returnPressed cannot catch that; a key press can."""
    window.show()
    window._nav_search.setFocus()
    QTest.keyClicks(window._nav_search, "courier")
    QTest.keyClick(window._nav_search, Qt.Key.Key_Return)
    assert window._settings_nav.currentItem().text() == "Orders mapping"
    assert started_workers == []
    assert window.result() == 0 and not window.isHidden()


def test_every_nav_page_has_search_keywords():
    listed = sorted(
        n for _g, names in SettingsWindow.SETTINGS_NAV_GROUPS for n in names
    )
    assert sorted(SETTINGS_SEARCH_KEYWORDS) == listed


def test_a_nav_name_with_no_page_fails_construction(
    qapp, no_modals, started_workers, make_settings_config
):
    class Broken(SettingsWindow):
        SETTINGS_NAV_GROUPS: ClassVar = [
            *SettingsWindow.SETTINGS_NAV_GROUPS,
            ("Extra", ["Nope"]),
        ]

    with pytest.raises(ValueError):
        Broken(
            client_id="M", client_config=make_settings_config(), profile_manager=Mock()
        )


def test_an_empty_nav_group_fails_construction(
    qapp, no_modals, started_workers, make_settings_config
):
    class Broken(SettingsWindow):
        SETTINGS_NAV_GROUPS: ClassVar = [
            *SettingsWindow.SETTINGS_NAV_GROUPS,
            ("Empty", []),
        ]

    with pytest.raises(ValueError):
        Broken(
            client_id="M", client_config=make_settings_config(), profile_manager=Mock()
        )


def test_a_page_missing_from_the_nav_fails_construction(
    qapp, no_modals, started_workers, make_settings_config
):
    class Broken(SettingsWindow):
        SETTINGS_NAV_GROUPS: ClassVar = [
            (group, [name for name in names if name != "Weight"])
            for group, names in SettingsWindow.SETTINGS_NAV_GROUPS
        ]

    with pytest.raises(ValueError, match="nav lists"):
        Broken(
            client_id="M", client_config=make_settings_config(), profile_manager=Mock()
        )


def test_a_keyword_table_that_misses_a_page_fails_construction(
    qapp, no_modals, started_workers, make_settings_config, monkeypatch
):
    monkeypatch.delitem(SETTINGS_SEARCH_KEYWORDS, "Weight")
    with pytest.raises(ValueError, match="SETTINGS_SEARCH_KEYWORDS"):
        SettingsWindow(
            client_id="M", client_config=make_settings_config(), profile_manager=Mock()
        )


# --- the frame, to the mockup (phase 7 spec section 6) ------------------------


def _page_row(win, name):
    nav = win._settings_nav
    return next(r for r in range(nav.count()) if nav.item(r).text() == name)


def test_the_title_bar_names_the_window_and_the_client(window):
    assert window.windowTitle() == "Client settings · M"


def test_the_nav_is_a_232px_column_of_30px_rows(window):
    from gui.settings.window import NAV_MARGIN_PX

    nav = window._settings_nav
    assert nav.width() + 2 * NAV_MARGIN_PX >= 232
    assert nav.item(_page_row(window, "General")).sizeHint().height() == 30
    assert nav.item(_page_row(window, "Data")).sizeHint().height() == 28
    assert window._nav_panel.objectName() == "settingsNavPanel"
    assert nav.parentWidget() is window._nav_panel


def test_only_the_open_page_reads_bold(window):
    nav = window._settings_nav
    window._select_page("Sets")
    bold = [
        nav.item(r).text()
        for r in range(nav.count())
        if nav.item(r).font().bold()
        and nav.item(r).data(Qt.ItemDataRole.UserRole) is not None
    ]
    assert bold == ["Sets"]


def test_a_rows_marks_are_drawn_at_its_right_edge(window):
    nav = window._settings_nav
    option = QStyleOptionViewItem()
    nav.itemDelegate().initStyleOption(
        option, nav.model().index(_page_row(window, "General"), 0)
    )
    assert option.decorationPosition == QStyleOptionViewItem.Position.Right


def _mark_pixel(win, name, x):
    from gui.settings.window import NAV_MARK_PX, NAV_MARKS_WIDTH_PX

    item = win._settings_nav.item(_page_row(win, name))
    image = item.icon().pixmap(NAV_MARKS_WIDTH_PX, NAV_MARK_PX).toImage()
    return image.pixelColor(x, NAV_MARK_PX // 2)


def test_the_unsaved_dot_is_the_text_colour(window):
    from gui.settings.window import NAV_MARKS_WIDTH_PX
    from gui.theme_manager import get_theme_manager

    assert _mark_pixel(window, "General", NAV_MARKS_WIDTH_PX - 4).alpha() == 0
    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["9"])
    dot = _mark_pixel(window, "General", NAV_MARKS_WIDTH_PX - 4)
    assert dot.name() == get_theme_manager().get_current_theme().text.lower()
    # The alert's place stays empty.
    assert _mark_pixel(window, "General", 1).alpha() == 0


def test_a_page_that_blocks_the_save_carries_the_alert(window):
    from PySide6.QtGui import QColor

    from gui.theme_manager import get_theme_manager

    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["x"])
    item = window._settings_nav.item(_page_row(window, "General"))
    assert item.toolTip() == "Needs attention, Unsaved changes"
    assert item.data(Qt.ItemDataRole.AccessibleTextRole) == (
        "General, needs attention, unsaved changes"
    )
    danger = QColor(get_theme_manager().get_current_theme().status_danger)
    edge = _mark_pixel(window, "General", 1)
    assert edge.alpha() > 0
    assert abs(edge.red() - danger.red()) < 40

    window._web_host.bridge.edit("threshold", ["5"])
    assert item.toolTip() == ""
    assert _mark_pixel(window, "General", 1).alpha() == 0


def test_a_profile_that_opens_with_a_required_column_unmapped_is_marked(
    qapp, no_modals, started_workers, make_settings_config
):
    config = make_settings_config()
    del config["column_mappings"]["orders"]["Shipping Method"]
    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    assert win._blocked == {"Orders mapping": "Map Shipping method"}
    item = win._settings_nav.item(_page_row(win, "Orders mapping"))
    assert item.toolTip() == "Needs attention"
    assert win.refresh_dirty() == []
    win.deleteLater()


def test_the_dialog_has_no_margins_and_a_qt_page_keeps_its_own(window):
    from gui.settings.window import FOOTER_HEIGHT_PX, PAGE_MARGIN_PX

    margins = window.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )
    assert window._pages_by_name["Sets"].contentsMargins().left() == PAGE_MARGIN_PX
    assert window._web_host.contentsMargins().left() == 0
    assert window._footer.height() == FOOTER_HEIGHT_PX == 60
