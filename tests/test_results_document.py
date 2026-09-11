"""The results document (9.13 + 9.15), driven through a real Chromium.

Sizes are the *page* area: the window minus the 56px rail and the 48 + 28 of
Qt chrome. 1366x768 -> 1310x692, 1920x1080 -> 1864x1004. Never mark skip.
"""

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page


def results_lines(orders=312):
    """A deterministic session: 1-5 lines per order, every 10th (from #3) blocked."""
    couriers = ["DHL", "DPD", "Packeta", ""]
    rows = []
    for i in range(orders):
        for line in range(1 + i % 5):
            rows.append(
                {
                    "Order_Number": f"#{10001 + i}",
                    "Order_Fulfillment_Status": "Not Fulfillable"
                    if i % 10 == 3
                    else "Fulfillable",
                    "Shipping_Provider": couriers[i % 4],
                    "Customer": f"Customer {i:03d}",
                    "Created_At": f"2026-09-0{1 + i % 3} 0{i % 10}:15:00 +0200",
                    "Total_Price": 10.0 + i,
                    "SKU": f"SKU-{i:03d}-{line}",
                    "Product_Name": f"Product {line}",
                    "Quantity": 1 + line,
                    "Internal_Tags": '["vip"]' if i % 7 == 0 else "[]",
                    "System_note": "",
                    "Stock_Alert": "Low Stock" if i % 11 == 0 else "",
                    "Has_SKU": i % 13 != 0,
                }
            )
    return pd.DataFrame(rows)


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


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _resize(qtbot, view, width, height):
    view.resize(width, height)
    _until_js(
        qtbot, view, f"window.innerWidth === {width} && window.innerHeight === {height}"
    )


def _choose_filter(qtbot, view, label):
    _eval(qtbot, view, "document.getElementById('add-filter').click(); true")
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#filter-menu .menu-item'))"
        f".find(function (b) {{ return b.textContent.trim() === {label!r}; }}).click(); true",
    )


def _count_is(qtbot, view, text):
    _until_js(qtbot, view, f"document.getElementById('count').textContent === {text!r}")


# --- 9.15: the numbers ------------------------------------------------------


def test_17_whole_rows_at_1366(qtbot, doc):
    view, _ = doc
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '17'"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('scroller').clientHeight")
        == 28 + 17 * 28
    )


def test_28_whole_rows_at_1920(qtbot, doc):
    view, _ = doc
    _resize(qtbot, view, 1864, 1004)
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '28'"
    )


def test_no_horizontal_scroll_until_the_table_minimum(qtbot, doc):
    view, _ = doc
    scroller = "document.getElementById('scroller')"
    assert (
        _eval(qtbot, view, f"{scroller}.scrollWidth <= {scroller}.clientWidth") is True
    )
    _resize(qtbot, view, 780, 692)
    _until_js(qtbot, view, f"{scroller}.scrollWidth > {scroller}.clientWidth")


def test_only_a_window_of_rows_exists(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 17 + 8
    )
    _eval(qtbot, view, "document.getElementById('scroller').scrollTop = 28 * 150; true")
    _until_js(qtbot, view, "!!document.querySelector('#rows .row[data-index=\"150\"]')")
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 17 + 8
    )


# --- 9.13: the document -------------------------------------------------------


def test_the_nine_columns_in_order(qtbot, doc):
    view, _ = doc
    titles = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#header .head'))"
        ".map(function (c) { return c.textContent.trim(); })",
    )
    assert titles == [
        "",
        "Status",
        "Order",
        "Customer",
        "Lines",
        "Units",
        "Value",
        "Courier",
        "Age",
    ]


def test_a_row_reads_as_the_order(qtbot, doc):
    view, _ = doc
    row = '#rows .row[data-order="#10004"]'
    assert _text(qtbot, view, row + " .status") == "Blocked"
    assert _text(qtbot, view, row + " .customer") == "Customer 003"
    assert _text(qtbot, view, row + " .lines") == "4"
    assert _text(qtbot, view, row + " .units") == "10"
    assert _text(qtbot, view, row + " .value") == "13.00"
    # i=3 ships with no courier: a missing value is a dash, not an empty cell.
    assert _text(qtbot, view, row + " .courier") == "—"


def test_the_kpis_count_the_session(qtbot, doc):
    view, _ = doc
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-kpi=orders] .kpi-value').textContent === '312'",
    )
    assert _text(qtbot, view, "[data-kpi=fulfillable] .kpi-value") == "281"
    assert _text(qtbot, view, "[data-kpi=blocked] .kpi-value") == "31"
    assert _text(qtbot, view, "[data-kpi=labels] .kpi-value") == "281"
    assert _text(qtbot, view, "[data-kpi=labels] .kpi-sub").startswith("DHL ")


def test_the_sixth_card_only_on_a_wide_page(qtbot, doc):
    view, _ = doc
    display = "getComputedStyle(document.querySelector('[data-kpi=oldest]')).display"
    assert _eval(qtbot, view, display) == "none"
    _resize(qtbot, view, 1864, 1004)
    _until_js(qtbot, view, f"{display} !== 'none'")


def test_export_names_the_count_and_reaches_python(qtbot, doc):
    view, bridge = doc
    _until_js(
        qtbot,
        view,
        "document.getElementById('export').textContent === 'Export 281 orders'",
    )
    with qtbot.waitSignal(bridge.exportRequested, timeout=5000):
        _eval(qtbot, view, "document.getElementById('export').click(); true")


def test_nothing_analysed_shows_its_state(qtbot, doc):
    view, bridge = doc
    bridge.set_orders(pd.DataFrame())
    _until_js(qtbot, view, "!document.getElementById('results-empty').hidden")
    assert _text(qtbot, view, "[data-kpi=orders] .kpi-value") == "—"
    assert _eval(qtbot, view, "document.getElementById('export').disabled") is True


# --- filtering ------------------------------------------------------------------


def test_search_finds_an_order_by_its_sku(qtbot, doc):
    view, _ = doc
    _count_is(qtbot, view, "312 orders")
    _eval(
        qtbot,
        view,
        "var s = document.getElementById('search'); s.value = 'sku-042-0';"
        " s.dispatchEvent(new Event('input')); true",
    )
    _count_is(qtbot, view, "1 of 312 orders")


def test_chips_and_across_groups_and_or_within_one(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Blocked")
    _count_is(qtbot, view, "31 of 312 orders")
    _choose_filter(qtbot, view, "Courier: DHL")  # no blocked order ships DHL
    _count_is(qtbot, view, "0 of 312 orders")
    _until_js(qtbot, view, "!document.getElementById('results-no-match').hidden")
    _choose_filter(qtbot, view, "Courier: DPD")  # blocked AND (DHL OR DPD)
    _count_is(qtbot, view, "15 of 312 orders")
    _eval(qtbot, view, "document.getElementById('clear-all').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_a_chip_removes_itself_when_clicked(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Repeat")
    _until_js(
        qtbot, view, "document.querySelectorAll('#chips .chip-filter').length === 1"
    )
    _eval(qtbot, view, "document.querySelector('#chips .chip-filter').click(); true")
    _count_is(qtbot, view, "312 orders")


# --- selection and sort ------------------------------------------------------------


def test_a_row_click_reaches_python_and_a_hiding_filter_drops_it(qtbot, doc):
    view, bridge = doc
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _eval(
            qtbot,
            view,
            "document.querySelector('#rows .row[data-order=\"#10001\"] .order').click(); true",
        )
    assert blocker.args == [["#10001"]]
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _choose_filter(qtbot, view, "Blocked")  # #10001 is fulfillable
    assert blocker.args == [[]]


def test_arrow_down_moves_the_selection(qtbot, doc):
    view, bridge = doc
    _eval(
        qtbot,
        view,
        "document.querySelector('#rows .row[data-order=\"#10001\"] .order').click(); true",
    )
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _eval(
            qtbot,
            view,
            "document.getElementById('table').dispatchEvent("
            "new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true})); true",
        )
    assert blocker.args == [["#10002"]]


def test_sorting_value_twice_is_descending(qtbot, doc):
    view, _ = doc
    head = "document.querySelector('#header .head[data-sort=value]')"
    _eval(qtbot, view, f"{head}.click(); {head}.click(); true")
    _until_js(
        qtbot,
        view,
        "document.querySelector('#rows .row[data-index=\"0\"]').dataset.order === '#10312'",
    )
