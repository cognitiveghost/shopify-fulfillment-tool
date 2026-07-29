"""Regression tests for order-level Internal_Tags consistency in MainWindow.

Internal_Tags is order-level (see shopify_tool.tag_manager.expand_to_order_rows),
but several write/read paths in MainWindow used to operate on a single row
(the clicked SKU line, or whichever line happened to be table-selected)
instead of the whole order. These tests cover the fixed behavior.

Uses a SimpleNamespace fake with the real MainWindow methods bound onto it
(types.MethodType), matching this codebase's established pattern of never
instantiating the real MainWindow in tests (see test_selection_helper.py's
_FakeMainWindow, test_actions_handler.py's SimpleNamespace fixture).
"""
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from gui.main_window_pyside import MainWindow


@pytest.fixture
def mw():
    fake = SimpleNamespace(
        analysis_results_df=pd.DataFrame(
            [
                {"Order_Number": "1001", "SKU": "A1", "Internal_Tags": "[]"},
                {"Order_Number": "1001", "SKU": "A2", "Internal_Tags": "[]"},
                {"Order_Number": "1002", "SKU": "B1", "Internal_Tags": "[]"},
            ]
        ),
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
    )
    fake._apply_tag_operation = types.MethodType(MainWindow._apply_tag_operation, fake)
    fake._add_internal_tag = types.MethodType(MainWindow._add_internal_tag, fake)
    return fake


def test_add_internal_tag_from_right_click_tags_every_line_of_the_order(mw):
    mw._add_internal_tag("1001", "A1", "GIFT")

    tags = mw.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert '"GIFT"' in tags.loc["A1"]  # the clicked line
    assert '"GIFT"' in tags.loc["A2"]  # the order's other line -- must ALSO be tagged
    assert '"GIFT"' not in tags.loc["B1"]  # different order, untouched
