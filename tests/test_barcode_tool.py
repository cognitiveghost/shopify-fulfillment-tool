"""Barcode labels as the Tools page runs it (phase 5 spec section 6.3).

No test runs a real Worker thread: the tool is given a pool that only captures
the worker, and the test calls the worker's function and the tool's slots
itself, in the order Worker emits them.
"""

import os

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QWidget
from test_reference_tool import Pool

from gui import barcode_tool
from gui.barcode_tool import BarcodeTool, read_packing_lists
from gui.tools_state import PackingList
from shopify_tool.barcode_processor import BarcodeGenerationError


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture(autouse=True)
def fresh_cache():
    barcode_tool._ORDERS_CACHE.clear()
    yield
    barcode_tool._ORDERS_CACHE.clear()


@pytest.fixture
def opened(monkeypatch):
    seen = []

    def open_url(url):
        seen.append(url.toLocalFile())
        return True

    monkeypatch.setattr(barcode_tool.QDesktopServices, "openUrl", open_url)
    return seen


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        barcode_tool, "show_error", lambda _host, headline, what: seen.append((headline, what))
    )
    return seen


def _analysis():
    """Four orders: #1 and #2 Fulfillable on DHL, #3 Fulfillable on DPD, #4 blocked."""
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3", "#4"],
            "SKU": ["A", "B", "A", "C", "A"],
            "Quantity": [1, 2, 1, 4, 1],
            "Shipping_Provider": ["DHL", "DHL", "DHL", "DPD", "DHL"],
            "Destination_Country": ["DE", "DE", "BG", "BG", "DE"],
            "Internal_Tags": ["[]", "[]", "[]", "[]", "[]"],
            "Order_Fulfillment_Status": [
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Not Fulfillable",
            ],
        }
    )


def _write_list(session, name, orders):
    folder = session / "packing_lists"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.xlsx"
    pd.DataFrame({"Order_Number": orders}).to_excel(path, index=False)
    return path


@pytest.fixture
def session(tmp_path):
    """A session with two packing lists: DHL (#1, #2, #4) and DPD (#3)."""
    folder = tmp_path / "2026-09-30_1"
    folder.mkdir()
    _write_list(folder, "DHL", ["#1", "#1", "#2", "#4"])
    _write_list(folder, "DPD", ["#3"])
    return folder


def _tool(host, session=None, frame="default"):
    pool = Pool()
    held = {"frame": _analysis() if isinstance(frame, str) else frame}
    tool = BarcodeTool(host, lambda: held["frame"], pool)
    if session is not None:
        tool.set_session(str(session))
    return tool, pool, held


def _load(tool, pool):
    """Reload the lists as the worker would: run its function, hand back the result."""
    tool.reload()
    worker = pool.started[-1]
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))


def _loaded(host, session):
    tool, pool, held = _tool(host, session)
    _load(tool, pool)
    return tool, pool, held


def _generate(tool, pool):
    """Run the captured generation here: result, then finished."""
    worker = pool.started[-1]
    outcome = worker.fn(*worker.args, **worker.kwargs)
    tool._on_result(outcome)
    tool._on_finished()
    return outcome


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


# --- reading the lists --------------------------------------------------------


def test_a_list_counts_its_fulfillable_orders(session):
    found = read_packing_lists(str(session), _analysis())
    assert [entry for entry, _orders in found] == [
        PackingList("DHL", 2, False, False),  # #4 is on the list but blocked
        PackingList("DPD", 1, False, False),
    ]
    assert found[0][1] == frozenset({"#1", "#2", "#4"})


def test_a_session_with_no_packing_lists_folder_has_none(tmp_path):
    assert read_packing_lists(str(tmp_path), _analysis()) == []


def test_with_no_analysis_the_lists_are_named_but_not_counted(session):
    found = read_packing_lists(str(session), None)
    assert [(entry.name, entry.count) for entry, _orders in found] == [("DHL", None), ("DPD", None)]


def test_a_workbook_that_cannot_be_read_is_listed_as_unreadable(session):
    (session / "packing_lists" / "Broken.xlsx").write_text("not a workbook")
    pd.DataFrame({"SKU": ["A"]}).to_excel(session / "packing_lists" / "NoOrders.xlsx", index=False)
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert found["Broken"].count is None
    assert found["NoOrders"].count is None
    assert found["DHL"].count == 2


def test_excels_lock_file_is_not_a_packing_list(session):
    (session / "packing_lists" / "~$DHL.xlsx").write_text("lock")
    names = [entry.name for entry, _orders in read_packing_lists(str(session), _analysis())]
    assert names == ["DHL", "DPD"]


def test_label_pdfs_on_disk_are_seen(session):
    labels = session / "barcodes" / "DHL"
    labels.mkdir(parents=True)
    (labels / "DHL_barcodes.pdf").write_bytes(b"%PDF")
    (labels / "DHL_qr_labels.pdf").write_bytes(b"%PDF")
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert (found["DHL"].has_labels, found["DHL"].has_qr) == (True, True)
    assert (found["DPD"].has_labels, found["DPD"].has_qr) == (False, False)


def test_an_unchanged_workbook_is_read_once(session, monkeypatch):
    reads = []
    real = barcode_tool.packing_list_orders

    def counting(path):
        reads.append(os.path.basename(str(path)))
        return real(path)

    monkeypatch.setattr(barcode_tool, "packing_list_orders", counting)
    read_packing_lists(str(session), _analysis())
    read_packing_lists(str(session), _analysis())
    assert sorted(reads) == ["DHL.xlsx", "DPD.xlsx"]

    # A list written again is read again.
    path = _write_list(session, "DPD", ["#3", "#2"])
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert reads.count("DPD.xlsx") == 2
    assert found["DPD"].count == 2


# --- the tool: session and lists ---------------------------------------------


def test_a_new_tool_has_nothing(host):
    tool, _pool, _held = _tool(host)
    facts = tool.facts()
    assert (facts.lists, facts.selected, facts.folder, facts.loading) == ((), "", "", False)
    assert (facts.qr, facts.open_pdf, facts.run, facts.result) == (False, True, None, None)


def test_reload_without_a_session_does_nothing(host):
    tool, pool, _held = _tool(host)
    tool.reload()
    assert pool.started == []


def test_reload_reads_on_a_worker_and_selects_the_first_list(host, session):
    tool, pool, _held = _tool(host, session)
    seen = _caught(tool.changed)
    tool.reload()
    assert tool.facts().loading is True
    assert len(pool.started) == 1 and len(seen) == 1
    tool.reload()  # already loading
    assert len(pool.started) == 1

    worker = pool.started[-1]
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))
    facts = tool.facts()
    assert facts.loading is False
    assert [entry.name for entry in facts.lists] == ["DHL", "DPD"]
    assert facts.selected == "DHL"
    assert facts.folder == str(session / "barcodes" / "DHL")
    assert facts.analysed is True


def test_a_reload_keeps_the_selection_when_the_list_is_still_there(host, session):
    tool, pool, _held = _loaded(host, session)
    tool.choose("DPD")
    _load(tool, pool)
    assert tool.facts().selected == "DPD"


def test_a_reload_moves_to_the_first_list_when_the_selected_one_is_gone(host, session):
    tool, pool, _held = _loaded(host, session)
    tool.choose("DPD")
    (session / "packing_lists" / "DPD.xlsx").unlink()
    _load(tool, pool)
    assert tool.facts().selected == "DHL"


def test_lists_that_arrive_for_a_session_the_operator_left_are_dropped(host, session, tmp_path):
    tool, pool, _held = _tool(host, session)
    tool.reload()
    worker = pool.started[-1]
    other = tmp_path / "2026-10-01_1"
    other.mkdir()
    tool.set_session(str(other))
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))
    assert tool.facts().lists == ()
    # ...and the new session can load at once.
    tool.reload()
    assert len(pool.started) == 2


def test_with_no_analysis_the_facts_say_so(host, session):
    tool, pool, _held = _tool(host, session, frame=None)
    _load(tool, pool)
    facts = tool.facts()
    assert facts.analysed is False
    assert [entry.count for entry in facts.lists] == [None, None]


@pytest.fixture
def share_gone(monkeypatch):
    def gone(session_path, analysis_df):
        raise OSError("share gone")

    monkeypatch.setattr(barcode_tool, "read_packing_lists", gone)


def test_a_failed_reload_stops_loading_and_says_so(host, session, errors, share_gone):
    tool, pool, _held = _tool(host, session)
    _load(tool, pool)
    assert tool.facts().loading is False
    assert errors == [
        ("The packing lists weren't read", "Check the server connection, then Refresh.")
    ]


def test_a_failed_reload_for_a_session_left_behind_says_nothing(
    host, session, tmp_path, errors, share_gone
):
    tool, pool, _held = _tool(host, session)
    tool.reload()
    tool.set_session(str(tmp_path / "another"))
    tool.reload()
    stale = pool.started[0]
    tool._on_lists(stale.fn(*stale.args, **stale.kwargs))
    assert tool.facts().loading is True  # the new session's own read is still out
    assert errors == []


def test_choose_selects_a_list_that_exists(host, session):
    tool, _pool, _held = _loaded(host, session)
    seen = _caught(tool.changed)
    tool.choose("DPD")
    tool.choose("Royal Mail")
    tool.choose("DPD")
    assert tool.facts().selected == "DPD"
    assert len(seen) == 1


def test_options(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.set_option("qr", True)
    tool.set_option("open_pdf", False)
    tool.set_option("locked", True)
    facts = tool.facts()
    assert (facts.qr, facts.open_pdf) == (True, False)


def test_a_session_change_forgets_the_lists(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.set_session(None)
    facts = tool.facts()
    assert (facts.lists, facts.selected, facts.folder) == ((), "", "")


# --- the run ------------------------------------------------------------------


def test_start_does_nothing_without_a_list_with_orders(host, session):
    tool, pool, held = _tool(host, session)
    tool.start()  # nothing loaded
    assert pool.started == []

    _load(tool, pool)
    before = len(pool.started)
    held["frame"] = None
    tool.start()  # no analysis
    assert len(pool.started) == before


def test_start_writes_the_selected_lists_fulfillable_orders(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    run = tool.facts().run
    assert run.label == "Preparing 2 labels…" and run.total == 0
    tool.start()  # a second click while running
    assert len(pool.started) == 2  # the list load, and one generation

    tool._on_progress("Writing 2 barcode labels…")
    assert tool.facts().run.label == "Writing 2 barcode labels…"

    outcome = _generate(tool, pool)
    folder = str(session / "barcodes" / "DHL")
    assert (outcome["list"], outcome["folder"], outcome["labels"]) == ("DHL", folder, 2)
    assert os.path.exists(outcome["pdf"])

    facts = tool.facts()
    assert facts.run is None
    assert facts.result == outcome
    assert facts.lists[0] == PackingList("DHL", 2, True, False)
    assert opened == [outcome["pdf"]]
    assert toasts == [(f"2 barcode labels saved to …{os.sep}barcodes{os.sep}DHL", folder)]


def test_with_qr_both_pdfs_are_written_opened_and_named_in_the_toast(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.set_option("qr", True)
    toasts = _caught(tool.toast)
    tool.start()
    outcome = _generate(tool, pool)
    assert opened == [outcome["pdf"], outcome["qr_pdf"]]
    assert toasts[0][0] == (
        f"2 barcode labels saved to …{os.sep}barcodes{os.sep}DHL. QR labels too."
    )
    assert tool.facts().lists[0].has_qr is True


def test_with_open_pdf_off_nothing_is_opened(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.set_option("open_pdf", False)
    tool.start()
    _generate(tool, pool)
    assert opened == []


def test_the_list_cannot_change_while_it_runs(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.start()
    tool.choose("DPD")
    assert tool.facts().selected == "DHL"


def test_replacing_existing_labels_asks_first(host, session, opened, monkeypatch):
    tool, pool, _held = _loaded(host, session)
    tool.start()
    _generate(tool, pool)
    started = len(pool.started)

    asked = []

    def ask(parent, *, title, body, verb):
        asked.append((title, body, verb))
        return False

    monkeypatch.setattr(barcode_tool.ConfirmDialog, "ask", staticmethod(ask))
    tool.start()
    assert asked == [
        (
            "Replace barcodes for DHL?",
            "The existing PDF is overwritten with 2 new barcodes. This cannot be undone.",
            "Replace barcodes",
        )
    ]
    assert len(pool.started) == started  # No: nothing started
    assert tool.facts().run is None

    monkeypatch.setattr(barcode_tool.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    tool.start()
    assert len(pool.started) == started + 1


def test_order_numbers_that_cannot_be_encoded_stay_in_the_result(host, tmp_path, opened):
    session = tmp_path / "2026-09-30_1"
    session.mkdir()
    _write_list(session, "DHL", ["#1", "!!!"])
    frame = _analysis()
    frame.loc[2, "Order_Number"] = "!!!"
    tool, pool, _held = _tool(host, session, frame=frame)
    _load(tool, pool)
    tool.start()
    outcome = _generate(tool, pool)
    assert (outcome["labels"], outcome["failed"]) == (1, 1)
    assert tool.facts().result == outcome


def test_a_render_failure_shows_the_error_and_no_toast(host, session, errors, monkeypatch):
    tool, _pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    error = BarcodeGenerationError("renderer down")
    tool._on_error((type(error), error, "trace"))
    tool._on_finished()
    assert errors == [("The barcode PDF wasn't created", "Details are in Logs.")]
    assert toasts == []
    facts = tool.facts()
    assert facts.run is None and facts.result is None
    assert facts.lists[0].has_labels is False


def test_a_run_that_outlives_its_session_still_toasts_but_keeps_no_result(
    host, session, opened, tmp_path
):
    tool, pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    other = tmp_path / "2026-10-01_1"
    other.mkdir()
    tool.set_session(str(other))
    outcome = _generate(tool, pool)
    # Written where the run was started, not into the new session.
    assert outcome["folder"] == str(session / "barcodes" / "DHL")
    assert tool.facts().result is None
    assert len(toasts) == 1


def test_a_late_progress_report_after_the_run_is_ignored(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.start()
    _generate(tool, pool)
    tool._on_progress("Writing 2 QR labels…")
    assert tool.facts().run is None


# --- print --------------------------------------------------------------------


def test_print_sends_the_selected_lists_pdf_with_the_barcode_scopes_settings(
    host, session, monkeypatch
):
    tool, _pool, _held = _loaded(host, session)
    calls = []
    monkeypatch.setattr(
        barcode_tool.pdf_printing, "load_print_settings", lambda scope: {"scope": scope}
    )
    monkeypatch.setattr(
        barcode_tool.pdf_printing,
        "print_pdf",
        lambda parent, path, settings: calls.append((str(path), settings)),
    )
    tool.print_labels("labels")
    tool.choose("DPD")
    tool.print_labels("qr")
    assert calls == [
        (str(session / "barcodes" / "DHL" / "DHL_barcodes.pdf"), {"scope": "barcode_generator"}),
        (str(session / "barcodes" / "DPD" / "DPD_qr_labels.pdf"), {"scope": "barcode_generator"}),
    ]


def test_print_does_nothing_with_no_list(host, monkeypatch):
    tool, _pool, _held = _tool(host)
    calls = []
    monkeypatch.setattr(barcode_tool.pdf_printing, "print_pdf", lambda *a: calls.append(a))
    tool.print_labels("labels")
    assert calls == []
