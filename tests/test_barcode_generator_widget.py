"""Regression test for gui.barcode_generator_widget.BarcodeGeneratorWidget.

Root cause: _generate_pdf_from_results() swallowed rendering exceptions and
_on_generation_complete() always showed the "Generation Complete" success
dialog regardless, so a WeasyPrint/blabel failure looked like success with
no PDF ever written (CodeRabbit review on PR #259). Extended to cover the
"Add QR labels" checkbox and the auto-open-PDF checkbox (PR #259 follow-up).
"""
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from gui.barcode_generator_widget import BarcodeGeneratorWidget


class _FakeWidget:
    """Stand-in exposing only what _on_generation_complete() touches --
    avoids constructing a real BarcodeGeneratorWidget (needs a live session)."""

    def __init__(self, pdf_ok, qr_pdf_ok=True):
        self._pdf_ok = pdf_ok
        self._qr_pdf_ok = qr_pdf_ok
        self.log = Mock()
        self.progress_bar = Mock()
        self.status_label = Mock()
        self.add_qr_checkbox = Mock()
        self.auto_open_pdf_checkbox = Mock()
        self.current_packing_list = "PL1"
        self.barcodes_dir = Path("/fake/barcodes")
        self.generation_complete = Mock()
        self.opened_pdfs = []
        self.pdf_render_calls = 0
        self.qr_pdf_render_calls = 0

    def _generate_pdf_from_results(self, results):
        self.pdf_render_calls += 1
        return self._pdf_ok

    def _generate_qr_pdf_from_results(self, results):
        self.qr_pdf_render_calls += 1
        return self._qr_pdf_ok

    def _open_pdf(self, pdf_path):
        self.opened_pdfs.append(pdf_path)


def _run(monkeypatch, pdf_ok, results=None, auto_open=True, add_qr=False, qr_pdf_ok=True):
    info = Mock()
    critical = Mock()
    monkeypatch.setattr(QMessageBox, "information", info)
    monkeypatch.setattr(QMessageBox, "critical", critical)

    widget = _FakeWidget(pdf_ok, qr_pdf_ok=qr_pdf_ok)
    widget.auto_open_pdf_checkbox.isChecked.return_value = auto_open
    widget.add_qr_checkbox.isChecked.return_value = add_qr
    if results is None:
        results = [{"success": True, "order_number": "#1"}]

    BarcodeGeneratorWidget._on_generation_complete(widget, results)
    return widget, info, critical


def test_pdf_render_failure_shows_error_not_success(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=False)
    assert critical.called
    assert not info.called
    assert not widget.opened_pdfs


def test_pdf_render_success_shows_completion_message(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True)
    assert info.called
    assert not critical.called
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]


def test_all_orders_failed_skips_pdf_render_and_shows_completion_message(monkeypatch):
    widget, info, critical = _run(
        monkeypatch, pdf_ok=True, results=[{"success": False, "order_number": "#1"}]
    )
    assert widget.pdf_render_calls == 0
    assert info.called
    assert not critical.called
    assert not widget.opened_pdfs


def test_auto_open_off_renders_but_does_not_open(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True, auto_open=False)
    assert widget.pdf_render_calls == 1
    assert not widget.opened_pdfs


def test_qr_checkbox_off_skips_qr_generation(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True, add_qr=False)
    assert widget.qr_pdf_render_calls == 0
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]


def test_qr_checkbox_on_generates_and_opens_both_pdfs(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=True)
    assert widget.qr_pdf_render_calls == 1
    assert widget.opened_pdfs == [
        Path("/fake/barcodes/PL1_barcodes.pdf"),
        Path("/fake/barcodes/PL1_qr_labels.pdf"),
    ]
    assert info.called
    assert not critical.called
    message = info.call_args[0][2]
    assert "QR" in message


def test_qr_generation_failure_does_not_block_primary_success_dialog(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=False)
    assert info.called
    assert not critical.called
    message = info.call_args[0][2]
    assert "QR labels PDF failed" in message
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]
