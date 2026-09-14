"""Bundle 14: the toast the page draws itself (ADR 0007)."""

import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _text(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"(document.querySelector({selector!r}) || {{textContent: null}}).textContent",
    )


def _wait_until(qtbot, view, expr, timeout_ms=6000):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _eval(qtbot, view, expr) is True:
            return
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def test_a_toast_shows_its_text(qtbot, page):
    view, bridge = page
    bridge.raise_toast("3 orders held")
    assert _text(qtbot, view, "#toast-text") == "3 orders held"
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is False


def test_an_undoable_toast_offers_undo(qtbot, page):
    view, bridge = page
    bridge.set_undo_available(True)
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    _until_js(qtbot, view, "document.getElementById('toast-undo').hidden === false")


def test_undo_is_hidden_when_nothing_can_be_undone(qtbot, page):
    view, bridge = page
    bridge.set_undo_available(False)
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    assert _eval(qtbot, view, "document.getElementById('toast-undo').hidden") is True


def test_a_non_undoable_toast_never_offers_undo(qtbot, page):
    view, bridge = page
    bridge.set_undo_available(True)
    bridge.raise_toast("3 order numbers copied")
    assert _eval(qtbot, view, "document.getElementById('toast-undo').hidden") is True


def test_undo_calls_the_bridge_and_dismisses(qtbot, page):
    view, bridge = page
    bridge.set_undo_available(True)
    bridge.raise_toast("3 orders held", undoable=True)
    with qtbot.waitSignal(bridge.undoRequested, timeout=3000):
        _eval(qtbot, view, "document.getElementById('toast-undo').click(); true")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_the_newest_replaces_the_oldest(qtbot, page):
    view, bridge = page
    bridge.raise_toast("first")
    bridge.raise_toast("second")
    assert _text(qtbot, view, "#toast-text") == "second"
    assert _eval(qtbot, view, "document.querySelectorAll('#toast').length") == 1


def test_the_badge_counts_from_the_third_in_a_run(qtbot, page):
    view, bridge = page
    bridge.raise_toast("one")
    assert _eval(qtbot, view, "document.getElementById('toast-badge').hidden") is True
    bridge.raise_toast("two")
    assert _eval(qtbot, view, "document.getElementById('toast-badge').hidden") is True
    bridge.raise_toast("three")
    assert _text(qtbot, view, "#toast-badge") == "3"


def test_it_dismisses_itself(qtbot, page):
    view, bridge = page
    bridge.raise_toast("gone in four seconds")
    _wait_until(
        qtbot, view, "document.getElementById('toast').hidden === true", timeout_ms=6000
    )
