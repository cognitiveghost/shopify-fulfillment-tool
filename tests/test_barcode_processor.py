"""Barcode content accuracy (priority: barcode generation accuracy).

generate_code128_labels_pdf()/generate_qr_labels_pdf() render real PDFs via
blabel/WeasyPrint (not asserted pixel-by-pixel here); what's tested is the
data that ends up ON the label -- the Code-128 payload, and that the batch
builder produces correctly-shaped, correctly-validated records.
"""
import pandas as pd
import pypdf
import pytest
from barcode.codex import Code128

from shopify_tool import label_tools
from shopify_tool.barcode_processor import (
    InvalidOrderNumberError,
    format_tags_for_barcode,
    generate_barcodes_batch,
    generate_code128_labels_pdf,
    generate_qr_labels_pdf,
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
        assert format_tags_for_barcode(["BAG", "TEST"]) == "BAG|TEST"

    def test_python_repr_style_list_string_is_parsed_not_leaked_raw(self):
        assert format_tags_for_barcode(str(["BAG", "TEST"])) == "BAG|TEST"

    def test_native_list_with_blank_element_has_no_stray_pipe(self):
        assert format_tags_for_barcode([" ", "A"]) == "A"

    def test_padded_json_array_string_is_parsed_not_leaked_raw(self):
        assert format_tags_for_barcode(' ["A"] ') == "A"


class TestGenerateBarcodesBatch:
    """generate_barcodes_batch() now only builds/validates records -- no
    rendering, no output_dir. Rendering is generate_code128_labels_pdf()."""

    def _df(self, **overrides):
        row = {
            "Order_Number": "#1029392", "Shipping_Provider": "DHL",
            "Destination_Country": "DE", "Internal_Tags": "[]", "item_count": 3,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_zero_item_count_is_not_coerced_to_one(self):
        results = generate_barcodes_batch(self._df(item_count=0))
        assert results[0]["item_count"] == 0

    def test_successful_row_has_safe_order_number(self):
        results = generate_barcodes_batch(self._df(Order_Number="#1029392!!"))
        assert results[0]["success"] is True
        assert results[0]["safe_order_number"] == "#1029392"

    def test_invalid_order_number_reports_failure_not_exception(self):
        results = generate_barcodes_batch(self._df(Order_Number="!!!"))
        assert results[0]["success"] is False
        assert results[0]["safe_order_number"] is None
        assert results[0]["error"]

    @pytest.mark.parametrize("missing", [float("nan"), None, pd.NA])
    def test_missing_order_number_reports_failure_not_nan_string(self, missing):
        results = generate_barcodes_batch(self._df(Order_Number=missing))
        assert results[0]["success"] is False
        assert results[0]["safe_order_number"] is None
        assert results[0]["error"]

    def test_sequential_numbering_defaults_to_row_index_plus_one(self):
        df = pd.concat([self._df(Order_Number="#1"), self._df(Order_Number="#2")], ignore_index=True)
        results = generate_barcodes_batch(df)
        assert [r["sequential_num"] for r in results] == [1, 2]

    def test_sequential_map_overrides_default_numbering(self):
        results = generate_barcodes_batch(self._df(), sequential_map={"#1029392": 42})
        assert results[0]["sequential_num"] == 42


class TestGenerateCode128LabelsPdfIntegration:
    """Smoke test the real blabel/WeasyPrint rendering path (no pixel
    assertions -- does it run, correct page count)."""

    def _order(self, **overrides):
        order = {
            "order_number": "#1029392", "safe_order_number": "#1029392",
            "sequential_num": 7, "courier": "DHL", "country": "DE",
            "tag": "N/A", "item_count": 3,
        }
        order.update(overrides)
        return order

    def test_generates_pdf_with_one_page_per_order(self, tmp_path):
        output_pdf = tmp_path / "labels.pdf"
        result = generate_code128_labels_pdf(
            [self._order(safe_order_number="#1"), self._order(safe_order_number="#2")],
            output_pdf,
        )
        assert result == output_pdf
        assert output_pdf.exists()
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 2

    def test_empty_orders_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            generate_code128_labels_pdf([], tmp_path / "labels.pdf")


class TestGenerateQrLabelsPdfIntegration:
    def _order(self, **overrides):
        order = {
            "safe_order_number": "#1029392",
            "sequential_num": 7, "courier": "DHL", "country": "DE",
            "tag": "N/A", "item_count": 3,
        }
        order.update(overrides)
        return order

    def test_generates_pdf_with_one_page_per_order(self, tmp_path):
        output_pdf = tmp_path / "qr_labels.pdf"
        result = generate_qr_labels_pdf(
            [self._order(safe_order_number="#1"), self._order(safe_order_number="#2")],
            output_pdf,
        )
        assert result == output_pdf
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 2

    def test_empty_orders_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            generate_qr_labels_pdf([], tmp_path / "qr_labels.pdf")

    def test_qr_payload_is_order_number_only(self, tmp_path, monkeypatch):
        captured = {}
        original_qr_code = label_tools.qr_code

        def spy_qr_code(data, *args, **kwargs):
            captured["data"] = data
            return original_qr_code(data, *args, **kwargs)

        monkeypatch.setattr(label_tools, "qr_code", spy_qr_code)

        generate_qr_labels_pdf(
            [self._order(safe_order_number="#1029392")], tmp_path / "qr_labels.pdf"
        )

        assert captured["data"] == "#1029392"
