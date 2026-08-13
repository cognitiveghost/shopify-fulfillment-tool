import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QScrollArea

from gui.column_mapping_widget import ColumnMappingWidget
from gui.settings.mappings import OrdersMappingPage, StockMappingPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def valid_column_mappings():
    return {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Article": "SKU", "Available": "Stock"},
    }


def test_orders_page_round_trips_valid_mappings(qapp):
    column_mappings = valid_column_mappings()
    courier_mappings = {"DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False}}
    page = OrdersMappingPage(column_mappings, courier_mappings)

    ok, errors = page.validate()
    assert (ok, errors) == (True, [])
    assert page.collect() == {
        "column_mappings": column_mappings,
        "courier_mappings": courier_mappings,
    }


def test_stock_page_round_trips_valid_mappings(qapp):
    column_mappings = valid_column_mappings()
    page = StockMappingPage(column_mappings)

    ok, errors = page.validate()
    assert (ok, errors) == (True, [])
    assert page.collect() == {"column_mappings": column_mappings}


def test_orders_page_deleting_a_courier_row_removes_it_on_save(qapp):
    """Regression: the shell merges collect() dict values one level deep, which
    would silently un-delete a removed courier code if collect() didn't mutate
    the live dict in place."""
    column_mappings = valid_column_mappings()
    courier_mappings = {"DHL": {"patterns": ["dhl"], "case_sensitive": False}}
    page = OrdersMappingPage(column_mappings, courier_mappings)

    # Simulate deleting the only courier row.
    row_refs = page.courier_mapping_widgets[0]
    page._delete_courier_row(row_refs)

    result = page.collect()
    assert result["courier_mappings"] == {}
    assert courier_mappings == {}, "the live dict passed in must be mutated in place"


def test_orders_page_validate_reports_invalid_orders_mapping(qapp):
    column_mappings = {
        "version": 2,
        "orders": {},  # missing every required field
        "stock": {"Article": "SKU", "Available": "Stock"},
    }
    page = OrdersMappingPage(column_mappings, {})
    ok, errors = page.validate()
    assert ok is False
    assert errors and "Orders CSV Column Mapping is invalid" in errors[0]


def test_get_mappings_preserves_an_internal_name_it_has_no_row_for(qapp):
    """A field missing from required/optional must not delete the client's
    mapping for it. Regression: stock_optional listed only Product_Name, so
    one Save destroyed the Expiry_Date and Batch mappings the default config
    ships with -- and with them, FIFO lot allocation."""
    widget = ColumnMappingWidget(
        mapping_type="stock",
        current_mappings={"Article": "SKU", "Available": "Stock", "Годност": "Expiry_Date"},
        required_fields=["SKU", "Stock"],
        optional_fields=[],  # deliberately does not manage Expiry_Date
    )
    assert widget.get_mappings() == {
        "Article": "SKU",
        "Available": "Stock",
        "Годност": "Expiry_Date",
    }


def test_get_mappings_still_removes_a_cleared_managed_field(qapp):
    """Carrying unmanaged entries through must not resurrect a field the user
    deliberately cleared."""
    widget = ColumnMappingWidget(
        mapping_type="stock",
        current_mappings={"Article": "SKU", "Name": "Product_Name"},
        required_fields=["SKU"],
        optional_fields=["Product_Name"],
    )
    widget.csv_column_inputs["Product_Name"].setCurrentText("")
    assert widget.get_mappings() == {"Article": "SKU"}


def test_validate_rejects_two_rows_sharing_one_csv_column(qapp):
    """Regression: the duplicate check read get_mappings(), which is keyed by
    CSV column -- so the duplicate had already collapsed and the check could
    never fire. Save then succeeded with the losing row unmapped. Now that the
    inputs are dropdowns, picking one header twice is a click away."""
    widget = ColumnMappingWidget(
        mapping_type="orders",
        current_mappings={"Name": "Order_Number", "Tags": "Tags"},
        required_fields=["Order_Number"],
        optional_fields=["Tags"],
    )
    widget.csv_column_inputs["Tags"].setCurrentText("Name")

    ok, error = widget.validate_mappings()
    assert ok is False
    assert "Name" in error


def test_stock_page_offers_rows_for_the_lot_tracking_fields(qapp):
    """Expiry_Date and Batch drive _build_fifo_lots(); before this they were
    in the default client config with no way to see or edit them."""
    page = StockMappingPage(valid_column_mappings())
    inputs = page.stock_mapping_widget.csv_column_inputs
    assert "Expiry_Date" in inputs
    assert "Batch" in inputs


def test_stock_lot_mappings_round_trip_through_the_page(qapp):
    column_mappings = valid_column_mappings()
    column_mappings["stock"] = {
        "Article": "SKU",
        "Available": "Stock",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }
    page = StockMappingPage(column_mappings)

    assert page.collect()["column_mappings"]["stock"] == {
        "Article": "SKU",
        "Available": "Stock",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }


def test_mapping_inputs_are_editable_combo_boxes(qapp):
    page = OrdersMappingPage(valid_column_mappings(), {})
    sku_input = page.orders_mapping_widget.csv_column_inputs["SKU"]
    assert isinstance(sku_input, QComboBox)
    assert sku_input.isEditable()
    assert sku_input.currentText() == "Lineitem sku"


def test_set_available_headers_offers_them_on_every_row_without_losing_text(qapp):
    page = OrdersMappingPage(valid_column_mappings(), {})
    widget = page.orders_mapping_widget

    widget.set_available_headers(["Name", "Lineitem sku", "Some other column"])

    sku_input = widget.csv_column_inputs["SKU"]
    assert [sku_input.itemText(i) for i in range(sku_input.count())] == [
        "Name",
        "Lineitem sku",
        "Some other column",
    ]
    assert sku_input.currentText() == "Lineitem sku", "typed/configured text must survive"


def test_the_widget_has_no_scroll_area_of_its_own(qapp):
    """The page already scrolls. A second QScrollArea inside it clips the
    Stock block to a few rows and produces two scrollbars side by side."""
    page = OrdersMappingPage(valid_column_mappings(), {})
    assert page.orders_mapping_widget.findChildren(QScrollArea) == []


def test_both_pages_collect_into_one_live_column_mappings_dict(qapp):
    """Two pages now own one config key. Each must write only its own sub-key
    in place -- a clear() or a freshly built dict in either one wipes the
    other's work, and _pages order decides who loses."""
    column_mappings = valid_column_mappings()
    orders_page = OrdersMappingPage(column_mappings, {})
    stock_page = StockMappingPage(column_mappings)

    stock_page.collect()
    orders_page.collect()

    assert column_mappings["orders"]["Lineitem sku"] == "SKU"
    assert column_mappings["stock"]["Article"] == "SKU"
    assert column_mappings["version"] == 2


def test_collect_order_does_not_matter(qapp):
    column_mappings = valid_column_mappings()
    orders_page = OrdersMappingPage(column_mappings, {})
    stock_page = StockMappingPage(column_mappings)

    orders_page.collect()
    result = stock_page.collect()["column_mappings"]

    assert set(result) == {"version", "orders", "stock"}
    assert result["orders"] and result["stock"]


def test_stock_page_collect_emits_every_stock_key_it_was_built_with(qapp):
    """Key coverage for the live-dict blind spot: collect() returns the same
    object the page was constructed with, so the roundtrip guard in
    test_settings_roundtrip.py cannot see a dropped sub-key here. Detach
    first, then assert on what collect() actively writes.

    This pins the write, not the field list -- get_mappings() carries an
    unmanaged internal name through from current_mappings, so a field dropped
    from OPTIONAL_FIELDS still lands here. The field list is guarded by
    test_stock_page_offers_rows_for_the_lot_tracking_fields."""
    column_mappings = valid_column_mappings()
    column_mappings["stock"] = {
        "Article": "SKU",
        "Available": "Stock",
        "Name": "Product_Name",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }
    page = StockMappingPage(column_mappings)

    page.column_mappings = {}  # detach from the live dict
    written = page.collect()["column_mappings"]["stock"]

    assert written == {
        "Article": "SKU",
        "Available": "Stock",
        "Name": "Product_Name",
        "Exp date": "Expiry_Date",
        "Lot": "Batch",
    }


def test_load_headers_fills_every_row_from_the_chosen_file(qapp, tmp_path, monkeypatch):
    csv = tmp_path / "stock.csv"
    csv.write_text("Article;Available;Exp date;Lot\nA1;5;261230;L7\n", encoding="utf-8")

    page = StockMappingPage(valid_column_mappings())
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(csv), ""),
    )

    page._load_headers_from_csv()

    sku_input = page.stock_mapping_widget.csv_column_inputs["SKU"]
    assert [sku_input.itemText(i) for i in range(sku_input.count())] == [
        "Article", "Available", "Exp date", "Lot",
    ]
    assert sku_input.currentText() == "Article", "the configured mapping must survive"


def test_load_headers_cancelled_leaves_the_inputs_alone(qapp, monkeypatch):
    page = StockMappingPage(valid_column_mappings())
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName", lambda *a, **k: ("", "")
    )

    page._load_headers_from_csv()

    sku_input = page.stock_mapping_widget.csv_column_inputs["SKU"]
    assert sku_input.count() == 0
    assert sku_input.currentText() == "Article"
