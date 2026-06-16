"""Tests for the volumetric weight calculator module."""

import pytest
import pandas as pd

from shopify_tool.weight_calculator import (
    calc_sku_volumetric_weight,
    calc_order_volumetric_weight,
    is_all_no_packaging,
    enrich_dataframe_with_weights,
    find_min_box_for_order,
    _item_fits_in_box,
    _order_fits_in_box,
    NO_BOX_NEEDED,
    NO_BOX_FITS,
    UNKNOWN_DIMS,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WEIGHT_CONFIG = {
    "volumetric_divisor": 6000,
    "products": {
        "SKU-A": {"name": "Product A", "length_cm": 30, "width_cm": 20, "height_cm": 10, "no_packaging": False},
        "SKU-B": {"name": "Product B", "length_cm": 60, "width_cm": 40, "height_cm": 30, "no_packaging": False},
        "SKU-NP": {"name": "No Packaging Product", "length_cm": 5, "width_cm": 5, "height_cm": 1, "no_packaging": True},
    },
    "boxes": [],
}


# ---------------------------------------------------------------------------
# calc_sku_volumetric_weight
# ---------------------------------------------------------------------------

class TestCalcSkuVolumetricWeight:
    def test_known_sku(self):
        # 30 * 20 * 10 / 6000 = 6000/6000 = 1.0
        result = calc_sku_volumetric_weight("SKU-A", SAMPLE_WEIGHT_CONFIG)
        assert result == pytest.approx(1.0)

    def test_larger_sku(self):
        # 60 * 40 * 30 / 6000 = 72000/6000 = 12.0
        result = calc_sku_volumetric_weight("SKU-B", SAMPLE_WEIGHT_CONFIG)
        assert result == pytest.approx(12.0)

    def test_no_packaging_sku_returns_zero(self):
        result = calc_sku_volumetric_weight("SKU-NP", SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0

    def test_unknown_sku_returns_zero(self):
        result = calc_sku_volumetric_weight("UNKNOWN", SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0

    def test_empty_sku_returns_zero(self):
        result = calc_sku_volumetric_weight("", SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0

    def test_missing_dimensions_returns_zero(self):
        config = {
            "volumetric_divisor": 6000,
            "products": {
                "SKU-X": {"name": "X", "length_cm": 0, "width_cm": 10, "height_cm": 10, "no_packaging": False}
            }
        }
        assert calc_sku_volumetric_weight("SKU-X", config) == 0.0

    def test_custom_divisor(self):
        config = {
            "volumetric_divisor": 5000,
            "products": {
                "SKU-D": {"name": "D", "length_cm": 50, "width_cm": 20, "height_cm": 10, "no_packaging": False}
            }
        }
        # 50*20*10 / 5000 = 10000/5000 = 2.0
        assert calc_sku_volumetric_weight("SKU-D", config) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# calc_order_volumetric_weight
# ---------------------------------------------------------------------------

class TestCalcOrderVolumetricWeight:
    def test_single_item_qty1(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 1}])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == pytest.approx(1.0)

    def test_single_item_qty3(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 3}])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == pytest.approx(3.0)

    def test_mixed_items(self):
        df = pd.DataFrame([
            {"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 2},  # 2 * 1.0 = 2.0
            {"Order_Number": "#1001", "SKU": "SKU-B", "Quantity": 1},  # 1 * 12.0 = 12.0
        ])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == pytest.approx(14.0)

    def test_no_packaging_sku_contributes_zero(self):
        df = pd.DataFrame([
            {"Order_Number": "#1001", "SKU": "SKU-NP", "Quantity": 5},
        ])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0

    def test_no_sku_rows_ignored(self):
        df = pd.DataFrame([
            {"Order_Number": "#1001", "SKU": "NO_SKU", "Quantity": 1},
        ])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Order_Number", "SKU", "Quantity"])
        result = calc_order_volumetric_weight(df, SAMPLE_WEIGHT_CONFIG)
        assert result == 0.0


# ---------------------------------------------------------------------------
# is_all_no_packaging
# ---------------------------------------------------------------------------

class TestIsAllNoPackaging:
    def test_all_no_packaging(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "SKU": "SKU-NP", "Quantity": 2}])
        assert is_all_no_packaging(df, SAMPLE_WEIGHT_CONFIG) is True

    def test_mixed_requires_packaging(self):
        df = pd.DataFrame([
            {"Order_Number": "#1001", "SKU": "SKU-NP", "Quantity": 1},
            {"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 1},
        ])
        assert is_all_no_packaging(df, SAMPLE_WEIGHT_CONFIG) is False

    def test_regular_sku_requires_packaging(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 1}])
        assert is_all_no_packaging(df, SAMPLE_WEIGHT_CONFIG) is False

    def test_unknown_sku_treated_as_packaging_required(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "SKU": "UNKNOWN", "Quantity": 1}])
        assert is_all_no_packaging(df, SAMPLE_WEIGHT_CONFIG) is False

    def test_no_sku_column_returns_false(self):
        df = pd.DataFrame([{"Order_Number": "#1001", "Quantity": 1}])
        assert is_all_no_packaging(df, SAMPLE_WEIGHT_CONFIG) is False


# ---------------------------------------------------------------------------
# enrich_dataframe_with_weights
# ---------------------------------------------------------------------------

class TestEnrichDataframeWithWeights:
    def _make_df(self):
        return pd.DataFrame([
            {"Order_Number": "#1001", "SKU": "SKU-A", "Quantity": 2},
            {"Order_Number": "#1001", "SKU": "SKU-B", "Quantity": 1},
            {"Order_Number": "#1002", "SKU": "SKU-NP", "Quantity": 3},
        ])

    def test_adds_sku_vol_weight_column(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert "SKU_Volumetric_Weight" in result.columns

    def test_adds_order_vol_weight_column(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert "Order_Volumetric_Weight" in result.columns

    def test_adds_all_no_packaging_column(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert "All_No_Packaging" in result.columns

    def test_order_vol_weight_values(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        # #1001: 2*1.0 + 1*12.0 = 14.0
        order_1001 = result[result["Order_Number"] == "#1001"]["Order_Volumetric_Weight"].iloc[0]
        assert order_1001 == pytest.approx(14.0)
        # #1002: SKU-NP is no_packaging so 0
        order_1002 = result[result["Order_Number"] == "#1002"]["Order_Volumetric_Weight"].iloc[0]
        assert order_1002 == pytest.approx(0.0)

    def test_all_no_packaging_values(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert bool(result[result["Order_Number"] == "#1001"]["All_No_Packaging"].iloc[0]) is False
        assert bool(result[result["Order_Number"] == "#1002"]["All_No_Packaging"].iloc[0]) is True

    def test_sku_vol_weight_per_unit(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        # SKU-A per unit = 1.0 (not multiplied by qty)
        sku_a_row = result[result["SKU"] == "SKU-A"].iloc[0]
        assert sku_a_row["SKU_Volumetric_Weight"] == pytest.approx(1.0)

    def test_empty_config_returns_unchanged(self):
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, {})
        assert "SKU_Volumetric_Weight" not in result.columns
        assert "Order_Volumetric_Weight" not in result.columns

    def test_does_not_mutate_original_df(self):
        df = self._make_df()
        original_cols = list(df.columns)
        enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert list(df.columns) == original_cols

    def test_order_min_box_column_added_when_boxes_configured(self):
        config_with_boxes = dict(SAMPLE_WEIGHT_CONFIG)
        config_with_boxes["boxes"] = [
            {"name": "S", "length_cm": 28, "width_cm": 15.5, "height_cm": 10},
            {"name": "L", "length_cm": 32, "width_cm": 30, "height_cm": 14},
        ]
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, config_with_boxes)
        assert "Order_Min_Box" in result.columns

    def test_order_min_box_always_present_defaults_to_unknown(self):
        # Column must always exist so downstream code never gets KeyError
        from shopify_tool.weight_calculator import UNKNOWN_DIMS
        df = self._make_df()
        result = enrich_dataframe_with_weights(df, SAMPLE_WEIGHT_CONFIG)
        assert "Order_Min_Box" in result.columns
        assert (result["Order_Min_Box"] == UNKNOWN_DIMS).all()


# ---------------------------------------------------------------------------
# Physical fit: _item_fits_in_box
# ---------------------------------------------------------------------------

class TestItemFitsInBox:
    def test_exact_fit(self):
        assert _item_fits_in_box((10, 20, 30), (10, 20, 30)) is True

    def test_fits_with_rotation(self):
        # Item 30x10x20 fits in box 30x20x10 after rotation
        assert _item_fits_in_box((30, 10, 20), (30, 20, 10)) is True

    def test_does_not_fit(self):
        # Item 24.5 x 24.5 x 2 in box 28 x 15.5 x 10
        # sorted item: [2, 24.5, 24.5] vs sorted box: [10, 15.5, 28]
        # 24.5 > 15.5 → does not fit
        assert _item_fits_in_box((24.5, 24.5, 2), (28, 15.5, 10)) is False

    def test_fits_in_large_box(self):
        # Item 24.5 x 24.5 x 2 in box 32 x 30 x 14
        assert _item_fits_in_box((24.5, 24.5, 2), (32, 30, 14)) is True

    def test_item_too_tall(self):
        assert _item_fits_in_box((5, 5, 50), (10, 10, 40)) is False


# ---------------------------------------------------------------------------
# Physical fit: find_min_box_for_order
# ---------------------------------------------------------------------------

BOXES = [
    {"name": "XS", "length_cm": 18.5, "width_cm": 18.5, "height_cm": 3},
    {"name": "S",  "length_cm": 28,   "width_cm": 15.5, "height_cm": 10},
    {"name": "M",  "length_cm": 32,   "width_cm": 19,   "height_cm": 10},
    {"name": "L",  "length_cm": 32,   "width_cm": 30,   "height_cm": 14},
    {"name": "XL", "length_cm": 100,  "width_cm": 100,  "height_cm": 50},
]

WEIGHT_CONFIG_WITH_BOXES = {
    "volumetric_divisor": 6000,
    "products": {
        "FLAT": {"name": "Flat Item", "length_cm": 24.5, "width_cm": 24.5, "height_cm": 2, "no_packaging": False},
        "SMALL": {"name": "Small Item", "length_cm": 10, "width_cm": 10, "height_cm": 5, "no_packaging": False},
        "NP": {"name": "No Pkg", "length_cm": 5, "width_cm": 5, "height_cm": 1, "no_packaging": True},
    },
    "boxes": BOXES,
}


class TestFindMinBoxForOrder:
    def _make_order(self, rows):
        return pd.DataFrame(rows)

    def test_flat_item_fits_in_L_not_S(self):
        # FLAT 24.5x24.5x2 should NOT fit in S(28x15.5x10) but SHOULD fit in L(32x30x14)
        df = self._make_order([{"Order_Number": "#1", "SKU": "FLAT", "Quantity": 1}])
        result = find_min_box_for_order(df, WEIGHT_CONFIG_WITH_BOXES)
        assert result == "L"

    def test_small_item_fits_in_XS(self):
        # SMALL 10x10x5 fits in XS(18.5x18.5x3)?
        # sorted item: [5, 10, 10] vs sorted XS: [3, 18.5, 18.5] → 5 > 3 → NO
        # fits in S(28x15.5x10)? sorted item: [5,10,10] vs [10,15.5,28] → YES
        df = self._make_order([{"Order_Number": "#1", "SKU": "SMALL", "Quantity": 1}])
        result = find_min_box_for_order(df, WEIGHT_CONFIG_WITH_BOXES)
        assert result == "S"

    def test_all_no_packaging_returns_no_box_needed(self):
        df = self._make_order([{"Order_Number": "#1", "SKU": "NP", "Quantity": 3}])
        result = find_min_box_for_order(df, WEIGHT_CONFIG_WITH_BOXES)
        assert result == NO_BOX_NEEDED

    def test_unknown_sku_returns_unknown_dims(self):
        df = self._make_order([{"Order_Number": "#1", "SKU": "UNKNOWN", "Quantity": 1}])
        result = find_min_box_for_order(df, WEIGHT_CONFIG_WITH_BOXES)
        assert result == UNKNOWN_DIMS

    def test_no_boxes_configured_returns_no_box_fits(self):
        config_no_boxes = dict(WEIGHT_CONFIG_WITH_BOXES)
        config_no_boxes["boxes"] = []
        df = self._make_order([{"Order_Number": "#1", "SKU": "FLAT", "Quantity": 1}])
        result = find_min_box_for_order(df, config_no_boxes)
        assert result == NO_BOX_FITS

    def test_two_flat_items_side_by_side(self):
        # Two FLAT (24.5x24.5x2): each item individually fails M (24.5 > 19) and S (24.5 > 15.5)
        # Each item fits L (32x30x14): sorted item [2,24.5,24.5] ≤ sorted L [14,30,32] → YES
        # Total volume 2x(24.5x24.5x2)=2401 ≤ L volume 13440 → YES
        df = self._make_order([{"Order_Number": "#1", "SKU": "FLAT", "Quantity": 2}])
        result = find_min_box_for_order(df, WEIGHT_CONFIG_WITH_BOXES)
        assert result == "L"

    def test_flat_items_fit_side_by_side_in_xs(self):
        # 3 items 9x9x3 → each fits in XS (18.5x18.5x3): sorted [3,9,9] ≤ [3,18.5,18.5] → YES
        # total volume 3x(9x9x3)=729 ≤ XS volume 18.5x18.5x3=1025.25 → YES
        config = {
            "volumetric_divisor": 6000,
            "products": {
                "THIN": {"name": "Thin", "length_cm": 9, "width_cm": 9, "height_cm": 3, "no_packaging": False}
            },
            "boxes": BOXES,
        }
        df = self._make_order([{"Order_Number": "#1", "SKU": "THIN", "Quantity": 3}])
        result = find_min_box_for_order(df, config)
        assert result == "XS"

    def test_item_too_large_for_any_box(self):
        config = {
            "volumetric_divisor": 6000,
            "products": {
                "GIANT": {"name": "Giant", "length_cm": 200, "width_cm": 200, "height_cm": 200, "no_packaging": False}
            },
            "boxes": BOXES,
        }
        df = self._make_order([{"Order_Number": "#1", "SKU": "GIANT", "Quantity": 1}])
        result = find_min_box_for_order(df, config)
        assert result == NO_BOX_FITS
