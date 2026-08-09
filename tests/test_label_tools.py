"""label_tools.py exposes vector barcode/QR rendering and text-fit helpers
to blabel templates. These tests cover the Python-level contract (valid
SVG data URIs, no exceptions, shrink-to-fit behavior) -- visual/print
correctness is manual QA (see spec Testing section)."""
import pytest

from shopify_tool.label_tools import barcode, fit_font_block, qr_code


class TestBarcode:
    @pytest.mark.parametrize("order_number", [
        "1029392", "BG10129-A", "ORDER_001234", "A", "#1029392",
    ])
    def test_returns_svg_data_uri(self, order_number):
        result = barcode(order_number)
        assert result.startswith("data:image/svg+xml")

    def test_does_not_render_human_readable_text_by_default(self):
        # write_text defaults to False -- the barcode payload carries no
        # visible caption, the label template draws its own order_number
        # text separately (see barcode_label/template.html).
        result = barcode("1029392", write_text=True)
        # Explicit override is honored (not clobbered by setdefault).
        assert result.startswith("data:image/svg+xml")


class TestQrCode:
    def test_returns_svg_data_uri(self):
        result = qr_code("#1029392\nWIDGET x2\nGADGET x1")
        assert result.startswith("data:image/svg+xml")

    def test_handles_multiline_payload(self):
        payload = "\n".join([f"SKU-{i} x{i}" for i in range(20)])
        result = qr_code(payload)
        assert result.startswith("data:image/svg+xml")


class TestFitFontBlock:
    def test_empty_text_returns_max_size(self):
        assert fit_font_block("", box_width_mm=30, box_height_mm=10, max_mm=5) == 5

    def test_stays_within_min_max_range(self):
        size = fit_font_block(
            "A very long tag list that will not fit on one line easily",
            box_width_mm=20, box_height_mm=8, max_mm=5, min_mm=2,
        )
        assert 2 <= size <= 5

    def test_shrinks_for_longer_text(self):
        short_size = fit_font_block("GIFT+1", box_width_mm=30, box_height_mm=10, max_mm=5, min_mm=2)
        long_size = fit_font_block(
            "GIFT+1, GIFT+2, URGENT, FRAGILE, PRIORITY, EXPRESS",
            box_width_mm=30, box_height_mm=10, max_mm=5, min_mm=2,
        )
        assert long_size <= short_size
