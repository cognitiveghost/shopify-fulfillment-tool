"""Inventory memory across re-runs of one session (Phase 14 Bundle 3, AUDIT-02-9).

Runs go through core.run_full_analysis with real CSVs; only the Packing Tool
reader and the history location are replaced.
"""

import pandas as pd
import pytest

from shopify_tool import core, fulfillment_history

MAPPINGS = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method",
    },
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}


class MemoryProfile:
    """The ProfileManager calls a run makes, with memory enabled."""

    def __init__(self, client_dir, skus):
        self.client_dir = client_dir
        self.memory = {"enabled": True, "skus": dict(skus), "names": {}}

    def get_inventory_memory(self, _cid):
        return self.memory

    def load_shopify_config(self, _cid):
        return {"inventory_memory": self.memory}

    def load_client_config(self, _cid):
        return {}

    def get_client_directory(self, _cid):
        return self.client_dir

    def save_inventory_memory(self, _cid, stock_dict, config=None, names_dict=None, session=None):
        self.memory["skus"] = dict(stock_dict)
        self.memory["session"] = session
        return True


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fulfillment_history, "get_persistent_data_path", lambda _n: tmp_path / "h.csv"
    )
    monkeypatch.setattr(
        core,
        "load_session_signals",
        lambda _pm, _cid: (pd.DataFrame(columns=["Order_Number", "Execution_Date", "Session"]), None),
    )
    counter = iter(range(100))

    def go(pm, order_rows, stock_rows=None, session="S1"):
        n = next(counter)
        orders = tmp_path / f"orders{n}.csv"
        pd.DataFrame(
            [
                {"Name": o, "Lineitem sku": s, "Lineitem quantity": q, "Shipping Method": "DHL"}
                for o, s, q in order_rows
            ]
        ).to_csv(orders, index=False)
        stock = None
        if stock_rows is not None:
            stock = tmp_path / f"stock{n}.csv"
            pd.DataFrame(
                [{"Артикул": s, "Име": f"{s} name", "Наличност": q} for s, q in stock_rows]
            ).to_csv(stock, index=False)
        ok, msg, _df, _stats = core.run_full_analysis(
            str(stock) if stock else None,
            str(orders),
            str(tmp_path / "out"),
            ",",
            ",",
            {"column_mappings": MAPPINGS},
            client_id="C",
            profile_manager=pm,
            session_path=str(tmp_path / session),
        )
        assert ok, msg

    return go


def test_memory_mode_rerun_of_same_session_draws_once(tmp_path, run):
    pm = MemoryProfile(tmp_path, {"A": 10.0})
    run(pm, [("#1", "A", 2)])
    assert pm.memory["skus"] == {"A": 8.0}
    run(pm, [("#1", "A", 2)])  # the same session again
    assert pm.memory["skus"] == {"A": 8.0}
    assert pm.memory["session"] == "S1"


def test_stock_file_run_writes_summed_baseline(tmp_path, run):
    pm = MemoryProfile(tmp_path, {"A": 99.0})
    run(pm, [("#1", "A", 1)], stock_rows=[("A", 3), ("A", 4)])
    assert core.read_memory_baseline(tmp_path / "S1")["skus"] == {"A": 7.0}
    assert pm.memory["skus"] == {"A": 6.0}


def test_a_new_session_draws_from_the_memory_the_last_one_left(tmp_path, run):
    pm = MemoryProfile(tmp_path, {"A": 10.0})
    run(pm, [("#1", "A", 2)], session="S1")
    run(pm, [("#2", "A", 3)], session="S2")
    assert pm.memory["skus"] == {"A": 5.0}
    assert pm.memory["session"] == "S2"


def test_rerunning_an_older_session_leaves_the_later_draw_alone(tmp_path, run):
    pm = MemoryProfile(tmp_path, {"A": 10.0})
    run(pm, [("#1", "A", 2)], session="S1")
    run(pm, [("#2", "A", 3)], session="S2")
    run(pm, [("#1", "A", 2)], session="S1")  # reopened from the Session Browser
    assert pm.memory["skus"] == {"A": 5.0}
    assert pm.memory["session"] == "S2"
