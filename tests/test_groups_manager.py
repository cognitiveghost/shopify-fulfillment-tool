"""Unit tests for GroupsManager — PostgreSQL backend.

Tests cover:
- Group CRUD operations
- Special groups immutability
- Client assignment queries
- Error handling
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from shopify_tool.db_manager import get_db
from shopify_tool.groups_manager import GroupsManager, GroupsManagerError
from shopify_tool.profile_manager import ProfileManager


# ── DB isolation ────────────────────────────────────────────────────────────


def _wipe():
    db = get_db()
    try:
        db.execute("DELETE FROM client_ui_settings")
    except Exception:
        pass
    try:
        db.execute("DELETE FROM groups")
    except Exception:
        pass
    try:
        db.execute("DELETE FROM clients")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_db():
    _wipe()
    yield
    _wipe()


# ── Common fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def temp_base_path():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def groups_manager(temp_base_path):
    return GroupsManager(str(temp_base_path))


# ── Initialization ──────────────────────────────────────────────────────────


class TestGroupsManagerInitialization:
    def test_init_creates_clients_directory(self, temp_base_path):
        """GroupsManager creates the Clients directory on the file server."""
        gm = GroupsManager(str(temp_base_path))
        assert (temp_base_path / "Clients").exists()

    def test_load_groups_empty_on_fresh_db(self, groups_manager):
        data = groups_manager.load_groups()
        assert "groups" in data
        assert "special_groups" in data
        assert data["groups"] == []

    def test_load_groups_includes_special_groups(self, groups_manager):
        data = groups_manager.load_groups()
        assert "pinned" in data["special_groups"]
        assert "all" in data["special_groups"]


# ── CRUD ────────────────────────────────────────────────────────────────────


class TestGroupCRUD:
    def test_create_group_success(self, groups_manager):
        group_id = groups_manager.create_group("Premium Clients", "#FF5722")

        assert group_id is not None
        assert isinstance(group_id, str)

        group = groups_manager.get_group(group_id)
        assert group is not None
        assert group["name"] == "Premium Clients"
        assert group["color"] == "#FF5722"
        assert "created_at" in group

    def test_create_group_default_color(self, groups_manager):
        group_id = groups_manager.create_group("Test Group")
        group = groups_manager.get_group(group_id)
        assert group["color"] == "#2196F3"

    def test_create_group_duplicate_name(self, groups_manager):
        groups_manager.create_group("Premium Clients")

        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.create_group("Premium Clients")
        assert "already exists" in str(exc_info.value).lower()

    def test_create_group_case_insensitive_duplicate(self, groups_manager):
        groups_manager.create_group("Premium Clients")
        with pytest.raises(GroupsManagerError):
            groups_manager.create_group("premium clients")

    def test_create_group_empty_name(self, groups_manager):
        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.create_group("")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_create_group_whitespace_name(self, groups_manager):
        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.create_group("   ")
        assert "cannot be empty" in str(exc_info.value).lower()

    def test_update_group_name(self, groups_manager):
        group_id = groups_manager.create_group("Old Name")

        success = groups_manager.update_group(group_id, name="New Name")
        assert success

        group = groups_manager.get_group(group_id)
        assert group["name"] == "New Name"

    def test_update_group_color(self, groups_manager):
        group_id = groups_manager.create_group("Test Group")

        success = groups_manager.update_group(group_id, color="#00FF00")
        assert success

        group = groups_manager.get_group(group_id)
        assert group["color"] == "#00FF00"

    def test_update_group_both_name_and_color(self, groups_manager):
        group_id = groups_manager.create_group("Old Name", "#FF0000")

        success = groups_manager.update_group(group_id, name="New Name", color="#0000FF")
        assert success

        group = groups_manager.get_group(group_id)
        assert group["name"] == "New Name"
        assert group["color"] == "#0000FF"

    def test_update_nonexistent_group(self, groups_manager):
        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.update_group("invalid-uuid", name="Test")
        assert "not found" in str(exc_info.value).lower()

    def test_update_group_duplicate_name(self, groups_manager):
        groups_manager.create_group("Group 1")
        group_id2 = groups_manager.create_group("Group 2")

        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.update_group(group_id2, name="Group 1")
        assert "already exists" in str(exc_info.value).lower()

    def test_delete_group(self, groups_manager):
        group_id = groups_manager.create_group("Test Group")

        success = groups_manager.delete_group(group_id)
        assert success

        assert groups_manager.get_group(group_id) is None

    def test_delete_nonexistent_group(self, groups_manager):
        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.delete_group("invalid-uuid")
        assert "not found" in str(exc_info.value).lower()

    def test_list_groups_sorted_by_display_order(self, groups_manager):
        id1 = groups_manager.create_group("Group C")
        id2 = groups_manager.create_group("Group A")
        id3 = groups_manager.create_group("Group B")

        groups = groups_manager.list_groups()

        assert len(groups) == 3
        assert groups[0]["name"] == "Group C"
        assert groups[1]["name"] == "Group A"
        assert groups[2]["name"] == "Group B"

    def test_list_groups_empty(self, groups_manager):
        assert groups_manager.list_groups() == []

    def test_get_group_by_id(self, groups_manager):
        group_id = groups_manager.create_group("Test Group", "#FF0000")

        group = groups_manager.get_group(group_id)
        assert group is not None
        assert group["id"] == group_id
        assert group["name"] == "Test Group"
        assert group["color"] == "#FF0000"

    def test_get_nonexistent_group(self, groups_manager):
        assert groups_manager.get_group("invalid-uuid") is None


# ── Special groups ──────────────────────────────────────────────────────────


class TestSpecialGroups:
    def test_special_groups_immutable(self, groups_manager):
        with pytest.raises(GroupsManagerError) as exc_info:
            groups_manager.delete_group("pinned")
        assert "special group" in str(exc_info.value).lower()

        with pytest.raises(GroupsManagerError):
            groups_manager.delete_group("all")

    def test_cannot_delete_special_groups(self, groups_manager):
        for gid in ("pinned", "all"):
            with pytest.raises(GroupsManagerError) as exc_info:
                groups_manager.delete_group(gid)
            assert "cannot delete" in str(exc_info.value).lower()
            assert "special" in str(exc_info.value).lower()


# ── Client coordination ─────────────────────────────────────────────────────


class TestClientCoordination:
    def test_get_clients_in_group(self, groups_manager, temp_base_path):
        """get_clients_in_group queries client_ui_settings via DB."""
        pm = ProfileManager(str(temp_base_path))
        pm.create_client_profile("M", "M Cosmetics")
        pm.create_client_profile("A", "A Company")

        group_id = groups_manager.create_group("Test Group")

        # Assign M to the group
        pm.update_ui_settings("M", {"group_id": group_id})

        clients = groups_manager.get_clients_in_group(group_id, pm)
        assert "M" in clients
        assert "A" not in clients

    def test_get_clients_in_group_empty(self, groups_manager, temp_base_path):
        pm = ProfileManager(str(temp_base_path))
        pm.create_client_profile("M", "M Cosmetics")

        group_id = groups_manager.create_group("Empty Group")
        clients = groups_manager.get_clients_in_group(group_id, pm)
        assert clients == []

    def test_delete_group_unassigns_clients(self, groups_manager, temp_base_path):
        """Deleting a group sets group_id = NULL for assigned clients in DB."""
        pm = ProfileManager(str(temp_base_path))
        pm.create_client_profile("M", "M Cosmetics")

        group_id = groups_manager.create_group("Test Group")
        pm.update_ui_settings("M", {"group_id": group_id})

        # Verify assignment
        assert "M" in groups_manager.get_clients_in_group(group_id, pm)

        groups_manager.delete_group(group_id)

        # group_id should be NULL after deletion
        config = pm.load_client_config("M")
        assert config["ui_settings"]["group_id"] is None

    def test_save_groups_sync(self, groups_manager):
        """save_groups can sync a full groups list back into DB."""
        g1 = groups_manager.create_group("Group 1")
        g2 = groups_manager.create_group("Group 2")

        groups_data = groups_manager.load_groups()
        groups_data["groups"][0]["name"] = "Group 1 Updated"

        success = groups_manager.save_groups(groups_data)
        assert success

        updated = groups_manager.get_group(g1)
        assert updated["name"] == "Group 1 Updated"


# ── Error handling ──────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_concurrent_writes_are_safe(self, groups_manager):
        """Creating multiple groups in sequence is safe (no file locking needed)."""
        id1 = groups_manager.create_group("Group 1")
        id2 = groups_manager.create_group("Group 2")

        groups = groups_manager.list_groups()
        assert len(groups) == 2

    def test_no_backup_files_created(self, groups_manager):
        """DB backend does not create backup files."""
        groups_manager.create_group("Test Group")
        group_id = groups_manager.create_group("Another Group")
        groups_manager.update_group(group_id, name="Renamed")

        backups_dir = groups_manager.clients_dir / "backups"
        backups = list(backups_dir.glob("groups_*.json")) if backups_dir.exists() else []
        assert len(backups) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
