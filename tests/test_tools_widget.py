"""The Tools screen's widget: the view, the wiring, sync() (phase 5 spec 6.1).

The page itself is tested in test_tools_page.py and the tools in
test_reference_tool.py and test_barcode_tool.py. Here: the widget joins them.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog
from test_reference_tool import Pool

from gui import tools_widget
from gui.setup_state import SessionFacts
from gui.tools_widget import ToolsWidget


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window():
    """What ToolsWidget reads from the main window."""
    return SimpleNamespace(
        session_path=None,
        session_facts=None,
        current_client_id="ACME",
        analysis_results_df=None,
    )


@pytest.fixture
def tools(qtbot, window, print_settings_store, monkeypatch):
    monkeypatch.setattr(tools_widget, "installed_printers", lambda: ("Zebra ZD421",))
    widget = ToolsWidget(window, pool=Pool())
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def session(tmp_path):
    folder = tmp_path / "2026-09-30_1"
    (folder / "packing_lists").mkdir(parents=True)
    return folder


def _raised(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, action: seen.append((text, action)))
    return seen


def test_it_hosts_one_web_view_and_starts_on_the_banner(tools):
    assert tools.findChildren(QWebEngineView) == [tools.view]
    state = tools.bridge.state
    assert state["banner"] is True
    assert state["session"] == {}
    assert state["reference"]["quiet"] is True


def test_the_state_carries_this_pcs_printers_and_saved_settings(
    qtbot, window, print_settings_store, monkeypatch
):
    print_settings_store["barcode_generator"] = {
        "print_mode": "raw_zpl",
        "raw_zpl_target": "Zebra ZD421",
        "raw_zpl_rotate": True,
        "raw_zpl_invert": False,
        "raw_zpl_label_width_mm": 68.0,
        "raw_zpl_label_height_mm": 38.0,
        "driver_printer_name": "",
    }
    monkeypatch.setattr(tools_widget, "installed_printers", lambda: ("Zebra ZD421", "HP"))
    widget = ToolsWidget(window, pool=Pool())
    qtbot.addWidget(widget)
    block = widget.bridge.state["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["setup"]["summary"] == "68 × 38 mm, rotated 90°"
    assert [p["value"] for p in block["printers"]] == ["Zebra ZD421", "HP"]
    assert widget.bridge.state["reference"]["print"]["mode"] == "driver"


def test_sync_hands_a_new_session_to_both_tools(tools, window, session):
    window.session_path = str(session)
    tools.sync()
    state = tools.bridge.state
    assert state["banner"] is False
    assert state["session"] == {"name": "2026-09-30_1", "meta": "ACME"}
    assert state["reference"]["folder"]["title"] == str(session / "reference_labels")
    assert tools.barcode.facts().lists == ()


def test_the_page_head_uses_the_windows_session_facts_when_they_are_this_sessions(
    tools, window, session
):
    opened = datetime.now().astimezone().replace(hour=14, minute=2)
    window.session_path = str(session)
    window.session_facts = SessionFacts("2026-09-30_1", opened, None)
    tools.sync()
    assert tools.bridge.state["session"]["meta"] == "ACME · opened 14:02"

    # Facts read for another session say nothing about this one.
    window.session_facts = SessionFacts("2026-09-29_2", opened, None)
    tools.sync()
    assert tools.bridge.state["session"]["meta"] == "ACME"


def test_sync_with_the_same_session_keeps_the_picks(tools, window, session, tmp_path, monkeypatch):
    window.session_path = str(session)
    tools.sync()
    csv = tmp_path / "refs.csv"
    csv.write_text("a,b,c,d,e,f,g\n,,REF-1,,,,Acme\n")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a: (str(csv), ""))
    )
    tools.bridge.chooseFile("csv")
    assert tools.bridge.state["reference"]["csv"]["meta"] == "1 row"

    tools.sync()  # the shell calls this on every refresh
    assert tools.bridge.state["reference"]["csv"]["meta"] == "1 row"

    tools.bridge.clearFile("csv")
    assert tools.bridge.state["reference"]["csv"] == {}


def test_a_hidden_page_does_not_read_the_share_when_the_session_changes(
    tools, window, session
):
    window.session_path = str(session)
    tools.sync()
    assert tools.barcode._pool.started == []


def test_showing_the_page_reads_the_packing_lists(tools, window, session, qtbot):
    window.session_path = str(session)
    tools.show()
    qtbot.waitExposed(tools)
    assert len(tools.barcode._pool.started) == 1
    assert tools.bridge.state["barcode"]["list"]["placeholder"] == "Reading packing lists…"


def test_a_session_opened_while_the_page_shows_reads_its_lists(tools, window, session, qtbot):
    tools.show()
    qtbot.waitExposed(tools)
    assert tools.barcode._pool.started == []  # no session yet
    window.session_path = str(session)
    tools.sync()
    assert len(tools.barcode._pool.started) == 1


def test_a_print_edit_is_saved_for_this_pc_and_pushed(tools, print_settings_store):
    tools.bridge.setPrint("barcode", "mode", "raw_zpl")
    tools.bridge.setPrint("barcode", "printer", "Zebra ZD421")
    tools.bridge.setPrint("barcode", "width", 68)
    saved = print_settings_store["barcode_generator"]
    assert saved["print_mode"] == "raw_zpl"
    assert saved["raw_zpl_target"] == "Zebra ZD421"
    assert saved["raw_zpl_label_width_mm"] == 68.0
    assert "reference_labels" not in print_settings_store
    block = tools.bridge.state["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["printer"]["label"] == "Zebra ZD421"


def test_a_print_edit_of_the_wrong_type_saves_nothing(tools, print_settings_store):
    before = tools.bridge.state
    tools.bridge.setPrint("barcode", "width", "wide")
    tools.bridge.setPrint("reference", "mode", "fax")
    tools.bridge.setPrint("reference", "rotate", 1)
    assert print_settings_store == {}
    assert tools.bridge.state == before


def test_options_reach_their_tool(tools):
    tools.bridge.setOption("barcode", "qr", True)
    tools.bridge.setOption("barcode", "open_pdf", False)
    tools.bridge.setOption("reference", "open_pdf", False)
    state = tools.bridge.state
    assert (state["barcode"]["qr"], state["barcode"]["open_pdf"]) == (True, False)
    assert state["reference"]["open_pdf"] is False


def test_run_cancel_and_print_reach_the_right_tool(tools, monkeypatch):
    calls = []
    monkeypatch.setattr(tools.reference, "start", lambda: calls.append("reference.start"))
    monkeypatch.setattr(tools.barcode, "start", lambda: calls.append("barcode.start"))
    monkeypatch.setattr(tools.reference, "print_output", lambda: calls.append("reference.print"))
    monkeypatch.setattr(
        tools.barcode, "print_labels", lambda what: calls.append(f"barcode.print:{what}")
    )
    tools.bridge.run("reference")
    tools.bridge.run("barcode")
    tools.bridge.printLabels("reference", "labels")
    tools.bridge.printLabels("barcode", "labels")
    tools.bridge.printLabels("barcode", "qr")
    assert calls == [
        "reference.start",
        "barcode.start",
        "reference.print",
        "barcode.print:labels",
        "barcode.print:qr",
    ]


def test_a_tools_change_is_pushed(tools, window, session):
    window.session_path = str(session)
    tools.sync()
    tools.reference.set_open_pdf(False)
    assert tools.bridge.state["reference"]["open_pdf"] is False


def test_a_done_toast_while_tools_shows_offers_open_folder(tools, qtbot, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(
        tools_widget.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile())
    )
    tools.show()
    qtbot.waitExposed(tools)
    seen = _raised(tools.bridge)

    tools.bridge.openFolder()  # nothing finished yet
    assert opened == []

    tools.barcode.toast.emit("2 barcode labels saved to …/barcodes/DHL", str(tmp_path))
    assert seen == [("2 barcode labels saved to …/barcodes/DHL", True)]
    tools.bridge.openFolder()
    assert opened == [str(tmp_path)]


def test_a_done_toast_while_another_screen_shows_goes_to_the_router(tools, monkeypatch, tmp_path):
    routed = []
    monkeypatch.setattr(tools_widget, "toast", lambda source, text: routed.append(text))
    seen = _raised(tools.bridge)
    tools.reference.toast.emit("2 labels saved to …/reference_labels", str(tmp_path))
    assert routed == ["2 labels saved to …/reference_labels"]
    assert seen == []


def test_a_toast_with_no_folder_goes_to_the_router_even_on_tools(tools, qtbot, monkeypatch):
    routed = []
    monkeypatch.setattr(tools_widget, "toast", lambda source, text: routed.append(text))
    tools.show()
    qtbot.waitExposed(tools)
    tools.reference.toast.emit("Processing cancelled", "")
    assert routed == ["Processing cancelled"]


def test_the_banners_two_requests_are_passed_on(tools):
    new, recent = [], []
    tools.new_session_requested.connect(lambda: new.append(1))
    tools.recent_requested.connect(lambda: recent.append(1))
    tools.bridge.newSession()
    tools.bridge.openRecent()
    assert (new, recent) == ([1], [1])
