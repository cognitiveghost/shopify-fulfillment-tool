"""The Hub remembers which page you were on.

Nine pages and one QListWidget; the Weight and Rules pages are the ones
people return to.

Fixtures (qapp, no_modals, started_workers, window, make_settings_config)
all come from conftest.py.
"""
from unittest.mock import Mock

from PySide6.QtCore import QSettings, Qt

from gui.settings.window import SettingsWindow


def _current_page_name(win):
    return win._settings_nav.currentItem().text()


def test_a_fresh_profile_lands_on_the_first_entry(window):
    assert _current_page_name(window) == "General"


def test_the_selected_page_is_remembered_by_name(
    qapp, no_modals, started_workers, make_settings_config
):
    first = SettingsWindow(client_id="M", client_config=make_settings_config(),
                           profile_manager=Mock())
    for row in range(first._settings_nav.count()):
        if first._settings_nav.item(row).text() == "Weight":
            first._settings_nav.setCurrentRow(row)
            break
    first.deleteLater()

    second = SettingsWindow(client_id="M", client_config=make_settings_config(),
                            profile_manager=Mock())
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

    win = SettingsWindow(client_id="M", client_config=make_settings_config(),
                         profile_manager=Mock())
    assert _current_page_name(win) == "General"
    win.deleteLater()


def test_group_headers_are_not_selectable(window):
    """Not selectable is also why one can never be the stored page name."""
    headers = [
        window._settings_nav.item(row)
        for row in range(window._settings_nav.count())
        if not window._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
    ]
    assert [h.text() for h in headers] == ["DATA", "FULFILLMENT LOGIC", "OUTPUT", "ORGANIZATION"]


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
