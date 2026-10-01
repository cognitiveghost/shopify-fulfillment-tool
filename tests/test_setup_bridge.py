"""The Setup page's bridge: every message is its own named member (ADR 0001)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.setup_bridge import SetupBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(SetupBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("chooseFile", "fileRequested"),
        ("chooseFolder", "folderRequested"),
        ("clearFile", "clearRequested"),
        ("fixProblem", "fixRequested"),
    ],
)
def test_a_card_slot_carries_its_kind_and_drops_an_unknown_one(slot, signal):
    bridge = SetupBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)("orders")
    getattr(bridge, slot)("stock")
    getattr(bridge, slot)("invoices")
    assert seen == [("orders",), ("stock",)]


def test_the_memory_switch_reports_a_bool():
    bridge = SetupBridge()
    seen = _caught(bridge.memoryToggled)
    bridge.setMemory(True)
    bridge.setMemory(False)
    assert seen == [(True,), (False,)]


def test_a_strategy_is_one_of_two_names():
    bridge = SetupBridge()
    seen = _caught(bridge.strategyChosen)
    bridge.setStrategy("fifo")
    bridge.setStrategy("multi_first")
    bridge.setStrategy("random")
    assert seen == [("fifo",), ("multi_first",)]


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("runAnalysis", "runRequested"),
        ("cancelRun", "cancelRequested"),
        ("newSession", "newSessionRequested"),
        ("openRecent", "recentRequested"),
        ("openConnection", "connectionRequested"),
    ],
)
def test_a_plain_command_emits_its_signal(slot, signal):
    bridge = SetupBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_a_state_is_announced_when_it_changes_and_only_then():
    bridge = SetupBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "setup"})
    assert len(seen) == 2
    assert bridge.state == {"view": "setup"}
