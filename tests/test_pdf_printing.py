"""Tests for gui.pdf_printing -- the shared print-to-printer dispatcher
(driver mode + raw ZPL mode) both windows' Print buttons call into. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings
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
        settings = pdf_printing.load_print_settings()
        assert settings == {"print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False}

    def test_save_then_load_roundtrip(self, isolated_settings):
        pdf_printing.save_print_settings(
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True}
        )
        assert pdf_printing.load_print_settings() == {
            "print_mode": "raw_zpl",
            "raw_zpl_target": "ZPL-RAW-Printer",
            "raw_zpl_rotate": True,
        }


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
