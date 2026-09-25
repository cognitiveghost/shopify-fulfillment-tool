"""Bundle 14: the bulk verbs, once the dialogs are gone."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtWidgets import QFileDialog

import gui.actions_handler as actions_handler_module
from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper


def test_no_input_dialog_survives_in_actions_handler():
    source = Path("gui/actions_handler.py").read_text(encoding="utf-8")
    assert "QInputDialog" not in source
    assert "Please select orders first" not in source


@pytest.fixture
def mw():
    df = pd.DataFrame(
        [
            {
                "Order_Number": "10443",
                "SKU": "TS-4409-B",
                "Quantity": 1,
                "Order_Fulfillment_Status": "Fulfillable",
                "Internal_Tags": '["FRAGILE"]',
            },
            {
                "Order_Number": "10443",
                "SKU": "TS-0001-X",
                "Quantity": 1,
                "Order_Fulfillment_Status": "Fulfillable",
                "Internal_Tags": '["FRAGILE"]',
            },
            {
                "Order_Number": "10444",
                "SKU": "TS-4409-B",
                "Quantity": 1,
                "Order_Fulfillment_Status": "Fulfillable",
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "10444",
                "SKU": "TS-0002-Y",
                "Quantity": 1,
                "Order_Fulfillment_Status": "Fulfillable",
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "10445",
                "SKU": "TS-9999-Z",
                "Quantity": 1,
                "Order_Fulfillment_Status": "Fulfillable",
                "Internal_Tags": "[]",
            },
        ]
    )
    window = SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        undo_last_operation=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        active_profile_config={"tag_categories": {}},
        _update_all_views=Mock(),
        results_bridge=Mock(),
        session_path=None,
        ui_manager=Mock(),
    )
    window.selection_helper = SelectionHelper(main_window=window)
    return window


@pytest.fixture
def handler(mw):
    return ActionsHandler(mw)


def test_bulk_change_status_writes_from_its_arguments(handler, mw):
    handler.bulk_change_status(["10443", "10444"], False)
    written = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"].isin(["10443", "10444"]),
        "Order_Fulfillment_Status",
    ]
    assert set(written) == {"Not Fulfillable"}


def test_bulk_change_status_records_undo_with_the_frozen_params(handler, mw):
    mw.analysis_results_df["Order_Fulfillment_Status"] = "Not Fulfillable"  # Mark needs something to change
    handler.bulk_change_status(["10443"], True)
    call = mw.undo_manager.record_operation.call_args.kwargs
    assert call["operation_type"] == "bulk_change_status"
    assert set(call["params"]) == {"is_fulfillable", "affected_indexes"}


def test_bulk_change_status_toasts_with_undo(handler, mw):
    mw.analysis_results_df["Order_Fulfillment_Status"] = "Not Fulfillable"  # Mark needs something to change
    handler.bulk_change_status(["10443", "10444"], True)
    mw.results_bridge.raise_toast.assert_called_once_with(
        "2 orders marked fulfillable", undoable=True
    )


def test_bulk_add_tag_skips_orders_that_already_carry_it(handler, mw):
    handler.bulk_add_tag(["10443", "10444"], "FRAGILE")
    handler.bulk_add_tag(["10443", "10444"], "FRAGILE")
    tags = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"] == "10443", "Internal_Tags"
    ].iloc[0]
    assert tags.count("FRAGILE") == 1


def test_bulk_add_tag_toasts_with_undo(handler, mw):
    handler.bulk_add_tag(["10444", "10445"], "URGENT")
    mw.results_bridge.raise_toast.assert_called_once_with(
        "URGENT added to 2 orders", undoable=True
    )


def test_bulk_add_tag_toasts_the_count_the_popover_promised(handler, mw):
    """Spec section 6: "its count matches the count on the button that caused
    it". 10443 already carries FRAGILE, so the popover's verb reads "Add to
    2 orders" and the toast has to say two, not the whole selection's three.
    """
    handler.bulk_add_tag(["10443", "10444", "10445"], "FRAGILE")
    mw.results_bridge.raise_toast.assert_called_once_with(
        "FRAGILE added to 2 orders", undoable=True
    )


def test_bulk_remove_tag_toasts_only_the_orders_that_carried_it(handler, mw):
    """The same rule the other way: only 10443 has FRAGILE to lose."""
    handler.bulk_remove_tag(["10443", "10444", "10445"], "FRAGILE")
    mw.results_bridge.raise_toast.assert_called_once_with(
        "FRAGILE removed from 1 order", undoable=True
    )


def test_bulk_remove_tag_writes_from_its_arguments(handler, mw):
    handler.bulk_remove_tag(["10443"], "FRAGILE")
    tags = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"] == "10443", "Internal_Tags"
    ].iloc[0]
    assert "FRAGILE" not in tags


def test_bulk_remove_tag_toasts_with_undo(handler, mw):
    handler.bulk_remove_tag(["10443"], "FRAGILE")
    mw.results_bridge.raise_toast.assert_called_once_with(
        "FRAGILE removed from 1 order", undoable=True
    )


def test_bulk_delete_orders_confirms_before_it_writes(handler, mw, monkeypatch):
    asked = {}

    def fake_ask(parent, *, title, body, verb):
        asked.update(title=title, verb=verb)
        return False

    monkeypatch.setattr(actions_handler_module.ConfirmDialog, "ask", fake_ask)
    before = len(mw.analysis_results_df)
    handler.bulk_delete_orders(["10443"])
    assert asked["title"] == "Exclude 1 order from the run?"
    assert asked["verb"] == "Exclude 1 order"
    assert len(mw.analysis_results_df) == before


def test_bulk_delete_orders_writes_when_confirmed(handler, mw, monkeypatch):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog,
        "ask",
        lambda parent, **kw: True,
    )
    handler.bulk_delete_orders(["10443"])
    assert "10443" not in set(mw.analysis_results_df["Order_Number"])
    mw.results_bridge.raise_toast.assert_called_once_with(
        "1 order excluded from the run", undoable=True
    )


def test_bulk_remove_sku_from_orders_confirms_before_it_writes(
    handler, mw, monkeypatch
):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog, "ask", lambda p, **k: False
    )
    before = len(mw.analysis_results_df)
    handler.bulk_remove_sku_from_orders(["10443", "10444"], "TS-4409-B")
    assert len(mw.analysis_results_df) == before


def test_bulk_remove_sku_from_orders_writes_when_confirmed(handler, mw, monkeypatch):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog, "ask", lambda p, **k: True
    )
    handler.bulk_remove_sku_from_orders(["10443", "10444"], "TS-4409-B")
    remaining = mw.analysis_results_df
    assert "TS-4409-B" not in set(remaining["SKU"])
    assert {"10443", "10444"} <= set(remaining["Order_Number"])
    mw.results_bridge.raise_toast.assert_called_once_with(
        "TS-4409-B removed from 2 orders", undoable=True
    )


def test_bulk_remove_orders_with_sku_confirms_before_it_writes(
    handler, mw, monkeypatch
):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog, "ask", lambda p, **k: False
    )
    before = len(mw.analysis_results_df)
    handler.bulk_remove_orders_with_sku(["10443", "10444"], "TS-4409-B")
    assert len(mw.analysis_results_df) == before


def test_bulk_remove_orders_with_sku_writes_when_confirmed(handler, mw, monkeypatch):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog, "ask", lambda p, **k: True
    )
    handler.bulk_remove_orders_with_sku(["10443", "10444"], "TS-4409-B")
    assert set(mw.analysis_results_df["Order_Number"]) == {"10445"}
    mw.results_bridge.raise_toast.assert_called_once_with(
        "2 orders containing TS-4409-B removed", undoable=True
    )


def test_bulk_export_selection_writes_the_file_and_toasts(
    handler, mw, monkeypatch, tmp_path
):
    target = tmp_path / "s.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(target), ""),
    )
    handler.bulk_export_selection(["10443"], "csv")
    assert target.exists()
    mw.results_bridge.raise_toast.assert_called_once_with(
        f"1 order exported to {target.name}", undoable=False
    )


def test_bulk_change_status_works_for_int_order_numbers(handler, mw):
    """A non-Shopify client: int64 Order_Number, page sends strings."""
    df = mw.analysis_results_df
    mw.analysis_results_df = df.assign(Order_Number=df["Order_Number"].astype(int))
    handler.bulk_change_status(["10443", "10444"], False)
    written = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"].isin([10443, 10444]),
        "Order_Fulfillment_Status",
    ]
    assert set(written) == {"Not Fulfillable"}


def test_update_undo_button_pushes_availability_to_the_page(handler, mw):
    mw.undo_manager.can_undo.return_value = True
    handler._update_undo_button()
    mw.results_bridge.set_undo_available.assert_called_with(True)


# --- Stock left: the ledger frames (AUDIT-01-3, -4; spec 2026-09-25 §4.3, §4.5) ---

from shopify_tool.analysis import run_analysis
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def _stock(rows):
    df = pd.DataFrame(rows, columns=["Артикул", "Наличност"])
    df["Име"] = df["Артикул"].astype(str) + " name"
    return df


def _orders(rows):
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


def _ledger_window(df):
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


def _status(df, order):
    return set(df.loc[df["Order_Number"] == order, "Order_Fulfillment_Status"])


def _final_stock(df, sku):
    return df.loc[df["SKU"] == sku, "Final_Stock"].iloc[0]


def test_bulk_mark_fulfillable_skips_what_stock_left_cannot_cover():
    df, *_ = run_analysis(_stock([("A", 3)]), _orders([("#1", "A", 2), ("#2", "A", 2), ("#3", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    ActionsHandler(mw).bulk_change_status(["#1"], False)  # free #1's 2 units: 3 left
    ActionsHandler(mw).bulk_change_status(["#1", "#2", "#3"], True)
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Fulfillable"}
    assert _status(out, "#2") == {"Not Fulfillable"} and _status(out, "#3") == {"Not Fulfillable"}
    assert _final_stock(out, "A") == 1
    mw.results_bridge.raise_toast.assert_called_with(
        "1 order marked fulfillable · 2 skipped: not enough stock", undoable=True
    )


def test_bulk_mark_fulfillable_with_nothing_covered_records_no_undo():
    df, *_ = run_analysis(_stock([("A", 1)]), _orders([("#1", "A", 1), ("#2", "A", 5)]), NO_HISTORY)
    mw = _ledger_window(df)
    before = len(mw.undo_manager.operations)
    ActionsHandler(mw).bulk_change_status(["#2"], True)
    assert len(mw.undo_manager.operations) == before
    mw.results_bridge.raise_toast.assert_called_with(
        "No orders marked fulfillable: not enough stock for 1 order", undoable=False
    )


def test_add_product_to_a_held_order_keeps_it_held_and_draws_nothing():
    df, *_ = run_analysis(_stock([("A", 5), ("B", 10)]), _orders([("#1", "A", 2)]), NO_HISTORY)
    mw = _ledger_window(df)
    handler = ActionsHandler(mw)
    handler.toggle_fulfillment_status_for_order("#1")  # hold
    stock_df = pd.DataFrame({"SKU": ["A", "B"], "Stock": [5, 10], "Product_Name": ["a", "b"]})
    handler._add_product_to_order(
        {"order_number": "#1", "sku": "B", "product_name": "b", "quantity": 1}, stock_df, {}
    )
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Not Fulfillable"}
    assert _final_stock(out, "A") == 5 and _final_stock(out, "B") == 10


def test_add_unlisted_sku_keeps_it_unlisted_and_the_order_fulfillable():
    # X is in the orders but not the stock file: unlisted, so it never blocks.
    df, *_ = run_analysis(_stock([("A", 5)]), _orders([("#1", "A", 1), ("#1", "X", 1)]), NO_HISTORY)
    mw = _ledger_window(df)
    handler = ActionsHandler(mw)
    handler.bulk_change_status(["#1"], True)
    assert _status(mw.analysis_results_df, "#1") == {"Fulfillable"}
    stock_df = pd.DataFrame({"SKU": ["A"], "Stock": [5], "Product_Name": ["a"]})
    handler._add_product_to_order(
        {"order_number": "#1", "sku": "X", "product_name": "x", "quantity": 1}, stock_df, {}
    )
    out = mw.analysis_results_df
    assert _status(out, "#1") == {"Fulfillable"}
    assert out.loc[out["SKU"] == "X", "Final_Stock"].isna().all()
    assert _final_stock(out, "A") == 4
