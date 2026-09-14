"""The detail pane's verbs on ActionsHandler (Bundle 13 spec §7.2)."""

import pandas as pd
import pytest


@pytest.fixture
def main_window(qapp, monkeypatch):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    monkeypatch.setattr(window, "save_session_state", lambda: None)
    window.undo_manager.reset_for_session()
    yield window
    window.close()


def _frame():
    return pd.DataFrame(
        [
            {
                "Order_Number": "1001",
                "Order_Fulfillment_Status": "Fulfillable",
                "SKU": "A",
                "Quantity": 1,
                "Final_Stock": 5,
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "1001",
                "Order_Fulfillment_Status": "Fulfillable",
                "SKU": "A",
                "Quantity": 2,
                "Final_Stock": 5,
                "Internal_Tags": "[]",
            },
            {
                "Order_Number": "1002",
                "Order_Fulfillment_Status": "Not Fulfillable",
                "SKU": "B",
                "Quantity": 1,
                "Final_Stock": 0,
                "Internal_Tags": '["vip"]',
            },
        ]
    )


def _tags(window, order):
    df = window.analysis_results_df
    return df.loc[df["Order_Number"] == order, "Internal_Tags"].tolist()


def test_set_order_fulfillable_toggles_only_when_the_status_differs(
    main_window, monkeypatch
):
    main_window.analysis_results_df = _frame()
    calls = []
    handler = main_window.actions_handler
    monkeypatch.setattr(handler, "toggle_fulfillment_status_for_order", calls.append)
    handler.set_order_fulfillable("1001", True)
    handler.set_order_fulfillable("1002", False)
    handler.set_order_fulfillable("9999", True)
    assert calls == []
    handler.set_order_fulfillable(" 1001 ", False)
    assert calls == [" 1001 "]


def test_remove_line_removes_the_indexed_one_of_two_same_sku_lines(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_line("1001", 1, "A")
    df = main_window.analysis_results_df
    assert df.loc[df["Order_Number"] == "1001", "Quantity"].tolist() == [1]


@pytest.mark.parametrize(("index", "sku"), [(2, "A"), (-1, "A"), (0, "B")])
def test_remove_line_refuses_a_line_that_moved(main_window, index, sku):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_line("1001", index, sku)
    assert len(main_window.analysis_results_df) == 3


def test_an_internal_tag_lands_on_every_line_and_undo_takes_it_back(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.add_internal_tag("1001", " rush ")
    assert all("rush" in t for t in _tags(main_window, "1001"))
    ok, _message = main_window.undo_manager.undo()
    assert ok
    assert all("rush" not in t for t in _tags(main_window, "1001"))


def test_removing_an_internal_tag(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_internal_tag("1002", "vip")
    assert "vip" not in _tags(main_window, "1002")[0]
    assert main_window.undo_manager.can_undo()


def test_a_blank_or_absent_tag_records_nothing(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.add_internal_tag("1001", "   ")
    main_window.actions_handler.remove_internal_tag("1001", "never-there")
    assert main_window.undo_manager.can_undo() is False
