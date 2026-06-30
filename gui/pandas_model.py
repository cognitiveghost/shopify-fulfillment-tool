from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, QModelIndex
from PySide6.QtGui import QColor
import pandas as pd
from gui.theme_manager import get_theme_manager


class FulfillmentFilterProxy(QSortFilterProxyModel):
    """Proxy that combines a plain-substring text filter with a tag filter.

    Replaces the default ``setFilterRegularExpression`` behaviour, which
    treated raw user input as a regex (so typing ``(``, ``+`` or ``[`` broke
    the filter or silently hid every row). Matching is plain substring on the
    cell's display text, and the text and tag filters are ANDed together
    instead of being mutually exclusive.

    Columns are addressed by *DataFrame* index (``-1`` = all columns); the
    proxy reads the source ``PandasModel``'s frame directly via ``iat``, so it
    is unaffected by the checkbox column offset present in bulk mode.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df_col = -1  # -1 = search all columns
        self._case_sensitive = False
        self._needle = ""  # text filter, pre-folded to match case sensitivity
        self._tag_needle = None  # tag filter as quoted JSON token, e.g. '"URGENT"'

    def set_text_filter(self, text, df_col=-1, case_sensitive=False):
        text = text or ""
        self._df_col = df_col
        self._case_sensitive = case_sensitive
        self._needle = text if case_sensitive else text.casefold()
        self.invalidateFilter()

    def set_tag_filter(self, tag):
        self._tag_needle = f'"{tag}"' if tag else None
        self.invalidateFilter()

    def clear_filters(self):
        self._df_col = -1
        self._needle = ""
        self._tag_needle = None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        df = getattr(model, "_dataframe", None) if model is not None else None
        if df is None:
            return True

        # Tag filter: Internal_Tags stores tags as a JSON array, so a quoted
        # match ("URGENT") avoids matching substrings of other tag names.
        if self._tag_needle:
            if "Internal_Tags" not in df.columns:
                return False
            val = df.iat[source_row, df.columns.get_loc("Internal_Tags")]
            if self._tag_needle not in ("" if pd.isna(val) else str(val)):
                return False

        if not self._needle:
            return True

        if self._df_col < 0:
            col_indices = range(len(df.columns))
        elif self._df_col < len(df.columns):
            col_indices = (self._df_col,)
        else:
            return True  # stale column index after a data reload

        fold = (lambda s: s) if self._case_sensitive else str.casefold
        for c in col_indices:
            cell = df.iat[source_row, c]
            hay = "" if pd.isna(cell) else str(cell)
            if self._needle in fold(hay):
                return True
        return False


class PandasModel(QAbstractTableModel):
    """A Qt model to interface a pandas DataFrame with a QTableView.

    This class acts as a wrapper around a pandas DataFrame, allowing it to be
    displayed and manipulated in a Qt view (like QTableView) while adhering to
    the Qt Model/View programming paradigm.

    It handles data retrieval, header information, and custom styling (e.g.,
    row colors) based on the DataFrame's content.

    Attributes:
        _dataframe (pd.DataFrame): The underlying pandas DataFrame.
        colors (dict): A mapping of status strings to QColor objects for row
                       styling.
        enable_checkboxes (bool): Whether to show checkbox column for bulk operations.
    """

    def __init__(self, dataframe: pd.DataFrame, parent=None, enable_checkboxes: bool = False):
        """Initializes the PandasModel.

        Args:
            dataframe (pd.DataFrame): The pandas DataFrame to be modeled.
            parent (QObject, optional): The parent object. Defaults to None.
            enable_checkboxes (bool): Whether to add a checkbox column at position 0.
        """
        super().__init__(parent)
        self._dataframe = dataframe
        self.enable_checkboxes = enable_checkboxes

        # Initialize colors based on current theme
        self._update_colors()

        # Pre-compute per-row color caches to avoid repeated column lookups in data()
        self._build_row_color_cache()

        # Connect to theme changes
        theme_manager = get_theme_manager()
        theme_manager.theme_changed.connect(self._update_colors)

    def rowCount(self, parent=QModelIndex()) -> int:
        """Returns the number of rows in the model."""
        if parent.isValid():
            return 0
        return len(self._dataframe)

    def columnCount(self, parent=QModelIndex()) -> int:
        """Returns the number of columns in the model."""
        if parent.isValid():
            return 0
        # Add 1 for checkbox column if enabled
        if self.enable_checkboxes:
            return len(self._dataframe.columns) + 1
        return len(self._dataframe.columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        """Returns the data for a given model index and role.

        This method is called by the view to get the data to display. It
        handles:
        - `DisplayRole`: The text to be displayed in a cell.
        - `BackgroundRole`: The background color of a row, based on the
          'System_note' or 'Order_Fulfillment_Status' columns.

        Args:
            index (QModelIndex): The index of the item to retrieve data for.
            role (Qt.ItemDataRole): The role for which to retrieve data.

        Returns:
            Any: The data for the given role, or None if not applicable.
        """
        if not index.isValid():
            return None

        row = index.row()

        # Handle checkbox column (column 0 when checkboxes enabled)
        # Checkbox rendering is handled by CheckboxDelegate
        if self.enable_checkboxes and index.column() == 0:
            return None

        # Adjust column index if checkboxes enabled
        col_index = index.column()
        if self.enable_checkboxes:
            col_index = index.column() - 1

        if role == Qt.ItemDataRole.DisplayRole:
            try:
                value = self._dataframe.iloc[row, col_index]
                if pd.isna(value):
                    return ""
                return str(value)
            except IndexError:
                return None

        if role == Qt.ItemDataRole.BackgroundRole:
            return self._row_bg_cache[row]

        if role == Qt.ItemDataRole.ForegroundRole:
            return self._row_fg_cache[row]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        """Returns the header data for the given section and orientation.

        Args:
            section (int): The row or column number.
            orientation (Qt.Orientation): The header orientation (Horizontal
                or Vertical).
            role (Qt.ItemDataRole): The role for which to retrieve data.

        Returns:
            str | None: The header title, or None.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                # Handle checkbox column header
                if self.enable_checkboxes:
                    if section == 0:
                        return ""  # Checkbox column header (empty or could be "")
                    return str(self._dataframe.columns[section - 1])
                return str(self._dataframe.columns[section])
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)
        return None

    def get_column_index(self, column_name):
        """Returns the numerical index of a column from its string name.

        Args:
            column_name (str): The name of the column.

        Returns:
            int | None: The index of the column, or None if not found.
        """
        try:
            df_index = self._dataframe.columns.get_loc(column_name)
            # Adjust for checkbox column if enabled
            if self.enable_checkboxes:
                return df_index + 1
            return df_index
        except KeyError:
            return None

    def set_column_order_and_visibility(self, all_columns_in_order, visible_columns):
        """Reorders and filters columns in the underlying DataFrame.

        Note: This method seems to be obsolete or not fully implemented, as
        column visibility is now handled by the view/proxy.

        Args:
            all_columns_in_order (list[str]): A list of all column names in
                the desired order.
            visible_columns (list[str]): A list of columns that should remain
                visible.
        """
        self.beginResetModel()
        existing_columns = [col for col in all_columns_in_order if col in self._dataframe.columns]
        self._dataframe = self._dataframe[existing_columns]
        self.hidden_columns = [col for col in all_columns_in_order if col not in visible_columns]
        self.endResetModel()

    def _build_row_color_cache(self):
        """Pre-compute background/foreground color for each row.

        Called once at init and after theme changes. Avoids per-cell column
        lookups in data() which were causing scroll lag on large DataFrames.

        Assumption: the underlying DataFrame is treated as immutable after
        the model is created. If row data changes in-place (status or note
        updated without recreating the model), call _build_row_color_cache()
        manually afterwards so the cache stays in sync.
        """
        n = len(self._dataframe)
        bg = [None] * n
        fg = [None] * n

        has_system_note = "System_note" in self._dataframe.columns
        has_status = "Order_Fulfillment_Status" in self._dataframe.columns

        # Pre-compute column indices so the hot loop uses iat (scalar, ~5-10x faster than iloc[i]["col"])
        sn_col = self._dataframe.columns.get_loc("System_note") if has_system_note else -1
        st_col = self._dataframe.columns.get_loc("Order_Fulfillment_Status") if has_status else -1

        for i in range(n):
            try:
                if has_system_note:
                    sn_val = self._dataframe.iat[i, sn_col]
                    if pd.notna(sn_val):
                        sn = str(sn_val)
                        if "Repeat" in sn and not sn.startswith("Cannot fulfill"):
                            bg[i] = self.colors["SystemNoteHighlight"]
                            fg[i] = self.text_colors["SystemNoteHighlight"]
                            continue

                if has_status:
                    status = self._dataframe.iat[i, st_col]
                    if status == "Fulfillable":
                        bg[i] = self.colors["Fulfillable"]
                        fg[i] = self.text_colors["Fulfillable"]
                    elif status == "Not Fulfillable":
                        bg[i] = self.colors["NotFulfillable"]
                        fg[i] = self.text_colors["NotFulfillable"]
            except (IndexError, KeyError):
                pass

        self._row_bg_cache = bg
        self._row_fg_cache = fg

    def _update_colors(self):
        """Update row colors based on current theme.

        Sets background and text colors for table rows based on fulfillment status.
        Uses different color palettes for light and dark themes to maintain contrast.
        """
        theme_manager = get_theme_manager()

        if theme_manager.is_dark_theme():
            # Dark theme: dark tinted backgrounds with white text
            self.colors = {
                "Fulfillable": QColor("#1B3A1B"),          # Dark green tint
                "NotFulfillable": QColor("#3A1B1B"),       # Dark red tint
                "SystemNoteHighlight": QColor("#3A3020"),  # Dark orange tint
            }
            self.text_colors = {
                "Fulfillable": QColor("#FFFFFF"),          # White text
                "NotFulfillable": QColor("#FFFFFF"),       # White text
                "SystemNoteHighlight": QColor("#FFFFFF"),  # White text
            }
        else:
            # Light theme: brighter tinted backgrounds with dark text (more visible)
            self.colors = {
                "Fulfillable": QColor("#C8E6C9"),          # Brighter green tint (was #E8F5E9)
                "NotFulfillable": QColor("#FFCDD2"),       # Brighter red tint (was #FFEBEE)
                "SystemNoteHighlight": QColor("#FFE0B2"),  # Brighter orange tint (was #FFF3E0)
            }
            self.text_colors = {
                "Fulfillable": QColor("#1B5E20"),          # Darker green text for contrast
                "NotFulfillable": QColor("#B71C1C"),       # Darker red text for contrast
                "SystemNoteHighlight": QColor("#E65100"),  # Darker orange text for contrast
            }

        # Rebuild per-row cache with new colors (if data already loaded)
        if hasattr(self, '_row_bg_cache'):
            self._build_row_color_cache()

        # Notify views that data has changed (triggers repaint)
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole, Qt.ForegroundRole])
