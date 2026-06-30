import pytest
import pandas as pd
import sys
import os

# Add the project root to the Python path to allow for correct module imports
# This ensures that we can import from the 'shopify_tool' package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shopify_tool.analysis import (
    _generalize_shipping_method,
    _prioritize_orders,
    run_analysis,
    toggle_order_fulfillment,
)


# Test cases for the _generalize_shipping_method function
# We use @pytest.mark.parametrize to run the same test with different inputs and expected outputs.
# This is an efficient way to test multiple scenarios.
@pytest.mark.parametrize(
    "input_method, expected_output",
    [
        ("dhl express", "DHL"),
        ("some other dhl service", "DHL"),
        ("DPD Standard", "DPD"),
        ("dpd", "DPD"),
        ("international shipping", "PostOne"),
        ("Some Custom Method", "Some Custom Method"),
        ("unknown", "Unknown"),
        (None, "Unknown"),
        (pd.NA, "Unknown"),
        ("", "Unknown"),  # An empty string should be handled as 'Unknown'
    ],
)
def test_generalize_shipping_method(input_method, expected_output):
    """
    Tests the _generalize_shipping_method function with various inputs using hardcoded fallback.

    Args:
        input_method (str or None): The raw shipping method string to test.
        expected_output (str): The expected standardized string.
    """
    # The assert statement checks if the function's output matches the expected output.
    # If they don't match, pytest will report a failure.
    assert _generalize_shipping_method(input_method) == expected_output


# Test cases for _generalize_shipping_method with courier_mappings parameter
@pytest.mark.parametrize(
    "input_method, courier_mappings, expected_output",
    [
        # New format tests
        ("dhl express", {"DHL": {"patterns": ["dhl"]}}, "DHL"),
        ("DHL Standard", {"DHL": {"patterns": ["dhl", "dhl express"]}}, "DHL"),
        ("dpd next day", {"DPD": {"patterns": ["dpd"]}}, "DPD"),
        ("speedy delivery", {"Speedy": {"patterns": ["speedy"]}}, "Speedy"),
        (
            "fedex overnight",
            {"FedEx": {"patterns": ["fedex", "federal express"]}},
            "FedEx",
        ),
        # Legacy format tests
        ("dhl express", {"dhl": "DHL", "dpd": "DPD"}, "DHL"),
        ("dpd standard", {"dhl": "DHL", "dpd": "DPD"}, "DPD"),
        ("speedy delivery", {"speedy": "Speedy"}, "Speedy"),
        # Custom couriers
        ("econt express", {"Econt": {"patterns": ["econt"]}}, "Econt"),
        ("my custom courier", {"CustomCo": {"patterns": ["custom"]}}, "CustomCo"),
        # Fallback for unknown couriers
        ("unknown courier", {"DHL": {"patterns": ["dhl"]}}, "Unknown Courier"),
        ("random service", {}, "Random Service"),
        # NaN and empty values
        (None, {"DHL": {"patterns": ["dhl"]}}, "Unknown"),
        (pd.NA, {"DHL": {"patterns": ["dhl"]}}, "Unknown"),
        ("", {"DHL": {"patterns": ["dhl"]}}, "Unknown"),
        ("  ", {"DHL": {"patterns": ["dhl"]}}, "Unknown"),
        # Empty courier_mappings should fall back to hardcoded rules
        ("dhl express", {}, "DHL"),
        ("dpd standard", {}, "DPD"),
        ("international shipping", {}, "PostOne"),
        ("custom method", {}, "Custom Method"),
    ],
)
def test_generalize_shipping_method_with_mappings(
    input_method, courier_mappings, expected_output
):
    """
    Tests the _generalize_shipping_method function with courier_mappings parameter.

    Args:
        input_method (str or None): The raw shipping method string to test.
        courier_mappings (dict): The courier mappings configuration.
        expected_output (str): The expected standardized string.
    """
    assert (
        _generalize_shipping_method(input_method, courier_mappings) == expected_output
    )


def test_run_analysis_with_courier_mappings():
    """Tests that run_analysis correctly uses courier_mappings parameter."""
    # Create test data
    stock_df = pd.DataFrame(
        {"Артикул": ["SKU-1"], "Име": ["Test Product"], "Наличност": [10]}
    )

    orders_df = pd.DataFrame(
        {
            "Name": ["1001", "1002", "1003"],
            "Lineitem sku": ["SKU-1", "SKU-1", "SKU-1"],
            "Lineitem quantity": [1, 1, 1],
            "Shipping Method": ["fedex overnight", "econt express", "custom delivery"],
            "Shipping Country": ["US", "BG", "UK"],
            "Tags": ["", "", ""],
            "Notes": ["", "", ""],
        }
    )

    history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

    # Define custom courier mappings (new format)
    courier_mappings = {
        "FedEx": {"patterns": ["fedex", "federal express"]},
        "Econt": {"patterns": ["econt"]},
        "CustomCo": {"patterns": ["custom"]},
    }

    # Run analysis with courier mappings
    final_df, _, _, _ = run_analysis(
        stock_df, orders_df, history_df, None, courier_mappings
    )

    # Check that shipping providers are correctly mapped
    providers = final_df.set_index("Order_Number")["Shipping_Provider"]
    assert providers["1001"] == "FedEx"
    assert providers["1002"] == "Econt"
    assert providers["1003"] == "CustomCo"


def test_run_analysis_with_legacy_courier_mappings():
    """Tests that run_analysis correctly uses legacy courier_mappings format."""
    # Create test data
    stock_df = pd.DataFrame(
        {"Артикул": ["SKU-1"], "Име": ["Test Product"], "Наличност": [10]}
    )

    orders_df = pd.DataFrame(
        {
            "Name": ["1001", "1002"],
            "Lineitem sku": ["SKU-1", "SKU-1"],
            "Lineitem quantity": [1, 1],
            "Shipping Method": ["dhl express", "speedy delivery"],
            "Shipping Country": ["DE", "BG"],
            "Tags": ["", ""],
            "Notes": ["", ""],
        }
    )

    history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

    # Define legacy courier mappings
    courier_mappings = {"dhl": "DHL", "speedy": "Speedy"}

    # Run analysis with legacy courier mappings
    final_df, _, _, _ = run_analysis(
        stock_df, orders_df, history_df, None, courier_mappings
    )

    # Check that shipping providers are correctly mapped
    providers = final_df.set_index("Order_Number")["Shipping_Provider"]
    assert providers["1001"] == "DHL"
    assert providers["1002"] == "Speedy"


def test_run_analysis_without_courier_mappings():
    """Tests that run_analysis works without courier_mappings (backward compatibility)."""
    # Create test data
    stock_df = pd.DataFrame(
        {"Артикул": ["SKU-1"], "Име": ["Test Product"], "Наличност": [10]}
    )

    orders_df = pd.DataFrame(
        {
            "Name": ["1001", "1002", "1003"],
            "Lineitem sku": ["SKU-1", "SKU-1", "SKU-1"],
            "Lineitem quantity": [1, 1, 1],
            "Shipping Method": [
                "dhl express",
                "dpd standard",
                "international shipping",
            ],
            "Shipping Country": ["DE", "BG", "UK"],
            "Tags": ["", "", ""],
            "Notes": ["", "", ""],
        }
    )

    history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

    # Run analysis without courier mappings (should use hardcoded fallback)
    final_df, _, _, _ = run_analysis(stock_df, orders_df, history_df)

    # Check that shipping providers are correctly mapped using hardcoded rules
    providers = final_df.set_index("Order_Number")["Shipping_Provider"]
    assert providers["1001"] == "DHL"
    assert providers["1002"] == "DPD"
    assert providers["1003"] == "PostOne"


def test_fulfillment_prioritization_logic():
    """Tests that the fulfillment logic correctly prioritizes multi-item orders."""
    # Create a stock of 4 for a single SKU. This is the key to the test.
    # It's enough to fulfill the two multi-item orders (2+2=4), but not any of the single-item orders.
    stock_df = pd.DataFrame(
        {"Артикул": ["SKU-1"], "Име": ["Test Product"], "Наличност": [4]}
    )

    # Create four orders for the same SKU with different priorities
    # Order 1001: Older, Multi-item (2 items) - Priority 1
    # Order 1002: Newer, Multi-item (2 items) - Priority 2
    # Order 1003: Older, Single-item (1 item) - Priority 3
    # Order 1004: Newer, Single-item (1 item) - Priority 4
    orders_df = pd.DataFrame(
        {
            "Name": ["1002", "1002", "1001", "1001", "1004", "1003"],
            "Lineitem sku": ["SKU-1", "SKU-1", "SKU-1", "SKU-1", "SKU-1", "SKU-1"],
            "Lineitem quantity": [1, 1, 1, 1, 1, 1],  # Each row is one item
            "Shipping Method": ["dhl"] * 6,
            "Shipping Country": ["BG"] * 6,
            "Tags": [""] * 6,
            "Notes": [""] * 6,
        }
    )

    # Empty history
    history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

    # With stock of 5, only the two multi-item orders should be fulfilled (2+2=4 items)
    # The single-item orders should not be fulfilled.
    final_df, _, _, _ = run_analysis(stock_df, orders_df, history_df)

    # Check status of each order
    status_map = final_df.drop_duplicates(subset=["Order_Number"]).set_index(
        "Order_Number"
    )["Order_Fulfillment_Status"]

    assert status_map["1001"] == "Fulfillable"  # Priority 1
    assert status_map["1002"] == "Fulfillable"  # Priority 2
    assert status_map["1003"] == "Not Fulfillable"  # Priority 3
    assert status_map["1004"] == "Not Fulfillable"  # Priority 4


def test_summary_missing_report():
    """Tests that the missing items summary is correctly generated."""
    stock_df = pd.DataFrame({"Артикул": ["SKU-1"], "Име": ["P1"], "Наличност": [5]})
    orders_df = pd.DataFrame(
        {
            "Name": ["1001"],
            "Lineitem sku": ["SKU-1"],
            "Lineitem quantity": [10],  # Require 10, but only 5 are in stock
            "Shipping Method": ["dhl"],
            "Shipping Country": ["BG"],
            "Tags": [""],
            "Notes": [""],
        }
    )
    history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

    _, _, summary_missing_df, _ = run_analysis(stock_df, orders_df, history_df)

    assert not summary_missing_df.empty
    assert len(summary_missing_df) == 1
    assert summary_missing_df.iloc[0]["SKU"] == "SKU-1"
    assert summary_missing_df.iloc[0]["Total Quantity"] == 10


@pytest.fixture
def sample_analysis_df():
    """Provides a sample analysis DataFrame fixture for testing."""
    df = pd.DataFrame(
        {
            "Order_Number": ["1001", "1001", "1002"],
            "SKU": ["SKU-A", "SKU-B", "SKU-A"],
            "Quantity": [1, 2, 3],
            "Stock": [10, 10, 10],
            "Final_Stock": [
                6,
                8,
                6,
            ],  # Note: Both SKU-A rows have the same final stock initially
            "Order_Fulfillment_Status": [
                "Fulfillable",
                "Fulfillable",
                "Not Fulfillable",
            ],
        }
    )
    # Ensure all rows for a given SKU start with the same Final_Stock
    df["Final_Stock"] = df.groupby("SKU")["Final_Stock"].transform("first")
    return df


class TestToggleOrderFulfillment:
    """Groups tests for the toggle_order_fulfillment function."""

    def test_toggle_fulfillable_to_not_fulfillable(self, sample_analysis_df):
        """Tests changing an order from 'Fulfillable' to 'Not Fulfillable'."""
        df = sample_analysis_df.copy()

        # Un-fulfill order 1001 (contains SKU-A:1, SKU-B:2)
        success, _, updated_df = toggle_order_fulfillment(df, "1001")

        assert success
        # Stock for SKU-A (6) should increase by 1 -> 7. This affects all SKU-A rows.
        # Stock for SKU-B (8) should increase by 2 -> 10.
        assert all(updated_df[updated_df["SKU"] == "SKU-A"]["Final_Stock"] == 7)
        assert all(updated_df[updated_df["SKU"] == "SKU-B"]["Final_Stock"] == 10)
        assert all(
            updated_df[updated_df["Order_Number"] == "1001"]["Order_Fulfillment_Status"]
            == "Not Fulfillable"
        )

    def test_toggle_not_fulfillable_to_fulfillable_success(self, sample_analysis_df):
        """Tests successfully changing an order to 'Fulfillable' when stock is sufficient."""
        df = sample_analysis_df.copy()
        # Stock for SKU-A is 6. Order 1002 needs 3. This should succeed.

        success, _, updated_df = toggle_order_fulfillment(df, "1002")

        assert success
        # Stock for SKU-A (6) should decrease by 3 -> 3. This affects all SKU-A rows.
        assert all(updated_df[updated_df["SKU"] == "SKU-A"]["Final_Stock"] == 3)
        assert all(
            updated_df[updated_df["Order_Number"] == "1002"]["Order_Fulfillment_Status"]
            == "Fulfillable"
        )

    def test_toggle_not_fulfillable_to_fulfillable_fail_no_stock(
        self, sample_analysis_df
    ):
        """Tests that changing an order to 'Fulfillable' fails when stock is insufficient."""
        df = sample_analysis_df.copy()
        # Order 1002 needs 3 of SKU-A, but let's set the stock to 2
        df.loc[df["SKU"] == "SKU-A", "Final_Stock"] = 2

        success, error_msg, updated_df = toggle_order_fulfillment(df, "1002")

        assert not success
        assert "Insufficient stock" in error_msg
        # The dataframe should not have been changed
        assert all(updated_df[updated_df["SKU"] == "SKU-A"]["Final_Stock"] == 2)
        assert all(
            updated_df[updated_df["Order_Number"] == "1002"]["Order_Fulfillment_Status"]
            == "Not Fulfillable"
        )


# ---------------------------------------------------------------------------
# Tests for _prioritize_orders analysis mode
# ---------------------------------------------------------------------------


@pytest.fixture()
def mixed_orders_df():
    """Orders DataFrame with a mix of multi-item and single-item orders.

    Order #999  → 3 lines (oldest by number)
    Order #1001 → 1 line
    Order #1002 → 2 lines
    """
    return pd.DataFrame(
        {
            "Order_Number": ["#999", "#999", "#999", "#1001", "#1002", "#1002"],
            "SKU": ["A", "B", "C", "A", "B", "C"],
            "Quantity": [1, 1, 1, 1, 1, 1],
        }
    )


class TestPrioritizeOrders:
    def test_multi_first_puts_most_items_first(self, mixed_orders_df):
        result = _prioritize_orders(mixed_orders_df, mode="multi_first")
        order_seq = list(result["Order_Number"])
        # #999 has 3 items — must come first
        assert order_seq[0] == "#999"
        # #1002 has 2 items — must come before #1001 (1 item)
        assert order_seq[1] == "#1002"
        assert order_seq[2] == "#1001"

    def test_fifo_orders_strictly_by_number(self, mixed_orders_df):
        result = _prioritize_orders(mixed_orders_df, mode="fifo")
        order_seq = list(result["Order_Number"])
        # Purely ascending by order number: #999 < #1001 < #1002
        assert order_seq == ["#999", "#1001", "#1002"]

    def test_default_mode_is_multi_first(self, mixed_orders_df):
        default_result = _prioritize_orders(mixed_orders_df)
        explicit_result = _prioritize_orders(mixed_orders_df, mode="multi_first")
        assert list(default_result["Order_Number"]) == list(
            explicit_result["Order_Number"]
        )

    def test_run_analysis_accepts_mode_kwarg(self):
        """Smoke-test: run_analysis accepts mode without raising."""
        stock = pd.DataFrame({"SKU": ["A"], "Stock": [10]})
        orders = pd.DataFrame(
            {
                "Name": ["#1", "#1"],
                "Lineitem sku": ["A", "A"],
                "Lineitem quantity": [1, 1],
                "Shipping Method": ["Standard", "Standard"],
            }
        )
        history = pd.DataFrame({"Order_Number": []})
        column_mappings = {
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Shipping Method": "Shipping_Method",
            },
            "stock": {"SKU": "SKU", "Stock": "Stock"},
            "version": 2,
        }
        # Should not raise regardless of mode
        for mode in ("multi_first", "fifo"):
            final_df, _, _, _ = run_analysis(
                stock, orders, history, column_mappings=column_mappings, mode=mode
            )
            assert not final_df.empty
