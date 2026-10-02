"""Reference labels, as the Tools page runs it (phase 5 spec section 6.2).

Not a widget. It holds the two picked files and the output folder, checks a
file when it is picked, runs the stamping on a worker with counted progress
and Cancel, and prints the result. The page draws what facts() returns, worded
by gui/tools_state.py.
"""

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QWidget

from gui import pdf_printing
from gui.components import show_error
from gui.tools_state import PRINT_SCOPE, PickedFile, ReferenceFacts, ToolRun, short_path
from gui.worker import Worker
from shopify_tool import pdf_processor
from shopify_tool.pdf_processor import (
    InvalidCSVError,
    InvalidPDFError,
    MappingError,
    ProcessingCancelled,
    reference_run_warning,
)

logger = logging.getLogger(__name__)

KINDS = ("pdf", "csv")
PDF_PROBLEM = (
    "This PDF can't be read",
    "Check that it isn't damaged, then choose it again.",
)
CSV_PROBLEM = (
    "This CSV has no usable rows",
    (
        "Each row needs the PostOne export's columns: PostOne ID (1st), Tracking (2nd), "
        "Reference (3rd) and Name (7th)."
    ),
)
_DIALOG = {
    "pdf": ("Select the labels PDF", "PDF Files (*.pdf)"),
    "csv": ("Select the mapping CSV", "CSV Files (*.csv);;All Files (*.*)"),
}
# Seconds between two progress pushes: a 2,000-page PDF must not redraw the
# page 4,000 times.
_REPORT_EVERY = 0.1


def _process(pdf_path, csv_path, folder, report):
    """The run, on a worker thread. Making the folder is part of it: the
    share can be slow, or gone."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    return pdf_processor.process_reference_labels(
        pdf_path=pdf_path,
        csv_path=csv_path,
        output_dir=str(folder),
        progress_callback=report,
    )


class ReferenceTool(QObject):
    """The Reference labels tool: picks, one run at a time, and Print."""

    changed = Signal()
    toast = Signal(str, str)  # text, the folder to offer ("" for none)
    _progress = Signal(int, int, str)  # from the worker thread

    def __init__(self, host: QWidget, pool: QThreadPool | None = None):
        """host: the parent for dialogs and error banners. pool: where a
        run's Worker starts; the global pool when None."""
        super().__init__(host)
        self._host = host
        self._pool = pool
        self._paths: dict[str, str | None] = {"pdf": None, "csv": None}
        self._picks: dict[str, PickedFile | None] = {"pdf": None, "csv": None}
        self._folder: Path | None = None
        self._open_pdf = True
        self._run: ToolRun | None = None
        self._result: dict | None = None
        self._output: Path | None = None
        # Counts session changes, so a run that outlives its session does not
        # leave its result on the next one.
        self._generation = 0
        self._started_in = 0
        # Held until the run finishes: a Worker kept only by a local is
        # collected before its queued result arrives (see the client-load
        # worker in gui/main_window_pyside.py).
        self._worker: Worker | None = None
        self._cancel = threading.Event()
        self._last_report = 0.0
        self._progress.connect(self._on_progress)

    # --- facts ---------------------------------------------------------------

    def facts(self) -> ReferenceFacts:
        return ReferenceFacts(
            pdf=self._picks["pdf"],
            csv=self._picks["csv"],
            folder=str(self._folder) if self._folder is not None else "",
            open_pdf=self._open_pdf,
            run=self._run,
            result=self._result,
            has_output=self._output is not None,
        )

    def set_session(self, session_path: str | None) -> None:
        """Another session, or none. The picks belonged to the last one's
        batch, so they go. Touches no file."""
        self._generation += 1
        self._paths = {"pdf": None, "csv": None}
        self._picks = {"pdf": None, "csv": None}
        self._result = None
        self._output = None
        self._folder = Path(session_path) / "reference_labels" if session_path else None
        self.changed.emit()

    # --- inputs --------------------------------------------------------------

    def _editable(self) -> bool:
        return self._folder is not None and self._run is None

    def choose(self, kind: str) -> None:
        if kind not in KINDS or not self._editable():
            return
        title, pattern = _DIALOG[kind]
        path, _ = QFileDialog.getOpenFileName(self._host, title, "", pattern)
        if path:
            self.load(kind, path)

    def load(self, kind: str, path: str) -> None:
        """Take a picked file and check it now, so a bad one is flagged under
        its own field instead of after Process."""
        if kind not in KINDS or not self._editable():
            return
        # ponytail: both checks read the file on the GUI thread. It was just
        # picked in a dialog, so it is normally local. Move them to a worker
        # if a pick from the share ever stalls the window.
        name = Path(path).name
        try:
            if kind == "pdf":
                count = pdf_processor.pdf_page_count(path)
            else:
                count = pdf_processor.load_csv_mapping(path)["rows"]
            pick = PickedFile(name, count)
        except (InvalidPDFError, InvalidCSVError):
            logger.warning(f"Picked {kind} file can't be used: {path}", exc_info=True)
            pick = PickedFile(name, None, PDF_PROBLEM if kind == "pdf" else CSV_PROBLEM)
        self._paths[kind] = str(path)
        self._picks[kind] = pick
        self._drop_result()
        self.changed.emit()

    def clear(self, kind: str) -> None:
        if kind not in KINDS or not self._editable():
            return
        self._paths[kind] = None
        self._picks[kind] = None
        self._drop_result()
        self.changed.emit()

    def _drop_result(self) -> None:
        # They described the inputs before.
        self._result = None
        self._output = None

    def change_folder(self) -> None:
        if not self._editable():
            return
        chosen = QFileDialog.getExistingDirectory(
            self._host, "Select the output folder", str(self._folder)
        )
        if chosen:
            self._folder = Path(chosen)
            logger.info(f"Reference labels output folder changed: {chosen}")
            self.changed.emit()

    def set_open_pdf(self, on: bool) -> None:
        self._open_pdf = bool(on)
        self.changed.emit()

    # --- the run -------------------------------------------------------------

    def start(self) -> None:
        if not self._editable():
            return
        picks = self._picks
        if any(picks[kind] is None or picks[kind].problem is not None for kind in KINDS):
            return
        self._cancel.clear()
        self._last_report = 0.0
        self._started_in = self._generation
        self._run = ToolRun(pdf_processor.READING, 0, picks["pdf"].count or 0)
        worker = Worker(
            _process, self._paths["pdf"], self._paths["csv"], self._folder, self._report
        )
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._worker = worker
        logger.info(f"Starting reference label processing: {self._paths['pdf']}")
        self.changed.emit()
        (self._pool or QThreadPool.globalInstance()).start(worker)

    def _report(self, done: int, total: int, label: str) -> None:
        """The processor's progress callback. Runs on the worker thread, so
        it only raises or emits."""
        if self._cancel.is_set():
            raise ProcessingCancelled
        now = time.monotonic()
        if done < total and now - self._last_report < _REPORT_EVERY:
            return
        self._last_report = now
        self._progress.emit(done, total, label)

    def _on_progress(self, done: int, total: int, label: str) -> None:
        if self._run is None:
            return  # a report that arrived after the run finished
        self._run = ToolRun(label, done, total, self._run.cancelling)
        self.changed.emit()

    def cancel(self) -> None:
        """Stop at the next page. Nothing has been written, so nothing is left."""
        run = self._run
        if run is None or run.cancelling or run.label == pdf_processor.SAVING:
            return
        self._cancel.set()
        self._run = replace(run, cancelling=True)
        self.changed.emit()

    def _on_result(self, result: dict) -> None:
        output = Path(result["output_file"])
        if self._started_in == self._generation:
            self._result = result
            self._output = output
        logger.info(
            f"PDF processing complete: {result['matched']} matched, "
            f"{result['unmatched']} unmatched"
        )
        if self._open_pdf:
            self._open(output)
        # Duplicate or missing REFs stay on screen, in the footer, not in a toast.
        if reference_run_warning(result) is None:
            pages = result["pages_processed"]
            folder = str(output.parent)
            self.toast.emit(
                f"{pages:,} label{'' if pages == 1 else 's'} saved to {short_path(folder)}",
                folder,
            )

    def _on_error(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        if isinstance(value, ProcessingCancelled):
            logger.info("Reference label processing cancelled")
            self.toast.emit("Processing cancelled", "")
            return
        logger.error(f"PDF processing failed: {value}\n{traceback_str}")
        if isinstance(value, InvalidPDFError):
            what_to_do = (
                "The PDF couldn't be read. Check that it isn't damaged, "
                "then process it again."
            )
        elif isinstance(value, InvalidCSVError):
            what_to_do = (
                "The CSV isn't in the expected format. Expected columns: "
                "PostOne ID (0), Tracking (1), Reference (2), Name (6)."
            )
        elif isinstance(value, MappingError):
            what_to_do = (
                "Some pages didn't match a row in the CSV. Check the CSV "
                "mapping file, then process it again."
            )
        elif isinstance(value, OSError):
            what_to_do = "Can't reach this session's folder. Check the server connection."
        else:
            what_to_do = "Details are in Logs."
        show_error(self._host, "The PDF wasn't processed", what_to_do)

    def _on_finished(self) -> None:
        self._run = None
        self._worker = None
        self.changed.emit()

    # --- output --------------------------------------------------------------

    def _open(self, path: Path) -> None:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            logger.info(f"Opened PDF: {path}")
        else:
            logger.warning(f"Failed to open PDF: {path}")
            show_error(self._host, "The PDF didn't open", f"Open it manually: {path}")

    def print_output(self) -> None:
        if self._output is None or self._run is not None:
            return
        pdf_printing.print_pdf(
            self._host,
            self._output,
            pdf_printing.load_print_settings(PRINT_SCOPE["reference"]),
        )
