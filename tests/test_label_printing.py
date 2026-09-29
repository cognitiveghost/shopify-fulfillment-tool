"""Tests for shopify_tool.label_printing -- raw ZPL printing for the Citizen
CL-E300, ported from barcode_tool's proven template_renderer.py /
zpl_print_service.py (see docs/superpowers/specs/2026-08-10-direct-label-printing-design.md)."""
import logging
import re
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


def _half_black(width=16, height=1):
    """Mode-"1" image, left half black, built the way rasterize_pdf builds
    one (greyscale -> convert("1")), so its pixels are 0/255."""
    grey = Image.new("L", (width, height), 255)
    grey.paste(0, (0, 0, width // 2, height))
    return grey.convert("1", dither=Image.Dither.NONE)


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

    def test_target_size_mm_overrides_source_page_size(self, tmp_path):
        # The source PDF here is authored at 68x38mm; a courier PDF's own
        # page size can't be trusted (varies page to page in the same
        # batch), so target_size_mm must win regardless of the source.
        pdf_path = _make_pdf(tmp_path, pages=1)
        image = label_printing.rasterize_pdf(pdf_path, dpi=203, target_size_mm=(100.0, 150.0))[0]
        assert image.size == (round(100.0 / 25.4 * 203), round(150.0 / 25.4 * 203))

    def test_target_size_mm_normalizes_pages_of_differing_source_size(self, tmp_path):
        # Reproduces the real bug: a batch PDF where pages have different
        # native sizes (mixed couriers) must all come out identical once a
        # target size is given, instead of mirroring their own varying size.
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "mixed.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.setPageSize((98 * mm, 147 * mm))
        c.showPage()
        c.setPageSize((114 * mm, 100 * mm))
        c.showPage()
        c.save()

        images = label_printing.rasterize_pdf(pdf_path, target_size_mm=(152.4, 101.6))
        assert images[0].size == images[1].size == (
            round(152.4 / 25.4 * 203), round(101.6 / 25.4 * 203)
        )

    def test_no_target_size_mm_keeps_source_page_size(self, tmp_path):
        pdf_path = _make_pdf(tmp_path, pages=1)
        default = label_printing.rasterize_pdf(pdf_path)[0]
        explicit_none = label_printing.rasterize_pdf(pdf_path, target_size_mm=None)[0]
        assert default.size == explicit_none.size


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

    def test_black_pixels_become_set_bits(self):
        # ZPL ^GFA: a set bit is a printed (black) dot. Left half black ->
        # first byte ff, second byte 00. Nothing checked this before.
        zpl = label_printing.image_to_zpl(_half_black())
        assert ",ff00^FS" in zpl

    def test_invert_flips_the_polarity(self):
        zpl = label_printing.image_to_zpl(_half_black(), invert=True)
        assert ",00ff^FS" in zpl

    def test_label_reverse_is_reset_right_after_xa(self):
        zpl = label_printing.image_to_zpl(Image.new("1", (100, 50)))
        assert zpl.startswith("^XA\n^LRN\n^PW100\n^LL50\n")

    def test_rotate_and_invert_compose(self):
        # 8 wide x 16 tall, top half black. ROTATE_90 (counter-clockwise)
        # makes it 16 wide x 8 tall with the black half on the left, so
        # each row is ff00; inverted, each row is 00ff.
        grey = Image.new("L", (8, 16), 255)
        grey.paste(0, (0, 0, 8, 8))
        image = grey.convert("1", dither=Image.Dither.NONE)
        zpl = label_printing.image_to_zpl(image, rotate=True, invert=True)
        assert "^PW16\n^LL8\n" in zpl
        assert "," + "00ff" * 8 + "^FS" in zpl


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

    def test_target_size_mm_passed_through_to_rasterize(self, tmp_path, monkeypatch):
        pdf_path = _make_pdf(tmp_path, pages=1)
        seen = []
        original_rasterize = label_printing.rasterize_pdf

        def spy_rasterize(path, dpi=label_printing.PRINT_DPI, target_size_mm=None):
            seen.append(target_size_mm)
            return original_rasterize(path, dpi=dpi, target_size_mm=target_size_mm)

        monkeypatch.setattr(label_printing, "rasterize_pdf", spy_rasterize)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(label_printing, "send_raw_linux", lambda target, data: None)

        label_printing.print_pdf_raw_zpl(pdf_path, "/dev/usb/lp0", target_size_mm=(152.4, 101.6))

        assert seen == [(152.4, 101.6)]

    def test_invert_passed_through_to_image_to_zpl(self, tmp_path, monkeypatch):
        pdf_path = _make_pdf(tmp_path, pages=1)
        seen = []
        monkeypatch.setattr(
            label_printing,
            "image_to_zpl",
            lambda image, rotate=False, invert=False: seen.append(invert) or "^XA^XZ",
        )
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(label_printing, "send_raw_linux", lambda target, data: None)

        label_printing.print_pdf_raw_zpl(pdf_path, "/dev/usb/lp0", invert=True)

        assert seen == [True]

    def test_logs_label_count_and_first_label_ink(self, tmp_path, monkeypatch, caplog):
        pdf_path = _make_pdf(tmp_path, pages=2)
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(label_printing, "send_raw_linux", lambda target, data: None)

        with caplog.at_level(logging.INFO, logger="shopify_tool.label_printing"):
            label_printing.print_pdf_raw_zpl(pdf_path, "/dev/usb/lp0")

        match = re.search(
            r"Raw ZPL: 2 label\(s\) to /dev/usb/lp0, first label (\d+)% black", caplog.text
        )
        assert match
        # A mostly-white label ("TEST" on white) is nowhere near inverted.
        assert int(match.group(1)) < 50


class TestWindowsPrintErrors:
    def test_returns_empty_tuple_when_pywintypes_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pywintypes", None)
        assert label_printing.windows_print_errors() == ()
