"""The Logs page's bridge (phase 6 spec section 3.2).

Rows go out in batches through one signal, `entriesAdded`; the page keeps
them and filters them itself. The page names an entry by its id. Nothing it
sends is written to disk or used as a path. The catalogue is the spec's
section 3.2: add a member there before adding it here.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.log_buffer import CAPACITY
from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "logs.html"
CHANNEL_NAME = "logs"


def _whole(value) -> bool:
    """A whole number. A JavaScript number can reach a slot as a float."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and float(value).is_integer()
    )


class LogsBridge(PageBridge):
    """The Logs page's one channel object."""

    # JS-facing: a batch of rows (gui/log_buffer.py to_row), oldest first.
    entriesAdded = Signal("QVariantList")
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    started = Signal()
    saveRequested = Signal(list)
    copyRequested = Signal(int)
    wrapRequested = Signal(bool)

    def __init__(self, parent=None, wrap: bool = False, capacity: int = CAPACITY):
        super().__init__(parent)
        self._wrap = bool(wrap)
        self._capacity = int(capacity)

    # --- out: Python -> JS -------------------------------------------------

    def _get_capacity(self) -> int:
        return self._capacity

    def _get_wrap(self) -> bool:
        return self._wrap

    capacity = Property(int, _get_capacity, constant=True)
    wrap = Property(bool, _get_wrap, constant=True)

    def send(self, rows) -> None:
        """One batch to the page. An empty batch is not sent."""
        if rows:
            self.entriesAdded.emit(list(rows))

    # --- in: JS -> Python --------------------------------------------------

    @Slot()
    def start(self) -> None:
        self.started.emit()

    @Slot("QVariantList")
    def saveShown(self, ids) -> None:
        self.saveRequested.emit([int(value) for value in ids if _whole(value)])

    @Slot(int)
    def copyTraceback(self, entry_id) -> None:
        self.copyRequested.emit(int(entry_id))

    @Slot(bool)
    def setWrap(self, on) -> None:
        self.wrapRequested.emit(bool(on))


def mount_logs_page(
    view: QWebEngineView, wrap: bool = False, capacity: int = CAPACITY
) -> LogsBridge:
    """Load the Logs page into `view` and return the bridge it talks to."""
    bridge = LogsBridge(view, wrap=wrap, capacity=capacity)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
