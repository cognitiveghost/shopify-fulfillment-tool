import json

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from gui.theme_manager import get_theme_manager

# The row's status as a theme role token name -- resolved against the live
# theme by StatusEdgeDelegate, not here. Qt.UserRole is unused on this model
# and TagDelegate reads none; +20 leaves room for both.
ROLE_STATUS = Qt.ItemDataRole.UserRole + 20


class FulfillmentFilterProxy(QSortFilterProxyModel):
    """Proxy that combines a plain-substring text filter with a tag filter.

    Replaces the default ``setFilterRegularExpression`` behaviour, which
    treated raw user input as a regex (so typing ``(``, ``+`` or ``[`` broke
    the filter or silently hid every row). Matching is plain substring on the
    cell's search text (see :func:`cell_search_text` — the display text, widened
    for lot cells so batch numbers and expiry dates stay findable), and the text
    and tag filters are ANDed together instead of being mutually exclusive.

    Columns are addressed by *DataFrame* index (``-1`` = all columns); the
    proxy reads the source ``PandasModel``'s frame directly via ``iat``, so it
    addresses the source frame's own column positions.
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
            if isinstance(val, list):
                # Internal_Tags is normally a JSON string, but is sometimes stored
                # unserialized (tag_manager.py:78, barcode_processor.py:82). json.dumps,
                # not str(): repr uses single quotes, so the double-quoted needle misses.
                # default=str: tag_manager returns the list verbatim, so a
                # non-string element would otherwise raise across the Qt boundary.
                hay = json.dumps(val, default=str)
            else:
                hay = "" if pd.isna(val) else str(val)
            if self._tag_needle not in hay:
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
            hay = cell_search_text(cell)
            if self._needle in fold(hay):
                return True
        return False


def _format_lot(lot: dict) -> str:
    """Render one Lot_Details entry as a human-readable line for the tooltip."""
    qty = lot.get("qty_allocated", lot.get("qty", 0))
    qty_str = f"{qty:g}" if isinstance(qty, float) else str(qty)
    expiry_dt = lot.get("expiry_dt")
    expiry_str = f"exp {expiry_dt.isoformat()}" if expiry_dt is not None else f"exp unparsed ({lot.get('expiry')!r})"
    batch = lot.get("batch")
    batch_str = f", Batch {batch}" if batch else ""
    return f"{qty_str}x, {expiry_str}{batch_str}"


# The order-frame column carrying "does any line of this order read as a
# repeat?". Named here rather than in orders_view because the status cache
# below reads it and orders_view already imports from this module -- the
# reverse import would make the two circular.
REPEAT_COLUMN = "_repeat"


def is_repeat(note) -> bool:
    """The row tint's own test: mentions a repeat, and is not purely a blocker.

    A compound note ("Repeat customer; Cannot fulfill: ...") is both, and the
    tint showed it amber rather than red -- its "Repeat" branch `continue`d
    before the status branch was reached. Preserved deliberately, not chosen.
    """
    if note is None or (isinstance(note, float) and pd.isna(note)):
        return False
    text = str(note)
    return "Repeat" in text and not text.startswith("Cannot fulfill")


def cell_display_text(value) -> str:
    """Render one DataFrame cell as the text the user sees in a table.

    The list check MUST come before ``pd.isna()``: ``Lot_Details`` holds real
    Python lists, and ``pd.isna()`` on a list returns an *array*, so a plain
    ``if`` on it raises "truth value of an array is ambiguous". Every caller
    that renders cell text must go through here, and every caller that
    searches it through :func:`cell_search_text` (which delegates here) — a
    private copy is how that crash got reintroduced in the filter proxy.

    Note the wording is column-agnostic: *any* list-valued cell renders as
    "N lots". ``Lot_Details`` is the only such column today.
    """
    if isinstance(value, list):
        if not value:
            return ""
        return f"{len(value)} lot{'s' if len(value) != 1 else ''}"
    if pd.isna(value):
        return ""
    return str(value)


def cell_search_text(value) -> str:
    """Render one DataFrame cell as the text the *search filter* matches against.

    Deliberately wider than :func:`cell_display_text`: a ``Lot_Details`` cell
    displays as "2 lots", but users search it by batch number or expiry date.
    The haystack is the display text, plus each lot's tooltip line, plus each
    lot's raw ``expiry`` string.

    Both expiry forms are included on purpose. ``expiry`` is the raw stock-file
    string ("261230") that a user reads off the ERP; ``_format_lot`` renders the
    parsed ISO date ("2026-12-30") that the tooltip shows. They are different
    strings and either is a reasonable thing to type.

    Non-list cells return ``cell_display_text(value)`` unchanged, so no other
    column's filtering behaviour changes.
    """
    text = cell_display_text(value)
    if not isinstance(value, list) or not value:
        return text
    parts = [text]
    for lot in value:
        if not isinstance(lot, dict):
            parts.append(str(lot))
            continue
        parts.append(_format_lot(lot))
        raw = lot.get("expiry")
        if raw:
            parts.append(str(raw))
    return "\n".join(parts)


class PandasModel(QAbstractTableModel):
    """A Qt model to interface a pandas DataFrame with a QTableView.

    This class acts as a wrapper around a pandas DataFrame, allowing it to be
    displayed and manipulated in a Qt view (like QTableView) while adhering to
    the Qt Model/View programming paradigm.

    It handles data retrieval, header information, and a per-row status token
    (ROLE_STATUS) that StatusEdgeDelegate resolves against the live theme.

    Attributes:
        _dataframe (pd.DataFrame): The underlying pandas DataFrame.
    """

    def __init__(self, dataframe: pd.DataFrame, parent=None):
        """Initializes the PandasModel.

        Args:
            dataframe (pd.DataFrame): The pandas DataFrame to be modeled.
            parent (QObject, optional): The parent object. Defaults to None.
        """
        super().__init__(parent)
        self._dataframe = dataframe

        # Pre-compute per-row status token cache to avoid repeated column lookups in data()
        self._build_row_status_cache()

        # Connect to theme changes
        theme_manager = get_theme_manager()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def rowCount(self, parent=QModelIndex()) -> int:
        """Returns the number of rows in the model."""
        if parent.isValid():
            return 0
        return len(self._dataframe)

    def columnCount(self, parent=QModelIndex()) -> int:
        """Returns the number of columns in the model."""
        if parent.isValid():
            return 0
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
        col_index = index.column()

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            try:
                value = self._dataframe.iloc[row, col_index]
            except IndexError:
                return None

            if role == Qt.ItemDataRole.ToolTipRole:
                if isinstance(value, list) and value:
                    return "\n".join(_format_lot(lot) for lot in value)
                return None  # no tooltip for empty or plain scalar cells

            return cell_display_text(value)

        if role == ROLE_STATUS:
            return self._row_status_cache[row]

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
            return self._dataframe.columns.get_loc(column_name)
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

    def _build_row_status_cache(self):
        """Pre-compute each row's status token: "status_warning" / "_success"
        / "_danger", or None.

        Token names, not colours, so the cache survives a theme change --
        StatusEdgeDelegate resolves them against the live theme at paint time.

        Serves both tables this model backs. The order frame answers "is this a
        repeat?" from the derived `_repeat` column (System_note is line-level
        and does not survive the fold); the detail pane's lines table has
        System_note itself and no Order_Fulfillment_Status. Presence checks,
        not two code paths.

        Assumption unchanged from the colour cache it replaces: the DataFrame
        is immutable after the model is created. Mutate rows in place and you
        must call this again.
        """
        n = len(self._dataframe)
        columns = self._dataframe.columns

        repeat_col = columns.get_loc(REPEAT_COLUMN) if REPEAT_COLUMN in columns else -1
        note_col = columns.get_loc("System_note") if "System_note" in columns else -1
        status_col = (
            columns.get_loc("Order_Fulfillment_Status")
            if "Order_Fulfillment_Status" in columns
            else -1
        )

        cache = [None] * n
        for i in range(n):
            try:
                if repeat_col >= 0 and bool(self._dataframe.iat[i, repeat_col]):
                    cache[i] = "status_warning"
                    continue
                if note_col >= 0 and is_repeat(self._dataframe.iat[i, note_col]):
                    cache[i] = "status_warning"
                    continue
                if status_col >= 0:
                    status = self._dataframe.iat[i, status_col]
                    if status == "Fulfillable":
                        cache[i] = "status_success"
                    elif status == "Not Fulfillable":
                        cache[i] = "status_danger"
            except (IndexError, KeyError):
                pass

        self._row_status_cache = cache

    def _on_theme_changed(self, theme=None):
        """Repaint. The cache holds token names, so nothing needs rebuilding."""
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [ROLE_STATUS])
