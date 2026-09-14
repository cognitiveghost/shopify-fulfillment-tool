"""The slot and the column registry (Bundle 13 spec §6.1, §6.8), through Chromium.

Sizes are the page area: 1310x692 is the page at 1366x768. Never mark skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js
from test_results_document import results_lines

from gui.results_bridge import mount_results_page


@pytest.fixture
def doc(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1310, 692)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_export_enabled(True)
    bridge.set_orders(results_lines())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length > 0")
    return view, bridge


def _json(qtbot, view, expr):
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


HEADERS = "[...document.querySelectorAll('#header .cell')].map(c => c.textContent.trim()).filter(Boolean)"


def _has_header(title):
    return f"{HEADERS}.includes({title!r})"


def _width(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"Math.round(document.querySelector({selector!r}).getBoundingClientRect().width)",
    )


def test_the_pane_slot_leaves_the_table_866_wide_and_17_rows(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.getElementById('table-area').dataset.slot")
        == "pane"
    )
    assert _width(qtbot, view, ".table-wrap") == 866
    assert _width(qtbot, view, "#slot") == 400
    assert (
        _eval(qtbot, view, "document.getElementById('table').dataset.visibleRows")
        == "17"
    )


def test_the_columns_button_counts_shown_of_total(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.getElementById('columns-button').textContent")
        == "Columns 8/18"
    )


def test_a_saved_layout_orders_and_hides_columns(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"order": ["age", "units"], "visible": ["age", "type"]})
    _until_js(qtbot, view, _has_header("Type"))
    assert _json(qtbot, view, HEADERS) == ["Status", "Order", "Age", "Type"]


def test_hiding_customer_leaves_a_filler_not_a_stretched_column(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"visible": ["lines"]})
    _until_js(qtbot, view, "document.querySelector('#rows .row .cell.filler') !== null")


def test_auto_hide_drops_a_column_empty_in_every_order(qtbot, doc):
    view, bridge = doc  # results_lines() has no Subtotal column
    bridge.set_column_settings(
        {"visible": ["subtotal", "lines"], "auto_hide_empty": False}
    )
    _until_js(qtbot, view, _has_header("Subtotal"))
    bridge.set_column_settings(
        {"visible": ["subtotal", "lines"], "auto_hide_empty": True}
    )
    _until_js(qtbot, view, f"!{_has_header('Subtotal')}")


def test_a_clients_extra_order_column_can_be_shown(qtbot, doc):
    view, bridge = doc
    df = results_lines()
    df["Sales_Channel"] = df["Order_Number"].map(
        lambda n: "web" if int(n[1:]) % 2 else "shop"
    )
    bridge.set_orders(df)
    assert bridge.columns["extras"] == ["Sales_Channel"]
    bridge.set_column_settings({"visible": ["extra:Sales_Channel"]})
    _until_js(qtbot, view, _has_header("Sales Channel"))
