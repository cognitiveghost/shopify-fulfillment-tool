"""Barcode content accuracy (priority: barcode generation accuracy).

generate_barcode_label() itself renders a PNG image (not asserted pixel-by-pixel
here); what's tested is the text/data that ends up ON the label -- the part
that must be byte-accurate: the Code-128 payload and the info-panel fields.
"""
import pandas as pd
import pytest
from barcode.codex import Code128
from PIL import Image, ImageDraw

from shopify_tool.barcode_processor import (
    InvalidOrderNumberError,
    _clamp_text_to_width,
    format_tags_for_barcode,
    generate_barcode_label,
    generate_barcodes_batch,
    load_font,
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

    def test_native_list_input_is_joined_not_stringified(self):
        # Internal_Tags is sometimes a native Python list rather than its
        # serialized JSON string (see tag_manager.parse_tags -- "Check list
        # first"). The formatter must handle that directly.
        assert format_tags_for_barcode(["BAG", "TEST"]) == "BAG|TEST"

    def test_python_repr_style_list_string_is_parsed_not_leaked_raw(self):
        # Reproduces the reported bug: a caller stringified a Python list
        # (str(["BAG", "TEST"])) instead of JSON-serializing it, producing a
        # single-quoted, non-JSON string that used to leak straight through
        # as a raw list literal onto the printed label.
        assert format_tags_for_barcode(str(["BAG", "TEST"])) == "BAG|TEST"

    def test_native_list_with_blank_element_has_no_stray_pipe(self):
        # A whitespace-only element used to survive the truthiness filter
        # (checked before stripping), then strip to "" and still get joined,
        # producing a leading "|A" instead of "A".
        assert format_tags_for_barcode([" ", "A"]) == "A"

    def test_padded_json_array_string_is_parsed_not_leaked_raw(self):
        # Surrounding whitespace used to make the '['/']' bounds check fail,
        # falling through to the plain-string path and leaking the bracketed
        # literal onto the label instead of parsing it.
        assert format_tags_for_barcode(' ["A"] ') == "A"


class TestClampTextToWidth:
    """Regression for tag text drawing straight into the barcode section
    ("getting into barcode territory"): the TAG line-wrapping loop only
    checked combined-line width, never a single tag/line on its own, so one
    oversized element (a long tag name, or a raw literal leaked by the bug
    above) drew unclamped past the info column boundary."""

    def _draw(self):
        return ImageDraw.Draw(Image.new('RGB', (10, 10)))

    def test_short_text_passes_through_unchanged(self):
        draw = self._draw()
        font = load_font(18, bold=True)
        assert _clamp_text_to_width(draw, "TAG", font, 123) == "TAG"

    def test_oversized_single_line_is_truncated_to_fit(self):
        draw = self._draw()
        font = load_font(18, bold=True)
        long_text = "MASK+BOX_ORDER, REGULAR_BOX, EXTRA_LONG_TAG_NAME"
        clamped = _clamp_text_to_width(draw, long_text, font, 123)
        width = draw.textbbox((0, 0), clamped, font=font)[2]
        assert width <= 123
        assert clamped != long_text


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
