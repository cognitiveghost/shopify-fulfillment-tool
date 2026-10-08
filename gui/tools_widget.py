"""The Tools screen: Reference labels and Barcode labels (phase 5 spec section 6.1).

A widget that hosts one web view. Everything drawn on this screen is in
gui/web/tools.*; what it draws is built by gui/tools_state.py from the two
tools' facts (gui/reference_tool.py, gui/barcode_tool.py). This widget wires
the page's requests to the tools and pushes the state.
"""

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui import pdf_printing
from gui.barcode_tool import BarcodeTool
from gui.components import toast
from gui.reference_tool import ReferenceTool
from gui.setup_state import SessionFacts
from gui.tools_bridge import TOOLS, mount_tools_page
from gui.tools_state import PRINT_SCOPE, PrintFacts, apply_print_edit, tools_state
from gui.web_page import is_current_page

logger = logging.getLogger(__name__)


def installed_printers() -> tuple[str, ...]:
    """The printers this PC lists, by name."""
    return tuple(QPrinterInfo.availablePrinterNames())


class ToolsWidget(QWidget):
    """The Tools screen's widget: one web view and the two tools behind it.

    Signals:
        new_session_requested: the no-session banner's New session
        recent_requested: the no-session banner's Open recent
    """

    new_session_requested = Signal()
    recent_requested = Signal()

    def __init__(self, main_window, parent=None, pool: QThreadPool | None = None):
        """main_window: read for session_path, session_facts, current_client_id
        and analysis_results_df. pool: where the tools' workers start; the
        global pool when None."""
        super().__init__(parent)
        self.mw = main_window
        self._session_path: str | None = None
        self._printers: tuple[str, ...] = ()
        self._settings: dict[str, dict] = {}
        self._toast_folder = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_tools_page(self.view)
        layout.addWidget(self.view, 1)

        self.reference = ReferenceTool(self, pool)
        self.barcode = BarcodeTool(
            self, lambda: getattr(self.mw, "analysis_results_df", None), pool
        )
        for tool in (self.reference, self.barcode):
            tool.changed.connect(self._push)
            tool.toast.connect(self._on_toast)

        bridge = self.bridge
        bridge.fileRequested.connect(self.reference.choose)
        bridge.clearRequested.connect(self.reference.clear)
        bridge.folderRequested.connect(self.reference.change_folder)
        bridge.optionChanged.connect(self._on_option)
        bridge.printChanged.connect(self._on_print_edit)
        bridge.listChosen.connect(self.barcode.choose)
        bridge.listsRequested.connect(self.barcode.reload)
        bridge.runRequested.connect(self._on_run)
        bridge.cancelRequested.connect(self.reference.cancel)
        bridge.printRequested.connect(self._on_print)
        bridge.folderOpenRequested.connect(self._open_toast_folder)
        bridge.newSessionRequested.connect(self.new_session_requested)
        bridge.recentRequested.connect(self.recent_requested)

        self._read_this_pc()
        self.sync()
        logger.info("ToolsWidget initialized")

    # --- state ---------------------------------------------------------------

    def _read_this_pc(self) -> None:
        """The installed printers and both tools' saved print settings."""
        self._printers = installed_printers()
        self._settings = {
            tool: pdf_printing.load_print_settings(PRINT_SCOPE[tool]) for tool in TOOLS
        }

    def sync(self) -> None:
        """Follow the window's session, then push. Touches no file, so the
        shell calls it on every client, session and connection change."""
        path = getattr(self.mw, "session_path", None)
        path = str(path) if path else None
        if path != self._session_path:
            self._session_path = path
            self.reference.set_session(path)
            self.barcode.set_session(path)
            if path and self._showing():
                self.barcode.reload()
        self._push()

    def _push(self) -> None:
        """Build the page's state from what the tools hold and send it."""
        session = None
        if self._session_path:
            name = Path(self._session_path).name
            facts = getattr(self.mw, "session_facts", None)
            session = (
                facts
                if facts is not None and facts.name == name
                else SessionFacts(name, None, None)
            )
        self.bridge.set_state(
            tools_state(
                client=getattr(self.mw, "current_client_id", None) or "",
                session=session,
                reference=self.reference.facts(),
                reference_print=PrintFacts(self._settings["reference"], self._printers),
                barcode=self.barcode.facts(),
                barcode_print=PrintFacts(self._settings["barcode"], self._printers),
                now=datetime.now().astimezone(),
            )
        )

    def _showing(self) -> bool:
        """Whether the user is looking at Tools. Every page of the shell stays
        visible to Qt (keep_pages_painted), so isVisible() alone cannot say."""
        return self.isVisible() and is_current_page(self)

    def showEvent(self, event):
        super().showEvent(event)
        if is_current_page(self):
            self.page_shown()

    def page_shown(self) -> None:
        """Each time Tools is shown: this PC's printers and settings, and the
        session's packing lists, are read again. The shell calls it when Tools
        becomes the current page, which sends no show event."""
        self._read_this_pc()
        self.sync()
        if self._session_path:
            self.barcode.reload()

    # --- what the page asks for ----------------------------------------------

    def _on_option(self, tool: str, name: str, on: bool) -> None:
        if tool == "reference":
            self.reference.set_open_pdf(on)
        else:
            self.barcode.set_option(name, on)

    def _on_print_edit(self, tool: str, key: str, value) -> None:
        edited = apply_print_edit(self._settings[tool], key, value)
        if edited is None:
            logger.warning(f"Dropped a print edit the page should not send: {tool}.{key}")
            return
        self._settings[tool] = edited
        pdf_printing.save_print_settings(PRINT_SCOPE[tool], edited)
        self._push()

    def _on_run(self, tool: str) -> None:
        if tool == "reference":
            self.reference.start()
        else:
            self.barcode.start()

    def _on_print(self, tool: str, what: str) -> None:
        if tool == "reference":
            self.reference.print_output()
        else:
            self.barcode.print_labels(what)

    # --- toasts --------------------------------------------------------------

    def _on_toast(self, text: str, folder: str) -> None:
        """A run finished. While this screen shows, its page draws the toast
        with Open folder; otherwise the router sends it to the page that is
        showing (ADR 0007), with no action."""
        if folder and self._showing():
            self._toast_folder = folder
            self.bridge.raise_toast(text, True)
        else:
            toast(self, text)

    def _open_toast_folder(self) -> None:
        if self._toast_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._toast_folder))
