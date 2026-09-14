"""The bridge, driven through a real Chromium (ADR 0001, roadmap 9.12).

Needs QtWebEngine's runtime libraries; CI installs them in the verify job.
Never mark these skip -- a bridge nobody can run is a bridge nobody guards.
"""

import time

import pandas as pd
import pytest
from PySide6.QtWebEngineCore import QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.results_bridge import (
    PAGE,
    THEME_MARKER,
    ResultsBridge,
    mount_results_page,
    normalize_column_settings,
)
from gui.theme_manager import get_theme_manager
from shared.theme import DARK_THEME, LIGHT_THEME


def _eval(qtbot, view, expr, timeout=5000):
    box = []
    view.page().runJavaScript(expr, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return box[0]


def _until_js(qtbot, view, expr, timeout_s=15):
    # A single slow round-trip (e.g. a cold QWebEngineView/Chromium spin-up
    # under CI load) can outlast _eval's own per-call timeout; catch that and
    # keep retrying against this function's own deadline instead of failing
    # on the first slow iteration.
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining_ms = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if _eval(qtbot, view, expr, timeout=min(remaining_ms, 5000)) is True:
                return
        except QtBotTimeoutError:
            continue
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
                "Notes": [None, "call first", "call first"],
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
    assert _eval(qtbot, view, "window.resultsBridge.orders[0].Notes === null") is True


def test_the_first_paint_is_already_themed(qtbot):
    # Read at DOMContentLoaded, before the channel's first reply can arrive, so
    # this sees what mount_results_page wrote into the HTML, not what results.js
    # applies once the bridge connects.
    view = QWebEngineView()
    qtbot.addWidget(view)
    probe = QWebEngineScript()
    probe.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    probe.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    probe.setSourceCode(
        "document.addEventListener('DOMContentLoaded', function () {"
        " window.__firstPaint = getComputedStyle(document.body).backgroundColor; });"
    )
    view.page().scripts().insert(probe)
    mount_results_page(view)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    assert _eval(qtbot, view, "window.__firstPaint") == _rgb(LIGHT_THEME.surface)


def test_the_bundled_inter_loads_in_both_weights(qtbot, page):
    # Chromium cannot see Qt's font database; a wrong @font-face path would
    # fall back to another sans without a sound.
    view, _ = page
    _eval(
        qtbot,
        view,
        "Promise.all([document.fonts.load('10pt Inter'),"
        " document.fonts.load('bold 10pt Inter')]).then(function (r) {"
        " window.__inter = r[0].concat(r[1]).filter(function (f) {"
        " return f.status === 'loaded'; }).length; },"
        " function () { window.__inter = -1; }); true",
    )
    _until_js(qtbot, view, "window.__inter !== undefined")
    assert _eval(qtbot, view, "window.__inter") == 2


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


def test_set_orders_also_sets_the_summary(qapp):
    bridge = ResultsBridge()
    seen = []
    bridge.summaryChanged.connect(lambda: seen.append(bridge.summary))
    bridge.set_orders(pd.DataFrame({"Order_Number": ["#1", "#2"], "SKU": ["A", "B"]}))
    assert seen and seen[-1]["orders"] == 2


def test_open_export_is_a_request_python_hears(qapp):
    bridge = ResultsBridge()
    heard = []
    bridge.exportRequested.connect(lambda: heard.append(True))
    bridge.openExport()
    assert heard == [True]


def test_open_screen_menu_is_a_request_python_hears(qapp):
    bridge = ResultsBridge()
    heard = []
    bridge.screenMenuRequested.connect(lambda: heard.append(True))
    bridge.openScreenMenu()
    assert heard == [True]


def test_export_enabled_notifies_only_on_change(qapp):
    bridge = ResultsBridge()
    changes = []
    bridge.exportEnabledChanged.connect(lambda: changes.append(bridge.exportEnabled))
    bridge.set_export_enabled(True)
    bridge.set_export_enabled(True)
    bridge.set_export_enabled(False)
    assert changes == [True, False]


def test_the_summary_arrives_in_js(qtbot, page):
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame({"Order_Number": ["#1", "#1", "#2"], "SKU": ["A", "B", "C"]})
    )
    _until_js(qtbot, view, "window.resultsBridge.summary.orders === 2")
    assert _eval(qtbot, view, "window.resultsBridge.summary.lines") == 3


def test_normalize_column_settings_cleans_junk():
    assert normalize_column_settings(None) == {
        "order": None,
        "visible": None,
        "auto_hide_empty": False,
    }
    assert normalize_column_settings(
        {"order": ["age", 3, "age", "lines"], "visible": "x", "auto_hide_empty": 1}
    ) == {"order": ["age", "lines"], "visible": None, "auto_hide_empty": True}


@pytest.mark.parametrize(
    ("slot", "args", "signal"),
    [
        ("holdOrder", ("#1",), "holdRequested"),
        ("fulfillOrder", ("#1",), "fulfillRequested"),
        ("excludeOrder", ("#1",), "excludeRequested"),
        ("removeLine", ("#1", 2, "SKU-A"), "lineRemovalRequested"),
        ("addOrderTag", ("#1", "vip"), "tagAddRequested"),
        ("removeOrderTag", ("#1", "vip"), "tagRemovalRequested"),
    ],
)
def test_each_pane_verb_is_a_request_python_hears(qtbot, slot, args, signal):
    bridge = ResultsBridge()
    with qtbot.waitSignal(getattr(bridge, signal), timeout=1000) as blocker:
        getattr(bridge, slot)(*args)
    assert tuple(blocker.args) == args


def test_column_slots_store_names_and_announce_them(qtbot):
    bridge = ResultsBridge()
    with qtbot.waitSignal(bridge.columnSettingsChanged, timeout=1000) as blocker:
        bridge.setColumnOrder(["age", "lines"])
    assert blocker.args[0] == {
        "order": ["age", "lines"],
        "visible": None,
        "auto_hide_empty": False,
    }
    bridge.setVisibleColumns(["age"])
    bridge.setAutoHideEmpty(True)
    assert bridge.columns["visible"] == ["age"]
    bridge.resetColumns()
    assert bridge.columns["order"] is None
    assert bridge.columns["visible"] is None
    assert bridge.columns["auto_hide_empty"] is True


def test_set_orders_names_the_clients_extra_order_columns(qapp):
    bridge = ResultsBridge()
    df = pd.DataFrame(
        [
            {"Order_Number": "1", "SKU": "A", "Channel": "web"},
            {"Order_Number": "1", "SKU": "B", "Channel": "web"},
            {"Order_Number": "2", "SKU": "C", "Channel": "shop"},
        ]
    )
    bridge.set_orders(df)
    assert bridge.columns["extras"] == ["Channel"]


def test_set_column_settings_keeps_extras(qapp):
    bridge = ResultsBridge()
    bridge._columns["extras"] = ["Channel"]
    bridge.set_column_settings({"visible": ["age"]})
    assert bridge.columns == {
        "order": None,
        "visible": ["age"],
        "auto_hide_empty": False,
        "extras": ["Channel"],
    }


def test_copy_text_reaches_the_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    ResultsBridge().copyText("#10445")
    assert QGuiApplication.clipboard().text() == "#10445"


def test_tag_categories_notify(qtbot):
    bridge = ResultsBridge()
    with qtbot.waitSignal(bridge.tagCategoriesChanged, timeout=1000):
        bridge.set_tag_categories({"prio": {"label": "Priority", "tags": ["vip"]}})
    assert bridge.tagCategories["prio"]["tags"] == ["vip"]
