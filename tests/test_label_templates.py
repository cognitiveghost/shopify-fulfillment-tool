"""Regression tests for the label template markup itself (not just that
blabel/WeasyPrint can render it without raising) -- guards against
re-introducing the TAG field's cramped 14mm x 10mm column box, which could
overflow the physical 68mm x 38mm label once an order carried enough tags
to need more than a line or two (reported against PR #259)."""
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "shopify_tool" / "templates"


class TestBarcodeLabelLayout:
    def test_tag_field_is_full_width_row_not_cramped_column_box(self):
        html = (_TEMPLATES_DIR / "barcode_label" / "template.html").read_text()
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "tag-row" in html
        assert "tag-row" in css

    def test_tag_value_box_has_hard_overflow_guard(self):
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "overflow: hidden" in css

    def test_tag_font_fit_uses_full_width_box_not_old_14mm_column(self):
        html = (_TEMPLATES_DIR / "barcode_label" / "template.html").read_text()
        assert "box_width_mm=14" not in html
        assert "fit_font_block" in html

    def test_courier_and_info_column_have_min_width_guard(self):
        """Regression guard: a long courier name previously pushed .info (and the
        barcode/order-number next to it) off the printable page edge, because
        WeasyPrint's flexbox gives nested flex items an implicit min-width:auto
        that ignores white-space:nowrap/overflow:hidden unless overridden."""
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "min-width: 0" in css


class TestQrLabelLayout:
    def test_mirrors_barcode_label_info_column_and_tag_row(self):
        html = (_TEMPLATES_DIR / "qr_label" / "template.html").read_text()
        css = (_TEMPLATES_DIR / "qr_label" / "style.css").read_text()
        for marker in ("sequential_num", "courier", "date_str", "tag-row"):
            assert marker in html
        assert "overflow: hidden" in css

    def test_qr_code_encodes_order_number_not_multiline_payload(self):
        html = (_TEMPLATES_DIR / "qr_label" / "template.html").read_text()
        assert "label_tools.qr_code(order_number)" in html
