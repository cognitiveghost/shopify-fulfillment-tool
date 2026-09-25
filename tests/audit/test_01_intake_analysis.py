"""Audit 01: order data intake -> core analysis -> bulk operations.

Report: docs/audit/01-intake-analysis.md. Every AUDIT-01-k test fails because
of the bug it names and is marked xfail(strict=True); the fix removes the
marker. The unmarked tests pin what the audit verified correct.

Fixtures are synthetic and use the default Shopify / Bulgarian-ERP headers
(run_analysis with column_mappings=None). No production data lives here.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

import gui.actions_handler as actions_handler_module
from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool.analysis import (
    recalculate_statistics,
    run_analysis,
    toggle_order_fulfillment,
)
from shopify_tool.csv_utils import merge_csv_files, resolve_delimiter
from shopify_tool.set_decoder import import_sets_from_csv
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def stock(rows, lots=False):
    """rows: (sku, qty) or (sku, qty, expiry, batch) when lots=True."""
    cols = ["Артикул", "Наличност", "Годност", "Партида"] if lots else ["Артикул", "Наличност"]
    df = pd.DataFrame(rows, columns=cols)
    df["Име"] = df["Артикул"].astype(str) + " name"
    return df


def orders(rows):
    """rows: (order_name, sku, qty). Order-level columns on every line."""
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


def analyse(stock_df, orders_df, **kw):
    return run_analysis(stock_df, orders_df, NO_HISTORY, **kw)


def status(df, order):
    return set(df.loc[df["Order_Number"] == order, "Order_Fulfillment_Status"])


def final_stock(df, sku):
    return df.loc[df["SKU"] == sku, "Final_Stock"].iloc[0]


def window(df):
    mw = SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=None,
        current_client_id="AUDIT",
        active_profile_config={"settings": {}},
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    mw.undo_manager = UndoManager(mw)
    return mw


@pytest.fixture
def confirm(monkeypatch):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog, "ask", lambda *a, **k: True
    )


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-1: adding a product re-checks and re-deducts the order's existing lines",
)
def test_add_product_to_fulfillable_order_keeps_it_fulfillable():
    df, *_ = analyse(stock([("A", 2), ("B", 10)]), orders([("#1", "A", 2)]))
    assert status(df, "#1") == {"Fulfillable"} and final_stock(df, "A") == 0
    mw = window(df)
    handler = ActionsHandler(mw)
    stock_df = pd.DataFrame(
        {"SKU": ["A", "B"], "Stock": [2, 10], "Product_Name": ["a", "b"]}
    )
    handler._add_product_to_order(
        {"order_number": "#1", "sku": "B", "product_name": "b", "quantity": 1},
        stock_df,
        {"A": 0, "B": 10},
    )
    out = mw.analysis_results_df
    assert status(out, "#1") == {"Fulfillable"}
    assert final_stock(out, "A") == 0  # A's 2 units were allocated once, by the run
    assert final_stock(out, "B") == 9


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-2: undoing a status toggle restores the status but not Stock left",
)
def test_undo_of_toggle_restores_stock_left():
    df, *_ = analyse(stock([("A", 5)]), orders([("#1", "A", 2)]))
    mw = window(df)
    ActionsHandler(mw).toggle_fulfillment_status_for_order("#1")
    assert final_stock(mw.analysis_results_df, "A") == 5  # stock returned by Hold
    ok, _ = mw.undo_manager.undo()
    assert ok
    out = mw.analysis_results_df
    assert status(out, "#1") == {"Fulfillable"}
    assert final_stock(out, "A") == 3  # back to what the run left


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-3: bulk status change never moves Stock left; the single-order path does",
)
def test_bulk_hold_moves_stock_left_like_single_hold():
    df, *_ = analyse(stock([("A", 5)]), orders([("#1", "A", 2), ("#2", "A", 1)]))
    single = window(df.copy())
    ActionsHandler(single).toggle_fulfillment_status_for_order("#1")
    bulk = window(df.copy())
    ActionsHandler(bulk).bulk_change_status(["#1"], False)
    assert status(bulk.analysis_results_df, "#1") == {"Not Fulfillable"}
    assert final_stock(bulk.analysis_results_df, "A") == final_stock(
        single.analysis_results_df, "A"
    )


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-4: removing a fulfillable order does not return its stock to Stock left",
)
@pytest.mark.parametrize("verb", ["remove_entire_order", "bulk_delete_orders"])
def test_removing_fulfillable_order_returns_its_stock(verb, confirm):
    df, *_ = analyse(stock([("A", 3)]), orders([("#1", "A", 2), ("#2", "A", 2)]))
    assert status(df, "#1") == {"Fulfillable"} and status(df, "#2") == {"Not Fulfillable"}
    mw = window(df)
    handler = ActionsHandler(mw)
    if verb == "remove_entire_order":
        handler.remove_entire_order("#1")
    else:
        handler.bulk_delete_orders(["#1"])
    # #1 left the run, so the 2 units it held are free again.
    assert final_stock(mw.analysis_results_df, "A") == 3


def test_toggle_holds_a_fulfillable_order_whose_first_line_has_no_sku():
    df, *_ = analyse(stock([("A", 5)]), orders([("#1", None, 1), ("#1", "A", 2)]))
    sku_line = df["SKU"] == "A"
    assert df.loc[sku_line, "Order_Fulfillment_Status"].iloc[0] == "Fulfillable"
    assert final_stock(df, "A") == 3
    ok, _, out = toggle_order_fulfillment(df, "#1")
    assert ok
    # The person asked to hold a fulfillable order: it is held and A's 2 units
    # come back. Today the no-SKU first row makes it "force-fulfill" instead.
    assert out.loc[out["SKU"] == "A", "Order_Fulfillment_Status"].iloc[0] == "Not Fulfillable"
    assert final_stock(out, "A") == 5


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-6: a fulfillable order with a no-SKU line is counted completed AND not completed",
)
def test_stats_count_each_order_once():
    df, *_ = analyse(stock([("A", 5)]), orders([("#1", "A", 1), ("#1", None, 1)]))
    stats = recalculate_statistics(df)
    assert stats["total_orders_completed"] + stats["total_orders_not_completed"] == 1


def test_blank_stock_cell_is_not_unlimited_stock():
    # A blank cell in a numeric CSV column loads as NaN in a float column.
    df, *_ = analyse(stock([("A", float("nan")), ("B", 1)]), orders([("#1", "A", 3)]))
    assert status(df, "#1") == {"Not Fulfillable"}


def test_duplicate_stock_rows_count_the_same_with_or_without_lot_columns():
    plain, *_ = analyse(stock([("A", 3), ("A", 4)]), orders([("#1", "A", 1)]))
    lots, *_ = analyse(
        stock([("A", 3, "261230", "B1"), ("A", 4, "270101", "B2")], lots=True),
        orders([("#1", "A", 1)]),
    )
    assert lots["Stock"].iloc[0] == 7
    assert plain["Stock"].iloc[0] == lots["Stock"].iloc[0]


def test_no_order_line_silently_disappears():
    raw = orders([(None, "A", 1), ("#1", "B", 1)])
    df, *_ = analyse(stock([("A", 5), ("B", 5)]), raw)
    assert len(df) == len(raw)


def test_set_import_keeps_sku_text(tmp_path):
    p = tmp_path / "sets.csv"
    p.write_text("Set_SKU,Component_SKU,Component_Quantity\n0100,0042,2\n", encoding="utf-8")
    assert import_sets_from_csv(str(p)) == {"0100": [{"sku": "0042", "quantity": 2}]}


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-11: undoing a removal puts the rows back at the end, not where they were",
)
def test_undo_of_removed_order_restores_row_order():
    df, *_ = analyse(
        stock([("A", 9)]), orders([("#1", "A", 1), ("#2", "A", 1), ("#3", "A", 1)])
    )
    before = df["Order_Number"].tolist()
    mw = window(df)
    ActionsHandler(mw).remove_entire_order("#2")
    assert mw.undo_manager.undo()[0]
    assert mw.analysis_results_df["Order_Number"].tolist() == before


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-01-12: undo history cannot be saved once rows carry lot details",
)
def test_undo_history_survives_reopen_for_lot_tracked_stock(tmp_path):
    df, *_ = analyse(
        stock([("A", 5, "261230", "B1")], lots=True), orders([("#1", "A", 1)])
    )
    assert df["Lot_Details"].iloc[0]  # lot tracking is on
    mw = window(df)
    mw.session_path = str(tmp_path)
    mw.undo_manager = UndoManager(mw)
    mw.undo_manager.record_operation("remove_order", "x", {"order_number": "#1"}, df.copy())
    assert len(UndoManager(mw).operations) == 1  # a reopened session still has it


# ---------------------------------------------------------------------------
# Verified correct
# ---------------------------------------------------------------------------


def test_repeated_sku_lines_stay_separate_and_allocate_together():
    raw = orders([("#1", "A", 1), ("#1", "A", 1), ("#2", "B", 3)])
    df, *_ = analyse(stock([("A", 1), ("B", 3)]), raw)
    assert len(df) == len(raw)
    assert df["Quantity"].sum() == raw["Lineitem quantity"].sum()
    # Two lines of one unit each need two units; one is in stock.
    assert status(df, "#1") == {"Not Fulfillable"}
    assert status(df, "#2") == {"Fulfillable"}


def test_sets_multiply_quantities_and_unknown_skus_stay_visible():
    sets = {"SET": [{"sku": "A", "quantity": 3}, {"sku": "B", "quantity": 1}]}
    df, *_ = analyse(
        stock([("A", 6), ("B", 2)]),
        orders([("#1", "SET", 2), ("#2", "GHOST", 1)]),
        column_mappings={
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU", "Lineitem quantity": "Quantity"},
            "stock": {"Артикул": "SKU", "Наличност": "Stock", "Име": "Product_Name"},
            "set_decoders": sets,
        },
    )
    one = df[df["Order_Number"] == "#1"].set_index("SKU")["Quantity"]
    assert one.to_dict() == {"A": 6, "B": 2}
    assert status(df, "#1") == {"Fulfillable"}
    ghost = df[df["Order_Number"] == "#2"]
    assert len(ghost) == 1 and status(df, "#2") == {"Not Fulfillable"}
    assert "GHOST" in ghost["System_note"].iloc[0]


@pytest.mark.parametrize("mode", ["fifo", "multi_first"])
def test_competing_orders_never_double_allocate(mode):
    raw = orders([("#10", "A", 1), ("#9", "A", 1), ("#11", "A", 1), ("#11", "B", 1)])
    df, *_ = analyse(stock([("A", 1), ("B", 1)]), raw, mode=mode)
    shipped = df[df["Order_Fulfillment_Status"] == "Fulfillable"]
    assert shipped.loc[shipped["SKU"] == "A", "Quantity"].sum() == 1
    assert (df["Final_Stock"] >= 0).all()
    winner = shipped["Order_Number"].unique().tolist()
    # fifo: lowest number wins (#9 before #10, not lexicographic);
    # multi_first: the multi-line order goes first.
    assert winner == (["#9"] if mode == "fifo" else ["#11"])


def test_lot_rows_sum_and_earliest_expiry_goes_first():
    df, *_ = analyse(
        stock([("A", 2, "270101", "LATE"), ("A", 3, "261230", "EARLY")], lots=True),
        orders([("#1", "A", 4)]),
    )
    assert df["Stock"].iloc[0] == 5 and df["Final_Stock"].iloc[0] == 1
    lots = df["Lot_Details"].iloc[0]
    assert [(lot["batch"], lot["qty_allocated"]) for lot in lots] == [("EARLY", 3), ("LATE", 1)]


def test_folder_merge_conserves_lines_under_the_owning_file_rule(tmp_path):
    old, new = tmp_path / "old.csv", tmp_path / "new.csv"
    old.write_text("Name,Lineitem sku,Lineitem quantity\n#1,A,1\n#1,A,1\n#2,B,1\n", encoding="utf-8")
    new.write_text("Name,Lineitem sku,Lineitem quantity\n#2,B,5\n#3,C,1\n#3,C,1\n", encoding="utf-8")
    os.utime(old, (1, 1))
    merged, skipped = merge_csv_files(
        [str(old), str(new)], "auto", "orders", owner_key="Name", add_source_column=False
    )
    got = sorted(map(tuple, merged.astype(str).values.tolist()))
    assert got == sorted([("#1", "A", "1"), ("#1", "A", "1"), ("#2", "B", "5"), ("#3", "C", "1"), ("#3", "C", "1")])
    assert skipped == 1


def test_auto_delimiter_reads_semicolon_file_with_commas_in_text(tmp_path):
    p = tmp_path / "stock.csv"
    p.write_text('Артикул;Име;Наличност\nA;"Cream, 50 ml";4\nB;"Soap, bar";2\n', encoding="utf-8-sig")
    assert resolve_delimiter(str(p), "auto", "stock") == ";"


def test_bulk_status_change_touches_every_line_of_each_order():
    df, *_ = analyse(stock([("A", 5), ("B", 5)]), orders([("#1", "A", 1), ("#1", "B", 1), ("#2", "A", 1)]))
    mw = window(df)
    ActionsHandler(mw).bulk_change_status(["#1"], False)
    out = mw.analysis_results_df
    assert status(out, "#1") == {"Not Fulfillable"} and status(out, "#2") == {"Fulfillable"}
    assert mw.undo_manager.undo()[0]
    assert status(mw.analysis_results_df, "#1") == {"Fulfillable"}


def test_undo_of_bulk_tag_and_bulk_delete_restores_content(confirm):
    df, *_ = analyse(stock([("A", 5)]), orders([("#1", "A", 1), ("#2", "A", 1)]))
    mw = window(df)
    handler = ActionsHandler(mw)
    snapshot = df.copy()
    handler.bulk_add_tag(["#1"], "FRAGILE")
    handler.bulk_delete_orders(["#2"])
    assert mw.undo_manager.undo()[0] and mw.undo_manager.undo()[0]
    out = mw.analysis_results_df.sort_values("Order_Number").reset_index(drop=True)
    cols = ["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status", "Internal_Tags"]
    pd.testing.assert_frame_equal(out[cols], snapshot[cols], check_dtype=False)


def test_order_level_fields_fill_within_an_order_only():
    raw = pd.DataFrame(
        {
            "Name": ["#1", "#1", "#2"],
            "Lineitem sku": ["A", "A", "A"],
            "Lineitem quantity": [1, 1, 1],
            "Tags": ["VIP", None, None],
            "Shipping Method": ["DHL", None, None],
        }
    )
    df, *_ = analyse(stock([("A", 9)]), raw)
    assert df.loc[df["Order_Number"] == "#1", "Tags"].tolist() == ["VIP", "VIP"]
    assert df.loc[df["Order_Number"] == "#2", "Tags"].isna().all()
    assert json.dumps(df.loc[df["Order_Number"] == "#2", "Shipping_Provider"].tolist()) == '["Unknown"]'
