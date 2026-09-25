import pandas as pd

from shopify_tool.barcode_processor import generate_barcodes_batch
from shopify_tool.packing_lists import create_packing_list, sort_for_packing_list


def _frame():
    return pd.DataFrame({
        "Order_Number": ["#3", "#1", "#2", "#10"],
        "SKU": ["A", "A", "A", "A"],
        "Quantity": [1, 1, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable"] * 4,
        "Shipping_Provider": ["DPD", "PostOne", "DHL", "DHL"],
        "Destination_Country": ["BG"] * 4,
        "Warehouse_Name": ["W"] * 4,
        "Internal_Tags": ["[]"] * 4,
    })


def test_sort_is_courier_then_numeric_order_number():
    assert sort_for_packing_list(_frame())["Order_Number"].tolist() == ["#2", "#10", "#1", "#3"]


def test_label_numbers_follow_the_packing_list(tmp_path):
    df = _frame()
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    listed = pd.read_excel(tmp_path / "p.xlsx", dtype={"Order_Number": str})["Order_Number"].tolist()
    orders = sort_for_packing_list(df.assign(item_count=1)).reset_index(drop=True)
    labels = generate_barcodes_batch(orders)
    assert [r["order_number"] for r in sorted(labels, key=lambda r: r["sequential_num"])] == listed


def test_lot_columns_follow_quantity_in_a_configured_layout(tmp_path):
    df = _frame().head(1)
    df["Lot_Details"] = [[{"qty_allocated": 1, "expiry": "2027-01", "batch": "L1"}]]
    create_packing_list(df, str(tmp_path / "p.xlsx"), columns=["Order_Number", "Quantity", "SKU"])
    assert pd.read_excel(tmp_path / "p.xlsx").columns.tolist() == [
        "Order_Number", "Quantity", "Lot_Expiry", "Lot_Batch", "SKU"]
