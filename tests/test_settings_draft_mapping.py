"""MappingDraft and StockDraft: a CSV's column mapping, with no widget
(phase 7 spec section 4.3)."""

import pytest

from gui.settings.page_state import (
    FIELDS,
    NOT_IN_FILE,
    FileColumns,
    MappingDraft,
    StockDraft,
)

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
    "Lineitem name": "Product_Name",
}
STOCK = {"Article": "SKU", "Available": "Stock", "Годност": "Expiry_Date"}

ORDERS_FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Lineitem name",
        "Tags",
        "Discount Code",
    ),
    first_row={
        "Name": "#10482",
        "Lineitem sku": "ACM-TEE-BLK-M",
        "Lineitem quantity": "2",
        "Shipping Method": "DHL Express Worldwide",
        "Lineitem name": "Tee, black, M",
        "Tags": "VIP, repeat",
        "Discount Code": "",
    },
    loaded=True,
)


def _mappings(orders=None, stock=None):
    return {
        "version": 2,
        "orders": dict(ORDERS if orders is None else orders),
        "stock": dict(STOCK if stock is None else stock),
    }


def _orders(file=ORDERS_FILE, **kwargs):
    live = _mappings(**kwargs)
    return MappingDraft("orders", live, "ACME", file), live


def _field(draft, name):
    return next(f for f in draft.view()["mapping"]["fields"] if f["name"] == name)


# --- what it opens with ------------------------------------------------------


def test_the_orders_page_has_the_profiles_twelve_fields_required_first():
    assert [f.name for f in FIELDS["orders"]] == [
        "Order_Number",
        "SKU",
        "Quantity",
        "Shipping_Method",
        "Product_Name",
        "Shipping_Country",
        "Tags",
        "Notes",
        "Total_Price",
        "Subtotal",
        "Customer",
        "Created_At",
    ]
    assert [f.name for f in FIELDS["orders"] if f.required] == [
        "Order_Number",
        "SKU",
        "Quantity",
        "Shipping_Method",
    ]


def test_the_stock_page_has_rows_for_the_lot_tracking_fields():
    """Expiry_Date and Batch are the names _build_fifo_lots() reads. A page
    with no row for them once deleted both mappings on every save."""
    assert [f.name for f in FIELDS["stock"]] == [
        "SKU",
        "Stock",
        "Product_Name",
        "Expiry_Date",
        "Batch",
    ]
    assert [f.name for f in FIELDS["stock"] if f.required] == ["SKU", "Stock"]


def test_it_reads_each_fields_column_from_the_stored_mapping():
    draft, _live = _orders()
    assert draft.chosen["Order_Number"] == "Name"
    assert draft.chosen["Product_Name"] == "Lineitem name"
    assert draft.chosen["Tags"] == ""


def test_it_round_trips_a_stored_mapping_untouched():
    draft, live = _orders()
    assert draft.collect() == {"column_mappings": live}
    assert live["orders"] == ORDERS
    assert live["stock"] == STOCK
    assert live["version"] == 2


def test_a_mapping_that_is_not_a_dict_opens_empty():
    live = {"orders": None, "stock": STOCK}
    draft = MappingDraft("orders", live, "ACME")
    assert set(draft.chosen.values()) == {""}


def test_an_internal_name_with_no_row_is_carried_through():
    draft, live = _orders(orders={**ORDERS, "Phone": "Shipping_Phone"})
    draft.collect()
    assert live["orders"]["Phone"] == "Shipping_Phone"


def test_stock_lot_mappings_round_trip():
    live = _mappings(stock={**STOCK, "Партида": "Batch"})
    draft = StockDraft(live, "ACME")
    draft.collect()
    assert live["stock"]["Годност"] == "Expiry_Date"
    assert live["stock"]["Партида"] == "Batch"


# --- choosing a column -------------------------------------------------------


def test_choosing_a_column_maps_it():
    draft, live = _orders()
    assert draft.apply("column", ["Tags", "Tags"]) is True
    draft.collect()
    assert live["orders"]["Tags"] == "Tags"


def test_not_imported_removes_an_optional_mapping():
    draft, live = _orders()
    assert draft.apply("column", ["Product_Name", ""]) is True
    draft.collect()
    assert "Lineitem name" not in live["orders"]


def test_a_required_field_cannot_be_set_to_not_imported():
    draft, _live = _orders()
    assert draft.apply("column", ["SKU", ""]) is False
    assert draft.chosen["SKU"] == "Lineitem sku"


def test_a_column_another_field_holds_moves():
    """The profile stores one field per column: {column: field}."""
    draft, live = _orders()
    assert draft.apply("column", ["Tags", "Lineitem name"]) is True
    assert draft.chosen["Tags"] == "Lineitem name"
    assert draft.chosen["Product_Name"] == ""
    draft.collect()
    assert live["orders"]["Lineitem name"] == "Tags"


def test_taking_a_required_fields_column_leaves_it_missing():
    draft, _live = _orders()
    draft.apply("column", ["Tags", "Shipping Method"])
    assert draft.chosen["Shipping_Method"] == ""
    assert draft.blocker() == "Map Shipping method"


@pytest.mark.parametrize(
    "args",
    [
        ["Tags", "No Such Column"],
        ["No_Such_Field", "Tags"],
        ["Tags"],
        ["Tags", 3],
        "Tags",
    ],
)
def test_an_edit_it_does_not_know_is_dropped(args):
    draft, _live = _orders()
    before = dict(draft.chosen)
    assert draft.apply("column", args) is False
    assert draft.chosen == before


def test_an_unknown_action_is_dropped():
    draft, _live = _orders()
    assert draft.apply("courier_add", []) is False


def test_choosing_the_column_already_chosen_reports_nothing():
    draft, _live = _orders()
    assert draft.apply("column", ["SKU", "Lineitem sku"]) is False


def test_nothing_can_be_chosen_before_a_file_is_read():
    draft, _live = _orders(file=None)
    assert draft.apply("column", ["Tags", "Tags"]) is False
    assert draft.apply("column", ["Product_Name", ""]) is False


def test_reading_a_file_changes_no_mapping():
    draft, _live = _orders(file=None)
    before = dict(draft.chosen)
    draft.set_file(FileColumns("other.csv", ("A", "B"), {"A": "1", "B": "2"}))
    assert draft.chosen == before
    assert draft.view()["mapping"]["columns"] == ["A", "B"]


# --- one live dict, two drafts -----------------------------------------------


def test_both_drafts_write_into_one_live_dict_in_either_order():
    for first in ("orders", "stock"):
        live = _mappings()
        orders = MappingDraft("orders", live, "ACME", ORDERS_FILE)
        stock = StockDraft(live, "ACME")
        orders.apply("column", ["Tags", "Tags"])
        drafts = [orders, stock] if first == "orders" else [stock, orders]
        for draft in drafts:
            assert draft.collect()["column_mappings"] is live
        assert live["orders"]["Tags"] == "Tags"
        assert live["stock"] == STOCK


def test_an_edit_on_orders_leaves_stock_clean():
    live = _mappings()
    orders = MappingDraft("orders", live, "ACME", ORDERS_FILE)
    stock = StockDraft(live, "ACME")
    orders.mark_clean()
    stock.mark_clean()
    orders.apply("column", ["Tags", "Tags"])
    orders.collect()
    assert orders.is_dirty() is True
    assert stock.is_dirty() is False


# --- what blocks a save ------------------------------------------------------


def test_nothing_blocks_a_complete_mapping():
    draft, _live = _orders()
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])


def test_a_required_field_with_no_column_blocks_the_save():
    orders = {k: v for k, v in ORDERS.items() if v != "Shipping_Method"}
    draft, _live = _orders(orders=orders)
    assert draft.blocker() == "Map Shipping method"
    assert draft.blocker_key() == "field-Shipping_Method"
    assert draft.validate() == (
        False,
        [
            (
                "Shipping method is required. Choose the column that holds it, "
                "e.g. Shipping Method."
            )
        ],
    )
    row = _field(draft, "Shipping_Method")
    assert row["problem"] == (
        "Shipping method is required. Choose the column that holds it, e.g."
    )
    assert row["example"] == "Shipping Method"


def test_with_no_file_the_problem_says_to_read_one_first():
    orders = {k: v for k, v in ORDERS.items() if v != "SKU"}
    draft, _live = _orders(file=None, orders=orders)
    row = _field(draft, "SKU")
    assert row["problem"] == (
        "SKU is required. Use Read columns from CSV…, then choose its column."
    )
    assert row["example"] == ""
    assert draft.validate()[1] == [row["problem"]]


def test_the_first_missing_field_in_page_order_is_the_one_named():
    draft, _live = _orders(orders={"Name": "Order_Number"})
    assert draft.blocker() == "Map SKU"
    assert len(draft.validate()[1]) == 3


def test_an_optional_field_never_has_a_problem():
    draft, _live = _orders()
    assert _field(draft, "Tags")["problem"] == ""


# --- what the page draws -----------------------------------------------------


def test_the_view_names_the_page_and_its_action():
    view = _orders()[0].view()
    assert view["page"] == "orders"
    assert view["title"] == "Orders mapping"
    assert view["subtitle"] == "Which column of ACME's orders CSV holds each field."
    assert view["action"] == "Read columns from CSV…"

    stock = StockDraft(_mappings(), "ACME").view()
    assert stock["page"] == "stock"
    assert stock["title"] == "Stock mapping"
    assert stock["subtitle"] == "Which column of ACME's stock CSV holds each field."
    assert "couriers" not in stock["mapping"]
    assert "additional" not in stock["mapping"]


def test_the_source_sentence_says_where_the_columns_came_from():
    loaded, _live = _orders()
    assert loaded.view()["mapping"]["source"] == {
        "lead": "Columns read from",
        "file": "orders-30-09.csv",
        "tail": ", the file loaded on Setup.",
    }
    picked, _live = _orders(file=FileColumns("picked.csv", ("Name",)))
    assert picked.view()["mapping"]["source"] == {
        "lead": "Columns read from",
        "file": "picked.csv",
        "tail": ".",
    }
    none, _live = _orders(file=None)
    assert none.view()["mapping"]["source"] == {
        "lead": "No CSV has been read. Use Read columns from CSV… to change a field.",
        "file": "",
        "tail": "",
    }


def test_the_view_says_whether_a_column_can_be_picked_and_lists_them():
    with_file = _orders()[0].view()["mapping"]
    assert with_file["can_pick"] is True
    assert with_file["columns"] == list(ORDERS_FILE.columns)
    without = _orders(file=None)[0].view()["mapping"]
    assert without["can_pick"] is False
    assert without["columns"] == []


def test_held_names_the_field_that_holds_each_chosen_column():
    held = _orders()[0].view()["mapping"]["held"]
    assert held == {
        "Name": "Order number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping method",
        "Lineitem name": "Product name",
    }


def test_a_field_row_carries_its_column_and_the_first_rows_value():
    row = _field(_orders()[0], "Order_Number")
    assert row == {
        "name": "Order_Number",
        "label": "Order number",
        "required": True,
        "column": "Name",
        "placeholder": "Choose column",
        "sample": "#10482",
        "sample_missing": False,
        "problem": "",
        "example": "",
        "hint": "",
    }


def test_an_unmapped_optional_field_reads_not_imported():
    row = _field(_orders()[0], "Tags")
    assert row["column"] == ""
    assert row["placeholder"] == "Not imported"
    assert row["sample"] == ""


def test_a_saved_column_the_file_lacks_stays_and_says_so():
    draft, live = _orders(orders={**ORDERS, "Old Notes": "Notes"})
    row = _field(draft, "Notes")
    assert row["column"] == "Old Notes"
    assert row["sample"] == NOT_IN_FILE
    assert row["sample_missing"] is True
    draft.collect()
    assert live["orders"]["Old Notes"] == "Notes"


def test_with_no_file_a_row_has_its_column_and_no_sample():
    row = _field(_orders(file=None)[0], "Order_Number")
    assert row["column"] == "Name"
    assert row["sample"] == ""
    assert row["sample_missing"] is False


def test_the_lot_fields_explain_themselves():
    draft = StockDraft(_mappings(), "ACME")
    assert _field(draft, "Expiry_Date")["hint"].startswith(
        "When mapped, stock is allocated oldest expiry first"
    )
    assert _field(draft, "Batch")["hint"].startswith("Lot or batch number.")
    assert _field(draft, "SKU")["hint"] == ""
