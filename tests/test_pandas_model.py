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

from gui.pandas_model import (
    FulfillmentFilterProxy,
    PandasModel,
    cell_display_text,
    cell_search_text,
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _model(lot_details_value):
    df = pd.DataFrame({"SKU": ["A1"], "Lot_Details": [lot_details_value]})
    return PandasModel(df)


def _lot_proxy(lots):
    """Proxy over a frame whose *last* column holds a lot list, as analysis emits it."""
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(PandasModel(pd.DataFrame({"SKU": ["A1"], "Lot_Details": [lots]})))
    return proxy


_TWO_LOTS = [
    {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
    {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
]


@pytest.mark.parametrize("empty", [None, [], float("nan")])
def test_empty_lot_details_shows_blank_and_no_tooltip(empty):
    model = _model(empty)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == ""
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None


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


def test_cell_display_text_renders_empty_and_missing_as_blank():
    assert cell_display_text(None) == ""
    assert cell_display_text([]) == ""
    assert cell_display_text(float("nan")) == ""


def test_cell_display_text_counts_lots_without_raising():
    """The list check must precede pd.isna(); see this module's docstring."""
    lots = [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
    ]
    assert cell_display_text(lots) == "2 lots"
    assert cell_display_text(lots[:1]) == "1 lot"
    assert cell_display_text("A1") == "A1"


def test_text_filter_over_a_multi_lot_row_does_not_raise():
    """Regression: pd.isna(list) raised inside filterAcceptsRow.

    The needle must match no earlier column, otherwise the column scan
    short-circuits before it ever reaches the list cell -- which is why this
    crash survived in production while ordinary searches looked fine.
    """
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("zzz")
    assert proxy.rowCount() == 0  # must not raise


def test_text_filter_matches_a_lot_cell_by_its_displayed_text():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("2 lots")
    assert proxy.rowCount() == 1


def test_text_filter_still_matches_plain_scalar_columns():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("a1")  # case-insensitive by default
    assert proxy.rowCount() == 1


def test_cell_search_text_exposes_batch_and_both_expiry_forms():
    """The haystack carries the raw stock-file expiry AND the parsed ISO date.

    Users read '261230' off the ERP but see '2026-12-30' in the tooltip; both
    must find the row. See the plan's Context section.
    """
    hay = cell_search_text(_TWO_LOTS)
    assert "B1" in hay             # batch
    assert "261230" in hay         # raw expiry, as typed from the ERP
    assert "2026-12-30" in hay     # parsed expiry, as shown in the tooltip
    assert "270101" in hay         # second lot, raw
    assert "2027-01-01" in hay     # second lot, parsed
    assert "2 lots" in hay         # display text is still part of the haystack


def test_cell_search_text_leaves_non_list_cells_identical_to_display_text():
    """Only list cells widen; every other column must behave exactly as before."""
    for value in ["A1", None, float("nan"), 5, []]:
        assert cell_search_text(value) == cell_display_text(value)


def test_text_filter_finds_a_row_by_batch_number():
    """The #285 regression, stated as the user sees it."""
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("B1")
    assert proxy.rowCount() == 1


def test_text_filter_finds_a_row_by_raw_and_iso_expiry():
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("261230")
    assert proxy.rowCount() == 1
    proxy.set_text_filter("2026-12-30")
    assert proxy.rowCount() == 1


def test_batch_search_works_on_the_second_lot_of_a_multi_lot_row():
    """Never worked at any revision: pre-#285 this raised, post-#285 it missed."""
    proxy = _lot_proxy(_TWO_LOTS)
    proxy.set_text_filter("2027-01-01")
    assert proxy.rowCount() == 1


def test_tag_filter_matches_an_unserialized_tag_list():
    """Internal_Tags is normally a JSON string, but tag_manager.py:78 and
    barcode_processor.py:82 both document that it is sometimes a native list.

    Two distinct bugs on that path: pd.isna(list) raises for 2+ elements, and
    str(["URGENT"]) is "['URGENT']" -- single quotes, so the double-quoted
    needle misses even when it doesn't raise. Hence json.dumps.
    """
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(
        PandasModel(pd.DataFrame({"SKU": ["A1"], "Internal_Tags": [["URGENT", "FRAGILE"]]}))
    )
    proxy.set_tag_filter("URGENT")
    assert proxy.rowCount() == 1  # must not raise, and must not filter the row out
    proxy.set_tag_filter("MISSING")
    assert proxy.rowCount() == 0


def test_tag_filter_matches_the_normal_json_string_form():
    """The list branch above is the rare one; analysis.py writes a JSON string."""
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(
        PandasModel(pd.DataFrame({"SKU": ["A1"], "Internal_Tags": ['["URGENT", "FRAGILE"]']}))
    )
    proxy.set_tag_filter("URGENT")
    assert proxy.rowCount() == 1
    proxy.set_tag_filter("MISSING")
    assert proxy.rowCount() == 0



def test_all_columns_search_ignores_the_derived_repeat_column():
    """8.8b added a hidden bool column; "all columns" must not match through it.

    cell_search_text(True) renders "True", so before this guard a needle of
    "f", "al", "true" -- the first keystrokes of most real searches -- matched
    every row through a column the user cannot see, and the table stopped
    narrowing. _search_text is derived too, but exists to be searched.
    """
    from gui.pandas_model import REPEAT_COLUMN

    df = pd.DataFrame({"SKU": ["A1", "B2"], REPEAT_COLUMN: [True, False]})
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(PandasModel(df))

    for needle in ("false", "true", "als", "ru"):
        proxy.set_text_filter(needle)
        assert proxy.rowCount() == 0, f"{needle!r} matched through {REPEAT_COLUMN}"

    proxy.set_text_filter("a1")  # a real column still matches
    assert proxy.rowCount() == 1
