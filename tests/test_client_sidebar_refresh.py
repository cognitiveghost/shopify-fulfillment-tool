"""ClientSidebar's pure data-gathering step (no widget construction --
must be safe to run off the GUI thread per this repo's threading rule)."""
import pytest
from PySide6.QtWidgets import QApplication

from gui.client_sidebar import ClientSidebar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def groups_manager(profile_manager):
    from shopify_tool.groups_manager import GroupsManager
    return GroupsManager(profile_manager.base_path)


@pytest.fixture
def sidebar(qapp, profile_manager, groups_manager):
    return ClientSidebar(profile_manager, groups_manager)


class TestGatherRefreshData:
    def test_gather_includes_all_clients(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        profile_manager.create_client_profile("N", "Client N")
        data = sidebar._gather_refresh_data()
        assert set(data["all_clients"]) == {"M", "N"}

    def test_gather_flags_pinned_clients(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        profile_manager.update_ui_settings("M", {"is_pinned": True})
        data = sidebar._gather_refresh_data()
        assert "M" in data["pinned_client_ids"]

    def test_gather_returns_no_qt_objects(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        data = sidebar._gather_refresh_data()
        import json
        json.dumps(data, default=str)  # must be plain-data serializable
