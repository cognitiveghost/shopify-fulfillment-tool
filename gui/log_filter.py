"""Level floor and text search over the log buffer. No sorting.

The model's order is the truth -- entries arrive in time order and a log
sorted by anything else is not a log. This proxy filters and nothing more.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging

from PySide6.QtCore import QSortFilterProxyModel, Qt

_LEVEL = 1
_SOURCE = 2
_MESSAGE = 3


class LogFilterProxy(QSortFilterProxyModel):
    """Show entries at or above a level whose text contains a substring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._floor = logging.NOTSET
        self._search = ""

    def set_level_floor(self, level: int) -> None:
        self._floor = level
        self.invalidateFilter()

    def set_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        level_name = model.index(row, _LEVEL, parent).data(Qt.DisplayRole)
        # getLevelName round-trips a name back to its number.
        level = logging.getLevelName(level_name)
        if isinstance(level, int) and level < self._floor:
            return False

        if not self._search:
            return True

        source = model.index(row, _SOURCE, parent).data(Qt.DisplayRole) or ""
        message = model.index(row, _MESSAGE, parent).data(Qt.DisplayRole) or ""
        haystack = f"{source} {message}".lower()
        return self._search in haystack
