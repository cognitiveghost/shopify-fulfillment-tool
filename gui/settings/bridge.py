"""The settings pages' bridge (phase 7 spec section 3.3).

Python pushes one `state` map, built by a draft's view() (gui/settings/
page_state.py); the page draws it and reports each edit through edit(). The
catalogue is the spec's section 3.3: add a member there before adding it here.

Nothing the page sends is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "settings.html"
CHANNEL_NAME = "settings"


class SettingsBridge(PageBridge):
    """The settings pages' one channel object."""

    stateChanged = Signal()
    # JS-facing: focus the control with this data-key and scroll it into view.
    problemFocusRequested = Signal(str)
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    editRequested = Signal(str, list)
    readColumnsRequested = Signal()

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

    @Slot(str, "QVariant")
    def edit(self, action, args) -> None:
        # The draft checks the action and every argument; this only refuses
        # what is not a list at all.
        if isinstance(args, list):
            self.editRequested.emit(str(action), args)

    @Slot()
    def readColumns(self) -> None:
        self.readColumnsRequested.emit()


def mount_settings_page(view: QWebEngineView) -> SettingsBridge:
    """Load the settings page into `view` and return the bridge it talks to."""
    bridge = SettingsBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
