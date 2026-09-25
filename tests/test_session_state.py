"""session_state owns current_state.pkl: stamp, stale check, atomic save."""

import pandas as pd
import pytest

from shopify_tool import session_state
from shopify_tool.session_state import StaleSessionError


def _df(*statuses, order_numbers=None):
    n = len(statuses)
    return pd.DataFrame(
        {
            "Order_Number": order_numbers or [f"#{1001 + i}" for i in range(n)],
            "SKU": [f"SKU-{i}" for i in range(n)],
            "Quantity": [1] * n,
            "Order_Fulfillment_Status": list(statuses),
        }
    )


def test_a_session_without_state_has_no_stamp(tmp_path):
    assert session_state.state_stamp(tmp_path) is None


def test_save_returns_the_stamp_now_on_disk(tmp_path):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    assert stamp == session_state.state_stamp(tmp_path)
    assert pd.read_pickle(tmp_path / "analysis" / "current_state.pkl").equals(_df("Fulfillable"))


def test_a_save_from_a_stale_stamp_is_refused_and_writes_nothing(tmp_path):
    first = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    session_state.save_state(tmp_path, _df("Not Fulfillable"), first)  # another PC
    with pytest.raises(StaleSessionError):
        session_state.save_state(tmp_path, _df("Fulfillable", "Fulfillable"), first)
    saved = pd.read_pickle(tmp_path / "analysis" / "current_state.pkl")
    assert saved["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"]


def test_state_created_by_another_pc_makes_a_none_stamp_stale(tmp_path):
    session_state.save_state(tmp_path, _df("Fulfillable"), None)
    assert session_state.is_stale(tmp_path, None)
    with pytest.raises(StaleSessionError):
        session_state.save_state(tmp_path, _df("Fulfillable"), None)


def test_a_failed_write_keeps_the_old_state(tmp_path, monkeypatch):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)

    def share_went_away(*_a, **_k):
        raise OSError("The specified network name is no longer available")

    monkeypatch.setattr(pd.DataFrame, "to_pickle", share_went_away)
    with pytest.raises(OSError):
        session_state.save_state(tmp_path, _df("Not Fulfillable"), stamp)
    assert session_state.state_stamp(tmp_path) == stamp
    assert not list((tmp_path / "analysis").glob(".current_state_tmp_*"))


def test_a_save_leaves_no_temp_file(tmp_path):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    session_state.save_state(tmp_path, _df("Not Fulfillable"), stamp)
    pkl = sorted(p.name for p in (tmp_path / "analysis").glob("*.pkl"))
    assert pkl == ["current_state.pkl"]


def test_order_counts_count_orders_not_lines(tmp_path):
    # #1001 has one blocked SKU line, so the whole order is blocked (R1).
    df = _df(
        "Fulfillable", "Not Fulfillable", "Fulfillable",
        order_numbers=["#1001", "#1001", "#1002"],
    )
    assert session_state.order_counts(df) == {
        "total_orders": 2,
        "fulfillable_orders": 1,
        "not_fulfillable_orders": 1,
    }
