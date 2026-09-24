"""One-shot profile migrations (ADR 0009: delimiters move to Auto once)."""

from shopify_tool.profile_migrations import migrate_delimiters_to_auto


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
