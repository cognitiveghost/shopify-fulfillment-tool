"""RulesDraft: the rules behind the Rules page (phase 8 spec sections 3.3 and 4).

No widget and no Chromium: the draft is plain Python. Rules are addressed by
the uid the draft hands out: "1", "2", ... in the order it lists them.
"""

import copy
import json

import pandas as pd
import pytest

from gui.settings.fields import ACTION_TYPES, CONDITION_OPERATORS, LEGACY_ACTION_TYPES
from gui.settings.rules_state import (
    CLEAR_FILTER,
    HOLD_HINT,
    NO_DATE,
    NO_FIELD,
    NOT_AVAILABLE,
    QUANTITY_PROBLEM,
    RETIRED_MANY,
    RETIRED_ONE,
    SUGGESTION_LIMIT,
    TEST_BLOCKED,
    TEST_NO_ANALYSIS,
    TEST_NO_CONDITION,
    UNKNOWN_ACTION,
    RulesDraft,
    rule_fields,
    value_kind,
)
from shopify_tool.rules import RuleEngine

TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "handling": {"label": "Handling", "color": "#FF0000", "tags": ["FRAGILE", "GIFT"], "order": 1},
        "shipping": {"label": "Shipping", "color": "#00FF00", "tags": ["EXPRESS", "GIFT"], "order": 2},
    },
}


@pytest.fixture
def analysis_df():
    return pd.DataFrame(
        {
            "Order_Number": ["A", "B"],
            "SKU": ["x", "y"],
            "Quantity": [1, 2],
            "Notes": ["leave at door", ""],
            "_internal": [0, 0],
        }
    )


def cond(field="SKU", operator="equals", value="x"):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(name="r", level="article", conditions=None, actions=None, match="ALL", **extra):
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


def names(draft):
    return [r["name"] for r in draft.rules]


def stored(draft):
    return draft.collect()["rules"]


def rows(draft):
    return [row for group in draft.view()["rules"]["groups"] for row in group["rows"]]


def editor(draft):
    return next(row["editor"] for row in rows(draft) if row["open"])


def opened(rules, analysis_df=None, **kwargs):
    """A draft with its first rule open."""
    draft = RulesDraft(rules, analysis_df, **kwargs)
    assert draft.apply("open", ["1"])
    return draft


# --- loading -----------------------------------------------------------------


def test_rules_load_in_the_order_the_engine_runs_them():
    given = [
        rule("o1", "order", priority=1),
        rule("a2", priority=2),
        rule("a1", priority=1),
        rule("late"),
    ]
    draft = RulesDraft(given)
    assert names(draft) == [r["name"] for r in RuleEngine(given).rules]
    assert names(draft) == ["a1", "a2", "late", "o1"]


def test_the_callers_rules_are_not_written_to():
    given = [rule("a", actions=[{"type": "SET_STATUS", "value": "Ready"}])]
    before = copy.deepcopy(given)
    draft = RulesDraft(given)
    draft.apply("rule_name", ["1", "renamed"])
    assert given == before


def test_the_old_format_loads_as_one_step():
    old = {
        "name": "old",
        "match": "ANY",
        "conditions": [cond()],
        "actions": [tag()],
    }
    assert stored(RulesDraft([old])) == [
        {
            "name": "old",
            "priority": 1,
            "level": "article",
            "steps": [{"conditions": [cond()], "match": "ANY", "actions": [tag()]}],
        }
    ]


@pytest.mark.parametrize(
    "match, read", [("any", "ANY"), ("ANY", "ANY"), ("all", "ALL"), ("either", "ALL"), (None, "ALL")]
)
def test_match_loads_as_the_engine_reads_it(match, read):
    draft = RulesDraft([rule(match=match)])
    assert stored(draft)[0]["steps"][0]["match"] == read


def test_a_rule_with_no_steps_gets_one_empty_step():
    draft = RulesDraft([{"name": "bare"}])
    assert stored(draft)[0]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]


def test_a_stale_status_loads_as_the_hold():
    draft = RulesDraft([rule(actions=[{"type": "SET_STATUS", "value": "Fulfillable"}])])
    assert stored(draft)[0]["steps"][0]["actions"] == [
        {"type": "SET_STATUS", "value": "Not Fulfillable"}
    ]


def test_set_multi_tags_loads_its_list_as_text():
    draft = RulesDraft([rule(actions=[{"type": "SET_MULTI_TAGS", "tags": ["A", "B"]}])])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": "SET_MULTI_TAGS", "value": "A, B"}]


@pytest.mark.parametrize("legacy", ["ADD_TAG", "ADD_ORDER_TAG"])
def test_a_retired_action_survives_untouched(legacy):
    action = {"type": legacy, "value": "KEEP_ME"}
    assert stored(RulesDraft([rule(actions=[action])]))[0]["steps"][0]["actions"] == [action]


def test_an_actions_extra_keys_survive():
    action = {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3, "product_name": "Bonus pen"}
    assert stored(RulesDraft([rule(actions=[action])]))[0]["steps"][0]["actions"] == [action]


def test_add_product_with_no_quantity_takes_one():
    draft = RulesDraft([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT"}])])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == 1


def test_an_unknown_operator_field_and_action_are_kept():
    given = rule(
        conditions=[cond("Mystery", "sounds like", "x")],
        actions=[{"type": "SET_PRIORITY", "value": "High"}],
    )
    assert stored(RulesDraft([given]))[0]["steps"] == given["steps"]


def test_a_profile_edited_into_odd_shapes_still_loads_and_saves(analysis_df):
    """A hand-edited profile: the page opens, lists what it can read, and
    saves without raising."""
    odd = [
        None,
        "not a rule",
        {"name": 7, "steps": "soon"},
        {"name": "nulls", "steps": [{"conditions": None, "actions": None, "match": None}, "x"]},
        {
            "name": "values",
            "steps": [
                {
                    "conditions": [cond("Quantity", "equals", 5), cond("SKU", "in list", ["A", "B"]), "junk", {}],
                    "actions": [{}, "junk", {"type": None}],
                }
            ],
        },
    ]
    draft = RulesDraft(odd, analysis_df)
    assert names(draft) == ["7", "nulls", "values"]
    for model in draft.rules:
        assert draft.apply("open", [model["uid"]])
        assert editor(draft)["steps"]
    saved = stored(draft)
    assert json.loads(json.dumps(saved)) == saved
    assert saved[0]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]
    assert saved[1]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]
    assert saved[2]["steps"][0]["conditions"] == [
        cond("Quantity", "equals", 5),
        cond("SKU", "in list", ["A", "B"]),
        cond("", "", ""),
    ]
    assert saved[2]["steps"][0]["actions"] == [{"type": ""}, {"type": ""}]
    assert draft.blocker() is None
    assert draft.snapshot()


def test_a_rules_other_keys_survive():
    assert stored(RulesDraft([rule(note="keep me")]))[0]["note"] == "keep me"


# --- collect, snapshot ---------------------------------------------------------


def test_the_fixture_config_round_trips():
    """What tests/conftest.py's settings_fixture_config holds under "rules"."""
    rules = [
        {
            "name": "Flag big orders",
            "priority": 1,
            "level": "order",
            "steps": [
                {
                    "conditions": [cond("item_count", "is greater than", "5")],
                    "match": "ALL",
                    "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                }
            ],
        }
    ]
    assert RulesDraft(rules).collect() == {"rules": rules}


def test_no_rules_collect_as_an_empty_list():
    assert RulesDraft([]).collect() == {"rules": []}
    assert RulesDraft(None).collect() == {"rules": []}


def test_priority_is_the_place_in_the_list():
    draft = RulesDraft([rule("a", priority=7), rule("b", priority=9)])
    assert [r["priority"] for r in stored(draft)] == [1, 2]


def test_enabled_is_written_only_when_a_rule_is_off():
    draft = RulesDraft([rule("on", enabled=True), rule("off", enabled=False), rule("plain")])
    assert ["enabled" in r for r in stored(draft)] == [False, True, False]
    assert stored(draft)[1]["enabled"] is False


def test_turning_a_rule_off_and_on_again_leaves_no_trace():
    draft = RulesDraft([rule()])
    draft.mark_clean()
    assert draft.apply("rule_enabled", ["1", False])
    assert draft.is_dirty()
    assert draft.apply("rule_enabled", ["1", True])
    assert not draft.is_dirty()


def test_what_is_only_drawn_does_not_mark_the_page_unsaved():
    draft = RulesDraft([rule("alpha"), rule("beta")])
    draft.mark_clean()
    assert draft.apply("filter", ["alp"])
    assert draft.apply("open", ["2"])
    assert draft.apply("close", [])
    assert not draft.is_dirty()


# --- edits the draft drops -------------------------------------------------------


@pytest.mark.parametrize(
    "action, args",
    [
        ("no_such_action", []),
        ("rule_name", ["1"]),
        ("rule_name", ["1", 5]),
        ("rule_name", "1"),
        ("rule_name", ["9", "x"]),
        ("rule_name", ["1", "r"]),
        ("rule_enabled", ["1", "false"]),
        ("rule_enabled", ["1", True]),
        ("rule_level", ["1", "line"]),
        ("rule_level", ["1", "article"]),
        ("rule_move", ["1", "sideways"]),
        ("rule_move", ["1", "up"]),
        ("rule_move", ["1", "down"]),
        ("rule_move_to", ["1", "0"]),
        ("rule_move_to", ["1", "1"]),
        ("rule_move_to", ["1", "-1"]),
        ("rule_delete", ["9"]),
        ("rule_duplicate", ["9"]),
        ("open", ["9"]),
        ("close", []),
        ("filter", [""]),
        ("reveal", ["threshold"]),
        ("reveal", ["rule-9-s0-c0-value"]),
        ("step_remove", ["1", "0"]),
        ("step_remove", ["1", "1"]),
        ("step_match", ["1", "0", "ALL"]),
        ("step_match", ["1", "0", "SOME"]),
        ("step_match", ["1", "4", "ANY"]),
        ("cond_add", ["1", "4"]),
        ("cond_remove", ["1", "0", "4"]),
        ("cond_field", ["1", "0", "0", "No_Such_Column"]),
        ("cond_field", ["1", "0", "0", "item_count"]),
        ("cond_field", ["1", "0", "0", "SKU"]),
        ("cond_operator", ["1", "0", "0", "sounds like"]),
        ("cond_operator", ["1", "0", "0", "equals"]),
        ("cond_value", ["1", "0", "0", "x"]),
        ("cond_value", ["1", "0", "x", "y"]),
        ("action_remove", ["1", "0", "4"]),
        ("action_type", ["1", "0", "0", "ADD_TAG"]),
        ("action_type", ["1", "0", "0", "ADD_INTERNAL_TAG"]),
        ("action_param", ["1", "0", "0", "sku", "x"]),
        ("action_param", ["1", "0", "0", "value", "T"]),
    ],
)
def test_an_edit_that_is_unknown_misshapen_or_changes_nothing_is_dropped(action, args, analysis_df):
    draft = RulesDraft([rule()], analysis_df)
    before = draft.collect()
    assert draft.apply(action, args) is False
    assert draft.collect() == before


# --- the list --------------------------------------------------------------------


def test_filter_lists_the_rules_whose_name_holds_the_text():
    draft = RulesDraft([rule("Alpha"), rule("beta"), rule("alphabet")])
    assert draft.apply("filter", [" ALP "])
    view = draft.view()["rules"]
    assert [row["name"] for row in rows(draft)] == ["Alpha", "alphabet"]
    assert [row["num"] for row in rows(draft)] == ["01", "03"]
    assert view["filtering"] is True
    assert view["no_hits"] == ""


def test_a_filter_is_plain_text():
    draft = RulesDraft([rule("Size (EU)"), rule("Size [US]")])
    draft.apply("filter", ["("])
    assert [row["name"] for row in rows(draft)] == ["Size (EU)"]
    draft.apply("filter", ["[u"])
    assert [row["name"] for row in rows(draft)] == ["Size [US]"]


def test_a_filter_with_no_match_says_so():
    draft = RulesDraft([rule("Alpha")])
    draft.apply("filter", [" zeta "])
    view = draft.view()["rules"]
    assert view["groups"] == []
    assert view["no_hits"] == "No rules named “zeta”."


def test_the_open_rule_is_listed_whatever_the_filter():
    draft = RulesDraft([rule("Alpha"), rule("beta")])
    draft.apply("open", ["2"])
    draft.apply("filter", ["alp"])
    assert [row["name"] for row in rows(draft)] == ["Alpha", "beta"]


def test_open_shows_one_editor_at_a_time():
    draft = RulesDraft([rule("a"), rule("b")])
    assert draft.apply("open", ["1"])
    assert draft.apply("open", ["2"])
    assert [row["open"] for row in rows(draft)] == [False, True]
    assert [row["editor"] is None for row in rows(draft)] == [True, False]
    assert draft.apply("close", [])
    assert not any(row["open"] for row in rows(draft))


def test_reveal_opens_the_rule_a_key_belongs_to():
    draft = RulesDraft([rule("a"), rule("b")])
    assert draft.apply("reveal", ["rule-2-s0-c0-value"])
    assert draft.open_uid == "2"
    assert draft.apply("reveal", ["rule-2-s0-c0-value"]) is False


def test_add_rule_appends_an_article_rule_and_opens_it():
    draft = RulesDraft([rule("a"), rule("o", "order")])
    assert draft.apply("rule_add", [])
    assert names(draft) == ["a", "New rule", "o"]
    new = stored(draft)[1]
    assert new == {
        "name": "New rule",
        "priority": 2,
        "level": "article",
        "steps": [{"conditions": [], "match": "ALL", "actions": []}],
    }
    assert draft.open_uid == draft.rules[1]["uid"]


def test_duplicate_puts_a_copy_right_after():
    draft = RulesDraft([rule("a", enabled=False, note="n"), rule("b")])
    assert draft.apply("rule_duplicate", ["1"])
    assert names(draft) == ["a", "a copy", "b"]
    twin = stored(draft)[1]
    assert twin["enabled"] is False and twin["note"] == "n"
    draft.apply("cond_value", [draft.rules[1]["uid"], "0", "0", "changed"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "x"


def test_delete_removes_the_rule_and_closes_its_editor():
    draft = opened([rule("a"), rule("b")])
    assert draft.apply("rule_delete", ["1"])
    assert names(draft) == ["b"]
    assert draft.open_uid is None


def test_a_move_stays_inside_the_rules_level():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order"), rule("o2", "order")])
    assert draft.apply("rule_move", ["2", "down"]) is False
    assert draft.apply("rule_move", ["3", "up"]) is False
    assert draft.apply("rule_move", ["2", "up"])
    assert draft.apply("rule_move", ["3", "down"])
    assert names(draft) == ["a2", "a1", "o2", "o1"]


def test_move_to_takes_a_place_among_the_rules_of_its_level():
    draft = RulesDraft(
        [rule("a1"), rule("a2"), rule("a3"), rule("o1", "order"), rule("o2", "order")]
    )
    assert draft.apply("rule_move_to", ["1", "2"])
    assert names(draft) == ["a2", "a3", "a1", "o1", "o2"]
    assert draft.apply("rule_move_to", ["5", "0"])
    assert names(draft) == ["a2", "a3", "a1", "o2", "o1"]
    assert draft.apply("rule_move_to", ["5", "2"]) is False


def test_changing_the_level_moves_the_rule_to_the_end_of_that_level():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order")])
    assert draft.apply("rule_level", ["1", "order"])
    assert names(draft) == ["a2", "o1", "a1"]
    assert stored(draft)[2]["level"] == "order"
    # o1 (uid 3) becomes the last article rule; a1 is the one order rule left.
    assert draft.apply("rule_level", ["3", "article"])
    assert names(draft) == ["a2", "o1", "a1"]
    assert [r["level"] for r in draft.rules] == ["article", "article", "order"]


def test_the_groups_are_labelled_only_when_both_levels_exist():
    one = RulesDraft([rule("a1"), rule("a2")]).view()["rules"]["groups"]
    assert [(g["level"], g["label"], g["note"]) for g in one] == [("article", "", "")]
    both = RulesDraft([rule("a1"), rule("o1", "order")]).view()["rules"]["groups"]
    assert [(g["level"], g["label"], g["note"]) for g in both] == [
        ("article", "Article rules", "Check one order line at a time."),
        ("order", "Order rules", "Check the whole order. Run after every article rule."),
    ]


def test_a_row_says_where_it_can_move():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order")])
    got = [(r["num"], r["can_up"], r["can_down"], r["can_drag"]) for r in rows(draft)]
    assert got == [
        ("01", False, True, True),
        ("02", True, False, True),
        ("03", False, False, False),
    ]
    draft.apply("filter", ["a"])
    assert all(
        (r["can_up"], r["can_down"], r["can_drag"], r["move_title"])
        == (False, False, False, CLEAR_FILTER)
        for r in rows(draft)
    )


def test_a_row_shows_whether_the_rule_is_on():
    draft = RulesDraft([rule("on"), rule("off", enabled=False)])
    assert [(r["on"], r["badge"], r["switch_title"]) for r in rows(draft)] == [
        (True, "", "Turn off"),
        (False, "Off", "Turn on"),
    ]


def test_a_row_is_called_by_its_name_or_says_it_has_none():
    draft = RulesDraft([rule("VIP"), rule("")])
    assert [(r["name"], r["label"]) for r in rows(draft)] == [("VIP", "VIP"), ("", "Unnamed rule")]
    assert stored(draft)[1]["name"] == ""


@pytest.mark.parametrize(
    "rules, count",
    [
        ([rule()], "1 rule · 1 on"),
        ([rule(), rule(enabled=False), rule()], "3 rules · 2 on"),
    ],
)
def test_the_count(rules, count):
    assert RulesDraft(rules).view()["rules"]["count"] == count


def test_the_head_and_the_empty_state():
    view = RulesDraft([]).view()
    assert view["page"] == "rules"
    assert view["title"] == "Rules"
    assert view["subtitle"] == (
        "Change orders at the end of each analysis. Rules run top to bottom."
    )
    assert view["action"] == ""
    assert view["rules"]["empty"] == {
        "title": "No rules yet",
        "text": "Rules change orders at the end of each analysis, e.g. tag VIP orders.",
        "action": "Add rule",
    }
    assert view["rules"]["groups"] == []
    assert view["rules"]["no_hits"] == ""

    with_one = RulesDraft([rule()]).view()
    assert with_one["action"] == "Add rule"
    assert with_one["rules"]["empty"] is None
    assert with_one["rules"]["filter_placeholder"] == "Filter by name"


# --- the summary -------------------------------------------------------------------


def parts(*pairs):
    return [{"t": kind, "v": text} for kind, text in pairs]


def test_a_summary_reads_as_a_sentence():
    given = rule(
        conditions=[cond("Tags", "contains", "VIP"), cond("Notes", "is empty", "")],
        actions=[tag("priority"), {"type": "SET_STATUS", "value": "Not Fulfillable"}],
    )
    row = rows(RulesDraft([given]))[0]
    assert row["wide_labels"] is False
    assert row["summary"] == [
        {
            "label": "When",
            "parts": parts(
                ("bold", "Tags"),
                ("text", "contains"),
                ("chip", "VIP"),
                ("join", "and"),
                ("bold", "Notes"),
                ("text", "is empty"),
            ),
        },
        {
            "label": "Then",
            "parts": parts(
                ("text", "Add internal tag"),
                ("chip", "priority"),
                ("join", "and"),
                ("text", "Hold the order"),
            ),
        },
    ]


def test_any_joins_its_conditions_with_or():
    given = rule(conditions=[cond("SKU", "equals", "A"), cond("SKU", "equals", "B")], match="ANY")
    when = rows(RulesDraft([given]))[0]["summary"][0]["parts"]
    assert {"t": "join", "v": "or"} in when


def test_a_rule_with_steps_reads_step_by_step():
    given = rule()
    given["steps"].append({"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": []})
    row = rows(RulesDraft([given]))[0]
    assert row["wide_labels"] is True
    assert [line["label"] for line in row["summary"]] == ["When", "Then", "And when", "Then"]
    assert row["summary"][3]["parts"] == parts(("muted", "No action yet."))


def test_an_empty_rule_says_it_never_matches():
    row = rows(RulesDraft([rule(conditions=[], actions=[])]))[0]
    assert row["summary"][0]["parts"] == parts(
        ("muted", "No condition yet, so this rule never matches.")
    )


@pytest.mark.parametrize(
    "action, expected",
    [
        ({"type": "REMOVE_INTERNAL_TAG", "value": "hold"}, [("text", "Remove internal tag"), ("chip", "hold")]),
        (
            {"type": "COPY_FIELD", "source": "SKU", "target": "Code"},
            [("text", "Copy"), ("chip", "SKU"), ("text", "to"), ("chip", "Code")],
        ),
        (
            {"type": "CALCULATE", "operation": "multiply", "field1": "Quantity", "field2": "Stock", "target": "Total"},
            [("text", "Calculate"), ("chip", "Quantity × Stock"), ("text", "into"), ("chip", "Total")],
        ),
        (
            {"type": "ALERT_NOTIFICATION", "message": "Check this", "severity": "warning"},
            [("text", "Log an alert"), ("chip", "Check this")],
        ),
        ({"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 2}, [("text", "Add bonus line"), ("chip", "GIFT ×2")]),
        ({"type": "ADD_TAG", "value": "VIP"}, [("text", "Add status note"), ("chip", "VIP")]),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, [("text", "Add status notes"), ("chip", "A, B")]),
        ({"type": "SET_PRIORITY", "value": "High"}, [("text", "SET_PRIORITY")]),
        ({"type": "ADD_INTERNAL_TAG", "value": ""}, [("text", "Add internal tag")]),
    ],
)
def test_each_action_has_its_words(action, expected):
    then = rows(RulesDraft([rule(actions=[action])]))[0]["summary"][1]["parts"]
    assert then == parts(*expected)


# --- fields --------------------------------------------------------------------------


def test_an_article_rule_is_not_offered_the_order_fields(analysis_df):
    groups = rule_fields("article", analysis_df)
    assert [label for label, _fields in groups] == ["Common fields", "Other fields in this analysis"]
    offered = {f for _label, fields in groups for f in fields}
    assert not offered & set(RuleEngine.ORDER_LEVEL_FIELDS)
    assert {"SKU", "Quantity", "Notes"} <= offered
    assert "_internal" not in offered
    assert groups[1][1] == ["Notes"]


def test_an_order_rule_is_offered_every_order_field_first(analysis_df):
    groups = rule_fields("order", analysis_df)
    assert groups[0] == ("Order fields", list(RuleEngine.ORDER_LEVEL_FIELDS))


@pytest.mark.parametrize("frame", [None, pd.DataFrame()])
def test_with_no_analysis_only_the_common_fields_are_listed(frame):
    assert [label for label, _fields in rule_fields("article", frame)] == ["Common fields"]


@pytest.mark.parametrize(
    "operator, kind",
    [("is empty", "none"), ("is not empty", "none"), ("date before", "date"),
     ("date equals", "date"), ("equals", "text"), ("matches regex", "text")],
)
def test_value_kind(operator, kind):
    assert value_kind(operator) == kind


# --- the editor: edits -----------------------------------------------------------------


def test_steps_are_added_and_removed_but_never_the_first():
    draft = opened([rule()])
    assert draft.apply("step_add", ["1"])
    assert stored(draft)[0]["steps"][1] == {"conditions": [], "match": "ALL", "actions": []}
    steps = editor(draft)["steps"]
    assert [(s["title"], s["note"], s["removable"]) for s in steps] == [
        ("Step 1", "", False),
        ("Step 2", "Checks only the lines step 1 matched.", True),
    ]
    assert draft.apply("step_remove", ["1", "1"])
    assert len(stored(draft)[0]["steps"]) == 1
    assert editor(draft)["steps"][0]["title"] == ""


def test_an_order_rules_later_step_says_it_is_a_gate():
    draft = opened([rule(level="order")])
    draft.apply("step_add", ["1"])
    assert editor(draft)["steps"][1]["note"] == "Runs only if step 1 matched."


def test_match_is_drawn_from_two_conditions_up():
    draft = opened([rule()])
    assert editor(draft)["steps"][0]["match"]["show"] is False
    assert draft.apply("cond_add", ["1", "0"])
    match = editor(draft)["steps"][0]["match"]
    assert match["show"] is True
    assert match["tail"] == "of these match"
    assert [(o["value"], o["label"], o["checked"]) for o in match["options"]] == [
        ("ALL", "All", True),
        ("ANY", "Any", False),
    ]
    assert draft.apply("step_match", ["1", "0", "ANY"])
    assert stored(draft)[0]["steps"][0]["match"] == "ANY"


@pytest.mark.parametrize("level, first", [("article", "Order_Number"), ("order", "item_count")])
def test_a_new_condition_starts_on_the_levels_first_field(level, first):
    draft = opened([rule(level=level, conditions=[])])
    assert draft.apply("cond_add", ["1", "0"])
    assert stored(draft)[0]["steps"][0]["conditions"] == [cond(first, "equals", "")]


def test_a_condition_is_edited_and_removed(analysis_df):
    draft = opened([rule()], analysis_df)
    assert draft.apply("cond_field", ["1", "0", "0", "Quantity"])
    assert draft.apply("cond_operator", ["1", "0", "0", "is greater than"])
    assert draft.apply("cond_value", ["1", "0", "0", "5"])
    assert stored(draft)[0]["steps"][0]["conditions"] == [cond("Quantity", "is greater than", "5")]
    assert draft.apply("cond_remove", ["1", "0", "0"])
    assert stored(draft)[0]["steps"][0]["conditions"] == []


def test_an_operator_keeps_the_value_unless_it_takes_another_kind():
    draft = opened([rule(conditions=[cond("SKU", "equals", "ABC")])])
    draft.apply("cond_operator", ["1", "0", "0", "contains"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "ABC"
    draft.apply("cond_operator", ["1", "0", "0", "date before"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == ""
    draft.apply("cond_value", ["1", "0", "0", "2026-01-30"])
    draft.apply("cond_operator", ["1", "0", "0", "date after"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "2026-01-30"
    draft.apply("cond_operator", ["1", "0", "0", "is empty"])
    assert stored(draft)[0]["steps"][0]["conditions"][0] == cond("SKU", "is empty", "")


def test_a_stored_number_is_kept_until_it_is_edited():
    draft = opened([rule(conditions=[cond("Quantity", "is greater than", 5)])])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == 5
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["text"] == "5"
    assert draft.apply("cond_value", ["1", "0", "0", "6"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "6"


def test_a_new_action_adds_an_internal_tag_and_starts_blank():
    draft = opened([rule(actions=[])], tag_categories=TAG_CATEGORIES)
    assert draft.apply("action_add", ["1", "0"])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": "ADD_INTERNAL_TAG", "value": ""}]


@pytest.mark.parametrize(
    "kind, default",
    [
        ("REMOVE_INTERNAL_TAG", {"value": ""}),
        ("SET_STATUS", {"value": "Not Fulfillable"}),
        ("COPY_FIELD", {"source": "Order_Number", "target": ""}),
        ("CALCULATE", {"operation": "add", "field1": "Order_Number", "field2": "Order_Number", "target": ""}),
        ("ALERT_NOTIFICATION", {"message": "", "severity": "info"}),
        ("ADD_PRODUCT", {"sku": "", "quantity": 1}),
    ],
)
def test_changing_an_actions_type_starts_it_from_that_types_default(kind, default):
    draft = opened([rule(actions=[{"type": "ADD_TAG", "value": "old"}])])
    assert draft.apply("action_type", ["1", "0", "0", kind])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": kind, **default}]


def test_every_offered_type_has_a_label_a_default_and_parameters():
    draft = opened([rule()])
    offered = editor(draft)["action_types"]
    assert [t["value"] for t in offered] == ACTION_TYPES
    assert not {t["value"] for t in offered} & set(LEGACY_ACTION_TYPES)
    for kind in ACTION_TYPES[1:] + ACTION_TYPES[:1]:
        assert draft.apply("action_type", ["1", "0", "0", kind])
        assert editor(draft)["steps"][0]["actions"][0]["extra_type"] is None


def test_an_actions_parameters_are_edited(analysis_df):
    draft = opened([rule(actions=[{"type": "CALCULATE", "operation": "add", "field1": "SKU", "field2": "SKU", "target": ""}])], analysis_df)
    assert draft.apply("action_param", ["1", "0", "0", "operation", "divide"])
    assert draft.apply("action_param", ["1", "0", "0", "field1", "Quantity"])
    assert draft.apply("action_param", ["1", "0", "0", "target", "Half"])
    assert draft.apply("action_param", ["1", "0", "0", "operation", "modulo"]) is False
    assert draft.apply("action_param", ["1", "0", "0", "field2", "Nope"]) is False
    assert stored(draft)[0]["steps"][0]["actions"] == [
        {"type": "CALCULATE", "operation": "divide", "field1": "Quantity", "field2": "SKU", "target": "Half"}
    ]


def test_a_quantity_is_stored_as_a_number_when_it_is_one():
    draft = opened([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}])])
    assert draft.apply("action_param", ["1", "0", "0", "quantity", " 3 "])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == 3
    assert draft.apply("action_param", ["1", "0", "0", "quantity", "3"]) is False
    assert draft.apply("action_param", ["1", "0", "0", "quantity", "lots"])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == "lots"


def test_an_action_is_removed():
    draft = opened([rule(actions=[tag("a"), tag("b")])])
    assert draft.apply("action_remove", ["1", "0", "0"])
    assert stored(draft)[0]["steps"][0]["actions"] == [tag("b")]


# --- the editor: the view ----------------------------------------------------------------


def test_the_editor_names_the_level_and_lists_its_fields(analysis_df):
    draft = opened([rule()], analysis_df)
    got = editor(draft)
    assert got["level"] == {
        "options": [
            {"value": "article", "label": "Article", "checked": True},
            {"value": "order", "label": "Order", "checked": False},
        ],
        "hint": "Checks one order line at a time.",
    }
    assert [g["label"] for g in got["field_groups"]] == ["Common fields", "Other fields in this analysis"]
    assert got["operators"] == CONDITION_OPERATORS

    draft.apply("rule_level", ["1", "order"])
    got = editor(draft)
    assert got["level"]["hint"] == "Checks the whole order. Runs after every article rule."
    assert got["field_groups"][0]["label"] == "Order fields"


@pytest.mark.parametrize(
    "operator, placeholder",
    [
        ("contains", "Value"),
        ("in list", "Value1, Value2, Value3"),
        ("not between", "10-100"),
        ("matches regex", "^SKU-\\d{4}$"),
    ],
)
def test_a_text_value_has_its_operators_placeholder(operator, placeholder):
    draft = opened([rule(conditions=[cond("SKU", operator, "1-2")])])
    value = editor(draft)["steps"][0]["conditions"][0]["value"]
    assert (value["kind"], value["placeholder"]) == ("text", placeholder)


def test_an_empty_check_has_no_value_control():
    draft = opened([rule(conditions=[cond("SKU", "is empty", "")])])
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["kind"] == "none"


@pytest.mark.parametrize(
    "stored_date, shown",
    [("2026-01-30", "2026-01-30"), ("30/01/2026", "2026-01-30"), ("30.01.2026", "2026-01-30"), ("soon", ""), ("", "")],
)
def test_a_date_is_shown_as_the_engine_reads_it(stored_date, shown):
    draft = opened([rule(conditions=[cond("Created_At", "date before", stored_date)])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["value"] == {"kind": "date", "text": shown, "placeholder": "Value", "suggestions": []}
    assert got["problem"] == ("" if shown else NO_DATE)
    assert got["invalid"] is False
    # Shown, not rewritten: the stored text is what Save writes.
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == stored_date


def test_equals_on_a_column_suggests_its_values(analysis_df):
    draft = opened([rule(conditions=[cond("SKU", "equals", "gone")])], analysis_df)
    value = editor(draft)["steps"][0]["conditions"][0]["value"]
    assert value["suggestions"] == ["x", "y"]
    assert value["text"] == "gone"

    draft.apply("cond_operator", ["1", "0", "0", "contains"])
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["suggestions"] == []


def test_suggestions_stop_at_the_limit():
    frame = pd.DataFrame({"Order_Number": [f"#{n:05d}" for n in range(SUGGESTION_LIMIT + 50)]})
    draft = opened([rule(conditions=[cond("Order_Number", "equals", "")])], frame)
    got = editor(draft)["steps"][0]["conditions"][0]["value"]["suggestions"]
    assert len(got) == SUGGESTION_LIMIT
    assert got[0] == "#00000"


@pytest.mark.parametrize(
    "condition, problem",
    [
        (cond("SKU", "matches regex", "("), "Invalid regex syntax"),
        (cond("Quantity", "between", "100-10"),
         "Start is greater than end. Write the smaller number first, for example 10-100."),
        (cond("SKU", "in list", " , "), "No valid items in list"),
        (cond("Quantity", "is greater than", "many"), "Value must be a number"),
    ],
)
def test_a_value_save_refuses_is_marked_and_blocks(condition, problem, analysis_df):
    draft = opened([rule("sizes", conditions=[cond(), condition])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][1]
    assert (got["problem"], got["invalid"]) == (problem, True)
    assert draft.blocker() == "Fix rule “sizes”"
    assert draft.blocker_key() == "rule-1-s0-c1-value"
    assert draft.validate() == (False, [f"Rule “sizes”, step 1, condition 2: {problem}"])
    assert rows(draft)[0]["problem"] == f"Condition 2: {problem}"


def test_a_clean_page_blocks_nothing(analysis_df):
    draft = RulesDraft([rule()], analysis_df)
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])
    assert rows(draft)[0]["problem"] == ""


def test_the_blocker_names_the_first_rule_in_the_list():
    bad = cond("SKU", "matches regex", "(")
    draft = RulesDraft([rule("fine"), rule("", conditions=[bad]), rule("later", conditions=[bad])])
    assert draft.blocker() == "Fix rule 02"
    assert draft.blocker_key() == "rule-2-s0-c0-value"


def test_a_rule_with_steps_says_which_step():
    given = rule("deep")
    given["steps"].append({"conditions": [cond("SKU", "matches regex", "(")], "match": "ALL", "actions": []})
    assert rows(RulesDraft([given]))[0]["problem"] == "Step 2, condition 1: Invalid regex syntax"


def test_a_list_says_how_many_items():
    draft = opened([rule(conditions=[cond("SKU", "in list", "A, B ,C"), cond("SKU", "not in list", "A")])])
    got = editor(draft)["steps"][0]["conditions"]
    assert [(c["problem"], c["hint"]) for c in got] == [("", "3 items"), ("", "1 item")]


def test_an_order_field_on_an_article_rule_never_matches(analysis_df):
    draft = opened([rule(conditions=[cond("item_count", "equals", "2")])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["problem"] == (
        "“item_count” is not a field an article rule can read, so this condition never matches."
    )
    assert got["field_invalid"] is True
    assert got["extra_field"] == {"value": "item_count", "note": NOT_AVAILABLE}
    assert got["invalid"] is False
    assert draft.blocker() is None
    # Kept, not replaced.
    assert stored(draft)[0]["steps"][0]["conditions"][0]["field"] == "item_count"


def test_the_same_holds_with_no_analysis():
    draft = opened([rule(conditions=[cond("item_count", "equals", "2")])])
    assert editor(draft)["steps"][0]["conditions"][0]["field_invalid"] is True


def test_an_unlisted_column_is_not_flagged_with_no_analysis():
    """Settings opens before any analysis runs, and the offered list is then
    only a guess: a client's own column must not be called a never-match."""
    draft = opened([rule(conditions=[cond("Total_Price", "equals", "1")])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert (got["problem"], got["field_invalid"]) == ("", False)
    assert got["extra_field"] == {"value": "Total_Price", "note": ""}


def test_an_unlisted_column_is_flagged_once_an_analysis_says_it_is_not_there(analysis_df):
    draft = opened([rule(conditions=[cond("Total_Price", "equals", "1")])], analysis_df)
    assert editor(draft)["steps"][0]["conditions"][0]["field_invalid"] is True


def test_switching_level_keeps_a_field_the_new_level_does_not_offer(analysis_df):
    draft = opened([rule(level="order", conditions=[cond("item_count", "equals", "2")])], analysis_df)
    assert editor(draft)["steps"][0]["conditions"][0]["extra_field"] is None
    draft.apply("rule_level", ["1", "article"])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["field"] == "item_count" and got["field_invalid"] is True


def test_a_condition_with_no_field_says_so():
    draft = opened([rule(conditions=[{"operator": "equals", "value": "x"}])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert (got["field"], got["problem"], got["extra_field"]) == ("", NO_FIELD, None)


def test_an_unknown_operator_is_listed_and_flagged(analysis_df):
    draft = opened([rule(conditions=[cond("SKU", "sounds like", "x")])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["extra_operator"] == "sounds like"
    assert got["problem"] == (
        "“sounds like” is not an operator this version knows, so this condition never matches."
    )


def test_a_tag_action_suggests_the_configured_tags():
    draft = opened([rule(actions=[tag("BRAND_NEW")])], tag_categories=TAG_CATEGORIES)
    assert draft.configured_tags() == ["EXPRESS", "FRAGILE", "GIFT"]
    action = editor(draft)["steps"][0]["actions"][0]
    assert action["label"] == "Add internal tag"
    assert action["params"] == [
        {
            "name": "value",
            "kind": "suggest",
            "value": "BRAND_NEW",
            "placeholder": "Tag",
            "lead": "",
            "options": ["EXPRESS", "FRAGILE", "GIFT"],
            "extra": None,
            "invalid": False,
        }
    ]


def test_no_tag_categories_means_no_suggestions():
    assert RulesDraft([]).configured_tags() == []


def test_the_hold_has_no_parameter_and_says_what_it_does():
    draft = opened([rule(actions=[{"type": "SET_STATUS", "value": "Not Fulfillable"}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert (action["label"], action["params"], action["hint"]) == ("Hold the order", [], HOLD_HINT)


def test_calculate_draws_its_four_parameters_in_reading_order(analysis_df):
    draft = opened(
        [rule(actions=[{"type": "CALCULATE", "operation": "add", "field1": "Gone", "field2": "SKU", "target": "T"}])],
        analysis_df,
    )
    params = editor(draft)["steps"][0]["actions"][0]["params"]
    assert [(p["name"], p["kind"], p["lead"]) for p in params] == [
        ("field1", "field", ""),
        ("operation", "choice", ""),
        ("field2", "field", ""),
        ("target", "text", "→"),
    ]
    assert params[0]["extra"] == "Gone"
    assert params[2]["extra"] is None
    assert params[1]["options"] == [
        {"value": "add", "label": "plus"},
        {"value": "subtract", "label": "minus"},
        {"value": "multiply", "label": "times"},
        {"value": "divide", "label": "divided by"},
    ]
    assert "Notes" in params[0]["options"]


@pytest.mark.parametrize(
    "action, hint",
    [
        ({"type": "ADD_TAG", "value": "T"}, RETIRED_ONE),
        ({"type": "ADD_ORDER_TAG", "value": "T"}, RETIRED_ONE),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, RETIRED_MANY),
    ],
)
def test_a_retired_action_is_listed_on_its_own_row_and_explains_itself(action, hint):
    draft = opened([rule(actions=[action, tag()])])
    retired, current = editor(draft)["steps"][0]["actions"]
    assert retired["extra_type"] == {"value": action["type"], "label": retired["label"]}
    assert "(retired)" in retired["label"]
    assert (retired["problem"], retired["hint"]) == ("", hint)
    assert (current["extra_type"], current["hint"]) == (None, "")


def test_an_unknown_action_says_it_does_nothing():
    draft = opened([rule(actions=[{"type": "SET_PRIORITY", "value": "High"}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert (action["label"], action["params"], action["problem"]) == ("SET_PRIORITY", [], UNKNOWN_ACTION)
    assert draft.blocker() is None


@pytest.mark.parametrize("quantity", ["", "0", "lots", "10000", "2.5"])
def test_a_bad_quantity_blocks(quantity):
    draft = opened([rule("bonus", actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": quantity}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert action["problem"] == QUANTITY_PROBLEM
    assert [p["invalid"] for p in action["params"]] == [False, True]
    assert draft.blocker_key() == "rule-1-s0-a0-quantity"
    assert draft.validate() == (False, [f"Rule “bonus”, step 1, action 1: {QUANTITY_PROBLEM}"])
    assert rows(draft)[0]["problem"] == f"Action 1: {QUANTITY_PROBLEM}"


@pytest.mark.parametrize("quantity", [1, 9999, "3"])
def test_a_whole_quantity_in_range_does_not(quantity):
    draft = RulesDraft([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": quantity}])])
    assert draft.blocker() is None


# --- Test... ----------------------------------------------------------------------------


def test_test_runs_what_save_would_store_whether_or_not_the_rule_is_on(analysis_df):
    given = rule("r", enabled=False, actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3}])
    draft = RulesDraft([given], analysis_df)
    assert draft.test_config("1") == {"name": "r", "level": "article", "steps": given["steps"]}
    assert rows(draft)[0]["can_test"] is True
    assert rows(draft)[0]["test_title"] == ""


@pytest.mark.parametrize(
    "given, frame, why",
    [
        (rule(), None, TEST_NO_ANALYSIS),
        (rule(), pd.DataFrame(), TEST_NO_ANALYSIS),
        (rule(conditions=[]), "analysis", TEST_NO_CONDITION),
        (rule(conditions=[cond("SKU", "matches regex", "(")]), "analysis", TEST_BLOCKED),
    ],
)
def test_test_says_why_it_cannot_run(given, frame, why, analysis_df):
    draft = RulesDraft([given], analysis_df if isinstance(frame, str) else frame)
    assert draft.test_config("1") is None
    assert (rows(draft)[0]["can_test"], rows(draft)[0]["test_title"]) == (False, why)


def test_test_config_of_a_rule_that_is_not_there(analysis_df):
    assert RulesDraft([rule()], analysis_df).test_config("9") is None
