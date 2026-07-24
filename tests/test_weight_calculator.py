"""Weight/box-fit accuracy for a genuinely-zero Quantity (found while auditing
for the same `x or 1` falsy-zero bug fixed in barcode_processor.py)."""
import pandas as pd

from shopify_tool.weight_calculator import (
    NO_BOX_NEEDED,
    calc_order_volumetric_weight,
    find_min_box_for_order,
)


def _weight_config():
    return {
        "volumetric_divisor": 6000,
        "products": {
            "A1": {"length_cm": 10, "width_cm": 10, "height_cm": 10, "no_packaging": False},
        },
        "boxes": [],
    }


class TestZeroQuantityIsNotCoercedToOne:
    def test_zero_quantity_contributes_no_volumetric_weight(self):
        order_df = pd.DataFrame([{"SKU": "A1", "Quantity": 0}])
        assert calc_order_volumetric_weight(order_df, _weight_config()) == 0.0

    def test_zero_quantity_needs_no_box(self):
        order_df = pd.DataFrame([{"SKU": "A1", "Quantity": 0}])
        assert find_min_box_for_order(order_df, _weight_config()) == NO_BOX_NEEDED
