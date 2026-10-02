"""The Browse page's bridge (phase 4 spec section 3.2).

Python pushes one `state` map, built by gui/browse_state.py; the page draws
it and reports what the operator asks for through the named slots below. The
catalogue is the spec's section 3.2: add a member there before adding it here.

The page names a session by its name. Nothing it sends is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page
from shopify_tool.session_manager import SessionManager

PAGE = WEB_DIR / "browse.html"
CHANNEL_NAME = "browse"


def _names(values) -> list[str]:
    """The session names in a list from the page; anything else is dropped."""
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str) and value]


class BrowseBridge(PageBridge):
    """The Browse page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    refreshRequested = Signal()
    openRequested = Signal(str)
    statusRequested = Signal(list, str)
    commentRequested = Signal(list, str)
    exportRequested = Signal(list)
    newSessionRequested = Signal()
    undoRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def set_state(self, state: dict) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    # --- in: JS -> Python --------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        self.refreshRequested.emit()

    @Slot(str)
    def openSession(self, name) -> None:
        if isinstance(name, str) and name:
            self.openRequested.emit(name)

    @Slot("QVariantList", str)
    def setStatus(self, names, status) -> None:
        names = _names(names)
        # A name, not a verb: an unknown status is dropped rather than guessed.
        if names and status in SessionManager.VALID_STATUSES:
            self.statusRequested.emit(names, status)

    @Slot("QVariantList", str)
    def setComment(self, names, text) -> None:
        names = _names(names)
        if names:
            self.commentRequested.emit(names, str(text))

    @Slot("QVariantList")
    def exportCombined(self, names) -> None:
        names = _names(names)
        if len(names) >= 2:
            self.exportRequested.emit(names)

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def undo(self) -> None:
        self.undoRequested.emit()


def mount_browse_page(view: QWebEngineView) -> BrowseBridge:
    """Load the Browse page into `view` and return the bridge it talks to."""
    bridge = BrowseBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
