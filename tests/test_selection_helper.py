"""Bulk-selection order-completeness (user-reported bug, fixed: bulk status
change via a filtered "Select All" used to only touch the visible/matching
rows, not every row of the orders they belong to -- leaving
Order_Fulfillment_Status inconsistent across an order's own line items)."""
import pandas as pd
import pytest

from gui.pandas_model import FulfillmentFilterProxy, PandasModel
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
def proxy_filtered_to_sku_a1(qtbot):
    df = _multi_item_orders_df()
    model = PandasModel(df)
    proxy = FulfillmentFilterProxy()
    proxy.setSourceModel(model)
    sku_col = df.columns.get_loc("SKU")
    proxy.set_text_filter("A1", df_col=sku_col)
    return df, proxy


class TestToggleRowExpandsToWholeOrder:
    def test_toggle_row_checks_every_row_of_the_order(self, qtbot):
        df = _multi_item_orders_df()
        helper = SelectionHelper(None, None, _FakeMainWindow(df))
        # Row 0 is order #1's A1 line; toggling it must also check row 1 (order
        # #1's B1 line), even though only row 0 was clicked.
        helper.toggle_row(0)
        assert helper.checked_rows == {0, 1}


class TestSelectAllConfirmedBug:
    def test_select_all_under_filter_still_covers_whole_orders(self, proxy_filtered_to_sku_a1):
        df, proxy = proxy_filtered_to_sku_a1
        # Sanity: the filter really did hide order #1's B1 row.
        assert proxy.rowCount() == 2  # only the two A1 rows (order #1 and #2)

        helper = SelectionHelper(None, proxy, _FakeMainWindow(df))
        helper.select_all()

        # Order #1 has two line items (A1 + B1); selecting "all" under a SKU
        # filter should still select the WHOLE order, not just the row that
        # happened to match the filter. Order #2's single A1 row stays too.
        assert helper.checked_rows == {0, 1, 2}
