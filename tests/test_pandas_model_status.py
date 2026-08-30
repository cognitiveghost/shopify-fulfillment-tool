"""Spec §9 tests 8-9: the model emits a token name, not a colour."""

import pandas as pd
from PySide6.QtCore import Qt

from gui.orders_view import REPEAT_COLUMN
from gui.pandas_model import ROLE_STATUS, PandasModel


def _model(rows):
    return PandasModel(pd.DataFrame(rows))


def test_fulfillable_row_reports_status_success():
    model = _model([{"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"}])
    assert model.data(model.index(0, 0), ROLE_STATUS) == "status_success"


def test_not_fulfillable_row_reports_status_danger():
    model = _model(
        [{"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable"}]
    )
    assert model.data(model.index(0, 0), ROLE_STATUS) == "status_danger"


def test_a_repeat_order_reports_status_warning_and_beats_blocked():
    model = _model(
        [
            {
                "Order_Number": "1",
                "Order_Fulfillment_Status": "Not Fulfillable",
                REPEAT_COLUMN: True,
            }
        ]
    )
    assert model.data(model.index(0, 0), ROLE_STATUS) == "status_warning"


def test_the_lines_table_reads_repeat_straight_off_system_note():
    """order_lines() carries System_note and no _repeat column."""
    model = _model([{"SKU": "AAA", "System_note": "Repeat customer"}])
    assert model.data(model.index(0, 0), ROLE_STATUS) == "status_warning"


def test_a_row_with_neither_signal_reports_nothing():
    model = _model([{"Order_Number": "1"}])
    assert model.data(model.index(0, 0), ROLE_STATUS) is None


def test_the_model_no_longer_paints_rows():
    model = _model([{"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"}])
    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.BackgroundRole) is None
    assert model.data(index, Qt.ItemDataRole.ForegroundRole) is None


def test_a_theme_change_repaints_without_rebuilding_the_cache():
    model = _model([{"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"}])
    before = model._row_status_cache
    emitted = []
    model.dataChanged.connect(lambda *args: emitted.append(args))
    model._on_theme_changed()
    assert model._row_status_cache is before  # same object: not rebuilt
    assert emitted
