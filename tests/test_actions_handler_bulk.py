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
    handler.bulk_change_status(["10443"], True)
    call = mw.undo_manager.record_operation.call_args.kwargs
    assert call["operation_type"] == "bulk_change_status"
    assert set(call["params"]) == {"is_fulfillable", "affected_indexes"}


def test_bulk_change_status_toasts_with_undo(handler, mw):
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


def test_update_undo_button_pushes_availability_to_the_page(handler, mw):
    mw.undo_manager.can_undo.return_value = True
    handler._update_undo_button()
    mw.results_bridge.set_undo_available.assert_called_with(True)
