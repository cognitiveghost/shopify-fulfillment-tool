"""
Set/Bundle decoder module for expanding sets into component SKUs.

This module provides functionality to:
1. Decode set/bundle SKUs into individual component SKUs
2. Import/export set definitions from/to CSV files
3. Track original set information during expansion
"""

import logging
import pandas as pd
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def decode_sets_in_orders(
    orders_df: pd.DataFrame,
    set_decoders: Dict[str, List[Dict[str, Any]]]
) -> pd.DataFrame:
    """
    Expand set/bundle SKUs into their component SKUs.

    Args:
        orders_df: DataFrame with order data (must have SKU and Quantity columns)
        set_decoders: Dict mapping set SKUs to list of components
                     Format: {"SET-SKU": [{"sku": "COMP-1", "quantity": 2}, ...]}

    Returns:
        DataFrame with sets expanded into components, including tracking columns:
        - Original_SKU: The original set SKU (or same as SKU if not a set)
        - Original_Quantity: The original order quantity
        - Is_Set_Component: True if this row is from set expansion

    Example:
        Input row: Order_Number=1001, SKU=SET-WINTER-KIT, Quantity=2
        Set definition: SET-WINTER-KIT = HAT(1x), GLOVES(1x), SCARF(1x)

        Output rows:
        - Order_Number=1001, SKU=HAT, Quantity=2, Original_SKU=SET-WINTER-KIT, ...
        - Order_Number=1001, SKU=GLOVES, Quantity=2, Original_SKU=SET-WINTER-KIT, ...
        - Order_Number=1001, SKU=SCARF, Quantity=2, Original_SKU=SET-WINTER-KIT, ...
    """
    if orders_df.empty:
        logger.info("Empty orders DataFrame, nothing to decode")
        # Add tracking columns even for empty DataFrame
        orders_df["Original_SKU"] = orders_df["SKU"] if "SKU" in orders_df.columns else None
        orders_df["Original_Quantity"] = orders_df["Quantity"] if "Quantity" in orders_df.columns else None
        orders_df["Is_Set_Component"] = False
        return orders_df

    if not set_decoders:
        logger.info("No set decoders defined, adding tracking columns only")
        orders_df["Original_SKU"] = orders_df["SKU"]
        orders_df["Original_Quantity"] = orders_df["Quantity"]
        orders_df["Is_Set_Component"] = False
        return orders_df

    expanded_rows = []
    set_orders_count = 0

    for idx, row in orders_df.iterrows():
        sku = row["SKU"]
        quantity = row["Quantity"]

        # Check if this SKU is a set
        if sku in set_decoders:
            components = set_decoders[sku]

            # Validate set has components
            if not components:
                logger.warning(f"Set '{sku}' has no components defined, skipping")
                # Keep original row but add tracking columns
                new_row = row.copy()
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = False
                expanded_rows.append(new_row)
                continue

            logger.debug(f"Decoding set {sku} (qty: {quantity}) → {len(components)} components")
            set_orders_count += 1

            # Expand into components
            valid_components_added = 0
            for component in components:
                component_sku = component.get("sku")
                component_qty = component.get("quantity")

                # Validate component
                if not component_sku:
                    logger.warning(f"Component in set '{sku}' has no SKU, skipping component")
                    continue

                if not component_qty or component_qty <= 0:
                    logger.warning(
                        f"Component '{component_sku}' in set '{sku}' has invalid quantity: {component_qty}, skipping"
                    )
                    continue

                # Create expanded row
                new_row = row.copy()
                new_row["SKU"] = component_sku
                new_row["Quantity"] = quantity * component_qty  # Multiply quantities
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = True

                expanded_rows.append(new_row)
                valid_components_added += 1

            if valid_components_added == 0:
                # Every component failed validation -- keep the original order
                # line instead of letting it vanish with only a debug log.
                logger.warning(
                    f"Set '{sku}' has no valid components after validation, keeping original row"
                )
                new_row = row.copy()
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = False
                expanded_rows.append(new_row)

        else:
            # Regular SKU - keep as-is with tracking columns
            new_row = row.copy()
            new_row["Original_SKU"] = sku
            new_row["Original_Quantity"] = quantity
            new_row["Is_Set_Component"] = False
            expanded_rows.append(new_row)

    if not expanded_rows:
        logger.warning("No rows after set expansion")
        # Return empty DataFrame with correct columns
        result_df = orders_df.copy()
        result_df["Original_SKU"] = None
        result_df["Original_Quantity"] = None
        result_df["Is_Set_Component"] = False
        return result_df.iloc[0:0]  # Empty with columns

    result_df = pd.DataFrame(expanded_rows)

    logger.info(
        f"Decoded {set_orders_count} set orders into components. "
        f"Total rows: {len(orders_df)} → {len(result_df)}"
    )

    return result_df


def import_sets_from_csv(csv_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Import set definitions from CSV file.

    CSV Format:
        Set_SKU,Component_SKU,Component_Quantity
        SET-A,COMP-1,1
        SET-A,COMP-2,2
        SET-B,COMP-3,1

    Args:
        csv_path: Path to CSV file

    Returns:
        Dict in set_decoders format:
        {
            "SET-A": [
                {"sku": "COMP-1", "quantity": 1},
                {"sku": "COMP-2", "quantity": 2}
            ],
            "SET-B": [{"sku": "COMP-3", "quantity": 1}]
        }

    Raises:
        ValueError: If CSV format is invalid
        FileNotFoundError: If CSV file doesn't exist
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    except Exception as e:
        raise ValueError(f"Failed to read CSV file: {e}")

    # Validate required columns
    required_columns = ["Set_SKU", "Component_SKU", "Component_Quantity"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV missing required columns: {missing_columns}. Expected: {required_columns}")

    # Validate data
    if df.empty:
        logger.warning("CSV file is empty")
        return {}

    # Check for empty SKUs
    if df["Set_SKU"].isna().any() or (df["Set_SKU"] == "").any():
        raise ValueError("CSV contains empty Set_SKU values")

    if df["Component_SKU"].isna().any() or (df["Component_SKU"] == "").any():
        raise ValueError("CSV contains empty Component_SKU values")

    # Check for invalid quantities
    try:
        df["Component_Quantity"] = df["Component_Quantity"].astype(int)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Component_Quantity must be integers: {e}")

    if (df["Component_Quantity"] <= 0).any():
        raise ValueError("All Component_Quantity values must be positive integers")

    # Check for duplicate (Set_SKU, Component_SKU) pairs
    duplicates = df.duplicated(subset=["Set_SKU", "Component_SKU"], keep=False)
    if duplicates.any():
        duplicate_rows = df[duplicates][["Set_SKU", "Component_SKU"]].drop_duplicates()
        logger.warning(f"CSV contains duplicate (Set_SKU, Component_SKU) pairs: {duplicate_rows.to_dict('records')}")
        # Keep last occurrence
        df = df.drop_duplicates(subset=["Set_SKU", "Component_SKU"], keep="last")

    # Build set_decoders dict
    set_decoders = {}
    for set_sku, group in df.groupby("Set_SKU"):
        components = []
        for _, row in group.iterrows():
            components.append({
                "sku": str(row["Component_SKU"]),
                "quantity": int(row["Component_Quantity"])
            })
        set_decoders[str(set_sku)] = components

    logger.info(f"Imported {len(set_decoders)} set definitions from {csv_path}")

    return set_decoders


def export_sets_to_csv(
    set_decoders: Dict[str, List[Dict[str, Any]]],
    csv_path: str
) -> None:
    """
    Export set definitions to CSV file.

    Args:
        set_decoders: Dict mapping set SKUs to components
        csv_path: Output CSV file path

    CSV Format:
        Set_SKU,Component_SKU,Component_Quantity
        SET-A,COMP-1,1
        SET-A,COMP-2,2

    Raises:
        ValueError: If set_decoders is empty
        IOError: If file cannot be written
    """
    if not set_decoders:
        raise ValueError("No sets to export (set_decoders is empty)")

    # Flatten dict to rows
    rows = []
    for set_sku, components in set_decoders.items():
        if not components:
            logger.warning(f"Set '{set_sku}' has no components, skipping")
            continue

        for component in components:
            rows.append({
                "Set_SKU": set_sku,
                "Component_SKU": component.get("sku", ""),
                "Component_Quantity": component.get("quantity", 0)
            })

    if not rows:
        raise ValueError("No valid components to export")

    # Create DataFrame and save
    df = pd.DataFrame(rows)

    try:
        df.to_csv(csv_path, index=False, encoding="utf-8")
        logger.info(f"Exported {len(set_decoders)} set definitions to {csv_path}")
    except Exception as e:
        raise IOError(f"Failed to write CSV file: {e}")
