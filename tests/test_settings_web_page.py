"""The settings pages, driven through a real Chromium (phase 7 spec section 5).

The page is a renderer: every test pushes a view built by a draft and reads
the DOM back, or clicks and reads what the bridge was sent. 868x560 is the
page area a 1100x600 dialog gives. Never mark skip.
"""

import copy
import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.settings.bridge import PAGE, mount_settings_page
from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    ADDITIONAL_UNKNOWN,
    COURIER_EMPTY,
    DELIMITER_PROBLEM,
    THRESHOLD_PROBLEM,
    FileColumns,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.settings.web_host import SettingsWebHost
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
    "Lineitem name": "Product_Name",
}
COURIERS = {
    "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False},
    "DPD": {"patterns": ["dpd"], "case_sensitive": False},
}
FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Lineitem name",
        "Notes",
        "Discount Code",
    ),
    first_row={
        "Name": "#10482",
        "Lineitem sku": "ACM-TEE-BLK-M",
        "Lineitem quantity": "2",
        "Shipping Method": "DHL Express Worldwide",
        "Lineitem name": "Tee, black, M",
        "Notes": "leave at door",
    },
    loaded=True,
)


def _entry(name, enabled=True, order_level=True):
    return {
        "csv_name": name,
        "internal_name": name.replace(" ", "_"),
        "enabled": enabled,
        "is_order_level": order_level,
        "exists_in_df": True,
    }


def general(**stored):
    settings = {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }
    settings.update(stored)
    return GeneralDraft(settings, "ACME")


def orders(mapping=None, couriers=None, additional=None, file=FILE, fallback=None):
    live = {
        "version": 2,
        "orders": dict(ORDERS if mapping is None else mapping),
        "stock": {"Article": "SKU", "Available": "Stock"},
        "additional_columns": copy.deepcopy(additional or []),
    }
    if fallback is not None:
        del live["additional_columns"]
    return OrdersDraft(
        live, copy.deepcopy(COURIERS if couriers is None else couriers), "ACME", fallback, file
    )


def stock(file=None):
    live = {"version": 2, "orders": dict(ORDERS), "stock": {"Article": "SKU", "Available": "Stock"}}
    return StockDraft(live, "ACME", file)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 560)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _show(qtbot, view, bridge, draft):
    """Push a draft's view and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.set_state(draft.view())
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _wired(qtbot, view, bridge, draft):
    """Show `draft` and answer the page's edits the way the host does."""
    seen = []

    def on_edit(action, args):
        seen.append((action, args))
        if draft.apply(action, args):
            bridge.set_state(draft.view())

    bridge.editRequested.connect(on_edit)
    _show(qtbot, view, bridge, draft)
    return seen


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _texts(qtbot, view, selector):
    return json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll("
            f"{selector!r})).map((el) => el.textContent.trim()))",
        )
    )


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _attr(qtbot, view, selector, name):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).getAttribute({name!r})"
    )


def _prop(qtbot, view, selector, name):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).{name}")


def _type(qtbot, view, selector, text):
    """Type into a field as keystrokes do: focus it, set the text, fire input."""
    _eval(
        qtbot,
        view,
        "(function () {"
        f" const el = document.querySelector({selector!r});"
        " el.focus();"
        f" el.value = {json.dumps(text)};"
        " el.dispatchEvent(new Event('input', { bubbles: true }));"
        " return true; })()",
    )


def _keydown(qtbot, view, key, selector=None):
    target = f"document.querySelector({selector!r})" if selector else "document"
    _eval(
        qtbot,
        view,
        f"{target}.dispatchEvent(new KeyboardEvent('keydown', "
        f"{{key: {key!r}, bubbles: true, cancelable: true}})); true",
    )


def _active(qtbot, view):
    return _eval(qtbot, view, "document.activeElement.dataset.key || ''")


def _key(name):
    return f'[data-key="{name}"]'


# --- the files ---------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="../../shared/web/kit.css"') < html.index('href="settings.css"')


# --- frame -------------------------------------------------------------------


def test_the_head_has_the_title_and_the_subtitle_and_no_action_on_general(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    assert _text(qtbot, view, ".page-title") == "General"
    assert _text(qtbot, view, ".page-sub") == (
        "How ACME's files are read, and when stock counts as low."
    )
    assert _count(qtbot, view, _key("read-columns")) == 0


def test_the_page_is_a_centred_column_on_the_sunken_plane(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, "body", "backgroundColor") == _rgb(theme.surface_sunken)
    assert _style(qtbot, view, ".settings-page", "maxWidth") == "860px"
    assert _style(qtbot, view, ".settings-page .card", "backgroundColor") == _rgb(
        theme.surface
    )


def test_a_mapping_page_offers_read_columns(qtbot, page):
    view, bridge = page
    seen = []
    bridge.readColumnsRequested.connect(lambda: seen.append(True))
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, _key("read-columns")) == "Read columns from CSV…"
    _click(qtbot, view, _key("read-columns"))
    qtbot.waitUntil(lambda: seen == [True])


# --- General -----------------------------------------------------------------


def test_general_draws_two_cards_with_their_rows(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    assert _texts(qtbot, view, ".card-title") == ["CSV files", "Stock alerts"]
    assert _texts(qtbot, view, ".card-label") == [
        "Stock CSV delimiter",
        "Orders CSV delimiter",
        "Low-stock threshold",
    ]
    assert _texts(qtbot, view, '[data-row="delimiter-stock"] .segment') == [
        "Auto",
        "Comma",
        "Semicolon",
        "Tab",
        "Other",
    ]
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .hint') == (
        "Detected for each file as it is read."
    )
    assert _prop(qtbot, view, _key("threshold"), "value") == "5"
    assert _text(qtbot, view, '[data-row="threshold"] .control-line span') == "units"


def test_the_stored_delimiter_is_the_checked_segment(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general(orders_csv_delimiter=";"))
    assert _attr(qtbot, view, _key("segment-orders-semicolon"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("segment-orders-auto"), "aria-checked") == "false"
    assert _attr(qtbot, view, _key("segment-stock-auto"), "aria-checked") == "true"


def test_clicking_a_segment_reports_the_delimiter(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    _click(qtbot, view, _key("segment-orders-semicolon"))
    qtbot.waitUntil(lambda: seen == [("delimiter", ["orders", "semicolon"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"segment-orders-semicolon\"]')"
        ".getAttribute('aria-checked') === 'true'",
    )
    assert _text(qtbot, view, '[data-row="delimiter-orders"] .hint') == (
        "Every file is split on semicolons."
    )


def test_other_shows_a_one_character_field_and_says_when_it_is_empty(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    assert _count(qtbot, view, _key("char-stock")) == 0
    _click(qtbot, view, _key("segment-stock-other"))
    _until_js(qtbot, view, "!!document.querySelector('[data-key=\"char-stock\"]')")
    assert _attr(qtbot, view, _key("char-stock"), "maxlength") == "1"
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .problem') == DELIMITER_PROBLEM
    assert "invalid" in _attr(qtbot, view, _key("char-stock"), "class")

    _type(qtbot, view, _key("char-stock"), "|")
    qtbot.waitUntil(lambda: seen[-1] == ("delimiter_char", ["stock", "|"]))
    _until_js(
        qtbot,
        view,
        "!document.querySelector('[data-row=\"delimiter-stock\"] .problem')",
    )
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .hint') == (
        "Every file is split on “|”."
    )


def test_typing_a_threshold_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    _type(qtbot, view, _key("threshold"), "12")
    qtbot.waitUntil(lambda: seen == [("threshold", ["12"])])
    assert _active(qtbot, view) == "threshold"
    assert _prop(qtbot, view, _key("threshold"), "value") == "12"


def test_a_bad_threshold_marks_the_field_and_says_why(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, general())
    _type(qtbot, view, _key("threshold"), "1x")
    _until_js(qtbot, view, "!!document.querySelector('[data-row=\"threshold\"] .problem')")
    assert _text(qtbot, view, '[data-row="threshold"] .problem') == THRESHOLD_PROBLEM
    assert "invalid" in _attr(qtbot, view, _key("threshold"), "class")
    assert _count(qtbot, view, '[data-row="threshold"] .hint') == 0
    # The field being typed in keeps what the operator sees.
    assert _prop(qtbot, view, _key("threshold"), "value") == "1x"
    assert _active(qtbot, view) == "threshold"


def test_left_and_right_move_between_segments(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    _eval(qtbot, view, "document.querySelector('[data-key=\"segment-stock-auto\"]').focus(); true")
    _keydown(qtbot, view, "ArrowRight", _key("segment-stock-auto"))
    assert _active(qtbot, view) == "segment-stock-comma"
    _keydown(qtbot, view, "ArrowLeft", _key("segment-stock-comma"))
    _keydown(qtbot, view, "ArrowLeft", _key("segment-stock-auto"))
    assert _active(qtbot, view) == "segment-stock-other"


# --- the Fields card ---------------------------------------------------------


def test_the_fields_card_says_where_its_columns_came_from(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, '[data-card="fields"] .card-text') == (
        "Columns read from orders-30-09.csv, the file loaded on Setup."
    )
    assert _text(qtbot, view, '[data-card="fields"] .card-text .mono') == "orders-30-09.csv"
    assert _texts(qtbot, view, ".field-heads span") == ["Field", "", "CSV column", "First row"]


def test_a_field_row_shows_its_label_its_column_and_the_first_rows_value(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _count(qtbot, view, ".field-row[data-field]") == 12
    assert _count(qtbot, view, ".field-required") == 4
    row = '[data-field="Order_Number"]'
    assert _text(qtbot, view, f"{row} .field-label") == "Order number"
    assert _text(qtbot, view, f"{row} .select-value") == "Name"
    assert "mono" in _attr(qtbot, view, f"{row} .select-value", "class")
    assert _text(qtbot, view, f"{row} .field-sample") == "#10482"
    assert _text(qtbot, view, '[data-field="Tags"] .select-value') == "Not imported"


def test_with_no_file_the_menus_are_disabled_and_the_card_says_so(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(file=None))
    assert _text(qtbot, view, '[data-card="fields"] .card-text') == (
        "No CSV has been read. Use Read columns from CSV… to change a field."
    )
    assert _prop(qtbot, view, _key("field-Order_Number"), "disabled") is True
    _click(qtbot, view, _key("field-Order_Number"))
    assert _count(qtbot, view, ".menu") == 0


def test_a_field_menu_lists_the_files_columns_and_who_holds_them(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    assert _texts(qtbot, view, ".field-menu .menu-label") == [
        "Not imported",
        *FILE.columns,
    ]
    assert _attr(qtbot, view, _key("field-Tags-item-none"), "aria-checked") == "true"
    assert _text(qtbot, view, f"{_key('field-Tags-item-0')} .menu-hint") == "Order number"
    assert _count(qtbot, view, f"{_key('field-Tags-item-5')} .menu-hint") == 0
    assert _attr(qtbot, view, _key("field-Tags"), "aria-expanded") == "true"


def test_a_required_fields_menu_has_no_not_imported_and_no_note_on_its_own_column(
    qtbot, page
):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-SKU"))
    assert _texts(qtbot, view, ".field-menu .menu-label") == list(FILE.columns)
    assert _attr(qtbot, view, _key("field-SKU-item-1"), "aria-checked") == "true"
    assert _count(qtbot, view, f"{_key('field-SKU-item-1')} .menu-hint") == 0


def test_picking_a_column_reports_it_closes_the_menu_and_keeps_focus(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, _key("field-Tags-item-5"))
    qtbot.waitUntil(lambda: seen == [("column", ["Tags", "Notes"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-field=\"Tags\"] .select-value')"
        ".textContent === 'Notes'",
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "field-Tags"
    assert _text(qtbot, view, '[data-field="Tags"] .field-sample') == "leave at door"


def test_a_required_field_with_no_column_is_marked_and_says_what_to_do(qtbot, page):
    view, bridge = page
    mapping = {k: v for k, v in ORDERS.items() if v != "Shipping_Method"}
    _show(qtbot, view, bridge, orders(mapping=mapping))
    row = '[data-field="Shipping_Method"]'
    assert "invalid" in _attr(qtbot, view, f"{row} .select", "class")
    assert _text(qtbot, view, f"{row} .select-value") == "Choose column"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{row} .select-value", "color") == _rgb(theme.status_danger)
    assert _text(qtbot, view, f"{row} .problem") == (
        "Shipping method is required. Choose the column that holds it, "
        "e.g. Shipping Method."
    )
    assert _text(qtbot, view, f"{row} .problem .mono") == "Shipping Method"


def test_a_saved_column_the_file_lacks_is_kept_and_listed_first(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(mapping={**ORDERS, "Old Notes": "Notes"}))
    row = '[data-field="Notes"]'
    assert _text(qtbot, view, f"{row} .select-value") == "Old Notes"
    assert _text(qtbot, view, f"{row} .field-sample") == "Not in this file"
    _click(qtbot, view, _key("field-Notes"))
    assert _texts(qtbot, view, ".field-menu .menu-label")[:2] == ["Not imported", "Old Notes"]
    assert _text(qtbot, view, f"{_key('field-Notes-item-0')} .menu-hint") == "Not in this file"
    assert _attr(qtbot, view, _key("field-Notes-item-0"), "aria-checked") == "true"


def test_the_stock_page_has_only_the_fields_card_and_its_hints(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, stock())
    assert _texts(qtbot, view, ".card-title") == ["Fields"]
    assert _count(qtbot, view, ".field-row[data-field]") == 5
    assert _text(qtbot, view, '[data-field="Batch"] .hint').startswith("Lot or batch number.")


# --- menus -------------------------------------------------------------------


def test_escape_and_an_outside_click_close_the_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    assert _count(qtbot, view, ".menu") == 1
    _keydown(qtbot, view, "Escape")
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "field-Tags"

    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, ".page-title")
    assert _count(qtbot, view, ".menu") == 0


def test_escape_with_no_menu_open_is_left_for_the_dialog(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    prevented = _eval(
        qtbot,
        view,
        "(function () { const e = new KeyboardEvent('keydown', "
        "{key: 'Escape', bubbles: true, cancelable: true});"
        " document.dispatchEvent(e); return e.defaultPrevented; })()",
    )
    assert prevented is False


def test_only_one_menu_is_open_at_a_time(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, _key("field-Notes"))
    assert _count(qtbot, view, ".menu") == 1
    assert _count(qtbot, view, '[data-field="Notes"] .menu') == 1


def test_arrow_keys_walk_the_open_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-SKU"))
    _keydown(qtbot, view, "ArrowDown")
    assert _active(qtbot, view) == "field-SKU-item-0"
    _keydown(qtbot, view, "ArrowDown")
    assert _active(qtbot, view) == "field-SKU-item-1"
    _keydown(qtbot, view, "ArrowUp")
    _keydown(qtbot, view, "ArrowUp")
    assert _active(qtbot, view) == "field-SKU-item-6"


def test_changing_page_closes_the_menu_and_returns_to_the_top(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _eval(qtbot, view, "document.getElementById('settings').scrollTop = 200; true")
    _show(qtbot, view, bridge, general())
    assert _count(qtbot, view, ".menu") == 0
    assert _eval(qtbot, view, "document.getElementById('settings').scrollTop") == 0
    assert _attr(qtbot, view, ".settings-page", "data-page") == "general"


def test_a_menu_closes_when_the_state_takes_its_opener_away(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _show(qtbot, view, bridge, orders(file=None))
    assert _count(qtbot, view, ".menu") == 0


# --- Courier names -----------------------------------------------------------


def test_courier_rows_show_the_text_and_the_courier(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, '[data-card="couriers"] .card-title') == "Courier names"
    assert _texts(qtbot, view, ".courier-heads span") == [
        "Shipping method contains",
        "",
        "Courier",
        "",
    ]
    assert _count(qtbot, view, ".courier-row[data-courier]") == 3
    assert _prop(qtbot, view, _key("courier-text-1"), "value") == "DHL Express"
    assert _text(qtbot, view, _key("courier-code-2")) == "DPD"


def test_no_courier_rows_shows_the_empty_sentence(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(couriers={}))
    assert _text(qtbot, view, '[data-card="couriers"] .card-empty') == COURIER_EMPTY
    assert _count(qtbot, view, ".courier-heads") == 0


def test_typing_a_courier_text_reports_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _type(qtbot, view, _key("courier-text-2"), "dpd classic")
    qtbot.waitUntil(lambda: seen == [("courier_pattern", ["2", "dpd classic"])])
    assert _active(qtbot, view) == "courier-text-2"


def test_add_name_adds_a_row_and_puts_the_caret_in_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-add"))
    qtbot.waitUntil(lambda: seen == [("courier_add", [])])
    _until_js(qtbot, view, "document.querySelectorAll('.courier-row[data-courier]').length === 4")
    _until_js(qtbot, view, "document.activeElement.dataset.key === 'courier-text-3'")
    assert _text(qtbot, view, _key("courier-code-3")) == "Choose courier"


def test_the_courier_menu_lists_the_couriers_in_use_and_takes_a_new_one(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-code-2"))
    assert _texts(qtbot, view, ".courier-menu .menu-label") == ["DHL", "DPD"]
    assert _attr(qtbot, view, _key("courier-code-2-item-1"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("courier-new-2"), "placeholder") == "New courier"

    _click(qtbot, view, _key("courier-code-2-item-0"))
    qtbot.waitUntil(lambda: seen == [("courier_code", ["2", "DHL"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-code-2\"]').textContent.trim() === 'DHL'",
    )
    assert _count(qtbot, view, ".menu") == 0

    _click(qtbot, view, _key("courier-code-0"))
    _eval(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-new-0\"]').value = 'Evri'; true",
    )
    _keydown(qtbot, view, "Enter", _key("courier-new-0"))
    qtbot.waitUntil(lambda: seen[-1] == ("courier_code", ["0", "Evri"]))
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-code-0\"]').textContent.trim() === 'Evri'",
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "courier-code-0"


def test_removing_a_courier_row_reports_its_index(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-remove-0"))
    qtbot.waitUntil(lambda: seen == [("courier_remove", ["0"])])
    _until_js(qtbot, view, "document.querySelectorAll('.courier-row[data-courier]').length === 2")
    assert _prop(qtbot, view, _key("courier-text-0"), "value") == "DHL Express"


# --- Additional columns ------------------------------------------------------


def test_kept_columns_are_chips_with_their_notes(qtbot, page):
    view, bridge = page
    additional = [_entry("Notes"), _entry("Gift Note", order_level=False)]
    _show(qtbot, view, bridge, orders(additional=additional))
    assert _texts(qtbot, view, ".chip-name") == ["Notes", "Gift Note"]
    assert _texts(qtbot, view, ".chip-note") == ["Not in this file, not filled down"]
    assert _count(qtbot, view, ".chips-empty") == 0


def test_no_kept_columns_says_none_kept(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, ".chips-empty") == "None kept."


def test_add_column_lists_the_candidates_and_keeping_one_makes_a_chip(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("column-add"))
    assert _text(qtbot, view, ".add-menu .menu-group") == (
        "Unmapped columns in orders-30-09.csv"
    )
    assert _texts(qtbot, view, ".add-menu .menu-label") == ["Discount Code", "Notes"]
    _click(qtbot, view, _key("column-add-item-1"))
    qtbot.waitUntil(lambda: seen == [("column_add", ["Notes"])])
    _until_js(qtbot, view, "document.querySelectorAll('.chip-name').length === 1")
    assert _texts(qtbot, view, ".chip-name") == ["Notes"]
    assert _count(qtbot, view, ".menu") == 0


def test_add_column_is_disabled_and_says_why_when_there_is_nothing_to_add(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(file=None))
    assert _prop(qtbot, view, _key("column-add"), "disabled") is True
    assert _attr(qtbot, view, _key("column-add"), "title") == (
        "Use Read columns from CSV… to list the file's unmapped columns."
    )


def test_removing_a_chip_reports_its_column(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry("Notes")]))
    _click(qtbot, view, ".chip-remove")
    qtbot.waitUntil(lambda: seen == [("column_remove", ["Notes"])])
    _until_js(qtbot, view, "document.querySelectorAll('.chip-name').length === 0")


def test_a_chips_menu_toggles_fill_down(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry("Notes")]))
    _click(qtbot, view, ".chip-name")
    item = '[data-chip="Notes"] .menu-item'
    assert _text(qtbot, view, item) == "Fill down onto every line of the order"
    assert _attr(qtbot, view, item, "aria-checked") == "true"
    _click(qtbot, view, item)
    qtbot.waitUntil(lambda: seen == [("column_fill", ["Notes", False])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-chip=\"Notes\"] .menu-item')"
        ".getAttribute('aria-checked') === 'false'",
    )
    assert _texts(qtbot, view, ".chip-note") == ["not filled down"]


def test_a_column_name_with_quotes_in_it_still_works(qtbot, page):
    """A key can hold a column's name, and a column's name can hold anything."""
    view, bridge = page
    name = 'Gift "note" <b>'
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry(name)]))
    assert _texts(qtbot, view, ".chip-name") == [name]
    _click(qtbot, view, ".chip-name")
    assert _count(qtbot, view, ".chip-anchor .menu") == 1
    _keydown(qtbot, view, "Escape")
    assert _eval(qtbot, view, "document.activeElement.className") == "chip-name mono"
    _click(qtbot, view, ".chip-remove")
    qtbot.waitUntil(lambda: seen == [("column_remove", [name])])


def test_a_column_name_with_a_carriage_return_comes_back_as_it_was_sent(qtbot, page):
    """A quoted header can span lines. The parser turns a bare carriage return
    into a line feed, and Python would not know the name that came back."""
    view, bridge = page
    name = "Gift\r\nNote"
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry(name)]))
    _click(qtbot, view, ".chip-remove")
    qtbot.waitUntil(lambda: seen == [("column_remove", [name])])


def test_an_unreadable_list_shows_the_notice(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(fallback=ADDITIONAL_COLUMNS_UNREADABLE))
    assert _text(qtbot, view, ".card-notice") == ADDITIONAL_UNKNOWN


# --- the footer's link -------------------------------------------------------


def test_a_problem_focus_request_focuses_that_control(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general(low_stock_threshold="x"))
    bridge.problemFocusRequested.emit("threshold")
    _until_js(qtbot, view, "document.activeElement.dataset.key === 'threshold'")


def test_the_link_reaches_a_control_on_a_page_that_is_not_showing(qtbot):
    """Through the host, in the window's order: the page, then the request.
    The request gets to Chromium first, before the state that draws the
    control."""
    host = SettingsWebHost(
        {"general": general(low_stock_threshold="x"), "stock": stock()}
    )
    qtbot.addWidget(host)
    host.resize(868, 560)
    host.show()
    view = host.view
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    host.show_page("stock")
    _until_js(
        qtbot, view, "document.querySelector('.settings-page').dataset.page === 'stock'"
    )

    host.show_page("general")
    host.focus_problem("threshold")

    _until_js(qtbot, view, "document.activeElement.dataset.key === 'threshold'")


def test_every_blocker_key_names_a_control_the_page_draws(qtbot, page):
    """The keys are spelled in page_state.py and again in settings.js: a
    rename on one side would leave the footer's link pointing at nothing."""
    view, bridge = page
    other = general()
    other.apply("delimiter", ["orders", "other"])
    unmapped = dict(ORDERS)
    del unmapped["Shipping Method"]
    no_quantity = StockDraft(
        {"version": 2, "orders": {}, "stock": {"Article": "SKU"}}, "ACME"
    )
    drafts = (general(low_stock_threshold="x"), other, orders(unmapped), no_quantity)
    for draft in drafts:
        key = draft.blocker_key()
        assert key
        _show(qtbot, view, bridge, draft)
        assert _eval(
            qtbot,
            view,
            "Array.from(document.querySelectorAll('[data-key]'))"
            f".some((el) => el.dataset.key === {json.dumps(key)})",
        ), key


# --- theme -------------------------------------------------------------------


def test_the_page_follows_a_theme_change_without_a_reload(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    manager = get_theme_manager()
    start = manager.get_current_theme().name
    other = "dark" if start == "light" else "light"
    try:
        manager.set_theme(other)
        surface = _rgb(manager.get_current_theme().surface)
        _until_js(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('.card')).backgroundColor"
            f" === {surface!r}",
        )
        assert _text(qtbot, view, ".page-title") == "General"
    finally:
        manager.set_theme(start)
