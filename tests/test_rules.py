"""RuleEngine correctness (priority: rules accuracy).

Column fixtures use internal (post-analysis) column names since RuleEngine
operates on the final_df produced by shopify_tool.analysis.run_analysis.
"""
import pandas as pd
import pytest

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

    def test_unrecognized_operator_condition_is_skipped_not_fatal(self):
        # Per _get_matching_rows: field/operator not found -> condition skipped,
        # remaining conditions still apply (documented current behavior).
        df = _df({"A": [1, 2]})
        rules = [_rule(
            [{"field": "A", "operator": "not_a_real_operator", "value": 1},
             {"field": "A", "operator": "equals", "value": 1}],
            [{"type": "ADD_TAG", "value": "X"}], match="ALL",
        )]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["X", ""]


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
        df = _df({"Quantity": [1], "Internal_Tags": ["[]"]})
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 1}],
                        [{"type": "ADD_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(RuleEngine(rules).rules).apply(df.copy())  # apply twice via re-run
        out = RuleEngine(rules).apply(out)
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]

    def test_empty_rules_list_is_noop(self):
        df = _df({"Quantity": [1, 2]})
        out = RuleEngine([]).apply(df.copy())
        pd.testing.assert_frame_equal(out, df)


class TestConfirmedBugs:
    """Each test encodes the behavior a reasonable user would expect; all were
    verified to fail against current shopify_tool/rules.py before being marked
    xfail. These serve as regression markers if/when the bug is fixed."""

    @pytest.mark.xfail(strict=True, reason="BUG: 'contains'/'starts with'/'ends with' "
                        "raise an uncaught AttributeError on numeric-dtype columns "
                        "instead of degrading to all-False like other operators.")
    def test_contains_on_numeric_column_does_not_crash(self):
        df = _df({"Quantity": [1, 2, 3]})
        rules = [_rule([{"field": "Quantity", "operator": "contains", "value": "2"}],
                        [{"type": "ADD_TAG", "value": "X"}])]
        out = RuleEngine(rules).apply(df.copy())  # currently raises AttributeError
        assert out["Status_Note"].tolist() == ["", "X", ""]

    @pytest.mark.xfail(strict=True, reason="BUG: 'is greater than'/'is less than'/etc "
                        "call float(rule_val) unguarded; a blank/non-numeric rule value "
                        "crashes the whole analysis instead of matching zero rows.")
    def test_greater_than_with_blank_value_does_not_crash(self):
        df = _df({"Final_Stock": [1, 2, 3]})
        rules = [_rule([{"field": "Final_Stock", "operator": "is greater than", "value": ""}],
                        [{"type": "ADD_TAG", "value": "X"}])]
        out = RuleEngine(rules).apply(df.copy())  # currently raises ValueError
        assert out["Status_Note"].tolist() == ["", "", ""]

    @pytest.mark.xfail(strict=True, reason="BUG: 'not between' with a malformed/reversed "
                        "range string (e.g. start > end) degrades the base 'between' "
                        "check to all-False, and negating all-False matches EVERY row "
                        "instead of zero rows.")
    def test_not_between_with_malformed_range_matches_nothing(self):
        df = _df({"Final_Stock": [1, 50, 999]})
        rules = [_rule([{"field": "Final_Stock", "operator": "not between", "value": "100-10"}],
                        [{"type": "ADD_TAG", "value": "FLAGGED"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    @pytest.mark.xfail(strict=True, reason="BUG: 'not in list' with an empty/blank rule "
                        "value degrades the base 'in list' check to all-False, and "
                        "negating all-False matches EVERY row instead of zero rows -- "
                        "a blank filter value in the UI silently tags the entire dataset.")
    def test_not_in_list_with_empty_value_matches_nothing(self):
        df = _df({"Shipping_Provider": ["DHL", "DPD", "PostOne"]})
        rules = [_rule([{"field": "Shipping_Provider", "operator": "not in list", "value": ""}],
                        [{"type": "ADD_TAG", "value": "FLAGGED"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert out["Status_Note"].tolist() == ["", "", ""]

    @pytest.mark.xfail(strict=True, reason="BUG: an order-level rule's ADD_ORDER_TAG "
                        "action only stamps the FIRST row of a multi-line order, not "
                        "every row -- despite the action name implying order-wide "
                        "application (only the literal 'ADD_TAG' type gets apply-to-all "
                        "treatment in the order-level branch).")
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

    @pytest.mark.xfail(strict=True, reason="BUG: SET_MULTI_TAGS writes to Status_Note "
                        "but is missing from _prepare_df_for_actions' needed-columns "
                        "scan, so a rules config using ONLY SET_MULTI_TAGS crashes with "
                        "KeyError('Status_Note') when that column doesn't already exist.")
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
