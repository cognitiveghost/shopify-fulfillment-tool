"""Regression tests for gui.pandas_model.PandasModel's Lot_Details rendering.

Root cause: Lot_Details cells hold a raw list[dict] (or None), which fell
through to the generic scalar renderer. That renderer's `if pd.isna(value):`
raises ValueError for any list with 2+ elements (pd.isna returns an array,
not a scalar, for list input) -- a live crash for any order with 2+ lots
allocated to one SKU line.
"""
from datetime import date

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.pandas_model import PandasModel


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _model(lot_details_value):
    df = pd.DataFrame({"SKU": ["A1"], "Lot_Details": [lot_details_value]})
    return PandasModel(df)


def test_empty_lot_details_shows_blank_not_crash():
    model = _model(None)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == ""


def test_single_lot_shows_count_and_tooltip_detail():
    lots = [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0}]
    model = _model(lots)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "1 lot"
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "2026-12-30" in tooltip
    assert "B1" in tooltip


def test_multi_lot_cell_does_not_raise_and_shows_count():
    """Regression test for the pd.isna(list) ValueError crash."""
    lots = [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
    ]
    model = _model(lots)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "2 lots"  # must not raise
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "2026-12-30" in tooltip and "2027-01-01" in tooltip


def test_unparseable_expiry_shown_in_tooltip_not_hidden():
    lots = [{"expiry": "2805", "expiry_dt": None, "batch": None, "qty_allocated": 1.0}]
    model = _model(lots)
    index = model.index(0, 1)
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "unparsed" in tooltip and "2805" in tooltip


def test_plain_scalar_cell_still_renders_and_has_no_tooltip():
    df = pd.DataFrame({"SKU": ["A1"]})
    model = PandasModel(df)
    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "A1"
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None
