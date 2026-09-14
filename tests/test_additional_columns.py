"""Additional columns are read from the column mappings first (ADR 0006)."""

from shopify_tool.core import effective_additional_columns

OLD = {"ui_settings": {"table_view": {"additional_columns": [{"csv_name": "Old"}]}}}


def test_the_mappings_key_wins():
    mappings = {"additional_columns": [{"csv_name": "New"}]}
    assert effective_additional_columns(mappings, OLD) == [{"csv_name": "New"}]


def test_an_empty_mappings_list_still_wins():
    assert effective_additional_columns({"additional_columns": []}, OLD) == []


def test_absent_key_falls_back_to_the_client_config():
    assert effective_additional_columns({"orders": {}}, OLD) == [{"csv_name": "Old"}]


def test_nothing_anywhere_is_empty():
    assert effective_additional_columns({}, {}) == []
    assert effective_additional_columns(None, None) == []
