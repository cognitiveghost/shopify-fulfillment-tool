import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.weight import WeightPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def sample_weight_config():
    return {
        "volumetric_divisor": 5000,
        "products": {
            "SKU1": {
                "name": "Widget",
                "length_cm": 10.0,
                "width_cm": 5.0,
                "height_cm": 2.0,
                "no_packaging": False,
            }
        },
        "boxes": [
            {"name": "Small Box", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}
        ],
    }


def test_weight_page_round_trips_its_config(qapp):
    weight_config = sample_weight_config()
    page = WeightPage(weight_config, {}, ";")
    assert page.collect() == {"weight_config": weight_config}


def test_weight_page_normalizes_an_empty_config(qapp):
    page = WeightPage({}, {}, ";")
    assert page.collect() == {
        "weight_config": {"volumetric_divisor": 6000, "products": {}, "boxes": []}
    }


def test_weight_page_deleting_a_product_row_removes_it_on_save(qapp):
    """Regression: the shell merges collect() dict values one level deep. Unlike
    courier_mappings, weight_config's collect() always returns all three sub-keys
    (volumetric_divisor/products/boxes) as a fresh dict, so the merge fully
    replaces "products" rather than partially updating it -- a deleted SKU must
    not survive the round trip."""
    weight_config = sample_weight_config()
    page = WeightPage(weight_config, {}, ";")

    page.weight_products_table.removeRow(0)

    result = page.collect()
    assert result["weight_config"]["products"] == {}
