"""Bundle 14: the bar that exists only while orders are selected."""

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
