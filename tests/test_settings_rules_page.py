"""The Rules page and the Test rule panel, driven through a real Chromium
(phase 8 spec sections 5 and 6).

The page is a renderer: every test pushes a view built by RulesDraft and
reads the DOM back, or clicks and reads what the bridge was sent. 868x700 is
the page area a small dialog gives. Never mark skip.
"""

import json

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
)

from gui.settings.bridge import PAGE, mount_settings_page
from gui.settings.rule_test import failed_view, run_rule_test, running_view
from gui.settings.rules_state import (
    CLEAR_FILTER,
    HOLD_HINT,
    RETIRED_ONE,
    TEST_NO_ANALYSIS,
    RulesDraft,
)
from gui.theme_manager import get_theme_manager

TAGS = {
    "version": 2,
    "categories": {"h": {"label": "H", "color": "#FF0000", "tags": ["priority", "heavy"], "order": 1}},
}


def cond(field="SKU", operator="equals", value="A"):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(name, level="article", conditions=None, actions=None, match="ALL", **extra):
    return {
        "name": name,
        "level": level,
        **extra,
        "steps": [
            {
                "conditions": [cond()] if conditions is None else conditions,
                "match": match,
                "actions": [tag()] if actions is None else actions,
            }
        ],
    }


def frame():
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3"],
            "SKU": ["A", "B", "B", "A"],
            "Quantity": [4, 3, 1, 1],
            "Tags": ["VIP, repeat", "", "", "VIP"],
            "Order_Fulfillment_Status": ["Fulfillable"] * 4,
            "Internal_Tags": ["[]"] * 4,
            "Status_Note": [""] * 4,
        }
    )


def rules():
    """Three article rules and one order rule: uids 1 to 4, in that order."""
    return [
        rule("VIP priority", conditions=[cond("Tags", "contains", "VIP")], actions=[tag("priority")]),
        rule("Second"),
        rule("Third", enabled=False),
        rule("Heavy parcels", "order", conditions=[cond("total_quantity", "is greater than", "5")]),
    ]


def draft(given=None, analysis=True):
    return RulesDraft(rules() if given is None else given, frame() if analysis else None, TAGS)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _wired(qtbot, view, bridge, d):
    """Show `d` and answer the page's edits the way the host does."""
    seen = []

    def on_edit(action, args):
        seen.append((action, args))
        if d.apply(action, args):
            bridge.set_state(d.view())

    bridge.editRequested.connect(on_edit)
    _show(qtbot, view, bridge, d)
    return seen


def _sent(qtbot, seen, action, args):
    qtbot.waitUntil(lambda: (action, args) in seen, timeout=5000)


def _there(qtbot, view, selector):
    _until_js(qtbot, view, f"document.querySelector({selector!r}) !== null")


def _gone(qtbot, view, selector):
    _until_js(qtbot, view, f"document.querySelector({selector!r}) === null")


def _focused(qtbot, view, key):
    _until_js(qtbot, view, f"(document.activeElement.dataset.key || '') === {key!r}")


def _open(qtbot, view, uid):
    _click(qtbot, view, _key(f"rule-{uid}-name"))
    _there(qtbot, view, f'.rule.open[data-rule="{uid}"] .rule-editor')


def _pointer(qtbot, view, kind, target, y):
    _eval(
        qtbot,
        view,
        f"{target}.dispatchEvent(new PointerEvent({kind!r}, {{bubbles: true, cancelable: true,"
        f" button: 0, pointerId: 7, clientX: 30, clientY: {y}}})); true",
    )


def _row_edge(qtbot, view, uid, edge):
    return _eval(
        qtbot, view, f"document.querySelector('.rule[data-rule=\"{uid}\"]').getBoundingClientRect().{edge}"
    )


# --- the files ---------------------------------------------------------------


def test_the_rules_script_loads_before_the_page_script():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('src="settings_rules.js"') < html.index('src="settings.js"')


# --- the head and the empty state ----------------------------------------------


def test_the_head_offers_add_rule(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _text(qtbot, view, ".page-title") == "Rules"
    assert _text(qtbot, view, ".page-sub") == (
        "Change orders at the end of each analysis. Rules run top to bottom."
    )
    assert _text(qtbot, view, _key("rule-add")) == "Add rule"

    _click(qtbot, view, _key("rule-add"))
    _sent(qtbot, seen, "rule_add", [])
    _there(qtbot, view, ".rule.open .rule-name-field")
    _focused(qtbot, view, "rule-5-name")
    assert _prop(qtbot, view, ".rule.open .rule-name-field", "value") == "New rule"
    # Selected, so typing replaces the placeholder name.
    assert _eval(qtbot, view, "document.activeElement.selectionEnd") == len("New rule")
    assert _eval(qtbot, view, "document.activeElement.selectionStart") == 0


def test_no_rules_shows_the_empty_state_and_its_own_button(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft([]))
    assert _count(qtbot, view, ".page-head [data-act]") == 0
    assert _count(qtbot, view, ".rules-card") == 0
    assert _text(qtbot, view, ".rules-empty .state-title") == "No rules yet"
    assert _text(qtbot, view, ".rules-empty .state-text") == (
        "Rules change orders at the end of each analysis, e.g. tag VIP orders."
    )
    assert _count(qtbot, view, ".rules-empty-tile svg") == 1
    assert _text(qtbot, view, ".rules-empty .btn.primary") == "Add rule"

    _click(qtbot, view, ".rules-empty .btn.primary")
    _sent(qtbot, seen, "rule_add", [])
    _there(qtbot, view, ".rules-card .rule.open")


# --- the list --------------------------------------------------------------------


def test_a_row_is_the_mockups_grid(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    columns = _style(qtbot, view, ".rule", "gridTemplateColumns").split()
    assert columns[:2] == ["20px", "32px"] and len(columns) == 4
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".rule", "borderTopColor") == _rgb(theme.border_subtle)
    assert _texts(qtbot, view, ".rule-num") == ["01", "02", "03", "04"]
    assert _texts(qtbot, view, ".rule-name") == ["VIP priority", "Second", "Third", "Heavy parcels"]
    assert _text(qtbot, view, ".rules-count") == "4 rules · 3 on"


def test_a_summary_reads_when_and_then_with_its_values_as_chips(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    first = '.rule[data-rule="1"]'
    assert _texts(qtbot, view, f"{first} .rule-line-label") == ["When", "Then"]
    assert _texts(qtbot, view, f"{first} .rule-line:nth-of-type(2) > :not(.rule-line-label)") == [
        "Tags",
        "contains",
        "VIP",
    ]
    assert _texts(qtbot, view, f"{first} .rule-chip") == ["VIP", "priority"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{first} .rule-chip", "backgroundColor") == _rgb(theme.surface_raised)
    assert _style(qtbot, view, f"{first} .rule-word.bold", "fontWeight") == "700"
    assert _style(qtbot, view, f"{first} .rule-line-label", "width") == "36px"


def test_a_rule_with_steps_has_wider_labels(qtbot, page):
    view, bridge = page
    stepped = rule("Stepped")
    stepped["steps"].append({"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": []})
    _show(qtbot, view, bridge, draft([stepped]))
    assert _texts(qtbot, view, ".rule-line-label") == ["When", "Then", "And when", "Then"]
    assert _style(qtbot, view, ".rule-line-label", "width") == "60px"
    assert _texts(qtbot, view, ".rule-word.muted") == ["No action yet."]


def test_the_two_levels_are_labelled_groups(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    assert _texts(qtbot, view, ".rules-group-label") == ["Article rules", "Order rules"]
    assert _texts(qtbot, view, ".rules-group") == [
        "Article rulesCheck one order line at a time.",
        "Order rulesCheck the whole order. Run after every article rule.",
    ]
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('.rule')).map((r) => r.dataset.group))",
        )
    ) == ["article", "article", "article", "order"]


def test_a_very_long_value_is_cut_and_never_widens_the_page(qtbot, page):
    view, bridge = page
    skus = ", ".join(f"SKU-{n:04d}" for n in range(60))
    _wired(qtbot, view, bridge, draft([rule("long", conditions=[cond("SKU", "in list", skus)])]))
    fits = (
        "(() => { const s = document.getElementById('settings');"
        " return s.scrollWidth <= s.clientWidth; })()"
    )
    assert _attr(qtbot, view, ".rule-chip", "title") == skus
    assert _eval(
        qtbot,
        view,
        "(() => { const c = document.querySelector('.rule-chip');"
        " return c.scrollWidth > c.clientWidth; })()",
    ) is True
    assert _eval(qtbot, view, fits) is True
    _open(qtbot, view, "1")
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == skus
    assert _eval(qtbot, view, fits) is True


def test_markup_in_a_name_or_a_value_is_drawn_as_text(qtbot, page):
    view, bridge = page
    name = '<b>"VIP" & co</b>'
    value = '<i>"x"</i>'
    given = rule(name, conditions=[cond("SKU", "equals", value)], actions=[tag('say "hi"')])
    seen = _wired(qtbot, view, bridge, draft([given]))
    assert _text(qtbot, view, ".rule-name") == name
    assert _count(qtbot, view, ".rule b, .rule i") == 0
    assert _texts(qtbot, view, ".rule-chip") == [value, 'say "hi"']
    assert _attr(qtbot, view, ".switch", "aria-label") == name

    _open(qtbot, view, "1")
    assert _prop(qtbot, view, _key("rule-1-name"), "value") == name
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == value
    assert _prop(qtbot, view, _key("rule-1-s0-a0-value"), "value") == 'say "hi"'
    _type(qtbot, view, _key("rule-1-name"), name + "!")
    _sent(qtbot, seen, "rule_name", ["1", name + "!"])


def test_one_level_has_no_group_label(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft([rule("a"), rule("b")]))
    assert _count(qtbot, view, ".rules-group") == 0


def test_a_rule_that_is_off_reads_quieter_and_says_off(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    theme = get_theme_manager().get_current_theme()
    off = '.rule[data-rule="3"]'
    assert _text(qtbot, view, f"{off} .badge") == "Off"
    assert _attr(qtbot, view, f"{off} .switch", "aria-checked") == "false"
    assert _attr(qtbot, view, f"{off} .switch", "title") == "Turn on"
    assert _style(qtbot, view, f"{off} .rule-name", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, f"{off} .rule-line", "color") == _rgb(theme.text_secondary)
    on = '.rule[data-rule="1"]'
    assert _count(qtbot, view, f"{on} .badge") == 0
    assert _style(qtbot, view, f"{on} .rule-name", "color") == _rgb(theme.text)


def test_the_switch_turns_a_rule_off_and_on(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-switch"))
    _sent(qtbot, seen, "rule_enabled", ["1", False])
    _there(qtbot, view, '.rule.off[data-rule="1"]')
    assert _text(qtbot, view, ".rules-count") == "4 rules · 2 on"
    _click(qtbot, view, _key("rule-1-switch"))
    _sent(qtbot, seen, "rule_enabled", ["1", True])


def test_a_rule_with_no_name_is_still_a_row_to_click(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft([rule("")]))
    assert _text(qtbot, view, ".rule-name") == "Unnamed rule"
    assert _attr(qtbot, view, ".switch", "aria-label") == "Unnamed rule"


def test_the_filter_narrows_the_list_and_stops_reordering(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _attr(qtbot, view, _key("rules-filter"), "placeholder") == "Filter by name"
    _type(qtbot, view, _key("rules-filter"), "sec")
    _sent(qtbot, seen, "filter", ["sec"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule').length === 1")
    assert _texts(qtbot, view, ".rule-num") == ["02"]
    assert _active(qtbot, view) == "rules-filter"
    assert _prop(qtbot, view, _key("rules-filter"), "value") == "sec"
    assert _prop(qtbot, view, _key("rule-2-up"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-2-up"), "title") == CLEAR_FILTER
    assert _attr(qtbot, view, ".rule-grip", "title") == CLEAR_FILTER

    _type(qtbot, view, _key("rules-filter"), "zzz")
    _there(qtbot, view, ".rules-none")
    assert _text(qtbot, view, ".rules-none") == "No rules named “zzz”."


def test_up_and_down_move_a_rule_inside_its_group_and_keep_the_focus_on_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _prop(qtbot, view, _key("rule-1-up"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-3-down"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-4-up"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-4-down"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-2-up"), "title") == "Move up"
    assert _attr(qtbot, view, _key("rule-2-down"), "title") == "Move down"

    _eval(qtbot, view, f"document.querySelector({_key('rule-2-down')!r}).focus(); true")
    _click(qtbot, view, _key("rule-2-down"))
    _sent(qtbot, seen, "rule_move", ["2", "down"])
    _until_js(
        qtbot, view, "document.querySelectorAll('.rule')[2].dataset.rule === '2'"
    )
    # It reached the group's end: Down is disabled, so Up takes the focus.
    _focused(qtbot, view, "rule-2-up")


def test_a_move_button_at_the_edge_only_greys(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    theme = get_theme_manager().get_current_theme()
    edge = _key("rule-1-up")
    assert _style(qtbot, view, edge, "color") == _rgb(theme.text_disabled)
    assert _style(qtbot, view, edge, "borderTopColor") == "rgba(0, 0, 0, 0)"
    assert _style(qtbot, view, edge, "backgroundColor") == "rgba(0, 0, 0, 0)"
    assert _style(qtbot, view, _key("rule-2-up"), "color") == _rgb(theme.text_secondary)


def test_the_more_menu_edits_duplicates_and_deletes(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    more = _key("rule-2-menu")
    assert _attr(qtbot, view, more, "title") == "Edit, duplicate, delete"
    _click(qtbot, view, more)
    assert _attr(qtbot, view, more, "aria-expanded") == "true"
    assert _texts(qtbot, view, ".rule-menu .menu-item") == ["Edit", "Duplicate", "Delete"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _key("rule-2-menu-delete"), "color") == _rgb(theme.status_danger)

    _click(qtbot, view, _key("rule-2-menu-duplicate"))
    _sent(qtbot, seen, "rule_duplicate", ["2"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule').length === 5")
    assert _count(qtbot, view, ".rule-menu") == 0
    assert _texts(qtbot, view, ".rule-name")[1:3] == ["Second", "Second copy"]

    _click(qtbot, view, more)
    _click(qtbot, view, _key("rule-2-menu-delete"))
    _sent(qtbot, seen, "rule_delete", ["2"])
    _gone(qtbot, view, '.rule[data-rule="2"]')
    _focused(qtbot, view, "rules-filter")

    _click(qtbot, view, _key("rule-1-menu"))
    _click(qtbot, view, _key("rule-1-menu-edit"))
    _sent(qtbot, seen, "open", ["1"])
    _there(qtbot, view, '.rule.open[data-rule="1"]')
    assert _count(qtbot, view, ".rule-menu") == 0
    _click(qtbot, view, _key("rule-1-menu"))
    assert _texts(qtbot, view, ".rule-menu .menu-item")[0] == "Close editor"
    _click(qtbot, view, _key("rule-1-menu-edit"))
    _sent(qtbot, seen, "close", [])
    _gone(qtbot, view, ".rule.open")


def test_escape_closes_the_more_menu_and_returns_focus(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-menu"))
    _there(qtbot, view, ".rule-menu")
    _keydown(qtbot, view, "Escape")
    _gone(qtbot, view, ".rule-menu")
    assert _active(qtbot, view) == "rule-1-menu"


# --- reordering by the grip --------------------------------------------------------


def test_dragging_a_grip_shows_where_the_rule_lands_and_moves_it_there(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    grip = "document.querySelector('[data-grip=\"1\"]')"
    assert _attr(qtbot, view, '[data-grip="1"]', "title") == "Drag to reorder"

    _pointer(qtbot, view, "pointerdown", grip, _row_edge(qtbot, view, "1", "top") + 5)
    assert _count(qtbot, view, '.rule.dragging[data-rule="1"]') == 1
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".rule.dragging", "backgroundColor") == _rgb(theme.selection_bg)

    # Just under the second rule's middle: it lands between the second and third.
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "2", "bottom") - 3)
    assert _count(qtbot, view, '.rule.drop-before[data-rule="3"]') == 1
    # Under the group's last rule: it lands at the end, never among the order rules.
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "4", "bottom") - 3)
    assert _count(qtbot, view, '.rule.drop-after[data-rule="3"]') == 1
    assert _count(qtbot, view, ".rule.drop-before") == 0

    _pointer(qtbot, view, "pointerup", "document", 0)
    _sent(qtbot, seen, "rule_move_to", ["1", "2"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule')[2].dataset.rule === '1'")
    assert _count(qtbot, view, ".rule.dragging, .rule.drop-after, .rule.drop-before") == 0
    assert _eval(qtbot, view, "document.body.classList.contains('is-dragging')") is False


def test_a_drag_dropped_where_it_started_or_escaped_moves_nothing(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    grip = "document.querySelector('[data-grip=\"2\"]')"
    middle = _row_edge(qtbot, view, "2", "top") + 5

    _pointer(qtbot, view, "pointerdown", grip, middle)
    _pointer(qtbot, view, "pointermove", "document", middle)
    assert _count(qtbot, view, ".rule.drop-before, .rule.drop-after") == 0
    _pointer(qtbot, view, "pointerup", "document", middle)

    _pointer(qtbot, view, "pointerdown", grip, middle)
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "1", "top") + 2)
    assert _count(qtbot, view, '.rule.drop-before[data-rule="1"]') == 1
    _keydown(qtbot, view, "Escape")
    assert _count(qtbot, view, ".rule.dragging, .rule.drop-before") == 0
    _pointer(qtbot, view, "pointerup", "document", 0)

    qtbot.wait(150)
    assert not [edit for edit in seen if edit[0].startswith("rule_move")]


def test_a_grip_that_cannot_drag_starts_nothing(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    # The one order rule has nowhere to go.
    _pointer(qtbot, view, "pointerdown", "document.querySelector('[data-grip=\"4\"]')", 400)
    assert _count(qtbot, view, ".rule.dragging") == 0
    _pointer(qtbot, view, "pointerup", "document", 0)
    qtbot.wait(100)
    assert not [edit for edit in seen if edit[0].startswith("rule_move")]


# --- opening a rule ------------------------------------------------------------------


def test_clicking_a_name_opens_the_editor_in_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-name"))
    _sent(qtbot, seen, "open", ["1"])
    row = '.rule.open[data-rule="1"]'
    _there(qtbot, view, f"{row} .rule-editor")
    _focused(qtbot, view, "rule-1-name")
    assert _prop(qtbot, view, f"{row} .rule-name-field", "value") == "VIP priority"
    assert _count(qtbot, view, f"{row} .rule-line") == 0
    assert _style(qtbot, view, f"{row} .rule-editor", "gridColumnStart") == "3"
    assert _texts(qtbot, view, f"{row} .editor-label") == ["Level", "When", "Then"]
    assert _count(qtbot, view, ".rule.open") == 1

    _click(qtbot, view, _key("rule-2-name"))
    _there(qtbot, view, '.rule.open[data-rule="2"]')
    assert _count(qtbot, view, ".rule.open") == 1

    _click(qtbot, view, _key("rule-2-done"))
    _sent(qtbot, seen, "close", [])
    _gone(qtbot, view, ".rule.open")
    _focused(qtbot, view, "rule-2-name")


def test_typing_a_name_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    _type(qtbot, view, _key("rule-1-name"), "VIP first")
    _sent(qtbot, seen, "rule_name", ["1", "VIP first"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-name"
    assert _prop(qtbot, view, _key("rule-1-name"), "value") == "VIP first"


def test_the_level_is_two_segments_with_what_each_means(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _texts(qtbot, view, ".level-line .segment") == ["Article", "Order"]
    assert _attr(qtbot, view, _key("rule-1-level-article"), "aria-checked") == "true"
    assert _text(qtbot, view, ".level-line .hint") == "Checks one order line at a time."

    _click(qtbot, view, _key("rule-1-level-order"))
    _sent(qtbot, seen, "rule_level", ["1", "order"])
    _until_js(qtbot, view, "document.querySelector('.rule.open').dataset.group === 'order'")
    assert _text(qtbot, view, ".level-line .hint") == (
        "Checks the whole order. Runs after every article rule."
    )
    _focused(qtbot, view, "rule-1-level-order")


# --- conditions ------------------------------------------------------------------------


def test_a_condition_row_is_a_field_an_operator_and_a_value(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-c0-field")) == "Tags"
    assert _text(qtbot, view, _key("rule-1-s0-c0-op")) == "contains"
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == "VIP"
    assert _attr(qtbot, view, _key("rule-1-s0-c0-value"), "placeholder") == "Value"
    assert _attr(qtbot, view, _key("rule-1-s0-c0-remove"), "title") == "Remove condition"
    assert _count(qtbot, view, ".match-line") == 0
    columns = _style(qtbot, view, ".cond-row", "gridTemplateColumns").split()
    assert columns[1] == "180px" and columns[3] == "28px"


def test_the_field_menu_is_grouped_and_picking_reports_the_field(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "4")
    field = _key("rule-4-s0-c0-field")
    _click(qtbot, view, field)
    assert _texts(qtbot, view, ".editor-menu .menu-group") == [
        "Order fields",
        "Common fields",
        "Other fields in this analysis",
    ]
    assert _text(qtbot, view, '.editor-menu .menu-item[aria-checked="true"]') == "total_quantity"

    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'item_count').click(); true",
    )
    _sent(qtbot, seen, "cond_field", ["4", "0", "0", "item_count"])
    _until_js(qtbot, view, f"document.querySelector({field!r}).textContent.trim() === 'item_count'")
    assert _count(qtbot, view, ".editor-menu") == 0
    assert _active(qtbot, view) == "rule-4-s0-c0-field"


def test_a_field_the_level_does_not_offer_is_kept_listed_first_and_marked(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft([rule("r", conditions=[cond("item_count", "equals", "2")])]))
    _open(qtbot, view, "1")
    field = _key("rule-1-s0-c0-field")
    assert _text(qtbot, view, field) == "item_count"
    assert "invalid" in _attr(qtbot, view, field, "class")
    assert _text(qtbot, view, ".cond .problem") == (
        "“item_count” is not a field an article rule can read, so this condition never matches."
    )
    _click(qtbot, view, field)
    assert _text(qtbot, view, ".editor-menu .menu-item") == "item_countNot available"


def test_the_operator_decides_the_value_control(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "2")
    value = _key("rule-2-s0-c0-value")
    # equals on a column of the analysis: its values are suggested.
    assert _attr(qtbot, view, value, "type") == "text"
    assert _attr(qtbot, view, value, "list") == "dl-rule-2-s0-c0"
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('#dl-rule-2-s0-c0 option')).map((o) => o.value))",
        )
    ) == ["A", "B"]

    def pick(operator):
        _click(qtbot, view, _key("rule-2-s0-c0-op"))
        _eval(
            qtbot,
            view,
            "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
            f".find((el) => el.dataset.value === {operator!r}).click(); true",
        )
        _sent(qtbot, seen, "cond_operator", ["2", "0", "0", operator])

    pick("date before")
    _until_js(qtbot, view, f"document.querySelector({value!r}).type === 'date'")
    pick("is empty")
    _gone(qtbot, view, value)
    assert _count(qtbot, view, ".cond-none") == 1
    pick("in list")
    _there(qtbot, view, value)
    assert _attr(qtbot, view, value, "placeholder") == "Value1, Value2, Value3"
    assert _eval(qtbot, view, f"document.querySelector({value!r}).hasAttribute('list')") is False


def test_typing_a_value_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    value = _key("rule-1-s0-c0-value")
    _type(qtbot, view, value, "VIPs")
    _sent(qtbot, seen, "cond_value", ["1", "0", "0", "VIPs"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-s0-c0-value"
    assert _prop(qtbot, view, value, "value") == "VIPs"


def test_a_value_save_refuses_is_marked_under_its_row_and_on_the_closed_row(qtbot, page):
    view, bridge = page
    bad = rule("sizes", conditions=[cond("SKU", "matches regex", "(")])
    _wired(qtbot, view, bridge, draft([bad]))
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, ".rule .problem") == "Condition 1: Invalid regex syntax"
    assert _style(qtbot, view, ".rule .problem", "color") == _rgb(theme.status_danger)

    _open(qtbot, view, "1")
    value = _key("rule-1-s0-c0-value")
    assert "invalid" in _attr(qtbot, view, value, "class")
    assert _style(qtbot, view, value, "borderTopColor") == _rgb(theme.status_danger)
    assert _text(qtbot, view, ".cond .problem") == "Invalid regex syntax"
    assert _prop(qtbot, view, _key("rule-1-test"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-1-test"), "title") == "Fix the marked value first."


def test_a_list_says_how_many_items_under_its_row(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft([rule("r", conditions=[cond("SKU", "in list", "A, B")])]))
    _open(qtbot, view, "1")
    assert _text(qtbot, view, ".cond .hint") == "2 items"
    assert _count(qtbot, view, ".cond .problem") == 0


def test_adding_and_removing_a_condition_moves_the_focus_with_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    add = _key("rule-1-s0-cond-add")
    assert _text(qtbot, view, add) == "Add condition"
    _click(qtbot, view, add)
    _sent(qtbot, seen, "cond_add", ["1", "0"])
    _there(qtbot, view, _key("rule-1-s0-c1-field"))
    _focused(qtbot, view, "rule-1-s0-c1-field")
    assert _text(qtbot, view, _key("rule-1-s0-c1-field")) == "Order_Number"

    # Two conditions: how they combine is now a choice.
    assert _texts(qtbot, view, ".match-line .segment") == ["All", "Any"]
    assert _text(qtbot, view, ".match-line > span") == "of these match"
    _click(qtbot, view, _key("rule-1-s0-match-ANY"))
    _sent(qtbot, seen, "step_match", ["1", "0", "ANY"])
    _until_js(
        qtbot,
        view,
        f"document.querySelector({_key('rule-1-s0-match-ANY')!r}).getAttribute('aria-checked') === 'true'",
    )

    _click(qtbot, view, _key("rule-1-s0-c1-remove"))
    _sent(qtbot, seen, "cond_remove", ["1", "0", "1"])
    _gone(qtbot, view, _key("rule-1-s0-c1-field"))
    _focused(qtbot, view, "rule-1-s0-cond-add")
    assert _count(qtbot, view, ".match-line") == 0


# --- actions -----------------------------------------------------------------------------


def test_an_action_row_names_its_type_in_words_and_suggests_the_tags(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Add internal tag"
    value = _key("rule-1-s0-a0-value")
    assert _prop(qtbot, view, value, "value") == "priority"
    assert _attr(qtbot, view, value, "placeholder") == "Tag"
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('#dl-rule-1-s0-a0-value option')).map((o) => o.value))",
        )
    ) == ["heavy", "priority"]
    assert _attr(qtbot, view, _key("rule-1-s0-a0-remove"), "title") == "Remove action"

    _type(qtbot, view, value, "urgent")
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "value", "urgent"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-s0-a0-value"


def test_the_type_menu_offers_the_seven_and_changing_type_redraws_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    kind = _key("rule-1-s0-a0-type")
    _click(qtbot, view, kind)
    assert _texts(qtbot, view, ".editor-menu .menu-item") == [
        "Add internal tag",
        "Remove internal tag",
        "Hold the order",
        "Copy field",
        "Calculate",
        "Log an alert",
        "Add bonus line",
    ]
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'CALCULATE').click(); true",
    )
    _sent(qtbot, seen, "action_type", ["1", "0", "0", "CALCULATE"])
    _there(qtbot, view, _key("rule-1-s0-a0-target"))
    assert _text(qtbot, view, kind) == "Calculate"
    assert _text(qtbot, view, _key("rule-1-s0-a0-field1")) == "Order_Number"
    assert _text(qtbot, view, _key("rule-1-s0-a0-operation")) == "plus"
    assert _text(qtbot, view, _key("rule-1-s0-a0-field2")) == "Order_Number"
    assert _attr(qtbot, view, _key("rule-1-s0-a0-target"), "placeholder") == "Result column"
    assert _texts(qtbot, view, ".action .param-lead") == ["→"]

    _click(qtbot, view, _key("rule-1-s0-a0-operation"))
    assert _texts(qtbot, view, ".editor-menu .menu-item") == ["plus", "minus", "times", "divided by"]
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'multiply').click(); true",
    )
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "operation", "multiply"])
    _until_js(
        qtbot,
        view,
        f"document.querySelector({_key('rule-1-s0-a0-operation')!r}).textContent.trim() === 'times'",
    )

    _click(qtbot, view, _key("rule-1-s0-a0-field1"))
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'Quantity').click(); true",
    )
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "field1", "Quantity"])


def test_a_bad_quantity_is_marked(qtbot, page):
    view, bridge = page
    bonus = rule("bonus", actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}])
    seen = _wired(qtbot, view, bridge, draft([bonus]))
    _open(qtbot, view, "1")
    quantity = _key("rule-1-s0-a0-quantity")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Add bonus line"
    assert _prop(qtbot, view, quantity, "value") == "1"
    assert _texts(qtbot, view, ".action .param-lead") == ["×"]
    _type(qtbot, view, quantity, "lots")
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "quantity", "lots"])
    _there(qtbot, view, ".action .problem")
    assert _text(qtbot, view, ".action .problem") == "Type a whole number from 1 to 9999."
    assert "invalid" in _attr(qtbot, view, quantity, "class")
    assert _active(qtbot, view) == "rule-1-s0-a0-quantity"


def test_the_hold_and_a_retired_action_explain_themselves(qtbot, page):
    view, bridge = page
    actions = [{"type": "SET_STATUS", "value": "Not Fulfillable"}, {"type": "ADD_TAG", "value": "hold"}]
    _wired(qtbot, view, bridge, draft([rule("r", actions=actions)]))
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Hold the order"
    assert _text(qtbot, view, _key("rule-1-s0-a1-type")) == "Add status note (retired)"
    assert _texts(qtbot, view, ".action .hint") == [HOLD_HINT, RETIRED_ONE]
    _click(qtbot, view, _key("rule-1-s0-a1-type"))
    # The retired type is offered on the row that holds it, and only there.
    assert _texts(qtbot, view, ".editor-menu .menu-item")[0] == "Add status note (retired)"
    assert _count(qtbot, view, ".editor-menu .menu-item") == 8
    _keydown(qtbot, view, "Escape")
    _click(qtbot, view, _key("rule-1-s0-a0-type"))
    assert _count(qtbot, view, ".editor-menu .menu-item") == 7


def test_adding_and_removing_an_action_moves_the_focus_with_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    _click(qtbot, view, _key("rule-1-s0-action-add"))
    _sent(qtbot, seen, "action_add", ["1", "0"])
    _focused(qtbot, view, "rule-1-s0-a1-type")
    assert _prop(qtbot, view, _key("rule-1-s0-a1-value"), "value") == ""
    _click(qtbot, view, _key("rule-1-s0-a1-remove"))
    _sent(qtbot, seen, "action_remove", ["1", "0", "1"])
    _focused(qtbot, view, "rule-1-s0-action-add")


# --- steps ---------------------------------------------------------------------------------


def test_a_second_step_gives_every_step_a_heading(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _count(qtbot, view, ".step-head") == 0
    _click(qtbot, view, _key("rule-1-step-add"))
    _sent(qtbot, seen, "step_add", ["1"])
    _until_js(qtbot, view, "document.querySelectorAll('.step-head').length === 2")
    assert _texts(qtbot, view, ".step-title") == ["Step 1", "Step 2"]
    assert _texts(qtbot, view, ".step-note") == ["", "Checks only the lines step 1 matched."]
    assert _count(qtbot, view, _key("rule-1-s0-remove")) == 0
    assert _text(qtbot, view, _key("rule-1-s1-remove")) == "Remove step"

    _click(qtbot, view, _key("rule-1-s1-remove"))
    _sent(qtbot, seen, "step_remove", ["1", "1"])
    _until_js(qtbot, view, "document.querySelectorAll('.step-head').length === 0")
    _focused(qtbot, view, "rule-1-step-add")


# --- Test... ----------------------------------------------------------------------------------


def test_test_asks_the_bridge_for_that_rule(qtbot, page):
    view, bridge = page
    asked = []
    bridge.testRequested.connect(asked.append)
    _show(qtbot, view, bridge, draft())
    assert _text(qtbot, view, _key("rule-2-test")) == "Test…"
    assert _attr(qtbot, view, _key("rule-2-test"), "title") == ""
    _click(qtbot, view, _key("rule-2-test"))
    qtbot.waitUntil(lambda: asked == ["2"])


def test_with_no_analysis_test_is_disabled_and_says_why(qtbot, page):
    view, bridge = page
    asked = []
    bridge.testRequested.connect(asked.append)
    _show(qtbot, view, bridge, draft(analysis=False))
    assert _prop(qtbot, view, _key("rule-1-test"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-1-test"), "title") == TEST_NO_ANALYSIS
    _click(qtbot, view, _key("rule-1-test"))
    qtbot.wait(100)
    assert asked == []


def _with_test(d, test):
    return {**d.view(), "test": {"uid": "1", **test}}


def _push(qtbot, view, bridge, state):
    before = _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")
    bridge.set_state(state)
    _until_js(qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}")


def test_the_panel_says_it_is_running_and_takes_the_page_over(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, running_view(d.test_config("1"), frame(), "2026-09-30_1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "running"
    assert _text(qtbot, view, ".test-title") == "Test “VIP priority”"
    assert _text(qtbot, view, ".test-intro") == (
        "Runs this rule, as edited, against the analysis in 2026-09-30_1. Orders aren’t changed."
    )
    assert _text(qtbot, view, ".test-intro .mono") == "2026-09-30_1"
    assert _text(qtbot, view, ".test-message") == "Testing 3 orders…"
    assert _count(qtbot, view, ".test-table") == 0
    assert _prop(qtbot, view, ".settings-page", "inert") is True
    assert _attr(qtbot, view, ".test-panel", "role") == "dialog"
    _focused(qtbot, view, "test-close")
    assert _style(qtbot, view, ".scrim", "backgroundColor") == "rgba(0, 0, 0, 0.35)"
    assert _style(qtbot, view, ".scrim", "position") == "fixed"
    assert _style(qtbot, view, ".test-panel", "width") == "580px"


def test_the_panel_counts_orders_and_lists_them(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, run_rule_test(d.test_config("1"), frame(), "S1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "done"
    assert _text(qtbot, view, ".test-matched") == "2"
    assert _text(qtbot, view, ".test-count") == "2of 3 orders match"
    assert _texts(qtbot, view, ".test-row.heads span") == ["Order", "Matched on", "Change"]
    assert _texts(qtbot, view, ".test-order") == ["#1", "#3"]
    assert _texts(qtbot, view, ".test-why") == ["Tags: VIP, repeat", "Tags: VIP"]
    assert _texts(qtbot, view, ".test-change") == ["+ priority", "+ priority"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".test-change", "color") == _rgb(theme.status_success)
    assert _style(qtbot, view, ".test-row.heads", "backgroundColor") == _rgb(theme.surface_raised)
    columns = _style(qtbot, view, ".test-row", "gridTemplateColumns").split()
    assert columns[0] == "90px" and columns[2] == "150px"
    assert _count(qtbot, view, ".test-more") == 0
    assert _count(qtbot, view, ".test-body .hint") == 0


def test_the_panel_says_more_no_change_and_no_match(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    done = run_rule_test(d.test_config("1"), frame(), "S1", limit=1)
    done["rows"][0].update(change="No change", changed=False)
    done["note"] = "No change: the analysis already has the saved rules applied."
    _push(qtbot, view, bridge, _with_test(d, done))
    assert _text(qtbot, view, ".test-more") == "and 1 more"
    assert "same" in _attr(qtbot, view, ".test-change", "class")
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".test-change", "color") == _rgb(theme.text_secondary)
    assert _text(qtbot, view, ".test-body .hint") == (
        "No change: the analysis already has the saved rules applied."
    )

    none = run_rule_test(rule("r", conditions=[cond("SKU", "equals", "Z")]), frame(), "S1")
    _push(qtbot, view, bridge, _with_test(d, none))
    assert _text(qtbot, view, ".test-matched") == "0"
    assert _text(qtbot, view, ".test-message") == "No order in this analysis matches."
    assert _count(qtbot, view, ".test-table") == 0


def test_a_failed_test_says_where_to_look(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, failed_view(d.test_config("1"), "S1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "failed"
    assert _text(qtbot, view, ".test-body .problem") == (
        "The rule test didn’t finish. Details are in Logs."
    )


@pytest.mark.parametrize("how", ["test-close", "test-x", "Escape"])
def test_close_the_x_and_escape_all_close_the_panel_and_focus_returns(qtbot, page, how):
    view, bridge = page
    d = draft()
    closed = []
    bridge.testClosed.connect(lambda: closed.append(True))
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, run_rule_test(d.test_config("1"), frame(), "S1")))
    if how == "Escape":
        _keydown(qtbot, view, "Escape")
    else:
        _click(qtbot, view, _key(how))
    qtbot.waitUntil(lambda: closed == [True])

    _push(qtbot, view, bridge, d.view())
    assert _count(qtbot, view, ".scrim") == 0
    assert _prop(qtbot, view, ".settings-page", "inert") is False
    _focused(qtbot, view, "rule-1-test")


def test_escape_with_nothing_open_is_left_for_the_dialog(qtbot, page):
    view, bridge = page
    closed = []
    bridge.testClosed.connect(lambda: closed.append(True))
    _show(qtbot, view, bridge, draft())
    prevented = _eval(
        qtbot,
        view,
        "!document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'Escape', bubbles: true, cancelable: true}))",
    )
    assert prevented is False
    assert closed == []


# --- the footer's link, and the theme -----------------------------------------------------------


def test_every_blocker_key_names_a_control_the_page_draws_once_revealed(qtbot, page):
    """The keys are spelled in rules_state.py and again in settings_rules.js."""
    view, bridge = page
    bad_value = rule("sizes", conditions=[cond(), cond("SKU", "matches regex", "(")])
    bad_quantity = rule("bonus", actions=[tag(), {"type": "ADD_PRODUCT", "sku": "G", "quantity": "x"}])
    for given in (bad_value, bad_quantity):
        d = draft([given])
        key = d.blocker_key()
        assert key
        assert d.apply("reveal", [key])
        _show(qtbot, view, bridge, d)
        assert _count(qtbot, view, _key(key)) == 1, key
        bridge.problemFocusRequested.emit(key)
        _focused(qtbot, view, key)


def test_the_page_follows_a_theme_change_without_a_reload(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    manager = get_theme_manager()
    start = manager.get_current_theme().name
    other = "dark" if start == "light" else "light"
    try:
        manager.set_theme(other)
        raised = _rgb(manager.get_current_theme().surface_raised)
        _until_js(
            qtbot,
            view,
            f"getComputedStyle(document.querySelector('.rule-chip')).backgroundColor === {raised!r}",
        )
        assert _style(qtbot, view, "#settings", "colorScheme") == other
    finally:
        manager.set_theme(start)
