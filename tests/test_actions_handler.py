"""Regression test for gui.actions_handler.ActionsHandler.remove_item_from_order.

Root cause: the handler used to match rows by (Order_Number, SKU) alone, so an
order with two lines sharing the same SKU would have both lines deleted when
the user only meant to remove one. The fix threads the clicked row's position
through from the context menu and removes exactly that row.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper


@pytest.fixture
def mw():
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 1},
            {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 2},
            {"Order_Number": "1001", "SKU": "SKU-B", "Lineitem_Quantity": 1},
        ]
    )
    return SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
    )


def test_remove_item_removes_only_the_clicked_duplicate_sku_line(mw, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    handler = ActionsHandler(mw)

    handler.remove_item_from_order("1001", "SKU-A", row_position=1)

    remaining = mw.analysis_results_df
    assert len(remaining) == 2
    sku_a_rows = remaining[remaining["SKU"] == "SKU-A"]
    assert len(sku_a_rows) == 1
    assert sku_a_rows.iloc[0]["Lineitem_Quantity"] == 1


def test_remove_item_aborts_if_row_no_longer_matches(mw, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    handler = ActionsHandler(mw)

    # row_position 2 is SKU-B, not SKU-A -- table changed since menu opened
    handler.remove_item_from_order("1001", "SKU-A", row_position=2)

    assert len(mw.analysis_results_df) == 3


def test_remove_item_aborts_if_snapshot_no_longer_matches(mw, monkeypatch):
    """A same-position row can still match (Order_Number, SKU) after the table
    changes if another duplicate-SKU line has taken that slot. The row
    snapshot, captured in full when the menu opened, must catch this even
    when order/SKU alone would pass.
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    handler = ActionsHandler(mw)

    stale_snapshot = {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 2}

    # row_position 0 is still Order 1001 / SKU-A, but with Lineitem_Quantity=1
    # now -- a different duplicate-SKU line than the one the snapshot captured.
    handler.remove_item_from_order(
        "1001", "SKU-A", row_position=0, row_snapshot=stale_snapshot
    )

    assert len(mw.analysis_results_df) == 3


@pytest.fixture
def mw_with_tags():
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "SKU": "A1", "Quantity": 1, "Internal_Tags": "[]"},
            {"Order_Number": "1001", "SKU": "A2", "Quantity": 1, "Internal_Tags": "[]"},
            {"Order_Number": "1002", "SKU": "B1", "Quantity": 1, "Internal_Tags": '["URGENT"]'},
        ]
    )
    mw = SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        active_profile_config={"tag_categories": {}},
        _update_all_views=Mock(),
    )
    mw.selection_helper = SelectionHelper(table_view=None, proxy_model=None, main_window=mw)
    return mw


def test_bulk_add_tag_writes_every_row_of_a_multi_line_order(mw_with_tags, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *a, **k: ("--- Custom Tag ---", True)
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("FRAGILE", True))

    mw_with_tags.selection_helper.checked_rows = {0}  # only line 1 of order 1001 checked
    handler = ActionsHandler(mw_with_tags)

    handler.bulk_add_tag()

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert '"FRAGILE"' in tags.loc["A1"]
    assert '"FRAGILE"' in tags.loc["A2"]  # order 1001's other line, not just the checked one
    assert '"FRAGILE"' not in tags.loc["B1"]  # different order, untouched


def test_bulk_remove_tag_removes_from_every_row_of_a_multi_line_order(mw_with_tags, monkeypatch):
    df = mw_with_tags.analysis_results_df
    df.loc[df["Order_Number"] == "1001", "Internal_Tags"] = '["URGENT"]'

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *a, **k: ("URGENT", True)
    )

    mw_with_tags.selection_helper.checked_rows = {0}  # only line 1 of order 1001 checked
    handler = ActionsHandler(mw_with_tags)

    handler.bulk_remove_tag()

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert tags.loc["A1"] == "[]"
    assert tags.loc["A2"] == "[]"  # order 1001's other line, not just the checked one
    assert tags.loc["B1"] == '["URGENT"]'  # different order, untouched
