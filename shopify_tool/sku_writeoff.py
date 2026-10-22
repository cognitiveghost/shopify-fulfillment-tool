"""SKU Writeoff calculation for tag-based packaging material tracking.

This module calculates automatic SKU writeoffs based on Internal_Tags applied to orders.
When a tag like "BOX" is applied, configured SKU quantities (e.g., PKG-BOX-SMALL: 1.0)
are automatically deducted from stock exports.

The writeoff system integrates with the tag categories v2 format, where each category
can have a sku_writeoff configuration with enabled flag and tag-to-SKU mappings.

Example usage:
    >>> import pandas as pd
    >>> from shopify_tool.sku_writeoff import calculate_writeoff_quantities
    >>>
    >>> df = pd.DataFrame({
    ...     "Order_Number": [1, 2, 3],
    ...     "Internal_Tags": ['["BOX"]', '["BOX"]', '["LARGE_BAG"]']
    ... })
    >>>
    >>> tag_categories = {
    ...     "version": 2,
    ...     "categories": {
    ...         "packaging": {
    ...             "tags": ["BOX", "LARGE_BAG"],
    ...             "sku_writeoff": {
    ...                 "enabled": True,
    ...                 "mappings": {
    ...                     "BOX": [{"sku": "PKG-BOX-SMALL", "quantity": 1.0}],
    ...                     "LARGE_BAG": [{"sku": "PKG-BAG-L", "quantity": 1.0}]
    ...                 }
    ...             }
    ...         }
    ...     }
    ... }
    >>>
    >>> result = calculate_writeoff_quantities(df, tag_categories)
    >>> print(result)
       SKU              Writeoff_Quantity  Tags_Applied  Order_Count
    0  PKG-BOX-SMALL    2.0                [BOX]         2
    1  PKG-BAG-L        1.0                [LARGE_BAG]   1
"""

import logging

import pandas as pd

from shopify_tool.report_filters import fulfillable_only
from shopify_tool.tag_manager import _normalize_tag_categories, parse_tags

logger = logging.getLogger("ShopifyToolLogger")


def calculate_writeoff_quantities(
    analysis_df: pd.DataFrame,
    tag_categories: dict
) -> pd.DataFrame:
    """Calculate total writeoff quantities from tags in analysis DataFrame.

    This function scans all Internal_Tags in the provided DataFrame, looks up
    configured writeoff mappings for each tag, and accumulates SKU quantities
    that should be written off based on the tag applications.

    Two contracts govern the count, and both matter:

    1. **Each (order, tag) pair is applied exactly once.** Internal_Tags is an
       order-level value that tag_manager.expand_to_order_rows replicates onto
       every line of the order, so the frame has one row per order LINE.
       Accumulating per row multiplies every writeoff by the order's line count.
       The key is (order, tag), not (order, SKU) -- two different tags mapping
       to the same SKU must each contribute.
    2. **Only Fulfillable rows count** when Order_Fulfillment_Status is present.
       When the column is absent, every row is considered.

    If multiple orders carry the same tag, their quantities are summed.

    Args:
        analysis_df: Analysis DataFrame with Internal_Tags column.
            Expected columns: Order_Number (optional), Internal_Tags (JSON string)
            The Internal_Tags column should contain JSON-encoded arrays like '["TAG1", "TAG2"]'
        tag_categories: Tag categories config in v1 or v2 format.
            V2 structure expected with sku_writeoff.enabled and mappings.
            Categories with enabled=False are ignored.

    Returns:
        DataFrame with writeoff summary containing columns:
            - SKU (str): SKU code to write off
            - Writeoff_Quantity (float): Total quantity to deduct (rounded to 2 decimals)
            - Tags_Applied (list): List of tags that triggered this writeoff
            - Order_Count (int): Number of orders that contributed to this writeoff

        Returns empty DataFrame with correct column structure if:
        - Input DataFrame is empty
        - Internal_Tags column is missing
        - No writeoff mappings are configured
        - No tags match any mappings

    Examples:
        >>> df = pd.DataFrame({
        ...     "Order_Number": [1, 2, 3],
        ...     "Internal_Tags": ['["BOX"]', '["BOX"]', '["LARGE_BAG"]']
        ... })
        >>> config = {
        ...     "version": 2,
        ...     "categories": {
        ...         "packaging": {
        ...             "tags": ["BOX", "LARGE_BAG"],
        ...             "sku_writeoff": {
        ...                 "enabled": True,
        ...                 "mappings": {
        ...                     "BOX": [{"sku": "PKG-BOX-SMALL", "quantity": 1.0}],
        ...                     "LARGE_BAG": [
        ...                         {"sku": "PKG-BAG-L", "quantity": 1.0},
        ...                         {"sku": "PKG-SEAL", "quantity": 1.0}
        ...                     ]
        ...                 }
        ...             }
        ...         }
        ...     }
        ... }
        >>> result = calculate_writeoff_quantities(df, config)
        >>> print(result)
           SKU              Writeoff_Quantity  Tags_Applied  Order_Count
        0  PKG-BOX-SMALL    2.0                ['BOX']       2
        1  PKG-BAG-L        1.0                ['LARGE_BAG'] 1
        2  PKG-SEAL         1.0                ['LARGE_BAG'] 1

    Notes:
        - Empty DataFrames return empty result with correct column structure
        - Tags without mappings are silently ignored (not an error)
        - Disabled categories (enabled=False) are skipped
        - Quantity accumulation handles floats for partial units
        - If Internal_Tags column is missing, logs warning and returns empty
        - Order numbers are tracked to count unique orders. If Order_Number is
          missing, per-order dedup is impossible and each row counts separately
          (logged as a warning) -- the pre-fix behaviour, kept as the fallback.

    Raises:
        Does not raise exceptions - logs warnings for invalid data and continues processing
    """
    if analysis_df.empty or "Internal_Tags" not in analysis_df.columns:
        if analysis_df.empty:
            logger.warning("Empty DataFrame provided to calculate_writeoff_quantities")
        else:
            logger.warning("Internal_Tags column missing from DataFrame")
        return pd.DataFrame(columns=["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"])

    # Extract writeoff mappings from config
    writeoff_mappings = _extract_writeoff_mappings(tag_categories)

    if not writeoff_mappings:
        logger.info("No writeoff mappings configured or enabled")
        return pd.DataFrame(columns=["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"])

    # Accumulator: {sku: {"quantity": float, "tags": set, "orders": set}}
    writeoff_accumulator = {}

    # Pre-filter to Fulfillable rows only when the status column is present
    has_status_col = "Order_Fulfillment_Status" in analysis_df.columns
    if has_status_col:
        rows_df = fulfillable_only(analysis_df)
    else:
        rows_df = analysis_df

    # Internal_Tags is order-level, but rows_df has one row per order LINE
    # (see tag_manager.expand_to_order_rows). Dedupe (order, tag) so each tag
    # is counted once per order -- matching how analysis.py builds its tags
    # breakdown. Accumulating per row multiplies every writeoff by the order's
    # line count.
    if "Order_Number" in rows_df.columns:
        # Stripped, as the ledger keys orders: "1001" and "1001 " are one
        # order and write off once (AUDIT-09-O6).
        order_col = rows_df["Order_Number"].astype(str).str.strip()
    else:
        logger.warning(
            "Order_Number column missing - writeoff cannot deduplicate per order; "
            "quantities will be counted per row"
        )
        order_col = pd.Series(
            [f"row_{i}" for i in rows_df.index], index=rows_df.index
        )

    order_tags = (
        pd.DataFrame({
            "order": order_col,
            "tag": rows_df["Internal_Tags"].fillna("[]").apply(parse_tags),
        })
        .explode("tag")
        .dropna(subset=["tag"])
        .drop_duplicates()
    )

    for pair in order_tags.itertuples(index=False):
        if pair.tag not in writeoff_mappings:
            continue

        for mapping in writeoff_mappings[pair.tag]:
            sku = mapping["sku"]

            if sku not in writeoff_accumulator:
                writeoff_accumulator[sku] = {
                    "quantity": 0.0,
                    "tags": set(),
                    "orders": set(),
                }

            writeoff_accumulator[sku]["quantity"] += mapping["quantity"]
            writeoff_accumulator[sku]["tags"].add(pair.tag)
            writeoff_accumulator[sku]["orders"].add(pair.order)

    # Convert to DataFrame
    if not writeoff_accumulator:
        logger.info("No writeoff quantities calculated (no matching tags found)")
        return pd.DataFrame(columns=["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"])

    rows = []
    for sku, data in writeoff_accumulator.items():
        rows.append({
            "SKU": sku,
            "Writeoff_Quantity": round(data["quantity"], 2),
            "Tags_Applied": sorted(data["tags"]),
            "Order_Count": len(data["orders"])
        })

    result_df = pd.DataFrame(rows)
    logger.info(
        f"Calculated writeoffs for {len(result_df)} SKUs "
        f"from {order_tags['order'].nunique()} orders"
    )

    return result_df


def _extract_writeoff_mappings(tag_categories: dict) -> dict[str, list[dict]]:
    """Extract all writeoff mappings from tag categories config.

    Internal helper function that normalizes v1/v2 config formats and extracts
    only the enabled writeoff mappings. Performs validation on each mapping to
    ensure it has the required fields and valid values.

    Args:
        tag_categories: Tag categories config in v1 or v2 format.
            V2 format expected with sku_writeoff.enabled and mappings structure.

    Returns:
        Dict mapping tag name to list of {sku, quantity} dicts.
        Only includes mappings from categories where enabled=True.

        Example return value:
        {
            "BOX": [{"sku": "PKG-BOX-SMALL", "quantity": 1.0}],
            "LARGE_BAG": [
                {"sku": "PKG-BAG-L", "quantity": 1.0},
                {"sku": "PKG-SEAL", "quantity": 1.0}
            ]
        }

    Notes:
        - Uses _normalize_tag_categories() to handle both v1 and v2 formats
        - Categories with sku_writeoff.enabled=False are skipped
        - Invalid mappings (missing fields, invalid types, quantity <= 0) are skipped with warnings
        - Returns empty dict if no valid mappings found

    Raises:
        Does not raise exceptions - logs warnings for invalid data
    """
    # Normalize config format (handles both v1 and v2)
    categories = _normalize_tag_categories(tag_categories)
    mappings = {}

    for category_id, category_config in categories.items():
        sku_writeoff = category_config.get("sku_writeoff", {})

        # Skip disabled categories
        if not sku_writeoff.get("enabled", False):
            continue

        tag_mappings = sku_writeoff.get("mappings", {})

        # Process each tag's mappings
        for tag, sku_list in tag_mappings.items():
            if not isinstance(sku_list, list):
                logger.warning(
                    f"Invalid mapping format for tag '{tag}' in category '{category_id}': "
                    f"expected list, got {type(sku_list).__name__}"
                )
                continue

            # Validate and collect valid mappings
            valid_mappings = []
            for item in sku_list:
                if not isinstance(item, dict):
                    logger.warning(
                        f"Invalid mapping item for tag '{tag}': expected dict, got {type(item).__name__}"
                    )
                    continue

                if "sku" not in item or "quantity" not in item:
                    logger.warning(
                        f"Invalid mapping for tag '{tag}': missing 'sku' or 'quantity' field"
                    )
                    continue

                try:
                    quantity = float(item["quantity"])
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid quantity for tag '{tag}', SKU '{item.get('sku')}': "
                        f"cannot convert '{item['quantity']}' to float"
                    )
                    continue

                if quantity <= 0:
                    logger.warning(
                        f"Invalid quantity for tag '{tag}', SKU '{item['sku']}': "
                        f"quantity must be positive, got {quantity}"
                    )
                    continue

                valid_mappings.append({
                    "sku": item["sku"],
                    "quantity": quantity
                })

            if valid_mappings:
                mappings[tag] = valid_mappings

    if mappings:
        logger.info(f"Extracted writeoff mappings for {len(mappings)} tag(s)")
    else:
        logger.info("No enabled writeoff mappings found in configuration")

    return mappings
