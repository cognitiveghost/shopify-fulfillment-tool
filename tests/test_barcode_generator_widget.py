"""Regression test for gui.barcode_generator_widget.BarcodeGeneratorWidget.

Root cause: _generate_pdf_from_results() swallowed rendering exceptions and
_on_generation_complete() always showed the "Generation Complete" success
dialog regardless, so a WeasyPrint/blabel failure looked like success with
no PDF ever written (CodeRabbit review on PR #259). Extended to cover the
"Add QR labels" checkbox and the auto-open-PDF checkbox (PR #259 follow-up).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from gui.barcode_generator_widget import IDLE_STATUS, BarcodeGeneratorWidget


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
        self.print_btn = Mock()
        self.print_qr_btn = Mock()
        self.last_barcode_pdf = None
        self.last_qr_pdf = None
        # Pinned at launch by _on_generate_clicked; the completion slot reads
        # this rather than the still-live combo.
        self._generating = ("PL1", 0)

    def _generate_pdf_from_results(self, results):
        self.pdf_render_calls += 1
        return self._pdf_ok

    def _generate_qr_pdf_from_results(self, results):
        self.qr_pdf_render_calls += 1
        return self._qr_pdf_ok

    def _open_pdf(self, pdf_path):
        self.opened_pdfs.append(pdf_path)


def _run(
    monkeypatch, pdf_ok, results=None, auto_open=True, add_qr=False, qr_pdf_ok=True
):
    info = Mock()
    critical = Mock()
    monkeypatch.setattr("gui.barcode_generator_widget.toast", info)
    monkeypatch.setattr("gui.barcode_generator_widget.show_error", critical)

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
    message = info.call_args[0][1]
    assert "QR" in message


def test_qr_generation_failure_does_not_block_primary_success_dialog(monkeypatch):
    widget, info, critical = _run(
        monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=False
    )
    assert info.called
    assert not critical.called
    message = info.call_args[0][1]
    assert "QR labels failed" in message
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]


def test_successful_generation_enables_print_button_and_sets_last_pdf(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True)
    assert widget.last_barcode_pdf == Path("/fake/barcodes/PL1_barcodes.pdf")
    widget.print_btn.setEnabled.assert_called_with(True)


def test_pdf_render_failure_leaves_print_button_disabled(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=False)
    assert widget.last_barcode_pdf is None
    widget.print_btn.setEnabled.assert_called_with(False)


def test_qr_checkbox_on_enables_print_qr_button(monkeypatch):
    widget, _info, _critical = _run(
        monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=True
    )
    assert widget.last_qr_pdf == Path("/fake/barcodes/PL1_qr_labels.pdf")
    widget.print_qr_btn.setEnabled.assert_called_with(True)


def test_qr_checkbox_off_leaves_print_qr_button_disabled(monkeypatch):
    widget, _info, _critical = _run(monkeypatch, pdf_ok=True, add_qr=False)
    assert widget.last_qr_pdf is None
    widget.print_qr_btn.setEnabled.assert_called_with(False)


class _FakeSelectionWidget:
    """Stand-in exposing only what _on_packing_list_changed() touches when no
    packing list is selected (index < 0) -- avoids constructing a real
    BarcodeGeneratorWidget (needs a live session)."""

    def __init__(self):
        self.status_label = Mock()
        self.order_count_label = Mock()
        self.output_dir_label = Mock()
        self.generate_btn = Mock()


def test_output_folder_row_is_never_blank(qtbot):
    """The Output folder row must say something before a packing list is chosen."""
    widget = BarcodeGeneratorWidget(SimpleNamespace(session_path=None))
    qtbot.addWidget(widget)
    assert widget.output_dir_label.text().strip() != ""


def test_order_count_label_wraps_instead_of_eliding(qtbot):
    """The count sentence must wrap, not elide, when it doesn't fit the card."""
    widget = BarcodeGeneratorWidget(SimpleNamespace(session_path=None))
    qtbot.addWidget(widget)
    assert widget.order_count_label.wordWrap() is True


def test_status_label_clears_when_packing_list_changes():
    """A previous run's count must not linger over a newly chosen packing list."""
    widget = _FakeSelectionWidget()

    BarcodeGeneratorWidget._on_packing_list_changed(widget, -1)

    widget.status_label.setText.assert_any_call("")


def test_barcode_generation_complete_logs_the_counts_for_a_repro(monkeypatch):
    """The log line must carry what a Windows repro needs: which packing
    list, how many orders were filtered, and the success/fail split."""
    monkeypatch.setattr("gui.barcode_generator_widget.toast", Mock())
    monkeypatch.setattr("gui.barcode_generator_widget.show_error", Mock())

    widget = _FakeWidget(pdf_ok=True)
    widget.auto_open_pdf_checkbox.isChecked.return_value = True
    widget.add_qr_checkbox.isChecked.return_value = False
    widget._generating = ("PL1", 2)
    results = [
        {"success": True, "order_number": "#1"},
        {"success": False, "order_number": "#2"},
    ]

    BarcodeGeneratorWidget._on_generation_complete(widget, results)

    logged = " ".join(str(c.args[0]) for c in widget.log.info.call_args_list)
    assert "PL1" in logged
    assert "2 orders filtered" in logged
    assert "1 labels written, 1 failed" in logged


def test_changing_the_packing_list_mid_run_still_writes_the_pdf(monkeypatch):
    """Only the generate button is disabled during a run, so the operator can
    still switch lists -- which clears filtered_orders_df. The completion slot
    must not read that state, or the PDF is lost to a TypeError."""
    monkeypatch.setattr("gui.barcode_generator_widget.toast", Mock())
    monkeypatch.setattr("gui.barcode_generator_widget.show_error", Mock())

    widget = _FakeWidget(pdf_ok=True)
    widget.auto_open_pdf_checkbox.isChecked.return_value = False
    widget.add_qr_checkbox.isChecked.return_value = False
    widget._generating = ("PL1", 2)
    # The operator switched lists while the worker ran.
    widget.filtered_orders_df = None

    BarcodeGeneratorWidget._on_generation_complete(
        widget, [{"success": True, "order_number": "#1"}]
    )

    assert widget.pdf_render_calls == 1
    logged = " ".join(str(c.args[0]) for c in widget.log.info.call_args_list)
    # ...and the line still names the list that was actually generated.
    assert "PL1" in logged
    assert "2 orders filtered" in logged


def test_status_label_shows_guidance_again_when_the_selection_clears():
    """Clearing a stale count must not leave the status row blank."""
    widget = _FakeSelectionWidget()

    BarcodeGeneratorWidget._on_packing_list_changed(widget, -1)

    assert widget.status_label.setText.call_args.args[0] == IDLE_STATUS
