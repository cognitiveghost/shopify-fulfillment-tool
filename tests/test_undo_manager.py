"""Regression tests for shopify_tool.undo_manager.UndoManager bulk-op undo.

Root cause: record_operation() serializes affected_rows_before via
to_dict('records'), and undo() reconstructs it via pd.DataFrame(records) --
this round-trip discards the DataFrame's original index labels and replaces
them with a fresh 0..n-1 range. The bulk undo handlers used to key off that
index directly (`if idx in df.index: df.loc[idx, ...] = ...`), so as soon as
the bulk selection's real index labels weren't already 0..n-1, undo() wrote
into the wrong rows (or no rows at all) while still reporting success. Fixed
by matching on Order_Number instead, mirroring the pattern already used by
the single-row undo handlers (_undo_toggle_status et al).
"""
from types import SimpleNamespace

import pandas as pd
import pytest

from shopify_tool.undo_manager import UndoManager


@pytest.fixture
def mw():
    df = pd.DataFrame(
        {
            "Order_Number": ["A", "B", "C", "D", "E"],
            "Order_Fulfillment_Status": ["Fulfillable"] * 5,
            "Internal_Tags": ["[]"] * 5,
        }
    )
    return SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        current_client_id="1",
        session_path=None,
    )


def test_undo_bulk_change_status_restores_the_selected_orders(mw):
    """Selection lands on non-leading index labels [2, 3] -- the exact shape
    that previously restored into rows [0, 1] (A, B) instead of [2, 3] (C, D)."""
    um = UndoManager(mw)
    selected = [2, 3]
    affected_before = mw.analysis_results_df.loc[selected].copy()
    mw.analysis_results_df.loc[selected, "Order_Fulfillment_Status"] = "Not Fulfillable"
    um.record_operation(
        "bulk_change_status", "Bulk status C,D", {"affected_indexes": selected}, affected_before
    )

    ok, _ = um.undo()

    by_order = mw.analysis_results_df.set_index("Order_Number")["Order_Fulfillment_Status"]
    assert ok is True
    assert by_order.loc["C"] == "Fulfillable"
    assert by_order.loc["D"] == "Fulfillable"
    assert by_order.loc["A"] == "Fulfillable"  # untouched
    assert by_order.loc["B"] == "Fulfillable"  # untouched


def test_undo_bulk_add_tag_restores_the_selected_orders(mw):
    um = UndoManager(mw)
    representative = [2, 3]
    affected_before = mw.analysis_results_df.loc[representative].copy()
    mw.analysis_results_df.loc[representative, "Internal_Tags"] = '["fragile"]'
    um.record_operation(
        "bulk_add_tag",
        "Bulk add tag",
        {"affected_indexes": representative, "order_numbers": ["C", "D"]},
        affected_before,
    )

    ok, _ = um.undo()

    by_order = mw.analysis_results_df.set_index("Order_Number")["Internal_Tags"]
    assert ok is True
    assert by_order.loc["C"] == "[]"
    assert by_order.loc["D"] == "[]"
    assert by_order.loc["A"] == "[]"  # untouched


@pytest.fixture
def mw_multiline():
    df = pd.DataFrame(
        {
            "Order_Number": ["A", "A", "B"],
            "SKU": ["S1", "S2", "S1"],
            "Internal_Tags": ["[]", "[]", "[]"],
        }
    )
    return SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        current_client_id="1",
        session_path=None,
    )


def test_undo_bulk_add_tag_restores_every_line_of_a_multiline_order(mw_multiline):
    um = UndoManager(mw_multiline)
    mask = mw_multiline.analysis_results_df["Order_Number"] == "A"
    affected_before = mw_multiline.analysis_results_df[mask].copy()
    mw_multiline.analysis_results_df.loc[mask, "Internal_Tags"] = '["fragile"]'
    um.record_operation(
        "bulk_add_tag", "Bulk add tag", {"order_numbers": ["A"]}, affected_before
    )

    ok, _ = um.undo()

    tags = mw_multiline.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert ok is True
    assert tags.loc["S2"] == "[]"  # order A, line 2 -- must ALSO be restored
    assert mw_multiline.analysis_results_df.iloc[0]["Internal_Tags"] == "[]"  # order A, line 1 -- restored
    assert mw_multiline.analysis_results_df.iloc[2]["Internal_Tags"] == "[]"  # order B untouched


# --- Stock left and row order (AUDIT-01-2, -11; spec 2026-09-25 §4.6) ---

from unittest.mock import Mock

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper


def _window(df, session_path=None):
    window = SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=session_path,
        current_client_id="TEST",
        active_profile_config={"settings": {}},
    )
    window.selection_helper = SelectionHelper(main_window=window)
    window.undo_manager = UndoManager(window)
    return window


def _final_stock(df, sku):
    return df.loc[df["SKU"] == sku, "Final_Stock"].iloc[0]


def test_undo_of_hold_on_mixed_order_restores_each_line():
    df = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "GIFT", "A"],
        "Has_SKU": [True, True, True],
        "Quantity": [2, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Fulfillable"],
        "Stock": [3, 0, 3],
        "Final_Stock": [2.0, 0.0, 2.0],
    })
    mw = _window(df)
    # #1 is mixed, so R1 reads it as blocked. Hold still writes every line.
    ActionsHandler(mw).bulk_change_status(["#1"], False)
    assert mw.undo_manager.undo()[0]
    out = mw.analysis_results_df
    assert out["Order_Fulfillment_Status"].tolist() == ["Fulfillable", "Not Fulfillable", "Fulfillable"]
    assert _final_stock(out, "A") == 2  # only #2 draws; the mixed #1 is blocked


def test_undo_without_row_positions_still_appends():
    df = pd.DataFrame({"Order_Number": ["#1", "#2"], "SKU": ["A", "A"], "Quantity": [1, 1],
                       "Order_Fulfillment_Status": ["Fulfillable"] * 2,
                       "Stock": [5, 5], "Final_Stock": [3.0, 3.0]})
    mw = _window(df)
    ActionsHandler(mw).remove_entire_order("#1")
    mw.undo_manager.operations[-1].pop("row_positions")  # a record from an older build
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == ["#2", "#1"]
    assert _final_stock(mw.analysis_results_df, "A") == 3


def test_undo_of_bulk_delete_restores_row_order():
    df = pd.DataFrame({"Order_Number": ["#1", "#2", "#3"], "SKU": ["A"] * 3, "Quantity": [1] * 3,
                       "Order_Fulfillment_Status": ["Fulfillable"] * 3,
                       "Stock": [9] * 3, "Final_Stock": [6.0] * 3})
    mw = _window(df)
    ActionsHandler(mw).bulk_delete_orders(["#1", "#3"])
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == ["#1", "#2", "#3"]


# --- Undo records hold the changed columns; the file goes through the queue (AUDIT-08-U2) ---

import json

from session_queue_support import gated

from gui.session_write_queue import SessionWriteQueue

UNDO_FRAME = pd.DataFrame({
    "Order_Number": ["#1", "#2"], "SKU": ["A", "B"], "Quantity": [1, 1],
    "Order_Fulfillment_Status": ["Fulfillable"] * 2, "Stock": [5, 5], "Final_Stock": [4.0, 4.0],
    "Product_Name": ["a", "b"], "Internal_Tags": ["[]", "[]"], "Status_Note": ["", ""],
})


def test_an_edit_record_holds_only_the_order_and_changed_columns(tmp_path):
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    ActionsHandler(mw).bulk_change_status(["#1"], False)
    op = mw.undo_manager.operations[-1]
    assert set(op["affected_rows_before"][0]) == {"Order_Number", "Order_Fulfillment_Status"}


def test_a_removal_record_keeps_whole_rows(tmp_path):
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    ActionsHandler(mw).remove_entire_order("#1")
    op = mw.undo_manager.operations[-1]
    assert set(op["affected_rows_before"][0]) == set(UNDO_FRAME.columns)


def test_a_whole_row_record_from_an_older_build_still_undoes(tmp_path):
    (tmp_path / "analysis").mkdir()
    whole_row = {"Order_Number": "#1", "SKU": "A", "Quantity": 1, "Order_Fulfillment_Status": "Fulfillable",
                 "Stock": 5, "Final_Stock": 4.0, "Product_Name": "a", "Internal_Tags": "[]", "Status_Note": ""}
    op = {"id": 1, "timestamp": "2026-10-01T10:00:00+03:00", "type": "toggle_status", "description": "t",
          "params": {"order_number": "#1"}, "affected_rows_before": [whole_row], "row_positions": [0],
          "stats_before": None, "client_id": "TEST", "session_path": str(tmp_path)}
    (tmp_path / "analysis" / "operations_history.json").write_text(
        json.dumps({"operations": [op], "current_position": 1, "max_history": 20}), encoding="utf-8")
    mw = _window(UNDO_FRAME.iloc[:1].assign(Order_Fulfillment_Status="Not Fulfillable"), session_path=str(tmp_path))
    mw.undo_manager.reload_session_history()
    ok, _ = mw.undo_manager.undo()
    assert ok and mw.analysis_results_df["Order_Fulfillment_Status"].tolist() == ["Fulfillable"]


def test_the_undo_file_is_written_by_the_queue(tmp_path, qapp):
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    mw.write_queue = SessionWriteQueue()
    history = mw.undo_manager._get_history_path()
    gate = gated(mw.write_queue)
    try:
        mw.undo_manager.record_operation("toggle_status", "t", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
        assert not history.exists()
    finally:
        gate.set()
    assert mw.write_queue.flush(timeout=5)
    assert json.loads(history.read_text(encoding="utf-8"))["current_position"] == 1


# --- Undo history per PC (AUDIT-08-U4) ---


def test_two_pcs_keep_their_own_undo_history(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    a = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    a.undo_manager.record_operation("toggle_status", "by A", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    monkeypatch.setenv("COMPUTERNAME", "PC-B")
    b = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    b.undo_manager.record_operation("toggle_status", "by B", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    a.undo_manager.reload_session_history()
    assert [op["description"] for op in a.undo_manager.operations] == ["by A"]
    assert a.undo_manager._get_history_path().name == "operations_history_PC-A.json"


def test_a_legacy_shared_history_still_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    (tmp_path / "analysis").mkdir()
    op = {"id": 1, "timestamp": "2026-10-01T10:00:00+03:00", "type": "toggle_status", "description": "legacy",
          "params": {"order_number": "#1"}, "affected_rows_before": [], "row_positions": [],
          "stats_before": None, "client_id": "TEST", "session_path": str(tmp_path)}
    legacy = tmp_path / "analysis" / "operations_history.json"
    legacy.write_text(json.dumps({"operations": [op], "current_position": 1, "max_history": 20}), encoding="utf-8")
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    assert [op["description"] for op in mw.undo_manager.operations] == ["legacy"]
    mw.undo_manager.record_operation("toggle_status", "new", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    assert json.loads(legacy.read_text(encoding="utf-8"))["current_position"] == 1  # never written


def test_a_pc_name_becomes_a_safe_file_name(monkeypatch):
    from shopify_tool import undo_manager

    monkeypatch.setenv("COMPUTERNAME", "WH PC/2:ä")
    assert undo_manager._pc_name() == "WH_PC_2_ä"


def test_non_latin_pc_names_of_one_length_get_their_own_undo_files(monkeypatch):
    from shopify_tool import undo_manager

    monkeypatch.setenv("COMPUTERNAME", "СКЛАД")
    first = undo_manager._pc_name()
    monkeypatch.setenv("COMPUTERNAME", "ОФИСИ")
    assert undo_manager._pc_name() != first


def test_recording_after_undo_logs_how_many_steps_it_cleared(tmp_path, caplog):
    """AUDIT-08-U5: the count was taken after the slice, so it always said 0."""
    import logging

    mw = _window(UNDO_FRAME.copy())
    for n in range(3):
        mw.undo_manager.record_operation("toggle_status", f"op {n}", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    mw.undo_manager.undo()
    mw.undo_manager.undo()
    with caplog.at_level(logging.INFO, logger="shopify_tool.undo_manager"):
        mw.undo_manager.record_operation("toggle_status", "op 3", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    assert "Cleared 2 future operations" in caplog.text


def test_a_rerun_clears_every_pcs_undo_history(tmp_path, monkeypatch):
    """AUDIT-08-U1 across PCs: every PC's steps point at the previous run's frame."""
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    stale = {"operations": [{"id": 1}], "current_position": 1, "max_history": 20}
    for name in ("operations_history_PC-B.json", "operations_history.json"):
        (analysis / name).write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    mw.undo_manager.clear_history()
    assert sorted(p.name for p in analysis.iterdir()) == ["operations_history_PC-A.json"]


def test_an_edit_right_after_a_rerun_does_not_cancel_the_clear(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "operations_history_PC-B.json").write_text("{}", encoding="utf-8")
    mw = _window(UNDO_FRAME.copy(), session_path=str(tmp_path))
    mw.write_queue = SessionWriteQueue()
    gate = gated(mw.write_queue)
    try:
        mw.undo_manager.clear_history()
        mw.undo_manager.record_operation("toggle_status", "t", {"order_number": "#1"}, UNDO_FRAME.iloc[:1])
    finally:
        gate.set()
    assert mw.write_queue.flush(timeout=5)
    assert not (tmp_path / "analysis" / "operations_history_PC-B.json").exists()
