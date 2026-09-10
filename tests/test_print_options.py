"""PrintOptions: closed by default, a mode hides the rows it does not use, and
every edit saves under the component's own scope (spec §4)."""

import pytest
from PySide6.QtCore import Qt

from gui.components import PrintOptions


@pytest.fixture
def options(qapp, print_settings_store):
    return PrintOptions("reference_labels", label_size_tooltip="Label size tip")


def _choose_mode(options, mode):
    options.print_mode_combo.setCurrentIndex(options.print_mode_combo.findData(mode))


def _zpl_fields(options):
    return (
        options.raw_zpl_target_edit,
        options.raw_zpl_label_width_spin.parentWidget(),  # the label-size row
        options.raw_zpl_rotate_check,
    )


def test_starts_closed_with_the_body_hidden(options):
    assert not options.is_open()
    assert options.body.isHidden()
    assert options.fold_button.arrowType() == Qt.RightArrow


def test_opening_shows_the_body_and_turns_the_arrow(options):
    options.set_open(True)
    assert options.is_open()
    assert not options.body.isHidden()
    assert options.fold_button.arrowType() == Qt.DownArrow

    options.set_open(False)
    assert options.body.isHidden()


def test_clicking_the_fold_button_opens_it(options):
    options.fold_button.click()
    assert options.is_open()
    assert not options.body.isHidden()


def test_driver_mode_shows_the_printer_row_and_hides_the_raw_zpl_rows(options):
    form = options.body.form
    assert form.isRowVisible(options.print_mode_combo)
    assert form.isRowVisible(options.driver_printer_combo)
    for field in _zpl_fields(options):
        assert not form.isRowVisible(field)


def test_raw_zpl_hides_the_driver_row(options):
    _choose_mode(options, "raw_zpl")
    form = options.body.form
    assert form.isRowVisible(options.print_mode_combo)
    assert not form.isRowVisible(options.driver_printer_combo)
    for field in _zpl_fields(options):
        assert form.isRowVisible(field)


def test_no_control_is_disabled_by_mode(options):
    controls = (options.driver_printer_combo, *_zpl_fields(options))
    for mode in ("raw_zpl", "driver"):
        _choose_mode(options, mode)
        assert all(control.isEnabled() for control in controls)


def test_an_edit_saves_under_the_scope_and_updates_the_summary(
    options, print_settings_store
):
    _choose_mode(options, "raw_zpl")
    assert print_settings_store["reference_labels"]["print_mode"] == "raw_zpl"
    assert (
        options.fold_button.text() == "Raw ZPL needs a printer target. Open to set one."
    )

    options.raw_zpl_target_edit.setText("ZPL-RAW")
    options.raw_zpl_target_edit.editingFinished.emit()
    assert print_settings_store["reference_labels"]["raw_zpl_target"] == "ZPL-RAW"
    assert (
        options.fold_button.text() == "Prints raw ZPL to ZPL-RAW at the PDF's page size"
    )
    assert options.fold_button.toolTip() == options.fold_button.text()


def test_an_edit_emits_changed(options):
    seen = []
    options.changed.connect(lambda: seen.append(True))
    options.raw_zpl_rotate_check.setChecked(True)
    assert seen == [True]


def test_construction_loads_the_saved_settings(qapp, print_settings_store):
    print_settings_store["barcode_generator"] = {
        "print_mode": "raw_zpl",
        "raw_zpl_target": "ZPL-RAW",
        "raw_zpl_rotate": True,
        "raw_zpl_label_width_mm": 68.0,
        "raw_zpl_label_height_mm": 38.0,
        "driver_printer_name": "",
    }
    options = PrintOptions("barcode_generator", label_size_tooltip="tip")
    assert options.print_mode_combo.currentData() == "raw_zpl"
    assert (
        options.fold_button.text()
        == "Prints raw ZPL to ZPL-RAW at 68 × 38 mm, rotated 90°"
    )
    assert options.current_settings() == print_settings_store["barcode_generator"]


def test_the_label_size_tooltip_reaches_both_spins(options):
    assert options.raw_zpl_label_width_spin.toolTip() == "Label size tip"
    assert options.raw_zpl_label_height_spin.toolTip() == "Label size tip"
