"""First run: the shell with nothing configured.

Every test here points the app at a path that does not exist, which is what
an unreachable UNC share looks like from inside ProfileManager.
"""

import pytest
from PySide6.QtWidgets import QApplication

from shopify_tool.profile_manager import NetworkError, ProfileManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def unreachable(tmp_path, monkeypatch):
    """A path under a file, so mkdir cannot succeed and neither can a touch."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    path = blocker / "server"
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(path))
    return path


def test_the_default_still_refuses_to_construct(unreachable):
    # The existing contract is unchanged for every caller that does not ask.
    with pytest.raises(NetworkError):
        ProfileManager()


def test_require_connection_false_returns_a_usable_object(unreachable):
    manager = ProfileManager(require_connection=False)
    assert manager.is_network_available is False
    # Every path it publishes is still a real Path, so no call site becomes
    # None-unsafe and no None-guard is written anywhere.
    assert manager.base_path.name == "server"
    assert manager.clients_dir.parent == manager.base_path


def test_a_reachable_share_is_unaffected_by_the_keyword(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    assert ProfileManager(require_connection=False).is_network_available is True


@pytest.fixture
def offline_window(unreachable):
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_window_opens_at_all(offline_window):
    # The contract this bundle changed: an unreachable share used to quit.
    assert offline_window.isVisible()
    assert offline_window.is_connected() is False


def test_only_setup_and_info_stay_enabled(offline_window):
    rail = offline_window.nav_rail
    enabled = [i for i in range(5) if rail.button(i).isEnabled()]
    # Disabled, never hidden: a rail that grows items as you configure the
    # app never lets you learn its shape.
    assert enabled == [0, 3]
    assert all(rail.button(i).isVisible() for i in range(5))


def test_setup_shows_the_unreachable_view_and_names_the_path(offline_window, unreachable):
    state = offline_window.setup_bridge.state
    assert state["view"] == "unreachable"
    assert state["server_path"] == str(unreachable)


def test_the_way_out_opens_the_connection_dialog(offline_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        offline_window.ui_manager, "_open_connection_settings", lambda: opened.append(1)
    )
    offline_window.setup_bridge.openConnection()
    assert opened == [1]


def test_the_sidebar_says_so_too(offline_window):
    sidebar = offline_window.sidebar
    assert sidebar.connection_label.text() == "Server unreachable"
    assert sidebar.retry_button.isVisible()


def test_the_rail_has_five_items_and_no_footer(offline_window):
    from PySide6.QtWidgets import QToolButton

    rail = offline_window.nav_rail
    assert len(rail.findChildren(QToolButton)) == 5
    assert not hasattr(offline_window, "connection_btn")


@pytest.fixture
def online_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_a_reachable_share_with_no_clients_asks_for_one(online_window):
    assert online_window.is_connected() is True
    assert online_window.setup_bridge.state["view"] == "no_client"


def test_with_no_client_the_selector_has_the_focus(online_window):
    # The action is the selector, so it takes focus; the page's panel has no button.
    assert online_window.command_bar.client_selector.hasFocus()


def test_the_share_answering_offers_what_needs_no_client(online_window):
    """Phase 1 spec section 5.4: Browse and Tools need a client, Results an
    analysis. Setup and Logs are always offered."""
    rail = online_window.nav_rail
    assert [i for i in range(5) if rail.button(i).isEnabled()] == [0, 3]


def test_the_rail_cannot_grow_a_footer_again():
    """The rail is for destinations, so there is no API for anything else.

    tests/test_components_navrail.py held four tests for add_footer_item;
    they were deleted with the method. This asserts the deletion rather than
    the behaviour, because the behaviour no longer exists to assert.
    """
    from shared.navrail import NavRail

    assert not hasattr(NavRail, "add_footer_item")


def test_the_selector_cannot_reach_the_share_it_cannot_reach(offline_window):
    """The disabled controls are the guard -- and the selector is one of them.

    It is not enough for the client list to come back empty: the component
    appends "New client..." and "Manage groups..." itself, and both write to
    the share. Disabled is the only state that closes that.
    """
    selector = offline_window.command_bar.client_selector
    assert selector.isEnabled() is False


def test_a_shortcut_cannot_walk_past_a_disabled_rail_button(offline_window):
    """Ctrl+2/3/5 go through the same gate the rail does.

    Bound straight to main_tabs they would navigate to Results, Browse and
    Tools while disconnected, which is the hole the disabled rail exists to
    close.
    """
    manager = offline_window.ui_manager
    manager._go_to_destination(1)          # Results, disabled offline
    assert offline_window.main_tabs.currentIndex() == 0
    manager._go_to_destination(3)          # Info, enabled offline
    assert offline_window.main_tabs.currentIndex() == 3


def test_the_title_names_the_app_and_its_version(offline_window):
    from shopify_tool import APP_NAME, __version__

    assert offline_window.windowTitle() == f"{APP_NAME} {__version__}"
