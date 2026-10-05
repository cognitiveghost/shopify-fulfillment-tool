"""Client/app configuration + inventory memory accuracy (priorities 5 & 6)."""

import json

import pytest

from shopify_tool.profile_manager import ProfileManager, ProfileManagerError


class TestValidateClientId:
    @pytest.mark.parametrize("client_id", ["M", "CLIENT1", "A_B_C"])
    def test_valid_ids_accepted(self, client_id):
        ok, _msg = ProfileManager.validate_client_id(client_id)
        assert ok is True

    def test_rejects_client_prefix(self):
        ok, _msg = ProfileManager.validate_client_id("CLIENT_FOO")
        assert ok is False

    def test_rejects_empty(self):
        ok, _msg = ProfileManager.validate_client_id("")
        assert ok is False

    def test_rejects_too_long(self):
        ok, _msg = ProfileManager.validate_client_id("X" * 21)
        assert ok is False

    def test_rejects_special_characters(self):
        ok, _msg = ProfileManager.validate_client_id("BAD-ID!")
        assert ok is False


class TestClientProfileCreation:
    def test_create_then_load_round_trips(self, profile_manager):
        profile_manager.create_client_profile("M", "My Client")
        config = profile_manager.load_shopify_config("M")
        assert config["client_id"] == "M"
        assert config["client_name"] == "My Client"
        assert config["inventory_memory"] == {
            "enabled": False,
            "skus": {},
            "names": {},
            "last_updated": None,
            "total_units": 0,
        }

    def test_duplicate_creation_returns_false_not_exception(self, profile_manager):
        profile_manager.create_client_profile("M", "First")
        result = profile_manager.create_client_profile("M", "Second")
        assert result is False

    def test_load_missing_client_returns_none(self, profile_manager):
        assert profile_manager.load_shopify_config("GHOST") is None
        assert profile_manager.load_client_config("GHOST") is None


class TestInventoryMemoryRoundTrip:
    def test_save_then_get_round_trips_values_as_float(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A1": 5, "B1": 3})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["skus"] == {"A1": 5.0, "B1": 3.0}

    def test_total_units_sums_only_positive_values(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A1": 5, "B1": -3, "C1": 0})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["total_units"] == 5

    def test_names_dict_round_trips(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory(
            "M", {"A1": 5}, names_dict={"A1": "Widget A1"}
        )
        mem = profile_manager.get_inventory_memory("M")
        assert mem["names"] == {"A1": "Widget A1"}

    def test_omitting_names_dict_preserves_previously_saved_names(
        self, profile_manager
    ):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory(
            "M", {"A1": 5}, names_dict={"A1": "Widget A1"}
        )
        # A later save that only has quantities (e.g. a run whose stock source
        # had no Product_Name column) must not wipe out the name already on file.
        profile_manager.save_inventory_memory("M", {"A1": 6})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["names"] == {"A1": "Widget A1"}
        assert mem["skus"] == {"A1": 6.0}

    def test_default_inventory_memory_schema_includes_names(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        mem = profile_manager.get_inventory_memory("M")
        assert mem["names"] == {}

    def test_loading_pre_upgrade_config_backfills_names_on_disk(self, profile_manager):
        # Simulates a real client directory saved before per-SKU name tracking
        # existed: inventory_memory is present but has no 'names' key.
        profile_manager.create_client_profile("M", "Client")
        config_path = profile_manager.get_client_directory("M") / "shopify_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["inventory_memory"] = {
            "enabled": False,
            "skus": {"A1": 5.0},
            "last_updated": None,
            "total_units": 5,
        }
        config_path.write_text(json.dumps(config), encoding="utf-8")

        loaded = profile_manager.load_shopify_config("M")
        assert loaded["inventory_memory"]["names"] == {}
        assert loaded["inventory_memory"]["skus"] == {"A1": 5.0}

        # Backfill must have been persisted, not just patched in memory.
        on_disk = json.loads(config_path.read_text(encoding="utf-8"))
        assert on_disk["inventory_memory"]["names"] == {}

    def test_missing_client_memory_returns_empty_dict(self, profile_manager):
        assert profile_manager.get_inventory_memory("GHOST") == {}

    # --- Confirmed bugs ---

    def test_float_sku_key_is_normalized_like_everywhere_else(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {5170.0: 12})
        mem = profile_manager.get_inventory_memory("M")
        assert "5170" in mem["skus"]

    def test_saving_empty_stock_dict_does_not_erase_previous_snapshot(
        self, profile_manager
    ):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A1": 5, "B1": 3})
        profile_manager.save_inventory_memory("M", {})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["skus"] == {"A1": 5.0, "B1": 3.0}


class TestListClientsBug:
    def test_client_id_containing_client_substring_round_trips(self, profile_manager):
        profile_manager.create_client_profile("ACLIENT_B", "Test")
        listed = profile_manager.list_clients()
        assert "ACLIENT_B" in listed
        assert profile_manager.client_exists(listed[0]) is True


class TestColumnMappingsMigrationBug:
    def test_unversioned_custom_mapping_is_not_silently_replaced(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        config = profile_manager.load_shopify_config("M")
        config["column_mappings"] = {
            "orders": {"MyCol": "SKU"},
            "stock": {"X": "Stock"},
        }
        profile_manager.save_shopify_config("M", config)

        reloaded = profile_manager.load_shopify_config("M")
        assert reloaded["column_mappings"]["orders"] == {"MyCol": "SKU"}


class TestLoadClientConfigCaching:
    def test_second_load_is_served_from_cache(self, profile_manager, monkeypatch):
        profile_manager.create_client_profile("M", "Client")
        first = profile_manager.load_client_config("M")
        call_count = {"n": 0}
        original_open = open

        def counting_open(*args, **kwargs):
            if "client_config.json" in str(args[0]):
                call_count["n"] += 1
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", counting_open)
        second = profile_manager.load_client_config("M")
        assert second == first
        assert call_count["n"] == 0  # served from cache, file not reopened

    def test_cache_invalidated_after_save(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        config = profile_manager.load_client_config("M")
        config["client_name"] = "Renamed"
        profile_manager.save_client_config("M", config)
        reloaded = profile_manager.load_client_config("M")
        assert reloaded["client_name"] == "Renamed"

    def test_cache_reflects_external_mtime_change(self, profile_manager):
        # Simulates another PC on the file server saving a change: same
        # mtime-based invalidation load_shopify_config already relies on.
        profile_manager.create_client_profile("M", "Client")
        profile_manager.load_client_config("M")  # warm the cache
        config_path = profile_manager.get_client_directory("M") / "client_config.json"
        data = json.loads(config_path.read_text())
        data["client_name"] = "Changed Externally"
        config_path.write_text(json.dumps(data))
        import os

        # Ensure a distinct mtime on filesystems with coarse mtime resolution.
        newer = os.path.getmtime(config_path) + 1
        os.utime(config_path, (newer, newer))
        reloaded = profile_manager.load_client_config("M")
        assert reloaded["client_name"] == "Changed Externally"

    def test_mutating_returned_config_does_not_corrupt_cache(self, profile_manager):
        # ui_settings is a nested dict; a shallow cache copy would share it
        # across calls, so mutating one caller's copy would corrupt the next.
        profile_manager.create_client_profile("M", "Client")
        first = profile_manager.load_client_config("M")
        first["ui_settings"]["is_pinned"] = True

        second = profile_manager.load_client_config("M")
        assert second["ui_settings"]["is_pinned"] is False


class TestLoadShopifyConfigCaching:
    def test_mutating_returned_config_does_not_corrupt_cache(self, profile_manager):
        # Same shallow-copy-cache hazard as load_client_config(), on the
        # nested inventory_memory dict.
        profile_manager.create_client_profile("M", "Client")
        first = profile_manager.load_shopify_config("M")
        first["inventory_memory"]["enabled"] = True

        second = profile_manager.load_shopify_config("M")
        assert second["inventory_memory"]["enabled"] is False

    def test_shopify_config_is_cached_after_a_migration(
        self, profile_manager, monkeypatch
    ):
        """A migrating load must leave the cache warm, like load_client_config does."""
        profile_manager.create_client_profile("M", "Client")
        config_path = profile_manager.get_client_directory("M") / "shopify_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        del config[
            "weight_config"
        ]  # stale key -- forces migrate_add_weight_config to fire
        config_path.write_text(json.dumps(config), encoding="utf-8")

        profile_manager.load_shopify_config("M")  # runs migrations, caches (or not)

        reads = []
        real_open = open

        def counting_open(path, *a, **k):
            if str(path).endswith("shopify_config.json"):
                reads.append(path)
            return real_open(path, *a, **k)

        monkeypatch.setattr("builtins.open", counting_open)
        profile_manager.load_shopify_config("M")
        assert reads == [], "second load re-read the file instead of using the cache"


class TestSaveIsAtomic:
    def test_save_shopify_config_is_atomic_and_leaves_no_temp(self, profile_manager):
        """A shorter document must fully replace a longer one, with no .tmp left behind."""
        profile_manager.create_client_profile("ALMA", "Alma")

        big = profile_manager.load_shopify_config("ALMA")
        big["filler"] = ["x"] * 500
        assert profile_manager.save_shopify_config("ALMA", big) is True

        small = profile_manager.load_shopify_config("ALMA")
        del small["filler"]
        assert profile_manager.save_shopify_config("ALMA", small) is True

        config_path = (
            profile_manager.get_client_directory("ALMA") / "shopify_config.json"
        )
        reloaded = json.loads(config_path.read_text(encoding="utf-8"))
        assert "filler" not in reloaded  # no surviving tail from the longer write
        assert list(config_path.parent.glob("*.tmp")) == []

    def test_save_shopify_config_has_no_fixed_temp_name(self):
        import inspect

        from shopify_tool.profile_manager import ProfileManager

        src = inspect.getsource(ProfileManager)
        assert 'with_suffix(".tmp")' not in src
        assert "msvcrt" not in src
        assert "shutil.move" not in src


class TestMigrationThatCannotSave:
    """AUDIT-07-M7: a locked file on the share must not hide a readable config."""

    def test_a_failed_migration_save_is_retried_on_the_next_load(
        self, profile_manager, monkeypatch
    ):
        profile_manager.create_client_profile("M", "Client")
        config_path = profile_manager.get_client_directory("M") / "shopify_config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        del data["weight_config"]  # an older file: migrate_add_weight_config fires
        config_path.write_text(json.dumps(data), encoding="utf-8")
        ProfileManager._config_cache.clear()

        def locked_by_another_pc(path, *_args, **_kwargs):
            raise PermissionError(13, "being used by another process", str(path))

        monkeypatch.setattr(
            "shopify_tool.profile_manager.atomic_write_json", locked_by_another_pc
        )
        first = profile_manager.load_shopify_config("M")
        assert "weight_config" in first  # migrated in memory
        assert "weight_config" not in json.loads(config_path.read_text(encoding="utf-8"))

        monkeypatch.undo()  # the other PC lets go
        profile_manager.load_shopify_config("M")

        assert "weight_config" in json.loads(config_path.read_text(encoding="utf-8"))


class TestUpdateShopifyConfig:
    """AUDIT-07-H1: one change saved over the config as it is on disk now."""

    def test_applies_one_change_over_the_config_on_disk(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.load_shopify_config("M")  # this PC, before PC-B
        other_pc = ProfileManager(base_path=str(profile_manager.base_path))
        fresh = other_pc.load_shopify_config("M")
        fresh["rules"] = [{"name": "from PC-B"}]
        other_pc.save_shopify_config("M", fresh)

        saved = profile_manager.update_shopify_config(
            "M", lambda cfg: cfg.update(analysis_mode="fifo")
        )

        on_disk = profile_manager.load_shopify_config("M")
        assert on_disk["analysis_mode"] == "fifo"
        assert on_disk["rules"] == [{"name": "from PC-B"}]
        assert saved["rules"] == [{"name": "from PC-B"}]

    def test_raises_for_a_missing_client(self, profile_manager):
        with pytest.raises(ProfileManagerError):
            profile_manager.update_shopify_config("NOPE", lambda cfg: None)


class TestConfigBackups:
    """Settings saves keep a backup; inventory-memory saves don't (AUDIT-07-M5)."""

    def test_a_settings_save_still_makes_a_backup(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        cfg = profile_manager.load_shopify_config("M")
        profile_manager.save_shopify_config("M", cfg)
        backups = list((profile_manager.clients_dir / "CLIENT_M" / "backups").glob("shopify_config_*.json"))
        assert len(backups) == 1

    def test_a_memory_save_makes_no_backup(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A": 1}, session="S")
        assert list((profile_manager.clients_dir / "CLIENT_M" / "backups").glob("shopify_config_*.json")) == []
