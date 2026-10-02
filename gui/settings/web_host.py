"""The widget that shows the settings pages the web tier draws (phase 7 spec
section 6.5).

One web view for General, Orders mapping and Stock mapping. The window keeps
the three drafts in its page list, like any other page; this widget shows one
of them at a time, hands the page's edits to it, and says when it changed.
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.settings.bridge import mount_settings_page
from gui.settings.page_state import MappingDraft, read_file_columns

logger = logging.getLogger(__name__)


class SettingsWebHost(QWidget):
    """One web view and the drafts it draws, keyed "general", "orders", "stock".

    Signals:
        edited: a draft's values, or the file it reads columns from, changed
    """

    edited = Signal()

    def __init__(self, drafts: dict, parent=None):
        super().__init__(parent)
        self.drafts = drafts
        self._current = next(iter(drafts))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_settings_page(self.view)
        layout.addWidget(self.view, 1)

        self.bridge.editRequested.connect(self._on_edit)
        self.bridge.readColumnsRequested.connect(self._read_columns)
        self._push()

    def show_page(self, key: str) -> None:
        """Draw the draft under `key`."""
        self._current = key
        self._push()

    def focus_problem(self, key: str) -> None:
        """Put the operator on the control with this data-key."""
        self.view.setFocus()
        self.bridge.problemFocusRequested.emit(key)

    def _push(self) -> None:
        self.bridge.set_state(self.drafts[self._current].view())

    def _on_edit(self, action: str, args: list) -> None:
        if not self.drafts[self._current].apply(action, args):
            # Nothing changed: a repeat of the current value, or an edit the
            # draft does not know.
            logger.debug(f"Settings edit changed nothing: {action} {args!r}")
            return
        self._push()
        self.edited.emit()

    def _read_columns(self) -> None:
        """Offer a chosen CSV's columns on the mapping page that is showing.

        Reads the header and one row, and detects the delimiter itself, so
        this does not depend on the delimiter General currently shows, which
        may hold an edit the operator has not saved yet.
        """
        draft = self.drafts[self._current]
        if not isinstance(draft, MappingDraft):
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Select {draft.kind.capitalize()} CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            file = read_file_columns(path, loaded=False)
        except Exception:
            logger.exception("Failed to read column names from CSV")
            show_error(
                self, "The column names couldn't be read", "Details are in Logs."
            )
            return
        draft.set_file(file)
        self._push()
        self.edited.emit()
