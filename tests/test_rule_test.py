"""run_rule_test: what the Test panel says about one rule (phase 8 spec section 6).

Plain Python on a small analysis-shaped frame. No widget and no Chromium.
"""

import pandas as pd
import pytest

from gui.settings.rule_test import (
    FAILED,
    HEADS,
    NO_CHANGE,
    NO_CHANGE_NOTE,
    NO_MATCH,
    failed_view,
    run_rule_test,
    running_view,
)
from shopify_tool.rules import RuleEngine


def frame(rows):
    """Analysis-shaped: (order, sku, quantity) lines, all Fulfillable."""
    return pd.DataFrame(
        {
            "Order_Number": [r[0] for r in rows],
            "SKU": [r[1] for r in rows],
            "Quantity": [r[2] for r in rows],
            "Stock": [10] * len(rows),
            "Product_Name": [f"P-{r[1]}" for r in rows],
            "Order_Fulfillment_Status": ["Fulfillable"] * len(rows),
            "System_note": [""] * len(rows),
            "Status_Note": [""] * len(rows),
            "Internal_Tags": ["[]"] * len(rows),
        }
    )


ORDERS = [("#1", "A", 4), ("#1", "B", 3), ("#2", "B", 1), ("#3", "A", 1)]


def cond(field, operator, value=""):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(conditions, actions, level="article", match="ALL", name="r", **extra):
    return {
        "name": name,
        "level": level,
        **extra,
        "steps": [{"conditions": conditions, "match": match, "actions": actions}],
    }


SKU_A = [cond("SKU", "equals", "A")]


def listed(view):
    return [(row["order"], row["why"], row["change"]) for row in view["rows"]]


def test_it_counts_orders_and_lists_what_matched_and_what_changed():
    view = run_rule_test(rule(SKU_A, [tag("priority")], name="VIP"), frame(ORDERS), "2026-09-30_1")
    assert view["status"] == "done"
    assert view["title"] == "Test “VIP”"
    assert view["intro"] == {
        "lead": "Runs this rule, as edited, against the analysis in ",
        "session": "2026-09-30_1",
        "tail": ". Orders aren’t changed.",
    }
    assert (view["matched"], view["total"]) == ("2", "of 3 orders match")
    assert view["heads"] == HEADS == ["Order", "Matched on", "Change"]
    assert listed(view) == [("#1", "SKU: A", "+ priority"), ("#3", "SKU: A", "+ priority")]
    assert [row["changed"] for row in view["rows"]] == [True, True]
    assert (view["more"], view["empty"], view["note"], view["message"]) == ("", "", "", "")


def test_the_analysis_is_left_as_it_was():
    df = frame(ORDERS)
    before = df.copy()
    run_rule_test(rule(SKU_A, [tag(), {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]), df)
    pd.testing.assert_frame_equal(df, before)


def test_with_no_session_name_it_says_the_last_analysis():
    view = run_rule_test(rule(SKU_A, [tag()]), frame(ORDERS))
    assert view["intro"] == {
        "lead": "Runs this rule, as edited, against the last analysis",
        "session": "",
        "tail": ". Orders aren’t changed.",
    }


def test_a_rule_that_is_off_still_runs():
    view = run_rule_test(rule(SKU_A, [tag()], enabled=False), frame(ORDERS))
    assert view["matched"] == "2"


def test_only_the_first_five_are_listed():
    df = frame([(f"#{n}", "A", 1) for n in range(1, 9)])
    view = run_rule_test(rule(SKU_A, [tag()]), df)
    assert (view["matched"], view["total"]) == ("8", "of 8 orders match")
    assert [row["order"] for row in view["rows"]] == ["#1", "#2", "#3", "#4", "#5"]
    assert view["more"] == "and 3 more"


def test_no_match_says_so():
    view = run_rule_test(rule([cond("SKU", "equals", "Z")], [tag()]), frame(ORDERS))
    assert (view["matched"], view["rows"], view["empty"], view["more"]) == ("0", [], NO_MATCH, "")


def test_one_order_is_singular():
    view = run_rule_test(rule(SKU_A, [tag()]), frame([("#1", "A", 1)]))
    assert (view["matched"], view["total"]) == ("1", "of 1 order matches")


def test_a_frame_with_no_order_numbers_counts_its_lines():
    df = frame(ORDERS).drop(columns="Order_Number")
    view = run_rule_test(rule(SKU_A, [{"type": "COPY_FIELD", "source": "SKU", "target": "Code"}]), df)
    assert (view["matched"], view["total"]) == ("2", "of 4 orders match")
    assert [row["order"] for row in view["rows"]] == ["0", "3"]


def test_an_analysis_with_a_blank_order_number_and_list_cells_is_still_tested():
    df = frame([*ORDERS, (None, "A", 2)])
    df["Lot_Details"] = [[{"lot": 1}], [], [{"lot": 1}, {"lot": 2}], [], []]
    df[7] = "x"  # a column whose name is not text
    view = run_rule_test(rule(SKU_A, [{"type": "COPY_FIELD", "source": "SKU", "target": 7}]), df)
    assert (view["status"], view["matched"], view["total"]) == ("done", "3", "of 4 orders match")
    assert listed(view) == [
        ("#1", "SKU: A", "7 → A"),
        ("#3", "SKU: A", "7 → A"),
        ("", "SKU: A", "7 → A"),
    ]


# --- Matched on --------------------------------------------------------------


def test_an_article_rule_shows_the_lines_that_matched():
    view = run_rule_test(rule([cond("Quantity", "is greater than", "2")], [tag()]), frame(ORDERS))
    assert listed(view) == [("#1", "Quantity: 4; 3", "+ T")]


def test_an_order_rule_shows_every_line_of_the_order():
    view = run_rule_test(rule(SKU_A, [tag()], level="order"), frame(ORDERS))
    assert listed(view)[0] == ("#1", "SKU: A; B", "+ T")


def test_a_numeric_order_field_shows_what_the_engine_worked_out():
    conditions = [cond("total_quantity", "is greater than", "5"), cond("item_count", "equals", "2")]
    view = run_rule_test(rule(conditions, [tag()], level="order"), frame(ORDERS))
    assert listed(view) == [("#1", "total_quantity: 7 · item_count: 2", "+ T")]


def test_a_yes_or_no_order_field_shows_what_it_was_asked():
    view = run_rule_test(rule([cond("has_sku", "equals", "B")], [tag()], level="order"), frame(ORDERS))
    assert [row["why"] for row in view["rows"]] == ["has_sku: B", "has_sku: B"]


def test_a_field_is_named_once_and_more_than_three_values_trail_off():
    df = frame([("#1", sku, 1) for sku in "ABCDE"])
    conditions = [cond("SKU", "is not empty"), cond("SKU", "does not equal", "Z")]
    view = run_rule_test(rule(conditions, [tag()]), df)
    assert listed(view) == [("#1", "SKU: A; B; C; …", "+ T")]


def test_an_empty_cell_reads_empty():
    df = frame(ORDERS)
    df["Notes"] = [None, "", "x", "y"]
    view = run_rule_test(rule([cond("Notes", "is empty")], [tag()]), df)
    assert listed(view) == [("#1", "Notes: empty", "+ T")]


def test_a_field_the_engine_cannot_read_is_left_out():
    conditions = [cond("SKU", "equals", "A"), cond("Nope", "equals", "x")]
    view = run_rule_test(rule(conditions, [tag()], match="ANY"), frame(ORDERS))
    assert [row["why"] for row in view["rows"]] == ["SKU: A", "SKU: A"]


def test_every_step_of_a_rule_is_read():
    stepped = rule(SKU_A, [tag("one")])
    stepped["steps"].append(
        {"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": [tag("two")]}
    )
    view = run_rule_test(stepped, frame(ORDERS))
    assert listed(view) == [
        ("#1", "SKU: A · Quantity: 4", "+ one, + two"),
        ("#3", "SKU: A · Quantity: 1", "+ one"),
    ]


# --- Change ------------------------------------------------------------------


def test_removing_a_tag():
    df = frame(ORDERS)
    df["Internal_Tags"] = '["old", "keep"]'
    view = run_rule_test(rule(SKU_A, [{"type": "REMOVE_INTERNAL_TAG", "value": "old"}, tag("new")]), df)
    assert view["rows"][0]["change"] == "+ new, − old"


def test_a_hold_reads_held_and_hides_its_reason_code():
    hold = rule(SKU_A, [{"type": "SET_STATUS", "value": "Not Fulfillable"}], name="big")
    view = run_rule_test(hold, frame(ORDERS))
    assert [row["change"] for row in view["rows"]] == ["Held", "Held"]


@pytest.mark.parametrize(
    "action, change",
    [
        ({"type": "COPY_FIELD", "source": "SKU", "target": "Code"}, "Code → A"),
        ({"type": "COPY_FIELD", "source": "SKU", "target": "Product_Name"}, "Product_Name → A"),
        (
            {"type": "CALCULATE", "operation": "multiply", "field1": "Quantity", "field2": "Stock", "target": "Total"},
            "Total → 40.0",
        ),
        ({"type": "ADD_TAG", "value": "VIP"}, "Status_Note → VIP"),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, "Status_Note → A, B"),
        ({"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 2}, "+ GIFT ×2"),
        ({"type": "ALERT_NOTIFICATION", "message": "look", "severity": "info"}, NO_CHANGE),
    ],
)
def test_each_action_reads_as_its_change(action, change):
    view = run_rule_test(rule(SKU_A, [action]), frame(ORDERS))
    assert view["rows"][0]["change"] == change


def test_several_changes_are_joined():
    actions = [tag("gift"), {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]
    view = run_rule_test(rule(SKU_A, actions), frame(ORDERS))
    assert view["rows"][0]["change"] == "+ gift, + GIFT ×1"


def test_an_order_the_saved_rules_already_changed_reads_no_change():
    tagging = rule(SKU_A, [tag("T")])
    analysed = RuleEngine([tagging]).apply(frame(ORDERS))
    view = run_rule_test(tagging, analysed)
    assert view["matched"] == "2"
    assert [(row["change"], row["changed"]) for row in view["rows"]] == [(NO_CHANGE, False)] * 2
    assert view["note"] == NO_CHANGE_NOTE == (
        "No change: the analysis already has the saved rules applied."
    )


# --- the other two states ----------------------------------------------------


def test_running_says_how_many_orders():
    view = running_view(rule(SKU_A, [tag()], name="VIP"), frame(ORDERS), "S1")
    assert (view["status"], view["message"]) == ("running", "Testing 3 orders…")
    assert view["title"] == "Test “VIP”"
    assert view["intro"]["session"] == "S1"
    assert view["rows"] == []
    assert running_view(rule(SKU_A, []), frame([("#1", "A", 1)]))["message"] == "Testing 1 order…"


def test_failed_says_where_to_look():
    view = failed_view(rule(SKU_A, [tag()], name="VIP"), "S1")
    assert (view["status"], view["message"]) == ("failed", FAILED)
    assert FAILED == "The rule test didn’t finish. Details are in Logs."


def test_every_state_has_the_same_keys():
    r, df = rule(SKU_A, [tag()]), frame(ORDERS)
    assert set(running_view(r, df)) == set(failed_view(r)) == set(run_rule_test(r, df))
