"""The bridge, driven through a real Chromium (ADR 0001, roadmap 9.12).

Needs QtWebEngine's runtime libraries; CI installs them in the verify job.
Never mark these skip -- a bridge nobody can run is a bridge nobody guards.
"""

import time

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.results_bridge import PAGE, THEME_MARKER, ResultsBridge, mount_results_page
from gui.theme_manager import get_theme_manager
from shared.theme import DARK_THEME, LIGHT_THEME


def _eval(qtbot, view, expr):
    box = []
    view.page().runJavaScript(expr, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=5000)
    return box[0]


def _until_js(qtbot, view, expr, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _eval(qtbot, view, expr) is True:
            return
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(h[i : i + 2], 16) for i in (0, 2, 4)))


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_an_unchanged_selection_is_announced_once(qapp):
    bridge = ResultsBridge()
    seen = []
    bridge.selectionChanged.connect(seen.append)
    bridge.setSelection(["#1001"])
    bridge.setSelection(["#1001"])
    assert seen == [["#1001"]]


def test_a_selection_made_in_js_arrives_in_python(qtbot, page):
    view, bridge = page
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        view.page().runJavaScript("window.resultsBridge.setSelection(['#1002'])")
    assert blocker.args == [["#1002"]]
    assert bridge.selection() == ["#1002"]


def test_an_order_payload_arrives_in_js_with_its_lines_nested(qtbot, page):
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame(
            {
                "Order_Number": ["#1001", "#1002", "#1002"],
                "SKU": ["A", "TS-4409-B", "C"],
                "Quantity": [1, 6, 2],
            }
        )
    )
    _until_js(qtbot, view, "window.resultsBridge.orders.length === 2")
    assert (
        _eval(qtbot, view, "window.resultsBridge.orders[1].lines[0].SKU") == "TS-4409-B"
    )
    assert _eval(qtbot, view, "window.resultsBridge.orders[1].lines[0].Quantity") == 6


def test_the_first_paint_is_already_themed(qtbot, page):
    view, _ = page
    assert _eval(
        qtbot, view, "getComputedStyle(document.body).backgroundColor"
    ) == _rgb(LIGHT_THEME.surface)


def test_a_theme_switch_repaints_the_document_without_a_reload(qtbot, page):
    view, _ = page
    _eval(qtbot, view, "window.__loadMarker = 'first load'")
    get_theme_manager().set_theme(
        "dark"
    )  # conftest's reset_theme_and_density restores light
    _until_js(
        qtbot,
        view,
        f"getComputedStyle(document.body).backgroundColor === '{_rgb(DARK_THEME.surface)}'",
    )
    assert _eval(qtbot, view, "window.__loadMarker") == "first load"


def test_a_density_change_reaches_the_type_scale(qtbot, page):
    view, _ = page
    get_theme_manager().set_density("floor")
    _until_js(
        qtbot,
        view,
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--type-body-size').trim() === '12pt'",
    )
