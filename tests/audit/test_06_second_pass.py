"""Audit 06: second pass over the data layer (order info and maths).

Report: docs/audit/06-second-pass.md. Every AUDIT-06-k test fails because of
the bug it names and is marked xfail(strict=True); the fix removes the marker.
Unmarked tests pin what the audit verified correct. Fixtures are synthetic;
no production data lives here.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool import analysis, core, fulfillment_history
from shopify_tool.analysis import run_analysis, toggle_order_fulfillment
from shopify_tool.packing_lists import create_packing_list
from shopify_tool.set_decoder import decode_sets_in_orders
from shopify_tool.stock_export import create_stock_export
from shopify_tool.undo_manager import UndoManager
from shopify_tool.weight_calculator import enrich_dataframe_with_weights

NO_HISTORY = pd.DataFrame({"Order_Number": []})
MAPS = {"stock": {"Артикул": "SKU", "Наличност": "Stock", "Име": "Product_Name"}}
CONFIG = {"column_mappings": MAPS, "settings": {}}
ORDER_MAPS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
}


def stock(rows):
    """rows: (sku, qty, expiry, batch), ERP headers."""
    df = pd.DataFrame(rows, columns=["Артикул", "Наличност", "Годност", "Партида"])
    df["Име"] = df["Артикул"].astype(str) + " name"
    return df


def orders(rows):
    """rows: (order_name, sku, qty), Shopify headers."""
    df = pd.DataFrame(rows, columns=["Name", "Lineitem sku", "Lineitem quantity"])
    df["Shipping Method"] = "DHL"
    return df


def lots_of(stock_df):
    return analysis.lot_table(analysis.stock_with_internal_columns(stock_df, MAPS))


def stock_rows(skus):
    return pd.DataFrame({"SKU": skus, "Stock": [5] * len(skus), "Product_Name": skus})


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


def add(mw, order, sku, qty=1):
    ActionsHandler(mw)._add_product_to_order(
        {"order_number": order, "sku": sku, "product_name": sku, "quantity": qty},
        stock_rows(["A", "B", "L", "S"]),
        {},
    )


def remove(mw, order, sku):
    df = mw.analysis_results_df
    label = df.index[(df["Order_Number"] == order) & (df["SKU"] == sku)][0]
    ActionsHandler(mw).remove_item_from_order(order, sku, int(df.index.get_loc(label)))


def refresh(mw, lots, config=CONFIG):
    """What MainWindow._update_all_views does after every edit (spec §3)."""
    mw.analysis_results_df = core.with_order_fields(mw.analysis_results_df, config, lots)
    return mw.analysis_results_df


def export_rows(df, tmp_path):
    out = tmp_path / "e.xls"
    create_stock_export(df, str(out))
    e = pd.read_excel(out, dtype={"Артикул": str, "Годност": str, "Партида": str}).fillna("")
    return sorted(zip(e["Артикул"], e["Годност"], e["Партида"], e["Брой"]))


# ---------------------------------------------------------------------------
# AUDIT-06-1 — lot details follow edits
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-06-1: an added line shares another line's lots")
def test_an_added_line_exports_its_own_sku_and_quantity(tmp_path):
    st = stock([("A", 5, "261230", "LA"), ("B", 5, "270101", "LB")])
    df, *_ = run_analysis(st, orders([("#1", "A", 2)]), NO_HISTORY)
    mw = window(df)
    add(mw, "#1", "B")
    out = refresh(mw, lots_of(st))
    assert export_rows(out, tmp_path) == [("A", "261230", "LA", 2), ("B", "270101", "LB", 1)]


@pytest.mark.xfail(strict=True, reason="AUDIT-06-1: a removed duplicate line leaves its lots")
def test_removing_one_of_two_same_sku_lines_exports_the_other_only(tmp_path):
    st = stock([("A", 5, "261230", "LA")])
    df, *_ = run_analysis(st, orders([("#1", "A", 2), ("#1", "A", 1)]), NO_HISTORY)
    mw = window(df)
    label = df.index[df["Quantity"] == 1][0]
    ActionsHandler(mw).remove_item_from_order("#1", "A", int(df.index.get_loc(label)))
    out = refresh(mw, lots_of(st))
    assert export_rows(out, tmp_path) == [("A", "261230", "LA", 2)]


@pytest.mark.xfail(strict=True, reason="AUDIT-06-1: a force-fulfilled order has no lots")
def test_an_order_made_fulfillable_after_the_run_exports_with_its_lots(tmp_path):
    st = stock([("A", 3, "261230", "LA")])
    df, *_ = run_analysis(st, orders([("#1", "A", 3), ("#2", "A", 3)]), NO_HISTORY)
    ok, _, df = toggle_order_fulfillment(df, "#1")  # hold #1
    assert ok
    ok, _, df = toggle_order_fulfillment(df, "#2")  # #2 takes the stock
    assert ok
    out = core.with_order_fields(df, CONFIG, lots_of(st))
    assert export_rows(out, tmp_path) == [("A", "261230", "LA", 3)]


@pytest.mark.xfail(strict=True, reason="AUDIT-06-1: REVE #1221, packing list prints 3 + 3")
def test_packing_list_prints_each_lines_own_quantity(tmp_path):
    st = stock([("L", 5, "1", "1"), ("S", 5, "1", "1")])
    df, *_ = run_analysis(st, orders([("#1", "L", 3)]), NO_HISTORY)
    mw = window(df)
    add(mw, "#1", "S")
    remove(mw, "#1", "L")
    add(mw, "#1", "L")
    out = refresh(mw, lots_of(st))
    create_packing_list(out, str(tmp_path / "p.xlsx"))
    x = pd.read_excel(tmp_path / "p.xlsx", dtype={"Order_Number": str, "SKU": str})
    assert x.groupby("SKU")["Quantity"].sum().to_dict() == {"L": 1, "S": 1}
    assert export_rows(out, tmp_path) == [("L", "", "", 1), ("S", "", "", 1)]


# ---------------------------------------------------------------------------
# AUDIT-06-2 — order-level columns follow edits
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-06-2: Order_Type frozen at run time")
def test_order_type_follows_added_and_removed_lines():
    st = stock([("A", 5, "1", "1"), ("B", 5, "1", "1")])
    df, *_ = run_analysis(st, orders([("#1", "A", 1), ("#2", "A", 1), ("#2", "B", 1)]), NO_HISTORY)
    mw = window(df)
    add(mw, "#1", "B")
    remove(mw, "#2", "B")
    out = refresh(mw, lots_of(st))
    types = out.groupby("Order_Number")["Order_Type"].agg(set).to_dict()
    assert types == {"#1": {"Multi"}, "#2": {"Single"}}


WEIGHTS = {
    "volumetric_divisor": 6000,
    "products": {
        "A": {"length_cm": 10, "width_cm": 10, "height_cm": 6},
        "B": {"length_cm": 30, "width_cm": 20, "height_cm": 10},
    },
    "boxes": [
        {"name": "S", "length_cm": 12, "width_cm": 12, "height_cm": 12},
        {"name": "L", "length_cm": 40, "width_cm": 30, "height_cm": 20},
    ],
}


@pytest.mark.xfail(strict=True, reason="AUDIT-06-2: box and weights frozen at run time")
def test_box_and_weight_follow_an_added_line():
    st = stock([("A", 5, "1", "1"), ("B", 5, "1", "1")])
    df, *_ = run_analysis(st, orders([("#1", "A", 1)]), NO_HISTORY)
    df = enrich_dataframe_with_weights(df, WEIGHTS)  # as the run does before rules
    assert set(df["Order_Min_Box"]) == {"S"}
    mw = window(df)
    add(mw, "#1", "B")
    out = refresh(mw, lots_of(st), {**CONFIG, "weight_config": WEIGHTS})
    assert set(out["Order_Min_Box"]) == {"L"}
    assert out.loc[out["SKU"] == "B", "SKU_Volumetric_Weight"].tolist() == [pytest.approx(1.0)]
    assert out["Order_Volumetric_Weight"].tolist() == [pytest.approx(1.1)] * 2


@pytest.mark.xfail(strict=True, reason="AUDIT-06-2: Stock_Alert frozen at run time")
def test_stock_alert_follows_a_hold():
    config = {**CONFIG, "settings": {"low_stock_threshold": 2}}
    st = stock([("A", 3, "1", "1")])
    df, *_ = run_analysis(st, orders([("#1", "A", 2)]), NO_HISTORY)
    core._add_stock_alert(df, config)  # run time: Stock left 1 < 2
    assert set(df["Stock_Alert"]) == {"Low Stock"}
    ok, _, df = toggle_order_fulfillment(df, "#1")  # hold: Stock left back to 3
    assert ok
    out = core.with_order_fields(df, config, lots_of(st))
    assert set(out["Stock_Alert"]) == {""}


# ---------------------------------------------------------------------------
# AUDIT-06-3 — inventory snapshot
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-06-3: raw and normalised SKU both remembered")
def test_inventory_snapshot_keys_are_normalised_skus():
    final = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["S-EX06-2MD"], "Final_Stock": [3.0]})
    raw = pd.DataFrame({"SKU": ["S-EX06-2MD ", "OTHER"], "Stock": [5, 4]})
    assert core.build_inventory_snapshot(final, raw) == {"S-EX06-2MD": 3.0, "OTHER": 4.0}
    # One SKU on two rows, one spelled with a space: summed first, then clamped.
    assert core.inventory_total_units(pd.DataFrame({"SKU": ["X ", "X"], "Stock": [5, -7]})) == 0.0


# ---------------------------------------------------------------------------
# AUDIT-06-4 — nested sets
# ---------------------------------------------------------------------------

DECODERS = {
    "OUTER": [{"sku": "INNER", "quantity": 1}, {"sku": "CAP", "quantity": 2}],
    "INNER": [{"sku": "BOTTLE", "quantity": 1}],
    "NECTAR": [{"sku": "NECTAR", "quantity": 1}, {"sku": "DROPPER", "quantity": 1}],
    "KIT": [{"sku": "NECTAR", "quantity": 1}, {"sku": "DROPPER", "quantity": 1}],
    "LOOP_A": [{"sku": "LOOP_B", "quantity": 1}],
    "LOOP_B": [{"sku": "LOOP_A", "quantity": 1}],
}


def decoded(sku, qty):
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": [sku], "Quantity": [qty]})
    out = decode_sets_in_orders(df, DECODERS)
    return sorted(zip(out["SKU"], out["Quantity"], out["Original_SKU"]))


@pytest.mark.xfail(strict=True, reason="AUDIT-06-4: nested sets expand one level only")
def test_a_nested_set_expands_to_its_inner_components():
    assert decoded("OUTER", 3) == [("BOTTLE", 3, "OUTER"), ("CAP", 6, "OUTER")]


def test_a_set_that_lists_itself_is_not_expanded_again():
    # HERBAR NECTAR-30: its parents list the dropper themselves (spec D4).
    assert decoded("KIT", 2) == [("DROPPER", 2, "KIT"), ("NECTAR", 2, "KIT")]
    assert decoded("NECTAR", 1) == [("DROPPER", 1, "NECTAR"), ("NECTAR", 1, "NECTAR")]


@pytest.mark.xfail(strict=True, reason="AUDIT-06-4: nested sets expand one level only")
def test_a_set_cycle_stops_instead_of_recursing():
    assert decoded("LOOP_A", 1) == [("LOOP_A", 1, "LOOP_A")]


# ---------------------------------------------------------------------------
# AUDIT-06-5 — run summaries
# ---------------------------------------------------------------------------


def _write_inputs(tmp_path, orders_csv, stock_csv):
    (tmp_path / "orders.csv").write_text(orders_csv, encoding="utf-8")
    (tmp_path / "stock.csv").write_text(stock_csv, encoding="utf-8")
    return {"orders": ORDER_MAPS, "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"}}


@pytest.mark.xfail(strict=True, reason="AUDIT-06-5: Summary_Missing is still written")
def test_run_report_has_no_summary_missing_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(
        core,
        "load_session_signals",
        lambda _pm, _cid: (pd.DataFrame(columns=["Order_Number", "Execution_Date", "Session"]), None),
    )
    monkeypatch.setattr(fulfillment_history, "get_persistent_data_path", lambda _n: tmp_path / "h.csv")
    maps = _write_inputs(
        tmp_path,
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,A,9,DHL\n",
        "Артикул,Име,Наличност\nA,Alpha,5\n",
    )
    ok, msg, _df, _stats = core.run_full_analysis(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), str(tmp_path / "out"),
        "auto", "auto", {"settings": {}, "column_mappings": maps},
    )
    assert ok, msg
    sheets = pd.ExcelFile(tmp_path / "out" / "fulfillment_analysis.xlsx").sheet_names
    assert "Summary_Present" in sheets
    assert "Summary_Missing" not in sheets


@pytest.mark.xfail(strict=True, reason="AUDIT-06-5: summary and stats predate rules")
def test_summary_present_and_stats_follow_rule_holds(tmp_path):
    maps = _write_inputs(
        tmp_path,
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,4,DHL\n#1,B,3,DHL\n#2,A,1,DHL\n",
        "Артикул,Име,Наличност\nA,Alpha,10\nB,Beta,10\n",
    )
    hold = {"name": "big", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than or equal", "value": "7"}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": "Not Fulfillable"}]}]}
    config = {"column_mappings": maps, "settings": {}, "rules": [hold]}
    orders_df, stock_df = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    _final, present, stats = core._run_analysis_and_rules(orders_df, stock_df, history, config)
    assert present.set_index("SKU")["Total Quantity"].to_dict() == {"A": 1}
    assert stats["total_orders_completed"] == 1


# ---------------------------------------------------------------------------
# AUDIT-06-7 — expiry formats
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-06-7: YYMM and day-00 expiries misread")
def test_yymm_and_day_zero_expiries_sort_by_their_real_month():
    assert analysis._parse_expiry_date("2805") == date(2028, 5, 1)  # YYMM
    assert analysis._parse_expiry_date("261200") == date(2026, 12, 1)  # day 00
    assert analysis._parse_expiry_date("0527") == date(2027, 5, 1)  # MMYY still first
    assert analysis._parse_expiry_date("261230") == date(2026, 12, 30)  # unchanged
