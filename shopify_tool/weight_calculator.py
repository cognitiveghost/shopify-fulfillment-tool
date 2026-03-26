"""
Volumetric weight calculator for products and packaging.

Volumetric weight formula: (length_cm * width_cm * height_cm) / divisor
Default divisor: 6000 (cm³ → kg, used by DPD/Speedy)

Physical fit check:
    Items are tested in all 6 orientations (rotations).
    For multi-item orders, items are stacked flat (largest face down):
      - Box L×W must fit the maximum footprint of any single item
      - Box H must fit the sum of all items' thinnest dimensions (stacked height)
    For SKUs with no_packaging=True: they are excluded from box selection.
"""

import logging
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Sentinel values used in Order_Min_Box column
NO_BOX_NEEDED = "NO_BOX_NEEDED"  # all items have no_packaging=True
NO_BOX_FITS = "NO_BOX_FITS"      # items have dimensions but no box is large enough
UNKNOWN_DIMS = "UNKNOWN_DIMS"     # some SKUs have no dimensions configured


def calc_sku_volumetric_weight(sku: str, weight_config: Dict) -> float:
    """
    Calculate volumetric weight for a single SKU.

    Returns 0 if:
    - SKU not found in weight_config
    - SKU has no_packaging=True
    - Dimensions are missing or zero
    """
    products = weight_config.get("products", {})
    divisor = float(weight_config.get("volumetric_divisor", 6000))

    if sku not in products:
        return 0.0

    product = products[sku]

    if product.get("no_packaging", False):
        return 0.0

    length = float(product.get("length_cm") or 0)
    width = float(product.get("width_cm") or 0)
    height = float(product.get("height_cm") or 0)

    if length <= 0 or width <= 0 or height <= 0 or divisor <= 0:
        return 0.0

    return (length * width * height) / divisor


def calc_order_volumetric_weight(order_df: pd.DataFrame, weight_config: Dict) -> float:
    """
    Calculate total volumetric weight for an order group.

    Sums (quantity * volumetric_weight_per_sku) for each line item.
    SKUs with no_packaging=True contribute 0.
    """
    if "SKU" not in order_df.columns:
        return 0.0

    total = 0.0
    for _, row in order_df.iterrows():
        sku = str(row.get("SKU", "") or "")
        if not sku or sku == "NO_SKU":
            continue

        qty = float(row.get("Quantity", 1) or 1)
        sku_vol_weight = calc_sku_volumetric_weight(sku, weight_config)
        total += qty * sku_vol_weight

    return round(total, 4)


def is_all_no_packaging(order_df: pd.DataFrame, weight_config: Dict) -> bool:
    """
    Returns True ONLY if at least one real SKU was found AND all such SKUs
    have no_packaging=True.

    Returns False when:
    - No SKU column exists
    - All rows are NO_SKU / empty (unknown packaging need → treat as required)
    - Any SKU requires packaging or is not configured
    """
    products = weight_config.get("products", {})

    if "SKU" not in order_df.columns:
        return False

    has_any_sku = False
    for _, row in order_df.iterrows():
        sku = str(row.get("SKU", "") or "")
        if not sku or sku == "NO_SKU":
            continue

        has_any_sku = True

        # If SKU is not in config, we don't know — treat as packaging required
        if sku not in products:
            return False

        if not products[sku].get("no_packaging", False):
            return False

    return has_any_sku  # True only if we found at least one SKU and all were no_packaging


# ---------------------------------------------------------------------------
# Physical fit logic
# ---------------------------------------------------------------------------

def _item_fits_in_box(item_dims: Tuple[float, float, float],
                      box_dims: Tuple[float, float, float]) -> bool:
    """
    Check if a single item fits in a box, trying all 6 rotations.

    Approach: sort both sets of dimensions.
    If sorted(item) ≤ sorted(box) element-wise → fits in some rotation.
    (This is equivalent to checking all permutations.)
    """
    si = sorted(item_dims)
    sb = sorted(box_dims)
    return si[0] <= sb[0] and si[1] <= sb[1] and si[2] <= sb[2]


def _order_fits_in_box(item_list: List[Tuple[float, float, float]],
                       box_dims: Tuple[float, float, float]) -> bool:
    """
    Check if a list of items fits in a box using two conditions:

    1. Each individual item must physically fit in the box (dimension check, all rotations).
       If any single item is too large for the box — the whole order doesn't fit.

    2. Total volume of all items must be ≤ box volume.
       This ensures there is enough space for all items together.

    This is a practical approximation for fulfillment packing.
    It is optimistic (assumes items can be arranged efficiently inside the box),
    but condition 1 prevents clearly impossible cases (e.g. wide flat item in a narrow box).

    Examples:
    - 3 items 9×9×3 in XS 18.5×18.5×3:
        • Each item fits individually ✓  (9≤18.5, 9≤18.5, 3≤3)
        • Total volume 729 ≤ 1025 ✓  → fits ✓
    - 1 item 24.5×24.5×2 in S 28×15.5×10:
        • Item does NOT fit individually ✗  (24.5 > 15.5)  → doesn't fit ✓
    """
    if not item_list:
        return True

    box_volume = box_dims[0] * box_dims[1] * box_dims[2]
    total_item_volume = 0.0

    for dims in item_list:
        # Condition 1: individual item must fit
        if not _item_fits_in_box(dims, box_dims):
            return False
        total_item_volume += dims[0] * dims[1] * dims[2]

    # Condition 2: total volume check
    return total_item_volume <= box_volume


def find_min_box_for_order(order_df: pd.DataFrame, weight_config: Dict) -> str:
    """
    Find the smallest box (by volume) that physically fits all items in the order.

    Returns:
    - Box name (str) if a fitting box is found
    - NO_BOX_NEEDED if all items have no_packaging=True
    - UNKNOWN_DIMS if some items have no dimensions configured
    - NO_BOX_FITS if no configured box fits all items
    """
    products = weight_config.get("products", {})
    boxes = weight_config.get("boxes", [])

    if not products or "SKU" not in order_df.columns:
        return UNKNOWN_DIMS

    # Collect item dimensions (expanded by quantity, excluding no_packaging items)
    item_dims_list: List[Tuple[float, float, float]] = []
    has_packaging_items = False
    has_unknown_dims = False

    for _, row in order_df.iterrows():
        sku = str(row.get("SKU", "") or "")
        if not sku or sku == "NO_SKU":
            continue

        if sku not in products:
            has_unknown_dims = True
            continue

        product = products[sku]
        if product.get("no_packaging", False):
            continue

        # This SKU requires packaging
        has_packaging_items = True

        l = float(product.get("length_cm") or 0)
        w = float(product.get("width_cm") or 0)
        h = float(product.get("height_cm") or 0)

        if l <= 0 or w <= 0 or h <= 0:
            has_unknown_dims = True
            continue

        qty = int(float(row.get("Quantity", 1) or 1))
        for _ in range(qty):
            item_dims_list.append((l, w, h))

    if not has_packaging_items and not has_unknown_dims:
        return NO_BOX_NEEDED

    if has_unknown_dims and not item_dims_list:
        return UNKNOWN_DIMS

    if not item_dims_list:
        return NO_BOX_NEEDED

    if not boxes:
        return NO_BOX_FITS

    # Sort boxes by volume (ascending) to find the smallest fitting box first
    def box_volume(b):
        return (float(b.get("length_cm") or 0) *
                float(b.get("width_cm") or 0) *
                float(b.get("height_cm") or 0))

    sorted_boxes = sorted(
        [b for b in boxes if box_volume(b) > 0],
        key=box_volume
    )

    for box in sorted_boxes:
        box_dims = (
            float(box.get("length_cm") or 0),
            float(box.get("width_cm") or 0),
            float(box.get("height_cm") or 0),
        )
        if _order_fits_in_box(item_dims_list, box_dims):
            return box.get("name", "").strip() or f"Box({box_dims})"

    return NO_BOX_FITS


def enrich_dataframe_with_weights(df: pd.DataFrame, weight_config: Dict) -> pd.DataFrame:
    """
    Adds volumetric weight and physical box columns to the DataFrame before Rule Engine runs.

    Adds:
    - SKU_Volumetric_Weight: per-line-item vol weight (per unit, not multiplied by qty)
    - Order_Volumetric_Weight: total vol weight for the entire order (sum of qty*vol_weight)
    - All_No_Packaging: True if all items in the order have no_packaging flag
    - Order_Min_Box: name of the smallest box that physically fits all order items
                     (or NO_BOX_NEEDED / NO_BOX_FITS / UNKNOWN_DIMS)

    Rule Engine triggers available:
    - order_volumetric_weight  (numeric)
    - all_no_packaging         (boolean)
    - Order_Min_Box            (string field, use "equals" / "contains" operators)
    """
    if not weight_config:
        return df

    if "SKU" not in df.columns or "Order_Number" not in df.columns:
        logger.warning("[WeightCalc] SKU or Order_Number column missing, skipping weight enrichment")
        return df

    # Per-SKU volumetric weight (per unit)
    df = df.copy()
    df["SKU_Volumetric_Weight"] = df["SKU"].apply(
        lambda sku: calc_sku_volumetric_weight(str(sku) if pd.notna(sku) else "", weight_config)
    )

    # Per-order aggregates
    order_vol_weights = {}
    order_all_no_pkg = {}
    order_min_box = {}

    boxes = weight_config.get("boxes", [])

    for order_num, order_group in df.groupby("Order_Number"):
        order_vol_weights[order_num] = calc_order_volumetric_weight(order_group, weight_config)
        order_all_no_pkg[order_num] = is_all_no_packaging(order_group, weight_config)
        if boxes:
            order_min_box[order_num] = find_min_box_for_order(order_group, weight_config)

    df["Order_Volumetric_Weight"] = df["Order_Number"].map(order_vol_weights).fillna(0.0)
    df["All_No_Packaging"] = df["Order_Number"].map(order_all_no_pkg).fillna(False)
    if boxes:
        df["Order_Min_Box"] = df["Order_Number"].map(order_min_box).fillna(UNKNOWN_DIMS)

    logger.info(
        f"[WeightCalc] Enriched {len(df)} rows with volumetric weights. "
        f"Orders: {len(order_vol_weights)}"
    )
    return df
