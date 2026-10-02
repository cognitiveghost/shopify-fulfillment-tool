"""The Tools page's bridge (phase 5 spec section 3.2).

Python pushes one `state` map, built by gui/tools_state.py; the page draws it
and reports what the operator asks for through the named slots below. The
catalogue is the spec's section 3.2: add a member there before adding it here.

The page names a tool, a packing list and a printer by name. Nothing it sends
is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "tools.html"
CHANNEL_NAME = "tools"
TOOLS = ("reference", "barcode")
KINDS = ("pdf", "csv")
OPTIONS = (("reference", "open_pdf"), ("barcode", "open_pdf"), ("barcode", "qr"))
PRINT_KEYS = ("mode", "printer", "target", "width", "height", "rotate", "invert")
PRINTABLE = (("reference", "labels"), ("barcode", "labels"), ("barcode", "qr"))


class ToolsBridge(PageBridge):
    """The Tools page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    fileRequested = Signal(str)
    clearRequested = Signal(str)
    folderRequested = Signal()
    optionChanged = Signal(str, str, bool)
    printChanged = Signal(str, str, object)
    listChosen = Signal(str)
    listsRequested = Signal()
    runRequested = Signal(str)
    cancelRequested = Signal()
    printRequested = Signal(str, str)
    folderOpenRequested = Signal()
    newSessionRequested = Signal()
    recentRequested = Signal()

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
    def clearFile(self, kind) -> None:
        if kind in KINDS:
            self.clearRequested.emit(kind)

    @Slot()
    def changeFolder(self) -> None:
        self.folderRequested.emit()

    @Slot(str, str, bool)
    def setOption(self, tool, name, on) -> None:
        if (tool, name) in OPTIONS:
            self.optionChanged.emit(tool, name, bool(on))

    @Slot(str, str, "QVariant")
    def setPrint(self, tool, key, value) -> None:
        # The value is checked where it is applied (tools_state.apply_print_edit).
        if tool in TOOLS and key in PRINT_KEYS:
            self.printChanged.emit(tool, key, value)

    @Slot(str)
    def chooseList(self, name) -> None:
        if isinstance(name, str) and name:
            self.listChosen.emit(name)

    @Slot()
    def refreshLists(self) -> None:
        self.listsRequested.emit()

    @Slot(str)
    def run(self, tool) -> None:
        if tool in TOOLS:
            self.runRequested.emit(tool)

    @Slot()
    def cancel(self) -> None:
        self.cancelRequested.emit()

    @Slot(str, str)
    def printLabels(self, tool, what) -> None:
        if (tool, what) in PRINTABLE:
            self.printRequested.emit(tool, what)

    @Slot()
    def openFolder(self) -> None:
        self.folderOpenRequested.emit()

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def openRecent(self) -> None:
        self.recentRequested.emit()


def mount_tools_page(view: QWebEngineView) -> ToolsBridge:
    """Load the Tools page into `view` and return the bridge it talks to."""
    bridge = ToolsBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
