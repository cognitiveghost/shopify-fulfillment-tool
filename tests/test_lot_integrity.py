"""The #1221 incident (REVE 2026-09-28_1) and its neighbours.

Spec: docs/superpowers/specs/2026-09-28-lot-labels-follow-quantity-design.md.
Synthetic, lot-tracked fixtures; no production data.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool.analysis import run_analysis
from shopify_tool.packing_lists import create_packing_list
from shopify_tool.stock_export import create_stock_export
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def lot_stock(rows):
    """(sku, qty, expiry, batch) -> a stock file with lot columns."""
    df = pd.DataFrame(rows, columns=["Артикул", "Наличност", "Годност", "Партида"])
    df["Име"] = df["Артикул"].astype(str) + " name"
    return df


def order_rows(rows):
    """(order, sku, qty)"""
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


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
        current_client_id="TEST",
        active_profile_config={"settings": {}},
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    mw.undo_manager = UndoManager(mw)
    return mw


def line_of(mw, order, sku):
    """The index remove_line expects: the line's position within its order."""
    df = mw.analysis_results_df
    own = df[df["Order_Number"] == order].reset_index(drop=True)
    return int(own.index[own["SKU"] == sku][0])


def export_totals(path):
    e = pd.read_excel(path, dtype={"Артикул": str})
    return e.groupby("Артикул")["Брой"].sum().to_dict()


def packing_lines(path):
    p = pd.read_excel(path, dtype={"Order_Number": str, "SKU": str})
    return p.groupby(["Order_Number", "SKU"])["Quantity"].sum().to_dict()


def add(handler, order, sku, qty):
    stock_df = pd.DataFrame({"SKU": [sku], "Stock": [50], "Product_Name": [sku.lower()]})
    handler._add_product_to_order(
        {"order_number": order, "sku": sku, "product_name": sku.lower(), "quantity": qty},
        stock_df,
        {},
    )


def incident_run():
    stock = lot_stock([
        ("L", 11, "20270101", "B1"), ("M", 12, "20270101", "B1"),
        ("S", 20, "20270101", "B1"), ("SM", 25, "20270101", "B1"),
        ("R", 46, "20270101", "B1"),
    ])
    orders = order_rows([
        ("#1221", "SM", 1), ("#1221", "L", 3), ("#1221", "M", 4), ("#1221", "S", 4),
        ("#1209", "R", 1),
    ])
    df, *_ = run_analysis(stock, orders, NO_HISTORY)
    return df


def test_the_1221_edits_export_exactly_what_the_order_holds(tmp_path):
    mw = window(incident_run())
    h = ActionsHandler(mw)
    # The session's operation history, in order.
    h.remove_line("#1221", line_of(mw, "#1221", "SM"), "SM")
    h.remove_line("#1221", line_of(mw, "#1221", "M"), "M")
    add(h, "#1221", "L", 1)
    add(h, "#1221", "S", 1)
    h.remove_line("#1221", line_of(mw, "#1221", "S"), "S")  # the original S x4
    h.remove_line("#1221", line_of(mw, "#1221", "L"), "L")  # the original L x3
    out = mw.analysis_results_df
    assert out.loc[out["Source"] == "Manual", "Lot_Details"].isna().all()

    create_stock_export(out, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls") == {"L": 1, "S": 1, "R": 1}

    create_packing_list(out, str(tmp_path / "p.xlsx"))
    assert packing_lines(tmp_path / "p.xlsx") == {
        ("#1221", "L"): 1, ("#1221", "S"): 1, ("#1209", "R"): 1,
    }


def test_adding_a_sku_the_order_already_has_labels_only_the_run_part(tmp_path):
    mw = window(incident_run())
    add(ActionsHandler(mw), "#1221", "L", 1)
    out = mw.analysis_results_df
    create_stock_export(out, str(tmp_path / "e.xls"))
    e = pd.read_excel(tmp_path / "e.xls", dtype={"Артикул": str, "Годност": str}).fillna("")
    l_rows = sorted(zip(e.loc[e["Артикул"] == "L", "Годност"], e.loc[e["Артикул"] == "L", "Брой"]))
    assert l_rows == [("", 1), ("20270101", 3)]


def test_a_lowered_lot_line_exports_its_new_quantity(tmp_path):
    mw = window(incident_run())
    ActionsHandler(mw).change_line_quantity("#1221", line_of(mw, "#1221", "S"), "S", 1)
    create_stock_export(mw.analysis_results_df, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls")["S"] == 1
