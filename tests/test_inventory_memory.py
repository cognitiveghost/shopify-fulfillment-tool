"""Tests for inventory memory feature.

Covers:
- ProfileManager.save_inventory_memory / get_inventory_memory round-trip
- FileHandler._check_inventory_anomaly logic (no GUI, no fixtures beyond tmp_path)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd


# ---------------------------------------------------------------------------
# ProfileManager round-trip
# ---------------------------------------------------------------------------


def _make_profile_manager(tmp_path: Path):
    """Create a ProfileManager pointed at a temp directory."""
    from shopify_tool.profile_manager import ProfileManager

    base = tmp_path / "server"
    base.mkdir()

    # Bypass network check by patching _test_connection
    with patch.object(ProfileManager, "_test_connection", return_value=True):
        pm = ProfileManager.__new__(ProfileManager)
        pm.base_path = base
        pm.clients_dir = base / "Clients"
        pm.sessions_dir = base / "Sessions"
        pm.stats_dir = base / "Stats"
        pm.logs_dir = base / "Logs" / "shopify_tool"
        for d in (pm.clients_dir, pm.sessions_dir, pm.stats_dir, pm.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        pm._metadata_cache = {}
        pm.connection_timeout = 5
        pm.is_network_available = True

    return pm


def test_save_and_get_inventory_memory(tmp_path):
    """Round-trip: save then retrieve inventory_memory."""
    pm = _make_profile_manager(tmp_path)

    # Create a minimal client profile manually
    client_dir = pm.clients_dir / "CLIENT_TEST"
    client_dir.mkdir()
    (client_dir / "backups").mkdir()

    shopify_cfg = {
        "client_id": "TEST",
        "client_name": "Test Client",
        "settings": {},
        "column_mappings": {"version": 2, "orders": {}, "stock": {}},
        "tag_categories": {"version": 2, "categories": {}},
        "inventory_memory": {
            "enabled": True,
            "skus": {},
            "last_updated": None,
            "total_units": 0,
        },
    }
    (client_dir / "shopify_config.json").write_text(
        json.dumps(shopify_cfg), encoding="utf-8"
    )

    stock = {
        "SKU-A": 10.0,
        "SKU-B": 5.0,
        "SKU-C": 0.0,
    }  # SKU-C=0 is kept (zero Final Stock = warehouse depleted; needed for anomaly overlap)

    result = pm.save_inventory_memory("TEST", stock)
    assert result is True

    mem = pm.get_inventory_memory("TEST")
    assert mem["skus"] == {"SKU-A": 10.0, "SKU-B": 5.0, "SKU-C": 0.0}
    assert mem["total_units"] == 15  # total_units counts only positive values
    assert mem["last_updated"] is not None
    # enabled flag must be preserved from original config
    assert mem["enabled"] is True


def test_get_inventory_memory_migration_adds_default(tmp_path):
    """get_inventory_memory triggers migration and returns default structure when key absent."""
    pm = _make_profile_manager(tmp_path)

    client_dir = pm.clients_dir / "CLIENT_NOKEY"
    client_dir.mkdir()
    (client_dir / "backups").mkdir()

    # Config without inventory_memory key — migration should add it
    shopify_cfg = {
        "client_id": "NOKEY",
        "client_name": "No Key",
        "settings": {},
        "column_mappings": {"version": 2, "orders": {}, "stock": {}},
        "tag_categories": {"version": 2, "categories": {}},
    }
    (client_dir / "shopify_config.json").write_text(
        json.dumps(shopify_cfg), encoding="utf-8"
    )

    mem = pm.get_inventory_memory("NOKEY")
    # Migration adds the default structure
    assert "skus" in mem
    assert mem["skus"] == {}
    assert mem["enabled"] is False
    assert mem["total_units"] == 0


# ---------------------------------------------------------------------------
# _check_inventory_anomaly — tested directly without instantiating FileHandler
# ---------------------------------------------------------------------------


def _anomaly_check(new_stock_df: pd.DataFrame, memory: dict):
    """Thin wrapper: instantiate FileHandler cheaply and call the method."""
    from gui.file_handler import FileHandler

    fh = FileHandler.__new__(FileHandler)
    fh.mw = MagicMock()
    fh.log = MagicMock()
    return fh._check_inventory_anomaly(new_stock_df, memory)


def test_no_anomaly_when_memory_empty():
    """Empty memory → no anomaly."""
    df = pd.DataFrame({"SKU": ["A", "B"], "Stock": [10, 20]})
    is_anomaly, msg = _anomaly_check(df, {})
    assert is_anomaly is False
    assert msg == ""


def test_no_anomaly_normal_load():
    """Healthy overlap and stable total → no anomaly."""
    memory = {
        "skus": {f"SKU-{i}": 10.0 for i in range(10)},
        "total_units": 100,
    }
    df = pd.DataFrame({"SKU": [f"SKU-{i}" for i in range(10)], "Stock": [10] * 10})
    is_anomaly, msg = _anomaly_check(df, memory)
    assert is_anomaly is False


def test_anomaly_wrong_client_low_overlap():
    """< 50% SKU overlap → anomaly."""
    memory = {
        "skus": {f"OLD-{i}": 10.0 for i in range(10)},
        "total_units": 100,
    }
    df = pd.DataFrame({"SKU": [f"NEW-{i}" for i in range(10)], "Stock": [10] * 10})
    is_anomaly, msg = _anomaly_check(df, memory)
    assert is_anomaly is True
    assert "overlap" in msg.lower() or "%" in msg


def test_anomaly_big_stock_drop():
    """> 40% total unit drop → anomaly."""
    memory = {
        "skus": {f"SKU-{i}": 10.0 for i in range(10)},
        "total_units": 100,
    }
    # Same SKUs but only 50 units total — 50% drop
    df = pd.DataFrame({"SKU": [f"SKU-{i}" for i in range(10)], "Stock": [5] * 10})
    is_anomaly, msg = _anomaly_check(df, memory)
    assert is_anomaly is True
    assert "%" in msg


def test_anomaly_big_stock_increase():
    """> 40% total unit increase → anomaly."""
    memory = {
        "skus": {f"SKU-{i}": 10.0 for i in range(10)},
        "total_units": 100,
    }
    df = pd.DataFrame(
        {
            "SKU": [f"SKU-{i}" for i in range(10)],
            "Stock": [20] * 10,
        }  # 200 units — 100% increase
    )
    is_anomaly, msg = _anomaly_check(df, memory)
    assert is_anomaly is True


def test_no_anomaly_when_old_total_zero():
    """old_total == 0 should not trigger percentage check (div-by-zero guard)."""
    memory = {
        "skus": {f"SKU-{i}": 0.0 for i in range(5)},
        "total_units": 0,
    }
    df = pd.DataFrame({"SKU": [f"SKU-{i}" for i in range(5)], "Stock": [10] * 5})
    # Low overlap would trigger, but since all skus match this should be clean
    is_anomaly, _ = _anomaly_check(df, memory)
    # Only SKU overlap matters here — all 5 match, so no overlap anomaly.
    # total_units == 0 means percentage check is skipped.
    assert is_anomaly is False
