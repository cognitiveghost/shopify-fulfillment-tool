"""
Unit tests for barcode processor module.

Tests cover:
- Sequential number generation
- Barcode image creation with complex layout
- PDF generation from PNG files
- Tag formatting
- Error handling for invalid inputs
"""

import pytest
from pathlib import Path
from PIL import Image
import json

from shopify_tool.barcode_processor import (
    generate_barcode_label,
    generate_barcodes_batch,
    generate_barcodes_pdf,
    format_tags_for_barcode,
    sanitize_order_number,
    LABEL_WIDTH_MM,
    LABEL_HEIGHT_MM,
    InvalidOrderNumberError
)


@pytest.fixture
def output_dir(tmp_path):
    """Create temporary output directory for test barcodes."""
    barcodes = tmp_path / "barcodes"
    barcodes.mkdir()
    return barcodes


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "Order_Number": "ORDER-001234",
        "Shipping_Provider": "DHL",
        "Destination_Country": "DE",
        "Internal_Tag": "Priority|VIP",
        "Quantity": 5
    }


class TestBarcodeGeneration:
    """Tests for individual barcode generation."""

    def test_generate_basic_label(self, output_dir, sample_order_data):
        """Test generating basic barcode label."""
        result = generate_barcode_label(
            order_number=sample_order_data["Order_Number"],
            sequential_num=12,
            courier=sample_order_data["Shipping_Provider"],
            country=sample_order_data["Destination_Country"],
            tag=sample_order_data["Internal_Tag"],
            item_count=sample_order_data["Quantity"],
            output_dir=output_dir
        )

        assert result['success'] is True
        assert result['file_path'].exists()
        assert result['sequential_num'] == 12
        assert result['courier'] == "DHL"

        # Verify image properties
        img = Image.open(result['file_path'])
        # 68mm at 203 DPI = 542px
        expected_width = int(LABEL_WIDTH_MM / 25.4 * 203)
        # 38mm at 203 DPI = 303px
        expected_height = int(LABEL_HEIGHT_MM / 25.4 * 203)

        assert img.width == expected_width
        assert img.height == expected_height

    def test_generate_label_no_country(self, output_dir):
        """Test generating label without country code."""
        result = generate_barcode_label(
            order_number="ORDER-999",
            sequential_num=1,
            courier="PostOne",
            country="",  # Empty country
            tag="",
            item_count=1,
            output_dir=output_dir
        )

        assert result['success'] is True
        assert result['country'] == "N/A"

    def test_generate_label_no_tag(self, output_dir):
        """Test generating label without internal tag."""
        result = generate_barcode_label(
            order_number="ORDER-888",
            sequential_num=2,
            courier="DPD",
            country="BG",
            tag="",  # Empty tag
            item_count=3,
            output_dir=output_dir
        )

        assert result['success'] is True
        assert result['tag'] == "N/A"

    def test_generate_label_invalid_order_number(self, output_dir):
        """Test handling invalid order number."""
        # Empty order number should fail gracefully
        result = generate_barcode_label(
            order_number="",
            sequential_num=1,
            courier="DHL",
            country="DE",
            tag="",
            item_count=1,
            output_dir=output_dir
        )

        assert result['success'] is False
        assert result['error'] is not None


class TestUtilityFunctions:
    """Tests for utility helper functions."""

    def test_sanitize_order_number_valid(self):
        """Test sanitizing valid order numbers."""
        result = sanitize_order_number("ORDER-12345")
        assert result == "ORDER-12345"

    def test_sanitize_order_number_special_chars(self):
        """Test sanitizing order number with special characters."""
        result = sanitize_order_number("ORDER#12345!")
        assert result == "ORDER#12345"

    def test_sanitize_shopify_hash_numeric(self):
        """# prefix preserved for Shopify numeric orders."""
        assert sanitize_order_number("#1029392") == "#1029392"

    def test_sanitize_shopify_hash_alphanumeric(self):
        """# prefix preserved for Shopify alphanumeric orders."""
        assert sanitize_order_number("#BG10129") == "#BG10129"

    def test_sanitize_order_number_empty(self):
        """Test sanitizing empty order number."""
        with pytest.raises(InvalidOrderNumberError):
            sanitize_order_number("")

    def test_format_single_tag(self):
        """Test formatting single tag."""
        result = format_tags_for_barcode("Priority")
        assert result == "Priority"

    def test_format_multiple_tags(self):
        """Test formatting multiple tags separated by pipe."""
        result = format_tags_for_barcode("Priority|VIP|Fragile")
        assert result == "Priority|VIP|Fragile"  # All tags kept (for multiline display)

    def test_format_empty_tag(self):
        """Test formatting empty tag."""
        result = format_tags_for_barcode("")
        assert result == ""

    def test_format_long_tag(self):
        """Test formatting very long tag (no truncation now)."""
        long_tag = "A" * 50
        result = format_tags_for_barcode(long_tag)
        assert result == long_tag  # No truncation - handled in display logic

    def test_format_json_array_tags(self):
        """Test formatting tags from JSON array format (Internal_Tags)."""
        result = format_tags_for_barcode('["GIFT+1", "GIFT+2", "GIFT+3"]')
        assert result == "GIFT+1|GIFT+2|GIFT+3"  # JSON array converted to pipe-separated


class TestBatchGeneration:
    """Tests for batch barcode generation."""

    def test_batch_generation_success(self, output_dir, tmp_path):
        """Test generating multiple barcodes in batch."""
        # Create mock DataFrame
        import pandas as pd
        df = pd.DataFrame([
            {
                "Order_Number": "ORDER-001",
                "Shipping_Provider": "DHL",
                "Destination_Country": "DE",
                "Internal_Tag": "Priority",
                "Quantity": 2
            },
            {
                "Order_Number": "ORDER-002",
                "Shipping_Provider": "PostOne",
                "Destination_Country": "BG",
                "Internal_Tag": "",
                "Quantity": 1
            },
            {
                "Order_Number": "ORDER-003",
                "Shipping_Provider": "DPD",
                "Destination_Country": "RO",
                "Internal_Tag": "VIP|Fragile",
                "Quantity": 5
            }
        ])

        # Create sequential map for testing
        sequential_map = {
            "ORDER-001": 1,
            "ORDER-002": 2,
            "ORDER-003": 3
        }

        results = generate_barcodes_batch(
            df=df,
            output_dir=output_dir,
            sequential_map=sequential_map
        )

        assert len(results) == 3
        assert all(r['success'] for r in results)

        # Check sequential numbering (from map)
        assert results[0]['sequential_num'] == 1
        assert results[1]['sequential_num'] == 2
        assert results[2]['sequential_num'] == 3

        # Check all files exist
        for r in results:
            assert r['file_path'].exists()

    def test_batch_generation_partial_failure(self, output_dir):
        """Test batch generation with some invalid orders."""
        import pandas as pd
        df = pd.DataFrame([
            {
                "Order_Number": "ORDER-GOOD",
                "Shipping_Provider": "DHL",
                "Destination_Country": "DE",
                "Internal_Tag": "",
                "Quantity": 1
            },
            {
                "Order_Number": "",  # Invalid
                "Shipping_Provider": "PostOne",
                "Destination_Country": "BG",
                "Internal_Tag": "",
                "Quantity": 1
            }
        ])

        # Create sequential map (only for valid order)
        sequential_map = {
            "ORDER-GOOD": 1
        }

        results = generate_barcodes_batch(
            df=df,
            output_dir=output_dir,
            sequential_map=sequential_map
        )

        assert len(results) == 2
        assert results[0]['success'] is True
        assert results[1]['success'] is False


class TestPDFGeneration:
    """Tests for PDF generation from barcode PNGs."""

    def test_pdf_generation_single_barcode(self, output_dir):
        """Test PDF generation with single barcode."""
        # Generate one barcode first
        result = generate_barcode_label(
            order_number="ORDER-PDF-001",
            sequential_num=1,
            courier="DHL",
            country="DE",
            tag="",
            item_count=1,
            output_dir=output_dir
        )

        barcode_files = [result['file_path']]
        pdf_path = output_dir / "test_single.pdf"

        output = generate_barcodes_pdf(
            barcode_files=barcode_files,
            output_pdf=pdf_path
        )

        assert output.exists()
        assert output.stat().st_size > 0

    def test_pdf_generation_multiple_barcodes(self, output_dir):
        """Test PDF generation with multiple barcodes."""
        # Generate 3 barcodes
        barcode_files = []
        for i in range(1, 4):
            result = generate_barcode_label(
                order_number=f"ORDER-PDF-{i:03d}",
                sequential_num=i,
                courier="DHL",
                country="DE",
                tag="",
                item_count=1,
                output_dir=output_dir
            )
            barcode_files.append(result['file_path'])

        pdf_path = output_dir / "test_multiple.pdf"

        output = generate_barcodes_pdf(
            barcode_files=barcode_files,
            output_pdf=pdf_path
        )

        assert output.exists()
        # PDF should be larger than single barcode
        assert output.stat().st_size > 5000

    def test_pdf_generation_empty_list(self, output_dir):
        """Test PDF generation with empty barcode list."""
        pdf_path = output_dir / "test_empty.pdf"

        with pytest.raises(ValueError):
            generate_barcodes_pdf(
                barcode_files=[],
                output_pdf=pdf_path
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
