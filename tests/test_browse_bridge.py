"""The Browse page's bridge: every message is its own named member (ADR 0001)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.browse_bridge import BrowseBridge
from gui.web_page import PageBridge
from shopify_tool.session_manager import SessionManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(BrowseBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("refresh", "refreshRequested"),
        ("newSession", "newSessionRequested"),
        ("undo", "undoRequested"),
    ],
)
def test_a_plain_command_emits_its_signal(slot, signal):
    bridge = BrowseBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_open_carries_the_session_name_and_drops_an_empty_one():
    bridge = BrowseBridge()
    seen = _caught(bridge.openRequested)
    bridge.openSession("2026-09-30_1")
    bridge.openSession("")
    assert seen == [("2026-09-30_1",)]


def test_a_status_is_one_of_the_four_a_person_can_set():
    bridge = BrowseBridge()
    seen = _caught(bridge.statusRequested)
    for status in [*SessionManager.VALID_STATUSES, "frozen", "in_progress", ""]:
        bridge.setStatus(["a", "b"], status)
    assert seen == [(["a", "b"], status) for status in SessionManager.VALID_STATUSES]


def test_names_that_are_not_strings_are_dropped():
    bridge = BrowseBridge()
    seen = _caught(bridge.statusRequested)
    bridge.setStatus(["a", 7, "", None, "b"], "archived")
    bridge.setStatus([], "archived")
    bridge.setStatus([7, None], "archived")
    bridge.setStatus("2026-09-30_1", "archived")
    assert seen == [(["a", "b"], "archived")]


def test_a_comment_carries_its_text_and_an_empty_one_clears():
    bridge = BrowseBridge()
    seen = _caught(bridge.commentRequested)
    bridge.setComment(["a"], "late van")
    bridge.setComment(["a", "b"], "")
    bridge.setComment([], "nobody")
    assert seen == [(["a"], "late van"), (["a", "b"], "")]


def test_a_combined_export_needs_two_sessions():
    bridge = BrowseBridge()
    seen = _caught(bridge.exportRequested)
    bridge.exportCombined(["a"])
    bridge.exportCombined(["a", ""])
    bridge.exportCombined(["a", "b"])
    assert seen == [(["a", "b"],)]


def test_a_state_is_announced_when_it_changes_and_only_then():
    bridge = BrowseBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "loading"})
    assert len(seen) == 2
    assert bridge.state == {"view": "loading"}
