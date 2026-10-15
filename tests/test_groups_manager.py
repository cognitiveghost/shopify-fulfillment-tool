"""Client group config accuracy (part of priority 6: app config accuracy)."""
import threading
import time

import pytest

from shopify_tool.groups_manager import GroupsManager, GroupsManagerError


@pytest.fixture
def groups_manager(tmp_path):
    return GroupsManager(base_path=str(tmp_path))


class TestBasicCrud:
    def test_create_then_list_round_trips(self, groups_manager):
        gid = groups_manager.create_group("Wholesale", color="#FF0000")
        groups = groups_manager.list_groups()
        assert len(groups) == 1
        assert groups[0]["id"] == gid
        assert groups[0]["name"] == "Wholesale"
        assert groups[0]["color"] == "#FF0000"

    def test_duplicate_name_rejected(self, groups_manager):
        groups_manager.create_group("Wholesale")
        with pytest.raises(GroupsManagerError):
            groups_manager.create_group("wholesale")  # case-insensitive collision

    def test_empty_name_rejected(self, groups_manager):
        with pytest.raises(GroupsManagerError):
            groups_manager.create_group("   ")

    def test_display_order_appends_to_end(self, groups_manager):
        groups_manager.create_group("A")
        groups_manager.create_group("B")
        groups = groups_manager.list_groups()
        orders = sorted(g["display_order"] for g in groups)
        assert orders == [0, 1]

    def test_delete_special_group_blocked(self, groups_manager):
        with pytest.raises(GroupsManagerError):
            groups_manager.delete_group("pinned")
        with pytest.raises(GroupsManagerError):
            groups_manager.delete_group("all")

    def test_update_special_group_raises_not_found(self, groups_manager):
        # 'pinned'/'all' live in a different JSON key than 'groups', so update
        # can never find them by id -- pinning this as the documented safe
        # (if accidental) behavior.
        with pytest.raises(GroupsManagerError, match="not found"):
            groups_manager.update_group("pinned", name="Hacked")

    def test_update_unknown_group_raises(self, groups_manager):
        with pytest.raises(GroupsManagerError):
            groups_manager.update_group("does-not-exist", name="X")


class TestConfirmedBugs:
    def test_create_group_colliding_with_special_group_name_is_rejected(self, groups_manager):
        with pytest.raises(GroupsManagerError):
            groups_manager.create_group("Pinned")

    def test_concurrent_create_group_does_not_lose_an_update(self, groups_manager, monkeypatch):
        original_load = groups_manager.load_groups

        def slow_load():
            data = original_load()
            time.sleep(0.05)  # widen the read-then-write race window deterministically
            return data

        monkeypatch.setattr(groups_manager, "load_groups", slow_load)

        results = {}

        def _create(name):
            results[name] = groups_manager.create_group(name)

        t1 = threading.Thread(target=_create, args=("Foo",))
        t2 = threading.Thread(target=_create, args=("Bar",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        names = {g["name"] for g in groups_manager.list_groups()}
        assert names == {"Foo", "Bar"}


class TestUpdateAndDelete:
    def test_update_renames_and_recolours_and_persists(self, groups_manager):
        gid = groups_manager.create_group("Wholesale", color="#FF0000")
        assert groups_manager.update_group(gid, name=" Retail ", color="#00FF00") is True
        group = groups_manager.get_group(gid)
        assert (group["name"], group["color"]) == ("Retail", "#00FF00")

    def test_update_to_an_existing_name_is_refused_and_changes_nothing(self, groups_manager):
        groups_manager.create_group("Retail")
        gid = groups_manager.create_group("Wholesale")
        with pytest.raises(GroupsManagerError, match="already exists"):
            groups_manager.update_group(gid, name="retail")
        assert groups_manager.get_group(gid)["name"] == "Wholesale"

    def test_update_to_an_empty_name_is_refused(self, groups_manager):
        gid = groups_manager.create_group("Wholesale")
        with pytest.raises(GroupsManagerError, match="empty"):
            groups_manager.update_group(gid, name="  ")

    def test_update_to_a_special_group_name_is_refused(self, groups_manager):
        gid = groups_manager.create_group("Wholesale")
        with pytest.raises(GroupsManagerError, match="already exists"):
            groups_manager.update_group(gid, name="Pinned")

    def test_delete_unknown_group_raises(self, groups_manager):
        with pytest.raises(GroupsManagerError, match="not found"):
            groups_manager.delete_group("does-not-exist")

    def test_get_unknown_group_is_none(self, groups_manager):
        assert groups_manager.get_group("does-not-exist") is None

    def test_delete_unassigns_that_groups_clients_only(self, tmp_path, profile_manager):
        groups = GroupsManager(base_path=str(tmp_path))
        keep = groups.create_group("Keep")
        drop = groups.create_group("Drop")
        for client, group in (("AAA", drop), ("BBB", keep), ("CCC", drop)):
            profile_manager.create_client_profile(client, f"Client {client}")
            profile_manager.update_ui_settings(client, {"group_id": group})
        assert sorted(groups.get_clients_in_group(drop, profile_manager)) == ["AAA", "CCC"]

        assert groups.delete_group(drop, profile_manager) is True

        assert groups.get_group(drop) is None
        assert profile_manager.get_ui_settings("AAA")["group_id"] is None
        assert profile_manager.get_ui_settings("CCC")["group_id"] is None
        assert profile_manager.get_ui_settings("BBB")["group_id"] == keep
        assert groups.get_clients_in_group(keep, profile_manager) == ["BBB"]


class TestLoadRecovery:
    def test_a_missing_file_gives_the_defaults(self, groups_manager):
        data = groups_manager.load_groups()
        assert data["groups"] == [] and set(data["special_groups"]) == {"pinned", "all"}

    def test_corrupt_json_is_backed_up_and_replaced_by_defaults(self, groups_manager, tmp_path):
        path = groups_manager.groups_path
        path.write_text("{not json", encoding="utf-8")
        assert groups_manager.load_groups()["groups"] == []
        assert path.with_suffix(".corrupted.bak").read_text(encoding="utf-8") == "{not json"

    def test_a_document_without_groups_is_backed_up_and_replaced(self, groups_manager):
        path = groups_manager.groups_path
        path.write_text('{"unrelated": 1}', encoding="utf-8")
        assert groups_manager.load_groups()["groups"] == []
        assert path.with_suffix(".corrupted.bak").exists()

    def test_a_client_that_fails_to_load_is_skipped_when_listing_a_group(self, groups_manager):
        class Profiles:
            def list_clients(self):
                return ["OK", "BAD"]

            def load_client_config(self, client_id):
                if client_id == "BAD":
                    raise OSError("share dropped")
                return {"ui_settings": {"group_id": "g1"}}

        assert groups_manager.get_clients_in_group("g1", Profiles()) == ["OK"]

    def test_save_failure_is_raised_as_a_groups_error(self, groups_manager, monkeypatch):
        import shopify_tool.groups_manager as module

        def boom(*a, **k):
            raise PermissionError("denied")

        monkeypatch.setattr(module, "atomic_write_json", boom)
        with pytest.raises(GroupsManagerError, match="Failed to save"):
            groups_manager.create_group("Wholesale")
