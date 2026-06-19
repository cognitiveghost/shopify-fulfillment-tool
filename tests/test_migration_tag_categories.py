"""Tests for tag_categories v1 to v2 migration."""

import json
import tempfile
import pytest
from pathlib import Path
from shopify_tool.db_manager import get_db
from shopify_tool.profile_manager import ProfileManager


# ============================================================================
# Fixtures
# ============================================================================


def _wipe_test_clients():
    db = get_db()
    try:
        db.execute("DELETE FROM sessions WHERE client_id IN ('TEST', 'MIGTEST')")
        db.execute("DELETE FROM clients WHERE client_id IN ('TEST', 'MIGTEST')")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clear_profile_manager_cache():
    """Clear class-level cache and DB test clients before each test."""
    ProfileManager._config_cache.clear()
    _wipe_test_clients()
    yield
    ProfileManager._config_cache.clear()
    _wipe_test_clients()


@pytest.fixture
def temp_profile_dir(tmp_path):
    """Create temporary profile directory structure."""
    profile_dir = tmp_path / "test_profile"
    profile_dir.mkdir()
    return profile_dir


@pytest.fixture
def profile_manager(temp_profile_dir):
    """Create ProfileManager instance with temp directory."""
    return ProfileManager(str(temp_profile_dir))


@pytest.fixture
def config_v1_basic():
    """Basic v1 format config."""
    return {
        "client_id": "TEST",
        "client_name": "Test Client",
        "tag_categories": {
            "packaging": {
                "label": "Packaging",
                "color": "#4CAF50",
                "tags": ["SMALL_BAG", "LARGE_BAG", "BOX"]
            },
            "priority": {
                "label": "Priority",
                "color": "#FF9800",
                "tags": ["URGENT", "HIGH_VALUE"]
            },
            "custom": {
                "label": "Custom",
                "color": "#9E9E9E",
                "tags": []
            }
        }
    }


@pytest.fixture
def config_v1_with_custom_category():
    """V1 format with custom user category."""
    return {
        "client_id": "TEST",
        "client_name": "Test Client",
        "tag_categories": {
            "packaging": {
                "label": "Packaging",
                "color": "#4CAF50",
                "tags": ["BOX"]
            },
            "my_custom_category": {
                "label": "My Custom Tags",
                "color": "#FF0000",
                "tags": ["CUSTOM_TAG_1", "CUSTOM_TAG_2"]
            }
        }
    }


@pytest.fixture
def config_v2_expected():
    """Expected v2 format after migration."""
    return {
        "client_id": "TEST",
        "client_name": "Test Client",
        "tag_categories": {
            "version": 2,
            "categories": {
                "packaging": {
                    "label": "Packaging",
                    "color": "#4CAF50",
                    "order": 1,
                    "tags": ["SMALL_BAG", "LARGE_BAG", "BOX"],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                },
                "priority": {
                    "label": "Priority",
                    "color": "#FF9800",
                    "order": 2,
                    "tags": ["URGENT", "HIGH_VALUE"],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                },
                "custom": {
                    "label": "Custom",
                    "color": "#9E9E9E",
                    "order": 3,
                    "tags": [],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                },
                # New categories added during migration
                "order_type": {
                    "label": "Тип замовлення",
                    "color": "#9C27B0",
                    "order": 4,
                    "tags": ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                },
                "accessories": {
                    "label": "Додатки",
                    "color": "#E91E63",
                    "order": 5,
                    "tags": ["STICKER", "BUSINESS_CARD", "GIFT_BOX"],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                },
                "delivery": {
                    "label": "Кур'єр/Доставка",
                    "color": "#FF5722",
                    "order": 6,
                    "tags": ["NOVA_POSHTA", "UKRPOSHTA", "SELF_PICKUP"],
                    "sku_writeoff": {
                        "enabled": False,
                        "mappings": {}
                    }
                }
            }
        }
    }


# ============================================================================
# Migration Tests
# ============================================================================


def test_migrate_tag_categories_v1_to_v2_basic(profile_manager, config_v1_basic):
    """Test basic v1 to v2 migration."""
    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_basic)

    assert result is True  # Migration occurred
    assert "version" in config_v1_basic["tag_categories"]
    assert config_v1_basic["tag_categories"]["version"] == 2
    assert "categories" in config_v1_basic["tag_categories"]

    categories = config_v1_basic["tag_categories"]["categories"]

    # Check existing categories migrated
    assert "packaging" in categories
    assert categories["packaging"]["label"] == "Packaging"
    assert categories["packaging"]["color"] == "#4CAF50"
    assert categories["packaging"]["tags"] == ["SMALL_BAG", "LARGE_BAG", "BOX"]
    assert "order" in categories["packaging"]
    assert "sku_writeoff" in categories["packaging"]

    # Check new categories added
    assert "order_type" in categories
    assert "accessories" in categories
    assert "delivery" in categories


def test_migrate_tag_categories_v1_to_v2_already_migrated(profile_manager, config_v2_expected):
    """Test that v2 config is not migrated again."""
    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v2_expected)

    assert result is False  # No migration needed
    # Config should remain unchanged
    assert config_v2_expected["tag_categories"]["version"] == 2


def test_migrate_tag_categories_v1_to_v2_preserves_custom_categories(
    profile_manager, config_v1_with_custom_category
):
    """Test that custom user categories are preserved during migration."""
    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_with_custom_category)

    assert result is True
    categories = config_v1_with_custom_category["tag_categories"]["categories"]

    # Check custom category preserved
    assert "my_custom_category" in categories
    assert categories["my_custom_category"]["label"] == "My Custom Tags"
    assert categories["my_custom_category"]["color"] == "#FF0000"
    assert categories["my_custom_category"]["tags"] == ["CUSTOM_TAG_1", "CUSTOM_TAG_2"]
    assert "order" in categories["my_custom_category"]
    assert "sku_writeoff" in categories["my_custom_category"]


def test_migrate_tag_categories_v1_to_v2_empty_config(profile_manager):
    """Test migration with empty tag_categories."""
    config = {"client_id": "TEST", "tag_categories": {}}

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is False  # Nothing to migrate


def test_migrate_tag_categories_v1_to_v2_missing_tag_categories(profile_manager):
    """Test migration when tag_categories key missing."""
    config = {"client_id": "TEST"}

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is False


def test_migrate_tag_categories_v1_to_v2_adds_sku_writeoff(profile_manager, config_v1_basic):
    """Test that sku_writeoff structure is added to all categories."""
    profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_basic)

    categories = config_v1_basic["tag_categories"]["categories"]

    for category_id, category in categories.items():
        assert "sku_writeoff" in category
        assert "enabled" in category["sku_writeoff"]
        assert "mappings" in category["sku_writeoff"]
        assert category["sku_writeoff"]["enabled"] is False
        assert category["sku_writeoff"]["mappings"] == {}


def test_migrate_tag_categories_v1_to_v2_order_is_set(profile_manager, config_v1_basic):
    """Test that order field is set for all categories."""
    profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_basic)

    categories = config_v1_basic["tag_categories"]["categories"]

    # Check that all categories have order
    for category in categories.values():
        assert "order" in category
        assert isinstance(category["order"], int)
        assert category["order"] > 0

    # Check known categories have expected order
    assert categories["packaging"]["order"] == 1
    assert categories["priority"]["order"] == 2
    assert categories.get("custom", {}).get("order") == 3


# ============================================================================
# Integration Tests (Full Load/Save Cycle)
# ============================================================================


def test_load_shopify_config_returns_v2(profile_manager):
    """Test that load_shopify_config returns v2 tag_categories from DB."""
    profile_manager.create_client_profile("TEST", "Test Client")

    loaded_config = profile_manager.load_shopify_config("TEST")

    assert loaded_config is not None
    assert "tag_categories" in loaded_config
    assert loaded_config["tag_categories"]["version"] == 2
    assert "categories" in loaded_config["tag_categories"]


def test_create_default_shopify_config_uses_v2(profile_manager):
    """Test that new configs are created with v2 format."""
    config = ProfileManager._create_default_shopify_config("TEST", "Test Client")

    assert "tag_categories" in config
    assert config["tag_categories"]["version"] == 2
    assert "categories" in config["tag_categories"]

    categories = config["tag_categories"]["categories"]

    # Check all default categories present
    assert "packaging" in categories
    assert "priority" in categories
    assert "status" in categories
    assert "order_type" in categories
    assert "accessories" in categories
    assert "delivery" in categories
    assert "custom" in categories

    # Check all have required v2 fields
    for category in categories.values():
        assert "label" in category
        assert "color" in category
        assert "tags" in category
        assert "order" in category
        assert "sku_writeoff" in category


def test_migrate_add_tag_categories_creates_v2(profile_manager):
    """Test that _migrate_add_tag_categories creates v2 format when adding missing tag_categories."""
    config = {"client_id": "TEST", "client_name": "Test Client"}

    result = profile_manager._migrate_add_tag_categories("TEST", config)

    assert result is True
    assert "tag_categories" in config
    assert config["tag_categories"]["version"] == 2
    assert "categories" in config["tag_categories"]


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


def test_backward_compatibility_existing_tags_still_work(profile_manager, config_v1_basic):
    """Test that existing Internal_Tags data still works after migration."""
    from shopify_tool.tag_manager import parse_tags, get_tag_category, _normalize_tag_categories

    # Existing DataFrame with Internal_Tags (unchanged format)
    internal_tags_json = '["BOX", "URGENT"]'
    tags = parse_tags(internal_tags_json)

    assert tags == ["BOX", "URGENT"]

    # Migrate config
    profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_basic)

    # Tags should still resolve to categories (using normalized categories)
    categories = _normalize_tag_categories(config_v1_basic["tag_categories"])

    category_box = get_tag_category("BOX", categories)
    category_urgent = get_tag_category("URGENT", categories)

    assert category_box == "packaging"
    assert category_urgent == "priority"


def test_backward_compatibility_with_pickle_sessions(profile_manager, config_v1_basic):
    """Test that migrated configs work with old pickle sessions."""
    import pickle
    import pandas as pd

    # Simulate DataFrame from old pickle session
    df = pd.DataFrame({
        "Order_Number": ["ORD001", "ORD002"],
        "SKU": ["SKU1", "SKU2"],
        "Internal_Tags": ['["BOX"]', '["URGENT", "CHECKED"]']
    })

    # Migrate config
    profile_manager._migrate_tag_categories_v1_to_v2("TEST", config_v1_basic)

    # DataFrame Internal_Tags format unchanged
    assert df.loc[0, "Internal_Tags"] == '["BOX"]'
    assert df.loc[1, "Internal_Tags"] == '["URGENT", "CHECKED"]'

    # Can still parse tags
    from shopify_tool.tag_manager import parse_tags

    tags = parse_tags(df.loc[0, "Internal_Tags"])
    assert tags == ["BOX"]


# ============================================================================
# Edge Cases
# ============================================================================


def test_migration_handles_missing_label(profile_manager):
    """Test migration when category missing label field."""
    config = {
        "client_id": "TEST",
        "tag_categories": {
            "test_category": {
                # Missing label
                "color": "#000000",
                "tags": ["TAG1"]
            }
        }
    }

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is True
    categories = config["tag_categories"]["categories"]

    # Should use category_id as fallback label
    assert categories["test_category"]["label"] == "Test_Category"


def test_migration_handles_missing_color(profile_manager):
    """Test migration when category missing color field."""
    config = {
        "client_id": "TEST",
        "tag_categories": {
            "test_category": {
                "label": "Test",
                # Missing color
                "tags": ["TAG1"]
            }
        }
    }

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is True
    categories = config["tag_categories"]["categories"]

    # Should use default gray color
    assert categories["test_category"]["color"] == "#9E9E9E"


def test_migration_handles_missing_tags(profile_manager):
    """Test migration when category missing tags field."""
    config = {
        "client_id": "TEST",
        "tag_categories": {
            "test_category": {
                "label": "Test",
                "color": "#000000"
                # Missing tags
            }
        }
    }

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is True
    categories = config["tag_categories"]["categories"]

    # Should default to empty list
    assert categories["test_category"]["tags"] == []


def test_migration_skips_non_dict_categories(profile_manager):
    """Test migration skips categories that are not dicts."""
    config = {
        "client_id": "TEST",
        "tag_categories": {
            "valid_category": {
                "label": "Valid",
                "color": "#000000",
                "tags": []
            },
            "invalid_category": "not a dict"  # Invalid
        }
    }

    result = profile_manager._migrate_tag_categories_v1_to_v2("TEST", config)

    assert result is True
    categories = config["tag_categories"]["categories"]

    # Valid category migrated
    assert "valid_category" in categories

    # Invalid category skipped
    assert "invalid_category" not in categories
