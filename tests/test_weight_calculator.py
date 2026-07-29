"""Weight/box-fit accuracy for a genuinely-zero Quantity (found while auditing
for the same `x or 1` falsy-zero bug fixed in barcode_processor.py)."""
import pandas as pd

from shopify_tool.weight_calculator import (
    NO_BOX_NEEDED,
    calc_order_volumetric_weight,
    enrich_dataframe_with_weights,
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


class TestOrderMinBoxWithNoBoxesConfigured:
    """Root cause: enrich_dataframe_with_weights() used to skip calling
    find_min_box_for_order() entirely whenever weight_config["boxes"] was
    empty, forcing every order to UNKNOWN_DIMS -- even orders whose items are
    all no_packaging=True and plainly need no box at all. find_min_box_for_order()
    already resolves this correctly on its own; the guard was redundant and wrong."""

    def test_all_no_packaging_order_is_labeled_no_box_needed_not_unknown(self):
        config = {
            "volumetric_divisor": 6000,
            "products": {"A1": {"no_packaging": True}},
            "boxes": [],
        }
        df = pd.DataFrame([{"Order_Number": "1001", "SKU": "A1", "Quantity": 1}])

        result = enrich_dataframe_with_weights(df, config)

        assert result.loc[0, "Order_Min_Box"] == NO_BOX_NEEDED

    def test_order_needing_packaging_with_no_boxes_configured_is_no_box_fits(self):
        """Dimensions ARE known here, so this must be distinguishable from the
        genuinely-unknown-dims case -- NO_BOX_FITS, not UNKNOWN_DIMS."""
        from shopify_tool.weight_calculator import NO_BOX_FITS

        df = pd.DataFrame([{"Order_Number": "1001", "SKU": "A1", "Quantity": 1}])

        result = enrich_dataframe_with_weights(df, _weight_config())

        assert result.loc[0, "Order_Min_Box"] == NO_BOX_FITS
