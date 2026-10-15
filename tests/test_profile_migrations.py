"""One-shot profile migrations (ADR 0009: delimiters move to Auto once)."""

import copy

import pytest

from shopify_tool.profile_migrations import (
    DEFAULT_TAG_CATEGORIES,
    migrate_add_inventory_memory,
    migrate_add_tag_categories,
    migrate_add_weight_config,
    migrate_column_mappings_v1_to_v2,
    migrate_delimiter_config_v1_to_v2,
    migrate_delimiters_to_auto,
    migrate_tag_categories_v1_to_v2,
    migrate_tag_category_labels_to_english,
)


def test_existing_delimiters_become_auto_once():
    config = {"settings": {"stock_csv_delimiter": ";", "orders_csv_delimiter": ","}}
    assert migrate_delimiters_to_auto("ACME", config) is True
    assert config["settings"]["stock_csv_delimiter"] == "auto"
    assert config["settings"]["orders_csv_delimiter"] == "auto"
    assert config["settings"]["delimiter_auto_migrated"] is True


def test_marker_protects_a_later_override():
    config = {
        "settings": {
            "stock_csv_delimiter": ";",
            "orders_csv_delimiter": "auto",
            "delimiter_auto_migrated": True,
        }
    }
    assert migrate_delimiters_to_auto("ACME", config) is False
    assert config["settings"]["stock_csv_delimiter"] == ";"


def test_a_config_without_settings_gets_them():
    config = {}
    assert migrate_delimiters_to_auto("ACME", config) is True
    assert config["settings"]["orders_csv_delimiter"] == "auto"



class TestColumnMappings:
    def test_v1_required_lists_become_the_default_v2_mappings(self):
        config = {"column_mappings": {"orders_required": ["Order_Number"], "stock_required": ["SKU"]}}
        assert migrate_column_mappings_v1_to_v2("ACME", config) is True
        mappings = config["column_mappings"]
        assert mappings["version"] == 2
        assert mappings["orders"]["Name"] == "Order_Number"
        assert mappings["stock"]["Наличност"] == "Stock"
        assert config["_migration_info"]["to_version"] == 2

    def test_a_v2_shape_without_a_version_keeps_its_own_mapping(self):
        config = {"column_mappings": {"orders": {"Order ID": "Order_Number"}, "stock": {"Code": "SKU"}}}
        assert migrate_column_mappings_v1_to_v2("ACME", config) is True
        assert config["column_mappings"]["orders"] == {"Order ID": "Order_Number"}
        assert config["column_mappings"]["version"] == 2

    def test_an_unknown_shape_gets_the_defaults(self):
        config = {"column_mappings": {"something": "else"}}
        assert migrate_column_mappings_v1_to_v2("ACME", config) is True
        assert "Name" in config["column_mappings"]["orders"]

    def test_already_v2_and_missing_are_left_alone(self):
        config = {"column_mappings": {"version": 2, "orders": {}, "stock": {}}}
        assert migrate_column_mappings_v1_to_v2("ACME", config) is False
        assert migrate_column_mappings_v1_to_v2("ACME", {}) is False


V1_TAG_CATEGORIES = {
    "packaging": {"label": "Box", "color": "#111111", "tags": ["BOX"]},
    "mine": {"label": "Mine", "tags": ["X"]},
}


class TestTagCategories:
    def test_add_creates_the_defaults_once(self):
        config = {}
        assert migrate_add_tag_categories("ACME", config) is True
        assert config["tag_categories"] == DEFAULT_TAG_CATEGORIES
        assert config["tag_categories"] is not DEFAULT_TAG_CATEGORIES  # a copy
        assert migrate_add_tag_categories("ACME", config) is False

    def test_v1_becomes_v2_keeping_tags_and_adding_the_new_defaults(self):
        config = {"tag_categories": copy.deepcopy(V1_TAG_CATEGORIES)}
        assert migrate_tag_categories_v1_to_v2("ACME", config) is True
        out = config["tag_categories"]
        assert out["version"] == 2
        cats = out["categories"]
        assert cats["packaging"]["tags"] == ["BOX"] and cats["packaging"]["color"] == "#111111"
        assert cats["packaging"]["sku_writeoff"] == {"enabled": False, "mappings": {}}
        assert cats["mine"]["label"] == "Mine" and cats["mine"]["color"] == "#9E9E9E"
        assert {"order_type", "accessories", "delivery"} <= set(cats)
        assert sorted(c["order"] for c in cats.values()) == list(range(1, len(cats) + 1))

    def test_the_v1_to_v2_migration_is_idempotent(self):
        config = {"tag_categories": copy.deepcopy(V1_TAG_CATEGORIES)}
        migrate_tag_categories_v1_to_v2("ACME", config)
        done = copy.deepcopy(config)
        assert migrate_tag_categories_v1_to_v2("ACME", config) is False
        assert config == done

    def test_nothing_to_migrate_is_false(self):
        assert migrate_tag_categories_v1_to_v2("ACME", {}) is False
        assert migrate_tag_categories_v1_to_v2("ACME", {"tag_categories": {}}) is False

    def test_untouched_ukrainian_default_labels_become_english(self):
        config = {"tag_categories": {"version": 2, "categories": {
            "packaging": {"label": "Пакетаж", "tags": ["BOX"]},
            "priority": {"label": "My own name", "tags": []},
        }}}
        assert migrate_tag_category_labels_to_english("ACME", config) is True
        cats = config["tag_categories"]["categories"]
        assert cats["packaging"]["label"] == DEFAULT_TAG_CATEGORIES["categories"]["packaging"]["label"]
        assert cats["packaging"]["tags"] == ["BOX"]
        assert cats["priority"]["label"] == "My own name"
        assert migrate_tag_category_labels_to_english("ACME", config) is False

    @pytest.mark.parametrize("config", [{}, {"tag_categories": "x"}, {"tag_categories": {"categories": 3}}])
    def test_label_migration_tolerates_odd_shapes(self, config):
        assert migrate_tag_category_labels_to_english("ACME", config) is False


class TestDelimiterV2:
    def test_stock_delimiter_is_renamed_and_orders_gets_a_default(self):
        config = {"settings": {"stock_delimiter": ";"}}
        assert migrate_delimiter_config_v1_to_v2("ACME", config) is True
        assert config["settings"] == {"stock_csv_delimiter": ";", "orders_csv_delimiter": ","}
        assert config["config_version"] == "2.1"

    def test_a_v2_setting_wins_over_a_leftover_v1_key(self):
        config = {"settings": {"stock_delimiter": ";", "stock_csv_delimiter": "\t", "orders_csv_delimiter": ","}}
        assert migrate_delimiter_config_v1_to_v2("ACME", config) is True
        assert config["settings"] == {"stock_csv_delimiter": "\t", "orders_csv_delimiter": ","}

    def test_second_run_changes_nothing(self):
        config = {"settings": {"stock_delimiter": ";"}}
        migrate_delimiter_config_v1_to_v2("ACME", config)
        done = copy.deepcopy(config)
        assert migrate_delimiter_config_v1_to_v2("ACME", config) is False
        assert config == done

    def test_no_settings_section_is_left_alone(self):
        assert migrate_delimiter_config_v1_to_v2("ACME", {}) is False


class TestAdditiveSections:
    def test_weight_config_is_added_once(self):
        config = {}
        assert migrate_add_weight_config("ACME", config) is True
        assert config["weight_config"] == {"volumetric_divisor": 6000, "products": {}, "boxes": []}
        assert migrate_add_weight_config("ACME", config) is False

    def test_inventory_memory_is_added_then_backfilled_then_left(self):
        config = {}
        assert migrate_add_inventory_memory("ACME", config) is True
        assert config["inventory_memory"]["enabled"] is False
        config["inventory_memory"] = {"enabled": True, "skus": {"A": 1}}
        assert migrate_add_inventory_memory("ACME", config) is True
        assert config["inventory_memory"]["names"] == {} and config["inventory_memory"]["skus"] == {"A": 1}
        assert migrate_add_inventory_memory("ACME", config) is False
