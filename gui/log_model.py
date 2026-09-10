"""Two ring buffers, one model, one selected source.

Callers push entries and pick a source. They never see a row index, the
buffer's capacity, or the point it wraps at -- which is the whole reason
this is a module rather than a list on the widget.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
from collections import deque

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from gui.log_entry import LogEntry
from gui.pandas_model import ROLE_STATUS
from gui.theme_manager import get_theme_manager

# The column layout, declared once. The proxy filters on LEVEL/SOURCE/MESSAGE
# and the viewer sizes and stretches by index, so all three files have to
# agree about these numbers -- which is the argument for them having one home.
COL_TIME = 0
COL_LEVEL = 1
COL_SOURCE = 2
COL_MESSAGE = 3

# The real level as an int, so the filter never has to read a level back out
# of the string the model rendered it as. Same UserRole convention as
# pandas_model's ROLE_STATUS.
ROLE_LEVEL = Qt.ItemDataRole.UserRole + 21


class LogBufferModel(QAbstractTableModel):
    """The rows the viewer shows, for whichever source is selected."""

    CAPACITY = 5000
    ACTIVITY = "Activity"
    EXECUTION = "Execution"
    COLUMNS = ("TIME", "LEVEL", "SOURCE", "MESSAGE")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buffers: dict[str, deque[LogEntry]] = {
            self.ACTIVITY: deque(maxlen=self.CAPACITY),
            self.EXECUTION: deque(maxlen=self.CAPACITY),
        }
        self._source = self.EXECUTION

    # -- the interface callers actually use ---------------------------------

    def append(self, entry: LogEntry, source: str) -> None:
        """Add one entry to a source's buffer, evicting the oldest at capacity.

        Only the *visible* source touches the model's row signals; an entry
        landing in the other buffer changes nothing on screen.
        """
        buffer = self._buffers[source]
        visible = source == self._source
        evicting = len(buffer) == self.CAPACITY

        if visible and not evicting:
            self.beginInsertRows(QModelIndex(), 0, 0)
            buffer.appendleft(entry)
            self.endInsertRows()
        elif visible:
            # A full deque both inserts and drops in one operation; a plain
            # insert signal would leave the view one row longer than the model.
            self.beginResetModel()
            buffer.appendleft(entry)
            self.endResetModel()
        else:
            buffer.appendleft(entry)

    def set_source(self, source: str) -> None:
        if source == self._source:
            return
        self.beginResetModel()
        self._source = source
        self.endResetModel()

    def current_source(self) -> str:
        return self._source

    def clear(self) -> None:
        """Empty the visible source. The other buffer is untouched."""
        self.beginResetModel()
        self._buffers[self._source].clear()
        self.endResetModel()

    def entries(self) -> list[LogEntry]:
        """The visible source's entries, newest first. For Save as text."""
        return list(self._buffers[self._source])

    # -- QAbstractTableModel ------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._buffers[self._source])

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._buffers[self._source][index.row()]

        if role == Qt.DisplayRole:
            column = index.column()
            if column == COL_TIME:
                return entry.timestamp.strftime("%H:%M:%S")
            if column == COL_LEVEL:
                return entry.level_name
            if column == COL_SOURCE:
                return entry.source
            return entry.message

        if role == Qt.ToolTipRole:
            # The absolute time lives here; the cell only has room for a clock.
            if index.column() == COL_TIME:
                return entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            return entry.message

        if role == ROLE_LEVEL:
            return entry.level

        if role == ROLE_STATUS:
            # StatusEdgeDelegate reads exactly this role, so answering it is
            # all the 3px error edge needs -- no delegate of our own.
            return "status_danger" if entry.level >= logging.ERROR else None

        if role == Qt.BackgroundRole and entry.level >= logging.ERROR:
            theme = get_theme_manager().get_current_theme()
            return QColor(theme.status_danger_bg)

        column = index.column()

        if role == Qt.ForegroundRole and column in (COL_TIME, COL_SOURCE):
            # TIME and SOURCE sit back so MESSAGE carries the row.
            theme = get_theme_manager().get_current_theme()
            return QColor(theme.text_secondary)

        if role == Qt.FontRole and column == COL_TIME:
            theme = get_theme_manager().get_current_theme()
            return QFont(theme.font_family_mono)

        return None
