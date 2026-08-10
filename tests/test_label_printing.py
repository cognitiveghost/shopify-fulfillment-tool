"""Tests for shopify_tool.label_printing -- raw ZPL printing for the Citizen
CL-E300, ported from barcode_tool's proven template_renderer.py /
zpl_print_service.py (see docs/superpowers/specs/2026-08-10-direct-label-printing-design.md)."""
import sys
import types

from PIL import Image

from shopify_tool import label_printing


def _make_pdf(tmp_path, pages=2):
    """A minimal multi-page PDF via reportlab (already a dependency) for
    rasterize_pdf() to read -- content doesn't matter, only page count/size."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "labels.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(68 * mm, 38 * mm))
    for _ in range(pages):
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
    c.save()
    return pdf_path


class TestRasterizePdf:
    def test_returns_one_image_per_page(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=3)
        images = label_printing.rasterize_pdf(pdf_path)
        assert len(images) == 3

    def test_images_are_1bit_mode(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=1)
        images = label_printing.rasterize_pdf(pdf_path)
        assert images[0].mode == "1"

    def test_dpi_controls_pixel_dimensions(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=1)
        low = label_printing.rasterize_pdf(pdf_path, dpi=72)[0]
        high = label_printing.rasterize_pdf(pdf_path, dpi=203)[0]
        assert high.width > low.width
        assert high.height > low.height


class TestImageToZpl:
    def test_wraps_field_in_xa_xz(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image)
        assert zpl.startswith("^XA\n")
        assert zpl.endswith("^XZ\n")

    def test_pw_ll_match_image_dimensions(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image)
        assert "^PW100\n" in zpl
        assert "^LL50\n" in zpl

    def test_rotate_swaps_pw_ll(self):
        image = Image.new("1", (100, 50))
        zpl = label_printing.image_to_zpl(image, rotate=True)
        assert "^PW50\n" in zpl
        assert "^LL100\n" in zpl


class TestSendRawLinux:
    def test_writes_bytes_to_device_path(self, tmp_path):
        target = tmp_path / "fake_device"
        label_printing.send_raw_linux(str(target), b"^XA...^XZ")
        assert target.read_bytes() == b"^XA...^XZ"


class TestSendRawWindows:
    def test_spools_raw_datatype_and_writes_data(self, monkeypatch):
        calls = []
        fake_win32print = types.SimpleNamespace(
            OpenPrinter=lambda name: calls.append(("open", name)) or "HANDLE",
            StartDocPrinter=lambda h, level, doc_info: calls.append(("start_doc", h, doc_info)),
            StartPagePrinter=lambda h: calls.append(("start_page", h)),
            WritePrinter=lambda h, data: calls.append(("write", h, data)),
            EndPagePrinter=lambda h: calls.append(("end_page", h)),
            EndDocPrinter=lambda h: calls.append(("end_doc", h)),
            ClosePrinter=lambda h: calls.append(("close", h)),
        )
        monkeypatch.setitem(sys.modules, "win32print", fake_win32print)

        label_printing.send_raw_windows("ZPL-RAW-Printer", b"^XA...^XZ")

        assert ("open", "ZPL-RAW-Printer") in calls
        assert calls[1] == ("start_doc", "HANDLE", ("ZPL label", "", "RAW"))
        assert ("write", "HANDLE", b"^XA...^XZ") in calls
        assert calls[-1] == ("close", "HANDLE")


class TestPrintPdfRawZpl:
    def test_sends_one_job_per_page(self, tmp_path, monkeypatch):
        pdf_path = _make_pdf(tmp_path, pages=2)
        sent = []
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(
            label_printing, "send_raw_linux", lambda target, data: sent.append((target, data))
        )
        label_printing.print_pdf_raw_zpl(pdf_path, "/dev/usb/lp0")
        assert len(sent) == 2
        assert all(target == "/dev/usb/lp0" for target, _ in sent)


class TestWindowsPrintErrors:
    def test_returns_empty_tuple_when_pywintypes_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pywintypes", None)
        assert label_printing.windows_print_errors() == ()
