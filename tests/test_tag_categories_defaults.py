"""Default tag categories: one source of truth, no Ukrainian localization."""

import re

from shopify_tool.profile_manager import ProfileManager
from shopify_tool.tag_manager import DEFAULT_TAG_CATEGORIES, validate_tag_categories_v2

CYRILLIC = re.compile(r"[Ѐ-ӿ]")

EXPECTED_LABELS = {
    "packaging": "Packaging",
    "priority": "Priority",
    "status": "Status",
    "order_type": "Order Type",
    "accessories": "Accessories",
    "delivery": "Delivery",
    "custom": "Other",
}


def test_default_categories_have_english_labels():
    labels = {k: v["label"] for k, v in DEFAULT_TAG_CATEGORIES["categories"].items()}
    assert labels == EXPECTED_LABELS


def test_default_categories_contain_no_cyrillic():
    assert not CYRILLIC.search(str(DEFAULT_TAG_CATEGORIES))


def test_delivery_seeds_no_tags():
    assert DEFAULT_TAG_CATEGORIES["categories"]["delivery"]["tags"] == []


def test_non_delivery_tag_lists_are_unchanged():
    cats = DEFAULT_TAG_CATEGORIES["categories"]
    assert cats["packaging"]["tags"] == ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"]
    assert cats["priority"]["tags"] == ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"]
    assert cats["status"]["tags"] == ["CHECKED", "PROBLEM", "VERIFIED"]
    assert cats["order_type"]["tags"] == ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"]
    assert cats["accessories"]["tags"] == ["STICKER", "BUSINESS_CARD", "GIFT_BOX"]
    assert cats["custom"]["tags"] == []


def test_defaults_pass_their_own_validator():
    is_valid, errors = validate_tag_categories_v2(DEFAULT_TAG_CATEGORIES)
    assert is_valid, errors


def test_migration_does_not_hand_out_the_shared_constant():
    from shopify_tool.profile_migrations import migrate_add_tag_categories

    config_a = {}
    config_b = {}
    migrate_add_tag_categories("A", config_a)
    migrate_add_tag_categories("B", config_b)

    config_a["tag_categories"]["categories"]["packaging"]["tags"].append("LEAKED")

    assert "LEAKED" not in config_b["tag_categories"]["categories"]["packaging"]["tags"]
    assert "LEAKED" not in DEFAULT_TAG_CATEGORIES["categories"]["packaging"]["tags"]


def test_new_client_config_has_english_labels():
    config = ProfileManager._create_default_shopify_config("001", "Test Client")

    labels = {k: v["label"] for k, v in config["tag_categories"]["categories"].items()}
    assert labels == EXPECTED_LABELS
    assert not CYRILLIC.search(str(config["tag_categories"]))
