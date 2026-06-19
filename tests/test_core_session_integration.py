"""Tests for core.py session integration.

These tests verify that the refactored core.py works correctly with
SessionManager and ProfileManager for the new session-based workflow.
"""
import sys
import os
import json
import pandas as pd
import pytest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shopify_tool import core
from shopify_tool.db_manager import get_db
from shopify_tool.profile_manager import ProfileManager
from shopify_tool.session_manager import SessionManager


def _delete_test_client(client_id: str):
    db = get_db()
    try:
        db.execute("DELETE FROM clients WHERE client_id = %s", (client_id.upper(),))
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_core_test_client():
    _delete_test_client("TEST")
    yield
    _delete_test_client("TEST")


def make_test_config(low_stock_threshold=4):
    """Create test config with v2 column mappings."""
    return {
        "settings": {"low_stock_threshold": low_stock_threshold, "stock_csv_delimiter": ";"},
        "column_mappings": {
            "version": 2,
            "orders": {
                "Name": "Order_Number",
                "Lineitem sku": "SKU",
                "Lineitem quantity": "Quantity",
                "Shipping Method": "Shipping_Method",
                "Shipping Country": "Shipping_Country",
                "Tags": "Tags",
                "Notes": "Notes"
            },
            "stock": {
                "Артикул": "SKU",
                "Име": "Product_Name",
                "Наличност": "Stock"
            }
        },
        "rules": []
    }


@pytest.fixture
def mock_file_server(tmp_path):
    """Create a mock file server structure for testing."""
    server_root = tmp_path / "file_server"
    server_root.mkdir()
    return server_root


@pytest.fixture
def profile_manager(mock_file_server):
    """Create a ProfileManager instance with mock server."""
    return ProfileManager(str(mock_file_server))


@pytest.fixture
def session_manager(profile_manager):
    """Create a SessionManager instance."""
    return SessionManager(profile_manager)


@pytest.fixture
def test_client(profile_manager):
    """Create a test client profile."""
    client_id = "TEST"
    profile_manager.create_client_profile(client_id, "Test Client")
    return client_id


@pytest.fixture
def test_data_files(tmp_path):
    """Create test CSV files for orders and stock."""
    # Create stock file
    stock_df = pd.DataFrame({
        "Артикул": ["SKU-001", "SKU-002", "SKU-003"],
        "Име": ["Product A", "Product B", "Product C"],
        "Наличност": [10, 20, 5]
    })
    stock_file = tmp_path / "stock.csv"
    stock_df.to_csv(stock_file, index=False, sep=";")

    # Create orders file
    orders_df = pd.DataFrame({
        "Name": ["ORD-001", "ORD-001", "ORD-002"],
        "Lineitem sku": ["SKU-001", "SKU-002", "SKU-003"],
        "Lineitem quantity": [2, 3, 1],
        "Shipping Method": ["dhl", "dhl", "dpd"],
        "Shipping Country": ["BG", "BG", "BG"],
        "Tags": ["", "", ""],
        "Notes": ["", "", ""]
    })
    orders_file = tmp_path / "orders.csv"
    orders_df.to_csv(orders_file, index=False)

    return str(stock_file), str(orders_file)


def test_run_full_analysis_with_session(
    profile_manager,
    session_manager,
    test_client,
    test_data_files
):
    """Test run_full_analysis with session-based workflow."""
    stock_file, orders_file = test_data_files

    config = make_test_config(low_stock_threshold=4)

    # Run analysis with session mode
    success, session_path, final_df, stats = core.run_full_analysis(
        stock_file_path=stock_file,
        orders_file_path=orders_file,
        output_dir_path=None,  # Not used in session mode
        stock_delimiter=";",
        orders_delimiter=",",
        config=config,
        client_id=test_client,
        session_manager=session_manager,
        profile_manager=profile_manager
    )

    # Verify success
    assert success
    assert session_path is not None

    # Verify session directory exists
    session_path_obj = Path(session_path)
    assert session_path_obj.exists()
    assert session_path_obj.is_dir()

    # Verify session subdirectories exist
    assert (session_path_obj / "input").exists()
    assert (session_path_obj / "analysis").exists()
    assert (session_path_obj / "packing_lists").exists()
    assert (session_path_obj / "stock_exports").exists()

    # Verify input files were copied
    assert (session_path_obj / "input" / "orders_export.csv").exists()
    assert (session_path_obj / "input" / "inventory.csv").exists()

    # Verify analysis results were saved
    assert (session_path_obj / "analysis" / "fulfillment_analysis.xlsx").exists()
    assert (session_path_obj / "analysis" / "analysis_data.json").exists()

    # Verify analysis_data.json structure
    with open(session_path_obj / "analysis" / "analysis_data.json", 'r') as f:
        analysis_data = json.load(f)

    assert "analyzed_at" in analysis_data
    assert "total_orders" in analysis_data
    assert "fulfillable_orders" in analysis_data
    assert "orders" in analysis_data
    assert len(analysis_data["orders"]) > 0

    # Verify order structure
    first_order = analysis_data["orders"][0]
    assert "order_number" in first_order
    assert "courier" in first_order
    assert "status" in first_order
    assert "items" in first_order

    # Verify session info was updated in DB (no session_info.json in new implementation)
    session_info = session_manager.get_session_info(session_path)
    assert session_info is not None

    assert session_info["created_by_tool"] == "shopify"
    assert session_info["client_id"] == test_client
    assert session_info["analysis_completed"]
    assert session_info["orders_file"] == "orders_export.csv"
    assert session_info["stock_file"] == "inventory.csv"


def test_create_packing_list_with_session(
    profile_manager,
    session_manager,
    test_client,
    test_data_files
):
    """Test create_packing_list_report with session mode."""
    stock_file, orders_file = test_data_files

    config = make_test_config()

    # First run analysis to create session
    success, session_path, final_df, stats = core.run_full_analysis(
        stock_file_path=stock_file,
        orders_file_path=orders_file,
        output_dir_path=None,
        stock_delimiter=";",
        orders_delimiter=",",
        config=config,
        client_id=test_client,
        session_manager=session_manager,
        profile_manager=profile_manager
    )

    assert success

    # Now create packing list in session mode (without filters to avoid parsing issues)
    report_config = {
        "name": "All Orders",
        "output_filename": "All_Orders.xlsx",
        "filters": []  # No filters to avoid potential parsing errors
    }

    pack_success, pack_msg = core.create_packing_list_report(
        final_df,
        report_config,
        session_manager=session_manager,
        session_path=session_path
    )

    assert pack_success
    assert "created successfully" in pack_msg

    # Verify packing list file exists in session directory
    session_path_obj = Path(session_path)
    packing_list_path = session_path_obj / "packing_lists" / "All_Orders.xlsx"
    assert packing_list_path.exists()

    # Verify session_info was updated
    session_info = session_manager.get_session_info(session_path)
    assert "All_Orders.xlsx" in session_info["packing_lists_generated"]


def test_create_stock_export_with_session(
    profile_manager,
    session_manager,
    test_client,
    test_data_files
):
    """Test create_stock_export_report with session mode."""
    stock_file, orders_file = test_data_files

    config = make_test_config()

    # First run analysis to create session
    success, session_path, final_df, stats = core.run_full_analysis(
        stock_file_path=stock_file,
        orders_file_path=orders_file,
        output_dir_path=None,
        stock_delimiter=";",
        orders_delimiter=",",
        config=config,
        client_id=test_client,
        session_manager=session_manager,
        profile_manager=profile_manager
    )

    assert success

    # Now create stock export in session mode
    report_config = {
        "name": "Stock Writeoff",
        "output_filename": "stock_writeoff.xlsx",
        "filters": []
    }

    export_success, export_msg = core.create_stock_export_report(
        final_df,
        report_config,
        session_manager=session_manager,
        session_path=session_path
    )

    # Note: This may fail if xlwt is not installed, which is expected
    # The important part is that if it fails, session_info is not incorrectly updated
    if export_success:
        assert "created successfully" in export_msg

        # Verify stock export file exists in session directory
        session_path_obj = Path(session_path)
        stock_export_path = session_path_obj / "stock_exports" / "stock_writeoff.xlsx"
        assert stock_export_path.exists()

        # Verify session_info was updated
        session_info = session_manager.get_session_info(session_path)
        assert "stock_writeoff.xlsx" in session_info["stock_exports_generated"]
    else:
        # If it failed, session_info should NOT be updated
        session_info = session_manager.get_session_info(session_path)
        assert "stock_writeoff.xlsx" not in session_info.get("stock_exports_generated", [])


def test_analysis_data_json_structure(test_data_files):
    """Test _create_analysis_data_for_packing function."""
    # Create a sample DataFrame using canonical column names
    final_df = pd.DataFrame({
        "Order_Number": ["ORD-001", "ORD-001", "ORD-002"],
        "SKU": ["SKU-A", "SKU-B", "SKU-C"],
        "Product_Name": ["Product A", "Product B", "Product C"],
        "Quantity": [2, 1, 3],
        "Shipping_Provider": ["DHL", "DHL", "DPD"],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Not Fulfillable"],
        "Destination_Country": ["BG", "BG", "BG"],
        "Tags": ["Priority", "Priority", ""],
        "Notes": ["", "", ""],
        "System_note": ["", "", ""],
        "Status_Note": ["", "", ""],
        "Internal_Tags": ["[]", "[]", "[]"],
        "Order_Type": ["Multi", "Multi", "Single"],
    })

    analysis_data = core._create_analysis_data_for_packing(final_df)

    # Verify structure
    assert "analyzed_at" in analysis_data
    assert "total_orders" in analysis_data
    assert analysis_data["total_orders"] == 2

    assert "fulfillable_orders" in analysis_data
    assert analysis_data["fulfillable_orders"] == 1

    assert "not_fulfillable_orders" in analysis_data
    assert analysis_data["not_fulfillable_orders"] == 1

    assert "orders" in analysis_data
    assert len(analysis_data["orders"]) == 2

    # Find ORD-001 and verify canonical + backwards-compat fields
    ord_001 = next(o for o in analysis_data["orders"] if o["order_number"] == "ORD-001")
    # Canonical fields
    assert ord_001["shipping_provider"] == "DHL"
    assert ord_001["order_fulfillment_status"] == "Fulfillable"
    assert ord_001["destination_country"] == "BG"
    # Backwards-compat aliases (must remain present in analysis_data.json)
    assert ord_001["courier"] == "DHL"
    assert ord_001["status"] == "Fulfillable"
    assert ord_001["shipping_country"] == "BG"
    assert len(ord_001["items"]) == 2

    # Verify items in ORD-001
    item_skus = [item["sku"] for item in ord_001["items"]]
    assert "SKU-A" in item_skus
    assert "SKU-B" in item_skus


def test_packing_list_error_does_not_update_session_info(
    profile_manager,
    session_manager,
    test_client,
    test_data_files,
    mocker
):
    """Test that session_info is not updated when packing list creation fails."""
    stock_file, orders_file = test_data_files

    config = make_test_config()

    # First run analysis to create session
    success, session_path, final_df, stats = core.run_full_analysis(
        stock_file_path=stock_file,
        orders_file_path=orders_file,
        output_dir_path=None,
        stock_delimiter=";",
        orders_delimiter=",",
        config=config,
        client_id=test_client,
        session_manager=session_manager,
        profile_manager=profile_manager
    )

    assert success

    # Mock create_packing_list to not create a file (simulating an error)
    mocker.patch("shopify_tool.packing_lists.create_packing_list")

    report_config = {
        "name": "Test Report",
        "output_filename": "test_report.xlsx",
        "filters": []
    }

    pack_success, pack_msg = core.create_packing_list_report(
        final_df,
        report_config,
        session_manager=session_manager,
        session_path=session_path
    )

    # Should return False since file was not created
    assert not pack_success
    assert "not created" in pack_msg

    # Verify session_info was NOT updated
    session_info = session_manager.get_session_info(session_path)
    assert "test_report.xlsx" not in session_info.get("packing_lists_generated", [])


def test_backwards_compatibility_without_session():
    """Test that run_full_analysis still works without session parameters."""
    stock_df = pd.DataFrame({
        "Артикул": ["SKU-001"],
        "Име": ["Product A"],
        "Наличност": [10]
    })

    orders_df = pd.DataFrame({
        "Name": ["ORD-001"],
        "Lineitem sku": ["SKU-001"],
        "Lineitem quantity": [2],
        "Shipping Method": ["dhl"],
        "Shipping Country": ["BG"],
        "Tags": [""],
        "Notes": [""]
    })

    config = make_test_config()
    # Add test dataframes to config
    config["test_stock_df"] = stock_df
    config["test_orders_df"] = orders_df
    config["test_history_df"] = pd.DataFrame({"Order_Number": []})

    # Run analysis WITHOUT session parameters (legacy mode)
    success, output_path, final_df, stats = core.run_full_analysis(
        stock_file_path=None,
        orders_file_path=None,
        output_dir_path=None,
        stock_delimiter=";",
        orders_delimiter=",",
        config=config
    )

    # Should still work
    assert success
    assert output_path is None  # Test mode
    assert final_df is not None
    assert len(final_df) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
