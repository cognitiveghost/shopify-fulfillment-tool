"""Both Tools widgets as card content: no group boxes, one PrintOptions each
under its own persisted scope (spec §3)."""

from types import SimpleNamespace

from PySide6.QtWidgets import QGroupBox

from gui.components import PrintOptions
from gui.reference_labels_widget import ReferenceLabelsWidget


def _main_window():
    # Both widgets tolerate a window with no session: no session_changed
    # signal, session_path None.
    return SimpleNamespace(session_path=None)


def test_reference_card_has_no_group_boxes(qapp, print_settings_store):
    widget = ReferenceLabelsWidget(_main_window())
    assert widget.findChildren(QGroupBox) == []


def test_reference_card_holds_one_print_options_under_its_scope(
    qapp, print_settings_store
):
    widget = ReferenceLabelsWidget(_main_window())
    assert widget.findChildren(PrintOptions) == [widget.print_options]

    widget.print_options.raw_zpl_rotate_check.setChecked(True)
    assert print_settings_store["reference_labels"]["raw_zpl_rotate"] is True


def test_reference_card_without_a_session_says_what_to_do(qapp, print_settings_store):
    widget = ReferenceLabelsWidget(_main_window())
    assert (
        widget.output_dir_label.full_text() == "Open a session to save labels into it"
    )
    assert widget.pdf_label.full_text() == "No file chosen"
    assert widget.csv_label.full_text() == "No file chosen"
    assert not widget.process_btn.isEnabled()
    assert not widget.print_btn.isEnabled()


def test_reference_card_is_ready_once_both_files_and_a_folder_exist(
    qapp, print_settings_store, tmp_path
):
    widget = ReferenceLabelsWidget(_main_window())
    widget.pdf_path, widget.csv_path, widget.output_dir = "in.pdf", "in.csv", tmp_path
    widget._update_process_button()
    assert widget.process_btn.isEnabled()
