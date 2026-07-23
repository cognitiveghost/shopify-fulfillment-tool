"""Client/app configuration + inventory memory accuracy (priorities 5 & 6)."""
import json

import pytest

from shopify_tool.profile_manager import ProfileManager


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
            "enabled": False, "skus": {}, "names": {}, "last_updated": None, "total_units": 0,
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
        profile_manager.save_inventory_memory("M", {"A1": 5}, names_dict={"A1": "Widget A1"})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["names"] == {"A1": "Widget A1"}

    def test_omitting_names_dict_preserves_previously_saved_names(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A1": 5}, names_dict={"A1": "Widget A1"})
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
            "enabled": False, "skus": {"A1": 5.0}, "last_updated": None, "total_units": 5,
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

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: save_inventory_memory() casts SKU keys with plain str(k), "
               "never through csv_utils.normalize_sku() (used everywhere else in "
               "this codebase, e.g. core.py's history SKU normalization). A "
               "numeric/float SKU key is persisted as '5170.0' instead of "
               "'5170', so it will never match the normalize_sku()'d SKU that "
               "comes back from a real stock CSV on the next analysis run.",
    )
    def test_float_sku_key_is_normalized_like_everywhere_else(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {5170.0: 12})
        mem = profile_manager.get_inventory_memory("M")
        assert "5170" in mem["skus"]

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: save_inventory_memory() has no guard against an empty "
               "stock_dict -- calling it with {} (e.g. because every row's "
               "Final_Stock was NaN in a degenerate analysis run, see "
               "core.py:1100-1105) silently overwrites and permanently erases "
               "a previously-good inventory snapshot instead of being a no-op "
               "or requiring an explicit confirmation.",
    )
    def test_saving_empty_stock_dict_does_not_erase_previous_snapshot(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        profile_manager.save_inventory_memory("M", {"A1": 5, "B1": 3})
        profile_manager.save_inventory_memory("M", {})
        mem = profile_manager.get_inventory_memory("M")
        assert mem["skus"] == {"A1": 5.0, "B1": 3.0}


class TestListClientsBug:
    @pytest.mark.xfail(
        strict=True,
        reason="BUG: list_clients() strips the directory prefix with "
               "item.name.replace('CLIENT_', '') instead of a prefix-only "
               "strip. validate_client_id() only rejects IDs that START WITH "
               "'CLIENT_', so an id like 'ACLIENT_B' is legal, creates dir "
               "'CLIENT_ACLIENT_B', but list_clients() replaces BOTH "
               "occurrences of the substring and reports it as 'AB' -- a name "
               "that doesn't round-trip through client_exists()/"
               "get_client_directory() at all.",
    )
    def test_client_id_containing_client_substring_round_trips(self, profile_manager):
        profile_manager.create_client_profile("ACLIENT_B", "Test")
        listed = profile_manager.list_clients()
        assert "ACLIENT_B" in listed
        assert profile_manager.client_exists(listed[0]) is True


class TestColumnMappingsMigrationBug:
    @pytest.mark.xfail(
        strict=True,
        reason="BUG: _migrate_column_mappings_v1_to_v2 computes is_v1 to decide "
               "which log message to print, but then unconditionally overwrites "
               "config['column_mappings'] with the hardcoded default Shopify/"
               "Bulgarian template regardless of is_v1's value. Any real, valid "
               "user-authored column_mappings dict that simply lacks the "
               "'version' key (e.g. hand-edited, or written by an older code "
               "path) has its actual orders/stock mapping silently discarded "
               "and replaced by the wrong default on the very next config load.",
    )
    def test_unversioned_custom_mapping_is_not_silently_replaced(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        config = profile_manager.load_shopify_config("M")
        config["column_mappings"] = {"orders": {"MyCol": "SKU"}, "stock": {"X": "Stock"}}
        profile_manager.save_shopify_config("M", config)

        reloaded = profile_manager.load_shopify_config("M")
        assert reloaded["column_mappings"]["orders"] == {"MyCol": "SKU"}
