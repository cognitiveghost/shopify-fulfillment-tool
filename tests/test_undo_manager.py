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
