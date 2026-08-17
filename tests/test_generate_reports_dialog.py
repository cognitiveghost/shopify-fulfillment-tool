"""One dialog generating any number of reports of both kinds in one pass.

Previously two buttons opened two modal dialogs, each emitting exactly one
config, so producing a packing list and its stock export took two full
round-trips.
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.report_selection_dialog import GenerateReportsDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


PACKING = [
    {"name": "DHL", "output_filename": "dhl.xlsx", "filters": []},
    {"name": "DPD", "output_filename": "dpd.xlsx", "filters": []},
]
STOCK = [{"name": "Daily ERP", "output_filename": "erp.xls", "filters": []}]


def _df():
    return pd.DataFrame({
        "Order_Number": ["#1001"],
        "SKU": ["AB-01"],
        "Quantity": [1],
        "Order_Fulfillment_Status": ["Fulfillable"],
    })


def _dialog():
    return GenerateReportsDialog(PACKING, STOCK, _df(), lambda df, f: df)


def test_emits_every_checked_report_with_its_type():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog.set_checked("packing_lists", 0, True)
    dialog.set_checked("packing_lists", 1, True)
    dialog.set_checked("stock_exports", 0, True)
    dialog._on_generate()

    (batch,) = emitted
    assert [(r["name"], r["report_type"]) for r in batch] == [
        ("DHL", "packing_lists"),
        ("DPD", "packing_lists"),
        ("Daily ERP", "stock_exports"),
    ]


def test_emits_nothing_when_no_report_is_checked():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog._on_generate()

    assert emitted == []


def test_generate_button_is_disabled_until_something_is_checked():
    dialog = _dialog()
    assert dialog.generate_button.isEnabled() is False

    dialog.set_checked("packing_lists", 0, True)

    assert dialog.generate_button.isEnabled() is True
