"""Tests for column mapping system (v2).

Tests verify:
- V1 → V2 migration
- Column mapping application
- Different CSV sources (Shopify, WooCommerce, custom)
- SKU type normalization
- Product_Name priority
"""
import sys
import os
import pandas as pd
import pytest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shopify_tool import analysis, core
from shopify_tool.db_manager import get_db
from shopify_tool.profile_manager import ProfileManager


def _delete_test_client(client_id: str):
    db = get_db()
    try:
        db.execute("DELETE FROM clients WHERE client_id = %s", (client_id.upper(),))
    except Exception:
        pass


class TestV1ToV2Migration:
    """Test column mappings are stored and loaded in v2 format."""

    def test_migrate_v1_to_v2(self, tmp_path):
        """Test that column mappings round-trip correctly in v2 format."""
        _delete_test_client("TEST")
        profile_manager = ProfileManager(str(tmp_path))

        client_id = "TEST"
        profile_manager.create_client_profile(client_id, "Test Client")

        # Default config has v2 column_mappings
        config = profile_manager.load_shopify_config(client_id)
        assert "version" in config["column_mappings"]
        assert config["column_mappings"]["version"] == 2

        # Modify an orders mapping, save, and reload
        config["column_mappings"]["orders"]["Custom_Field"] = "Custom_Internal"
        profile_manager.save_shopify_config(client_id, config)

        reloaded = profile_manager.load_shopify_config(client_id)

        # Verify v2 format preserved
        assert "version" in reloaded["column_mappings"]
        assert reloaded["column_mappings"]["version"] == 2
        assert "orders" in reloaded["column_mappings"]
        assert "stock" in reloaded["column_mappings"]

        orders_mappings = reloaded["column_mappings"]["orders"]
        assert "Name" in orders_mappings
        assert orders_mappings["Name"] == "Order_Number"
        assert "Lineitem sku" in orders_mappings
        assert orders_mappings["Lineitem sku"] == "SKU"
        assert orders_mappings.get("Custom_Field") == "Custom_Internal"

        stock_mappings = reloaded["column_mappings"]["stock"]
        assert "Артикул" in stock_mappings
        assert stock_mappings["Артикул"] == "SKU"

        _delete_test_client("TEST")


class TestColumnMappingApplication:
    """Test that column mappings are correctly applied during analysis."""

    def test_shopify_default_mappings(self):
        """Test analysis with default Shopify column names."""
        # Create test data with Shopify column names
        orders_df = pd.DataFrame({
            "Name": ["ORD-001", "ORD-002"],
            "Lineitem sku": ["SKU-A", "SKU-B"],
            "Lineitem quantity": [2, 1],
            "Shipping Method": ["dhl", "dpd"],
            "Shipping Country": ["BG", "BG"],
            "Tags": ["", ""],
            "Notes": ["", ""]
        })

        stock_df = pd.DataFrame({
            "Артикул": ["SKU-A", "SKU-B"],
            "Име": ["Product A", "Product B"],
            "Наличност": [10, 5]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        # Run analysis with default mappings (None = use defaults)
        final_df, summary_present, summary_missing, stats = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Verify analysis ran successfully
        assert not final_df.empty
        assert "Order_Number" in final_df.columns
        assert "SKU" in final_df.columns
        assert "Quantity" in final_df.columns

        # Verify results
        assert final_df.loc[0, "Order_Number"] == "ORD-001"
        assert final_df.loc[0, "SKU"] == "SKU-A"

    def test_custom_column_names(self):
        """Test analysis with custom column names (WooCommerce-like)."""
        # Create test data with custom column names
        orders_df = pd.DataFrame({
            "Order ID": ["WOO-001", "WOO-002"],
            "Product SKU": ["ITEM-X", "ITEM-Y"],
            "Qty": [3, 2],
            "Shipping Service": ["DHL Express", "DPD Standard"],
            "Destination": ["Bulgaria", "Romania"],
            "Order Tags": ["", ""],
            "Customer Note": ["", ""]
        })

        stock_df = pd.DataFrame({
            "SKU": ["ITEM-X", "ITEM-Y"],
            "Name": ["Item X", "Item Y"],
            "QTY": [20, 10]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        # Custom mappings
        custom_mappings = {
            "version": 2,
            "orders": {
                "Order ID": "Order_Number",
                "Product SKU": "SKU",
                "Qty": "Quantity",
                "Shipping Service": "Shipping_Method",
                "Destination": "Shipping_Country",
                "Order Tags": "Tags",
                "Customer Note": "Notes"
            },
            "stock": {
                "SKU": "SKU",
                "Name": "Product_Name",
                "QTY": "Stock"
            }
        }

        # Run analysis with custom mappings
        final_df, summary_present, summary_missing, stats = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=custom_mappings
        )

        # Verify analysis ran successfully
        assert not final_df.empty
        assert final_df.loc[0, "Order_Number"] == "WOO-001"
        assert final_df.loc[0, "SKU"] == "ITEM-X"
        assert final_df.loc[0, "Quantity"] == 3


class TestSKUTypeNormalization:
    """Test SKU type normalization for consistent merging."""

    def test_int_sku_in_orders_string_sku_in_stock(self):
        """Test when orders has int SKU and stock has string SKU."""
        orders_df = pd.DataFrame({
            "Name": ["ORD-001"],
            "Lineitem sku": [12345],  # Integer SKU
            "Lineitem quantity": [1],
            "Shipping Method": ["dhl"],
            "Shipping Country": ["BG"],
            "Tags": [""],
            "Notes": [""]
        })

        stock_df = pd.DataFrame({
            "Артикул": ["12345"],  # String SKU
            "Име": ["Product"],
            "Наличност": [10]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        # Should not raise ValueError about type mismatch
        final_df, _, _, _ = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Verify merge worked
        assert not final_df.empty
        assert final_df.loc[0, "SKU"] == "12345"  # Normalized to string
        assert final_df.loc[0, "Stock"] == 10

    def test_mixed_sku_types(self):
        """Test with mixed SKU types in both files."""
        orders_df = pd.DataFrame({
            "Name": ["ORD-001", "ORD-002", "ORD-003"],
            "Lineitem sku": [123, "ABC-456", "789 "],  # Mixed: int, string, string with whitespace
            "Lineitem quantity": [1, 2, 1],
            "Shipping Method": ["dhl", "dpd", "dhl"],
            "Shipping Country": ["BG", "BG", "BG"],
            "Tags": ["", "", ""],
            "Notes": ["", "", ""]
        })

        stock_df = pd.DataFrame({
            "Артикул": ["123 ", " ABC-456", 789],  # Mixed with whitespace
            "Име": ["Product A", "Product B", "Product C"],
            "Наличност": [10, 20, 5]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        final_df, _, _, _ = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Verify all SKUs matched (normalized and trimmed)
        assert not final_df.empty
        assert len(final_df) == 3
        # All should have stock (successful merge)
        assert all(final_df["Stock"] > 0)


class TestProductNamePriority:
    """Test Product_Name priority from orders over stock."""

    def test_product_name_from_orders_priority(self):
        """Test that Product_Name from orders has priority over stock."""
        orders_df = pd.DataFrame({
            "Name": ["ORD-001"],
            "Lineitem sku": ["SKU-001"],
            "Lineitem quantity": [1],
            "Lineitem name": ["Detailed Product Name from Order"],  # Product_Name from orders
            "Shipping Method": ["dhl"],
            "Shipping Country": ["BG"],
            "Tags": [""],
            "Notes": [""]
        })

        stock_df = pd.DataFrame({
            "Артикул": ["SKU-001"],
            "Име": ["Short Name from Stock"],  # Product_Name from stock
            "Наличност": [10]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        final_df, _, _, _ = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Verify Product_Name from orders is used
        assert final_df.loc[0, "Product_Name"] == "Detailed Product Name from Order"
        # Stock Product_Name should be dropped
        assert "Product_Name_stock" not in final_df.columns

    def test_product_name_only_in_stock(self):
        """Test when Product_Name exists only in stock."""
        orders_df = pd.DataFrame({
            "Name": ["ORD-001"],
            "Lineitem sku": ["SKU-001"],
            "Lineitem quantity": [1],
            # No "Lineitem name" column
            "Shipping Method": ["dhl"],
            "Shipping Country": ["BG"],
            "Tags": [""],
            "Notes": [""]
        })

        stock_df = pd.DataFrame({
            "Артикул": ["SKU-001"],
            "Име": ["Product Name from Stock"],
            "Наличност": [10]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        final_df, _, _, _ = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Verify Product_Name from stock is used when orders doesn't have it
        assert final_df.loc[0, "Product_Name"] == "Product Name from Stock"


class TestValidation:
    """Test validation with v2 column mappings."""

    def test_validation_checks_csv_column_names(self):
        """Test that validation checks CSV column names, not internal names."""
        orders_df = pd.DataFrame({
            "Name": [1],  # Has Name (CSV name)
            # Missing: Lineitem sku, Lineitem quantity, Shipping Method
        })

        stock_df = pd.DataFrame({
            "Артикул": ["SKU-001"],  # Has Артикул (CSV name)
            # Missing: Наличност
        })

        config = {
            "column_mappings": {
                "version": 2,
                "orders": {
                    "Name": "Order_Number",
                    "Lineitem sku": "SKU",
                    "Lineitem quantity": "Quantity",
                    "Shipping Method": "Shipping_Method"
                },
                "stock": {
                    "Артикул": "SKU",
                    "Наличност": "Stock"
                }
            }
        }

        errors = core._validate_dataframes(orders_df, stock_df, config)

        # Should have 4 errors
        assert len(errors) == 4

        # Check for CSV column names in error messages
        assert any("Lineitem sku" in err for err in errors)
        assert any("Lineitem quantity" in err for err in errors)
        assert any("Shipping Method" in err for err in errors)
        assert any("Наличност" in err for err in errors)


class TestBackwardCompatibility:
    """Test backward compatibility with DataFrames that already use internal names."""

    def test_dataframes_with_internal_names(self):
        """Test that DataFrames with internal names work without mapping."""
        # DataFrames already have internal names (like in old tests)
        orders_df = pd.DataFrame({
            "Order_Number": ["ORD-001", "ORD-002"],
            "SKU": ["SKU-A", "SKU-B"],
            "Quantity": [2, 1],
            "Shipping_Method": ["dhl", "dpd"],
            "Shipping_Country": ["BG", "BG"]
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU-A", "SKU-B"],
            "Product_Name": ["Product A", "Product B"],
            "Stock": [10, 5]
        })

        history_df = pd.DataFrame({"Order_Number": []})

        # Run with column_mappings=None (should detect internal names and skip mapping)
        final_df, _, _, _ = analysis.run_analysis(
            stock_df, orders_df, history_df, column_mappings=None
        )

        # Should work correctly
        assert not final_df.empty
        assert final_df.loc[0, "Order_Number"] == "ORD-001"
        assert final_df.loc[0, "SKU"] == "SKU-A"
