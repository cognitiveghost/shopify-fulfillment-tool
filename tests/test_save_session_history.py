from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from gui.main_window_pyside import MainWindow
from shared.atomic_write import atomic_write_json
from shopify_tool import fulfillment_history


def _mw(tmp_path, df):
    session = tmp_path / "CLIENT_X" / "2026-09-25_1"
    (session / "analysis").mkdir(parents=True)
    return SimpleNamespace(
        session_path=str(session),
        analysis_results_df=df,
        analysis_stats=None,
        _state_stamp=None,
        session_manager=None,
        current_client_id="X",
        profile_manager=SimpleNamespace(get_client_directory=lambda _c: tmp_path),
        active_profile_config={"inventory_memory": {"enabled": False}},
    )


def _df(status):
    return pd.DataFrame(
        {
            "Order_Number": ["#1"],
            "SKU": ["A"],
            "Stock": [5],
            "Final_Stock": [4],
            "Quantity": [1],
            "Order_Fulfillment_Status": [status],
        }
    )


def test_save_session_state_records_this_sessions_orders(tmp_path):
    mw = _mw(tmp_path, _df("Fulfillable"))
    MainWindow.save_session_state(mw)
    h = fulfillment_history.load(tmp_path / "fulfillment_history.csv")
    assert h[["Order_Number", "Session"]].values.tolist() == [["#1", "2026-09-25_1"]]


def _memory_mw(tmp_path, owner):
    """A window whose profile has inventory memory on, last written by `owner`."""
    mw = _mw(tmp_path, _df("Fulfillable"))
    mw.active_profile_config = {"inventory_memory": {"enabled": True}}
    mw.profile_manager = SimpleNamespace(
        get_client_directory=lambda _c: tmp_path,
        get_inventory_memory=lambda _c: {"enabled": True, "session": owner},
        save_inventory_memory=Mock(return_value=True),
    )
    atomic_write_json(
        Path(mw.session_path) / "analysis" / "memory_baseline.json",
        {"skus": {"A": 5, "B": 7}, "names": {"A": "Widget"}},
    )
    return mw


def test_save_rewrites_memory_owned_by_this_session(tmp_path):
    mw = _memory_mw(tmp_path, owner="2026-09-25_1")
    mw.analysis_results_df = _df("Fulfillable").assign(Final_Stock=3)
    MainWindow.save_session_state(mw)
    mw.profile_manager.save_inventory_memory.assert_called_once_with(
        "X", {"A": 3.0, "B": 7.0}, names_dict={"A": "Widget"}, session="2026-09-25_1"
    )


def test_save_skips_memory_owned_by_another_session(tmp_path):
    mw = _memory_mw(tmp_path, owner="2026-09-25_2")
    MainWindow.save_session_state(mw)
    mw.profile_manager.save_inventory_memory.assert_not_called()


def test_save_session_state_survives_history_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fulfillment_history, "record_session", Mock(side_effect=RuntimeError("share"))
    )
    mw = _mw(tmp_path, _df("Fulfillable"))
    MainWindow.save_session_state(mw)
    assert (Path(mw.session_path) / "analysis" / "current_state.pkl").exists()
