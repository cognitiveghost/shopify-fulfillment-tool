"""Tests for gui.pdf_printing -- the shared print-to-printer dispatcher
(driver mode + raw ZPL mode) both windows' Print buttons call into. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit, QMessageBox

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


class TestRefreshPrintControls:
    """Reference Labels and Barcode Generator each keep their own copy of
    these controls; refresh_print_controls() is what stops one window's
    stale controls from clobbering a change just made in the other (see
    PR #261 review, Important #2)."""

    @staticmethod
    def _make_controls():
        combo = QComboBox()
        combo.addItem("OS driver (print dialog)", "driver")
        combo.addItem("Raw ZPL (direct)", "raw_zpl")
        return combo, QLineEdit(), QCheckBox()

    def test_pulls_current_settings_into_controls(self, isolated_settings):
        pdf_printing.save_print_settings(
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True}
        )
        combo, target_edit, rotate_check = self._make_controls()

        pdf_printing.refresh_print_controls(combo, target_edit, rotate_check)

        assert combo.currentData() == "raw_zpl"
        assert target_edit.text() == "ZPL-RAW-Printer"
        assert rotate_check.isChecked() is True
        assert target_edit.isEnabled() and rotate_check.isEnabled()

    def test_reload_does_not_resave_and_clobber_other_window(self, isolated_settings):
        # Simulates: Barcode Generator sets raw_zpl + a target...
        pdf_printing.save_print_settings(
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": False}
        )
        # ...operator switches to Reference Labels, whose controls were built
        # earlier and still show the stale "driver" default.
        combo, target_edit, rotate_check = self._make_controls()
        save_spy = Mock(wraps=pdf_printing.save_print_settings)
        combo.currentIndexChanged.connect(lambda _: save_spy(pdf_printing.load_print_settings()))
        rotate_check.toggled.connect(lambda _: save_spy(pdf_printing.load_print_settings()))

        pdf_printing.refresh_print_controls(combo, target_edit, rotate_check)

        assert not save_spy.called
        assert pdf_printing.load_print_settings() == {
            "print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": False,
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
