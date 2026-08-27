"""ClientDirectory: the client list and the actions that change it.

Inherits tests/test_client_sidebar_refresh.py's subject -- the sidebar this
came from is deleted in Task 8.
"""
import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui.client_directory import ClientDirectory


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def groups_manager(profile_manager):
    from shopify_tool.groups_manager import GroupsManager
    return GroupsManager(profile_manager.base_path)


@pytest.fixture
def directory(qapp, profile_manager, groups_manager):
    return ClientDirectory(profile_manager, groups_manager)


def test_gather_includes_all_clients(directory, profile_manager):
    profile_manager.create_client_profile("M", "Client M")
    profile_manager.create_client_profile("N", "Client N")
    assert set(directory.gather()["all_clients"]) == {"M", "N"}


def test_gather_flags_pinned_clients(directory, profile_manager):
    profile_manager.create_client_profile("M", "Client M")
    profile_manager.update_ui_settings("M", {"is_pinned": True})
    assert "M" in directory.gather()["pinned_client_ids"]


def test_gather_returns_no_qt_objects(directory, profile_manager):
    """It runs off the GUI thread, so it must be plain data."""
    import json
    profile_manager.create_client_profile("M", "Client M")
    json.dumps(directory.gather(), default=str)


def test_refresh_keeps_its_worker_alive(directory, profile_manager):
    """A bare local would be collected before the queued result lands --
    see the note ported from client_sidebar.py:333."""
    profile_manager.create_client_profile("M", "Client M")
    directory.refresh()
    assert directory._refresh_workers


def test_menu_offers_pin_for_an_unpinned_client(directory, profile_manager, qapp):
    profile_manager.create_client_profile("M", "Client M")
    menu = directory.menu_for("M", QWidget())
    assert next(a.text() for a in menu.actions()) == "Pin to Top"


def test_menu_offers_unpin_for_a_pinned_client(directory, profile_manager, qapp):
    profile_manager.create_client_profile("M", "Client M")
    profile_manager.update_ui_settings("M", {"is_pinned": True})
    menu = directory.menu_for("M", QWidget())
    assert next(a.text() for a in menu.actions()) == "Unpin"


def test_menu_lists_every_group_under_move_to_group(directory, profile_manager,
                                                    groups_manager, qapp):
    profile_manager.create_client_profile("M", "Client M")
    groups_manager.create_group("Retail")
    menu = directory.menu_for("M", QWidget())
    move = next(a for a in menu.actions() if a.text() == "Move to Group")
    assert [a.text() for a in move.menu().actions()] == ["(No group)", "Retail"]
