"""Sets, Weight, Reports and Tag categories, driven through a real Chromium
(phase 9 spec sections 4.7, 5.8, 6.8, 7.7 and 8.3).

The page is a renderer: every test pushes a view built by a draft and reads
the DOM back, or clicks and reads what the bridge was sent. 868x700 is the
page area a small dialog gives. Never mark skip.
"""

import copy

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js
from test_settings_web_page import (
    _active,
    _attr,
    _click,
    _count,
    _key,
    _keydown,
    _prop,
    _show,
    _style,
    _text,
    _texts,
    _type,
    _wired,
)

from gui.settings.bridge import mount_settings_page
from gui.settings.reports_state import ReportsDraft
from gui.settings.sets_state import NO_SKU, SetsDraft
from gui.settings.tags_state import TagsDraft
from gui.settings.weight_state import NUMBER_PROBLEM, WeightDraft
from gui.theme_manager import get_theme_manager

SETS = {
    "SET-A": [{"sku": "HAT", "quantity": 1}, {"sku": "SCARF", "quantity": 2}],
    "SET-B": [{"sku": "MUG", "quantity": 1}],
}
WEIGHT = {
    "volumetric_divisor": 5000,
    "products": {
        "SKU1": {"name": "Widget", "length_cm": 10.0, "width_cm": 5.0, "height_cm": 2.0, "no_packaging": False},
        "SKU2": {"name": "Gadget", "length_cm": 0.0, "width_cm": 0.0, "height_cm": 0.0, "no_packaging": True},
    },
    "boxes": [{"name": "Small", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}],
}
PACKING = [
    {"name": "DHL", "output_filename": "DHL.xlsx", "filters": [{"field": "Shipping_Provider", "operator": "equals", "value": "DHL"}], "exclude_skus": []},
    {"name": "DPD", "output_filename": "", "filters": [], "exclude_skus": [], "columns": ["SKU"]},
]
STOCK = [{"name": "Daily", "output_filename": "daily.xls", "filters": []}]
TAGS = {
    "version": 2,
    "categories": {
        "packaging": {
            "label": "Packaging",
            "color": "#00FF00",
            "order": 1,
            "tags": ["BOX", "BAG"],
            "sku_writeoff": {"enabled": True, "mappings": {"BOX": [{"sku": "PKG-BOX-S", "quantity": 1.0}]}},
        },
        "priority": {"label": "Priority", "color": "#FF0000", "order": 2, "tags": ["VIP"]},
    },
}


def frame():
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#2"],
            "SKU": ["A", "B"],
            "Shipping_Provider": ["DHL", "DPD"],
            "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"],
        }
    )


def sets(stored=None):
    return SetsDraft(copy.deepcopy(SETS if stored is None else stored))


def weight(stored=None):
    return WeightDraft(copy.deepcopy(WEIGHT if stored is None else stored), {}, "auto")


def reports():
    return ReportsDraft(copy.deepcopy(PACKING), copy.deepcopy(STOCK), frame())


def tags(stored=None):
    return TagsDraft(copy.deepcopy(TAGS if stored is None else stored))


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _settled(qtbot, view, expression):
    """Wait until the page has answered an edit: `expression` holds."""
    _until_js(qtbot, view, expression)


def _edit(qtbot, view, seen, action):
    """Wait for the page to have sent `action`, and return its arguments."""
    qtbot.waitUntil(lambda: any(sent == action for sent, _args in seen), timeout=3000)
    return next(args for sent, args in reversed(seen) if sent == action)


# --- Sets ---------------------------------------------------------------------


def test_sets_draws_the_head_the_bar_and_a_row_per_set(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, sets())
    assert _text(qtbot, view, ".page-title") == "Sets"
    assert _text(qtbot, view, _key("set-add")) == "Add set"
    assert _text(qtbot, view, ".list-count") == "2 sets"
    assert _texts(qtbot, view, ".list-row .list-name") == ["SET-A", "SET-B"]
    assert _texts(qtbot, view, '[data-set="1"] .rule-chip') == ["HAT ×1", "SCARF ×2"]
    assert _style(qtbot, view, ".list-row", "display") == "grid"
    assert _prop(qtbot, view, _key("sets-export"), "disabled") is False


def test_a_set_opens_in_place_and_its_fields_report_each_keystroke(qtbot, page):
    view, bridge = page
    d = sets()
    seen = _wired(qtbot, view, bridge, d)
    _click(qtbot, view, _key("set-1-sku"))
    _settled(qtbot, view, "document.querySelector('.list-row.open .list-name-field') !== null")
    assert _active(qtbot, view) == "set-1-sku"
    assert _count(qtbot, view, ".comp-row") == 2

    _type(qtbot, view, _key("set-1-c1-quantity"), "x")
    assert _edit(qtbot, view, seen, "comp_quantity") == ["1", "1", "x"]
    _settled(qtbot, view, "document.querySelector('.comp-row .invalid') !== null")
    # The field being typed in keeps the focus and its text.
    assert _active(qtbot, view) == "set-1-c1-quantity"
    assert _prop(qtbot, view, _key("set-1-c1-quantity"), "value") == "x"
    assert _text(qtbot, view, '[data-comp="1"] .problem') == "Type a whole number from 1 to 9999."

    _click(qtbot, view, _key("set-1-comp-add"))
    _settled(qtbot, view, "document.querySelectorAll('.comp-row').length === 3")
    assert _active(qtbot, view) == "set-1-c2-sku"
    _click(qtbot, view, _key("set-1-c2-remove"))
    _settled(qtbot, view, "document.querySelectorAll('.comp-row').length === 2")
    assert _active(qtbot, view) == "set-1-comp-add"

    _click(qtbot, view, _key("set-1-done"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') === null")
    assert _text(qtbot, view, '[data-set="1"] .problem') == "Type a whole number from 1 to 9999."


def test_add_set_opens_a_new_row_first_with_its_sku_focused(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, sets())
    _click(qtbot, view, _key("set-add"))
    assert _edit(qtbot, view, seen, "set_add") == []
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 3")
    assert _attr(qtbot, view, ".list-row", "data-set") == "3"
    assert _active(qtbot, view) == "set-3-sku"
    assert _text(qtbot, view, ".list-row.open .problem") == NO_SKU


def test_the_sets_filter_and_delete(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, sets())
    _type(qtbot, view, _key("sets-filter"), "mug")
    assert _edit(qtbot, view, seen, "filter") == ["mug"]
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 1")
    assert _active(qtbot, view) == "sets-filter"
    _type(qtbot, view, _key("sets-filter"), "zzz")
    _settled(qtbot, view, "document.querySelector('.list-none') !== null")
    assert _text(qtbot, view, ".list-none") == "No set matches “zzz”."
    _type(qtbot, view, _key("sets-filter"), "")
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 2")
    _click(qtbot, view, _key("set-2-delete"))
    assert _edit(qtbot, view, seen, "set_delete") == ["2"]
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 1")


def test_the_import_menu_and_export_ask_the_bridge(qtbot, page):
    view, bridge = page
    imports, exports = [], []
    bridge.importRequested.connect(imports.append)
    bridge.exportRequested.connect(exports.append)
    _show(qtbot, view, bridge, sets())
    _click(qtbot, view, _key("sets-import"))
    _settled(qtbot, view, "document.querySelector('.menu') !== null")
    assert _text(qtbot, view, ".menu .menu-group") == "CSV columns: Set_SKU, Component_SKU, Component_Quantity"
    _click(qtbot, view, _key("sets-import-replace"))
    qtbot.waitUntil(lambda: imports == ["sets-replace"], timeout=3000)
    assert _count(qtbot, view, ".menu") == 0
    _click(qtbot, view, _key("sets-export"))
    qtbot.waitUntil(lambda: exports == ["sets"], timeout=3000)


def test_with_no_set_the_page_is_the_empty_state(qtbot, page):
    view, bridge = page
    imports = []
    bridge.importRequested.connect(imports.append)
    _show(qtbot, view, bridge, sets({}))
    assert _text(qtbot, view, ".state-title") == "No sets yet"
    assert _count(qtbot, view, ".page-head .btn") == 0
    assert _texts(qtbot, view, ".state .btn") == ["Add set", "Import from CSV…"]
    _click(qtbot, view, _key("sets-import-merge"))
    qtbot.waitUntil(lambda: imports == ["sets-merge"], timeout=3000)


# --- Weight -------------------------------------------------------------------


def test_weight_draws_three_cards_and_a_row_of_fields_per_product(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, weight())
    assert _texts(qtbot, view, ".card-title") == ["Volumetric weight", "Products", "Boxes"]
    assert _prop(qtbot, view, _key("divisor"), "value") == "5000"
    assert _texts(qtbot, view, ".weight-heads.product-row span") == ["SKU", "Name", "L", "W", "H", "Vol. weight", "No packaging", ""]
    assert _count(qtbot, view, ".product-rows .product-row") == 2
    assert _prop(qtbot, view, _key("product-1-l"), "value") == "10"
    assert _text(qtbot, view, '[data-product="1"] .weight-value') == "0.02 kg"
    assert _attr(qtbot, view, _key("product-2-no-packaging"), "aria-checked") == "true"
    assert _text(qtbot, view, ".list-count") == "2 products, 1 with no size"
    assert _count(qtbot, view, ".box-rows .box-row") == 1
    assert _style(qtbot, view, ".product-rows .product-row", "display") == "grid"


def test_typing_a_dimension_reports_it_marks_a_bad_one_and_keeps_focus(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, weight())
    _type(qtbot, view, _key("product-1-w"), "wide")
    assert _edit(qtbot, view, seen, "product_text") == ["1", "w", "wide"]
    _settled(qtbot, view, "document.querySelector('.product-row .invalid') !== null")
    assert _active(qtbot, view) == "product-1-w"
    assert _text(qtbot, view, '[data-product="1"] .problem') == NUMBER_PROBLEM
    _type(qtbot, view, _key("product-1-w"), "6")
    _settled(qtbot, view, "document.querySelector('.product-row .invalid') === null")
    assert _text(qtbot, view, '[data-product="1"] .weight-value') == "0.024 kg"

    _type(qtbot, view, _key("divisor"), "6000")
    assert _edit(qtbot, view, seen, "divisor") == ["6000"]
    _click(qtbot, view, _key("product-1-no-packaging"))
    assert _edit(qtbot, view, seen, "product_no_packaging") == ["1", True]
    _type(qtbot, view, _key("box-3-h"), "12")
    assert _edit(qtbot, view, seen, "box_text") == ["3", "h", "12"]


def test_add_product_focuses_the_new_first_row_and_add_box_the_new_last_one(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, weight())
    _click(qtbot, view, _key("product-add"))
    _settled(qtbot, view, "document.querySelectorAll('.product-rows .product-row').length === 3")
    assert _active(qtbot, view) == "product-4-sku"
    assert _attr(qtbot, view, ".product-rows .product-row", "data-product") == "4"
    _click(qtbot, view, _key("product-4-remove"))
    _settled(qtbot, view, "document.querySelectorAll('.product-rows .product-row').length === 2")
    assert _active(qtbot, view) == "product-add"
    _click(qtbot, view, _key("box-add"))
    _settled(qtbot, view, "document.querySelectorAll('.box-rows .box-row').length === 2")
    assert _active(qtbot, view) == "box-5-name"


def test_the_weight_imports_and_exports_ask_the_bridge(qtbot, page):
    view, bridge = page
    imports, exports = [], []
    bridge.importRequested.connect(imports.append)
    bridge.exportRequested.connect(exports.append)
    _show(qtbot, view, bridge, weight())
    _click(qtbot, view, _key("products-import"))
    _settled(qtbot, view, "document.querySelector('.menu') !== null")
    _click(qtbot, view, _key("products-import-dims"))
    _click(qtbot, view, _key("boxes-import"))
    _click(qtbot, view, _key("products-export"))
    _click(qtbot, view, _key("boxes-export"))
    qtbot.waitUntil(lambda: (imports, exports) == (["products-dims", "boxes"], ["products", "boxes"]), timeout=3000)


def test_weight_with_nothing_listed_says_so_and_cannot_export(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, weight({}))
    assert _texts(qtbot, view, ".card-empty") == ["No products yet. Add one, or import them from a CSV.", "No boxes yet."]
    assert _prop(qtbot, view, _key("products-export"), "disabled") is True
    assert _prop(qtbot, view, _key("boxes-export"), "disabled") is True


# --- Reports ------------------------------------------------------------------


def test_reports_draws_a_card_per_kind_with_a_summary_and_a_match_count(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, reports())
    assert _texts(qtbot, view, ".card-title") == ["Packing lists", "Stock exports"]
    assert _texts(qtbot, view, '[data-kind="packing"] .list-name') == ["DHL", "DPD"]
    assert _texts(qtbot, view, '[data-report="1"] .rule-line span') == ["Shipping_Provider", "equals", "DHL"]
    assert _text(qtbot, view, '[data-report="1"] .report-match') == "Matches 1 order · 1 row"
    assert _text(qtbot, view, '[data-report="2"] .problem') == "No file name yet, so this report can't be generated."
    assert _prop(qtbot, view, _key("report-1-up"), "disabled") is True
    assert _prop(qtbot, view, _key("report-1-down"), "disabled") is False
    assert _count(qtbot, view, ".page-head .btn") == 0


def test_a_report_opens_and_its_filter_is_the_rules_condition_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, reports())
    _click(qtbot, view, _key("report-1-name"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') !== null")
    assert _active(qtbot, view) == "report-1-name"
    assert _count(qtbot, view, ".list-editor .cond-row") == 1
    assert _prop(qtbot, view, _key("report-1-f0-value"), "value") == "DHL"

    _type(qtbot, view, _key("report-1-f0-value"), "FEDEX")
    assert _edit(qtbot, view, seen, "filter_value") == ["1", "0", "FEDEX"]
    _settled(qtbot, view, "document.querySelector('.report-match.warn') !== null")
    assert _text(qtbot, view, ".list-editor .report-match") == "Matches no orders. Check the filters."
    assert _style(qtbot, view, ".report-match.warn", "color") == _rgb(get_theme_manager().get_current_theme().status_warning)

    _click(qtbot, view, _key("report-1-f0-op"))
    _settled(qtbot, view, "document.querySelector('.menu') !== null")
    _click(qtbot, view, '.menu [data-value="is empty"]')
    assert _edit(qtbot, view, seen, "filter_operator") == ["1", "0", "is empty"]
    _settled(qtbot, view, "document.querySelector('.cond-none') !== null")

    _click(qtbot, view, _key("report-1-filter-add"))
    _settled(qtbot, view, "document.querySelectorAll('.list-editor .cond-row').length === 2")
    assert _active(qtbot, view) == "report-1-f1-field"
    _click(qtbot, view, _key("report-1-f1-remove"))
    assert _edit(qtbot, view, seen, "filter_remove") == ["1", "1"]

    _type(qtbot, view, _key("report-1-filename"), "dhl.xlsx")
    assert _edit(qtbot, view, seen, "report_filename") == ["1", "dhl.xlsx"]
    _type(qtbot, view, _key("report-1-exclude"), "A, B")
    assert _edit(qtbot, view, seen, "report_exclude") == ["1", "A, B"]


def test_a_packing_lists_columns_are_chips_added_from_a_menu(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, reports())
    _click(qtbot, view, _key("report-2-name"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') !== null")
    assert _texts(qtbot, view, ".report-chips .chip .mono") == ["SKU"]
    _click(qtbot, view, _key("report-2-column-add"))
    _settled(qtbot, view, "document.querySelector('.menu') !== null")
    _click(qtbot, view, '.menu [data-name="Order_Number"]')
    assert _edit(qtbot, view, seen, "column_add") == ["2", "Order_Number"]
    _settled(qtbot, view, "document.querySelectorAll('.report-chips .chip').length === 2")
    assert _texts(qtbot, view, ".report-chips .chip .mono") == ["SKU", "Order_Number"]
    _click(qtbot, view, _key("report-2-column-remove:SKU"))
    assert _edit(qtbot, view, seen, "column_remove") == ["2", "SKU"]


def test_a_stock_export_has_no_exclude_and_no_columns(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, reports())
    _click(qtbot, view, _key("report-3-name"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') !== null")
    assert _texts(qtbot, view, ".list-editor .editor-label") == ["File name", "Filters"]


def test_reports_add_move_and_delete(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, reports())
    _click(qtbot, view, _key("report-1-down"))
    assert _edit(qtbot, view, seen, "report_move") == ["1", "down"]
    _settled(qtbot, view, "document.querySelector('[data-kind=\"packing\"] .list-row').dataset.report === '2'")
    # At the edge now: the other button takes the focus.
    assert _active(qtbot, view) == "report-1-up"
    _click(qtbot, view, _key("report-add-stock"))
    assert _edit(qtbot, view, seen, "report_add") == ["stock"]
    _settled(qtbot, view, "document.querySelectorAll('[data-kind=\"stock\"] .list-row').length === 2")
    assert _active(qtbot, view) == "report-4-name"
    _click(qtbot, view, _key("report-4-delete"))
    assert _edit(qtbot, view, seen, "report_delete") == ["4"]
    _settled(qtbot, view, "document.querySelectorAll('[data-kind=\"stock\"] .list-row').length === 1")
    assert _active(qtbot, view) == "report-add-stock"


# --- Tag categories -----------------------------------------------------------


def test_tags_draws_a_row_per_category_with_its_tags_and_a_badge(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, tags())
    assert _text(qtbot, view, _key("cat-add")) == "Add category"
    assert _text(qtbot, view, ".list-count") == "2 categories, 3 tags"
    assert _texts(qtbot, view, ".list-row .list-name") == ["Packaging", "Priority"]
    assert _texts(qtbot, view, '[data-category="1"] .rule-chip') == ["BOX", "BAG"]
    assert _texts(qtbot, view, ".list-row .badge") == ["Write-off"]


def test_a_category_opens_and_enter_adds_a_tag_in_capitals(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, tags())
    _click(qtbot, view, _key("cat-2-label"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') !== null")
    assert _active(qtbot, view) == "cat-2-label"
    assert _texts(qtbot, view, ".list-editor .chip .mono") == ["VIP"]

    _type(qtbot, view, _key("cat-2-tag-input"), "urgent")
    _keydown(qtbot, view, "Enter", _key("cat-2-tag-input"))
    assert _edit(qtbot, view, seen, "tag_add") == ["2", "urgent"]
    _settled(qtbot, view, "document.querySelectorAll('.list-editor .chip').length === 2")
    assert _texts(qtbot, view, ".list-editor .chip .mono") == ["VIP", "URGENT"]
    assert _prop(qtbot, view, _key("cat-2-tag-input"), "value") == ""
    assert _active(qtbot, view) == "cat-2-tag-input"

    _type(qtbot, view, _key("cat-2-tag-input"), "box")
    _keydown(qtbot, view, "Enter", _key("cat-2-tag-input"))
    _settled(qtbot, view, "document.querySelector('.list-editor .problem') !== null")
    assert _text(qtbot, view, ".list-editor .problem") == "BOX is already in Packaging. A tag belongs to one category."

    _click(qtbot, view, _key("cat-2-tag-remove:VIP"))
    assert _edit(qtbot, view, seen, "tag_remove") == ["2", "VIP"]
    _settled(qtbot, view, "document.querySelectorAll('.list-editor .chip').length === 1")
    assert _active(qtbot, view) == "cat-2-tag-input"


def test_the_write_off_rows_and_their_switch(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, tags())
    _click(qtbot, view, _key("cat-1-label"))
    _settled(qtbot, view, "document.querySelector('.list-row.open') !== null")
    assert _attr(qtbot, view, _key("cat-1-writeoff"), "aria-checked") == "true"
    assert _prop(qtbot, view, _key("cat-1-m0-sku"), "value") == "PKG-BOX-S"

    _click(qtbot, view, _key("cat-1-map-add"))
    _settled(qtbot, view, "document.querySelectorAll('.map-row').length === 2")
    assert _active(qtbot, view) == "cat-1-m1-sku"
    assert _text(qtbot, view, '[data-map="1"] .problem') == "Type the SKU to write off."
    _type(qtbot, view, _key("cat-1-m1-sku"), "TAPE")
    assert _edit(qtbot, view, seen, "map_sku") == ["1", "1", "TAPE"]
    _type(qtbot, view, _key("cat-1-m1-quantity"), "0,5")
    assert _edit(qtbot, view, seen, "map_quantity") == ["1", "1", "0,5"]

    _click(qtbot, view, _key("cat-1-m1-tag"))
    _settled(qtbot, view, "document.querySelector('.menu') !== null")
    _click(qtbot, view, '.menu [data-value="BAG"]')
    assert _edit(qtbot, view, seen, "map_tag") == ["1", "1", "BAG"]

    _click(qtbot, view, _key("cat-1-writeoff"))
    assert _edit(qtbot, view, seen, "writeoff") == ["1", False]
    _click(qtbot, view, _key("cat-1-m1-remove"))
    assert _edit(qtbot, view, seen, "map_remove") == ["1", "1"]


def test_add_category_selects_the_new_name_and_move_and_delete(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, tags())
    _click(qtbot, view, _key("cat-add"))
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 3")
    assert _active(qtbot, view) == "cat-3-label"
    assert _eval(qtbot, view, "document.activeElement.selectionEnd - document.activeElement.selectionStart") == len("New category")
    assert _prop(qtbot, view, _key("cat-3-map-add"), "disabled") is True
    assert _attr(qtbot, view, _key("cat-3-map-add"), "title") == "Add a tag first."
    _click(qtbot, view, _key("cat-3-up"))
    assert _edit(qtbot, view, seen, "cat_move") == ["3", "up"]
    _click(qtbot, view, _key("cat-3-delete"))
    assert _edit(qtbot, view, seen, "cat_delete") == ["3"]
    _settled(qtbot, view, "document.querySelectorAll('.list-row').length === 2")
    assert _active(qtbot, view) == "cat-add"


def test_with_no_category_the_page_is_the_empty_state(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, tags({"version": 2, "categories": {}}))
    assert _text(qtbot, view, ".state-title") == "No tag categories yet"
    assert _count(qtbot, view, ".page-head .btn") == 0


# --- the toast ----------------------------------------------------------------


def test_a_toast_shows_its_text_and_its_action_calls_the_bridge(qtbot, page):
    view, bridge = page
    actions = []
    bridge.toastActionRequested.connect(lambda: actions.append(True))
    _show(qtbot, view, bridge, sets())
    assert _prop(qtbot, view, "#toast", "hidden") is True

    bridge.raise_toast("Imported 2 sets from sets.csv")
    _settled(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "Imported 2 sets from sets.csv"
    assert _prop(qtbot, view, "#toast-action", "hidden") is True
    assert _style(qtbot, view, "#toast", "position") == "fixed"
    _click(qtbot, view, "#toast-dismiss")
    assert _prop(qtbot, view, "#toast", "hidden") is True

    bridge.raise_toast("Added 1. Skipped 2 already in the table.", True)
    _settled(qtbot, view, "document.getElementById('toast-action').hidden === false")
    assert _text(qtbot, view, "#toast-action") == "Update them"
    _click(qtbot, view, "#toast-action")
    qtbot.waitUntil(lambda: actions == [True], timeout=3000)
    assert _prop(qtbot, view, "#toast", "hidden") is True


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_list_pages_read_their_colours_from_the_theme(qtbot, page, theme):
    view, bridge = page
    manager = get_theme_manager()
    manager.set_theme(theme)
    tokens = manager.get_current_theme()
    _show(qtbot, view, bridge, tags())
    _until_js(
        qtbot,
        view,
        "getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() !== ''",
    )
    qtbot.waitUntil(
        lambda: _style(qtbot, view, ".list-count", "color") == _rgb(tokens.text_secondary),
        timeout=3000,
    )
    assert _style(qtbot, view, ".list-row", "borderTopColor") == _rgb(tokens.border_subtle)
