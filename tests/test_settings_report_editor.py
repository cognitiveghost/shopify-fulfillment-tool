"""A report's editor says how many orders its filters match while they are written."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings import report_editor
from gui.settings.report_editor import (
    PACKING_LISTS,
    STOCK_EXPORTS,
    ReportEditor,
    match_text,
)

ANALYSIS = pd.DataFrame(
    {
        "Order_Number": ["1", "1", "2", "3"],
        "SKU": ["A", "B", "A", "C"],
        "Order_Fulfillment_Status": [
            "Fulfillable",
            "Fulfillable",
            "Fulfillable",
            "Not Fulfillable",
        ],
    }
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_match_text_copy():
    assert (
        match_text(None)
        == "Run an analysis to see how many orders this report matches."
    )
    assert match_text((0, 0)) == "Matches no orders. Check the filters."
    assert match_text((1, 1)) == "Matches 1 order · 1 row"
    assert match_text((148, 372)) == "Matches 148 orders · 372 rows"


def test_the_editor_counts_matches_when_it_opens():
    config = {
        "name": "a",
        "filters": [{"field": "SKU", "operator": "contains", "value": "A"}],
    }
    editor = ReportEditor(PACKING_LISTS, config, ANALYSIS)
    assert editor.match_label.text() == "Matches 2 orders · 2 rows"


def test_the_count_follows_a_filter_edit():
    config = {
        "name": "a",
        "filters": [{"field": "SKU", "operator": "contains", "value": "A"}],
    }
    editor = ReportEditor(PACKING_LISTS, config, ANALYSIS)

    editor.filters[0]["value_widget"].setText(
        "C"
    )  # C is only on an unfulfillable order
    assert editor._match_timer.isActive()
    editor.refresh_match_count()

    assert editor.match_label.text() == "Matches no orders. Check the filters."


def test_without_an_analysis_the_editor_says_how_to_get_a_count():
    editor = ReportEditor(STOCK_EXPORTS, {}, None)
    assert (
        editor.match_label.text()
        == "Run an analysis to see how many orders this report matches."
    )


def test_editors_share_one_match_cache(monkeypatch):
    calls = []
    real = report_editor.count_matches
    monkeypatch.setattr(
        "gui.settings.report_editor.count_matches",
        lambda df, filters: calls.append(1) or real(df, filters),
    )
    config = {
        "name": "a",
        "filters": [{"field": "SKU", "operator": "contains", "value": "A"}],
    }
    cache = {}

    ReportEditor(PACKING_LISTS, config, ANALYSIS, match_cache=cache)
    ReportEditor(PACKING_LISTS, config, ANALYSIS, match_cache=cache)

    assert len(calls) == 1


def test_a_filter_that_cannot_be_counted_says_so(monkeypatch):
    def boom(df, filters):
        raise ValueError("bad regex")

    monkeypatch.setattr("gui.settings.report_editor.count_matches", boom)
    editor = ReportEditor(PACKING_LISTS, {"filters": []}, ANALYSIS)
    assert editor.match_label.text() == "Can't count matches for these filters."
