"""The Setup page's bridge (phase 3 spec section 3.3).

Python pushes one `state` map, built by gui/setup_state.py; the page renders
it and reports clicks through the named slots below. The catalogue is the
spec's section 3.3: add a member there before adding it here.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtGui import QDragLeaveEvent
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "setup.html"
CHANNEL_NAME = "setup"
KINDS = ("orders", "stock")
STRATEGIES = ("multi_first", "fifo")


class SetupBridge(PageBridge):
    """The Setup page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    fileRequested = Signal(str)
    folderRequested = Signal(str)
    clearRequested = Signal(str)
    fixRequested = Signal(str)
    memoryToggled = Signal(bool)
    strategyChosen = Signal(str)
    runRequested = Signal()
    cancelRequested = Signal()
    newSessionRequested = Signal()
    recentRequested = Signal()
    connectionRequested = Signal()

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

    @Slot(str)
    def chooseFile(self, kind) -> None:
        if kind in KINDS:
            self.fileRequested.emit(kind)

    @Slot(str)
    def chooseFolder(self, kind) -> None:
        if kind in KINDS:
            self.folderRequested.emit(kind)

    @Slot(str)
    def clearFile(self, kind) -> None:
        if kind in KINDS:
            self.clearRequested.emit(kind)

    @Slot(str)
    def fixProblem(self, kind) -> None:
        if kind in KINDS:
            self.fixRequested.emit(kind)

    @Slot(bool)
    def setMemory(self, on) -> None:
        self.memoryToggled.emit(bool(on))

    @Slot(str)
    def setStrategy(self, name) -> None:
        # A name, not a verb: an unknown one is dropped rather than guessed.
        if name in STRATEGIES:
            self.strategyChosen.emit(name)

    @Slot()
    def runAnalysis(self) -> None:
        self.runRequested.emit()

    @Slot()
    def cancelRun(self) -> None:
        self.cancelRequested.emit()

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def openRecent(self) -> None:
        self.recentRequested.emit()

    @Slot()
    def openConnection(self) -> None:
        self.connectionRequested.emit()


# Which card is under a point: the page knows its layout, Python does not.
_CARD_AT = (
    "(function () {"
    " var el = document.elementFromPoint(%d, %d);"
    " var card = el && el.closest('[data-file-kind]');"
    " return card ? card.dataset.fileKind : '';"
    " })()"
)


class SetupView(QWebEngineView):
    """The Setup page's view. It takes file drops itself (spec section 3.4).

    Chromium navigates to a dropped file, and a page cannot read a dropped
    file's path. So the drag reaches the page (it highlights the card) and
    the drop stops here: the path comes from the mime data and the card from
    the page.
    """

    pathDropped = Signal(str, str)  # kind, local path

    def dragEnterEvent(self, event) -> None:
        super().dragEnterEvent(event)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        super().dragMoveEvent(event)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        point = event.position().toPoint()
        # Never the base class: that is the navigation. Ending the drag this
        # way sends the page a dragleave, so its highlight clears.
        super().dragLeaveEvent(QDragLeaveEvent())
        if not urls:
            return
        path = urls[0].toLocalFile()
        event.acceptProposedAction()
        self.page().runJavaScript(
            _CARD_AT % (point.x(), point.y()),
            0,
            lambda kind: self._dropped(kind, path),
        )

    def _dropped(self, kind, path: str) -> None:
        if kind in KINDS and path:
            self.pathDropped.emit(kind, path)


def mount_setup_page(view: QWebEngineView) -> SetupBridge:
    """Load the Setup page into `view` and return the bridge it talks to."""
    bridge = SetupBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
