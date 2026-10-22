"""Creating a client: look in one write, settings copied from another (spec A3)."""

import json


def _client_cfg(pm, cid):
    return json.loads((pm.clients_dir / f"CLIENT_{cid}" / "client_config.json").read_text("utf-8"))


def _shopify_cfg(pm, cid):
    return json.loads((pm.clients_dir / f"CLIENT_{cid}" / "shopify_config.json").read_text("utf-8"))


def test_ui_settings_land_in_the_first_write(profile_manager):
    pm = profile_manager
    ok = pm.create_client_profile(
        "ACME", "Acme", ui_settings={"is_pinned": True, "group_id": "g1", "custom_color": "#123456"}
    )
    assert ok
    ui = _client_cfg(pm, "ACME")["ui_settings"]
    assert ui["is_pinned"] is True
    assert ui["group_id"] == "g1"
    assert ui["custom_color"] == "#123456"
    # defaults still present (table_view etc.)
    assert set(pm._get_default_ui_settings()) <= set(ui)


def test_an_archived_id_cannot_be_reused(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("ACME", "Acme")
    pm.archive_client("ACME")
    assert pm.create_client_profile("ACME", "Acme again") is False
    assert not (pm.clients_dir / "CLIENT_ACME").exists()


def test_copy_from_takes_every_setting_but_identity_and_stock_memory(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("SRC", "Source")
    src = _shopify_cfg(pm, "SRC")
    src["rules"] = [{"name": "r1"}]
    src["settings"]["low_stock_threshold"] = 9
    src["inventory_memory"]["skus"] = {"A": 3}
    src["custom_key"] = {"kept": True}
    pm.save_shopify_config("SRC", src)

    assert pm.create_client_profile("NEW", "New Co", copy_from="SRC")
    new = _shopify_cfg(pm, "NEW")
    assert new["client_id"] == "NEW"
    assert new["client_name"] == "New Co"
    assert new["created_at"] != src["created_at"]
    assert new["rules"] == [{"name": "r1"}]
    assert new["settings"]["low_stock_threshold"] == 9
    assert new["custom_key"] == {"kept": True}
    default_memory = pm._create_default_shopify_config("NEW", "New Co")["inventory_memory"]
    assert new["inventory_memory"]["skus"] == default_memory["skus"]


def test_copy_from_a_missing_client_creates_nothing(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("NEW", "New Co", copy_from="GHOST") is False
    assert not (pm.clients_dir / "CLIENT_NEW").exists()
