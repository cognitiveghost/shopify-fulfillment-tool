"""RuleEngine correctness (priority: rules accuracy).

Column fixtures use internal (post-analysis) column names since RuleEngine
operates on the final_df produced by shopify_tool.analysis.run_analysis.
"""
import pandas as pd

from shopify_tool.rules import RuleEngine
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

    def test_later_rule_set_status_overwrites_earlier_one(self):
        df = _df({"Quantity": [5], "Order_Fulfillment_Status": ["Fulfillable"]})
        rules = [
            _rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                  [{"type": "SET_STATUS", "value": "A"}], priority=1),
            _rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                  [{"type": "SET_STATUS", "value": "B"}], priority=2),
        ]
        out = RuleEngine(rules).apply(df.copy())
        assert out.loc[0, "Order_Fulfillment_Status"] == "B"

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
