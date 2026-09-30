"""The shell's sidebar: header, destinations, footer (phase 1 spec section 4.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.sidebar import SIDEBAR_WIDTH, Sidebar
from shared.theme import current_tokens

LONG_PATH = r"\\warehouse-fs01.corp.local\shares\fulfilment\production"


@pytest.fixture
def sidebar(qapp):
    bar = Sidebar()
    bar.resize(SIDEBAR_WIDTH, 700)
    bar.show()
    QApplication.processEvents()
    yield bar
    bar.close()


def test_it_starts_expanded_at_200(sidebar):
    assert sidebar.is_expanded()
    assert sidebar.width() == 200
    assert sidebar.rail.is_expanded()


def test_connected_has_no_retry(sidebar):
    sidebar.set_connection(True, r"\\fs01\fulfilment")
    assert sidebar.connection_label.text() == "Server connected"
    assert not sidebar.retry_button.isVisible()


def test_unreachable_offers_retry_and_retry_asks(sidebar):
    sidebar.set_connection(False, r"\\fs01\fulfilment")
    assert sidebar.connection_label.text() == "Server unreachable"
    assert sidebar.retry_button.isVisible()
    asked = []
    sidebar.retryRequested.connect(lambda: asked.append(1))
    sidebar.retry_button.click()
    assert asked == [1]


def test_a_long_server_path_elides_instead_of_widening(sidebar):
    sidebar.set_connection(True, LONG_PATH)
    QApplication.processEvents()
    assert sidebar.width() == 200
    assert "…" in sidebar.path_label.text()
    assert sidebar.path_label.toolTip() == LONG_PATH


def test_the_theme_segments_ask_for_their_theme(sidebar):
    seen = []
    sidebar.themeRequested.connect(seen.append)
    sidebar.dark_button.click()
    sidebar.light_button.click()
    assert seen == ["dark", "light"]


def test_the_collapsed_theme_button_always_asks_for_the_other_theme(sidebar):
    seen = []
    sidebar.themeRequested.connect(seen.append)
    sidebar.set_theme_name("light")
    sidebar.theme_toggle.click()
    sidebar.set_theme_name("dark")
    sidebar.theme_toggle.click()
    assert seen == ["dark", "light"]
    assert sidebar.theme_toggle.toolTip() == "Switch to Light"


def test_collapsing_leaves_a_56px_rail_and_says_so(sidebar):
    seen = []
    sidebar.expandedChanged.connect(seen.append)
    sidebar.collapse_button.click()
    QApplication.processEvents()
    assert seen == [False]
    assert sidebar.width() == 56
    assert not sidebar.rail.is_expanded()
    assert sidebar.expand_button.isVisible()
    assert not sidebar.collapse_button.isVisible()
    assert sidebar.connection_icon.isVisible()
    assert not sidebar.retry_button.isVisible()
    sidebar.expand_button.click()
    assert seen == [False, True]
    assert sidebar.width() == 200


def test_set_expanded_is_silent(sidebar):
    """Only the operator's click is a preference worth saving."""
    seen = []
    sidebar.expandedChanged.connect(seen.append)
    sidebar.set_expanded(False)
    assert seen == []


def test_client_settings_asks_and_can_be_disabled(sidebar):
    asked = []
    sidebar.settingsRequested.connect(lambda: asked.append(1))
    sidebar.settings_button.click()
    assert asked == [1]
    sidebar.set_settings_enabled(False)
    assert not sidebar.settings_button.isEnabled()


def test_the_sidebar_repaints_on_a_theme_change(sidebar):
    """Its own sheet outranks the app's, so it has to re-run on a toggle."""
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    start = "dark" if manager.is_dark_theme() else "light"
    other = "light" if start == "dark" else "dark"
    try:
        manager.set_theme(other)
        QApplication.processEvents()
        assert current_tokens().surface_sunken in sidebar.styleSheet()
        assert current_tokens().name == other
    finally:
        manager.set_theme(start)
