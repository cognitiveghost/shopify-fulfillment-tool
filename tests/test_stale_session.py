"""The stamp's life cycle on a real MainWindow (ADR 0011)."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

import gui.actions_handler as actions_module
import gui.main_window_pyside as main_window_module
import gui.session_browser_widget as browser_module
from gui.main_window_pyside import MainWindow
from shopify_tool import session_state


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    monkeypatch.setattr(browser_module.SessionBrowserWidget, "USE_ASYNC", False)
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    win.profile_manager.create_client_profile("acme", "Client Acme")
    win.current_client_id = "acme"
    win.load_client_config("acme")
    yield win
    win.close()


@pytest.fixture
def told(monkeypatch):
    got = []
    record = lambda *a, **k: got.append(a[1])  # noqa: E731 -- headline only
    monkeypatch.setattr(main_window_module, "show_error", record)
    monkeypatch.setattr(actions_module, "show_error", record)
    return got


def _orders(*statuses):
    return pd.DataFrame(
        {
            "Order_Number": [f"#{1001 + i}" for i in range(len(statuses))],
            "SKU": [f"SKU-{i}" for i in range(len(statuses))],
            "Quantity": [1] * len(statuses),
            "Stock": [5] * len(statuses),
            "Order_Fulfillment_Status": list(statuses),
        }
    )


def _open_with_state(win, df):
    path = win.session_manager.create_session("acme")
    session_state.save_state(path, df, None)
    win.load_existing_session(path)
    return path


def _another_pc_saves(path, df):
    session_state.save_state(path, df, session_state.state_stamp(path))


def test_an_edit_after_analysis_saves(main_window, told):
    path = main_window.session_manager.create_session("acme")
    main_window.session_path = path
    df = _orders("Fulfillable", "Fulfillable")
    session_state.save_state(path, df, None)  # what core.run_full_analysis writes
    main_window.actions_handler.on_analysis_complete((True, "report.xlsx", df, {}))

    main_window.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    main_window.save_session_state()

    assert told == []
    assert main_window._state_stamp == session_state.state_stamp(path)


def test_two_edits_in_a_row_both_save(main_window, told):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    for i in (0, 1):
        main_window.analysis_results_df.loc[i, "Order_Fulfillment_Status"] = "Not Fulfillable"
        main_window.save_session_state()
    assert told == []
    saved = pd.read_pickle(main_window.session_manager.get_analysis_dir(path) / "current_state.pkl")
    assert saved["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"] * 2


def test_a_save_after_another_pc_saved_is_refused(main_window, told):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    _another_pc_saves(path, _orders("Not Fulfillable", "Fulfillable"))

    main_window.analysis_results_df.loc[1, "Order_Fulfillment_Status"] = "Not Fulfillable"
    main_window.save_session_state()

    assert told == ["Another PC changed this session"]
