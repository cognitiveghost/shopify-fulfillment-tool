"""Reference labels as the Tools page runs it (phase 5 spec section 6.2).

No test runs a real Worker thread: the tool is given a pool that only captures
the worker, and the test calls the worker's function and the tool's result,
error and finished slots itself, in the order Worker emits them.
"""

import os

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget
from reportlab.pdfgen import canvas

from gui import reference_tool
from gui.reference_tool import CSV_PROBLEM, PDF_PROBLEM, ReferenceTool
from gui.tools_state import PickedFile
from shopify_tool.pdf_processor import (
    READING,
    SAVING,
    STAMPING,
    InvalidCSVError,
    InvalidPDFError,
    MappingError,
    ProcessingCancelled,
)

MAPPING = (
    "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
    ",,REF-001,,,,Acme Warehouse Co\n"
    ",,REF-002,,,,Borealis Ltd\n"
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class Pool:
    """Captures a worker instead of running it on a thread."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def opened(monkeypatch):
    """Record PDFs the tool opens instead of launching a viewer."""
    seen = []

    def open_url(url):
        seen.append(url.toLocalFile())
        return True

    monkeypatch.setattr(reference_tool.QDesktopServices, "openUrl", open_url)
    return seen


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        reference_tool, "show_error", lambda _host, headline, what: seen.append((headline, what))
    )
    return seen


@pytest.fixture
def files(tmp_path):
    """A two-page courier PDF, its mapping CSV, and a session folder."""
    pdf = tmp_path / "dhl-labels.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(288, 432))
    c.drawString(20, 400, "Acme Warehouse Co")
    c.showPage()
    c.drawString(20, 400, "Borealis Ltd")
    c.showPage()
    c.save()
    csv = tmp_path / "refs.csv"
    csv.write_text(MAPPING)
    session = tmp_path / "2026-09-30_1"
    session.mkdir()
    return str(pdf), str(csv), str(session)


def _tool(host, session=None):
    pool = Pool()
    tool = ReferenceTool(host, pool)
    if session:
        tool.set_session(session)
    return tool, pool


def _ready(host, files):
    pdf, csv, session = files
    tool, pool = _tool(host, session)
    tool.load("pdf", pdf)
    tool.load("csv", csv)
    return tool, pool


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def _finish(tool, pool):
    """Run the captured worker's function here and hand the tool its result,
    as Worker would: result, then finished."""
    worker = pool.started[-1]
    result = worker.fn(*worker.args, **worker.kwargs)
    tool._on_result(result)
    tool._on_finished()
    return result


# --- session and picks --------------------------------------------------------


def test_a_new_tool_has_no_session_and_no_picks(host):
    tool, _pool = _tool(host)
    facts = tool.facts()
    assert (facts.pdf, facts.csv, facts.folder, facts.run, facts.result) == (
        None,
        None,
        "",
        None,
        None,
    )
    assert facts.open_pdf is True and facts.has_output is False


def test_a_session_sets_the_folder_without_touching_the_share(host, tmp_path):
    tool, _pool = _tool(host)
    session = tmp_path / "not-created-yet"
    tool.set_session(str(session))
    assert tool.facts().folder == str(session / "reference_labels")
    assert not session.exists()


def test_a_good_pdf_and_csv_are_counted(host, files):
    tool, _pool = _ready(host, files)
    facts = tool.facts()
    assert facts.pdf == PickedFile("dhl-labels.pdf", 2)
    assert facts.csv == PickedFile("refs.csv", 2)


def test_a_file_that_is_not_a_pdf_is_flagged(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    bad = tmp_path / "notes.pdf"
    bad.write_text("not a pdf")
    tool.load("pdf", str(bad))
    assert tool.facts().pdf == PickedFile("notes.pdf", None, PDF_PROBLEM)


def test_a_csv_with_no_usable_rows_is_flagged(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    bad = tmp_path / "orders.csv"
    bad.write_text("Order,Tracking,Date\n#1,TR1,2026-09-30\n")
    tool.load("csv", str(bad))
    assert tool.facts().csv == PickedFile("orders.csv", None, CSV_PROBLEM)


def test_a_pick_that_vanished_before_the_check_is_flagged_not_raised(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    tool.load("pdf", str(tmp_path / "gone.pdf"))
    tool.load("csv", str(tmp_path / "gone.csv"))
    assert tool.facts().pdf.problem == PDF_PROBLEM
    assert tool.facts().csv.problem == CSV_PROBLEM


def test_with_no_session_nothing_loads(host, files):
    pdf, _csv, _session = files
    tool, _pool = _tool(host)
    tool.load("pdf", pdf)
    assert tool.facts().pdf is None


def test_every_change_is_announced(host, files):
    pdf, _csv, session = files
    tool, _pool = _tool(host)
    seen = _caught(tool.changed)
    tool.set_session(session)
    tool.load("pdf", pdf)
    tool.clear("pdf")
    tool.set_open_pdf(False)
    assert len(seen) == 4
    assert tool.facts().open_pdf is False


def test_a_session_change_clears_the_picks_and_the_result(host, files, opened, tmp_path):
    tool, pool = _ready(host, files)
    tool.start()
    _finish(tool, pool)
    assert tool.facts().has_output is True

    other = tmp_path / "2026-10-01_1"
    tool.set_session(str(other))
    facts = tool.facts()
    assert (facts.pdf, facts.csv, facts.result, facts.has_output) == (None, None, None, False)
    assert facts.folder == str(other / "reference_labels")

    tool.set_session(None)
    assert tool.facts().folder == ""


def test_choose_opens_a_dialog_and_loads_what_was_picked(host, files, monkeypatch):
    pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    asked = []

    def pick(parent, title, start, pattern):
        asked.append((title, pattern))
        return pdf, pattern

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(pick))
    tool.choose("pdf")
    assert asked == [("Select the labels PDF", "PDF Files (*.pdf)")]
    assert tool.facts().pdf.count == 2


def test_a_cancelled_dialog_changes_nothing(host, files, monkeypatch):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a: ("", "")))
    seen = _caught(tool.changed)
    tool.choose("csv")
    assert seen == [] and tool.facts().csv is None


def test_change_folder_takes_the_chosen_folder_until_the_session_changes(
    host, files, monkeypatch, tmp_path
):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(elsewhere))
    )
    tool.change_folder()
    assert tool.facts().folder == str(elsewhere)
    tool.set_session(session)
    assert tool.facts().folder == os.path.join(session, "reference_labels")


# --- the run ------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["pdf", "csv"])
def test_start_does_nothing_until_both_files_are_good(host, files, missing):
    tool, pool = _ready(host, files)
    tool.clear(missing)
    tool.start()
    assert pool.started == [] and tool.facts().run is None


def test_start_does_nothing_with_a_problem_file(host, files, tmp_path):
    tool, pool = _ready(host, files)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    tool.load("csv", str(bad))
    tool.start()
    assert pool.started == []


def test_start_hands_one_worker_to_the_pool_and_shows_the_first_phase(host, files):
    tool, pool = _ready(host, files)
    tool.start()
    assert len(pool.started) == 1
    run = tool.facts().run
    assert (run.label, run.done, run.total, run.cancelling) == (READING, 0, 2, False)
    tool.start()  # a second click while running
    assert len(pool.started) == 1


def test_inputs_cannot_change_while_running(host, files):
    pdf, _csv, _session = files
    tool, _pool = _ready(host, files)
    tool.start()
    tool.clear("pdf")
    tool.load("csv", pdf)
    assert tool.facts().pdf.count == 2
    assert tool.facts().csv.name == "refs.csv"


def test_a_finished_run_keeps_its_result_opens_the_pdf_and_toasts(host, files, opened):
    _pdf, _csv, session = files
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    result = _finish(tool, pool)

    folder = os.path.join(session, "reference_labels")
    assert os.path.dirname(result["output_file"]) == folder  # the worker made it
    facts = tool.facts()
    assert facts.run is None
    assert facts.result == result
    assert facts.has_output is True
    assert opened == [result["output_file"]]
    assert toasts == [
        (f"2 labels saved to …{os.sep}2026-09-30_1{os.sep}reference_labels", folder)
    ]


def test_with_open_pdf_off_nothing_is_opened(host, files, opened):
    tool, pool = _ready(host, files)
    tool.set_open_pdf(False)
    tool.start()
    _finish(tool, pool)
    assert opened == []


def test_a_run_that_needs_checking_raises_no_toast(host, files, opened):
    tool, _pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    result = {
        "output_file": os.path.join(files[2], "reference_labels", "out.pdf"),
        "pages_processed": 2,
        "matched": 2,
        "unmatched": 0,
        "duplicate_refs": ["REF-001"],
        "missing_refs": [],
        "name_matched": 0,
    }
    tool._on_result(result)
    tool._on_finished()
    assert toasts == []
    assert tool.facts().result == result


def test_a_pdf_that_will_not_open_says_where_it_is(host, files, errors, monkeypatch):
    monkeypatch.setattr(reference_tool.QDesktopServices, "openUrl", lambda url: False)
    tool, pool = _ready(host, files)
    tool.start()
    result = _finish(tool, pool)
    assert errors == [("The PDF didn't open", f"Open it manually: {result['output_file']}")]


def test_progress_reaches_the_facts(host, files):
    tool, _pool = _ready(host, files)
    tool.start()
    tool._on_progress(1, 2, STAMPING)
    run = tool.facts().run
    assert (run.label, run.done, run.total) == (STAMPING, 1, 2)


def test_a_late_progress_report_after_the_run_is_ignored(host, files, opened):
    tool, pool = _ready(host, files)
    tool.start()
    _finish(tool, pool)
    tool._on_progress(2, 2, STAMPING)
    assert tool.facts().run is None


def test_reports_are_throttled_but_a_phases_last_one_always_gets_through(
    host, files, monkeypatch
):
    tool, _pool = _ready(host, files)
    tool.start()
    seen = _caught(tool._progress)
    clock = iter([10.0, 10.01, 10.02, 10.5])
    monkeypatch.setattr(reference_tool.time, "monotonic", lambda: next(clock))
    tool._report(1, 100, READING)  # first: through
    tool._report(2, 100, READING)  # 10 ms later: dropped
    tool._report(100, 100, READING)  # the phase's last: through
    tool._report(1, 100, STAMPING)  # 480 ms later: through
    assert seen == [(1, 100, READING), (100, 100, READING), (1, 100, STAMPING)]


def test_cancel_marks_the_run_and_stops_it_at_the_next_report(host, files):
    tool, _pool = _ready(host, files)
    tool.start()
    tool.cancel()
    assert tool.facts().run.cancelling is True
    with pytest.raises(ProcessingCancelled):
        tool._report(1, 2, READING)


def test_a_cancelled_run_writes_nothing_toasts_and_shows_no_error(host, files, errors, opened):
    _pdf, _csv, session = files
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool.cancel()
    worker = pool.started[-1]
    with pytest.raises(ProcessingCancelled) as caught:
        worker.fn(*worker.args, **worker.kwargs)
    tool._on_error((ProcessingCancelled, caught.value, "trace"))
    tool._on_finished()

    assert os.listdir(os.path.join(session, "reference_labels")) == []
    assert toasts == [("Processing cancelled", "")]
    assert errors == []
    facts = tool.facts()
    assert (facts.run, facts.result, facts.has_output) == (None, None, False)
    assert facts.pdf.count == 2  # the picks stay, ready to run again


def test_cancel_does_nothing_when_idle_or_once_saving(host, files):
    tool, _pool = _ready(host, files)
    tool.cancel()
    assert tool.facts().run is None
    tool.start()
    tool._on_progress(2, 2, SAVING)
    tool.cancel()
    assert tool.facts().run.cancelling is False
    tool._report(2, 2, SAVING)  # does not raise


def test_a_second_run_is_not_cancelled_by_the_first_ones_cancel(host, files, opened):
    tool, pool = _ready(host, files)
    tool.start()
    tool.cancel()
    tool._on_error((ProcessingCancelled, ProcessingCancelled(), ""))
    tool._on_finished()
    tool.start()
    result = _finish(tool, pool)
    assert result["pages_processed"] == 2


@pytest.mark.parametrize(
    ("error", "what"),
    [
        (
            InvalidPDFError("x"),
            "The PDF couldn't be read. Check that it isn't damaged, then process it again.",
        ),
        (
            InvalidCSVError("x"),
            (
                "The CSV isn't in the expected format. Expected columns: "
                "PostOne ID (1st), Tracking (2nd), Reference (3rd), Name (7th)."
            ),
        ),
        (
            MappingError("x"),
            (
                "Some pages didn't match a row in the CSV. Check the CSV "
                "mapping file, then process it again."
            ),
        ),
        (
            PermissionError("share gone"),
            "Can't reach this session's folder. Check the server connection.",
        ),
        (RuntimeError("boom"), "Details are in Logs."),
    ],
)
def test_a_failed_run_says_what_to_do(host, files, errors, error, what):
    tool, _pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool._on_error((type(error), error, "trace"))
    tool._on_finished()
    assert errors == [("The PDF wasn't processed", what)]
    assert toasts == []
    assert tool.facts().run is None


def test_a_run_that_outlives_its_session_does_not_leave_its_result_behind(
    host, files, opened, tmp_path
):
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool.set_session(str(tmp_path / "2026-10-01_1"))
    _finish(tool, pool)
    facts = tool.facts()
    assert (facts.result, facts.has_output) == (None, False)
    assert len(toasts) == 1  # the labels were still written, and the toast says where


# --- print --------------------------------------------------------------------


def test_print_sends_the_output_with_the_reference_scopes_settings(
    host, files, opened, monkeypatch
):
    tool, pool = _ready(host, files)
    calls = []
    monkeypatch.setattr(
        reference_tool.pdf_printing, "load_print_settings", lambda scope: {"scope": scope}
    )
    monkeypatch.setattr(
        reference_tool.pdf_printing,
        "print_pdf",
        lambda parent, path, settings: calls.append((path, settings)),
    )
    tool.print_output()  # nothing to print yet
    assert calls == []
    tool.start()
    result = _finish(tool, pool)
    tool.print_output()
    assert [(str(path), settings) for path, settings in calls] == [
        (result["output_file"], {"scope": "reference_labels"})
    ]
