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
import os
import pandas as pd
from typing import Dict, List, Optional

from shopify_tool.tag_manager import parse_tags, _normalize_tag_categories

logger = logging.getLogger("ShopifyToolLogger")


def calculate_writeoff_quantities(
    analysis_df: pd.DataFrame,
    tag_categories: Dict
) -> pd.DataFrame:
    """Calculate total writeoff quantities from tags in analysis DataFrame.

    This function scans all Internal_Tags in the provided DataFrame, looks up
    configured writeoff mappings for each tag, and accumulates SKU quantities
    that should be written off based on the tag applications.

    The function processes each row in the DataFrame, extracts the tags, and
    for each tag that has a writeoff mapping configured, adds the corresponding
    SKU quantities to the accumulator. If multiple orders have the same tag,
    the quantities are summed together.

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
        - Order numbers are tracked to count unique orders (uses row index if missing)

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

    # Process each row
    for idx, row in analysis_df.iterrows():
        # Only write off packaging for orders that are actually Fulfillable
        if "Order_Fulfillment_Status" in analysis_df.columns:
            if row.get("Order_Fulfillment_Status", "") != "Fulfillable":
                continue

        tags = parse_tags(row.get("Internal_Tags"))

        # Get order number (use row index if Order_Number not present)
        if "Order_Number" in analysis_df.columns:
            order_number = row.get("Order_Number", f"row_{idx}")
        else:
            order_number = f"row_{idx}"

        for tag in tags:
            if tag not in writeoff_mappings:
                continue

            # Apply mappings for this tag
            for mapping in writeoff_mappings[tag]:
                sku = mapping["sku"]
                quantity = mapping["quantity"]

                if sku not in writeoff_accumulator:
                    writeoff_accumulator[sku] = {
                        "quantity": 0.0,
                        "tags": set(),
                        "orders": set()
                    }

                writeoff_accumulator[sku]["quantity"] += quantity
                writeoff_accumulator[sku]["tags"].add(tag)
                writeoff_accumulator[sku]["orders"].add(str(order_number))

    # Convert to DataFrame
    if not writeoff_accumulator:
        logger.info("No writeoff quantities calculated (no matching tags found)")
        return pd.DataFrame(columns=["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"])

    rows = []
    for sku, data in writeoff_accumulator.items():
        rows.append({
            "SKU": sku,
            "Writeoff_Quantity": round(data["quantity"], 2),
            "Tags_Applied": sorted(list(data["tags"])),
            "Order_Count": len(data["orders"])
        })

    result_df = pd.DataFrame(rows)
    logger.info(f"Calculated writeoffs for {len(result_df)} SKUs from {len(analysis_df)} orders")

    return result_df


def apply_writeoff_to_stock_export(
    stock_df: pd.DataFrame,
    writeoff_df: pd.DataFrame
) -> pd.DataFrame:
    """Apply writeoff deductions to stock export DataFrame.

    Takes a stock export DataFrame (with SKU and quantity columns) and a writeoff
    DataFrame (from calculate_writeoff_quantities), performs a left join, and
    calculates net quantities after writeoff deductions.

    Net quantities are calculated as: max(0, Original_Quantity - Writeoff_Quantity)
    This ensures negative quantities are never returned (stock can't go below zero).

    Args:
        stock_df: Stock export DataFrame with columns:
            - Артикул (str): SKU code
            - Наличност (int/float): Original quantity in stock
        writeoff_df: Writeoff DataFrame from calculate_writeoff_quantities() with columns:
            - SKU (str): SKU code
            - Writeoff_Quantity (float): Quantity to deduct
            - Tags_Applied (list): Tags that triggered writeoff
            - Order_Count (int): Number of orders

    Returns:
        DataFrame with columns:
            - Артикул (str): SKU code
            - Original_Quantity (int/float): Original quantity before writeoff
            - Writeoff_Quantity (float): Amount deducted (0.0 if no writeoff for this SKU)
            - Net_Quantity (int/float): Final quantity after writeoff (never negative)

        If either input DataFrame is empty, returns stock_df with zero writeoff columns added.

    Examples:
        >>> stock_df = pd.DataFrame({
        ...     "Артикул": ["PKG-BOX-SMALL", "PKG-BAG-L", "OTHER-SKU"],
        ...     "Наличност": [10, 5, 20]
        ... })
        >>> writeoff_df = pd.DataFrame({
        ...     "SKU": ["PKG-BOX-SMALL", "PKG-BAG-L"],
        ...     "Writeoff_Quantity": [3.0, 2.0],
        ...     "Tags_Applied": [["BOX"], ["LARGE_BAG"]],
        ...     "Order_Count": [3, 2]
        ... })
        >>> result = apply_writeoff_to_stock_export(stock_df, writeoff_df)
        >>> print(result)
           Артикул           Original_Quantity  Writeoff_Quantity  Net_Quantity
        0  PKG-BOX-SMALL     10                 3.0                7.0
        1  PKG-BAG-L         5                  2.0                3.0
        2  OTHER-SKU         20                 0.0                20.0

    Notes:
        - SKUs in stock_df without matching writeoff get Writeoff_Quantity=0.0
        - SKUs with writeoff > available stock get Net_Quantity=0.0 (clamped at zero)
        - Logs warnings when writeoff exceeds available stock
        - Column names use Ukrainian labels (Артикул, Наличност) to match stock export format

    Raises:
        Does not raise exceptions - logs warnings for overages and continues
    """
    if stock_df.empty or writeoff_df.empty:
        if stock_df.empty:
            logger.warning("Empty stock DataFrame provided to apply_writeoff_to_stock_export")
        if writeoff_df.empty:
            logger.info("Empty writeoff DataFrame - no writeoffs to apply")

        # Return original with zero writeoff columns
        result = stock_df.copy()
        result["Writeoff_Quantity"] = 0.0
        result["Net_Quantity"] = result["Наличност"]
        result.rename(columns={"Наличност": "Original_Quantity"}, inplace=True)
        return result

    # Prepare result DataFrame
    result = stock_df.copy()
    result.rename(columns={"Артикул": "SKU", "Наличност": "Original_Quantity"}, inplace=True)

    # Merge with writeoff data
    result = result.merge(
        writeoff_df[["SKU", "Writeoff_Quantity"]],
        on="SKU",
        how="left"
    )

    # Fill NaN writeoffs with 0
    result["Writeoff_Quantity"] = result["Writeoff_Quantity"].fillna(0.0)

    # Calculate net quantity (never negative)
    result["Net_Quantity"] = (result["Original_Quantity"] - result["Writeoff_Quantity"]).clip(lower=0)

    # Log warnings for overages (writeoff > available)
    overages = result[result["Writeoff_Quantity"] > result["Original_Quantity"]]
    if not overages.empty:
        logger.warning(f"Writeoff exceeds available stock for {len(overages)} SKU(s):")
        for _, row in overages.iterrows():
            logger.warning(
                f"  {row['SKU']}: Available={row['Original_Quantity']}, "
                f"Writeoff={row['Writeoff_Quantity']}, Net=0.0"
            )

    # Rename back to Ukrainian column name for consistency
    result.rename(columns={"SKU": "Артикул"}, inplace=True)

    logger.info(f"Applied writeoff to {len(result)} SKUs, {len(overages)} with overages")

    return result


def generate_writeoff_report(
    analysis_df: pd.DataFrame,
    tag_categories: Dict,
    output_file: str
) -> None:
    """Generate detailed writeoff report as .xls file.

    Creates a comprehensive Excel report showing which tags triggered writeoffs,
    which orders contributed to each writeoff, and total quantities per SKU.

    The report contains two sheets:
    1. Summary: High-level statistics (total orders, SKUs affected, total quantity)
    2. Writeoff_Details: Per-SKU breakdown with tags and order counts

    Args:
        analysis_df: Analysis DataFrame with Internal_Tags column.
            Expected columns: Order_Number (optional), Internal_Tags (JSON string)
        tag_categories: Tag categories config in v1 or v2 format with writeoff mappings
        output_file: Path to save .xls report (must end with .xls)

    Returns:
        None. Writes report file to disk.

    Side Effects:
        - Creates .xls file at output_file path
        - Logs info messages about report generation
        - Logs warning if no writeoffs to report

    Report Structure:
        Sheet 1 "Summary":
            - Total_Orders_Scanned: Number of orders in analysis_df
            - Total_SKUs_Affected: Number of unique SKUs with writeoffs
            - Total_Writeoff_Quantity: Sum of all writeoff quantities
            - Generated_At: Timestamp of report generation

        Sheet 2 "Writeoff_Details":
            - SKU: SKU code
            - Writeoff_Quantity: Total quantity to write off
            - Tags_Applied: List of tags that triggered this writeoff
            - Order_Count: Number of orders that contributed

    Examples:
        >>> df = pd.DataFrame({
        ...     "Order_Number": [1, 2, 3],
        ...     "Internal_Tags": ['["BOX"]', '["BOX"]', '["LARGE_BAG"]']
        ... })
        >>> config = {...}  # V2 format with writeoff mappings
        >>> generate_writeoff_report(df, config, "writeoff_report.xls")
        # Creates writeoff_report.xls with two sheets

    Notes:
        - Uses xlwt engine for Excel export (compatible with .xls format)
        - If no writeoffs are found, creates minimal report with message
        - Timestamps use current system time
        - Directory for output_file must exist (not created automatically)

    Raises:
        May raise exceptions from pandas ExcelWriter or file I/O operations.
        These are not caught to allow caller to handle appropriately.
    """
    logger.info(f"Generating writeoff report: {output_file}")

    # Calculate writeoffs
    writeoff_df = calculate_writeoff_quantities(analysis_df, tag_categories)

    # Simple format: just SKU and Quantity (same as stock export)
    if writeoff_df.empty:
        logger.warning("No writeoffs to report - creating empty report")
        export_df = pd.DataFrame(columns=["Артикул", "Наличност"])
    else:
        export_df = pd.DataFrame({
            "Артикул": writeoff_df["SKU"],
            "Наличност": writeoff_df["Writeoff_Quantity"].astype(int)
        })

    # Write to Excel using xlwt (same format as stock_export)
    try:
        with pd.ExcelWriter(output_file, engine="xlwt") as writer:
            export_df.to_excel(writer, sheet_name="Sheet1", index=False)
    except Exception as e:
        # Fallback for environments where xlwt might not be properly registered
        if "No Excel writer 'xlwt'" in str(e):
            logger.warning("Pandas failed to find 'xlwt' engine. Trying direct save with xlwt.")
            import xlwt
            workbook = xlwt.Workbook()
            sheet = workbook.add_sheet('Sheet1')

            # Write header
            for col_num, value in enumerate(export_df.columns):
                sheet.write(0, col_num, value)

            # Write data
            for row_num, row in export_df.iterrows():
                for col_num, value in enumerate(row):
                    sheet.write(row_num + 1, col_num, value)

            workbook.save(output_file)
            logger.info(f"Writeoff report created using direct xlwt save: {output_file}")
        else:
            raise e

    total_quantity = export_df["Наличност"].sum() if not export_df.empty else 0
    logger.info(
        f"Writeoff report created: {output_file} "
        f"({len(export_df)} SKUs, {total_quantity} total quantity)"
    )


def _extract_writeoff_mappings(tag_categories: Dict) -> Dict[str, List[Dict]]:
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
