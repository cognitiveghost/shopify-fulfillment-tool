"""Unit tests for statistics enhancement features (tags breakdown and SKU summary)."""

import pytest
import pandas as pd
from shopify_tool.analysis import recalculate_statistics


def test_recalculate_statistics_with_tags():
    """Test that tags_breakdown counts per unique ORDER (union of tags per order).

    Order A (Fulfillable) has two SKU rows both carrying "Priority"; this still counts
    as 1 fulfillable order with "Priority".  Order B (Not Fulfillable) carries "Standard"
    and is tracked separately in tags_breakdown_not_fulfillable.
    """
    df = pd.DataFrame({
        "Order_Number": ["A", "A", "B"],
        "SKU": ["S1", "S2", "S3"],
        "Quantity": [1, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Not Fulfillable"],
        "Product_Name": ["Product 1", "Product 2", "Product 3"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 1", "Warehouse 2"],
        "Shipping_Provider": ["DHL", "DHL", "UPS"],
        "System_note": ["", "", ""],
        "Internal_Tags": ['["Priority", "Express"]', '["Priority"]', '["Standard"]']
    })

    stats = recalculate_statistics(df)

    # tags_breakdown = fulfillable only, per-order count
    assert "tags_breakdown" in stats
    assert stats["tags_breakdown"] is not None
    # Order A is 1 fulfillable order that has both Priority and Express
    assert stats["tags_breakdown"]["Priority"] == 1
    assert stats["tags_breakdown"]["Express"] == 1
    assert "Standard" not in stats["tags_breakdown"]  # Standard is not-fulfillable

    # Not-fulfillable breakdown
    assert stats["tags_breakdown_not_fulfillable"] is not None
    assert stats["tags_breakdown_not_fulfillable"]["Standard"] == 1


def test_recalculate_statistics_with_sku_summary():
    """Test that sku_summary is calculated correctly."""
    df = pd.DataFrame({
        "Order_Number": ["A", "A", "B"],
        "SKU": ["S1", "S1", "S2"],
        "Product_Name": ["Product 1", "Product 1", "Product 2"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 1", "Warehouse 2"],
        "Quantity": [2, 3, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Not Fulfillable"],
        "Shipping_Provider": ["DHL", "DHL", "UPS"],
        "System_note": ["", "", ""],
        "Internal_Tags": ["[]", "[]", "[]"]
    })

    stats = recalculate_statistics(df)

    assert "sku_summary" in stats
    assert stats["sku_summary"] is not None
    assert len(stats["sku_summary"]) == 2

    # S1 should be first (total qty = 5)
    s1_data = stats["sku_summary"][0]
    assert s1_data["SKU"] == "S1"
    assert s1_data["Total_Quantity"] == 5
    assert s1_data["Fulfillable_Items"] == 5  # Two fulfillable rows with qty 2+3
    assert s1_data["Not_Fulfillable_Items"] == 0


def test_recalculate_statistics_without_tags():
    """Test that function works when no Internal_Tags column."""
    df = pd.DataFrame({
        "Order_Number": ["A"],
        "SKU": ["S1"],
        "Product_Name": ["Product 1"],
        "Warehouse_Name": ["Warehouse 1"],
        "Quantity": [1],
        "Order_Fulfillment_Status": ["Fulfillable"],
        "Shipping_Provider": ["DHL"],
        "System_note": [""]
    })

    stats = recalculate_statistics(df)

    assert "tags_breakdown" in stats
    assert stats["tags_breakdown"] is None  # No tags column


def test_recalculate_statistics_with_empty_tags():
    """Test that function handles empty tags correctly."""
    df = pd.DataFrame({
        "Order_Number": ["A", "B"],
        "SKU": ["S1", "S2"],
        "Product_Name": ["Product 1", "Product 2"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 2"],
        "Quantity": [1, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable"],
        "Shipping_Provider": ["DHL", "UPS"],
        "System_note": ["", ""],
        "Internal_Tags": ["[]", "[]"]
    })

    stats = recalculate_statistics(df)

    assert "tags_breakdown" in stats
    # Empty tags should result in empty dict
    assert stats["tags_breakdown"] == {}


def test_recalculate_statistics_sku_sorting():
    """Test that SKU summary is sorted by total quantity (descending)."""
    df = pd.DataFrame({
        "Order_Number": ["A", "B", "C"],
        "SKU": ["S1", "S2", "S3"],
        "Product_Name": ["Product 1", "Product 2", "Product 3"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 2", "Warehouse 3"],
        "Quantity": [1, 5, 3],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Fulfillable"],
        "Shipping_Provider": ["DHL", "DHL", "UPS"],
        "System_note": ["", "", ""],
        "Internal_Tags": ["[]", "[]", "[]"]
    })

    stats = recalculate_statistics(df)

    assert "sku_summary" in stats
    assert stats["sku_summary"] is not None
    assert len(stats["sku_summary"]) == 3

    # Check ordering (descending by quantity)
    assert stats["sku_summary"][0]["SKU"] == "S2"
    assert stats["sku_summary"][0]["Total_Quantity"] == 5
    assert stats["sku_summary"][1]["SKU"] == "S3"
    assert stats["sku_summary"][1]["Total_Quantity"] == 3
    assert stats["sku_summary"][2]["SKU"] == "S1"
    assert stats["sku_summary"][2]["Total_Quantity"] == 1


def test_recalculate_statistics_tags_sorting():
    """Test that tags breakdown is sorted by count (descending)."""
    df = pd.DataFrame({
        "Order_Number": ["A", "B", "C"],
        "SKU": ["S1", "S2", "S3"],
        "Product_Name": ["Product 1", "Product 2", "Product 3"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 2", "Warehouse 3"],
        "Quantity": [1, 1, 1],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Fulfillable"],
        "Shipping_Provider": ["DHL", "DHL", "UPS"],
        "System_note": ["", "", ""],
        "Internal_Tags": ['["Priority"]', '["Priority", "Express"]', '["Express"]']
    })

    stats = recalculate_statistics(df)

    assert "tags_breakdown" in stats
    assert stats["tags_breakdown"] is not None

    # Check ordering (descending by count)
    tags_list = list(stats["tags_breakdown"].items())
    # Both Priority and Express have count 2, so they could be in either order
    # Just check that counts are in descending order
    counts = [count for tag, count in tags_list]
    assert counts == sorted(counts, reverse=True)


def test_recalculate_statistics_sku_fulfillable_counts():
    """Test that fulfillable and not fulfillable item counts are correct."""
    df = pd.DataFrame({
        "Order_Number": ["A", "B", "C", "D"],
        "SKU": ["S1", "S1", "S1", "S2"],
        "Product_Name": ["Product 1", "Product 1", "Product 1", "Product 2"],
        "Warehouse_Name": ["Warehouse 1", "Warehouse 1", "Warehouse 1", "Warehouse 2"],
        "Quantity": [2, 3, 1, 5],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Not Fulfillable", "Not Fulfillable"],
        "Shipping_Provider": ["DHL", "DHL", "UPS", "UPS"],
        "System_note": ["", "", "", ""],
        "Internal_Tags": ["[]", "[]", "[]", "[]"]
    })

    stats = recalculate_statistics(df)

    assert "sku_summary" in stats
    assert stats["sku_summary"] is not None

    # S1: total=6 (2+3+1), fulfillable=5 (2+3), not fulfillable=1
    s1_data = [s for s in stats["sku_summary"] if s["SKU"] == "S1"][0]
    assert s1_data["Total_Quantity"] == 6
    assert s1_data["Fulfillable_Items"] == 5  # Two fulfillable rows with qty 2+3
    assert s1_data["Not_Fulfillable_Items"] == 1  # 6 - 5

    # S2: total=5, fulfillable=0, not fulfillable=5
    s2_data = [s for s in stats["sku_summary"] if s["SKU"] == "S2"][0]
    assert s2_data["Total_Quantity"] == 5
    assert s2_data["Fulfillable_Items"] == 0
    assert s2_data["Not_Fulfillable_Items"] == 5
