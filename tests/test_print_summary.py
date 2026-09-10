"""The folded print-options row states its own values (spec §4 wording table)."""

import pytest

from gui.components.print_options import print_summary


def _settings(**overrides):
    settings = {
        "print_mode": "driver",
        "raw_zpl_target": "",
        "raw_zpl_rotate": False,
        "raw_zpl_label_width_mm": 0.0,
        "raw_zpl_label_height_mm": 0.0,
        "driver_printer_name": "",
    }
    settings.update(overrides)
    return settings


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "Prints through the print dialog to the Windows default printer"),
        (
            {"driver_printer_name": "Zebra GK420"},
            "Prints through the print dialog to Zebra GK420",
        ),
        (
            {"print_mode": "raw_zpl"},
            "Raw ZPL needs a printer target. Open to set one.",
        ),
        (
            {"print_mode": "raw_zpl", "raw_zpl_target": "   "},
            "Raw ZPL needs a printer target. Open to set one.",
        ),
        (
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW"},
            "Prints raw ZPL to ZPL-RAW at the PDF's page size",
        ),
        (
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 152.4,
                "raw_zpl_label_height_mm": 101.6,
                "raw_zpl_rotate": True,
            },
            "Prints raw ZPL to ZPL-RAW at 152.4 × 101.6 mm, rotated 90°",
        ),
        (
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 68.0,
                "raw_zpl_label_height_mm": 38.0,
            },
            "Prints raw ZPL to ZPL-RAW at 68 × 38 mm",
        ),
        (
            # One dimension alone is not a size: fitting needs both.
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_label_width_mm": 68.0,
            },
            "Prints raw ZPL to ZPL-RAW at the PDF's page size",
        ),
        (
            {
                "print_mode": "raw_zpl",
                "raw_zpl_target": "ZPL-RAW",
                "raw_zpl_rotate": True,
            },
            "Prints raw ZPL to ZPL-RAW at the PDF's page size, rotated 90°",
        ),
    ],
)
def test_print_summary(overrides, expected):
    assert print_summary(_settings(**overrides)) == expected


def test_driver_mode_ignores_raw_zpl_values():
    settings = _settings(raw_zpl_target="ZPL-RAW", raw_zpl_rotate=True)
    assert print_summary(settings) == (
        "Prints through the print dialog to the Windows default printer"
    )
