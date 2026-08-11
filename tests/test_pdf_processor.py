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


class TestProcessReferenceLabelsRotation:
    def test_rotated_page_normalized_before_shrink(self, tmp_path):
        """Courier PDFs vary in /Rotate (some ship pre-rotated label stock).
        The strip must always land on the true visual bottom, not the raw
        mediabox's unrotated bottom edge."""
        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path, width_pt=288, height_pt=432)

        reader = PdfReader(str(pdf_path))
        writer_page = reader.pages[0]
        writer_page.rotate(90)
        from pypdf import PdfWriter
        rotated_writer = PdfWriter()
        rotated_writer.add_page(writer_page)
        rotated_pdf_path = tmp_path / "courier_rotated.pdf"
        with open(rotated_pdf_path, "wb") as f:
            rotated_writer.write(f)

        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text(
            "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
            ",,REF-001,,,,Acme Warehouse Co\n"
        )
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = pdf_processor.process_reference_labels(
            str(rotated_pdf_path), str(csv_path), str(output_dir)
        )
        assert result["matched"] == 1

        out_page = PdfReader(result["output_file"]).pages[0]
        # Rotation baked into content and reset -- mediabox now reflects the
        # true visual page (swapped from the original 288x432 mediabox).
        assert out_page.rotation == 0
        assert float(out_page.mediabox.width) == pytest.approx(432)
        assert float(out_page.mediabox.height) == pytest.approx(288)


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

    def test_barcode_module_width_is_whole_dots_at_print_dpi(self, monkeypatch):
        # 0.8pt (the old value) is 2.26 dots at 203 DPI -- a fractional dot
        # count where rasterization rounds bars inconsistently, blurring
        # the barcode into a near-solid block. barWidth must land on a
        # clean whole-dot count.
        from reportlab.graphics.barcode import code128

        from shopify_tool.label_printing import PRINT_DPI

        calls = []
        original_init = code128.Code128.__init__

        def spy_init(self, value, **kwargs):
            calls.append(kwargs.get("barWidth"))
            return original_init(self, value, **kwargs)

        monkeypatch.setattr(code128.Code128, "__init__", spy_init)

        pdf_processor.create_reference_overlay("REF-001", 288, 432)

        assert len(calls) == 1
        module_dots = calls[0] * PRINT_DPI / 72
        assert module_dots == pytest.approx(round(module_dots))
        assert module_dots >= 3


class TestCreateReferenceOverlayLayout:
    def test_ref_and_barcode_block_is_horizontally_centered(self, monkeypatch):
        from reportlab.graphics.barcode import code128
        from reportlab.pdfgen import canvas as canvas_mod

        page_width = 288
        draw_string_calls = []
        original_draw_string = canvas_mod.Canvas.drawString

        def spy_draw_string(self, x, y, text, **kwargs):
            draw_string_calls.append((x, y, text))
            return original_draw_string(self, x, y, text, **kwargs)

        monkeypatch.setattr(canvas_mod.Canvas, "drawString", spy_draw_string)

        barcode_calls = []
        original_draw_on = code128.Code128.drawOn

        def spy_draw_on(self, canv, x, y, **kwargs):
            barcode_calls.append((x, self.width))
            return original_draw_on(self, canv, x, y, **kwargs)

        monkeypatch.setattr(code128.Code128, "drawOn", spy_draw_on)

        pdf_processor.create_reference_overlay("REF-001", page_width, 432)

        text_x, _text_y, text = draw_string_calls[0]
        barcode_x, barcode_width = barcode_calls[0]

        block_start = text_x
        block_end = barcode_x + barcode_width
        block_center = (block_start + block_end) / 2

        # The combined REF-text + barcode block sits centered on the page,
        # not left-margin-anchored -- "bottom middle", not "bottom left".
        assert block_center == pytest.approx(page_width / 2, abs=1.0)
        assert text == "REF: REF-001"

    def test_separator_line_drawn_at_strip_boundary(self, monkeypatch):
        from reportlab.pdfgen import canvas as canvas_mod

        page_height = 432
        line_calls = []
        original_line = canvas_mod.Canvas.line

        def spy_line(self, x1, y1, x2, y2, **kwargs):
            line_calls.append((x1, y1, x2, y2))
            return original_line(self, x1, y1, x2, y2, **kwargs)

        monkeypatch.setattr(canvas_mod.Canvas, "line", spy_line)

        pdf_processor.create_reference_overlay("REF-001", 288, page_height)

        assert len(line_calls) == 1
        x1, y1, x2, y2 = line_calls[0]
        strip_height = page_height * (1 - pdf_processor._CONTENT_SCALE)
        # Horizontal line at the top of the reference strip -- the boundary
        # between the shrunk courier content and the added strip.
        assert y1 == pytest.approx(strip_height)
        assert y1 == pytest.approx(y2)
        assert x2 > x1
