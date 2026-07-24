"""Barcode content accuracy (priority: barcode generation accuracy).

generate_barcode_label() itself renders a PNG image (not asserted pixel-by-pixel
here); what's tested is the text/data that ends up ON the label -- the part
that must be byte-accurate: the Code-128 payload and the info-panel fields.
"""
import pandas as pd
import pytest
from barcode.codex import Code128

from shopify_tool.barcode_processor import (
    InvalidOrderNumberError,
    format_tags_for_barcode,
    generate_barcode_label,
    generate_barcodes_batch,
    sanitize_order_number,
)


class TestSanitizeOrderNumber:
    @pytest.mark.parametrize("raw, expected", [
        ("#1029392", "#1029392"),
        ("BG-10129", "BG-10129"),
        ("ORDER_001", "ORDER_001"),
        ("#12 34", "#1234"),      # internal space stripped
        ("Ord#5!", "Ord#5"),      # punctuation stripped
    ])
    def test_preserves_shopify_safe_characters(self, raw, expected):
        assert sanitize_order_number(raw) == expected

    def test_empty_raises(self):
        with pytest.raises(InvalidOrderNumberError):
            sanitize_order_number("")

    def test_all_symbols_raises(self):
        with pytest.raises(InvalidOrderNumberError):
            sanitize_order_number("!!!***")


class TestSanitizedNumberEncodesFaithfullyInCode128:
    """The whole point of sanitize_order_number is that what gets barcode-encoded
    is EXACTLY what the packer will read back -- verify via python-barcode's own
    get_fullcode(), which is the actual payload the scanner will decode."""

    @pytest.mark.parametrize("raw", ["#1029392", "BG-10129", "ORDER_001", "12345"])
    def test_fullcode_matches_sanitized_input_exactly(self, raw):
        safe = sanitize_order_number(raw)
        assert Code128(safe).get_fullcode() == safe


class TestFormatTagsForBarcode:
    def test_json_array_joined_with_pipe(self):
        assert format_tags_for_barcode('["GIFT+1", "GIFT+2"]') == "GIFT+1|GIFT+2"

    def test_plain_string_passthrough(self):
        assert format_tags_for_barcode("Priority") == "Priority"

    def test_empty_and_sentinel_values_return_blank(self):
        assert format_tags_for_barcode("") == ""
        assert format_tags_for_barcode("nan") == ""
        assert format_tags_for_barcode("None") == ""

    def test_empty_json_array_returns_blank_not_literal_brackets(self):
        assert format_tags_for_barcode("[]") == ""


class TestItemCountZeroFalsyBug:
    def test_zero_item_count_is_not_coerced_to_one(self, tmp_path, monkeypatch):
        captured = {}

        def fake_generate_barcode_label(*, item_count, **kwargs):
            captured["item_count"] = item_count
            return {"success": True, "error": None}

        monkeypatch.setattr(
            "shopify_tool.barcode_processor.generate_barcode_label",
            fake_generate_barcode_label,
        )
        df = pd.DataFrame([{
            "Order_Number": "#1", "Shipping_Provider": "DHL",
            "Destination_Country": "DE", "Internal_Tags": "[]", "item_count": 0,
        }])
        generate_barcodes_batch(df, tmp_path)
        assert captured["item_count"] == 0


class TestGenerateBarcodeLabelIntegration:
    """Smoke test the real PNG generation path (no image-content assertions,
    just: does it run, and does the returned metadata match input)."""

    def test_generates_png_and_reports_success(self, tmp_path):
        result = generate_barcode_label(
            order_number="#1029392",
            sequential_num=7,
            courier="DHL",
            country="DE",
            tag="",
            item_count=3,
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["file_path"].exists()
        assert result["sequential_num"] == 7
        assert result["item_count"] == 3

    def test_invalid_order_number_reports_failure_not_exception(self, tmp_path):
        result = generate_barcode_label(
            order_number="!!!",
            sequential_num=1,
            courier="DHL",
            country="DE",
            tag="",
            item_count=1,
            output_dir=tmp_path,
        )
        assert result["success"] is False
        assert result["file_path"] is None
