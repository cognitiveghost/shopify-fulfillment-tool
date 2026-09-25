"""core._settle_rule_changes: stock after rules (spec 2026-09-26 §2, ADR 0013)."""

import pandas as pd

from shopify_tool import core
from shopify_tool.tag_manager import add_tag

CONFIG = {"column_mappings": {}}  # stock frame below already has internal names


def _run(tmp_path, orders_csv, stock_csv, rules):
    (tmp_path / "orders.csv").write_text(orders_csv, encoding="utf-8")
    (tmp_path / "stock.csv").write_text(stock_csv, encoding="utf-8")
    config = {
        "column_mappings": {
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
                       "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
        },
        "settings": {},
        "rules": rules,
    }
    orders_df, stock_df = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    return core._run_analysis_and_rules(orders_df, stock_df, history, config)[0]


def test_a_rule_hold_returns_the_orders_stock(tmp_path):
    hold = {"name": "big", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than or equal", "value": "7"}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": "Not Fulfillable"}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,4,DHL\n#1,B,3,DHL\n#2,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,10\nB,Beta,10\n", [hold])
    one = out[out["Order_Number"] == "#1"]
    assert (one["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert one["System_note"].str.contains("Cannot fulfill: Held by rule: big", regex=False).all()
    assert (out.loc[out["SKU"] == "A", "Final_Stock"] == 9).all()   # only #2 draws
    assert (out.loc[out["SKU"] == "B", "Final_Stock"] == 10).all()


def test_an_uncovered_bonus_holds_its_order_with_the_runs_reason(tmp_path):
    gift = {"name": "gift", "level": "article", "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,5\nGIFT,Gift box,1\n", [gift])
    status = out.groupby("Order_Number")["Order_Fulfillment_Status"].agg(set).to_dict()
    assert status == {"#1": {"Fulfillable"}, "#2": {"Not Fulfillable"}}
    assert out.loc[out["Order_Number"] == "#2", "System_note"].str.contains(
        "Cannot fulfill: GIFT: Out of stock", regex=False).all()
    assert (out.loc[out["SKU"] == "A", "Final_Stock"] == 4).all()   # #2's A released
    assert set(out.loc[out["SKU"] == "GIFT", "Warehouse_Name"]) == {"Gift box"}


def test_a_bonus_the_stock_file_does_not_list_holds_the_order(tmp_path):
    gift = {"name": "gift", "level": "article", "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_PRODUCT", "sku": "NOPE", "quantity": 1}]}]}
    out = _run(tmp_path,
               "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n",
               "Артикул,Име,Наличност\nA,Alpha,5\n", [gift])
    assert (out["Order_Fulfillment_Status"] == "Not Fulfillable").all()


def _frame(order_numbers):
    """A post-rules frame: order 1001 has A, a NO_SKU line and a GIFT bonus."""
    return pd.DataFrame({
        "Order_Number": order_numbers,
        "SKU": ["A", "NO_SKU", "GIFT"],
        "Has_SKU": [True, False, True],
        "Quantity": [1, 1, 1],
        "Stock": [5, None, 0],
        "Final_Stock": [4, None, 0],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Fulfillable"],
        "System_note": ["", "Cannot fulfill: NO_SKU [NO_SKU]", ""],
        "Internal_Tags": ["[]", "[]", add_tag("[]", "rule_added_product")],
    })


def test_settle_keeps_a_no_sku_line_held_and_matches_numeric_orders():
    stock = pd.DataFrame({"SKU": ["A", "GIFT"], "Stock": [5, 2], "Product_Name": ["Alpha", "Gift"]})
    out = core._settle_rule_changes(_frame([1001, 1001, 1001]), stock, CONFIG)
    assert out["Order_Fulfillment_Status"].tolist() == ["Fulfillable", "Not Fulfillable", "Fulfillable"]
    assert out["Final_Stock"].tolist()[2] == 1
