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

import gui.actions_handler as actions_handler_module
from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper


def _window(df):
    window = SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=None,
        current_client_id="TEST",
        active_profile_config={"settings": {}},
    )
    window.selection_helper = SelectionHelper(main_window=window)
    window.undo_manager = UndoManager(window)
    return window


def _final_stock(df, sku):
    return df.loc[df["SKU"] == sku, "Final_Stock"].iloc[0]


@pytest.fixture
def confirm(monkeypatch):
    monkeypatch.setattr(actions_handler_module.ConfirmDialog, "ask", lambda *a, **k: True)


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


def test_undo_of_bulk_delete_restores_row_order(confirm):
    df = pd.DataFrame({"Order_Number": ["#1", "#2", "#3"], "SKU": ["A"] * 3, "Quantity": [1] * 3,
                       "Order_Fulfillment_Status": ["Fulfillable"] * 3,
                       "Stock": [9] * 3, "Final_Stock": [6.0] * 3})
    mw = _window(df)
    ActionsHandler(mw).bulk_delete_orders(["#1", "#3"])
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == ["#1", "#2", "#3"]
