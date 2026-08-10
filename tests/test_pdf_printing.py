"""Tests for gui.pdf_printing -- the shared print-to-printer dispatcher
(driver mode + raw ZPL mode) both windows' Print buttons call into. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication, QMessageBox

from gui import pdf_printing


@pytest.fixture(scope="module", autouse=True)
def qapp():
    # _print_pdf_driver_mode() below constructs real QPdfDocument/QPrinter/
    # QPainter objects -- without a live QApplication these abort the
    # process (SIGABRT), not raise a catchable Python exception. Matches the
    # qapp fixture pattern used throughout tests/ (e.g. test_pandas_model.py).
    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_settings(monkeypatch):
    """Point QSettings at a throwaway org/app pair so tests never touch the
    developer's real local settings."""
    monkeypatch.setattr(pdf_printing, "_SETTINGS", ("ShopifyFulfillmentToolTest", "PrintingTest"))
    yield
    QSettings(*pdf_printing._SETTINGS).clear()


class TestPrintSettingsRoundTrip:
    def test_defaults_when_nothing_saved(self, isolated_settings):
        settings = pdf_printing.load_print_settings("reference_labels")
        assert settings == {
            "print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False,
            "driver_printer_name": "",
        }

    def test_save_then_load_roundtrip(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {
                "print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer",
                "raw_zpl_rotate": True, "driver_printer_name": "Labels 6x4",
            },
        )
        assert pdf_printing.load_print_settings("reference_labels") == {
            "print_mode": "raw_zpl",
            "raw_zpl_target": "ZPL-RAW-Printer",
            "raw_zpl_rotate": True,
            "driver_printer_name": "Labels 6x4",
        }

    def test_different_scopes_do_not_collide(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {
                "print_mode": "raw_zpl", "raw_zpl_target": "Labels 6x4",
                "raw_zpl_rotate": False, "driver_printer_name": "Labels 6x4",
            },
        )
        pdf_printing.save_print_settings(
            "barcode_generator",
            {
                "print_mode": "driver", "raw_zpl_target": "Barcodes",
                "raw_zpl_rotate": True, "driver_printer_name": "Barcodes",
            },
        )

        ref_settings = pdf_printing.load_print_settings("reference_labels")
        barcode_settings = pdf_printing.load_print_settings("barcode_generator")
        assert ref_settings["driver_printer_name"] == "Labels 6x4"
        assert barcode_settings["driver_printer_name"] == "Barcodes"


class TestPrintPdfRawZplMode:
    def test_blank_target_warns_and_returns_false(self, monkeypatch, tmp_path):
        warning = Mock()
        monkeypatch.setattr(QMessageBox, "warning", warning)
        called = Mock()
        monkeypatch.setattr(pdf_printing.label_printing, "print_pdf_raw_zpl", called)

        result = pdf_printing.print_pdf(
            None, tmp_path / "x.pdf", {"print_mode": "raw_zpl", "raw_zpl_target": "", "raw_zpl_rotate": False}
        )

        assert result is False
        assert warning.called
        assert not called.called

    def test_calls_print_pdf_raw_zpl_with_target_and_rotate(self, monkeypatch, tmp_path):
        called = Mock()
        monkeypatch.setattr(pdf_printing.label_printing, "print_pdf_raw_zpl", called)
        pdf_path = tmp_path / "x.pdf"

        result = pdf_printing.print_pdf(
            None, pdf_path,
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True},
        )

        assert result is True
        called.assert_called_once_with(pdf_path, "ZPL-RAW-Printer", rotate=True)

    def test_exception_shows_critical_and_returns_false(self, monkeypatch, tmp_path):
        critical = Mock()
        monkeypatch.setattr(QMessageBox, "critical", critical)
        monkeypatch.setattr(
            pdf_printing.label_printing, "print_pdf_raw_zpl",
            Mock(side_effect=OSError("printer offline")),
        )

        result = pdf_printing.print_pdf(
            None, tmp_path / "x.pdf",
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": False},
        )

        assert result is False
        assert critical.called


class TestPrintPdfDriverMode:
    def test_missing_pdf_shows_critical_and_returns_false(self, monkeypatch, tmp_path):
        critical = Mock()
        monkeypatch.setattr(QMessageBox, "critical", critical)

        result = pdf_printing._print_pdf_driver_mode(None, tmp_path / "does_not_exist.pdf")

        assert result is False
        assert critical.called

    def test_renders_expected_page_count_to_pdf_output(self, tmp_path):
        """No real OS printer needed: point QPrinter at PdfFormat output
        instead of a live printer, matching the original D-1 testing note."""
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        for _ in range(2):
            c.drawString(5 * mm, 5 * mm, "TEST")
            c.showPage()
        c.save()

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)

        assert result is True
        assert out_pdf.exists()
        import pypdf
        assert len(pypdf.PdfReader(str(out_pdf)).pages) == 2


class TestResolvePageRange:
    def test_all_pages_when_range_unset(self):
        printer = QPrinter()
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (0, 4)

    def test_honors_page_range_selection(self):
        printer = QPrinter()
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 3)
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (1, 2)

    def test_page_range_clamped_to_document_length(self):
        printer = QPrinter()
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 99)
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (1, 4)


class TestApplyDefaultPageSize:
    def test_sets_page_size_from_pdf_dimensions(self, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "label.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        document = QPdfDocument()
        document.load(str(src_pdf))
        printer = QPrinter()

        pdf_printing._apply_default_page_size(printer, document)

        page_size = printer.pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        assert page_size.width() == pytest.approx(68, abs=0.5)
        assert page_size.height() == pytest.approx(38, abs=0.5)


class TestPrintPdfDriverModeRendersAtCorrectSize:
    def test_renders_larger_than_the_old_point_size_bug(self, monkeypatch, tmp_path):
        """Regression test for the tiny-corner-stamp bug: the old code called
        document.render(page, document.pagePointSize(page).toSize()) -- a
        68x38mm label's *point* size (~193x108) used directly as *pixel*
        dimensions, then drawn 1:1 onto the printer's high-res canvas. The
        fix renders at the printer's actual device-pixel page rect instead,
        which is always larger than the raw point size once a real printer
        resolution (HighResolution mode) is applied."""
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        render_calls = []
        original_render = QPdfDocument.render

        def spy_render(self, page, size):
            render_calls.append(size)
            return original_render(self, page, size)

        monkeypatch.setattr(QPdfDocument, "render", spy_render)

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)
        assert result is True

        probe = QPdfDocument()
        probe.load(str(src_pdf))
        point_size = probe.pagePointSize(0).toSize()

        assert len(render_calls) == 1
        rendered_size = render_calls[0]
        assert rendered_size.width() > point_size.width()
        assert rendered_size.height() > point_size.height()


class TestPrintPdfDriverModeDefaultPrinter:
    def test_applies_stored_default_printer_name(self, monkeypatch, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        calls = []
        original_set_name = QPrinter.setPrinterName

        def spy_set_name(self, name):
            calls.append(name)
            return original_set_name(self, name)

        monkeypatch.setattr(QPrinter, "setPrinterName", spy_set_name)

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(
            None, src_pdf, output_path=out_pdf, driver_printer_name="Labels 6x4"
        )

        assert result is True
        assert calls == ["Labels 6x4"]

    def test_blank_default_printer_name_does_not_set_printer_name(self, monkeypatch, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        calls = []
        monkeypatch.setattr(QPrinter, "setPrinterName", lambda self, name: calls.append(name))

        out_pdf = tmp_path / "out.pdf"
        pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)

        assert calls == []


class TestPrintPdfDispatchesDriverPrinterName:
    def test_print_pdf_forwards_stored_printer_name(self, monkeypatch, tmp_path):
        called = Mock()
        monkeypatch.setattr(pdf_printing, "_print_pdf_driver_mode", called)

        pdf_printing.print_pdf(
            None, tmp_path / "x.pdf",
            {
                "print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False,
                "driver_printer_name": "Labels 6x4",
            },
        )

        called.assert_called_once_with(None, tmp_path / "x.pdf", driver_printer_name="Labels 6x4")
