import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.mappings import MappingsPage


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


def test_mappings_page_round_trips_valid_mappings(qapp):
    column_mappings = valid_column_mappings()
    courier_mappings = {"DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False}}
    page = MappingsPage(column_mappings, courier_mappings)

    ok, errors = page.validate()
    assert (ok, errors) == (True, [])
    assert page.collect() == {
        "column_mappings": column_mappings,
        "courier_mappings": courier_mappings,
    }


def test_mappings_page_deleting_a_courier_row_removes_it_on_save(qapp):
    """Regression: the shell merges collect() dict values one level deep, which
    would silently un-delete a removed courier code if collect() didn't mutate
    the live dict in place."""
    column_mappings = valid_column_mappings()
    courier_mappings = {"DHL": {"patterns": ["dhl"], "case_sensitive": False}}
    page = MappingsPage(column_mappings, courier_mappings)

    # Simulate deleting the only courier row.
    row_refs = page.courier_mapping_widgets[0]
    page._delete_courier_row(row_refs)

    result = page.collect()
    assert result["courier_mappings"] == {}
    assert courier_mappings == {}, "the live dict passed in must be mutated in place"


def test_mappings_page_validate_reports_invalid_orders_mapping(qapp):
    column_mappings = {
        "version": 2,
        "orders": {},  # missing every required field
        "stock": {"Article": "SKU", "Available": "Stock"},
    }
    page = MappingsPage(column_mappings, {})
    ok, errors = page.validate()
    assert ok is False
    assert errors and "Orders column mapping is invalid" in errors[0]
