"""
Set/Bundle decoder module for expanding sets into component SKUs.

This module provides functionality to:
1. Decode set/bundle SKUs into individual component SKUs
2. Import/export set definitions from/to CSV files
3. Track original set information during expansion
"""

import logging
from collections.abc import Iterable
from typing import Any

import pandas as pd

from .csv_utils import normalize_sku

logger = logging.getLogger(__name__)


def _lists_itself(sku, set_decoders) -> bool:
    return any(c.get("sku") == sku for c in set_decoders.get(sku) or [])


def _components(sku, quantity, set_decoders, path) -> list[tuple[str, Any]]:
    """(component SKU, quantity) pairs for `quantity` of set `sku`, nested sets expanded.

    A component that is itself a set is expanded, unless it lists itself
    (a product sold with extras, HERBAR NECTAR-30: its parent sets list the
    extras themselves) or it is already on `path` (a cycle). AUDIT-06-4.
    """
    out = []
    for component in set_decoders[sku]:
        component_sku = component.get("sku")
        component_qty = component.get("quantity")
        if not component_sku:
            logger.warning(f"Component in set '{sku}' has no SKU, skipping component")
            continue
        if not component_qty or component_qty <= 0:
            logger.warning(
                f"Component '{component_sku}' in set '{sku}' has invalid quantity: {component_qty}, skipping"
            )
            continue
        total = quantity * component_qty
        if component_sku in path and component_sku != sku:
            logger.warning(f"Set '{sku}' reaches '{component_sku}' again (a cycle); not expanding it")
        nested = (
            component_sku in set_decoders
            and component_sku not in path
            and not _lists_itself(component_sku, set_decoders)
        )
        inner = _components(component_sku, total, set_decoders, path | {component_sku}) if nested else []
        out.extend(inner or [(component_sku, total)])
    return out


def decode_sets_in_orders(
    orders_df: pd.DataFrame,
    set_decoders: dict[str, list[dict[str, Any]]]
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

    A component that is itself a set is expanded too, unless it lists
    itself or would loop (AUDIT-06-4).

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

    set_decoders = _normalized_decoders(set_decoders)
    work = orders_df.reset_index(drop=True)
    ordered_sets = [sku for sku in work["SKU"].unique() if _is_set(sku, set_decoders)]
    table = _set_table(set_decoders, ordered_sets)
    set_orders_count = int(work["SKU"].isin([s for s in ordered_sets if set_decoders[s]]).sum())

    # A set whose expansion is empty is absent from the table, so its line
    # stays as it is, like a plain line.
    is_set = work["SKU"].isin(table["Original_SKU"].unique()).to_numpy()
    plain = _with_tracking(work[~is_set], is_component=False)

    if is_set.any():
        lines = work[is_set]
        expanded = lines.assign(**{_POS: lines.index.to_numpy()}).merge(
            table.rename(columns={"Original_SKU": "__set", "SKU": "__component",
                                  "_per_unit": "__per_unit", "_seq": _SEQ}).astype({"__set": object}),
            left_on=lines["SKU"].astype(object).to_numpy(), right_on="__set", how="inner",
        )
        expanded = _with_tracking(expanded, is_component=True)
        expanded["SKU"] = expanded["__component"]
        expanded["Quantity"] = expanded["Quantity"] * expanded["__per_unit"]
        expanded = expanded[list(plain.columns)]
        result_df = pd.concat([plain, expanded], ignore_index=True) if len(plain) else expanded
        # Input order, each set's components in definition order.
        result_df = result_df.sort_values([_POS, _SEQ], kind="stable")
    else:
        result_df = plain

    result_df.index = orders_df.index[result_df[_POS].to_numpy()]
    result_df = result_df.drop(columns=[_POS, _SEQ])

    logger.info(
        f"Decoded {set_orders_count} set orders into components. "
        f"Total rows: {len(orders_df)} → {len(result_df)}"
    )

    return result_df


_POS = "__set_decoder_pos"
_SEQ = "__set_decoder_seq"


def _is_set(sku, set_decoders) -> bool:
    try:
        return sku in set_decoders
    except TypeError:  # an unhashable cell is never a set
        return False


def _with_tracking(lines: pd.DataFrame, is_component: bool) -> pd.DataFrame:
    """`lines` with the three tracking columns set from its own SKU and Quantity.

    Existing tracking columns keep their place; new ones go after the
    input's columns, as the per-row expansion did.
    """
    lines = lines.copy()
    lines["Original_SKU"] = lines["SKU"]
    lines["Original_Quantity"] = lines["Quantity"]
    lines["Is_Set_Component"] = is_component
    if _POS not in lines.columns:
        lines[_POS] = lines.index.to_numpy()
        lines[_SEQ] = 0
    return lines


def _normalized_decoders(set_decoders: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Set and component SKUs trimmed as order SKUs are (normalize_sku, AUDIT-09-O4).

    A set saved before imports trimmed its SKUs still expands. Two keys that
    trim to one SKU: the last one wins, with a warning.
    """
    normalized: dict[str, list[dict[str, Any]]] = {}
    for set_sku, components in set_decoders.items():
        key = normalize_sku(set_sku)
        if key in normalized:
            logger.warning(f"Sets '{key}' are defined twice (spaces aside); using the last one")
        normalized[key] = [
            {**component, "sku": normalize_sku(component.get("sku"))}
            for component in components or []
        ]
    return normalized


def _set_table(set_decoders: dict[str, list[dict[str, Any]]], skus: Iterable | None = None) -> pd.DataFrame:
    """One row per (set, component): Original_SKU, SKU, _per_unit, _seq.

    `_per_unit` is the component quantity in one unit of the set, nested sets
    expanded by the same rules as `_components` (a self-listing set or a
    cycle is not expanded). `_seq` is the component's place in the
    expansion. A set whose expansion is empty is absent; its warning is
    logged here, once per set. `skus` limits the table to those sets
    (default: every set).
    """
    rows = []
    for set_sku in set_decoders if skus is None else skus:
        if not set_decoders[set_sku]:
            logger.warning(f"Set '{set_sku}' has no components defined, skipping")
            continue
        expansion = _components(set_sku, 1, set_decoders, {set_sku})
        if not expansion:
            logger.warning(
                f"Set '{set_sku}' has no valid components after validation, keeping original row"
            )
            continue
        rows.extend(
            (set_sku, component_sku, per_unit, seq)
            for seq, (component_sku, per_unit) in enumerate(expansion)
        )
    return pd.DataFrame(rows, columns=["Original_SKU", "SKU", "_per_unit", "_seq"])


def import_sets_from_csv(csv_path: str) -> dict[str, list[dict[str, Any]]]:
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
        df = pd.read_csv(csv_path, dtype=str)
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

    # Trimmed as order SKUs are, before the checks below (AUDIT-09-O4)
    df["Set_SKU"] = df["Set_SKU"].map(normalize_sku)
    df["Component_SKU"] = df["Component_SKU"].map(normalize_sku)

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
    set_decoders: dict[str, list[dict[str, Any]]],
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
        raise OSError(f"Failed to write CSV file: {e}")
