"""The Tools page's bridge: every message is its own named member (phase 5 spec 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.tools_bridge import ToolsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(ToolsBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [("chooseFile", "fileRequested"), ("clearFile", "clearRequested")],
)
def test_a_file_slot_carries_its_kind_and_drops_an_unknown_one(slot, signal):
    bridge = ToolsBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)("pdf")
    getattr(bridge, slot)("csv")
    getattr(bridge, slot)("xlsx")
    assert seen == [("pdf",), ("csv",)]


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("changeFolder", "folderRequested"),
        ("refreshLists", "listsRequested"),
        ("cancel", "cancelRequested"),
        ("openFolder", "folderOpenRequested"),
        ("newSession", "newSessionRequested"),
        ("openRecent", "recentRequested"),
    ],
)
def test_a_plain_request_emits_its_signal(slot, signal):
    bridge = ToolsBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_an_option_is_one_of_three_pairs():
    bridge = ToolsBridge()
    seen = _caught(bridge.optionChanged)
    bridge.setOption("reference", "open_pdf", False)
    bridge.setOption("barcode", "open_pdf", True)
    bridge.setOption("barcode", "qr", True)
    bridge.setOption("reference", "qr", True)
    bridge.setOption("labels", "open_pdf", True)
    bridge.setOption("barcode", "locked", True)
    assert seen == [
        ("reference", "open_pdf", False),
        ("barcode", "open_pdf", True),
        ("barcode", "qr", True),
    ]


def test_a_print_edit_carries_its_value_as_it_came():
    bridge = ToolsBridge()
    seen = _caught(bridge.printChanged)
    bridge.setPrint("reference", "mode", "raw_zpl")
    bridge.setPrint("barcode", "width", 68.5)
    bridge.setPrint("barcode", "rotate", True)
    assert seen == [
        ("reference", "mode", "raw_zpl"),
        ("barcode", "width", 68.5),
        ("barcode", "rotate", True),
    ]


def test_a_print_edit_for_an_unknown_tool_or_key_is_dropped():
    bridge = ToolsBridge()
    seen = _caught(bridge.printChanged)
    bridge.setPrint("labels", "mode", "driver")
    bridge.setPrint("reference", "print_mode", "driver")
    bridge.setPrint("reference", "raw_zpl_target", "x")
    assert seen == []


def test_a_packing_list_is_named_and_an_empty_name_is_dropped():
    bridge = ToolsBridge()
    seen = _caught(bridge.listChosen)
    bridge.chooseList("DHL")
    bridge.chooseList("")
    assert seen == [("DHL",)]


def test_run_names_a_tool():
    bridge = ToolsBridge()
    seen = _caught(bridge.runRequested)
    bridge.run("reference")
    bridge.run("barcode")
    bridge.run("everything")
    assert seen == [("reference",), ("barcode",)]


def test_print_names_a_tool_and_what_to_print():
    bridge = ToolsBridge()
    seen = _caught(bridge.printRequested)
    bridge.printLabels("reference", "labels")
    bridge.printLabels("barcode", "labels")
    bridge.printLabels("barcode", "qr")
    bridge.printLabels("reference", "qr")
    bridge.printLabels("barcode", "invoices")
    assert seen == [("reference", "labels"), ("barcode", "labels"), ("barcode", "qr")]


def test_set_state_announces_a_change_once_and_never_the_same_state_twice():
    bridge = ToolsBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"banner": True})
    bridge.set_state({"banner": True})
    bridge.set_state({"banner": False})
    assert len(seen) == 2
    assert bridge.state == {"banner": False}
