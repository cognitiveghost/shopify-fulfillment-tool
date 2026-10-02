"""The Logs screen (phase 6 spec section 6): one web view over a LogBuffer.

Everything drawn on this screen is in gui/web/logs.*. This widget keeps the
entries, sends the page its rows in batches, and does the two things the page
cannot: write a file and set the clipboard.

append() and _flush() must never log. The root logger's handler calls
append() for every record, on the GUI thread, so a log call inside either
would call itself without end.
"""

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.log_buffer import LogBuffer, default_filename, save_text
from gui.logs_bridge import mount_logs_page

logger = logging.getLogger(__name__)

# How long a row waits for others before the batch leaves (spec section 3).
BATCH_MS = 100
WRAP_KEY = "logs/wrap"


def _settings() -> QSettings:
    """This PC's store, the same pair theme_manager uses. A function so tests
    can point it at an INI file under tmp_path."""
    return QSettings("ShopifyFulfillmentTool", "FulfillmentApp")


def _entries(n: int) -> str:
    return "1 entry" if n == 1 else f"{n} entries"


class LogsWidget(QWidget):
    """The Logs screen's widget: one web view and the buffer behind it."""

    def __init__(self, main_window, parent=None):
        """main_window: read for current_client_id, which names the saved file."""
        super().__init__(parent)
        self.mw = main_window
        self.buffer = LogBuffer()
        self._pending: list[dict] = []
        self._started = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        wrap = bool(_settings().value(WRAP_KEY, False, type=bool))
        self.bridge = mount_logs_page(self.view, wrap=wrap, capacity=self.buffer.capacity)
        layout.addWidget(self.view, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(BATCH_MS)
        self._timer.timeout.connect(self._flush)

        self.view.loadStarted.connect(self._on_load_started)
        self.bridge.started.connect(self._on_started)
        self.bridge.saveRequested.connect(self._save)
        self.bridge.copyRequested.connect(self._copy)
        self.bridge.wrapRequested.connect(self._remember_wrap)

    # --- entries -------------------------------------------------------------

    def append(self, entry, stream) -> None:
        """Keep one entry. It reaches the page with the next batch."""
        row = self.buffer.add(entry, stream)
        if not self._started:
            return  # the backlog carries it when the page starts
        self._pending.append(row)
        if not self._timer.isActive():
            self._timer.start()

    def _flush(self) -> None:
        batch, self._pending = self._pending, []
        self.bridge.send(batch)

    def _on_load_started(self) -> None:
        """The page is loading again (a reload): hold rows until it starts.

        A batch that reached the new page ahead of the backlog would move its
        last-seen id past every backlog row, and the page would skip them all.
        """
        self._started = False
        self._timer.stop()
        self._pending = []

    def _on_started(self) -> None:
        """The page is listening: everything held so far, as one batch."""
        self._started = True
        self._pending = []
        self.bridge.send(self.buffer.rows())

    # --- what the page asks for ----------------------------------------------

    def _remember_wrap(self, on: bool) -> None:
        _settings().setValue(WRAP_KEY, bool(on))

    def _save(self, ids) -> None:
        rows = self.buffer.pick(ids)
        if not rows:
            return
        client = getattr(self.mw, "current_client_id", None)
        name = default_filename(client, datetime.now().astimezone().date())
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save log as text", name, "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(save_text(rows), encoding="utf-8")
        except OSError as error:
            # Operators save to UNC shares that go away mid-write. An
            # unhandled OSError out of a Qt slot takes the app down rather
            # than telling anyone which file failed.
            logger.warning("Could not save log to %s: %s", path, error)
            show_error(
                self,
                "The log wasn't saved",
                f"{path} couldn't be written. Choose another folder and save again.",
            )
            return
        self.bridge.raise_toast(f"Saved {_entries(len(rows))} to {Path(path).name}")

    def _copy(self, entry_id: int) -> None:
        rows = self.buffer.pick([entry_id])
        if not rows or not rows[0]["traceback"]:
            return
        QGuiApplication.clipboard().setText(rows[0]["traceback"])
        self.bridge.raise_toast("Traceback copied")
