"""RuleEngine correctness (priority: rules accuracy).

Column fixtures use internal (post-analysis) column names since RuleEngine
operates on the final_df produced by shopify_tool.analysis.run_analysis.
"""
import warnings

import pandas as pd
import pytest

from shopify_tool import rules
from shopify_tool.rules import RuleEngine, _op_matches_regex
from shopify_tool.tag_manager import parse_tags


def _df(rows):
    return pd.DataFrame(rows)


def _rule(conditions, actions, match="ALL", level="article", priority=None, name="r"):
    rule = {"name": name, "level": level, "steps": [
        {"conditions": conditions, "match": match, "actions": actions}
    ]}
    if priority is not None:
        rule["priority"] = priority
    return rule


class TestOperatorsCorrectBehavior:
    def test_equals_numeric(self):
        df = _df({"Quantity": [1, 2, 3]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                        [{"type": "ADD_TAG", "value": "TWO"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "TWO", ""]

    def test_contains_case_insensitive_on_string_column(self):
        df = _df({"Product_Name": ["Red Hat", "blue hat", "Scarf"]})
        rules = [_rule([{"field": "Product_Name", "operator": "contains", "value": "HAT"}],
                        [{"type": "ADD_TAG", "value": "HAT_ITEM"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["HAT_ITEM", "HAT_ITEM", ""]

    def test_in_list_case_insensitive_and_trimmed(self):
        df = _df({"Shipping_Provider": ["DHL", " dpd ", "PostOne"]})
        rules = [_rule([{"field": "Shipping_Provider", "operator": "in list", "value": "dhl, DPD"}],
                        [{"type": "ADD_TAG", "value": "PRIORITY_COURIER"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["PRIORITY_COURIER", "PRIORITY_COURIER", ""]

    def test_between_numeric(self):
        df = _df({"Final_Stock": [1, 5, 10, 50]})
        rules = [_rule([{"field": "Final_Stock", "operator": "between", "value": "5-10"}],
                        [{"type": "ADD_TAG", "value": "MID"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "MID", "MID", ""]

    def test_is_empty_and_is_not_empty(self):
        df = _df({"Notes": ["", "hello", None]})
        rules = [_rule([{"field": "Notes", "operator": "is empty", "value": "x"}],
                        [{"type": "ADD_TAG", "value": "EMPTY"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["EMPTY", "", "EMPTY"]

    def test_match_any_vs_all(self):
        df = _df({"A": [1, 1, 0], "B": [0, 1, 0]})
        any_rule = [_rule(
            [{"field": "A", "operator": "equals", "value": 1}, {"field": "B", "operator": "equals", "value": 1}],
            [{"type": "ADD_TAG", "value": "MATCH"}], match="ANY",
        )]
        out = RuleEngine(any_rule).apply(df.copy())
        assert out["Status_Note"].tolist() == ["MATCH", "MATCH", ""]

    def test_unrecognized_operator_condition_fails_the_rule_closed(self):
        # Was documenting the widening bug: a bad condition used to be dropped
        # from the ALL-match, letting the rule fire on the remaining condition
        # alone. It now fails closed instead -- see
        # TestUnresolvableConditionsFailClosed.
        df = _df({"A": [1, 2]})
        rules = [_rule(
            [{"field": "A", "operator": "not_a_real_operator", "value": 1},
             {"field": "A", "operator": "equals", "value": 1}],
            [{"type": "ADD_TAG", "value": "X"}], match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]


class TestRulePriorityAndAccumulation:
    def test_lower_priority_number_runs_first_and_tags_accumulate(self):
        df = _df({"Quantity": [5]})
        rules = [
            _rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                  [{"type": "ADD_TAG", "value": "SECOND"}], priority=2, name="second"),
            _rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                  [{"type": "ADD_TAG", "value": "FIRST"}], priority=1, name="first"),
        ]
        out = RuleEngine(rules).apply(df.copy())
        assert out.loc[0, "Status_Note"] == "FIRST, SECOND"

    def test_add_internal_tag_deduplicates_via_tag_manager(self):
        df = _df({"Order_Number": ["X"], "Quantity": [1], "Internal_Tags": ["[]"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "ADD_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(RuleEngine(rules).rules).apply(df.copy())  # apply twice via re-run
        out = RuleEngine(rules).apply(out)
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]

    def test_add_internal_tag_applies_to_every_line_of_the_matched_order(self):
        # Rule matches only the line with Quantity == 5 (row 0), but
        # Internal_Tags is order-level -- both of order "1001"'s lines must
        # get the tag, not just the matched line.
        df = _df({
            "Order_Number": ["1001", "1001", "1002"],
            "Quantity": [5, 1, 5],
            "Internal_Tags": ["[]", "[]", "[]"],
        })
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                        [{"type": "ADD_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]
        assert parse_tags(out.loc[1, "Internal_Tags"]) == ["GIFT"]  # order 1001's other line
        assert parse_tags(out.loc[2, "Internal_Tags"]) == ["GIFT"]  # order 1002, matched directly

    def test_remove_internal_tag_clears_the_tag_from_every_line_of_the_order(self):
        # Mirror of the ADD case: the rule matches only row 0, but
        # Internal_Tags is order-level, so both of order 1001's lines must
        # lose the tag -- not just the matched line.
        df = _df({
            "Order_Number": ["1001", "1001", "1002"],
            "Quantity": [5, 1, 9],
            "Internal_Tags": ['["GIFT", "FRAGILE"]', '["GIFT", "FRAGILE"]', '["GIFT"]'],
        })
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["FRAGILE"]
        assert parse_tags(out.loc[1, "Internal_Tags"]) == ["FRAGILE"]  # same order
        assert parse_tags(out.loc[2, "Internal_Tags"]) == ["GIFT"]     # unmatched order

    def test_remove_internal_tag_is_a_noop_for_an_absent_tag(self):
        df = _df({"Order_Number": ["X"], "Quantity": [1], "Internal_Tags": ['["GIFT"]']})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "NOT_THERE"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]

    def test_remove_internal_tag_creates_the_column_when_missing(self):
        # _prepare_df_for_actions must build Internal_Tags even for a
        # remove-only rule, or the read at execute time raises KeyError.
        df = _df({"Order_Number": ["X"], "Quantity": [1]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == []

    def test_remove_internal_tag_on_an_order_level_rule_clears_every_line(self):
        # Order-level rules route through the apply_to_first bucket, so
        # REMOVE_INTERNAL_TAG has to expand back out to the whole order the
        # same way ADD_INTERNAL_TAG does.
        df = _df({
            "Order_Number": ["1001", "1001", "1002"],
            "Quantity": [5, 1, 1],
            "Internal_Tags": ['["GIFT"]', '["GIFT"]', '["GIFT"]'],
        })
        rules = [_rule([{"field": "total_quantity", "operator": "equals", "value": 6}],
                        [{"type": "REMOVE_INTERNAL_TAG", "value": "GIFT"}], level="order")]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == []
        assert parse_tags(out.loc[1, "Internal_Tags"]) == []
        assert parse_tags(out.loc[2, "Internal_Tags"]) == ["GIFT"]  # unmatched order

    def test_empty_rules_list_is_noop(self):
        df = _df({"Quantity": [1, 2]})
        out = RuleEngine([]).apply(df.copy())
        pd.testing.assert_frame_equal(out, df)


class TestConfirmedBugs:
    """Each test encodes the behavior a reasonable user would expect; all were
    verified to fail against current shopify_tool/rules.py before being marked
    xfail. These serve as regression markers if/when the bug is fixed."""

    def test_contains_on_numeric_column_does_not_crash(self):
        df = _df({"Quantity": [1, 2, 3]})
        rules = [_rule([{"field": "Quantity", "operator": "contains", "value": "2"}],
                        [{"type": "ADD_TAG", "value": "X"}])]
        out = RuleEngine(rules).apply(df.copy())  # currently raises AttributeError
        assert out["Status_Note"].tolist() == ["", "X", ""]

    def test_greater_than_with_blank_value_does_not_crash(self):
        df = _df({"Final_Stock": [1, 2, 3]})
        rules = [_rule([{"field": "Final_Stock", "operator": "is greater than", "value": ""}],
                        [{"type": "ADD_TAG", "value": "X"}])]
        out = RuleEngine(rules).apply(df.copy())  # currently raises ValueError
        assert out["Status_Note"].tolist() == ["", "", ""]

    def test_not_between_with_malformed_range_matches_nothing(self):
        df = _df({"Final_Stock": [1, 50, 999]})
        rules = [_rule([{"field": "Final_Stock", "operator": "not between", "value": "100-10"}],
                        [{"type": "ADD_TAG", "value": "FLAGGED"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    def test_not_in_list_with_empty_value_matches_nothing(self):
        df = _df({"Shipping_Provider": ["DHL", "DPD", "PostOne"]})
        rules = [_rule([{"field": "Shipping_Provider", "operator": "not in list", "value": ""}],
                        [{"type": "ADD_TAG", "value": "FLAGGED"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    def test_add_order_tag_applies_to_every_row_of_the_order(self):
        df = _df({
            "Order_Number": ["#1", "#1", "#2"],
            "SKU": ["A", "B", "C"],
            "Quantity": [1, 1, 1],
            "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        })
        rules = [_rule(
            [{"field": "Order_Fulfillment_Status", "operator": "equals", "value": "Fulfillable"}],
            [{"type": "ADD_ORDER_TAG", "value": "GIFT"}], level="order",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["GIFT", "GIFT", "GIFT"]

    def test_set_multi_tags_does_not_crash_when_status_note_column_absent(self):
        df = _df({
            "Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
            "Order_Fulfillment_Status": ["Fulfillable"],
        })
        rules = [_rule(
            [{"field": "Order_Fulfillment_Status", "operator": "equals", "value": "Fulfillable"}],
            [{"type": "SET_MULTI_TAGS", "tags": ["A", "B"]}],
        )]
        out = RuleEngine(rules).apply(df.copy())  # currently raises KeyError
        assert "A" in out.loc[0, "Status_Note"]


class TestUnresolvableConditionsFailClosed:
    """An unresolvable condition evaluates to False, it is not dropped.

    Before this change _get_matching_rows skipped conditions it could not
    resolve, so an ALL-match rule fired on its surviving conditions alone and
    tagged more rows than the rule was written to tag.
    """

    def test_all_match_with_unknown_field_does_not_fire(self):
        df = _df({"Order_Type": ["Single", "Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "item_count", "operator": "is greater than", "value": 3}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    def test_any_match_with_unknown_field_still_fires_on_valid_condition(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "no_such_column", "operator": "equals", "value": "x"}],
            [{"type": "ADD_TAG", "value": "YES"}],
            match="ANY",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["YES", ""]

    def test_unknown_operator_fails_closed(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "sounds like", "value": "Single"}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]

    def test_separator_field_fails_closed(self):
        df = _df({"Order_Type": ["Single", "Multi"]})
        rules = [_rule(
            [{"field": "Order_Type", "operator": "equals", "value": "Single"},
             {"field": "--- ORDER-LEVEL FIELDS ---", "operator": "equals", "value": ""}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]

    def test_order_level_rule_agrees_on_unknown_field(self):
        df = _df({
            "Order_Number": ["A", "A"],
            "Quantity": [1, 2],
        })
        rules = [_rule(
            [{"field": "item_count", "operator": "equals", "value": 2},
             {"field": "no_such_column", "operator": "equals", "value": "x"}],
            [{"type": "ADD_TAG", "value": "NOPE"}],
            match="ALL", level="order",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", ""]


class TestOrderRuleLoopRewrite:
    """Order-level rules: same results, without O(rows) slicing per step."""

    def test_multi_order_multi_rule_output_unchanged(self):
        df = _df({
            "Order_Number": ["A", "A", "B", "C", "C", "C"],
            "Quantity": [1, 2, 5, 1, 1, 1],
            "SKU": ["x", "y", "z", "x", "x", "y"],
        })
        rules = [
            _rule([{"field": "item_count", "operator": "is greater than", "value": 2}],
                  [{"type": "ADD_TAG", "value": "BIG"}],
                  level="order", priority=1, name="big"),
            _rule([{"field": "total_quantity", "operator": "is greater than or equal", "value": 5}],
                  [{"type": "ADD_TAG", "value": "HEAVY"}],
                  level="order", priority=2, name="heavy"),
        ]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == [
            "", "", "HEAVY", "BIG", "BIG", "BIG",
        ]

    def test_later_step_sees_earlier_step_action_writes(self):
        """Guards the deliberate re-slice: order_df is re-taken every step."""
        df = _df({
            "Order_Number": ["A", "A"],
            "Quantity": [1, 1],
        })
        rules = [{
            "name": "two-step", "level": "order", "priority": 1,
            "steps": [
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 2}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "FIRST"}]},
                {"conditions": [{"field": "Status_Note", "operator": "contains", "value": "FIRST"}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "SECOND"}]},
            ],
        }]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["FIRST, SECOND", "FIRST, SECOND"]

    def test_first_row_action_targets_one_row_with_duplicate_index_labels(self):
        df = pd.DataFrame(
            {"Order_Number": ["A", "A"], "Quantity": [1, 1]},
            index=[0, 0],
        )
        rules = [_rule([{"field": "item_count", "operator": "equals", "value": 2}],
                       [{"type": "ADD_ORDER_TAG", "value": "ONCE"}],
                       level="order")]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["ONCE", "ONCE"]

    def test_order_step_gates_and_stops(self):
        df = _df({"Order_Number": ["A", "A"], "Quantity": [1, 1]})
        rules = [{
            "name": "gate", "level": "order", "priority": 1,
            "steps": [
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 99}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "NO"}]},
                {"conditions": [{"field": "item_count", "operator": "equals", "value": 2}],
                 "match": "ALL",
                 "actions": [{"type": "ADD_TAG", "value": "ALSO_NO"}]},
            ],
        }]
        out = RuleEngine(rules).apply(df.copy())

        assert out["Status_Note"].tolist() == ["", ""]


class TestRuleCreatedColumnSeeding:
    """A column the engine creates is NaN where the rule did not write.

    Regression: seeding a new COPY_FIELD target with "" made it str dtype on
    pandas 3, so copying a numeric source into it raised TypeError.
    """

    def test_copy_field_numeric_source_into_new_column(self):
        df = _df({"Quantity": [1, 2, 3], "SKU": ["a", "b", "c"]})
        rules = [_rule([{"field": "Quantity", "operator": "is greater than", "value": 1}],
                       [{"type": "COPY_FIELD", "source": "Quantity", "target": "Qty_Copy"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert "Qty_Copy" in out.columns
        assert out.loc[0, "Qty_Copy"] != out.loc[0, "Qty_Copy"]  # NaN: unmatched
        assert out.loc[1, "Qty_Copy"] == 2
        assert out.loc[2, "Qty_Copy"] == 3

    def test_copy_field_string_source_into_new_column(self):
        df = _df({"Quantity": [1, 2, 3], "SKU": ["a", "b", "c"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "COPY_FIELD", "source": "SKU", "target": "SKU_Copy"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert out.loc[1, "SKU_Copy"] == "b"
        assert pd.isna(out.loc[0, "SKU_Copy"])
        assert pd.isna(out.loc[2, "SKU_Copy"])

    def test_copy_field_into_existing_column_leaves_other_rows_alone(self):
        df = _df({"Quantity": [1, 2], "SKU": ["a", "b"], "Note": ["keep", "keep"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "COPY_FIELD", "source": "SKU", "target": "Note"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert out.loc[0, "Note"] == "keep"
        assert out.loc[1, "Note"] == "b"

    def test_calculate_leaves_unmatched_rows_empty(self):
        df = _df({"Quantity": [1, 2], "Price": [10, 20]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 2}],
                       [{"type": "CALCULATE", "operation": "multiply",
                         "field1": "Quantity", "field2": "Price", "target": "Total"}])]
        out = RuleEngine(rules).apply(df.copy())

        assert pd.isna(out.loc[0, "Total"]), "unmatched row must be blank, not 0.0"
        assert out.loc[1, "Total"] == 40


def test_shopify_timestamp_compares_by_its_own_date():
    """D9: the offset is ignored; the date as written is the shop's date."""
    from shopify_tool.rules import _op_date_equals, _parse_date_safe

    late = pd.Series(["2026-01-14 23:30:00 +0200", "2026-01-14T23:30:00+02:00"])
    assert _op_date_equals(late, "2026-01-14").tolist() == [True, True]
    assert _parse_date_safe("2026-01-14 23:30:00 +0200").tzinfo is None


def test_not_contains_is_literal_too():
    from shopify_tool.rules import _op_not_contains

    assert _op_not_contains(pd.Series(["ABC"]), ".").tolist() == [True]


def test_order_rule_negation_on_a_line_field_means_no_line():
    """D2: 'SKU does not equal GIFT' on an order rule = no line is GIFT."""
    df = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "GIFT", "A"],
        "Internal_Tags": ["[]"] * 3,
    })
    rule = {"name": "r", "level": "order", "steps": [{
        "conditions": [{"field": "SKU", "operator": "does not equal", "value": "GIFT"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": "NO_GIFT"}]}]}
    out = RuleEngine([rule]).apply(df)
    tagged = out.loc[out["Internal_Tags"].str.contains("NO_GIFT"), "Order_Number"]
    assert set(tagged) == {"#2"}


def test_execution_order_puts_unprioritised_rules_last_in_list_order():
    a, b, c = {"name": "a"}, {"name": "b", "priority": 5}, {"name": "c"}
    assert [r["name"] for r in RuleEngine.execution_order([a, b, c])] == ["b", "a", "c"]
    assert "priority" not in a  # the caller's dicts are not written to


def test_execution_order_runs_article_rules_before_order_rules():
    o = {"name": "o", "level": "order", "priority": 1}
    a = {"name": "a", "priority": 2}
    assert [r["name"] for r in RuleEngine.execution_order([o, a])] == ["a", "o"]


def _status_frame():
    return pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2"],
        "SKU": ["A", "B", "A"],
        "Quantity": [4, 3, 1],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
        "System_note": ["", "", ""],
        "Internal_Tags": ["[]"] * 3,
    })


def _hold(level, value="Not Fulfillable", name="big; heavy"):
    field = "total_quantity" if level == "order" else "SKU"
    op, val = ("is greater than or equal", "7") if level == "order" else ("equals", "B")
    return {"name": name, "level": level, "steps": [{
        "conditions": [{"field": field, "operator": op, "value": val}],
        "match": "ALL", "actions": [{"type": "SET_STATUS", "value": value}]}]}


@pytest.mark.parametrize("level", ["order", "article"])
def test_set_status_holds_every_line_and_records_the_rule(level):
    out = RuleEngine([_hold(level)]).apply(_status_frame())
    one = out[out["Order_Number"] == "#1"]
    assert (one["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert (one["System_note"] == "Cannot fulfill: Held by rule: big, heavy").all()
    assert out.loc[out["Order_Number"] == "#2", "Order_Fulfillment_Status"].tolist() == ["Fulfillable"]


def test_set_status_twice_records_the_rule_once():
    engine = RuleEngine([_hold("order")])
    out = engine.apply(engine.apply(_status_frame()))
    assert (out.loc[out["Order_Number"] == "#1", "System_note"]
            == "Cannot fulfill: Held by rule: big, heavy").all()


def test_set_status_never_makes_an_order_fulfillable(caplog):
    df = _status_frame()
    df["Order_Fulfillment_Status"] = "Not Fulfillable"
    out = RuleEngine([_hold("order", value="Fulfillable")]).apply(df)
    assert (out["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert (out["System_note"] == "").all()
    assert "SET_STATUS can only hold" in caplog.text


def test_matched_rows_covers_an_order_rules_whole_order():
    df = _status_frame()
    engine = RuleEngine([{"name": "t", "level": "order", "steps": [{
        "conditions": [{"field": "total_quantity", "operator": "is greater than or equal", "value": "7"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": "BIG"}]}]}])
    engine.apply(df)
    assert engine.matched_rows.tolist() == [True, True, False]


def test_regex_with_groups_matches_without_warning():
    # Operators write alternations like ^(01|05); pandas warns that the group
    # is not extracted, which is irrelevant to a boolean match.

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _op_matches_regex(pd.Series(["01-A", "03-B", "05-C"]), "^(01|05)")
    assert result.tolist() == [True, False, True]
    assert not [w for w in caught if issubclass(w.category, UserWarning)]


def _tagging(name, **extra):
    """An article rule that tags every order holding SKU A with its own name."""
    return {"name": name, "level": "article", **extra, "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": name}]}]}


def _all_tags(df):
    return {tag for value in df["Internal_Tags"] for tag in parse_tags(value)}


def test_a_rule_that_is_off_is_skipped():
    out = RuleEngine([_tagging("OFF", enabled=False), _tagging("ON")]).apply(_status_frame())
    assert _all_tags(out) == {"ON"}


@pytest.mark.parametrize("extra", [{}, {"enabled": True}], ids=["no flag", "on"])
def test_a_rule_runs_unless_it_is_stored_off(extra):
    out = RuleEngine([_tagging("T", **extra)]).apply(_status_frame())
    assert _all_tags(out) == {"T"}


def test_an_engine_of_off_rules_changes_nothing():
    df = _status_frame()
    engine = RuleEngine([_tagging("OFF", enabled=False)])
    out = engine.apply(df)
    assert engine.rules == []
    assert _all_tags(out) == set()
    assert not engine.matched_rows.any()


def test_execution_order_still_lists_a_rule_that_is_off():
    """The Rules page orders every rule with it, off or not."""
    off = _tagging("off", enabled=False, priority=1)
    on = _tagging("on", priority=2)
    assert [r["name"] for r in RuleEngine.execution_order([on, off])] == ["off", "on"]


class TestOrderRulesVectorised:
    """Pins the order-level path's results across its vectorisation (AUDIT-08-R1)."""

    FRAME = pd.DataFrame({
        "Order_Number": ["#1", "#1", "#2", "#3", "#3", "#3", None],
        "SKU": ["A", "B", "A", "C", "C", None, "A"],
        "Product_Name": ["Apple", "Box", "Apple", "Cup", "Cup", "Lid", "Apple"],
        "Quantity": [1, 4, 2, 1, 1, 3, 9],
        "Order_Volumetric_Weight": [1.5, 1.5, 0.2, float("nan"), 9.0, 9.0, 9.0],
        "All_No_Packaging": [True, True, False, "true", "true", "true", True],
        "Order_Min_Box": ["S", "S", "M", "L", "L", "L", "S"],
    })

    @pytest.mark.parametrize("condition, tagged", [
        ({"field": "item_count", "operator": "is greater than", "value": "1"}, {"#1", "#3"}),
        ({"field": "total_quantity", "operator": "is greater than or equal", "value": "5"}, {"#1", "#3"}),
        ({"field": "unique_sku_count", "operator": "equals", "value": "2"}, {"#1", "#3"}),  # NaN counts
        ({"field": "max_quantity", "operator": "is greater than", "value": "3"}, {"#1"}),
        ({"field": "order_volumetric_weight", "operator": "is greater than", "value": "1"}, {"#1"}),  # first row
        ({"field": "all_no_packaging", "operator": "equals", "value": "true"}, {"#1", "#3"}),
        ({"field": "order_min_box", "operator": "equals", "value": "M"}, {"#2"}),
        ({"field": "has_sku", "operator": "equals", "value": "A"}, {"#1", "#2"}),
        ({"field": "has_sku", "operator": "does not equal", "value": "A"}, {"#3"}),
        ({"field": "has_product", "operator": "contains", "value": "pp"}, {"#1", "#2"}),
        ({"field": "SKU", "operator": "equals", "value": "C"}, {"#3"}),
        ({"field": "SKU", "operator": "does not equal", "value": "C"}, {"#1", "#2"}),
        ({"field": "no_such_column", "operator": "equals", "value": "x"}, set()),
    ])
    def test_order_rule_matches_the_orders_it_names(self, condition, tagged):
        rule = {"name": "o", "level": "order", "conditions": [condition],
                "actions": [{"type": "ADD_TAG", "value": "hit"}]}
        out = RuleEngine([rule]).apply(self.FRAME.copy())
        assert set(out.loc[out["Status_Note"].fillna("").str.contains("hit"), "Order_Number"]) == tagged

    def test_order_steps_gate_on_the_step_before(self):
        rule = {"name": "g", "level": "order", "steps": [
            {"conditions": [{"field": "item_count", "operator": "is greater than", "value": "1"}],
             "match": "ALL", "actions": [{"type": "ADD_TAG", "value": "s1"}]},
            {"conditions": [{"field": "has_sku", "operator": "equals", "value": "B"}],
             "match": "ALL", "actions": [{"type": "ADD_TAG", "value": "s2"}]}]}
        out = RuleEngine([rule]).apply(self.FRAME.copy())
        notes = out.groupby("Order_Number")["Status_Note"].first()
        assert notes.to_dict() == {"#1": "s1, s2", "#2": "", "#3": "s1"}

    def test_added_products_keep_order_then_rule_order(self):
        rules = [{"name": n, "level": "order", "priority": p,
                  "conditions": [{"field": "has_sku", "operator": "equals", "value": "A"}],
                  "actions": [{"type": "ADD_PRODUCT", "sku": g, "quantity": 1}]}
                 for n, p, g in [("r1", 1, "G1"), ("r2", 2, "G2")]]
        out = RuleEngine(rules).apply(self.FRAME.copy())
        added = out.iloc[len(self.FRAME):]
        assert list(zip(added["Order_Number"], added["SKU"])) == [
            ("#1", "G1"), ("#1", "G2"), ("#2", "G1"), ("#2", "G2")]

    def test_matched_rows_cover_every_line_of_a_matched_order(self):
        rule = {"name": "o", "level": "order",
                "conditions": [{"field": "has_sku", "operator": "equals", "value": "B"}],
                "actions": [{"type": "ADD_TAG", "value": "hit"}]}
        engine = RuleEngine([rule])
        engine.apply(self.FRAME.copy())
        assert engine.matched_rows.tolist() == [True, True, False, False, False, False, False]


class TestParseDates:
    """One parse per format over the column, same answers as the per-value parser (AUDIT-08-R2)."""

    VALUES = ("2024-01-30", "30/01/2024", "30.01.2024", "2026-10-01 10:00:00", "2026-10-01 10:00:00 +0200",
              "2026-10-01T10:00:00+02:00", "2026-10-01T10:00:00Z", " 2024-01-30 ", "2026-10-01T10:00:00",
              "2026-10-01 10:00:00+0200", "2024-02-30", "1/2/2024", "", None, float("nan"), "not a date",
              pd.Timestamp("2024-01-30 08:00"))

    @pytest.mark.parametrize("value", VALUES)
    def test_parse_dates_matches_the_single_value_parser(self, value):
        got = rules._parse_dates(pd.Series([value], dtype=object)).iloc[0]
        want = rules._parse_date_safe(value)
        assert (pd.isna(got) and want is None) or got == want

    def test_mixed_offsets_parse_to_the_date_as_written(self):
        s = pd.Series(["2026-03-28 23:30:00 +0200", "2026-03-30 00:30:00 +0300"], name="Created_At")
        assert rules._parse_dates(s).tolist() == [pd.Timestamp("2026-03-28 23:30"), pd.Timestamp("2026-03-30 00:30")]


def test_the_page_order_is_the_run_order():
    rules_list = [{"name": "A", "enabled": False}, {"name": "B"}, {"name": "C", "priority": 1000}]
    assert [r["name"] for r in RuleEngine.execution_order(rules_list)] == ["B", "C", "A"]
    assert [r["name"] for r in RuleEngine(rules_list).rules] == ["B", "C"]


RULE_LISTS = [
    [{"name": "a1"}, {"name": "o1", "level": "order"}, {"name": "a2", "priority": 5}],
    [{"name": "x", "enabled": False}, {"name": "y"}, {"name": "z", "priority": 1001},
     {"name": "w", "level": "order", "priority": 1}],
    [{"name": "p", "priority": 1000}, {"name": "q"}, {"name": "r", "enabled": False, "priority": 2},
     {"name": "s"}],
    [{"name": "n1", "enabled": False}, {"name": "n2", "enabled": False}, {"name": "n3"},
     {"name": "o2", "level": "order"}, {"name": "o3", "level": "order", "enabled": False}],
]


@pytest.mark.parametrize("rules_list", RULE_LISTS)
def test_enabled_rules_list_in_the_order_the_engine_runs_them(rules_list):
    page = [r["name"] for r in RuleEngine.execution_order(rules_list) if r.get("enabled", True) is not False]
    assert page == [r["name"] for r in RuleEngine(rules_list).rules]


TEXT = pd.Series([" DHL ", "dhl", "Dhl-Express", None, "UPS"])


@pytest.mark.parametrize("op, value, want", [
    ("equals", "dhl ", [True, True, False, False, False]),
    ("does not equal", " DHL", [False, False, True, True, True]),
    ("starts with", " dhl", [True, True, True, False, False]),
    ("ends with", "HL ", [True, True, False, False, False]),
    ("contains", " Express", [False, False, True, False, False]),
    ("does not contain", "dhl", [False, False, False, True, True]),
    ("in list", "dhl , ups", [True, True, False, False, True]),
    ("not in list", "DHL", [False, False, True, True, True]),
])
def test_text_operators_ignore_case_and_spaces(op, value, want):
    assert getattr(rules, rules.OPERATOR_MAP[op])(TEXT, value).tolist() == want


def test_a_product_added_from_a_set_line_is_not_a_component():
    """AUDIT-08-R5: the added row copied the set line's tracking fields."""
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [2], "Original_SKU": ["SET-1"],
                       "Original_Quantity": [1], "Is_Set_Component": [True]})
    rule = {"name": "gift", "level": "article", "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
            "actions": [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]}
    added = RuleEngine([rule]).apply(df).iloc[-1]
    assert (added["Original_SKU"], added["Original_Quantity"], added["Is_Set_Component"]) == ("GIFT", 1, False)
