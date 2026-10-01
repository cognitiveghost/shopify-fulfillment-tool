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
    """FRAGILE sits on #10443 only. TS-4409-B sits on #10443 and #10445 (2
    orders); TS-0001-X sits on #10443 only (1 order); TS-9999-Z on #10444
    only (1 order) -- every count and sort order in this file is the true one.
    """
    rows = []

    def add(order, sku, tags):
        rows.append(
            {
                "Order_Number": order,
                "SKU": sku,
                "Product_Name": "Product " + sku,
                "Quantity": 1,
                "Final_Stock": 10,
                "Order_Fulfillment_Status": "Fulfillable",
                "Shipping_Provider": "DPD",
                "Total_Price": 10.0,
                "Internal_Tags": tags,
                "Customer": "A",
            }
        )

    add("10443", "TS-4409-B", '["FRAGILE"]')
    add("10443", "TS-0001-X", '["FRAGILE"]')
    add("10444", "TS-9999-Z", "[]")
    add("10445", "TS-4409-B", "[]")
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


def _open_sku(qtbot, view, orders, item):
    _select(qtbot, view, orders)
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, f"document.getElementById('{item}').click(); true")


def _pick(qtbot, view, tag):
    _eval(qtbot, view, f"document.querySelector(\"[data-tag='{tag}']\").click(); true")


def _changes(qtbot, view):
    return _json(
        qtbot,
        view,
        "[...document.querySelectorAll('#bulk-changes .bulk-change')]"
        ".map(e => e.textContent)",
    )


def test_the_sku_list_counts_orders_not_lines(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-sku")
    assert _text(qtbot, view, "[data-tag='TS-4409-B'] .bulk-count") == "on 2 of 2"


def test_the_sku_list_sorts_by_count_then_name(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-sku")
    skus = _json(
        qtbot,
        view,
        "[...document.querySelectorAll('#bulk-list .bulk-row')].map(b => b.dataset.tag)",
    )
    assert skus[0] == "TS-4409-B"  # on 2 orders, ahead of TS-0001-X on 1


def test_removing_a_sku_says_what_will_change(qtbot, page):
    """Phase 2 spec section 5.7. 10443 keeps its other line; 10445 has only
    this one. All three orders in the session are fulfillable."""
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-sku")
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is True
    assert _eval(qtbot, view, "document.getElementById('bulk-changes').hidden") is True
    _pick(qtbot, view, "TS-4409-B")
    assert _changes(qtbot, view) == [
        "2 TS-4409-B lines removed from 10443, 10445",
        "10445 has no lines left and leaves the session",
        "2 units of TS-4409-B go back to stock",
        "Export goes from 3 to 2 orders",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Remove TS-4409-B from 2"
    assert "critical" in _eval(qtbot, view, "document.getElementById('bulk-verb').className")
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is False
    assert (
        _text(qtbot, view, ".bulk-hint")
        == "You can undo this from the confirmation that follows."
    )


def test_removing_orders_with_a_sku_says_what_will_change(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-orders")
    _pick(qtbot, view, "TS-4409-B")
    assert _changes(qtbot, view) == [
        "10443, 10445 leave the session: results, export and labels",
        (
            "3 units go back to stock. Other orders do not get them until you mark"
            " them fulfillable or run the analysis again"
        ),
        "Export goes from 3 to 1 order",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Remove 2 orders"


def test_excluding_orders_needs_no_pick_and_says_what_will_change(qtbot, page):
    view, bridge = page
    _select(qtbot, view, ["10444"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-exclude').click(); true")
    assert _text(qtbot, view, "#bulk-title") == "Exclude this order from the run"
    assert _eval(qtbot, view, "document.getElementById('bulk-list').hidden") is True
    assert _changes(qtbot, view) == [
        "10444 leaves the session: results, export and labels",
        (
            "1 unit goes back to stock. Other orders do not get them until you mark"
            " them fulfillable or run the analysis again"
        ),
        "Export goes from 3 to 2 orders",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Exclude 1 order"
    with qtbot.waitSignal(bridge.bulkExcludeRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10444"]]


def _line(order, sku, status, note="", qty=1):
    return {
        "Order_Number": order,
        "SKU": sku,
        "Product_Name": "Product " + sku,
        "Quantity": qty,
        "Final_Stock": 10,
        "Order_Fulfillment_Status": status,
        "Shipping_Provider": "DPD",
        "Total_Price": 10.0,
        "Internal_Tags": "[]",
        "Customer": "A",
        "System_note": note,
    }


def test_a_blocked_order_is_told_it_stays_blocked(qtbot, page):
    """The app does not re-evaluate an order when its short line goes, so the
    popover must not promise that it does."""
    view, bridge = page
    short = "Cannot fulfill: X-1: Insufficient stock (need 2, have 0)"
    bridge.set_orders(
        pd.DataFrame(
            [
                _line("B1", "X-1", "Not Fulfillable", short, qty=2),
                _line("B1", "Y-1", "Not Fulfillable", short),
                _line("F1", "Y-1", "Fulfillable"),
            ]
        )
    )
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 2")
    _open_sku(qtbot, view, ["B1"], "more-remove-sku")
    _pick(qtbot, view, "X-1")
    assert _changes(qtbot, view) == [
        "1 X-1 line removed from B1",
        "B1 stays Blocked until marked fulfillable",
        "Export stays at 1 order",
    ]


def test_fifty_orders_are_named_three_and_counted(qtbot, page):
    """Review focus 2."""
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame([_line(f"O{i:02d}", "S-1", "Fulfillable") for i in range(1, 51)])
    )
    _until_js(qtbot, view, "state.records.length === 50")
    _eval(
        qtbot,
        view,
        "state.selected = new Set(state.records.map(r => r.key)); render(); true",
    )
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-exclude').click(); true")
    assert _changes(qtbot, view)[0] == (
        "O01, O02, O03 and 47 more leave the session: results, export and labels"
    )
    assert _text(qtbot, view, "#bulk-verb") == "Exclude 50 orders"


def test_thirty_skus_scroll_and_the_verb_stays_on_screen(qtbot, page):
    """Review focus 1: the picker scrolls inside the popover; the foot does not."""
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame([_line("W1", f"SKU-{i:02d}", "Fulfillable") for i in range(30)])
    )
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 1")
    _open_sku(qtbot, view, ["W1"], "more-remove-sku")
    _pick(qtbot, view, "SKU-00")
    fits = _json(
        qtbot,
        view,
        "(function () {"
        " var verb = document.getElementById('bulk-verb').getBoundingClientRect();"
        " var area = document.getElementById('table-area').getBoundingClientRect();"
        " var list = document.getElementById('bulk-list');"
        " return [verb.bottom <= area.bottom, list.scrollHeight > list.clientHeight];"
        " })()",
    )
    assert fits == [True, True]


def _open_exclude(qtbot, view, orders):
    _select(qtbot, view, orders)
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-exclude').click(); true")


def test_the_popover_opens_under_more(qtbot, page):
    view, _ = page
    _open_exclude(qtbot, view, ["10444"])
    edges = _json(
        qtbot,
        view,
        "['bulk-popover', 'selection-more'].map("
        "id => document.getElementById(id).getBoundingClientRect().left)",
    )
    assert edges[0] == edges[1]


def test_a_changed_selection_closes_the_popover(qtbot, page):
    """The popover is the only confirmation a removal gets, so it must never
    say one order and then act on every order shown (Ctrl+A from the table)."""
    view, _ = page
    _open_exclude(qtbot, view, ["10444"])
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-popover').length") == 1
    _eval(qtbot, view, "selectAll(true); true")
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-popover').length") == 0


def test_an_orders_push_closes_the_popover(qtbot, page):
    """An undo or a tag re-pushes the session: the lines it showed may be stale."""
    view, bridge = page
    _open_exclude(qtbot, view, ["10444"])
    bridge.set_orders(popover_orders())
    _until_js(qtbot, view, "document.querySelectorAll('#bulk-popover').length === 0")
    assert _eval(qtbot, view, "state.selected.size") == 1


def test_committing_a_line_removal_sends_the_sku(qtbot, page):
    view, bridge = page
    _open_sku(qtbot, view, ["10443"], "more-remove-sku")
    _eval(
        qtbot, view, "document.querySelector(\"[data-tag='TS-4409-B']\").click(); true"
    )
    with qtbot.waitSignal(bridge.bulkSkuRemovalRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10443"], "TS-4409-B"]


def test_committing_an_order_removal_sends_the_sku(qtbot, page):
    view, bridge = page
    _open_sku(qtbot, view, ["10443"], "more-remove-orders")
    _eval(
        qtbot, view, "document.querySelector(\"[data-tag='TS-4409-B']\").click(); true"
    )
    with qtbot.waitSignal(bridge.bulkOrderRemovalRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10443"], "TS-4409-B"]


def test_a_search_row_appears_only_above_ten_skus(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10443"], "more-remove-sku")
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-search').length") == 0


def test_bulk_menu_reads_naturally_for_one_order(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10444"])
    labels = _json(qtbot, view, "moreItems().map(i => i.label)")
    assert "Remove a SKU from this order" in labels
    assert "Export this order to Excel" in labels
    assert "Export this order to CSV" in labels
    assert not any(label and "these 1" in label for label in labels)
    # Tooltips are copy too -- "None of these 1 order carry a tag" is the same
    # defect one attribute over.
    titles = _json(qtbot, view, "moreItems().map(i => i.title || '')")
    assert not any("these 1" in title for title in titles)
    assert "This order doesn't carry a tag" in titles


def test_the_sku_popover_title_reads_naturally_for_one_order(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10444"], "more-remove-sku")
    assert _text(qtbot, view, "#bulk-title") == "Remove a SKU from this order"


def test_bulk_menu_still_pluralises_for_many(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444", "10445"])
    labels = _json(qtbot, view, "moreItems().map(i => i.label)")
    assert "Remove a SKU from these 3 orders" in labels
    assert "Export these 3 orders to Excel" in labels
    assert "Export these 3 orders to CSV" in labels


def test_the_remove_tag_list_is_ungrouped(qtbot, page):
    """Spec section 5.2: "ungrouped -- a tag's category does not help you find
    a tag you can see". The add list groups; this one must not."""
    view, _ = page
    _open_remove_tag(qtbot, view, ["10443"])
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#bulk-list .menu-group').length")
        == 0
    )
    assert _text(qtbot, view, "[data-tag='FRAGILE'] .bulk-count") == "on 1 of 1"


def wide_sku_orders():
    """#10443 carries 11 distinct SKUs, #10444 exactly 10 -- the two sides of
    section 5.3's "the search row shows above 10 rows"."""
    rows = []
    for order, count in (("10443", 11), ("10444", 10)):
        for i in range(count):
            rows.append(
                {
                    "Order_Number": order,
                    "SKU": f"{order}-SKU-{i:02d}",
                    "Product_Name": "Product",
                    "Quantity": 1,
                    "Final_Stock": 10,
                    "Order_Fulfillment_Status": "Fulfillable",
                    "Shipping_Provider": "DPD",
                    "Total_Price": 10.0,
                    "Internal_Tags": "[]",
                    "Customer": "A",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def wide_page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_tag_categories(CATEGORIES)
    bridge.set_orders(wide_sku_orders())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 2")
    return view, bridge


def test_exactly_ten_skus_is_still_no_search_row(qtbot, wide_page):
    view, _ = wide_page
    _open_sku(qtbot, view, ["10444"], "more-remove-sku")
    assert _eval(qtbot, view, "document.querySelectorAll('.bulk-row').length") == 10
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-search').length") == 0


def test_above_ten_skus_the_search_row_appears_and_filters(qtbot, wide_page):
    view, _ = wide_page
    _open_sku(qtbot, view, ["10443"], "more-remove-sku")
    assert _eval(qtbot, view, "document.querySelectorAll('#bulk-search').length") == 1

    _eval(
        qtbot,
        view,
        "const s = document.getElementById('bulk-search');"
        "s.value = 'SKU-07'; s.dispatchEvent(new Event('input', {bubbles: true})); true",
    )
    shown = _json(
        qtbot,
        view,
        "[...document.querySelectorAll('.bulk-row')].filter(r => !r.hidden)"
        ".map(r => r.dataset.tag)",
    )
    assert shown == ["10443-SKU-07"]


def test_the_arrows_skip_the_rows_the_search_hid(qtbot, wide_page):
    """The walker filters on .hidden, so a filtered list must not step into
    a row the operator cannot see."""
    view, _ = wide_page
    _open_sku(qtbot, view, ["10443"], "more-remove-sku")
    _eval(
        qtbot,
        view,
        "const s = document.getElementById('bulk-search');"
        "s.value = 'SKU-0'; s.dispatchEvent(new Event('input', {bubbles: true})); true",
    )
    _eval(
        qtbot,
        view,
        "const first = [...document.querySelectorAll('.bulk-row')]"
        ".filter(r => !r.hidden)[0];"
        "first.focus();"
        "first.dispatchEvent(new KeyboardEvent('keydown', "
        "{key: 'ArrowDown', bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.activeElement.dataset.tag") == "10443-SKU-01"
