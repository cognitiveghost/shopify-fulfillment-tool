import sys
import os
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shopify_tool import stock_export


@pytest.fixture
def sample_analysis_df():
    """Provides a sample DataFrame for testing."""
    return pd.DataFrame(
        {
            "Order_Fulfillment_Status": [
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Not Fulfillable",
                "Fulfillable",
            ],
            "SKU": ["SKU-A", "SKU-B", "SKU-A", "SKU-C", "SKU-D"],
            "Quantity": [5, 3, 2, 10, 0],
            "Order_Type": ["Single", "Multi", "Single", "Single", "Multi"],
        }
    )


def test_create_stock_export_success(tmp_path, sample_analysis_df):
    """Tests the successful creation and content of a stock export file."""
    output_path = tmp_path / "stock_export_out.xls"

    stock_export.create_stock_export(sample_analysis_df, str(output_path))

    assert os.path.exists(output_path)

    # Read the output and validate its content
    result_df = pd.read_excel(output_path)

    # Canonical ERP layout (blank spacer reads back as "Unnamed: 1").
    assert list(result_df.columns) == [
        "Артикул",
        "Unnamed: 1",
        "Мярка",
        "Брой",
        "Годност",
        "Партида",
    ]

    # Expected data: SKU-A: 5+2=7, SKU-B: 3. SKU-C is not fulfillable, SKU-D has 0 quantity.
    result_df = result_df.sort_values(by="Артикул").reset_index(drop=True)
    assert list(result_df["Артикул"]) == ["SKU-A", "SKU-B"]
    assert list(result_df["Брой"]) == [7, 3]
    assert set(result_df["Мярка"]) == {"брой"}


def test_create_stock_export_with_filters(tmp_path, sample_analysis_df):
    """Tests that filters are correctly applied before generating a stock export."""
    output_path = tmp_path / "output.xls"
    filters = [{"field": "Order_Type", "operator": "==", "value": "Single"}]

    stock_export.create_stock_export(
        sample_analysis_df, str(output_path), filters=filters
    )

    assert os.path.exists(output_path)
    result_df = pd.read_excel(output_path)

    # Should only contain SKU-A from single orders
    assert list(result_df["Артикул"]) == ["SKU-A"]
    assert result_df["Брой"].iloc[0] == 7
    assert result_df["Мярка"].iloc[0] == "брой"


def test_create_stock_export_empty_after_filter(tmp_path, sample_analysis_df):
    """Tests that an empty file with headers is created if filtering results in an empty dataset."""
    output_path = tmp_path / "output.xls"
    filters = [{"field": "Order_Type", "operator": "==", "value": "NonExistent"}]

    stock_export.create_stock_export(
        sample_analysis_df, str(output_path), filters=filters
    )

    assert os.path.exists(output_path)
    result_df = pd.read_excel(output_path)
    assert result_df.empty
    assert list(result_df.columns) == [
        "Артикул",
        "Unnamed: 1",
        "Мярка",
        "Брой",
        "Годност",
        "Партида",
    ]


def test_create_stock_export_no_fulfillable_items(tmp_path):
    """Tests that an empty file is created when no items are fulfillable."""
    df = pd.DataFrame(
        {
            "Order_Fulfillment_Status": ["Not Fulfillable"],
            "SKU": ["S1"],
            "Quantity": [1],
        }
    )
    output_path = tmp_path / "output.xls"

    stock_export.create_stock_export(df, str(output_path))

    assert os.path.exists(output_path)
    result_df = pd.read_excel(output_path)
    assert result_df.empty
    assert list(result_df.columns) == [
        "Артикул",
        "Unnamed: 1",
        "Мярка",
        "Брой",
        "Годност",
        "Партида",
    ]


def test_create_stock_export_skips_invalid_filter(tmp_path, sample_analysis_df, caplog):
    """Tests that an invalid filter object is skipped without crashing."""
    output_path = tmp_path / "output.xls"
    # This filter is missing the 'value' key
    filters = [{"field": "Order_Type", "operator": "=="}]

    stock_export.create_stock_export(
        sample_analysis_df, str(output_path), filters=filters
    )

    assert "Skipping invalid filter" in caplog.text
    # The report should be created as if there were no filters
    assert os.path.exists(output_path)
    result_df = pd.read_excel(output_path)
    assert len(result_df) == 2  # SKU-A and SKU-B
