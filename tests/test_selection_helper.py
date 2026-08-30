"""Bulk-selection order-completeness (user-reported bug, fixed: bulk status
change via a filtered "Select All" used to only touch the visible/matching
rows, not every row of the orders they belong to -- leaving
Order_Fulfillment_Status inconsistent across an order's own line items)."""
import pandas as pd
import pytest

from gui.selection_helper import SelectionHelper


class _FakeMainWindow:
    def __init__(self, df):
        self.analysis_results_df = df


def _multi_item_orders_df():
    return pd.DataFrame([
        {"Order_Number": "#1", "SKU": "A1", "Quantity": 2, "Order_Fulfillment_Status": "Fulfillable"},
        {"Order_Number": "#1", "SKU": "B1", "Quantity": 1, "Order_Fulfillment_Status": "Fulfillable"},
        {"Order_Number": "#2", "SKU": "A1", "Quantity": 3, "Order_Fulfillment_Status": "Fulfillable"},
    ])


@pytest.fixture
def helper_with_df():
    """SelectionHelper over a 2-order / 5-line frame with a non-contiguous index.

    The gapped index is deliberate: bulk_delete_orders drops rows, so
    analysis_results_df is not guaranteed to be a RangeIndex, and checked_rows
    holds index *labels*.
    """
    df = pd.DataFrame(
        {
            "Order_Number": ["1001", "1001", "1002", "1002", "1002"],
            "Quantity": [2, 1, 5, 1, 1],
        },
        index=[0, 1, 4, 5, 9],
    )

    class _MainWindow:
        analysis_results_df = df

    return SelectionHelper(table_view=None, proxy_model=None, main_window=_MainWindow())


def test_set_selected_orders_checks_every_line_of_each_order(helper_with_df):
    """Spec §10 test 7."""
    helper = helper_with_df
    df = helper.main_window.analysis_results_df

    helper.set_selected_orders(["1001"])

    expected = set(df.index[df["Order_Number"] == "1001"])
    assert helper.checked_rows == expected
    assert set(helper.get_selected_orders_data()["Order_Number"]) == {"1001"}


def test_set_selected_orders_replaces_rather_than_adds(helper_with_df):
    helper = helper_with_df
    helper.set_selected_orders(["1001"])
    helper.set_selected_orders(["1002"])
    assert set(helper.get_selected_orders_data()["Order_Number"]) == {"1002"}


def test_selection_summary_unchanged_for_the_same_orders(helper_with_df):
    """Spec §10 test 8: the summary is what the bulk toolbar prints."""
    helper = helper_with_df
    df = helper.main_window.analysis_results_df

    helper.set_selected_orders(["1001", "1002"])
    orders, items = helper.get_selection_summary()

    subset = df[df["Order_Number"].isin(["1001", "1002"])]
    assert orders == subset["Order_Number"].nunique()
    assert items == int(subset["Quantity"].sum())


def test_set_selected_orders_with_empty_iterable_clears(helper_with_df):
    helper = helper_with_df
    helper.set_selected_orders(["1001"])
    helper.set_selected_orders([])
    assert helper.checked_rows == set()


def test_toggle_row_is_gone():
    """The line-level toggle was the workaround; it must not survive."""
    from gui.selection_helper import SelectionHelper

    assert not hasattr(SelectionHelper, "toggle_row")
    assert not hasattr(SelectionHelper, "is_row_checked")
