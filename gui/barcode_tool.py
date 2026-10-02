"""Barcode labels, as the Tools page runs it (phase 5 spec section 6.3).

Not a widget. It reads the session's packing lists on a worker, holds which
one is selected, writes that list's label PDFs on a worker, and prints them.
The page draws what facts() returns, worded by gui/tools_state.py.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from gui import pdf_printing
from gui.components import ConfirmDialog, show_error
from gui.tools_state import PRINT_SCOPE, BarcodeFacts, PackingList, ToolRun, short_path
from gui.worker import Worker
from shopify_tool.barcode_processor import (
    barcode_pdf_path,
    barcodes_dir,
    generate_list_labels,
    packing_list_orders,
    qr_pdf_path,
)
from shopify_tool.report_filters import fulfillable_only

logger = logging.getLogger(__name__)

# path -> (mtime, order numbers). The share is slow and the Tools page reloads
# its lists every time it is shown, so a workbook is read once until it changes.
_ORDERS_CACHE: dict[str, tuple[float, frozenset]] = {}


def _orders(path: Path) -> frozenset:
    key = str(path)
    mtime = os.path.getmtime(path)
    hit = _ORDERS_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    orders = packing_list_orders(path)
    _ORDERS_CACHE[key] = (mtime, orders)
    return orders


def read_packing_lists(session_path, analysis_df) -> list[tuple[PackingList, frozenset]]:
    """The session's packing lists, each with its order numbers.

    Runs on a worker: it reads every workbook and looks for each list's label
    PDFs on the share. A list's count is its Fulfillable orders, or None when
    its workbook can't be read or there is no analysis to count against.
    """
    folder = Path(session_path) / "packing_lists"
    if not folder.is_dir():
        return []
    fulfillable = None
    if analysis_df is not None:
        base = fulfillable_only(analysis_df)
        if "Order_Number" in base.columns:
            fulfillable = base["Order_Number"]

    found = []
    # "~$DHL.xlsx" is the lock file Excel leaves beside an open workbook.
    paths = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")]
    for path in sorted(paths, key=lambda p: p.stem):
        name = path.stem
        orders, count = frozenset(), None
        try:
            orders = _orders(path)
            if fulfillable is not None:
                count = int(fulfillable[fulfillable.isin(orders)].nunique())
        except Exception:
            logger.exception(f"Failed to read packing list {path}")
            orders, count = frozenset(), None
        labels = barcodes_dir(session_path, name)
        found.append(
            (
                PackingList(
                    name,
                    count,
                    has_labels=barcode_pdf_path(labels, name).exists(),
                    has_qr=qr_pdf_path(labels, name).exists(),
                ),
                orders,
            )
        )
    return found


def _read(session_path, analysis_df):
    """The worker's function: the session comes back with its lists, so a
    result for a session the operator has left can be told apart."""
    return session_path, read_packing_lists(session_path, analysis_df)


class BarcodeTool(QObject):
    """The Barcode labels tool: the lists, one run at a time, and Print."""

    changed = Signal()
    toast = Signal(str, str)  # text, the folder to offer ("" for none)
    _progress = Signal(str)  # from the worker thread

    def __init__(
        self,
        host: QWidget,
        analysis: Callable[[], object],
        pool: QThreadPool | None = None,
    ):
        """host: the parent for dialogs and error banners. analysis: returns
        the window's analysis frame, or None. pool: where a Worker starts;
        the global pool when None."""
        super().__init__(host)
        self._host = host
        self._analysis = analysis
        self._pool = pool
        self._session: str | None = None
        self._lists: list[PackingList] = []
        self._orders: dict[str, frozenset] = {}
        self._loading = False
        self._analysed = True
        self._selected = ""
        self._qr = False
        self._open_pdf = True
        self._run: ToolRun | None = None
        self._result: dict | None = None
        # Held until each finishes: a Worker kept only by a local is collected
        # before its queued result arrives (see gui/main_window_pyside.py).
        self._list_worker: Worker | None = None
        self._run_worker: Worker | None = None
        self._progress.connect(self._on_progress)

    def _start(self, worker: Worker) -> None:
        (self._pool or QThreadPool.globalInstance()).start(worker)

    # --- facts ---------------------------------------------------------------

    def facts(self) -> BarcodeFacts:
        folder = ""
        if self._session and self._selected:
            folder = str(barcodes_dir(self._session, self._selected))
        return BarcodeFacts(
            lists=tuple(self._lists),
            loading=self._loading,
            analysed=self._analysed,
            selected=self._selected,
            folder=folder,
            qr=self._qr,
            open_pdf=self._open_pdf,
            run=self._run,
            result=self._result,
        )

    def _entry(self, name: str) -> PackingList | None:
        return next((entry for entry in self._lists if entry.name == name), None)

    def set_session(self, session_path: str | None) -> None:
        """Another session, or none: its lists are not this one's. Touches no file."""
        self._session = str(session_path) if session_path else None
        self._lists = []
        self._orders = {}
        self._selected = ""
        self._result = None
        self._loading = False
        self.changed.emit()

    # --- the lists -----------------------------------------------------------

    def reload(self) -> None:
        """Read the session's packing lists again, off the GUI thread."""
        if not self._session or self._loading:
            return
        frame = self._analysis()
        self._analysed = frame is not None
        self._loading = True
        worker = Worker(_read, self._session, frame)
        worker.signals.result.connect(self._on_lists)
        worker.signals.error.connect(self._on_lists_failed)
        self._list_worker = worker
        self.changed.emit()
        self._start(worker)

    def _on_lists(self, payload) -> None:
        session, found = payload
        if session != self._session:
            return  # the operator moved to another session while it loaded
        self._loading = False
        self._list_worker = None
        self._lists = [entry for entry, _orders in found]
        self._orders = {entry.name: orders for entry, orders in found}
        names = [entry.name for entry in self._lists]
        if self._selected not in names:
            self._selected = names[0] if names else ""
            self._result = None
        self.changed.emit()

    def _on_lists_failed(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        logger.error(f"Reading packing lists failed: {value}\n{traceback_str}")
        self._loading = False
        self._list_worker = None
        self.changed.emit()
        show_error(
            self._host,
            "The packing lists weren't read",
            "Check the server connection, then Refresh.",
        )

    def choose(self, name: str) -> None:
        if self._run is not None or self._entry(name) is None or name == self._selected:
            return
        self._selected = name
        self._result = None
        self.changed.emit()

    def set_option(self, name: str, on: bool) -> None:
        if name == "qr":
            self._qr = bool(on)
        elif name == "open_pdf":
            self._open_pdf = bool(on)
        else:
            return
        self.changed.emit()

    # --- the run -------------------------------------------------------------

    def start(self) -> None:
        if self._run is not None or not self._session:
            return
        entry = self._entry(self._selected)
        frame = self._analysis()
        if entry is None or not entry.count or frame is None:
            return
        folder = barcodes_dir(self._session, entry.name)
        if barcode_pdf_path(folder, entry.name).exists() and not ConfirmDialog.ask(
            self._host,
            title=f"Replace barcodes for {entry.name}?",
            body=(
                f"The existing PDF is overwritten with {entry.count} new barcodes. "
                "This cannot be undone."
            ),
            verb="Replace barcodes",
        ):
            return
        base = fulfillable_only(frame)
        rows = base[base["Order_Number"].isin(self._orders.get(entry.name, frozenset()))].copy()
        if rows.empty:
            logger.warning(f"No Fulfillable orders left for packing list {entry.name!r}")
            return
        # The folder and the name go in as arguments: a session change during
        # the run cannot redirect it.
        worker = Worker(
            generate_list_labels,
            rows,
            folder,
            entry.name,
            qr=self._qr,
            progress=self._progress.emit,
        )
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._run_worker = worker
        self._run = ToolRun(f"Preparing {entry.count:,} labels…")
        logger.info(f"Started barcode generation for packing list {entry.name!r}")
        self.changed.emit()
        self._start(worker)

    def _on_progress(self, label: str) -> None:
        if self._run is None:
            return  # a report that arrived after the run finished
        self._run = ToolRun(label)
        self.changed.emit()

    def _on_result(self, outcome: dict) -> None:
        name, folder = outcome["list"], outcome["folder"]
        ours = bool(self._session) and str(barcodes_dir(self._session, name)) == folder
        if ours:
            self._result = outcome
            self._lists = [
                replace(
                    entry,
                    has_labels=entry.has_labels or bool(outcome["pdf"]),
                    has_qr=entry.has_qr or bool(outcome["qr_pdf"]),
                )
                if entry.name == name
                else entry
                for entry in self._lists
            ]
        if self._open_pdf:
            for path in (outcome["pdf"], outcome["qr_pdf"]):
                if path:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if outcome["pdf"]:
            labels = outcome["labels"]
            text = (
                f"{labels:,} barcode label{'' if labels == 1 else 's'} "
                f"saved to {short_path(folder)}"
            )
            if outcome["qr_pdf"]:
                text += ". QR labels too."
            self.toast.emit(text, folder)

    def _on_error(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        logger.error(f"Barcode generation failed: {value}\n{traceback_str}")
        show_error(self._host, "The barcode PDF wasn't created", "Details are in Logs.")

    def _on_finished(self) -> None:
        self._run = None
        self._run_worker = None
        self.changed.emit()

    # --- output --------------------------------------------------------------

    def print_labels(self, what: str) -> None:
        if self._run is not None or not self._session or not self._selected:
            return
        folder = barcodes_dir(self._session, self._selected)
        path_for = qr_pdf_path if what == "qr" else barcode_pdf_path
        pdf_printing.print_pdf(
            self._host,
            path_for(folder, self._selected),
            pdf_printing.load_print_settings(PRINT_SCOPE["barcode"]),
        )
