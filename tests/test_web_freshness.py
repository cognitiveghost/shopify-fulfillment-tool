"""A page never shows an old session (2026-10-08 web tier freshness spec).

Driven through a real Chromium. Never mark skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QStackedWidget, QWidget
from test_browse_state import H, session
from test_browse_state import make_state as browse_state_of
from test_logs_page import row as log_row
from test_results_bridge import _eval, _until_js
from test_results_document import results_lines
from test_setup_state import loaded
from test_setup_state import make_state as setup_state_of
from test_tools_state import make_state as tools_state_of

from gui.browse_bridge import mount_browse_page
from gui.logs_bridge import mount_logs_page
from gui.results_bridge import mount_results_page
from gui.settings.bridge import mount_settings_page
from gui.setup_bridge import mount_setup_page
from gui.tools_bridge import mount_tools_page
from gui.web_page import keep_pages_painted

MOUNTS = {
    "setup": mount_setup_page,
    "results": mount_results_page,
    "browse": mount_browse_page,
    "logs": mount_logs_page,
    "tools": mount_tools_page,
    "settings": mount_settings_page,
}


def _ready(qtbot, view):
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")


def _painted(qtbot, view, bridge):
    """Wait until the page has reported the bridge's current revision."""
    qtbot.waitUntil(lambda: bridge.painted_revision == bridge.revision, timeout=15000)
    assert _eval(qtbot, view, "Number(document.documentElement.dataset.painted)") == bridge.revision


@pytest.mark.parametrize("name", sorted(MOUNTS))
def test_every_page_reports_the_revision_it_painted(qtbot, name):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = MOUNTS[name](view)
    view.resize(1166, 720)
    view.show()
    _ready(qtbot, view)
    _painted(qtbot, view, bridge)
    bridge.set_theme_css(bridge.themeCss + "\n/* again */")
    _painted(qtbot, view, bridge)


OLD, NEW = "OLD-SESSION-MARK", "NEW-SESSION-MARK"


def _in_stack(qtbot, name):
    """The page beside a filler in a kept stack, with the page current."""
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    stack.addWidget(QWidget())
    view = QWebEngineView()
    stack.addWidget(view)
    bridge = MOUNTS[name](view)
    keep_pages_painted(stack)
    stack.resize(1166, 720)
    stack.setCurrentIndex(1)
    stack.show()
    _ready(qtbot, view)
    return stack, view, bridge


def _body(qtbot, view):
    return _eval(qtbot, view, "document.body.innerText")


def _state_push(name, mark):
    """A push that puts `mark` on the page, per page."""
    if name == "setup":
        return lambda bridge: bridge.set_state(
            setup_state_of(orders=loaded("orders", path=f"/d/{mark}.csv"))
        )
    if name == "browse":
        return lambda bridge: bridge.set_state(browse_state_of([session(mark, age=H)]))
    if name == "tools":
        return lambda bridge: bridge.set_state(tools_state_of(client=mark))
    if name == "results":

        def push(bridge):
            lines = results_lines(12)
            lines["Order_Number"] = [f"{mark}-{n}" for n in lines["Order_Number"]]
            bridge.set_orders(lines)

        return push
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["browse", "results", "setup", "tools"])
def test_a_page_pushed_while_covered_is_current_when_shown(qtbot, name):
    stack, view, bridge = _in_stack(qtbot, name)
    _state_push(name, OLD)(bridge)
    _painted(qtbot, view, bridge)
    assert OLD in _body(qtbot, view)  # the mark really is on the page

    stack.setCurrentIndex(0)  # cover it
    _state_push(name, NEW)(bridge)
    _painted(qtbot, view, bridge)  # it paints while covered
    stack.setCurrentIndex(1)

    assert bridge.painted_revision == bridge.revision
    body = _body(qtbot, view)
    assert NEW in body
    assert OLD not in body


def test_log_rows_sent_while_covered_are_there_when_shown(qtbot):
    stack, view, bridge = _in_stack(qtbot, "logs")
    stack.setCurrentIndex(0)
    bridge.send([log_row(1, NEW)])
    stack.setCurrentIndex(1)
    _until_js(qtbot, view, f"document.body.innerText.includes('{NEW}')")


def test_a_new_session_forgets_the_previous_view(qtbot):
    _stack, view, bridge = _in_stack(qtbot, "results")
    bridge.set_orders(results_lines(40))
    _painted(qtbot, view, bridge)
    _eval(
        qtbot,
        view,
        "(() => { const f = document.getElementById('search'); f.value = '#1';"
        " f.dispatchEvent(new Event('input', {bubbles: true}));"
        " document.querySelector('#header .col-order').click();"
        " document.querySelector('#header .col-select input').click();"
        " state.chips = [{kind: 'status', value: 'fulfillable', label: 'Fulfillable'}];"
        " render(); els.scroller.scrollTop = 64; return true; })()",
    )
    before = json.loads(
        _eval(qtbot, view, "JSON.stringify({q: state.query, s: state.sort, n: state.selected.size})")
    )
    assert before["q"] == "#1" and before["s"] is not None and before["n"] > 0

    bridge.forget_view()
    lines = results_lines(12)
    lines["Order_Number"] = [f"{NEW}-{n}" for n in lines["Order_Number"]]
    bridge.set_orders(lines)
    _painted(qtbot, view, bridge)

    after = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify({q: state.query, field: document.getElementById('search').value,"
            " chips: state.chips.length, s: state.sort, n: state.selected.size,"
            " anchor: state.anchorKey, cursor: state.cursorKey, top: els.scroller.scrollTop,"
            " shown: state.view.length, columns: state.columnSettings})",
        )
    )
    assert after["q"] == "" and after["field"] == ""
    assert after["chips"] == 0 and after["s"] is None and after["n"] == 0
    assert after["anchor"] is None and after["cursor"] is None and after["top"] == 0
    assert after["shown"] == 12
    assert NEW in _body(qtbot, view)


def test_forgetting_the_view_keeps_the_column_choices(qtbot):
    _stack, view, bridge = _in_stack(qtbot, "results")
    bridge.set_orders(results_lines(12))
    bridge.setAutoHideEmpty(True)
    _painted(qtbot, view, bridge)
    bridge.forget_view()
    _painted(qtbot, view, bridge)
    assert _eval(qtbot, view, "state.columnSettings.auto_hide_empty") is True
