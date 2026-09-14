"""Additional columns on Settings › Mappings (Bundle 13 spec §7.5, ADR 0006)."""

from PySide6.QtWidgets import QCheckBox

from gui.settings.mappings import OrdersMappingPage


def _entry(name, enabled=False):
    return {
        "csv_name": name,
        "internal_name": name,
        "enabled": enabled,
        "is_order_level": True,
        "exists_in_df": True,
    }


def test_without_the_key_the_page_shows_the_old_client_config_list(qapp):
    page = OrdersMappingPage(
        {"orders": {}}, {}, fallback_additional_columns=[_entry("Email")]
    )
    assert [e["csv_name"] for e in page.additional_entries] == ["Email"]


def test_the_mappings_key_wins_over_the_fallback(qapp):
    page = OrdersMappingPage(
        {"orders": {}, "additional_columns": []},
        {},
        fallback_additional_columns=[_entry("Email")],
    )
    assert page.additional_entries == []


def test_loading_headers_lists_the_unmapped_columns(qapp, monkeypatch):
    page = OrdersMappingPage(
        {"orders": {"Name": "Order_Number", "Lineitem sku": "SKU"}}, {}
    )
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName",
        lambda *a, **k: ("orders.csv", ""),
    )
    monkeypatch.setattr(
        "gui.settings.mappings.read_csv_headers",
        lambda path: ["Name", "Lineitem sku", "Email", "Phone"],
    )
    page._load_headers_from_csv()
    assert [e["csv_name"] for e in page.additional_entries] == ["Email", "Phone"]


def test_collect_writes_the_list_and_snapshot_sees_a_toggle(qapp):
    mappings = {"orders": {}}
    page = OrdersMappingPage(
        mappings, {}, fallback_additional_columns=[_entry("Email")]
    )
    before = page.snapshot()
    box = next(
        b
        for b in page.additional_container.findChildren(QCheckBox)
        if b.text() == "Email"
    )
    box.setChecked(True)
    assert page.snapshot() != before
    result = page.collect()
    assert result["column_mappings"]["additional_columns"][0]["enabled"] is True
    assert mappings["additional_columns"][0]["enabled"] is True  # the live dict
