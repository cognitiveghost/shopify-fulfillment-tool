"""The order detail pane (Bundle 13 spec §6.2-6.7), through Chromium. Never mark skip."""

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page

SHORT = "Cannot fulfill: TS-4409-B: Insufficient stock (need 6, have 4)"


def pane_lines():
    """Ready, short, review by the run (no SKU), review set by a person."""
    base = {
        "Shipping_Provider": "DPD",
        "Customer": "B. Fischer",
        "Destination_Country": "AT",
        "Total_Price": 204.3,
        "Created_At": "2026-09-11 06:00:00 +0000",
        "Internal_Tags": "[]",
        "Has_SKU": True,
        "Stock_Alert": "",
    }
    rows = []

    def add(order, status, sku, qty, left, note="", **extra):
        rows.append(
            {
                **base,
                "Order_Number": order,
                "Order_Fulfillment_Status": status,
                "SKU": sku,
                "Product_Name": f"Product {sku}",
                "Quantity": qty,
                "Final_Stock": left,
                "System_note": note,
                **extra,
            }
        )

    add("#10443", "Fulfillable", "TS-4410-B", 4, 96)
    add("#10443", "Fulfillable", "TS-9001-C", 2, 41)
    for sku, qty, left in (
        ("TS-4409-B", 6, 4),
        ("TS-9002-C", 2, 18),
        ("BX-3311-A", 1, 7),
    ):
        add("#10445", "Not Fulfillable", sku, qty, left, SHORT)
    add("#10447", "Not Fulfillable", None, 1, None, "[NO_SKU]", Has_SKU=False)
    add("#10447", "Not Fulfillable", "TS-6640-D", 1, 33)
    add(
        "#10449",
        "Fulfillable",
        "BX-7742-D",
        1,
        0,
        "Cannot fulfill: BX-7742-D: Out of stock",
        Internal_Tags='["vip"]',
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
    bridge.set_tag_categories({"prio": {"label": "Priority", "tags": ["rush", "vip"]}})
    bridge.set_orders(pane_lines())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 4")
    return view, bridge


def _js(qtbot, view, statement):
    _eval(qtbot, view, f"{statement}; true")


def _text(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"(document.querySelector({selector!r}) || {{textContent: null}}).textContent",
    )


def _select(qtbot, view, order):
    _js(
        qtbot,
        view,
        f"document.querySelector('#rows .row[data-order=\"{order}\"]').click()",
    )
    _until_js(
        qtbot,
        view,
        f"(document.querySelector('.pane-order') || {{}}).textContent === {order!r}",
    )


def _menu_item(menu, label):
    return f"[...document.querySelectorAll('#{menu} .menu-item')].find(b => b.textContent === {label!r}).click()"


def test_nothing_selected_says_how_to_move(qtbot, doc):
    view, _ = doc
    assert _text(qtbot, view, "#pane-empty .state-title") == "No order selected"
    assert "moves through the 4 shown." in _text(qtbot, view, "#pane-empty .state-text")


def test_the_pane_is_400_by_508_beside_the_table(qtbot, doc):
    view, _ = doc
    size = _eval(
        qtbot,
        view,
        "(r => Math.round(r.width) + 'x' + Math.round(r.height))(document.getElementById('pane').getBoundingClientRect())",
    )
    assert size == "400x508"


def test_a_short_order_names_the_sku_and_both_numbers(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10445")
    assert _text(qtbot, view, ".verdict-title") == "Cannot ship: 1 of 3 lines is short"
    assert (
        "There were 4 units of TS-4409-B left for this order, and it wants 6."
        in _text(qtbot, view, ".verdict-text")
    )
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#pane .line.short').length") == 1
    )
    assert _text(qtbot, view, ".pane-position") == "2 of 4"
    assert _text(qtbot, view, "#pane-status-verb") == "Mark fulfillable"


def test_a_ready_order_has_no_source_line_and_offers_hold(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10443")
    assert _text(qtbot, view, ".verdict-title") == "Ships complete"
    # runJavaScript on this VM's Qt build turns a JS null/undefined result into
    # "" rather than None (no element matched .verdict-source); confirmed via
    # document.querySelectorAll('.verdict-source').length === 0.
    assert _text(qtbot, view, ".verdict-source") == ""
    assert _text(qtbot, view, "#pane-status-verb") == "Hold"


@pytest.mark.parametrize(
    ("order", "title", "source", "by_hand"),
    [
        (
            "#10447",
            "Fix the data before this ships",
            "Detected by the run, not set by a person.",
            "false",
        ),
        (
            "#10449",
            "Marked fulfillable by hand",
            "Set by a person, not detected by the run.",
            "true",
        ),
    ],
)
def test_the_review_state_says_which_cause(qtbot, doc, order, title, source, by_hand):
    view, _ = doc
    _select(qtbot, view, order)
    assert _text(qtbot, view, ".verdict-title") == title
    assert _text(qtbot, view, ".verdict-source") == source
    assert (
        _eval(qtbot, view, "document.querySelector('.verdict').dataset.byHand")
        == by_hand
    )
    assert _eval(
        qtbot, view, "document.querySelector('.verdict .mark.solid') !== null"
    ) is (by_hand == "true")


@pytest.mark.parametrize(
    ("order", "click", "signal", "args"),
    [
        (
            "#10443",
            "document.getElementById('pane-status-verb').click()",
            "holdRequested",
            ["#10443"],
        ),
        (
            "#10445",
            "document.getElementById('pane-status-verb').click()",
            "fulfillRequested",
            ["#10445"],
        ),
        (
            "#10443",
            "document.getElementById('pane-exclude').click()",
            "excludeRequested",
            ["#10443"],
        ),
        (
            "#10449",
            "document.querySelector('.tag-chip[data-tag=\"vip\"]').click()",
            "tagRemovalRequested",
            ["#10449", "vip"],
        ),
    ],
)
def test_each_action_reaches_python(qtbot, doc, order, click, signal, args):
    view, bridge = doc
    _select(qtbot, view, order)
    with qtbot.waitSignal(getattr(bridge, signal), timeout=3000) as blocker:
        _js(qtbot, view, click)
    assert list(blocker.args) == args


def test_remove_this_line_sends_the_index_and_its_sku(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10445")
    _js(
        qtbot,
        view,
        "document.querySelector('#pane .line[data-index=\"1\"] .line-menu-button').click()",
    )
    with qtbot.waitSignal(bridge.lineRemovalRequested, timeout=3000) as blocker:
        _js(qtbot, view, _menu_item("line-menu", "Remove this line"))
    assert list(blocker.args) == ["#10445", 1, "TS-9002-C"]


def test_the_tag_menu_offers_only_tags_the_order_lacks(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10449")
    _js(qtbot, view, "document.getElementById('pane-add-tag').click()")
    items = _eval(
        qtbot,
        view,
        "[...document.querySelectorAll('#tag-menu .menu-item')].map(b => b.textContent).join('|')",
    )
    assert items == "rush"
    with qtbot.waitSignal(bridge.tagAddRequested, timeout=3000) as blocker:
        _js(qtbot, view, _menu_item("tag-menu", "rush"))
    assert list(blocker.args) == ["#10449", "rush"]


def test_choosing_a_tag_returns_focus_to_add_tag(qtbot, doc):
    """Spec §6.5: a choice closes the menu and focus returns to "+ Tag"."""
    view, bridge = doc
    _select(qtbot, view, "#10449")
    _js(qtbot, view, "document.getElementById('pane-add-tag').click()")
    with qtbot.waitSignal(bridge.tagAddRequested, timeout=3000):
        _js(qtbot, view, _menu_item("tag-menu", "rush"))
    assert _eval(qtbot, view, "document.querySelectorAll('.pane-menu').length") == 0
    assert _eval(qtbot, view, "document.activeElement.id") == "pane-add-tag"


def test_a_new_tag_is_typed_and_entered(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10443")
    _js(qtbot, view, "document.getElementById('pane-add-tag').click()")
    with qtbot.waitSignal(bridge.tagAddRequested, timeout=3000) as blocker:
        _js(
            qtbot,
            view,
            "(i => { i.value = ' gift '; i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })(document.getElementById('new-tag'))",
        )
    assert list(blocker.args) == ["#10443", "gift"]


def _table_width(qtbot, view):
    return _eval(
        qtbot,
        view,
        "Math.round(document.querySelector('.table-wrap').getBoundingClientRect().width)",
    )


def test_hiding_leaves_a_strip_and_showing_restores_the_table(qtbot, doc):
    view, _ = doc
    _js(qtbot, view, "document.getElementById('pane-hide').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'strip'"
    )
    assert _table_width(qtbot, view) == 1242
    _js(qtbot, view, "document.getElementById('pane-show').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'"
    )
    assert _table_width(qtbot, view) == 866


def test_a_narrow_page_collapses_the_pane_until_asked(qtbot, doc):
    view, _ = doc
    view.resize(1100, 692)
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'strip'"
    )
    _js(qtbot, view, "document.getElementById('pane-show').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'"
    )
    _until_js(
        qtbot,
        view,
        "(s => s.scrollWidth > s.clientWidth)(document.getElementById('scroller'))",
    )
