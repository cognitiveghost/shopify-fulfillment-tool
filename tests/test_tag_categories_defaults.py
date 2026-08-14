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


UKRAINIAN_CONFIG = {
    "tag_categories": {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Пакетаж", "color": "#4CAF50", "order": 1,
                "tags": ["SMALL_BAG", "BOX"],
                "sku_writeoff": {"enabled": True,
                                 "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]}},
            },
            "delivery": {
                "label": "Кур'єр/Доставка", "color": "#FF5722", "order": 6,
                "tags": ["NOVA_POSHTA", "UKRPOSHTA"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
            "custom": {
                "label": "Інші", "color": "#9E9E9E", "order": 999, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
        },
    }
}


def _ukrainian_config():
    import copy as _copy
    return _copy.deepcopy(UKRAINIAN_CONFIG)


def test_relabels_untouched_ukrainian_defaults():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    assert migrate_tag_category_labels_to_english("001", config) is True

    cats = config["tag_categories"]["categories"]
    assert cats["packaging"]["label"] == "Packaging"
    assert cats["delivery"]["label"] == "Delivery"
    assert cats["custom"]["label"] == "Other"


def test_user_renamed_label_is_preserved():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    config["tag_categories"]["categories"]["packaging"]["label"] = "Boxes & Bags"

    assert migrate_tag_category_labels_to_english("001", config) is True

    cats = config["tag_categories"]["categories"]
    assert cats["packaging"]["label"] == "Boxes & Bags"
    assert cats["delivery"]["label"] == "Delivery"


def test_migration_is_idempotent():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    assert migrate_tag_category_labels_to_english("001", config) is True
    snapshot = str(config)
    assert migrate_tag_category_labels_to_english("001", config) is False
    assert str(config) == snapshot


def test_migration_never_touches_tags_colors_orders_or_writeoff():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    before = {
        cid: (c["tags"], c["color"], c["order"], c["sku_writeoff"])
        for cid, c in _ukrainian_config()["tag_categories"]["categories"].items()
    }

    migrate_tag_category_labels_to_english("001", config)

    for cid, cat in config["tag_categories"]["categories"].items():
        assert (cat["tags"], cat["color"], cat["order"], cat["sku_writeoff"]) == before[cid]
    # the Ukrainian carrier tags specifically survive
    assert config["tag_categories"]["categories"]["delivery"]["tags"] == [
        "NOVA_POSHTA", "UKRPOSHTA"
    ]


def test_migration_tolerates_malformed_configs():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    for config in (
        {},
        {"tag_categories": {}},
        {"tag_categories": {"packaging": {"label": "Пакетаж"}}},  # v1 shape
        {"tag_categories": {"version": 2, "categories": "not a dict"}},
        {"tag_categories": {"version": 2, "categories": {"packaging": "not a dict"}}},
    ):
        assert migrate_tag_category_labels_to_english("001", config) is False


def test_loading_a_ukrainian_config_relabels_it(tmp_path):
    """The migration reaches real configs through load_shopify_config()."""
    import json

    pm = ProfileManager(str(tmp_path))
    pm.create_client_profile("001", "Test Client")

    config_path = pm.clients_dir / "CLIENT_001" / "shopify_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["tag_categories"] = _ukrainian_config()["tag_categories"]
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loaded = pm.load_shopify_config("001")
    labels = {k: v["label"] for k, v in loaded["tag_categories"]["categories"].items()}
    assert labels["packaging"] == "Packaging"
    assert labels["delivery"] == "Delivery"
