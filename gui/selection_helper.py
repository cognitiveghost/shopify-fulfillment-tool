"""Selection helper utilities for bulk operations.

This module provides the SelectionHelper class that manages table selection
and checkbox state for bulk operations on the Analysis Results table.
"""

from typing import List, Tuple, Set
import pandas as pd


class SelectionHelper:
    """Manages table selection and checkbox state for bulk operations.

    This class tracks which rows are "checked" (selected for bulk operations)
    independently from Qt's native row selection. The checked state is stored
    as a set of source DataFrame indexes.

    Attributes:
        table_view: Reference to the QTableView widget
        proxy_model: Reference to the QSortFilterProxyModel
        main_window: Reference to the MainWindow instance
        checked_rows: Set of source DataFrame indexes that are checked
    """

    def __init__(self, table_view, proxy_model, main_window):
        """Initialize SelectionHelper.

        Args:
            table_view: QTableView widget (can be None, set later)
            proxy_model: QSortFilterProxyModel for the table
            main_window: MainWindow instance containing analysis_results_df
        """
        self.table_view = table_view
        self.proxy_model = proxy_model
        self.main_window = main_window
        self.checked_rows: Set[int] = set()  # Set of source DataFrame indexes

    def get_selected_source_rows(self) -> List[int]:
        """Get list of source DataFrame indexes for checked rows.

        Returns:
            List of integer indexes in analysis_results_df, sorted ascending
        """
        return sorted(list(self.checked_rows))

    def get_selected_orders_data(self) -> pd.DataFrame:
        """Get DataFrame slice of selected rows.

        Returns:
            DataFrame containing only checked rows, or empty DataFrame if none
        """
        if not self.checked_rows:
            return pd.DataFrame()

        df = self.main_window.analysis_results_df
        if df is None or df.empty:
            return pd.DataFrame()

        # Get only indexes that exist in the DataFrame
        valid_indexes = [idx for idx in self.checked_rows if idx in df.index]
        if not valid_indexes:
            return pd.DataFrame()

        return df.loc[valid_indexes].copy()

    def get_selection_summary(self) -> Tuple[int, int]:
        """Get summary of selected items.

        Returns:
            Tuple of (unique_orders_count, total_items_count)
        """
        if not self.checked_rows:
            return (0, 0)

        selected_df = self.get_selected_orders_data()
        if selected_df.empty:
            return (0, 0)

        unique_orders = selected_df['Order_Number'].nunique()
        # Sum quantities instead of counting rows
        total_items = int(selected_df['Quantity'].sum()) if 'Quantity' in selected_df.columns else len(selected_df)

        return (unique_orders, total_items)

    def toggle_row(self, source_row_index: int):
        """Toggle checkbox state for an order (all rows with same Order_Number).

        When a row is toggled, all rows belonging to the same order are
        toggled together. This ensures bulk operations work at the order level.

        Args:
            source_row_index: Index in the source DataFrame (not proxy)
        """
        df = self.main_window.analysis_results_df
        if df is None or df.empty or source_row_index not in df.index:
            # Fallback to single row toggle if no DataFrame
            if source_row_index in self.checked_rows:
                self.checked_rows.remove(source_row_index)
            else:
                self.checked_rows.add(source_row_index)
            return

        # Get the Order_Number for the clicked row
        order_number = df.loc[source_row_index, 'Order_Number']

        # Find all rows with the same Order_Number
        order_rows = df[df['Order_Number'] == order_number].index.tolist()

        # Check if any row of this order is currently checked
        is_order_checked = any(row in self.checked_rows for row in order_rows)

        # Toggle all rows of this order
        if is_order_checked:
            # Uncheck all rows of this order
            for row in order_rows:
                self.checked_rows.discard(row)
        else:
            # Check all rows of this order
            for row in order_rows:
                self.checked_rows.add(row)

    def select_all(self):
        """Check all visible rows (respecting current filter), expanded to
        every row of the same order.

        A filter can hide some line items of a multi-item order (e.g. a SKU
        search). Checking only the visible rows would let a bulk action write
        a new status/tag to part of an order while leaving its hidden
        sibling rows on the old value. Every row sharing an Order_Number with
        a visible row is checked too, mirroring toggle_row()'s expansion.
        """
        self.checked_rows.clear()

        if self.proxy_model is None:
            return

        visible_rows = set()
        for proxy_row in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(proxy_row, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            visible_rows.add(source_index.row())

        df = self.main_window.analysis_results_df
        if df is None or df.empty or "Order_Number" not in df.columns:
            self.checked_rows = visible_rows
            return

        visible_indexes = [row for row in visible_rows if row in df.index]
        visible_orders = df.loc[visible_indexes, "Order_Number"].unique()
        self.checked_rows = set(df[df["Order_Number"].isin(visible_orders)].index)

    def clear_selection(self):
        """Uncheck all rows."""
        self.checked_rows.clear()

    def is_row_checked(self, source_row_index: int) -> bool:
        """Check if row is checked.

        Args:
            source_row_index: Index in the source DataFrame (not proxy)

        Returns:
            True if the row is checked, False otherwise
        """
        return source_row_index in self.checked_rows

    def set_table_view(self, table_view):
        """Set the table view reference.

        Args:
            table_view: QTableView widget
        """
        self.table_view = table_view

    def get_checked_count(self) -> int:
        """Get the number of checked rows.

        Returns:
            Number of checked rows
        """
        return len(self.checked_rows)

    def has_selection(self) -> bool:
        """Check if any rows are selected.

        Returns:
            True if at least one row is checked
        """
        return len(self.checked_rows) > 0
