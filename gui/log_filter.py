"""Level floor and text search over the log buffer. No sorting.

The model's order is the truth -- entries arrive in time order and a log
sorted by anything else is not a log. This proxy filters and nothing more.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging

from PySide6.QtCore import QSortFilterProxyModel, Qt

from gui.log_model import COL_LEVEL, COL_MESSAGE, COL_SOURCE, ROLE_LEVEL


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

        # ROLE_LEVEL, not the LEVEL column's text: a level recovered from the
        # string the model rendered it as is a level you can get wrong. A
        # custom level has no registered name, so getLevelName hands back
        # "Level 25" and the row escapes the floor entirely.
        level = model.index(row, COL_LEVEL, parent).data(ROLE_LEVEL)
        if level is not None and level < self._floor:
            return False

        if not self._search:
            return True

        source = model.index(row, COL_SOURCE, parent).data(Qt.DisplayRole) or ""
        message = model.index(row, COL_MESSAGE, parent).data(Qt.DisplayRole) or ""
        haystack = f"{source} {message}".lower()
        return self._search in haystack
