"""The Packing Tool order list is built once per frame (AUDIT-09-O2).

`core.build_packing_orders` must give exactly what the old per-order builder
gave. The old builder is frozen below as `_order_reference`.
"""

import json
from typing import Any

import pandas as pd

from shopify_tool import core
from shopify_tool.stock_ledger import FULFILLABLE, NOT_FULFILLABLE, is_fulfillable


# the pre-D implementation, frozen to pin behaviour
def _order_reference(order_number: str, group: pd.DataFrame) -> dict[str, Any]:
    first_row = group.iloc[0]

    tags_raw = first_row.get("Internal_Tags", "[]") or "[]"
    try:
        internal_tags = json.loads(tags_raw) if isinstance(tags_raw, str) else []
    except (json.JSONDecodeError, TypeError):
        internal_tags = []

    tags_value = first_row.get("Tags", "") or ""
    tags_list = (
        [t.strip() for t in str(tags_value).split(",") if t.strip()]
        if str(tags_value).strip()
        else []
    )

    min_box_raw = first_row.get("Order_Min_Box", None)
    order_min_box = (
        str(min_box_raw)
        if min_box_raw is not None and not pd.isna(min_box_raw) and str(min_box_raw) != ""
        else None
    )

    shipping_provider = str(first_row.get("Shipping_Provider", "") or "")
    if "Order_Fulfillment_Status" in group.columns and "Order_Number" in group.columns:
        fulfillment_status = (
            FULFILLABLE if is_fulfillable(group, first_row["Order_Number"]) else NOT_FULFILLABLE
        )
    else:
        fulfillment_status = "Unknown"
    destination_country = str(first_row.get("Destination_Country", "") or "")

    items = []
    for _, row in group.iterrows():
        warehouse_name = row.get("Warehouse_Name", "")
        if not warehouse_name or warehouse_name == "N/A":
            warehouse_name = row.get("Product_Name", "")
        qty_raw = row.get("Quantity", 0)
        try:
            quantity = int(qty_raw) if qty_raw is not None and not pd.isna(qty_raw) else 0
        except (ValueError, TypeError):
            quantity = 0
        items.append(
            {
                "sku": str(row.get("SKU", "")),
                "product_name": str(warehouse_name),
                "quantity": quantity,
                "order_fulfillment_status": str(row.get("Order_Fulfillment_Status", "") or ""),
                "status_note": str(row.get("Status_Note", "") or ""),
                "system_note": str(row.get("System_note", "") or ""),
            }
        )

    return {
        "order_number": str(order_number),
        "order_type": str(first_row.get("Order_Type", "") or ""),
        "shipping_provider": shipping_provider,
        "order_fulfillment_status": fulfillment_status,
        "destination_country": destination_country,
        "courier": shipping_provider,
        "status": fulfillment_status,
        "shipping_country": destination_country,
        "tags": tags_list,
        "notes": str(first_row.get("Notes", "") or ""),
        "system_note": str(first_row.get("System_note", "") or ""),
        "internal_tags": internal_tags,
        "order_min_box": order_min_box,
        "items": items,
    }


NAN = float("nan")

FRAME = pd.DataFrame(
    {
        "Order_Number": ["#2", "#1", "#1", "#2", 1003, 1003, "#4"],
        "SKU": ["C", "A", "B", "D", "E", None, "F"],
        "Product_Name": ["Cup", "Apple", "Box", "Dish", "Egg", "Gift note", "Fig"],
        "Warehouse_Name": [NAN, "", "N/A", "W-D", "W-E", "W-N", "W-F"],
        "Quantity": [NAN, "3", "x", 1, 2, 1, 4],
        "Order_Fulfillment_Status": [
            "Fulfillable", "Fulfillable", "Fulfillable", "Not Fulfillable",
            "Fulfillable", "Not Fulfillable", "Fulfillable",
        ],
        "Internal_Tags": ['["a","b"]', "[]", "[]", '["a","b"]', "not json", "not json", NAN],
        "Tags": ["", "x, y", "x, y", "", NAN, NAN, " , z "],
        "Order_Min_Box": ["", NAN, NAN, "", "M", "M", NAN],
        "Status_Note": [NAN, "Repeat", NAN, "", "note", NAN, NAN],
        "System_note": ["", NAN, "", "held", NAN, "", "s"],
        "Shipping_Provider": ["DHL", "DPD", "DPD", "DHL", NAN, NAN, "UPS"],
        "Destination_Country": ["BG", "RO", "RO", "BG", "GR", "GR", NAN],
        "Notes": [NAN, "fragile", "", NAN, "", "", "n"],
        "Order_Type": ["Single", "Multi", "Multi", "Single", NAN, NAN, "Single"],
    },
    index=[7, 3, 9, 0, 5, 1, 2],
)


def test_orders_match_the_reference():
    expected = [_order_reference(str(n), g) for n, g in FRAME.groupby("Order_Number")]
    assert core.build_packing_orders(FRAME) == expected


def test_without_a_status_column_the_status_is_unknown():
    frame = FRAME.drop(columns=["Order_Fulfillment_Status"])
    expected = [_order_reference(str(n), g) for n, g in frame.groupby("Order_Number")]
    assert core.build_packing_orders(frame) == expected
    assert {o["status"] for o in expected} == {"Unknown"}


def test_a_row_without_an_order_number_is_left_out_not_a_crash():
    """ngroup gives such a row NaN, which made the group numbers float."""
    frame = FRAME.astype({"Order_Number": object})
    frame.loc[9, "Order_Number"] = NAN
    expected = [_order_reference(str(n), g) for n, g in frame.groupby("Order_Number")]
    assert core.build_packing_orders(frame) == expected
