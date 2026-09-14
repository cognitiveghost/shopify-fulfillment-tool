"""Bundle 14: the one popover that carries a whole bulk action."""

import json

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page

CATEGORIES = {
    "handling": {"label": "Handling", "tags": ["FRAGILE", "FRAGILE-GLASS"]},
    "priority": {"label": "Priority", "tags": ["URGENT"]},
}


def popover_orders():
    """FRAGILE sits on #10443 only, so every count in this file is the true one."""
    rows = []

    def add(order, tags):
        rows.append(
            {
                "Order_Number": order,
                "SKU": "TS-4409-B",
                "Product_Name": "Product TS-4409-B",
                "Quantity": 1,
                "Final_Stock": 10,
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DPD",
                "Total_Price": 10.0,
                "Internal_Tags": tags,
                "Customer": "A",
            }
        )

    add("10443", '["FRAGILE"]')
    add("10444", "[]")
    add("10445", "[]")
    return pd.DataFrame(rows)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_tag_categories(CATEGORIES)
    bridge.set_orders(popover_orders())
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
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _open_add_tag(qtbot, view, orders):
    _select(qtbot, view, orders)
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-add-tag').click(); true")


def _open_remove_tag(qtbot, view, orders):
    _select(qtbot, view, orders)
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-remove-tag').click(); true")


def test_the_title_carries_the_count(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10443", "10444"])
    assert _text(qtbot, view, "#bulk-title") == "Add a tag to 2 orders"


def test_the_list_is_grouped_by_tag_category(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10444"])
    groups = _json(
        qtbot,
        view,
        "[...document.querySelectorAll('#bulk-list .menu-group')].map(g => g.textContent)",
    )
    assert groups == ["Handling", "Priority", "NEW"]


def test_a_tag_already_on_some_orders_shows_its_count(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10443", "10444", "10445"])
    assert _text(qtbot, view, "[data-tag='FRAGILE'] .bulk-count") == "on 1 of 3"


def test_a_tag_on_no_selected_order_shows_no_count(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10443"])
    assert (
        _eval(
            qtbot,
            view,
            "document.querySelectorAll(\"[data-tag='URGENT'] .bulk-count\").length",
        )
        == 0
    )


def test_the_verb_excludes_the_orders_that_already_carry_it(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10443", "10444", "10445"])
    _eval(qtbot, view, "document.querySelector(\"[data-tag='FRAGILE']\").click(); true")
    assert _text(qtbot, view, "#bulk-verb") == "Add to 2 orders"


def test_the_verb_is_disabled_until_a_tag_is_picked(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10444"])
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is True


def test_a_tag_already_on_every_order_cannot_be_added(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.querySelector(\"[data-tag='FRAGILE']\").click(); true")
    assert _text(qtbot, view, "#bulk-verb") == "Already on all 1"
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is True


def test_committing_sends_the_orders_and_the_tag(qtbot, page):
    view, bridge = page
    _open_add_tag(qtbot, view, ["10444", "10445"])
    _eval(qtbot, view, "document.querySelector(\"[data-tag='URGENT']\").click(); true")
    with qtbot.waitSignal(bridge.bulkTagAddRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10444", "10445"], "URGENT"]


def test_removing_sends_the_orders_and_the_tag(qtbot, page):
    view, bridge = page
    _open_remove_tag(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.querySelector(\"[data-tag='FRAGILE']\").click(); true")
    with qtbot.waitSignal(bridge.bulkTagRemovalRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10443"], "FRAGILE"]


def test_a_new_tag_commits_on_enter(qtbot, page):
    view, bridge = page
    _open_add_tag(qtbot, view, ["10444"])
    _eval(qtbot, view, "document.getElementById('bulk-new-tag').value = 'FRAG'; true")
    with qtbot.waitSignal(bridge.bulkTagAddRequested, timeout=3000) as blocker:
        _eval(
            qtbot,
            view,
            "document.getElementById('bulk-new-tag').dispatchEvent("
            "new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); true",
        )
    assert list(blocker.args) == [["10444"], "FRAG"]


def test_escape_closes_the_popover_and_keeps_the_selection(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10444"])
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-popover').length") == 0
    assert _eval(qtbot, view, "state.selected.size") == 1


def test_a_click_outside_closes_it(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10444"])
    _eval(
        qtbot,
        view,
        "document.getElementById('search').dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-popover').length") == 0


def test_the_arrows_walk_the_rows(qtbot, page):
    view, _ = page
    _open_add_tag(qtbot, view, ["10444"])
    _eval(
        qtbot,
        view,
        "document.querySelector('#bulk-list .bulk-row').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.activeElement.dataset.tag") == "FRAGILE-GLASS"


def test_the_pane_tag_menu_still_groups_and_excludes_own_tags(qtbot, page):
    """The pane's menu now shares the builder; it must not have changed."""
    view, _ = page
    _eval(qtbot, view, "state.cursorKey = '10443'; render(); true")
    _eval(qtbot, view, "document.getElementById('pane-add-tag').click(); true")
    labels = _json(
        qtbot,
        view,
        "[...document.querySelectorAll('.pane-menu .menu-item')].map(b => b.textContent.trim())",
    )
    assert "FRAGILE" not in labels  # #10443 already carries it
