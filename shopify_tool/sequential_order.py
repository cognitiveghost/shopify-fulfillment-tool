"""
Sequential Order Numbering System.

Provides consistent sequential numbering across barcode labels and reference labels.
Sequential numbers are generated once after analysis and persist across sessions.

Features:
- Numbers orders 1, 2, 3, ... based on analysis sort order
- Persists numbering in session (sequential_order.json)
- Reuses existing numbers across tool runs
- Shared between Barcode Generator and Reference Labels features

Usage:
    # Generate numbering after analysis
    order_map = generate_sequential_order_map(analysis_df, session_path)

    # Get number for specific order
    seq_num = get_sequential_number("ORDER-001", session_path)
"""

import logging
import json
import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

# Sequential order map version
SEQUENTIAL_ORDER_VERSION = "1.0"


def generate_sequential_order_map(
    analysis_results_df: pd.DataFrame,
    session_path: Path,
    force_regenerate: bool = False
) -> Dict[str, int]:
    """
    Generate sequential order numbers for all Fulfillable orders.

    Numbers orders 1, 2, 3, ... based on analysis results sort order.
    Only includes Fulfillable orders.

    The sequential order map is saved to session/analysis/sequential_order.json
    and reused across tool runs to maintain consistent numbering.

    Args:
        analysis_results_df: Analysis results DataFrame
        session_path: Path to session directory
        force_regenerate: If True, regenerate even if file exists (DANGEROUS!)

    Returns:
        Dict mapping Order_Number to sequential ID (1-indexed)

    Example:
        >>> order_map = generate_sequential_order_map(df, session_path)
        >>> order_map
        {'ORDER-001': 1, 'ORDER-002': 2, 'ORDER-003': 3}
    """
    json_path = session_path / "analysis" / "sequential_order.json"

    # Check if map already exists
    if json_path.exists() and not force_regenerate:
        logger.info(f"Sequential order map already exists: {json_path}")
        return load_sequential_order_map(session_path)

    # Filter to Fulfillable orders only
    fulfillable_df = analysis_results_df[
        analysis_results_df['Order_Fulfillment_Status'] == 'Fulfillable'
    ].copy()

    # Get unique order numbers (drop NaN to avoid JSON serialization failure)
    unique_orders = fulfillable_df['Order_Number'].dropna().unique()

    # Sort with numeric awareness (ORDER-1, ORDER-2, ORDER-10)
    def natural_sort_key(s):
        """Convert string to list of strings and numbers for natural sorting."""
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', str(s))]

    unique_orders_sorted = sorted(unique_orders, key=natural_sort_key)

    # Assign sequential numbers (1-indexed)
    order_map = {
        order_num: idx + 1
        for idx, order_num in enumerate(unique_orders_sorted)
    }

    # Save to JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": SEQUENTIAL_ORDER_VERSION,
        "generated_at": datetime.now().isoformat(),
        "total_orders": len(order_map),
        "order_sequence": order_map
    }

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Generated sequential order map: {len(order_map)} orders")

    return order_map


def load_sequential_order_map(session_path: Path) -> Dict[str, int]:
    """
    Load existing sequential order map from session.

    Args:
        session_path: Path to session directory

    Returns:
        Dict mapping Order_Number to sequential ID, or empty dict if not found
    """
    json_path = session_path / "analysis" / "sequential_order.json"

    if not json_path.exists():
        logger.warning(f"Sequential order map not found: {json_path}")
        return {}

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        order_map = data.get("order_sequence", {})
        logger.info(f"Loaded sequential order map: {len(order_map)} orders")
        return order_map

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to load sequential order map: {e}")
        return {}


def get_sequential_number(order_number: str, session_path: Path) -> Optional[int]:
    """
    Get sequential number for specific order.

    Args:
        order_number: Order number to look up
        session_path: Path to session directory

    Returns:
        Sequential number (1-indexed) or None if not found
    """
    order_map = load_sequential_order_map(session_path)
    return order_map.get(order_number)


def regenerate_sequential_order_map(
    analysis_results_df: pd.DataFrame,
    session_path: Path
) -> Dict[str, int]:
    """
    Force regeneration of sequential order map.

    USE WITH CAUTION: This will renumber all orders, invalidating
    previously printed barcode labels.

    Args:
        analysis_results_df: Analysis results DataFrame
        session_path: Path to session directory

    Returns:
        Dict mapping Order_Number to sequential ID
    """
    logger.warning("Force regenerating sequential order map (existing numbering will be lost)")
    return generate_sequential_order_map(
        analysis_results_df,
        session_path,
        force_regenerate=True
    )
