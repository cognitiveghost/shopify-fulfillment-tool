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
    @pytest.mark.xfail(
        strict=True,
        reason="BUG: create_group's duplicate-name check only scans "
               "groups_data['groups'], never special_groups -- "
               "create_group('Pinned') succeeds and produces a normal group "
               "whose display name collides with the built-in 'Pinned' group.",
    )
    def test_create_group_colliding_with_special_group_name_is_rejected(self, groups_manager):
        with pytest.raises(GroupsManagerError):
            groups_manager.create_group("Pinned")

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: save_groups()/create_group() only lock around the final "
               "write, not the preceding load_groups() read -- two near-"
               "simultaneous create_group() calls both read the same stale "
               "snapshot, so the second writer's save clobbers the first "
               "writer's newly-appended group even though create_group() "
               "returned a success UUID to both callers.",
    )
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
