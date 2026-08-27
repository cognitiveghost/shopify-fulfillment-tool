"""Shared fixtures for the test suite.

Column names mirror the DEFAULT Shopify/Bulgarian-ERP mapping hardcoded in
shopify_tool.analysis._clean_and_prepare_data (used when column_mappings=None),
so fixtures exercise the exact same path production runs through.

The SettingsWindow fixtures at the bottom are here rather than in a test
module because three test files need them and `tests/` is not a package --
conftest is the only sharing mechanism that does not depend on sys.path.
"""
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.settings.window import SettingsWindow


@pytest.fixture
def profile_manager(tmp_path):
    """Real ProfileManager rooted at a throwaway tmp_path -- exercises the
    actual file-locking/JSON read-write code path, not a mock."""
    from shopify_tool.profile_manager import ProfileManager
    ProfileManager._config_cache.clear()  # class-level cache; avoid cross-test leakage
    return ProfileManager(base_path=str(tmp_path))


@pytest.fixture
def orders_df_factory():
    """Build a raw orders DataFrame using real Shopify CSV export column names.

    Each row is one line item. Pass rows as dicts; missing keys default sensibly.
    Order-level columns (Name/Shipping Method/...) should be set only on an
    order's first row and left blank on subsequent rows to mimic Shopify's
    forward-fill export format -- pass explicit values on every row if you don't
    want to rely on ffill.
    """
    def _make(rows):
        defaults = {
            "Name": "",
            "Lineitem sku": "",
            "Lineitem quantity": 1,
            "Lineitem name": "",
            "Shipping Method": "Standard",
            "Shipping Country": "DE",
            "Tags": "",
            "Notes": "",
        }
        full_rows = [{**defaults, **row} for row in rows]
        return pd.DataFrame(full_rows)
    return _make


@pytest.fixture
def stock_df_factory():
    """Build a raw stock DataFrame using real Bulgarian-ERP CSV column names."""
    def _make(rows):
        defaults = {"Артикул": "", "Име": "", "Наличност": 0}
        full_rows = [{**defaults, **row} for row in rows]
        return pd.DataFrame(full_rows)
    return _make


@pytest.fixture
def empty_history_df():
    return pd.DataFrame(columns=["Order_Number", "Execution_Date"])


@pytest.fixture
def simple_orders_df(orders_df_factory):
    """One single-item order, one two-item order."""
    return orders_df_factory([
        {"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 2},
        {"Name": "#1002", "Lineitem sku": "B1", "Lineitem quantity": 1},
        {"Name": "#1002", "Lineitem sku": "B2", "Lineitem quantity": 3},
    ])


@pytest.fixture
def simple_stock_df(stock_df_factory):
    return stock_df_factory([
        {"Артикул": "A1", "Име": "Widget A1", "Наличност": 10},
        {"Артикул": "B1", "Име": "Widget B1", "Наличност": 10},
        {"Артикул": "B2", "Име": "Widget B2", "Наличност": 10},
    ])


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_modals(monkeypatch):
    """Fail loudly instead of blocking forever.

    save_settings() reports validation failures through modal QMessageBox
    calls and returns early. Under the offscreen QPA platform an unstubbed
    modal hangs the test run, so every popup is recorded and dismissed.
    """
    seen = []
    for name in ("warning", "critical", "information", "question"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: seen.append((_n, a[1:3]))),
        )
    return seen


def settings_fixture_config():
    """A config touching every section save_settings() writes."""
    return {
        "settings": {
            "stock_csv_delimiter": ";",
            "orders_csv_delimiter": ",",
            "low_stock_threshold": 5,
            "repeat_detection_days": 30,
        },
        "rules": [
            {
                "name": "Flag big orders",
                "priority": 1,
                "level": "order",
                "steps": [
                    {
                        "conditions": [
                            {"field": "item_count", "operator": "is greater than", "value": "5"}
                        ],
                        "match": "ALL",
                        "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                    }
                ],
            }
        ],
        "packing_list_configs": [
            {
                "name": "Main",
                "output_filename": "main.xlsx",
                "filters": [{"field": "SKU", "operator": "contains", "value": "AB"}],
                "exclude_skus": ["X1", "X2"],
            }
        ],
        "stock_export_configs": [
            {
                "name": "Daily",
                "output_filename": "daily.csv",
                "filters": [{"field": "Tags", "operator": "equals", "value": "hot"}],
            }
        ],
        # v2 mappings are {csv_column: internal_name}. Every required internal
        # field must appear or save_settings() aborts at validation.
        "column_mappings": {
            "version": 2,
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Shipping Method": "Shipping_Method",
                "Lineitem name": "Product_Name",
            },
            "stock": {
                "Article": "SKU",
                "Available": "Stock",
                "Годност": "Expiry_Date",
                "Партида": "Batch",
            },
        },
        "courier_mappings": {
            "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False}
        },
        "set_decoders": {},
        "weight_config": {
            "volumetric_divisor": 5000,
            "products": {
                "SKU1": {
                    "name": "Widget",
                    "length_cm": 10.0,
                    "width_cm": 5.0,
                    "height_cm": 2.0,
                    "no_packaging": False,
                }
            },
            "boxes": [
                {"name": "Small", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}
            ],
        },
        "tag_categories": {"version": 2, "categories": {}},
    }


@pytest.fixture
def make_settings_config():
    """Factory, not a value: test_settings_nav builds two windows in one test
    and each needs its own config to mutate."""
    return settings_fixture_config


@pytest.fixture
def started_workers(monkeypatch):
    """Intercept the background save instead of letting it run.

    save_settings() hands a Worker to QThreadPool.globalInstance().start().
    Left alone that really runs, on a real thread, racing the assertions and
    delivering a success QMessageBox through queued signals. Capturing the
    worker keeps the test deterministic and still proves the save was reached.
    """
    started = []
    monkeypatch.setattr(
        "gui.settings.window.QThreadPool",
        type("Pool", (), {
            "globalInstance": staticmethod(
                lambda: type("P", (), {"start": staticmethod(started.append)})()
            )
        }),
    )
    return started


@pytest.fixture(autouse=True)
def clean_nav_setting():
    """QSettings is process-global and writes to the real ~/.config store, so
    any test that builds a SettingsWindow would otherwise leave the developer's
    (and CI's) last-page setting behind and leak it into the next run."""
    store = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
    store.remove(SettingsWindow.NAV_SETTINGS_KEY)
    yield
    store.remove(SettingsWindow.NAV_SETTINGS_KEY)


@pytest.fixture(autouse=True)
def reset_theme_and_density():
    """ThemeManager is a process-wide singleton that reads real QSettings once,
    on its first construction anywhere in the whole test run -- so a
    developer's actual saved theme (or a previous test's toggle) leaks into
    every later test, including ones that never touch theming themselves.
    Removing the QSettings keys is not enough on its own: the singleton
    already has the leaked value cached in memory, so the in-memory state is
    forced back to the desk/light baseline directly, both before and after.

    Resetting the flag is not enough either: ThemeManager.set_density() also
    pushes a new app-wide stylesheet, and nothing else takes it back down. A
    test that switched to floor would otherwise leave every later test file
    asserting geometry against 44px controls."""
    from gui.theme_manager import (
        DEFAULT_DENSITY,
        get_density,
        get_theme_manager,
        set_density,
    )

    store = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")

    def _reset():
        store.remove("theme")
        store.remove("density")
        manager = get_theme_manager()
        # Only restyle when a test actually moved something. apply_theme() sets
        # an app-wide stylesheet, which re-polishes every live widget -- paid on
        # all ~850 tests it would dwarf the suite, and almost none of them touch
        # theming at all.
        dirty = manager._current_theme_name != "light" or get_density() != DEFAULT_DENSITY
        manager._current_theme_name = "light"
        set_density(DEFAULT_DENSITY)
        if dirty and QApplication.instance():
            manager.apply_theme()

    _reset()
    yield
    _reset()


@pytest.fixture
def window(qapp, no_modals, started_workers):
    """A real SettingsWindow with the background save intercepted."""
    win = SettingsWindow(
        client_id="M",
        client_config=settings_fixture_config(),
        profile_manager=Mock(),
    )
    yield win
    win.deleteLater()
