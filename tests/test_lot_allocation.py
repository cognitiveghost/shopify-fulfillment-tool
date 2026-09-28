"""R3 (ADR 0014): lot allocation derived from the frame and the session's opening lots."""

import json
from datetime import date

import pandas as pd

from shopify_tool import analysis, core, stock_ledger

FF, NF = "Fulfillable", "Not Fulfillable"
LOTS = {
    "A": [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "E", "qty": 3.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": "L", "qty": 2.0},
    ],
    "B": [{"expiry": "1", "expiry_dt": None, "batch": None, "qty": 5.0}],
}


def frame(rows):
    """(order, sku, qty, status) rows."""
    return pd.DataFrame(rows, columns=["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status"])


def shares(lot_details):
    return [(e["batch"], e["qty_allocated"]) for e in lot_details]


def test_drawing_rows_are_sku_lines_of_fulfillable_orders():
    df = frame([("#1", "A", 1, FF), ("#1", "NO_SKU", 1, NF), ("#2", "A", 1, NF)])
    assert stock_ledger.drawing_rows(df).tolist() == [True, False, False]
    assert stock_ledger.drawing_rows(df.drop(columns="Order_Fulfillment_Status")).tolist() == [False] * 3


def test_each_line_owns_its_share_in_row_order():
    out = analysis.with_lots(frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)]), LOTS)
    assert [shares(ld) for ld in out["Lot_Details"]] == [[("E", 2.0)], [("E", 1.0), ("L", 1.0)]]
    assert out["Lot_Details"].iloc[0] is not out["Lot_Details"].iloc[1]


def test_units_beyond_the_lots_get_a_no_lot_entry():
    ld = analysis.with_lots(frame([("#1", "A", 6, FF)]), LOTS)["Lot_Details"].iloc[0]
    assert [(e["expiry"], e["qty_allocated"]) for e in ld] == [("261230", 3.0), ("270101", 2.0), ("1", 1.0)]


def test_held_orders_no_sku_lines_and_unlisted_skus_get_none():
    df = frame([("#1", "A", 1, NF), ("#2", "ZZZ", 1, FF), ("#3", "NO_SKU", 1, FF)])
    assert analysis.with_lots(df, LOTS)["Lot_Details"].isna().all()


def test_orders_draw_in_the_runs_priority_order():
    rows = [("#1", "A", 3, FF), ("#9", "A", 1, FF), ("#9", "B", 1, FF)]
    multi = analysis.with_lots(frame(rows), LOTS)  # the two-line #9 draws first
    assert shares(multi["Lot_Details"].iloc[1]) == [("E", 1.0)]
    assert shares(multi["Lot_Details"].iloc[0]) == [("E", 2.0), ("L", 1.0)]
    fifo = analysis.with_lots(frame(rows), LOTS, mode="fifo")  # #1 first
    assert shares(fifo["Lot_Details"].iloc[0]) == [("E", 3.0)]


def test_the_lot_table_is_not_consumed():
    analysis.with_lots(frame([("#1", "A", 5, FF)]), LOTS)
    assert [lot["qty"] for lot in LOTS["A"]] == [3.0, 2.0]


def test_expiry_dt_is_an_iso_string_so_rows_serialise():
    ld = analysis.with_lots(frame([("#1", "A", 1, FF)]), LOTS)["Lot_Details"].iloc[0]
    assert ld[0]["expiry_dt"] == "2026-12-30"
    json.dumps(ld)


def test_no_lot_table_clears_lot_details():
    df = frame([("#1", "A", 1, FF)])
    df["Lot_Details"] = [[{"qty_allocated": 9}]]
    assert analysis.with_lots(df, None)["Lot_Details"].isna().all()


def test_lot_table_is_none_without_lot_columns():
    assert analysis.lot_table(pd.DataFrame({"SKU": ["A"], "Stock": [1]})) is None


def test_lot_table_normalises_skus_and_stock():
    lots = analysis.lot_table(
        pd.DataFrame({"SKU": [" A ", 5170.0], "Stock": ["3", 2], "Expiry_Date": ["261230", None]})
    )
    assert set(lots) == {"A", "5170"}
    assert lots["A"][0]["qty"] == 3.0


CONFIG = {"column_mappings": {"stock": {"Артикул": "SKU", "Наличност": "Stock", "Име": "Product_Name"}}}


def test_session_lot_table_reads_the_sessions_stock_file(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "inventory.csv").write_text(
        "Артикул,Име,Годност,Партида,Наличност\nA,Alpha,270101,LATE,2\nA,Alpha,261230,EARLY,3\n",
        encoding="utf-8",
    )
    lots = core.session_lot_table(str(tmp_path), CONFIG)
    assert [(lot["batch"], lot["qty"]) for lot in lots["A"]] == [("EARLY", 3.0), ("LATE", 2.0)]
    assert core.session_lot_table(str(tmp_path / "missing"), CONFIG) is None
    assert core.session_lot_table(None, CONFIG) is None
    (tmp_path / "input" / "inventory.csv").write_text("not,a\nstock,file\n", encoding="utf-8")
    assert core.session_lot_table(str(tmp_path), CONFIG) is None  # unreadable: logged, not raised


def test_with_order_fields_leaves_a_minimal_frame_alone():
    df = pd.DataFrame({"Order_Number": ["1"], "System_note": [""]})
    assert core.with_order_fields(df, {}, None).columns.tolist() == ["Order_Number", "System_note"]
    assert core.with_order_fields(None, {}, None) is None
