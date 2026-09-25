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
        == "Columns 9/18"
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


# --- the column manager (spec §6.9) ------------------------------------------

ROW = "document.querySelector('.col-row[data-key=\"{}\"] {}')"


def _open_columns(qtbot, view):
    _eval(qtbot, view, "document.getElementById('columns-button').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'columns'"
    )


def _settings(qtbot, view, bridge, js):
    """Run `js` and return the settings dict Python was told to store."""
    with qtbot.waitSignal(bridge.columnSettingsChanged, timeout=3000) as blocker:
        _eval(qtbot, view, js)
    return blocker.args[0]


def test_the_manager_keeps_the_table_width_and_counts_shown_and_hidden(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _width(qtbot, view, ".table-wrap") == 866
    assert (
        _eval(qtbot, view, "document.getElementById('columns-count').textContent")
        == "9 shown · 9 hidden"
    )


def test_every_registry_column_has_a_row_and_the_scroller_reaches_the_last(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, "document.querySelectorAll('.col-row').length") == 18
    assert _eval(
        qtbot,
        view,
        "(() => { const s = document.getElementById('columns-scroller');"
        " s.scrollTop = s.scrollHeight;"
        " const rows = s.querySelectorAll('.col-row');"
        " const last = rows[rows.length - 1].getBoundingClientRect();"
        " return last.bottom <= s.getBoundingClientRect().bottom + 1; })()",
    )


def test_the_scroller_reserves_a_gutter_so_meta_text_never_clips(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.getElementById('columns-scroller')).scrollbarGutter",
        )
        == "stable"
    )


def test_a_pinned_row_is_checked_disabled_and_has_no_drag_handle(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, ROW.format("order", ".col-check") + ".disabled") is True
    assert _eval(qtbot, view, ROW.format("order", ".col-check") + ".checked") is True
    assert (
        _eval(qtbot, view, ROW.format("order", ".col-note") + ".textContent")
        == "pinned"
    )
    assert _eval(qtbot, view, ROW.format("order", ".col-grip") + ".innerHTML") == ""


def test_toggling_a_column_stores_it_and_the_header_gains_it(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge, ROW.format("type", ".col-check") + ".click()"
    )
    assert "type" in stored["visible"]
    _until_js(qtbot, view, _has_header("Type"))


def test_alt_up_moves_a_column_before_the_previous_row(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot,
        view,
        bridge,
        "document.querySelector('.col-row[data-key=\"age\"]').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'ArrowUp', altKey: true, bubbles: true, cancelable: true}))",
    )
    order = stored["order"]
    assert order.index("age") == order.index("units") - 1


def test_a_drop_on_the_top_half_moves_the_column_before_that_row(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot,
        view,
        bridge,
        "(() => { const s = document.getElementById('columns-scroller');"
        " const src = s.querySelector('.col-row[data-key=\"age\"]');"
        " const dst = s.querySelector('.col-row[data-key=\"lines\"]');"
        " const dt = new DataTransfer();"
        " src.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));"
        " const box = dst.getBoundingClientRect();"
        " dst.dispatchEvent(new DragEvent('dragover',"
        " {dataTransfer: dt, bubbles: true, cancelable: true, clientY: box.top + 2}));"
        " dst.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));"
        " return 1; })()",
    )
    order = stored["order"]
    assert order.index("age") == order.index("lines") - 1


def test_a_drop_above_the_pinned_pair_lands_after_order(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot,
        view,
        bridge,
        "(() => { const s = document.getElementById('columns-scroller');"
        " const src = s.querySelector('.col-row[data-key=\"age\"]');"
        " const dst = s.querySelector('.col-row[data-key=\"status\"]');"
        " const dt = new DataTransfer();"
        " src.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));"
        " const box = dst.getBoundingClientRect();"
        " dst.dispatchEvent(new DragEvent('dragover',"
        " {dataTransfer: dt, bubbles: true, cancelable: true, clientY: box.top + 2}));"
        " dst.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));"
        " return 1; })()",
    )
    assert stored["order"][:3] == ["status", "order", "age"]


def test_the_search_hides_groups_with_no_match_and_the_handles(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    _eval(
        qtbot,
        view,
        "(() => { const s = document.getElementById('columns-search'); s.value = 'ship';"
        " s.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()",
    )
    assert _json(
        qtbot,
        view,
        "[...document.querySelectorAll('.col-group')].map(g => g.dataset.group)",
    ) == ["Shipping"]
    assert _json(
        qtbot,
        view,
        "[...document.querySelectorAll('.col-row')].map(r => r.dataset.key)",
    ) == ["method"]
    assert _eval(qtbot, view, ROW.format("method", ".col-grip") + ".innerHTML") == ""


def test_the_group_header_counts_shown_of_that_group(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    # Order holds status, order, lines, units, age, type, reason; five are shown.
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelector('.col-group[data-group=\"Order\"]').textContent",
        )
        == "ORDER 5 of 7"
    )


def test_the_footer_checkbox_sets_auto_hide_and_the_row_says_empty(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings(
        {"visible": ["subtotal", "lines"], "auto_hide_empty": False}
    )
    _until_js(qtbot, view, _has_header("Subtotal"))
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge, "document.getElementById('hide-empty').click()"
    )
    assert stored["auto_hide_empty"] is True
    _until_js(qtbot, view, f"!{_has_header('Subtotal')}")
    assert (
        _eval(qtbot, view, ROW.format("subtotal", ".col-note") + ".textContent")
        == "empty"
    )
    assert _eval(qtbot, view, ROW.format("subtotal", ".col-check") + ".checked") is True


def test_reset_clears_the_layout_and_keeps_auto_hide(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"visible": ["type"], "auto_hide_empty": True})
    _until_js(qtbot, view, f"!{_has_header('Customer')}")
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge, "document.getElementById('columns-reset').click()"
    )
    assert stored["visible"] is None and stored["order"] is None
    assert stored["auto_hide_empty"] is True
    _until_js(qtbot, view, _has_header("Customer"))


def test_done_closes_the_manager_and_returns_focus_to_the_button(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    _eval(qtbot, view, "document.getElementById('columns-done').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'"
    )
    assert _eval(qtbot, view, "document.activeElement.id") == "columns-button"
    assert (
        _eval(
            qtbot,
            view,
            "document.getElementById('columns-button').getAttribute('aria-pressed')",
        )
        == "false"
    )


def test_escape_closes_the_manager(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, "document.activeElement.id") == "columns-search"
    _eval(
        qtbot,
        view,
        "document.getElementById('columns-panel').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))",
    )
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'"
    )


def _sorted_header(qtbot, view):
    """The title of the header cell currently marked sorted, else ""."""
    return _eval(
        qtbot,
        view,
        "(() => { const c = document.querySelector('#header .cell.sorted');"
        " return c ? c.textContent.trim() : ''; })()",
    )


def test_hiding_the_sorted_column_clears_the_sort(qtbot, doc):
    """Spec §6.8: the one manager action that changes what the table shows."""
    view, bridge = doc
    _eval(
        qtbot,
        view,
        "[...document.querySelectorAll('#header .cell')]"
        ".find(c => c.textContent.trim() === 'Customer').click()",
    )
    _until_js(qtbot, view, "document.querySelector('#header .cell.sorted') !== null")
    assert _sorted_header(qtbot, view) == "Customer"

    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge, ROW.format("customer", ".col-check") + ".click()"
    )

    assert "customer" not in stored["visible"]
    _until_js(qtbot, view, "!" + _has_header("Customer"))
    assert _sorted_header(qtbot, view) == ""


def test_the_group_header_stays_above_the_rows_it_is_stuck_over(qtbot, doc):
    """Spec §6.9: sticky means visible. .col-row is positioned and comes later,
    so without a z-index the rows paint over the header."""
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(
        qtbot,
        view,
        "(() => { const s = document.getElementById('columns-scroller');"
        " s.scrollTop = 120;"
        " const g = s.querySelector('.col-group');"
        " const r = g.getBoundingClientRect();"
        " const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);"
        " return Boolean(hit && hit.closest('.col-group')); })()",
    )


def test_the_bridge_echoing_the_pages_own_layout_does_not_rerender(qtbot, doc):
    """Spec §4: the page ignores a columnsChanged equal to what it applied.
    The bridge's QVariantMap arrives with sorted keys, so the comparison has
    to be positional, not a raw JSON.stringify of the two dicts."""
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge, ROW.format("type", ".col-check") + ".click()"
    )
    _eval(qtbot, view, "document.querySelector('.col-row').dataset.sentinel = 'kept'")

    bridge.set_column_settings(stored)
    qtbot.wait(200)

    assert (
        _eval(qtbot, view, "document.querySelector('.col-row').dataset.sentinel")
        == "kept"
    )
