"""Bundle 14: the bar that exists only while orders are selected."""

import json

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page


def selection_bar_orders():
    """Three orders: 7 + 5 + 7 = 19 units, 150.00 + 184.60 = 334.60, 2 couriers."""
    rows = [
        {
            "Order_Number": "10443",
            "SKU": "TS-4409-B",
            "Product_Name": "Product TS-4409-B",
            "Quantity": 7,
            "Final_Stock": 40,
            "Order_Fulfillment_Status": "Fulfillable",
            "Shipping_Provider": "DPD",
            "Total_Price": 150.00,
            "Internal_Tags": "[]",
            "Customer": "A. Aachen",
        },
        {
            "Order_Number": "10444",
            "SKU": "TS-4409-B",
            "Product_Name": "Product TS-4409-B",
            "Quantity": 5,
            "Final_Stock": 40,
            "Order_Fulfillment_Status": "Fulfillable",
            "Shipping_Provider": "GLS",
            "Total_Price": 184.60,
            "Internal_Tags": "[]",
            "Customer": "B. Berlin",
        },
        {
            "Order_Number": "10445",
            "SKU": "TS-9999-Z",
            "Product_Name": "Product TS-9999-Z",
            "Quantity": 7,
            "Final_Stock": 12,
            "Order_Fulfillment_Status": "Fulfillable",
            "Shipping_Provider": "DPD",
            "Total_Price": 99.00,
            "Internal_Tags": "[]",
            "Customer": "C. Cologne",
        },
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_orders(selection_bar_orders())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 3")
    return view, bridge


def _text(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"(document.querySelector({selector!r}) || {{textContent: null}}).textContent",
    )


def _select(qtbot, view, order_numbers):
    keys = ", ".join(repr(str(n)) for n in order_numbers)
    _eval(qtbot, view, f"state.selected = new Set([{keys}]); render(); true")


def _json(qtbot, view, expr):
    # A bare array/object result marshals to '' on this Qt build; round-trip
    # through JSON.stringify like the rest of the results-document suite.
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def test_the_bar_is_absent_with_no_selection(qtbot, page):
    view, _ = page
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is True


def test_the_bar_counts_orders_and_units(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444", "10445"])
    assert _text(qtbot, view, "#selection-count") == "3 orders · 19 units selected"


def test_one_order_reads_singular_and_the_verbs_drop_their_count(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    assert _text(qtbot, view, "#selection-count") == "1 order · 7 units selected"
    assert _text(qtbot, view, "#selection-mark") == "Mark fulfillable"
    assert _text(qtbot, view, "#selection-hold") == "Hold"


def test_the_verbs_carry_the_count_above_one(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444"])
    assert _text(qtbot, view, "#selection-mark") == "Mark 2 fulfillable"
    assert _text(qtbot, view, "#selection-hold") == "Hold these 2"


def test_the_sub_line_counts_value_and_couriers(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444"])
    assert _text(qtbot, view, "#selection-sub") == "334.60 · 2 couriers"


def test_export_drops_to_secondary_while_the_bar_is_up(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    assert "secondary" in _eval(
        qtbot, view, "document.getElementById('export').className"
    )
    _eval(qtbot, view, "document.getElementById('selection-clear').click(); true")
    assert "primary" in _eval(
        qtbot, view, "document.getElementById('export').className"
    )


def test_the_bar_takes_its_height_from_the_table(qtbot, page):
    view, _ = page
    before = int(_eval(qtbot, view, "state.visible"))
    _select(qtbot, view, ["10443"])
    after = int(_eval(qtbot, view, "state.visible"))
    assert before - after == 1


def test_the_row_budget_reads_the_bar_height_from_css(qtbot, page):
    """CSS states the height and JS reads it back, so the two can never
    disagree about how much the bar costs the table (spec section 3.1)."""
    view, _ = page
    assert _eval(qtbot, view, "selectionBarPx()") == 44
    assert (
        _eval(
            qtbot,
            view,
            "getComputedStyle(document.getElementById('selection-bar')).height",
        )
        == "44px"
    )


def test_mounting_the_bar_does_not_move_focus(qtbot, page):
    view, _ = page
    _eval(qtbot, view, "document.getElementById('search').focus(); true")
    _select(qtbot, view, ["10443"])
    assert _eval(qtbot, view, "document.activeElement.id") == "search"


def test_clear_empties_the_selection_and_hides_the_bar(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('selection-clear').click(); true")
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is True


def test_more_lists_its_seven_items_in_order(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444", "10445"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    labels = _json(
        qtbot,
        view,
        "[...document.querySelectorAll('#selection-menu .menu-item')]"
        ".map(b => b.firstChild.textContent.trim())",
    )
    assert labels == [
        "Add a tag to 3 orders",
        "Remove a tag from 3 orders",
        "Copy 3 order numbers",
        "Export these 3 orders to Excel",
        "Export these 3 orders to CSV",
        "Remove a SKU from these 3 orders",
        "Remove whole orders containing a SKU",
    ]


def test_a_separator_sits_above_the_two_destructive_items(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelectorAll('#selection-menu .menu-separator').length",
        )
        == 1
    )


def test_remove_a_tag_is_disabled_when_nothing_carries_one(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10445"])  # no order in this fixture carries a tag
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    assert (
        _eval(qtbot, view, "document.getElementById('more-remove-tag').disabled")
        is True
    )
    assert _text(qtbot, view, "#more-remove-tag") == "Remove a tag from 1 order"
    assert (
        _eval(qtbot, view, "document.getElementById('more-remove-tag').title")
        == "None of these 1 order carry a tag"
    )


def test_copy_sends_the_order_numbers_one_per_line(qtbot, page):
    from PySide6.QtGui import QGuiApplication

    view, _ = page
    _select(qtbot, view, ["10443", "10444"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-copy').click(); true")
    assert QGuiApplication.clipboard().text() == "10443\n10444"


def test_ctrl_c_copies_without_opening_the_menu(qtbot, page):
    from PySide6.QtGui import QGuiApplication

    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', "
        "{key: 'c', ctrlKey: true, bubbles: true})); true",
    )
    assert QGuiApplication.clipboard().text() == "10443"
    assert (
        _eval(qtbot, view, "document.getElementById('selection-menu').hidden") is True
    )


def test_export_items_send_their_format(qtbot, page):
    view, bridge = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    with qtbot.waitSignal(bridge.bulkExportRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('more-export-csv').click(); true")
    assert list(blocker.args) == [["10443"], "csv"]


def _escape(qtbot, view):
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', "
        "{key: 'Escape', bubbles: true})); true",
    )


def test_escape_closes_the_more_menu_and_keeps_the_selection(qtbot, page):
    """Spec section 10: Escape closes the innermost thing -- popover, then
    menu, then the selection. With the menu open it is the menu's turn."""
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    assert (
        _eval(qtbot, view, "document.getElementById('selection-menu').hidden") is False
    )

    _escape(qtbot, view)

    assert (
        _eval(qtbot, view, "document.getElementById('selection-menu').hidden") is True
    )
    assert _eval(qtbot, view, "state.selected.size") == 1
    assert _eval(qtbot, view, "document.activeElement.id") == "selection-more"


def test_escape_with_nothing_open_still_clears_the_selection(qtbot, page):
    """The fall-through: once the menu and the popover are shut, Escape goes
    back to meaning what it meant before this bundle. Dispatched on the table,
    which is where results.js binds the handler that clears the selection.
    """
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(
        qtbot,
        view,
        "document.getElementById('table').dispatchEvent(new KeyboardEvent("
        "'keydown', {key: 'Escape', bubbles: true})); true",
    )
    assert _eval(qtbot, view, "state.selected.size") == 0


def test_escape_closes_the_menu_before_it_clears_the_selection(qtbot, page):
    """Innermost first: the same key on the same element must shut the menu
    and leave the selection alone, then clear it on a second press."""
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")

    def escape_on_table():
        _eval(
            qtbot,
            view,
            "document.getElementById('table').dispatchEvent(new KeyboardEvent("
            "'keydown', {key: 'Escape', bubbles: true})); true",
        )

    escape_on_table()
    assert (
        _eval(qtbot, view, "document.getElementById('selection-menu').hidden") is True
    )
    assert _eval(qtbot, view, "state.selected.size") == 1

    escape_on_table()
    assert _eval(qtbot, view, "state.selected.size") == 0


def test_opening_more_closes_the_filter_menu(qtbot, page):
    """Both hang off a .menu-anchor, so the filter menu's outside-click guard
    used to treat a click on More as a click on itself."""
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.getElementById('add-filter').click(); true")
    assert _eval(qtbot, view, "document.getElementById('filter-menu').hidden") is False

    _eval(
        qtbot,
        view,
        "document.getElementById('selection-more').dispatchEvent("
        "new MouseEvent('mousedown', {bubbles: true}));"
        "document.getElementById('selection-more').click(); true",
    )

    assert _eval(qtbot, view, "document.getElementById('filter-menu').hidden") is True
    assert (
        _eval(qtbot, view, "document.getElementById('selection-menu').hidden") is False
    )
