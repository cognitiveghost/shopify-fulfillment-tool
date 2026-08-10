"""Regression test for gui.reference_labels_widget.ReferenceLabelsWidget's
Print button -- mirrors the _FakeWidget pattern in
test_barcode_generator_widget.py. See
docs/superpowers/specs/2026-08-10-direct-label-printing-design.md."""
from pathlib import Path
from unittest.mock import Mock

from gui.reference_labels_widget import ReferenceLabelsWidget


class _FakeWidget:
    def __init__(self):
        self.log = Mock()
        self.progress_bar = Mock()
        self.status_label = Mock()
        self.history = None
        self.pdf_path = "in.pdf"
        self.csv_path = "in.csv"
        self.auto_open_checkbox = Mock(isChecked=Mock(return_value=False))
        self.print_btn = Mock()
        self.processing_complete = Mock()
        self.last_output_pdf = None

    def _open_pdf(self, path):
        pass


def _result(**overrides):
    result = {
        "matched": 3, "unmatched": 0, "output_file": "/fake/out.pdf",
        "pages_processed": 3, "processing_time": 1.2,
    }
    result.update(overrides)
    return result


def test_print_button_disabled_before_processing():
    widget = _FakeWidget()
    assert widget.last_output_pdf is None


def test_processing_complete_sets_last_output_pdf_and_enables_print(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", Mock())

    widget = _FakeWidget()
    ReferenceLabelsWidget._on_processing_complete(widget, _result())

    assert widget.last_output_pdf == Path("/fake/out.pdf")
    widget.print_btn.setEnabled.assert_called_with(True)
