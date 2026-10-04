"""The results document (9.13 + 9.15), driven through a real Chromium.

Sizes are the *page* area: the window minus the 56px rail and the 48 + 28 of
Qt chrome. 1366x768 -> 1310x692, 1920x1080 -> 1864x1004. Never mark skip.
"""

import json

import pandas as pd
import pytest
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.results_bridge import mount_results_page
from gui.theme_manager import get_theme_manager
from shared.theme import LIGHT_THEME


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


def _search(qtbot, view, text):
    _eval(
        qtbot,
        view,
        f"var s = document.getElementById('search'); s.value = {text!r};"
        " s.dispatchEvent(new Event('input')); true",
    )


def _click_order(qtbot, view, order, **modifiers):
    init = json.dumps({"bubbles": True, **modifiers})
    _eval(
        qtbot,
        view,
        f"document.querySelector('#rows .row[data-order=\"{order}\"] .col-order')"
        f".dispatchEvent(new MouseEvent('click', {init})); true",
    )


def _check(qtbot, view, order):
    _eval(
        qtbot,
        view,
        f"document.querySelector('#rows .row[data-order=\"{order}\"] input[type=checkbox]')"
        ".click(); true",
    )


def _key(qtbot, view, key, **modifiers):
    init = json.dumps({"key": key, "bubbles": True, **modifiers})
    _eval(
        qtbot,
        view,
        "document.getElementById('table')"
        f".dispatchEvent(new KeyboardEvent('keydown', {init})); true",
    )


# --- 9.15: the numbers ------------------------------------------------------


def test_14_whole_rows_at_1366(qtbot, doc):
    """692 high: 36 of page padding, 88 of KPI, 32 of filter bar and two 12px
    gaps leave a 512px card. Its edges leave 510, the header takes 36, and
    474 holds 14 rows of 32."""
    view, _ = doc
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '14'"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('scroller').clientHeight")
        == 36 + 14 * 32
    )


def test_24_whole_rows_at_1920(qtbot, doc):
    view, _ = doc
    _resize(qtbot, view, 1864, 1004)
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '24'"
    )


def test_only_a_window_of_rows_exists(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 14 + 8
    )
    _eval(qtbot, view, "document.getElementById('scroller').scrollTop = 32 * 150; true")
    _until_js(qtbot, view, "!!document.querySelector('#rows .row[data-index=\"150\"]')")
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 14 + 8
    )


def test_the_header_is_36_tall_and_a_row_32(qtbot, doc):
    view, _ = doc
    assert _eval(qtbot, view, "document.getElementById('header').offsetHeight") == 36
    assert _eval(qtbot, view, "document.querySelector('#rows .row').offsetHeight") == 32


def test_floor_density_rows_are_four_taller_than_the_token(qtbot, doc):
    """Review focus 4: the +4 holds in both densities, and the row maths follows."""
    view, _ = doc
    get_theme_manager().set_density("floor")  # conftest restores desk
    _until_js(qtbot, view, "document.querySelector('#rows .row').offsetHeight === 44")
    rows = int(
        _eval(qtbot, view, "document.getElementById('table').dataset.visibleRows")
    )
    assert (
        _eval(qtbot, view, "document.getElementById('scroller').clientHeight")
        == 36 + rows * 44
    )


def test_the_table_and_the_pane_share_one_card(qtbot, doc):
    view, _ = doc
    area = "document.getElementById('table-area')"
    assert _eval(qtbot, view, f"{area}.classList.contains('card')") is True
    assert _eval(qtbot, view, f"{area}.contains(document.getElementById('pane'))") is True
    assert _eval(
        qtbot, view, "getComputedStyle(document.body).backgroundColor"
    ) == _rgb(LIGHT_THEME.surface_sunken)


def test_the_status_is_a_badge(qtbot, doc):
    view, _ = doc
    blocked = "document.querySelector('#rows .row[data-order=\"#10004\"] .col-status .badge')"
    ready = "document.querySelector('#rows .row[data-order=\"#10001\"] .col-status .badge')"
    assert _eval(qtbot, view, f"{blocked}.className") == "badge danger"
    assert _eval(qtbot, view, f"{ready}.className") == "badge success"
    # A repeat order wears an info badge in its Repeat cell.
    assert (
        _eval(
            qtbot,
            view,
            "cellElement({key: 'repeat', text: function () { return 'Repeat'; }},"
            " {key: 'x', o: {_repeat: true}}, false).querySelector('.badge.info') !== null",
        )
        is True
    )


def test_the_order_is_bold_mono_and_a_missing_value_is_quiet(qtbot, doc):
    view, _ = doc
    row = "#rows .row[data-order=\"#10004\"]"
    for cell in ("order", "lines", "units", "value"):
        assert (
            _eval(
                qtbot,
                view,
                f"document.querySelector('{row} .col-{cell}').classList.contains('mono')",
            )
            is True
        ), cell
    assert (
        _eval(
            qtbot, view, f"getComputedStyle(document.querySelector('{row} .col-order')).fontWeight"
        )
        == "700"
    )
    # i=3 ships with no courier: the dash is in the disabled text colour.
    assert _eval(
        qtbot, view, f"getComputedStyle(document.querySelector('{row} .col-courier')).color"
    ) == _rgb(LIGHT_THEME.text_disabled)


def test_the_value_header_is_quiet_until_a_price_column_is_mapped(qtbot, doc):
    view, bridge = doc
    head = "document.querySelector('#header .head.col-value')"
    assert _eval(qtbot, view, f"{head}.classList.contains('unmapped')") is False
    bridge.set_orders(results_lines().drop(columns=["Total_Price"]))
    _until_js(qtbot, view, f"{head}.classList.contains('unmapped')")


def test_no_horizontal_scroll_until_the_table_minimum(qtbot, doc):
    view, _ = doc
    scroller = "document.getElementById('scroller')"
    assert (
        _eval(qtbot, view, f"{scroller}.scrollWidth <= {scroller}.clientWidth") is True
    )
    _resize(qtbot, view, 780, 692)
    _until_js(qtbot, view, f"{scroller}.scrollWidth > {scroller}.clientWidth")


# --- 9.13: the document -------------------------------------------------------


def test_the_default_columns_in_order(qtbot, doc):
    # JSON-encoded and decoded on the Python side: runJavaScript's automatic
    # QVariantList marshalling of a JS array is unreliable under this box's
    # software-rendered QtWebEngine, though the page and the DOM it produces
    # are unaffected -- see the horizontal-scroll fix in results.css for the
    # one genuine bug this environment did surface.
    view, _ = doc
    titles = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('#header .head'))"
            ".map(function (c) { return c.textContent.trim(); }))",
        )
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
        "Repeat",
    ]


def test_a_row_reads_as_the_order(qtbot, doc):
    view, _ = doc
    row = '#rows .row[data-order="#10004"]'
    assert _text(qtbot, view, row + " .col-status") == "Blocked"
    assert _text(qtbot, view, row + " .col-customer") == "Customer 003"
    assert _text(qtbot, view, row + " .col-lines") == "4"
    assert _text(qtbot, view, row + " .col-units") == "10"
    assert _text(qtbot, view, row + " .col-value") == "13.00"
    # i=3 ships with no courier: a missing value is a dash, not an empty cell.
    assert _text(qtbot, view, row + " .col-courier") == "—"


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
    _search(qtbot, view, "sku-042-0")
    _count_is(qtbot, view, "1 of 312 orders")


def test_search_finds_an_order_by_a_lot_batch_or_either_expiry_form(qtbot, doc):
    """#285: a lot is searched by batch, raw expiry and parsed expiry."""
    view, bridge = doc
    lot = {
        "batch": "B7",
        "expiry": "261230",
        "expiry_dt": pd.Timestamp("2026-12-30").date(),
        "qty_allocated": 1,
    }
    lines = results_lines(3)
    lines["Lot_Details"] = [[lot] if i == 0 else None for i in range(len(lines))]
    bridge.set_orders(lines)
    _count_is(qtbot, view, "3 orders")
    for query in ("b7", "261230", "2026-12-30"):
        _search(qtbot, view, query)
        _count_is(qtbot, view, "1 of 3 orders")


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


def test_the_filter_bar_reads_search_add_filter_then_chips(qtbot, doc):
    view, _ = doc
    order = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify([...document.getElementById('filterbar').children]"
            ".map(function (e) { return e.id || e.className; }))",
        )
    )
    assert order[:4] == ["input search", "filter-anchor", "chips", "clear-all"]
    assert order[-3:] == ["columns-anchor", "screen-menu", "export"]


def test_a_chip_names_its_key_and_only_its_x_removes_it(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Courier: DPD")
    _until_js(
        qtbot, view, "document.querySelectorAll('#chips .chip-filter').length === 1"
    )
    assert _text(qtbot, view, "#chips .chip-filter") == "Courier is DPD"
    _count_is(qtbot, view, "78 of 312 orders")
    _eval(qtbot, view, "document.querySelector('#chips .chip-value').click(); true")
    _count_is(qtbot, view, "78 of 312 orders")
    assert (
        _eval(qtbot, view, "document.querySelector('#chips .chip-remove').title")
        == "Remove filter"
    )
    _eval(qtbot, view, "document.querySelector('#chips .chip-remove').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_no_match_says_what_is_filtering(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Blocked")
    _choose_filter(qtbot, view, "Courier: DHL")  # no blocked order ships DHL
    _until_js(qtbot, view, "!document.getElementById('results-no-match').hidden")
    assert _text(qtbot, view, "#no-match-text") == "Status is Blocked and Courier is DHL."
    _search(qtbot, view, "zzz")
    _until_js(
        qtbot,
        view,
        "document.getElementById('no-match-text').textContent"
        " === 'Status is Blocked and Courier is DHL and search is “zzz”.'",
    )
    # Within Courier the chips are alternatives, and the sentence says so.
    _choose_filter(qtbot, view, "Courier: DPD")
    assert (
        _eval(qtbot, view, "filterSentence()")
        == "Status is Blocked and Courier is DHL or DPD and search is “zzz”."
    )
    assert _text(qtbot, view, "#no-match-clear") == "Clear filters"
    _eval(qtbot, view, "document.getElementById('no-match-clear').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_columns_and_export_keep_their_words_beside_a_glyph(qtbot, doc):
    view, _ = doc
    assert _text(qtbot, view, "#columns-button") == "Columns 9/18"
    assert _eval(qtbot, view, "!!document.querySelector('#columns-button svg')") is True
    _until_js(
        qtbot,
        view,
        "document.getElementById('export').textContent === 'Export 281 orders'",
    )
    assert _eval(qtbot, view, "!!document.querySelector('#export svg')") is True

# --- selection and sort ------------------------------------------------------------


def _has_class(order, name):
    return (
        f"document.querySelector('#rows .row[data-order=\"{order}\"]')"
        f".classList.contains('{name}')"
    )


def test_a_row_click_moves_the_cursor_and_checks_nothing(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _until_js(qtbot, view, _has_class("#10001", "cursor"))
    assert bridge.selection() == []
    assert _eval(qtbot, view, "state.selected.size") == 0
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is True


def test_a_checkbox_checks_the_order_and_leaves_the_cursor(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10003")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10003"])
    assert _eval(qtbot, view, "state.cursorKey") == "#10001"
    assert _eval(qtbot, view, _has_class("#10003", "selected")) is True
    assert _eval(qtbot, view, _has_class("#10003", "cursor")) is False
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is False
    _click_order(qtbot, view, "#10003", ctrlKey=True)  # Ctrl-click toggles too
    qtbot.waitUntil(lambda: bridge.selection() == [])


def test_a_hiding_filter_unchecks_the_order_and_empties_the_pane(qtbot, doc):
    """Review focus 3: nothing keeps pointing at an order the operator cannot see."""
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10001")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10001"])
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _choose_filter(qtbot, view, "Blocked")  # #10001 is fulfillable
    assert blocker.args == [[]]
    assert _eval(qtbot, view, "state.cursorKey === null") is True
    assert _eval(qtbot, view, "document.querySelectorAll('#rows .row.cursor').length") == 0
    assert _text(qtbot, view, "#pane-empty .state-title") == "No order selected"


def test_arrow_down_moves_the_cursor_only(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _key(qtbot, view, "ArrowDown")
    _until_js(qtbot, view, "state.cursorKey === '#10002'")
    assert bridge.selection() == []


def test_escape_clears_the_checked_orders_and_then_the_cursor(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10002")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10002"])
    _key(qtbot, view, "Escape")
    qtbot.waitUntil(lambda: bridge.selection() == [])
    assert _eval(qtbot, view, "state.cursorKey") == "#10001"
    _key(qtbot, view, "Escape")
    _until_js(qtbot, view, "state.cursorKey === null")


def test_the_header_box_checks_everything_or_clears(qtbot, doc):
    view, bridge = doc
    box = "document.querySelector('#header .col-select input')"
    _choose_filter(qtbot, view, "Blocked")
    _count_is(qtbot, view, "31 of 312 orders")
    _eval(qtbot, view, f"{box}.click(); true")
    qtbot.waitUntil(lambda: len(bridge.selection()) == 31)
    assert _eval(qtbot, view, f"{box}.title") == "Clear selection"
    _check(qtbot, view, "#10004")  # 30 of 31: the box is mixed, and still clears
    qtbot.waitUntil(lambda: len(bridge.selection()) == 30)
    assert _eval(qtbot, view, f"{box}.indeterminate") is True
    _eval(qtbot, view, f"{box}.click(); true")
    qtbot.waitUntil(lambda: bridge.selection() == [])


def test_the_cursor_row_wears_a_bar_on_its_left_edge(qtbot, doc):
    """The bar is a pseudo-element above the sticky cells, or they would paint
    over it. Only pixels can tell -- getComputedStyle cannot."""
    view, _ = doc
    _click_order(qtbot, view, "#10001")
    rect = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(document.querySelector('#rows .row.cursor')"
            ".getBoundingClientRect())",
        )
    )

    def token(name):
        return QColor(
            _eval(
                qtbot,
                view,
                "getComputedStyle(document.documentElement)"
                f".getPropertyValue('{name}').trim()",
            )
        ).name()

    x = int(rect["left"]) + 1  # inside the 3px bar
    y = int(rect["top"]) + int(rect["height"]) // 2
    qtbot.waitUntil(
        lambda: view.grab().toImage().pixelColor(x, y).name()
        == token("--selection-border"),
        timeout=5000,
    )
    # The rest of the row is the selection tint: sampled in the last cell's
    # right padding, clear of any text.
    tint_x = int(rect["right"]) - 4
    assert view.grab().toImage().pixelColor(tint_x, y).name() == token("--selection-bg")


def test_a_near_miss_beside_the_checkbox_still_checks(qtbot, doc):
    """The whole select cell toggles, so a click 5px off the box does not move
    the cursor instead."""
    view, bridge = doc
    _eval(
        qtbot,
        view,
        "document.querySelector('#rows .row[data-order=\"#10002\"] .cell.col-select')"
        ".dispatchEvent(new MouseEvent('click', {bubbles: true})); true",
    )
    qtbot.waitUntil(lambda: bridge.selection() == ["#10002"])
    assert _eval(qtbot, view, "state.cursorKey === null") is True


def test_a_shift_click_reopens_a_hidden_pane(qtbot, doc):
    view, _ = doc
    _click_order(qtbot, view, "#10001")
    _eval(qtbot, view, "state.paneHidden = true; render(); true")
    assert _eval(qtbot, view, "document.getElementById('pane').hidden") is True
    _click_order(qtbot, view, "#10003", shiftKey=True)
    assert _eval(qtbot, view, "document.getElementById('pane').hidden") is False


def test_an_orders_push_keeps_the_selection(qtbot, doc):
    """Every tag, status or undo re-pushes the session; the selection stays."""
    view, bridge = doc
    _check(qtbot, view, "#10002")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10002"])
    _eval(qtbot, view, "document.querySelector('#rows .row').dataset.stale = '1'; true")
    bridge.set_orders(results_lines())
    _until_js(qtbot, view, "!document.querySelector('#rows [data-stale]')")
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('#rows .row[data-order=\"#10002\"]')"
            ".classList.contains('selected')",
        )
        is True
    )
    assert bridge.selection() == ["#10002"]


def test_shift_selects_a_range_and_shift_arrow_can_shrink_it(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _click_order(qtbot, view, "#10004", shiftKey=True)
    qtbot.waitUntil(
        lambda: bridge.selection() == ["#10001", "#10002", "#10003", "#10004"]
    )
    _key(qtbot, view, "ArrowUp", shiftKey=True)
    qtbot.waitUntil(lambda: bridge.selection() == ["#10001", "#10002", "#10003"])


def test_ctrl_a_selects_every_order_shown_and_escape_clears(qtbot, doc):
    view, bridge = doc
    _choose_filter(qtbot, view, "Blocked")
    _count_is(qtbot, view, "31 of 312 orders")
    _key(qtbot, view, "a", ctrlKey=True)
    qtbot.waitUntil(lambda: len(bridge.selection()) == 31)
    _key(qtbot, view, "Escape")
    qtbot.waitUntil(lambda: bridge.selection() == [])


def test_ctrl_f_focuses_the_search_field(qtbot, doc):
    view, bridge = doc
    bridge.focusSearchRequested.emit()
    _until_js(
        qtbot, view, "document.activeElement === document.getElementById('search')"
    )


def test_sorting_value_twice_is_descending(qtbot, doc):
    view, _ = doc
    head = "document.querySelector('#header .head[data-sort=value]')"
    _eval(qtbot, view, f"{head}.click(); {head}.click(); true")
    _until_js(
        qtbot,
        view,
        "document.querySelector('#rows .row[data-index=\"0\"]').dataset.order === '#10312'",
    )


def test_the_kpi_strip_is_one_card(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.getElementById('kpis').classList.contains('card')")
        is True
    )
    # Cells, not cards: five of them at this width, the wide one hidden.
    assert _eval(qtbot, view, "document.querySelectorAll('#kpis .kpi').length") == 6
    assert _eval(qtbot, view, "document.querySelectorAll('#kpis .card').length") == 0
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#kpis .kpi-dot').length") == 2
    )


def test_a_mapped_price_gives_the_value_ready_cell(qtbot, doc):
    view, _ = doc
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-kpi=value] .kpi-label') !== null"
        " && document.querySelector('[data-kpi=value] .kpi-sub').textContent !== ''",
    )
    assert _text(qtbot, view, "[data-kpi=value] .kpi-label") == "Value ready"
    assert (
        _text(qtbot, view, "[data-kpi=value] .kpi-sub")
        == "across 281 fulfillable orders"
    )
    assert _eval(qtbot, view, "document.getElementById('map-columns') === null") is True


def test_an_unmapped_price_gives_a_hint_that_opens_the_mapping(qtbot, doc):
    view, bridge = doc
    bridge.set_orders(results_lines().drop(columns=["Total_Price"]))
    _until_js(qtbot, view, "document.getElementById('map-columns') !== null")
    assert (
        "Order value shows once a price column is mapped."
        in _text(qtbot, view, "[data-kpi=value]")
    )
    assert _text(qtbot, view, "#map-columns") == "Map columns"
    with qtbot.waitSignal(bridge.columnMappingRequested, timeout=5000):
        _eval(qtbot, view, "document.getElementById('map-columns').click(); true")


def test_the_lines_column_cells_are_not_boxed_like_the_panes_line_list(qtbot, doc):
    """The pane's `.lines` list and the table's Lines column share a word; the
    pane's border once leaked onto every cell of the column."""
    view, _ = doc
    cell = "document.querySelector('#rows .row .cell.col-lines')"
    assert _eval(qtbot, view, f"getComputedStyle({cell}).borderTopWidth") == "0px"


def test_the_pane_footer_fits_its_longest_verb_and_a_three_digit_position(qtbot, doc):
    """A blocked order's verb is "Mark fulfillable", the longest; it shares
    339px with Exclude order and "↑ ↓  250 / 312" in Inter."""
    view, _ = doc
    _eval(
        qtbot,
        view,
        "state.cursorKey = state.view.filter(r => !isFulfillable(r.o)).pop().key;"
        " render(); true",
    )
    _until_js(qtbot, view, "!!document.querySelector('#pane .pane-actions')")
    assert _text(qtbot, view, "#pane-status-verb") == "Mark fulfillable"
    position = _text(qtbot, view, "#pane .pane-position")
    assert position.endswith(" / 312") and len(position.split("/")[0].split()[-1]) == 3
    fits = _eval(
        qtbot,
        view,
        "(function () { var f = document.querySelector('#pane .pane-actions');"
        " return f.scrollWidth <= f.clientWidth; })()",
    )
    assert fits is True


def test_the_pane_footer_stays_on_one_row_for_a_forty_order_session(qtbot, doc):
    """Spacer-free: "Mark fulfillable", "Exclude order" and "↑ ↓  25 / 40"
    share one row at 339px (the wrap is only for three-digit positions)."""
    view, _ = doc
    _eval(
        qtbot,
        view,
        "state.view = state.view.slice(0, 40);"
        " state.cursorKey = state.view.filter(r => !isFulfillable(r.o)).pop().key;"
        " renderPane(); true",
    )
    _until_js(qtbot, view, "!!document.querySelector('#pane .pane-actions')")
    rows = _eval(
        qtbot,
        view,
        "new Set([...document.querySelectorAll('#pane .pane-actions > *')]"
        ".map(e => { var r = e.getBoundingClientRect();"
        " return Math.round(r.top + r.height / 2); })).size",
    )
    assert rows == 1
