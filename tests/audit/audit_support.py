"""Helpers and fixtures shared by the audit 07-09 tests.

A module, not tests/audit/conftest.py: a second conftest would shadow
tests/conftest.py for the tests that import from it by name. Test modules
import the *_fixture functions they use; each registers under its name=.

Synthetic data only: the benchmark frame is the one the audits time against
(5,000 orders x 3 lines = 15,000 rows, built through run_analysis), and
every session lives under tmp_path.
"""

import builtins
import copy
import logging
import os
import time
from pathlib import Path

import pandas as pd
import pytest

from shopify_tool import core, fulfillment_history
from shopify_tool.analysis import run_analysis
from shopify_tool.session_manager import SessionManager

BENCH_ORDERS = 5000
MAPPINGS = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method",
    },
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}


def bench_orders(n=BENCH_ORDERS):
    """Shopify headers, n orders of three lines each (A, B, C)."""
    return pd.DataFrame(
        {
            "Name": [f"#{i}" for i in range(n) for _ in range(3)],
            "Lineitem sku": ["A", "B", "C"] * n,
            "Lineitem quantity": [1] * (3 * n),
            "Shipping Method": ["DHL"] * (3 * n),
            "Shipping Country": ["BG"] * (3 * n),
        }
    )


def timed(fn):
    """Wall time of fn() in seconds, and its result."""
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


class Profiles:
    """The ProfileManager calls SessionManager and one run make, memory off."""

    def __init__(self, root):
        self.root = Path(root)

    def get_sessions_root(self):
        return self.root / "Sessions"

    def client_exists(self, _client_id):
        return True

    def invalidate_metadata_cache(self, _client_id):
        pass

    def get_client_directory(self, _client_id):
        path = self.root / "client"
        path.mkdir(exist_ok=True)
        return path

    def get_inventory_memory(self, _client_id):
        return {}

    def load_shopify_config(self, _client_id):
        return {}

    def load_client_config(self, _client_id):
        return {}


@pytest.fixture(scope="session", name="benchmark_frame")
def benchmark_frame_fixture():
    """The audits' benchmark frame and stats. Copy it before changing it."""
    logging.disable(logging.CRITICAL)
    try:
        stock = pd.DataFrame(
            {"Артикул": ["A", "B", "C"], "Име": list("abc"), "Наличност": [7000] * 3}
        )
        df, stats = run_analysis(stock, bench_orders(), pd.DataFrame({"Order_Number": []}))
    finally:
        logging.disable(logging.NOTSET)
    return df, stats


@pytest.fixture(name="sessions")
def sessions_fixture(tmp_path):
    return SessionManager(Profiles(tmp_path))


@pytest.fixture(name="analysis_run")
def analysis_run_fixture(tmp_path, sessions, monkeypatch):
    """run(session_path, orders) -> run_full_analysis's tuple, in session mode.

    Real CSVs, a real SessionManager; only Packing Tool's packed-order reader
    is replaced, as in tests/test_memory_baseline.py.
    """
    monkeypatch.setattr(
        core,
        "load_session_signals",
        lambda _pm, _cid: (pd.DataFrame(columns=fulfillment_history.COLUMNS), None),
    )
    profiles = sessions.profile_manager
    counter = iter(range(100))

    def run(session_path, orders=(("#1", "A", 1), ("#2", "B", 1))):
        n = next(counter)
        orders_csv = tmp_path / f"orders{n}.csv"
        pd.DataFrame(
            [
                {"Name": o, "Lineitem sku": s, "Lineitem quantity": q, "Shipping Method": "DHL"}
                for o, s, q in orders
            ]
        ).to_csv(orders_csv, index=False)
        stock_csv = tmp_path / f"stock{n}.csv"
        pd.DataFrame(
            [{"Артикул": s, "Име": f"{s} name", "Наличност": 10} for s in ("A", "B")]
        ).to_csv(stock_csv, index=False)
        return core.run_full_analysis(
            str(stock_csv),
            str(orders_csv),
            str(tmp_path / "out"),
            ",",
            ",",
            {"column_mappings": copy.deepcopy(MAPPINGS)},
            client_id="M",
            session_manager=sessions,
            profile_manager=profiles,
            session_path=str(session_path),
        )

    return run


@pytest.fixture(name="in_place_writes")
def in_place_writes_fixture(monkeypatch):
    """watch(*names) -> list that collects each named file opened for writing
    in place, i.e. not through a temp file and a rename. A reader on another
    PC can see such a file half written."""

    def watch(*names):
        seen = []
        real_open = builtins.open

        def spy(file, mode="r", *args, **kwargs):
            if (
                isinstance(file, (str, os.PathLike))
                and any(flag in mode for flag in "wax+")
                and Path(file).name in names
            ):
                seen.append(Path(file).name)
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", spy)
        return seen

    return watch
