"""Shared fixtures for the backend test suite.

Column names mirror the DEFAULT Shopify/Bulgarian-ERP mapping hardcoded in
shopify_tool.analysis._clean_and_prepare_data (used when column_mappings=None),
so fixtures exercise the exact same path production runs through.
"""
import pandas as pd
import pytest


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
