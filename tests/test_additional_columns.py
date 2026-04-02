"""
Unit tests for additional columns feature.

Tests the per-client dynamic column configuration functionality that allows
preserving additional CSV columns in the analysis results.
"""

import pytest
import pandas as pd
from shopify_tool.csv_utils import discover_additional_columns
from shopify_tool.analysis import _clean_and_prepare_data


class TestDiscoverAdditionalColumns:
    """Tests for the discover_additional_columns utility function."""

    def test_discover_with_empty_config(self):
        """Test discovery with no existing config."""
        # Create test dataframe with extra columns
        df = pd.DataFrame({
            "Name": ["Order1"],
            "Lineitem sku": ["SKU1"],
            "Email": ["test@example.com"],
            "Phone": ["+1234567890"]
        })

        column_mappings = {
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU"
            }
        }

        discovered = discover_additional_columns(df, column_mappings, [])

        # Should discover Email and Phone
        assert len(discovered) == 2
        csv_names = {col["csv_name"] for col in discovered}
        assert "Email" in csv_names
        assert "Phone" in csv_names

        # All should be disabled by default
        for col in discovered:
            assert col["enabled"] is False
            assert col["is_order_level"] is True
            assert col["exists_in_df"] is True

    def test_discover_preserves_enabled_state(self):
        """Test that discovery preserves existing enabled state."""
        df = pd.DataFrame({
            "Name": ["Order1"],
            "Email": ["test@example.com"],
            "Phone": ["+1234567890"]
        })

        column_mappings = {"orders": {"Name": "Order_Number"}}

        # Existing config with Email enabled
        current_config = [
            {
                "csv_name": "Email",
                "internal_name": "Email",
                "enabled": True,
                "is_order_level": True
            }
        ]

        discovered = discover_additional_columns(df, column_mappings, current_config)

        # Email should be enabled, Phone should be disabled
        email_col = next(col for col in discovered if col["csv_name"] == "Email")
        phone_col = next(col for col in discovered if col["csv_name"] == "Phone")

        assert email_col["enabled"] is True
        assert phone_col["enabled"] is False

    def test_discover_handles_missing_columns(self):
        """Test handling of previously configured columns missing from current CSV."""
        df = pd.DataFrame({
            "Name": ["Order1"],
            "Email": ["test@example.com"]
        })

        column_mappings = {"orders": {"Name": "Order_Number"}}

        # Config includes Phone which is not in current CSV
        current_config = [
            {
                "csv_name": "Phone",
                "internal_name": "Phone",
                "enabled": True,
                "is_order_level": True
            }
        ]

        discovered = discover_additional_columns(df, column_mappings, current_config)

        # Should include both Email (in CSV) and Phone (in config but not in CSV)
        assert len(discovered) == 2

        phone_col = next(col for col in discovered if col["csv_name"] == "Phone")
        email_col = next(col for col in discovered if col["csv_name"] == "Email")

        assert phone_col["exists_in_df"] is False
        assert email_col["exists_in_df"] is True

    def test_discover_skips_critical_columns(self):
        """Test that critical internal columns are skipped."""
        df = pd.DataFrame({
            "Name": ["Order1"],
            "SKU": ["SKU1"],  # SKU as CSV column (not mapped)
            "Quantity": [1],  # Quantity as CSV column (not mapped)
            "Email": ["test@example.com"]
        })

        column_mappings = {"orders": {"Name": "Order_Number"}}

        discovered = discover_additional_columns(df, column_mappings, [])

        # Should only discover Email, not SKU or Quantity
        csv_names = {col["csv_name"] for col in discovered}
        assert "Email" in csv_names
        assert "SKU" not in csv_names
        assert "Quantity" not in csv_names

    def test_normalize_column_names(self):
        """Test that column names are normalized correctly."""
        df = pd.DataFrame({
            "Name": ["Order1"],
            "Financial Status": ["paid"],
            "Billing-Address": ["123 Main St"]
        })

        column_mappings = {"orders": {"Name": "Order_Number"}}

        discovered = discover_additional_columns(df, column_mappings, [])

        # Check normalized internal names
        for col in discovered:
            if col["csv_name"] == "Financial Status":
                assert col["internal_name"] == "Financial_Status"
            elif col["csv_name"] == "Billing-Address":
                assert col["internal_name"] == "Billing_Address"


class TestAdditionalColumnsInAnalysis:
    """Tests for additional columns in the analysis pipeline."""

    def test_additional_columns_preserved(self):
        """Test that configured additional columns are preserved in analysis."""
        # Create test orders dataframe with extra columns
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1", "Order1"],
            "SKU": ["SKU1", "SKU2"],
            "Quantity": [1, 2],
            "Email": ["test@example.com", "test@example.com"],  # Additional column
            "Phone": ["+1234567890", "+1234567890"]  # Additional column
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1", "SKU2"],
            "Stock": [10, 20]
        })

        # Configure Email as additional column (enabled)
        additional_columns_config = [
            {
                "csv_name": "Email",
                "internal_name": "Email",
                "enabled": True,
                "is_order_level": True
            }
        ]

        cleaned_orders, cleaned_stock, _ = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,  # Use defaults
            additional_columns_config=additional_columns_config
        )

        # Email should be present, Phone should be dropped
        assert "Email" in cleaned_orders.columns
        assert "Phone" not in cleaned_orders.columns

    def test_additional_columns_order_level_forward_fill(self):
        """Test that order-level additional columns are forward-filled."""
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1", "Order1"],
            "SKU": ["SKU1", "SKU2"],
            "Quantity": [1, 2],
            "Email": ["test@example.com", None],  # Only first row has Email
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1", "SKU2"],
            "Stock": [10, 20]
        })

        additional_columns_config = [
            {
                "csv_name": "Email",
                "internal_name": "Email",
                "enabled": True,
                "is_order_level": True  # Should be forward-filled
            }
        ]

        cleaned_orders, _, _fifo = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,
            additional_columns_config=additional_columns_config
        )

        # Email should be forward-filled to second row
        assert cleaned_orders.iloc[1]["Email"] == "test@example.com"

    def test_additional_columns_missing_from_csv_silent_skip(self):
        """Test that missing configured columns are silently skipped."""
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1"],
            "SKU": ["SKU1"],
            "Quantity": [1]
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1"],
            "Stock": [10]
        })

        # Configure Email which doesn't exist in CSV
        additional_columns_config = [
            {
                "csv_name": "Email",
                "internal_name": "Email",
                "enabled": True,
                "is_order_level": True
            }
        ]

        # Should not raise exception
        cleaned_orders, _, _fifo = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,
            additional_columns_config=additional_columns_config
        )

        # Email should not be in result (missing from CSV)
        assert "Email" not in cleaned_orders.columns

    def test_backward_compatibility_empty_config(self):
        """Test that empty additional columns config behaves like current version."""
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1"],
            "SKU": ["SKU1"],
            "Quantity": [1],
            "Email": ["test@example.com"]
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1"],
            "Stock": [10]
        })

        # Empty config
        additional_columns_config = []

        cleaned_orders, _, _fifo = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,
            additional_columns_config=additional_columns_config
        )

        # Email should be dropped (not in base columns)
        assert "Email" not in cleaned_orders.columns

    def test_backward_compatibility_none_config(self):
        """Test that None additional columns config behaves like current version."""
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1"],
            "SKU": ["SKU1"],
            "Quantity": [1],
            "Email": ["test@example.com"]
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1"],
            "Stock": [10]
        })

        cleaned_orders, _, _fifo = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,
            additional_columns_config=None  # No config provided
        )

        # Email should be dropped (not in base columns)
        assert "Email" not in cleaned_orders.columns

    def test_multiple_additional_columns(self):
        """Test enabling multiple additional columns."""
        orders_df = pd.DataFrame({
            "Order_Number": ["Order1"],
            "SKU": ["SKU1"],
            "Quantity": [1],
            "Email": ["test@example.com"],
            "Phone": ["+1234567890"],
            "Financial_Status": ["paid"]
        })

        stock_df = pd.DataFrame({
            "SKU": ["SKU1"],
            "Stock": [10]
        })

        additional_columns_config = [
            {
                "csv_name": "Email",
                "internal_name": "Email",
                "enabled": True,
                "is_order_level": True
            },
            {
                "csv_name": "Phone",
                "internal_name": "Phone",
                "enabled": True,
                "is_order_level": True
            },
            {
                "csv_name": "Financial_Status",
                "internal_name": "Financial_Status",
                "enabled": True,
                "is_order_level": True
            }
        ]

        cleaned_orders, _, _fifo = _clean_and_prepare_data(
            orders_df,
            stock_df,
            column_mappings=None,
            additional_columns_config=additional_columns_config
        )

        # All additional columns should be present
        assert "Email" in cleaned_orders.columns
        assert "Phone" in cleaned_orders.columns
        assert "Financial_Status" in cleaned_orders.columns
