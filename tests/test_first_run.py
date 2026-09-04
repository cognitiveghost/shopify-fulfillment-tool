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


def test_setup_shows_the_panel_and_names_the_path(offline_window, unreachable):
    from PySide6.QtWidgets import QLabel

    assert offline_window.setup_stack.currentIndex() == 0
    rendered = " ".join(
        label.text()
        for label in offline_window.setup_state_panel.findChildren(QLabel)
    )
    assert "can't reach the fulfilment server" in rendered
    assert str(unreachable) in rendered
    assert "!" not in rendered
    assert "sorry" not in rendered.lower()


def test_the_one_accent_pixel_is_the_way_out(offline_window):
    button = offline_window.setup_state_panel.button
    assert button.text() == "Server connection…"
    assert button.property("role") == "primary"


def test_the_status_bar_says_so_too(offline_window):
    chip = offline_window.connection_chip
    assert chip.isVisible()
    assert "unreachable" in chip.text().lower()


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
    from PySide6.QtWidgets import QLabel

    assert online_window.is_connected() is True
    assert online_window.setup_stack.currentIndex() == 0
    rendered = " ".join(
        label.text()
        for label in online_window.setup_state_panel.findChildren(QLabel)
    )
    assert "Choose a client to begin" in rendered


def test_the_second_beat_has_no_accent_pixel_of_its_own(online_window):
    # The action is the selector, which takes focus; the primary reappears in
    # the command bar as New Session once a client exists. No third layout.
    assert online_window.setup_state_panel.button is None
    assert online_window.command_bar.client_selector.hasFocus()


def test_every_rail_item_is_enabled_once_the_share_answers(online_window):
    rail = online_window.nav_rail
    assert all(rail.button(i).isEnabled() for i in range(5))


def test_the_rail_cannot_grow_a_footer_again():
    """The rail is for destinations, so there is no API for anything else.

    tests/test_components_navrail.py held four tests for add_footer_item;
    they were deleted with the method. This asserts the deletion rather than
    the behaviour, because the behaviour no longer exists to assert.
    """
    from shared.navrail import NavRail

    assert not hasattr(NavRail, "add_footer_item")
