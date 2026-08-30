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
import json
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

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
    fake._pane_lines = types.MethodType(MainWindow._pane_lines, fake)
    return fake


def test_selecting_a_row_shows_the_orders_tags_in_the_pane(mw):
    """Internal_Tags is now an order-level column (Phase 8.8a): every line of
    an order carries the same value by construction (writes always go through
    expand_to_order_rows / an Order_Number mask), so the order frame's
    orders_frame() folds it with .first() rather than merging across lines."""
    from gui.orders_view import orders_frame

    mw.on_results_selection_changed = types.MethodType(
        MainWindow.on_results_selection_changed, mw
    )
    mw.analysis_results_df["Internal_Tags"] = '["A"]'
    mw.orders_df = orders_frame(mw.analysis_results_df)

    mw.selection_helper = Mock()
    mw.order_detail_pane = MagicMock()
    mw._update_selection_bar_state = Mock()

    # Select order 1001's row (row 0 of the order frame) in the table
    fake_index = MagicMock()
    fake_index.row.return_value = 0
    fake_index.isValid.return_value = True
    mw.proxy_model = MagicMock()
    mw.proxy_model.mapToSource.return_value = fake_index
    mw.tableView = MagicMock()
    mw.tableView.selectionModel.return_value.selectedRows.return_value = [MagicMock()]
    mw.tableView.selectionModel.return_value.currentIndex.return_value = fake_index

    mw.on_results_selection_changed()

    order_number, order_row, lines = mw.order_detail_pane.set_order.call_args[0]
    assert order_number == "1001"
    assert json.loads(order_row["Internal_Tags"]) == ["A"]
    assert list(lines["SKU"]) == ["A1", "A2"]
