"""Tests for shopify_tool.pdf_processor's reference-overlay content-shrink +
barcode strip. See
docs/superpowers/specs/2026-08-10-print-polish-and-reference-barcode-design.md."""
import inspect

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from shopify_tool import pdf_processor


def _make_courier_pdf(path, width_pt=288, height_pt=432, name="Acme Warehouse Co"):
    c = canvas.Canvas(str(path), pagesize=(width_pt, height_pt))
    c.drawString(20, height_pt - 20, name)
    c.showPage()
    c.save()


class TestCreateReferenceOverlaySignature:
    def test_order_number_parameter_removed(self):
        params = list(inspect.signature(pdf_processor.create_reference_overlay).parameters)
        assert params == ["reference_number", "page_width", "page_height"]


class TestCreateReferenceOrderMapRemoved:
    def test_function_no_longer_exists(self):
        assert not hasattr(pdf_processor, "create_reference_order_map")


class TestCreateReferenceOverlayContent:
    def test_shows_ref_text_without_counter_prefix(self):
        overlay_pdf = pdf_processor.create_reference_overlay("REF-001", 288, 432)
        text = PdfReader(overlay_pdf).pages[0].extract_text()
        assert "REF: REF-001" in text
        assert "1. REF" not in text


class TestProcessReferenceLabelsShrink:
    def test_matched_page_shrinks_content_but_keeps_page_size(self, tmp_path):
        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path)

        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text(
            "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
            ",,REF-001,,,,Acme Warehouse Co\n"
        )

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = pdf_processor.process_reference_labels(str(pdf_path), str(csv_path), str(output_dir))

        assert result["matched"] == 1
        reader = PdfReader(result["output_file"])
        assert len(reader.pages) == 1
        page = reader.pages[0]
        # Shrink is a content transform, not a page-size change -- the
        # output page must stay the same physical size as the courier
        # label stock.
        assert float(page.mediabox.width) == pytest.approx(288)
        assert float(page.mediabox.height) == pytest.approx(432)
        assert "REF: REF-001" in page.extract_text()


class TestCreateReferenceOverlayBarcode:
    def test_draws_code128_barcode_with_reference_value(self, monkeypatch):
        from reportlab.graphics.barcode import code128

        calls = []
        original_draw_on = code128.Code128.drawOn

        def spy_draw_on(self, canv, x, y, **kwargs):
            calls.append((self.value, x, y))
            return original_draw_on(self, canv, x, y, **kwargs)

        monkeypatch.setattr(code128.Code128, "drawOn", spy_draw_on)

        pdf_processor.create_reference_overlay("REF-001", 288, 432)

        assert len(calls) == 1
        value, x, y = calls[0]
        assert value == "REF-001"
        assert x > 0
        assert y >= 0

    def test_overlay_still_valid_single_page_pdf(self):
        overlay_pdf = pdf_processor.create_reference_overlay("REF-001", 288, 432)
        reader = PdfReader(overlay_pdf)
        assert len(reader.pages) == 1
