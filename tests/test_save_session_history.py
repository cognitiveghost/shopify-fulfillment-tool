from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from gui.main_window_pyside import MainWindow
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


def test_save_session_state_survives_history_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fulfillment_history, "record_session", Mock(side_effect=RuntimeError("share"))
    )
    mw = _mw(tmp_path, _df("Fulfillable"))
    MainWindow.save_session_state(mw)
    assert (Path(mw.session_path) / "analysis" / "current_state.pkl").exists()
