"""Selection helper utilities for bulk operations.

This module provides the SelectionHelper class that manages table selection
and checkbox state for bulk operations on the Analysis Results table.
"""


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
        checked_rows: Set of analysis_results_df index labels for the lines of
            the selected orders.
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
        self.checked_rows: set[int] = set()  # Set of source DataFrame indexes

    def get_selected_source_rows(self) -> list[int]:
        """Get list of source DataFrame indexes for checked rows.

        Returns:
            List of integer indexes in analysis_results_df, sorted ascending
        """
        return sorted(self.checked_rows)

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

    def get_selection_summary(self) -> tuple[int, int]:
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

    def set_selected_orders(self, order_numbers) -> None:
        """Check exactly the line rows belonging to ``order_numbers``.

        Replaces the previous selection rather than adding to it: the table's
        own selection is now the whole truth, so there is nothing to merge with.

        ``checked_rows`` holds DataFrame index *labels*, matching
        ``get_selected_orders_data``'s ``df.loc[...]``. The old line-level
        toggle mixed labels with view row positions, which only agreed while
        the frame happened to have a contiguous index.
        """
        self.checked_rows = set()

        wanted = set(order_numbers)
        if not wanted:
            return

        df = self.main_window.analysis_results_df
        if df is None or df.empty or "Order_Number" not in df.columns:
            return

        self.checked_rows = set(df.index[df["Order_Number"].isin(wanted)])

    def clear_selection(self):
        """Uncheck all rows."""
        self.checked_rows.clear()

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
