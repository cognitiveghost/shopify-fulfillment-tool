"""Unit tests for ProfileManager.

Tests cover:
- Client ID validation
- Client profile creation
- Configuration loading and saving
- Caching mechanism
- File locking
- Network error handling
- Backup creation
"""

import json
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shopify_tool.profile_manager import (
    NetworkError,
    ProfileManager,
    ProfileManagerError,
    ValidationError,
)


@pytest.fixture
def temp_base_path():
    """Create temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_base_path):
    """Create ProfileManager instance for testing."""
    return ProfileManager(str(temp_base_path))


class TestClientIDValidation:
    """Test client ID validation."""

    def test_valid_client_id(self):
        """Test validation of valid client IDs."""
        valid_ids = ["M", "A", "ABC", "TEST_123", "CLIENT123"]

        for client_id in valid_ids:
            is_valid, error = ProfileManager.validate_client_id(client_id)
            assert is_valid, f"{client_id} should be valid, got error: {error}"
            assert error == ""

    def test_empty_client_id(self):
        """Test validation of empty client ID."""
        is_valid, error = ProfileManager.validate_client_id("")
        assert not is_valid
        assert "cannot be empty" in error

    def test_too_long_client_id(self):
        """Test validation of too long client ID."""
        long_id = "A" * 21
        is_valid, error = ProfileManager.validate_client_id(long_id)
        assert not is_valid
        assert "too long" in error

    def test_invalid_characters(self):
        """Test validation of client IDs with invalid characters."""
        invalid_ids = ["test-client", "test.client", "test client", "тест"]

        for client_id in invalid_ids:
            is_valid, error = ProfileManager.validate_client_id(client_id)
            assert not is_valid, f"{client_id} should be invalid"
            assert "only contain" in error

    def test_client_prefix_included(self):
        """Test validation when CLIENT_ prefix is included."""
        is_valid, error = ProfileManager.validate_client_id("CLIENT_M")
        assert not is_valid
        assert "prefix" in error

    def test_reserved_names(self):
        """Test validation of Windows reserved names."""
        reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]

        for name in reserved:
            is_valid, error = ProfileManager.validate_client_id(name)
            assert not is_valid
            assert "reserved" in error


class TestNetworkConnection:
    """Test network connectivity testing."""

    def test_connection_success(self, temp_base_path):
        """Test successful connection."""
        manager = ProfileManager(str(temp_base_path))
        assert manager.is_network_available

    def test_connection_failure(self):
        """Test connection failure with invalid path."""
        # Mock Path.mkdir to raise PermissionError
        with patch('pathlib.Path.mkdir', side_effect=PermissionError("Access denied")):
            with pytest.raises(NetworkError) as exc_info:
                ProfileManager("/invalid/path")

            assert "Cannot connect" in str(exc_info.value)

    def test_base_path_created(self, temp_base_path):
        """Test that base directories are created."""
        # Remove existing dirs to test creation
        if temp_base_path.exists():
            shutil.rmtree(temp_base_path)

        manager = ProfileManager(str(temp_base_path))

        assert manager.clients_dir.exists()
        assert manager.sessions_dir.exists()
        assert manager.stats_dir.exists()
        assert manager.logs_dir.exists()


class TestClientManagement:
    """Test client profile management."""

    def test_list_clients_empty(self, profile_manager):
        """Test listing clients when none exist."""
        clients = profile_manager.list_clients()
        assert clients == []

    def test_create_client_profile(self, profile_manager):
        """Test creating a new client profile."""
        result = profile_manager.create_client_profile("M", "M Cosmetics")

        assert result is True
        assert profile_manager.client_exists("M")

        # Check directory structure
        client_dir = profile_manager.get_client_directory("M")
        assert (client_dir / "client_config.json").exists()
        assert (client_dir / "shopify_config.json").exists()
        assert (client_dir / "backups").exists()

    def test_create_duplicate_client(self, profile_manager):
        """Test creating duplicate client returns False."""
        profile_manager.create_client_profile("M", "M Cosmetics")
        result = profile_manager.create_client_profile("M", "M Cosmetics Again")

        assert result is False

    def test_create_client_invalid_id(self, profile_manager):
        """Test creating client with invalid ID raises ValidationError."""
        with pytest.raises(ValidationError):
            profile_manager.create_client_profile("invalid-id", "Test Client")

    def test_list_clients_after_creation(self, profile_manager):
        """Test listing clients after creating some."""
        profile_manager.create_client_profile("M", "M Cosmetics")
        profile_manager.create_client_profile("A", "A Company")
        profile_manager.create_client_profile("B", "B Store")

        clients = profile_manager.list_clients()
        assert sorted(clients) == ["A", "B", "M"]

    def test_client_exists(self, profile_manager):
        """Test checking if client exists."""
        assert not profile_manager.client_exists("M")

        profile_manager.create_client_profile("M", "M Cosmetics")

        assert profile_manager.client_exists("M")
        assert profile_manager.client_exists("m")  # Case insensitive


class TestConfigurationManagement:
    """Test configuration loading and saving."""

    def test_load_client_config(self, profile_manager):
        """Test loading general client config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_client_config("M")

        assert config is not None
        assert config["client_id"] == "M"
        assert config["client_name"] == "M Cosmetics"
        assert "created_at" in config

    def test_load_shopify_config(self, profile_manager):
        """Test loading Shopify config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_shopify_config("M")

        assert config is not None
        assert config["client_id"] == "M"
        assert "column_mappings" in config
        assert "courier_mappings" in config
        assert "settings" in config

    def test_load_nonexistent_config(self, profile_manager):
        """Test loading config for nonexistent client."""
        config = profile_manager.load_shopify_config("NONEXISTENT")
        assert config is None

    def test_save_shopify_config(self, profile_manager):
        """Test saving Shopify config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Load and modify
        config = profile_manager.load_shopify_config("M")
        config["settings"]["low_stock_threshold"] = 10

        # Save
        result = profile_manager.save_shopify_config("M", config)
        assert result is True

        # Verify changes
        reloaded = profile_manager.load_shopify_config("M")
        assert reloaded["settings"]["low_stock_threshold"] == 10
        assert "last_updated" in reloaded

    def test_save_config_nonexistent_client(self, profile_manager):
        """Test saving config for nonexistent client raises error."""
        config = {"test": "data"}

        with pytest.raises(ProfileManagerError):
            profile_manager.save_shopify_config("NONEXISTENT", config)


class TestCaching:
    """Test configuration caching mechanism."""

    def test_config_cached(self, profile_manager):
        """Test that config is cached after first load."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # First load
        config1 = profile_manager.load_shopify_config("M")

        # Second load (should be from cache)
        config2 = profile_manager.load_shopify_config("M")

        assert config1 is config2  # Same object reference

    def test_cache_invalidation_after_save(self, profile_manager):
        """Test that cache is invalidated after save."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Load to cache
        config1 = profile_manager.load_shopify_config("M")

        # Modify and save
        config1["settings"]["low_stock_threshold"] = 10
        profile_manager.save_shopify_config("M", config1)

        # Load again (should be fresh from disk)
        config2 = profile_manager.load_shopify_config("M")

        assert config1 is not config2  # Different object reference
        assert config2["settings"]["low_stock_threshold"] == 10

    def test_cache_invalidation_by_mtime(self, profile_manager):
        """Test that cache is invalidated when file mtime changes (mtime-based cache)."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # First load — populates cache
        config1 = profile_manager.load_shopify_config("M")

        # Advance mtime by touching the file
        config_path = profile_manager.clients_dir / "CLIENT_M" / "shopify_config.json"
        current_mtime = config_path.stat().st_mtime
        import os
        os.utime(config_path, (current_mtime + 1, current_mtime + 1))

        # Second load — mtime changed, should re-read from disk
        config2 = profile_manager.load_shopify_config("M")

        # Different objects because cache was invalidated
        assert config1 is not config2


class TestBackups:
    """Test backup creation."""

    def test_backup_created_on_save(self, profile_manager):
        """Test that backup is created when saving config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Load and modify
        config = profile_manager.load_shopify_config("M")
        config["settings"]["low_stock_threshold"] = 10

        # Save (should create backup)
        profile_manager.save_shopify_config("M", config)

        # Check backup exists
        backup_dir = profile_manager.get_client_directory("M") / "backups"
        backups = list(backup_dir.glob("shopify_config_*.json"))

        assert len(backups) == 1

    def test_backup_limit(self, profile_manager):
        """Test that only last 10 backups are kept."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Create 15 backups by saving multiple times
        for i in range(15):
            config = profile_manager.load_shopify_config("M")
            config["test_value"] = i
            profile_manager.save_shopify_config("M", config)
            time.sleep(0.1)  # Ensure different timestamps

        # Check that at most 10 backups remain (first save creates backup)
        backup_dir = profile_manager.get_client_directory("M") / "backups"
        backups = list(backup_dir.glob("shopify_config_*.json"))

        # Should be 10 or less (first save doesn't create backup)
        assert len(backups) <= 10


class TestDefaultConfiguration:
    """Test default configuration structure."""

    def test_default_shopify_config_structure(self, profile_manager):
        """Test that default config has required structure."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_shopify_config("M")

        # Check required sections
        required_sections = [
            "client_id",
            "client_name",
            "created_at",
            "column_mappings",
            "courier_mappings",
            "settings",
            "rules",
            "order_rules",
            "packing_list_configs",
            "stock_export_configs",
            "set_decoders",
            "packaging_rules"
        ]

        for section in required_sections:
            assert section in config, f"Missing section: {section}"

    def test_default_column_mappings(self, profile_manager):
        """Test default column mappings (v2 format)."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_shopify_config("M")
        mappings = config["column_mappings"]

        # Check v2 format
        assert "version" in mappings
        assert mappings["version"] == 2
        assert "orders" in mappings
        assert "stock" in mappings

        # Check mappings structure (CSV name -> Internal name)
        orders_mappings = mappings["orders"]
        assert "Name" in orders_mappings
        assert orders_mappings["Name"] == "Order_Number"
        assert "Lineitem sku" in orders_mappings
        assert orders_mappings["Lineitem sku"] == "SKU"

        stock_mappings = mappings["stock"]
        assert "Артикул" in stock_mappings
        assert stock_mappings["Артикул"] == "SKU"
        assert "Наличност" in stock_mappings
        assert stock_mappings["Наличност"] == "Stock"

    def test_default_courier_mappings(self, profile_manager):
        """Test default courier mappings."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_shopify_config("M")
        couriers = config["courier_mappings"]

        # Check default couriers
        assert "DHL" in couriers
        assert "DPD" in couriers
        assert "Speedy" in couriers

        # Check structure
        assert "patterns" in couriers["DHL"]
        assert "case_sensitive" in couriers["DHL"]


class TestPathGetters:
    """Test path getter methods."""

    def test_get_clients_root(self, profile_manager, temp_base_path):
        """Test getting clients root path."""
        path = profile_manager.get_clients_root()
        assert path == temp_base_path / "Clients"

    def test_get_sessions_root(self, profile_manager, temp_base_path):
        """Test getting sessions root path."""
        path = profile_manager.get_sessions_root()
        assert path == temp_base_path / "Sessions"

    def test_get_stats_path(self, profile_manager, temp_base_path):
        """Test getting stats path."""
        path = profile_manager.get_stats_path()
        assert path == temp_base_path / "Stats"

    def test_get_logs_path(self, profile_manager, temp_base_path):
        """Test getting logs path."""
        path = profile_manager.get_logs_path()
        assert path == temp_base_path / "Logs" / "shopify_tool"

    def test_get_client_directory(self, profile_manager):
        """Test getting client directory."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        client_dir = profile_manager.get_client_directory("M")
        assert client_dir.name == "CLIENT_M"
        assert client_dir.exists()


class TestCaseInsensitivity:
    """Test that client IDs are case-insensitive."""

    def test_create_and_load_mixed_case(self, profile_manager):
        """Test creating with lowercase and loading with uppercase."""
        # Create with lowercase
        profile_manager.create_client_profile("m", "M Cosmetics")

        # Load with uppercase
        config = profile_manager.load_shopify_config("M")
        assert config is not None
        assert config["client_id"] == "M"

    def test_save_mixed_case(self, profile_manager):
        """Test saving with different case."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Load with lowercase
        config = profile_manager.load_shopify_config("m")
        config["settings"]["low_stock_threshold"] = 10

        # Save with lowercase
        result = profile_manager.save_shopify_config("m", config)
        assert result is True

        # Verify with uppercase
        reloaded = profile_manager.load_shopify_config("M")
        assert reloaded["settings"]["low_stock_threshold"] == 10


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_json_in_config(self, profile_manager):
        """Test handling of corrupted JSON config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Clear cache to force reload
        profile_manager._config_cache.clear()

        # Corrupt the config file
        config_path = (
            profile_manager.get_client_directory("M") / "shopify_config.json"
        )
        with open(config_path, 'w') as f:
            f.write("invalid json {{{")

        # Should return None and log error
        config = profile_manager.load_shopify_config("M")
        assert config is None

    def test_permission_error_handling(self, profile_manager):
        """Test handling of permission errors."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Clear cache to force reload
        profile_manager._config_cache.clear()

        config_path = (
            profile_manager.get_client_directory("M") / "shopify_config.json"
        )

        # Mock permission error on file open
        original_open = open
        def selective_open(*args, **kwargs):
            # Only raise error for our specific config file
            if len(args) > 0 and "shopify_config.json" in str(args[0]):
                raise PermissionError("Access denied")
            return original_open(*args, **kwargs)

        with patch('builtins.open', side_effect=selective_open):
            config = profile_manager.load_shopify_config("M")
            assert config is None


class TestSetDecoderMethods:
    """Test set/bundle decoder management methods."""

    def test_get_set_decoders_empty(self, profile_manager):
        """Test getting set decoders from fresh config returns empty dict."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        set_decoders = profile_manager.get_set_decoders("M")

        assert isinstance(set_decoders, dict)
        assert len(set_decoders) == 0

    def test_save_and_get_set_decoders(self, profile_manager):
        """Test saving and retrieving set decoders."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Create test sets
        test_sets = {
            "SET-WINTER": [
                {"sku": "HAT-001", "quantity": 1},
                {"sku": "GLOVES-001", "quantity": 1}
            ],
            "SET-SUMMER": [
                {"sku": "SUNGLASSES-001", "quantity": 1}
            ]
        }

        # Save
        success = profile_manager.save_set_decoders("M", test_sets)
        assert success is True

        # Get
        loaded_sets = profile_manager.get_set_decoders("M")
        assert loaded_sets == test_sets
        assert len(loaded_sets) == 2
        assert "SET-WINTER" in loaded_sets
        assert len(loaded_sets["SET-WINTER"]) == 2

    def test_add_set_valid(self, profile_manager):
        """Test adding a valid set definition."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        components = [
            {"sku": "COMP-1", "quantity": 1},
            {"sku": "COMP-2", "quantity": 2},
            {"sku": "COMP-3", "quantity": 1}
        ]

        # Add set
        success = profile_manager.add_set("M", "NEW-SET", components)
        assert success is True

        # Verify saved
        sets = profile_manager.get_set_decoders("M")
        assert "NEW-SET" in sets
        assert len(sets["NEW-SET"]) == 3
        assert sets["NEW-SET"][0]["sku"] == "COMP-1"
        assert sets["NEW-SET"][1]["quantity"] == 2

    def test_add_set_update_existing(self, profile_manager):
        """Test updating an existing set."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Add initial set
        profile_manager.add_set("M", "TEST-SET", [{"sku": "OLD-COMP", "quantity": 1}])

        # Update same set with new components
        new_components = [
            {"sku": "NEW-COMP-1", "quantity": 2},
            {"sku": "NEW-COMP-2", "quantity": 3}
        ]
        success = profile_manager.add_set("M", "TEST-SET", new_components)
        assert success is True

        # Verify updated
        sets = profile_manager.get_set_decoders("M")
        assert "TEST-SET" in sets
        assert len(sets["TEST-SET"]) == 2
        assert sets["TEST-SET"][0]["sku"] == "NEW-COMP-1"

    def test_add_set_invalid_empty_components(self, profile_manager):
        """Test adding set with empty components list raises ValidationError."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Try to add set with empty components
        with pytest.raises(ValidationError) as exc_info:
            profile_manager.add_set("M", "BAD-SET", [])

        assert "non-empty list" in str(exc_info.value).lower()

    def test_add_set_invalid_component_missing_sku(self, profile_manager):
        """Test adding set with component missing SKU raises ValidationError."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Component without SKU
        components = [{"quantity": 1}]

        with pytest.raises(ValidationError) as exc_info:
            profile_manager.add_set("M", "BAD-SET", components)

        assert "sku" in str(exc_info.value).lower()

    def test_add_set_invalid_negative_quantity(self, profile_manager):
        """Test adding set with negative quantity raises ValidationError."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        components = [{"sku": "COMP-1", "quantity": -1}]

        with pytest.raises(ValidationError) as exc_info:
            profile_manager.add_set("M", "BAD-SET", components)

        assert "positive" in str(exc_info.value).lower()

    def test_add_set_invalid_non_integer_quantity(self, profile_manager):
        """Test adding set with non-integer quantity raises ValidationError."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        components = [{"sku": "COMP-1", "quantity": "abc"}]

        with pytest.raises(ValidationError) as exc_info:
            profile_manager.add_set("M", "BAD-SET", components)

        assert "integer" in str(exc_info.value).lower()

    def test_delete_set_exists(self, profile_manager):
        """Test deleting an existing set."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Add set
        profile_manager.add_set("M", "DELETE-ME", [{"sku": "COMP-1", "quantity": 1}])

        # Verify exists
        sets = profile_manager.get_set_decoders("M")
        assert "DELETE-ME" in sets

        # Delete
        success = profile_manager.delete_set("M", "DELETE-ME")
        assert success is True

        # Verify removed
        sets = profile_manager.get_set_decoders("M")
        assert "DELETE-ME" not in sets

    def test_delete_set_not_exists(self, profile_manager):
        """Test deleting non-existent set returns False."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Try to delete non-existent set
        success = profile_manager.delete_set("M", "NON-EXISTENT")
        assert success is False

    def test_set_decoders_persistence_across_loads(self, profile_manager):
        """Test that set decoders persist across multiple loads."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Add sets
        sets = {
            "SET-A": [{"sku": "COMP-A", "quantity": 1}],
            "SET-B": [{"sku": "COMP-B", "quantity": 2}]
        }
        profile_manager.save_set_decoders("M", sets)

        # Clear cache to force reload
        profile_manager._config_cache.clear()

        # Load again
        loaded_sets = profile_manager.get_set_decoders("M")
        assert loaded_sets == sets

    def test_multiple_sets_add_and_delete(self, profile_manager):
        """Test adding and deleting multiple sets in sequence."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Clear any existing sets to ensure clean state
        profile_manager.save_set_decoders("M", {})

        # Add multiple sets
        profile_manager.add_set("M", "SET-1", [{"sku": "C1", "quantity": 1}])
        profile_manager.add_set("M", "SET-2", [{"sku": "C2", "quantity": 1}])
        profile_manager.add_set("M", "SET-3", [{"sku": "C3", "quantity": 1}])

        sets = profile_manager.get_set_decoders("M")
        assert len(sets) == 3

        # Delete one
        profile_manager.delete_set("M", "SET-2")

        sets = profile_manager.get_set_decoders("M")
        assert len(sets) == 2
        assert "SET-1" in sets
        assert "SET-2" not in sets
        assert "SET-3" in sets


class TestUISettings:
    """Test UI settings management."""

    def test_update_ui_settings(self, profile_manager):
        """Test updating UI settings."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Update UI settings
        success = profile_manager.update_ui_settings("M", {
            "is_pinned": True,
            "group_id": "test-group-uuid",
            "custom_color": "#FF0000"
        })
        assert success

        # Verify settings were saved
        config = profile_manager.load_client_config("M")
        assert config["ui_settings"]["is_pinned"] is True
        assert config["ui_settings"]["group_id"] == "test-group-uuid"
        assert config["ui_settings"]["custom_color"] == "#FF0000"

    def test_update_ui_settings_partial(self, profile_manager):
        """Test partial update of UI settings."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Initial update
        profile_manager.update_ui_settings("M", {"is_pinned": True, "custom_color": "#FF0000"})

        # Partial update (only change is_pinned)
        profile_manager.update_ui_settings("M", {"is_pinned": False})

        # Verify only is_pinned changed, custom_color preserved
        config = profile_manager.load_client_config("M")
        assert config["ui_settings"]["is_pinned"] is False
        assert config["ui_settings"]["custom_color"] == "#FF0000"

    def test_get_ui_settings_defaults(self, profile_manager):
        """Test getting UI settings returns defaults if not set."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        ui_settings = profile_manager.get_ui_settings("M")

        # Verify defaults
        assert ui_settings["is_pinned"] is False
        assert ui_settings["group_id"] is None
        assert ui_settings["custom_color"] == "#4CAF50"
        assert ui_settings["custom_badges"] == []
        assert ui_settings["display_order"] == 0

    def test_get_ui_settings_nonexistent_client(self, profile_manager):
        """Test getting UI settings for non-existent client returns defaults."""
        ui_settings = profile_manager.get_ui_settings("NONEXISTENT")

        # Should return defaults, not raise error
        assert ui_settings["is_pinned"] is False
        assert ui_settings["group_id"] is None

    def test_update_ui_settings_nonexistent_client(self, profile_manager):
        """Test updating UI settings for non-existent client fails."""
        with pytest.raises(ProfileManagerError):
            profile_manager.update_ui_settings("NONEXISTENT", {"is_pinned": True})


class TestMetadata:
    """Test metadata calculation."""

    def test_calculate_metadata_no_sessions(self, profile_manager):
        """Test metadata calculation when client has no sessions."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        metadata = profile_manager.calculate_metadata("M")

        assert metadata["total_sessions"] == 0
        assert metadata["last_session_date"] is None
        assert "last_accessed" in metadata

    def test_calculate_metadata_with_sessions(self, profile_manager, temp_base_path):
        """Test metadata calculation with existing sessions."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Create mock session directories
        sessions_dir = temp_base_path / "Sessions" / "CLIENT_M"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Create session folders
        (sessions_dir / "2025-01-15_1").mkdir()
        (sessions_dir / "2025-01-20_1").mkdir()
        (sessions_dir / "2025-01-20_2").mkdir()

        metadata = profile_manager.calculate_metadata("M")

        assert metadata["total_sessions"] == 3
        assert metadata["last_session_date"] == "2025-01-20"

    def test_calculate_metadata_ignores_non_session_folders(self, profile_manager, temp_base_path):
        """Test that metadata calculation ignores non-session folders."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        sessions_dir = temp_base_path / "Sessions" / "CLIENT_M"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Create valid session
        (sessions_dir / "2025-01-15_1").mkdir()

        # Create invalid folders (should be ignored)
        (sessions_dir / "random_folder").mkdir()
        (sessions_dir / "not-a-session").mkdir()

        metadata = profile_manager.calculate_metadata("M")

        assert metadata["total_sessions"] == 1
        assert metadata["last_session_date"] == "2025-01-15"

    def test_update_last_accessed(self, profile_manager):
        """Test updating last_accessed timestamp."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Update last accessed
        success = profile_manager.update_last_accessed("M")
        assert success

        # Verify timestamp was set
        config = profile_manager.load_client_config("M")
        assert "metadata" in config
        assert "last_accessed" in config["metadata"]

        # Verify timestamp is recent (within last 5 seconds)
        from datetime import datetime
        last_accessed = datetime.fromisoformat(config["metadata"]["last_accessed"])
        now = datetime.now()
        diff_seconds = (now - last_accessed).total_seconds()
        assert diff_seconds < 5

    def test_update_last_accessed_nonexistent_client(self, profile_manager):
        """Test updating last_accessed for non-existent client fails gracefully."""
        success = profile_manager.update_last_accessed("NONEXISTENT")
        assert success is False


class TestMigration:
    """Test configuration migration."""

    def test_migration_adds_ui_settings(self, profile_manager, temp_base_path):
        """Test that migration adds ui_settings to old configs."""
        # Create client directory
        client_dir = temp_base_path / "Clients" / "CLIENT_M"
        client_dir.mkdir(parents=True, exist_ok=True)

        # Create old-format config (without ui_settings)
        old_config = {
            "client_id": "M",
            "client_name": "M Cosmetics",
            "created_at": "2025-01-01T00:00:00"
        }

        config_path = client_dir / "client_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(old_config, f)

        # Load config (should trigger migration)
        config = profile_manager.load_client_config("M")

        # Verify ui_settings was added
        assert "ui_settings" in config
        assert config["ui_settings"]["is_pinned"] is False
        assert config["ui_settings"]["group_id"] is None

        # Verify migration was saved
        with open(config_path, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        assert "ui_settings" in saved_config

    def test_migration_preserves_existing_data(self, profile_manager, temp_base_path):
        """Test that migration preserves existing fields."""
        client_dir = temp_base_path / "Clients" / "CLIENT_M"
        client_dir.mkdir(parents=True, exist_ok=True)

        # Create old-format config with custom fields
        old_config = {
            "client_id": "M",
            "client_name": "M Cosmetics",
            "created_at": "2025-01-01T00:00:00",
            "custom_field": "custom_value"
        }

        config_path = client_dir / "client_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(old_config, f)

        # Load config (triggers migration)
        config = profile_manager.load_client_config("M")

        # Verify existing fields preserved
        assert config["client_id"] == "M"
        assert config["client_name"] == "M Cosmetics"
        assert config["custom_field"] == "custom_value"
        # And ui_settings added
        assert "ui_settings" in config

    def test_migration_idempotent(self, profile_manager):
        """Test that migration is idempotent (safe to run multiple times)."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Load config multiple times
        config1 = profile_manager.load_client_config("M")
        config2 = profile_manager.load_client_config("M")
        config3 = profile_manager.load_client_config("M")

        # All should have ui_settings
        assert "ui_settings" in config1
        assert "ui_settings" in config2
        assert "ui_settings" in config3

        # Settings should be identical
        assert config1["ui_settings"] == config2["ui_settings"]
        assert config2["ui_settings"] == config3["ui_settings"]


class TestExtendedConfig:
    """Test extended configuration retrieval."""

    def test_get_client_config_extended(self, profile_manager):
        """Test getting extended config with metadata."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.get_client_config_extended("M")

        # Verify all sections present
        assert "client_id" in config
        assert "ui_settings" in config
        assert "metadata" in config

        # Verify metadata structure
        assert "total_sessions" in config["metadata"]
        assert "last_session_date" in config["metadata"]
        assert "last_accessed" in config["metadata"]

    def test_extended_config_includes_calculated_metadata(self, profile_manager, temp_base_path):
        """Test that extended config includes calculated metadata."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Create mock sessions
        sessions_dir = temp_base_path / "Sessions" / "CLIENT_M"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "2025-01-15_1").mkdir()
        (sessions_dir / "2025-01-20_1").mkdir()

        config = profile_manager.get_client_config_extended("M")

        # Verify metadata was calculated
        assert config["metadata"]["total_sessions"] == 2
        assert config["metadata"]["last_session_date"] == "2025-01-20"

    def test_extended_config_nonexistent_client(self, profile_manager):
        """Test getting extended config for non-existent client returns empty dict."""
        config = profile_manager.get_client_config_extended("NONEXISTENT")
        assert config == {}


class TestSaveClientConfig:
    """Test save_client_config method."""

    def test_save_client_config_success(self, profile_manager):
        """Test saving client config."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        # Modify config
        config = profile_manager.load_client_config("M")
        config["custom_field"] = "test_value"

        # Save
        success = profile_manager.save_client_config("M", config)
        assert success

        # Verify saved
        loaded_config = profile_manager.load_client_config("M")
        assert loaded_config["custom_field"] == "test_value"

    def test_save_client_config_adds_timestamps(self, profile_manager):
        """Test that save_client_config adds last_updated timestamp."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_client_config("M")

        # Save
        profile_manager.save_client_config("M", config)

        # Verify timestamps added
        loaded_config = profile_manager.load_client_config("M")
        assert "last_updated" in loaded_config
        assert "updated_by" in loaded_config

    def test_save_client_config_creates_backup(self, profile_manager, temp_base_path):
        """Test that save_client_config creates backup."""
        profile_manager.create_client_profile("M", "M Cosmetics")

        config = profile_manager.load_client_config("M")
        config["test_field"] = "test"

        # Save (should create backup)
        profile_manager.save_client_config("M", config)

        # Check backup exists
        backups_dir = temp_base_path / "Clients" / "CLIENT_M" / "backups"
        if backups_dir.exists():
            backups = list(backups_dir.glob("client_config_*.json"))
            assert len(backups) >= 1

    def test_save_client_config_nonexistent_client(self, profile_manager):
        """Test saving config for non-existent client fails."""
        with pytest.raises(ProfileManagerError) as exc_info:
            profile_manager.save_client_config("NONEXISTENT", {})

        assert "does not exist" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
