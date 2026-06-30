"""Tests for SKU writeoff functionality."""

import pytest
import pandas as pd
import os
from shopify_tool.sku_writeoff import (
    calculate_writeoff_quantities,
    apply_writeoff_to_stock_export,
    generate_writeoff_report,
    _extract_writeoff_mappings
)


@pytest.fixture
def tag_categories_with_writeoff():
    """V2 format with writeoff mappings enabled."""
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Packaging",
                "color": "#4CAF50",
                "order": 1,
                "tags": ["BOX", "LARGE_BAG", "SMALL_BAG"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {
                        "BOX": [
                            {"sku": "PKG-BOX-SMALL", "quantity": 1.0}
                        ],
                        "LARGE_BAG": [
                            {"sku": "PKG-BAG-L", "quantity": 1.0},
                            {"sku": "PKG-SEAL", "quantity": 1.0}
                        ]
                    }
                }
            },
            "priority": {
                "label": "Priority",
                "color": "#FF9800",
                "order": 2,
                "tags": ["URGENT"],
                "sku_writeoff": {
                    "enabled": False,  # Disabled - should be ignored
                    "mappings": {
                        "URGENT": [{"sku": "PRIORITY-FLAG", "quantity": 1.0}]
                    }
                }
            }
        }
    }


@pytest.fixture
def tag_categories_v1_format():
    """V1 format (legacy) - should still work via normalization."""
    return {
        "packaging": {
            "label": "Packaging",
            "color": "#4CAF50",
            "tags": ["BOX", "BAG"],
            "sku_writeoff": {
                "enabled": True,
                "mappings": {
                    "BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]
                }
            }
        }
    }


@pytest.fixture
def analysis_df_with_tags():
    """Sample analysis DataFrame with Internal_Tags."""
    return pd.DataFrame({
        "Order_Number": [1, 2, 3, 4],
        "SKU": ["PROD-A", "PROD-B", "PROD-C", "PROD-D"],
        "Quantity": [2, 1, 3, 1],
        "Internal_Tags": [
            '["BOX"]',
            '["BOX", "URGENT"]',
            '["LARGE_BAG"]',
            '[]'
        ]
    })


@pytest.fixture
def analysis_df_no_order_number():
    """DataFrame without Order_Number column."""
    return pd.DataFrame({
        "SKU": ["PROD-A", "PROD-B"],
        "Internal_Tags": ['["BOX"]', '["BOX"]']
    })


# Tests for calculate_writeoff_quantities()


def test_calculate_writeoff_basic(analysis_df_with_tags, tag_categories_with_writeoff):
    """Test basic writeoff calculation."""
    result = calculate_writeoff_quantities(analysis_df_with_tags, tag_categories_with_writeoff)

    assert not result.empty
    assert "SKU" in result.columns
    assert "Writeoff_Quantity" in result.columns
    assert "Tags_Applied" in result.columns
    assert "Order_Count" in result.columns

    # 2 BOX tags (orders 1 and 2) -> 2x PKG-BOX-SMALL
    box_row = result[result["SKU"] == "PKG-BOX-SMALL"]
    assert len(box_row) == 1
    assert box_row.iloc[0]["Writeoff_Quantity"] == 2.0
    assert box_row.iloc[0]["Tags_Applied"] == ["BOX"]
    assert box_row.iloc[0]["Order_Count"] == 2

    # 1 LARGE_BAG tag (order 3) -> 1x PKG-BAG-L + 1x PKG-SEAL
    bag_row = result[result["SKU"] == "PKG-BAG-L"]
    assert len(bag_row) == 1
    assert bag_row.iloc[0]["Writeoff_Quantity"] == 1.0
    assert bag_row.iloc[0]["Tags_Applied"] == ["LARGE_BAG"]
    assert bag_row.iloc[0]["Order_Count"] == 1

    seal_row = result[result["SKU"] == "PKG-SEAL"]
    assert len(seal_row) == 1
    assert seal_row.iloc[0]["Writeoff_Quantity"] == 1.0


def test_calculate_writeoff_empty_df(tag_categories_with_writeoff):
    """Test with empty DataFrame."""
    empty_df = pd.DataFrame(columns=["Order_Number", "Internal_Tags"])
    result = calculate_writeoff_quantities(empty_df, tag_categories_with_writeoff)

    assert result.empty
    assert list(result.columns) == ["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"]


def test_calculate_writeoff_missing_column(tag_categories_with_writeoff):
    """Test with DataFrame missing Internal_Tags column."""
    df = pd.DataFrame({
        "Order_Number": [1, 2],
        "SKU": ["PROD-A", "PROD-B"]
    })
    result = calculate_writeoff_quantities(df, tag_categories_with_writeoff)

    assert result.empty
    assert list(result.columns) == ["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"]


def test_calculate_writeoff_no_mappings():
    """Test with config that has no enabled writeoffs."""
    df = pd.DataFrame({
        "Order_Number": [1],
        "Internal_Tags": ['["SOME_TAG"]']
    })

    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["SOME_TAG"],
                "sku_writeoff": {"enabled": False, "mappings": {}}
            }
        }
    }

    result = calculate_writeoff_quantities(df, config)
    assert result.empty


def test_calculate_writeoff_no_matching_tags(tag_categories_with_writeoff):
    """Test when tags don't match any mappings."""
    df = pd.DataFrame({
        "Order_Number": [1, 2],
        "Internal_Tags": ['["UNKNOWN_TAG"]', '["ANOTHER_UNKNOWN"]']
    })

    result = calculate_writeoff_quantities(df, tag_categories_with_writeoff)
    assert result.empty


def test_calculate_writeoff_v1_format(tag_categories_v1_format):
    """Test with v1 config format (backward compatibility)."""
    df = pd.DataFrame({
        "Order_Number": [1, 2],
        "Internal_Tags": ['["BOX"]', '["BOX"]']
    })

    result = calculate_writeoff_quantities(df, tag_categories_v1_format)

    assert not result.empty
    box_row = result[result["SKU"] == "PKG-BOX"]
    assert len(box_row) == 1
    assert box_row.iloc[0]["Writeoff_Quantity"] == 2.0


def test_calculate_writeoff_multiple_tags_same_sku():
    """Test accumulation when multiple tags map to same SKU."""
    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["TAG1", "TAG2"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {
                        "TAG1": [{"sku": "SHARED-SKU", "quantity": 1.0}],
                        "TAG2": [{"sku": "SHARED-SKU", "quantity": 2.0}]
                    }
                }
            }
        }
    }

    df = pd.DataFrame({
        "Order_Number": [1, 2],
        "Internal_Tags": ['["TAG1"]', '["TAG2"]']
    })

    result = calculate_writeoff_quantities(df, config)

    # Should have one row with accumulated quantity
    assert len(result) == 1
    assert result.iloc[0]["SKU"] == "SHARED-SKU"
    assert result.iloc[0]["Writeoff_Quantity"] == 3.0  # 1.0 + 2.0
    assert set(result.iloc[0]["Tags_Applied"]) == {"TAG1", "TAG2"}
    assert result.iloc[0]["Order_Count"] == 2


def test_calculate_writeoff_no_order_number(analysis_df_no_order_number, tag_categories_with_writeoff):
    """Test DataFrame without Order_Number column."""
    result = calculate_writeoff_quantities(analysis_df_no_order_number, tag_categories_with_writeoff)

    assert not result.empty
    box_row = result[result["SKU"] == "PKG-BOX-SMALL"]
    assert len(box_row) == 1
    assert box_row.iloc[0]["Writeoff_Quantity"] == 2.0
    assert box_row.iloc[0]["Order_Count"] == 2  # Should count rows


def test_calculate_writeoff_fractional_quantities():
    """Test with fractional quantities."""
    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["HALF_TAG"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {
                        "HALF_TAG": [{"sku": "PARTIAL-SKU", "quantity": 0.5}]
                    }
                }
            }
        }
    }

    df = pd.DataFrame({
        "Order_Number": [1, 2, 3],
        "Internal_Tags": ['["HALF_TAG"]', '["HALF_TAG"]', '["HALF_TAG"]']
    })

    result = calculate_writeoff_quantities(df, config)

    assert len(result) == 1
    assert result.iloc[0]["Writeoff_Quantity"] == 1.5  # 0.5 * 3


def test_calculate_writeoff_disabled_category_ignored(analysis_df_with_tags, tag_categories_with_writeoff):
    """Test that disabled categories are ignored."""
    result = calculate_writeoff_quantities(analysis_df_with_tags, tag_categories_with_writeoff)

    # URGENT tag should not appear (priority category is disabled)
    urgent_skus = result[result["Tags_Applied"].apply(lambda tags: "URGENT" in tags)]
    assert len(urgent_skus) == 0

    # Should not have PRIORITY-FLAG SKU
    priority_rows = result[result["SKU"] == "PRIORITY-FLAG"]
    assert len(priority_rows) == 0


# Tests for apply_writeoff_to_stock_export()


def test_apply_writeoff_basic():
    """Test basic writeoff application to stock."""
    stock_df = pd.DataFrame({
        "Артикул": ["PKG-BOX-SMALL", "PKG-BAG-L", "OTHER-SKU"],
        "Наличност": [10, 5, 20]
    })

    writeoff_df = pd.DataFrame({
        "SKU": ["PKG-BOX-SMALL", "PKG-BAG-L"],
        "Writeoff_Quantity": [3.0, 2.0],
        "Tags_Applied": [["BOX"], ["LARGE_BAG"]],
        "Order_Count": [3, 2]
    })

    result = apply_writeoff_to_stock_export(stock_df, writeoff_df)

    assert "Net_Quantity" in result.columns
    assert "Original_Quantity" in result.columns
    assert "Writeoff_Quantity" in result.columns
    assert "Артикул" in result.columns

    # PKG-BOX-SMALL: 10 - 3 = 7
    box_row = result[result["Артикул"] == "PKG-BOX-SMALL"]
    assert len(box_row) == 1
    assert box_row.iloc[0]["Original_Quantity"] == 10
    assert box_row.iloc[0]["Writeoff_Quantity"] == 3.0
    assert box_row.iloc[0]["Net_Quantity"] == 7.0

    # PKG-BAG-L: 5 - 2 = 3
    bag_row = result[result["Артикул"] == "PKG-BAG-L"]
    assert len(bag_row) == 1
    assert bag_row.iloc[0]["Net_Quantity"] == 3.0

    # OTHER-SKU: no writeoff
    other_row = result[result["Артикул"] == "OTHER-SKU"]
    assert len(other_row) == 1
    assert other_row.iloc[0]["Writeoff_Quantity"] == 0.0
    assert other_row.iloc[0]["Net_Quantity"] == 20.0


def test_apply_writeoff_overage():
    """Test writeoff exceeding available stock."""
    stock_df = pd.DataFrame({
        "Артикул": ["PKG-BOX-SMALL"],
        "Наличност": [2]
    })

    writeoff_df = pd.DataFrame({
        "SKU": ["PKG-BOX-SMALL"],
        "Writeoff_Quantity": [5.0],
        "Tags_Applied": [["BOX"]],
        "Order_Count": [5]
    })

    result = apply_writeoff_to_stock_export(stock_df, writeoff_df)

    # Net should be 0, not negative
    assert result.iloc[0]["Original_Quantity"] == 2
    assert result.iloc[0]["Writeoff_Quantity"] == 5.0
    assert result.iloc[0]["Net_Quantity"] == 0.0  # Clamped at zero


def test_apply_writeoff_empty_stock_df():
    """Test with empty stock DataFrame."""
    empty_stock = pd.DataFrame(columns=["Артикул", "Наличност"])

    writeoff_df = pd.DataFrame({
        "SKU": ["PKG-BOX"],
        "Writeoff_Quantity": [1.0],
        "Tags_Applied": [["BOX"]],
        "Order_Count": [1]
    })

    result = apply_writeoff_to_stock_export(empty_stock, writeoff_df)

    # Should return empty DataFrame with correct column structure
    assert result.empty
    assert "Original_Quantity" in result.columns
    assert "Writeoff_Quantity" in result.columns
    assert "Net_Quantity" in result.columns
    assert "Артикул" in result.columns


def test_apply_writeoff_empty_writeoff_df():
    """Test with empty writeoff DataFrame."""
    stock_df = pd.DataFrame({
        "Артикул": ["PKG-BOX", "PKG-BAG"],
        "Наличност": [10, 5]
    })

    empty_writeoff = pd.DataFrame(columns=["SKU", "Writeoff_Quantity", "Tags_Applied", "Order_Count"])

    result = apply_writeoff_to_stock_export(stock_df, empty_writeoff)

    # All writeoffs should be 0, net = original
    assert all(result["Writeoff_Quantity"] == 0.0)
    assert all(result["Net_Quantity"] == result["Original_Quantity"])


def test_apply_writeoff_partial_overlap():
    """Test when only some SKUs have writeoffs."""
    stock_df = pd.DataFrame({
        "Артикул": ["SKU-A", "SKU-B", "SKU-C"],
        "Наличност": [10, 10, 10]
    })

    writeoff_df = pd.DataFrame({
        "SKU": ["SKU-B"],
        "Writeoff_Quantity": [3.0],
        "Tags_Applied": [["TAG1"]],
        "Order_Count": [3]
    })

    result = apply_writeoff_to_stock_export(stock_df, writeoff_df)

    # SKU-A: no writeoff
    sku_a = result[result["Артикул"] == "SKU-A"]
    assert sku_a.iloc[0]["Writeoff_Quantity"] == 0.0
    assert sku_a.iloc[0]["Net_Quantity"] == 10.0

    # SKU-B: has writeoff
    sku_b = result[result["Артикул"] == "SKU-B"]
    assert sku_b.iloc[0]["Writeoff_Quantity"] == 3.0
    assert sku_b.iloc[0]["Net_Quantity"] == 7.0

    # SKU-C: no writeoff
    sku_c = result[result["Артикул"] == "SKU-C"]
    assert sku_c.iloc[0]["Writeoff_Quantity"] == 0.0


# Tests for generate_writeoff_report()


def test_generate_writeoff_report_basic(tmp_path, analysis_df_with_tags, tag_categories_with_writeoff):
    """Test report generation."""
    output_file = tmp_path / "writeoff_test.xls"

    generate_writeoff_report(
        analysis_df_with_tags,
        tag_categories_with_writeoff,
        str(output_file)
    )

    assert output_file.exists()

    # Read back and verify structure (simple format like stock export)
    import xlrd
    workbook = xlrd.open_workbook(str(output_file))

    assert "Sheet1" in workbook.sheet_names()

    # Verify sheet has data: header + 3 SKUs
    sheet = workbook.sheet_by_name("Sheet1")
    assert sheet.nrows >= 4  # Header + 3 SKUs

    # Verify canonical ERP layout: Артикул | blank | Мярка | Брой | Годност | Партида
    assert sheet.cell_value(0, 0) == "Артикул"
    assert sheet.cell_value(0, 1) == ""
    assert sheet.cell_value(0, 2) == "Мярка"
    assert sheet.cell_value(0, 3) == "Брой"
    assert sheet.cell_value(0, 4) == "Годност"
    assert sheet.cell_value(0, 5) == "Партида"


def test_generate_writeoff_report_empty_mappings(tmp_path):
    """Test report generation when no writeoffs triggered."""
    df = pd.DataFrame({
        "Order_Number": [1, 2],
        "Internal_Tags": ['["UNKNOWN"]', '[]']
    })

    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["TAG1"],
                "sku_writeoff": {"enabled": False, "mappings": {}}
            }
        }
    }

    output_file = tmp_path / "empty_writeoff.xls"

    generate_writeoff_report(df, config, str(output_file))

    assert output_file.exists()

    # Should create empty report with correct structure
    import xlrd
    workbook = xlrd.open_workbook(str(output_file))
    assert "Sheet1" in workbook.sheet_names()

    # Should have header but no data rows
    sheet = workbook.sheet_by_name("Sheet1")
    assert sheet.nrows == 1  # Only header
    assert sheet.cell_value(0, 0) == "Артикул"
    assert sheet.cell_value(0, 3) == "Брой"


def test_generate_writeoff_report_summary_stats(tmp_path, analysis_df_with_tags, tag_categories_with_writeoff):
    """Test that writeoff quantities are correct."""
    output_file = tmp_path / "stats_test.xls"

    generate_writeoff_report(
        analysis_df_with_tags,
        tag_categories_with_writeoff,
        str(output_file)
    )

    # Read report (canonical ERP layout)
    report_df = pd.read_excel(str(output_file), sheet_name="Sheet1")

    assert "Артикул" in report_df.columns
    assert "Брой" in report_df.columns

    # Should have 3 SKUs
    assert len(report_df) == 3  # PKG-BOX-SMALL, PKG-BAG-L, PKG-SEAL

    # Verify total quantity
    total_quantity = report_df["Брой"].sum()
    assert total_quantity == 4  # 2 + 1 + 1 from analysis_df_with_tags


# Tests for _extract_writeoff_mappings()


def test_extract_writeoff_mappings_basic(tag_categories_with_writeoff):
    """Test basic mapping extraction."""
    mappings = _extract_writeoff_mappings(tag_categories_with_writeoff)

    assert "BOX" in mappings
    assert len(mappings["BOX"]) == 1
    assert mappings["BOX"][0]["sku"] == "PKG-BOX-SMALL"
    assert mappings["BOX"][0]["quantity"] == 1.0

    assert "LARGE_BAG" in mappings
    assert len(mappings["LARGE_BAG"]) == 2

    # URGENT should not be in mappings (disabled category)
    assert "URGENT" not in mappings


def test_extract_writeoff_mappings_disabled_categories():
    """Test that disabled categories are excluded."""
    config = {
        "version": 2,
        "categories": {
            "cat1": {
                "tags": ["TAG1"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {"TAG1": [{"sku": "SKU1", "quantity": 1.0}]}
                }
            },
            "cat2": {
                "tags": ["TAG2"],
                "sku_writeoff": {
                    "enabled": False,  # Disabled
                    "mappings": {"TAG2": [{"sku": "SKU2", "quantity": 1.0}]}
                }
            }
        }
    }

    mappings = _extract_writeoff_mappings(config)

    assert "TAG1" in mappings
    assert "TAG2" not in mappings


def test_extract_writeoff_mappings_invalid_data():
    """Test handling of invalid mapping data."""
    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["TAG1", "TAG2", "TAG3", "TAG4"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {
                        "TAG1": [{"sku": "SKU1", "quantity": 1.0}],  # Valid
                        "TAG2": "not a list",  # Invalid: not a list
                        "TAG3": [{"sku": "SKU3"}],  # Invalid: missing quantity
                        "TAG4": [{"sku": "SKU4", "quantity": -1.0}]  # Invalid: negative quantity
                    }
                }
            }
        }
    }

    mappings = _extract_writeoff_mappings(config)

    # Only TAG1 should be valid
    assert "TAG1" in mappings
    assert "TAG2" not in mappings
    assert "TAG3" not in mappings
    assert "TAG4" not in mappings


def test_extract_writeoff_mappings_no_enabled():
    """Test when no categories have writeoff enabled."""
    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["TAG1"],
                "sku_writeoff": {"enabled": False, "mappings": {}}
            }
        }
    }

    mappings = _extract_writeoff_mappings(config)

    assert len(mappings) == 0


def test_extract_writeoff_mappings_v1_format(tag_categories_v1_format):
    """Test extraction with v1 format."""
    mappings = _extract_writeoff_mappings(tag_categories_v1_format)

    assert "BOX" in mappings
    assert mappings["BOX"][0]["sku"] == "PKG-BOX"


def test_extract_writeoff_mappings_quantity_conversion():
    """Test that quantities are converted to float."""
    config = {
        "version": 2,
        "categories": {
            "test": {
                "tags": ["TAG1"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {
                        "TAG1": [
                            {"sku": "SKU1", "quantity": 1},  # Int should convert
                            {"sku": "SKU2", "quantity": "2.5"}  # String should convert
                        ]
                    }
                }
            }
        }
    }

    mappings = _extract_writeoff_mappings(config)

    assert len(mappings["TAG1"]) == 2
    assert isinstance(mappings["TAG1"][0]["quantity"], float)
    assert mappings["TAG1"][0]["quantity"] == 1.0
    assert isinstance(mappings["TAG1"][1]["quantity"], float)
    assert mappings["TAG1"][1]["quantity"] == 2.5
