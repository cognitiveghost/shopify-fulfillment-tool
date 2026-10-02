"""The Logs page's bridge: every message is its own named member (phase 6 spec 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.log_buffer import CAPACITY
from gui.logs_bridge import LogsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(LogsBridge, PageBridge)


def test_it_tells_the_page_the_capacity_and_whether_wrap_starts_on():
    assert LogsBridge().capacity == CAPACITY
    assert LogsBridge().wrap is False
    bridge = LogsBridge(wrap=True, capacity=3)
    assert bridge.capacity == 3
    assert bridge.wrap is True


def test_send_emits_one_batch_and_nothing_for_an_empty_one():
    bridge = LogsBridge()
    seen = _caught(bridge.entriesAdded)
    bridge.send([{"id": 0}, {"id": 1}])
    bridge.send([])
    assert seen == [([{"id": 0}, {"id": 1}],)]


def test_start_is_a_request_python_hears():
    bridge = LogsBridge()
    seen = _caught(bridge.started)
    bridge.start()
    assert seen == [()]


def test_save_shown_keeps_whole_numbers_only():
    bridge = LogsBridge()
    seen = _caught(bridge.saveRequested)
    bridge.saveShown([0, 2.0, 7, "3", 1.5, None, True, float("nan"), float("inf")])
    assert seen == [([0, 2, 7],)]
    assert all(type(value) is int for value in seen[0][0])


def test_copy_traceback_carries_the_id():
    bridge = LogsBridge()
    seen = _caught(bridge.copyRequested)
    bridge.copyTraceback(12)
    assert seen == [(12,)]


def test_set_wrap_carries_the_choice():
    bridge = LogsBridge()
    seen = _caught(bridge.wrapRequested)
    bridge.setWrap(True)
    bridge.setWrap(False)
    assert seen == [(True,), (False,)]
