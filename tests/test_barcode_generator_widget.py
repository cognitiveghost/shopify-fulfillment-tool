"""Regression test for gui.barcode_generator_widget.BarcodeGeneratorWidget.

Root cause: _generate_pdf_from_results() swallowed rendering exceptions and
_on_generation_complete() always showed the "Generation Complete" success
dialog regardless, so a WeasyPrint/blabel failure looked like success with
no PDF ever written (CodeRabbit review on PR #259).
"""
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from gui.barcode_generator_widget import BarcodeGeneratorWidget


class _FakeWidget:
    """Stand-in exposing only what _on_generation_complete() touches --
    avoids constructing a real BarcodeGeneratorWidget (needs a live session)."""

    def __init__(self, pdf_ok):
        self._pdf_ok = pdf_ok
        self.log = Mock()
        self.progress_bar = Mock()
        self.status_label = Mock()
        self.auto_open_folder_checkbox = Mock()
        self.current_packing_list = "PL1"
        self.generation_complete = Mock()
        self.opened_folder = False
        self.pdf_render_calls = 0

    def _generate_pdf_from_results(self, results):
        self.pdf_render_calls += 1
        return self._pdf_ok

    def _open_barcodes_folder(self):
        self.opened_folder = True


def _run(monkeypatch, pdf_ok, results=None, auto_open=True):
    info = Mock()
    critical = Mock()
    monkeypatch.setattr(QMessageBox, "information", info)
    monkeypatch.setattr(QMessageBox, "critical", critical)

    widget = _FakeWidget(pdf_ok)
    widget.auto_open_folder_checkbox.isChecked.return_value = auto_open
    if results is None:
        results = [{"success": True, "order_number": "#1"}]

    BarcodeGeneratorWidget._on_generation_complete(widget, results)
    return widget, info, critical


def test_pdf_render_failure_shows_error_not_success(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=False)
    assert critical.called
    assert not info.called
    assert not widget.opened_folder


def test_pdf_render_success_shows_completion_message(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True)
    assert info.called
    assert not critical.called
    assert widget.opened_folder


def test_all_orders_failed_skips_pdf_render_and_shows_completion_message(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, results=[{"success": False, "order_number": "#1"}])
    assert widget.pdf_render_calls == 0
    assert info.called
    assert not critical.called
    assert not widget.opened_folder
