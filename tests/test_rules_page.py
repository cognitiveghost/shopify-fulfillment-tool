"""RulesPage field vocabularies and level awareness."""
import pandas as pd
import pytest

from gui.settings.rules import RulesPage
from shopify_tool.rules import RuleEngine


@pytest.fixture
def analysis_df():
    return pd.DataFrame({
        "Order_Number": ["A", "B"],
        "SKU": ["x", "y"],
        "Quantity": [1, 2],
    })


def _order_field_names():
    return set(RuleEngine.ORDER_LEVEL_FIELDS.keys())


class TestLevelAwareFields:
    def test_article_level_omits_order_fields(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = set(page.get_available_rule_fields(level="article"))
        assert not (fields & _order_field_names())
        assert "--- ORDER-LEVEL FIELDS ---" not in fields

    def test_order_level_includes_every_engine_order_field(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = set(page.get_available_rule_fields(level="order"))
        assert _order_field_names() <= fields

    def test_article_level_still_offers_dataframe_columns(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        fields = page.get_available_rule_fields(level="article")
        assert "SKU" in fields
        assert "Quantity" in fields


class TestLevelSwitchPreservesSavedField:
    def test_switching_to_article_keeps_unknown_field_selected(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "order",
            "steps": [{
                "conditions": [{"field": "item_count", "operator": "equals", "value": "2"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        refs = page.rule_widgets[0]
        refs["level_combo"].setCurrentText("article")

        combo = refs["steps"][0]["conditions"][0]["field"]
        assert combo.currentText() == "item_count"
        assert "border" in combo.styleSheet()  # preserved, but flagged
        assert page.collect()["rules"][0]["steps"][0]["conditions"][0]["field"] == "item_count"


class TestUnresolvableFieldIsFlagged:
    def test_order_field_on_article_rule_is_flagged(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "item_count", "operator": "equals", "value": "2"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        # Asserted before calling the helper: the flag has to be there on load,
        # which is the only moment the user sees a rule they did not just edit.
        assert "border" in cond_refs["field"].styleSheet()
        assert page._check_field_resolvable(cond_refs) is False

    def test_order_field_on_article_rule_is_flagged_without_an_analysis(self, qtbot):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "item_count", "operator": "equals", "value": "2"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], pd.DataFrame())
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert "border" in cond_refs["field"].styleSheet()

    def test_unlisted_column_is_not_flagged_without_an_analysis(self, qtbot):
        """Settings opens before any analysis runs, and the offered field list
        is then only a hardcoded guess -- a real client column must not be
        called a never-match on the strength of that guess."""
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "Total_Price", "operator": "equals", "value": "1"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], pd.DataFrame())
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert cond_refs["field"].styleSheet() == ""

    def test_real_column_is_not_flagged(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        cond_refs = page.rule_widgets[0]["steps"][0]["conditions"][0]
        assert page._check_field_resolvable(cond_refs) is True
        assert cond_refs["field"].styleSheet() == ""


class TestCollapsibleRuleCards:
    def _rule(self, name="r"):
        return {
            "name": name, "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    def test_loaded_rules_start_collapsed(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        assert page.rule_widgets[0]["body"].isVisibleTo(page) is False

    def test_added_rule_starts_expanded(self, qtbot, analysis_df):
        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        page.add_rule_widget()
        assert page.rule_widgets[0]["body"].isVisibleTo(page) is True

    def test_summary_reports_counts(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        text = page.rule_widgets[0]["summary_label"].text()
        assert "article" in text
        assert "1 step" in text
        assert "1 condition" in text
        assert "1 action" in text

    def test_collect_is_unaffected_by_collapse_state(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        collapsed = page.collect()
        page.rule_widgets[0]["body"].setVisible(True)
        assert page.collect() == collapsed


class TestFilterAndReorder:
    def _rule(self, name, level="article"):
        return {
            "name": name, "level": level,
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    def test_filter_hides_non_matching_rules(self, qtbot, analysis_df):
        page = RulesPage([self._rule("alpha"), self._rule("beta")], analysis_df)
        qtbot.addWidget(page)
        page._filter_rules("alp")
        assert page.rule_widgets[0]["group_box"].isVisibleTo(page) is True
        assert page.rule_widgets[1]["group_box"].isVisibleTo(page) is False

    def test_empty_filter_shows_everything(self, qtbot, analysis_df):
        page = RulesPage([self._rule("alpha"), self._rule("beta")], analysis_df)
        qtbot.addWidget(page)
        page._filter_rules("alp")
        page._filter_rules("")
        assert page.rule_widgets[1]["group_box"].isVisibleTo(page) is True

    def test_move_up_skips_over_other_level(self, qtbot, analysis_df):
        page = RulesPage(
            [self._rule("a1", "article"),
             self._rule("o1", "order"),
             self._rule("a2", "article")],
            analysis_df,
        )
        qtbot.addWidget(page)
        page._move_rule_up(page.rule_widgets[2])
        names = [r["name_edit"].text() for r in page.rule_widgets]
        assert names == ["a2", "o1", "a1"]

    def test_first_of_its_level_cannot_move_up(self, qtbot, analysis_df):
        page = RulesPage(
            [self._rule("a1", "article"), self._rule("o1", "order")],
            analysis_df,
        )
        qtbot.addWidget(page)
        assert page.rule_widgets[0]["up_btn"].isEnabled() is False
        assert page.rule_widgets[1]["up_btn"].isEnabled() is False

    def test_last_of_its_level_cannot_move_down(self, qtbot, analysis_df):
        page = RulesPage(
            [self._rule("a1", "article"), self._rule("o1", "order")],
            analysis_df,
        )
        qtbot.addWidget(page)
        assert page.rule_widgets[0]["down_btn"].isEnabled() is False


class TestValidationFeedbackPlacement:
    """The message has to land somewhere the user can actually read it."""

    @staticmethod
    def _rule(field="SKU", operator="matches regex", value="["):
        return {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": field, "operator": operator, "value": value}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }

    @staticmethod
    def _condition(page):
        return page.rule_widgets[0]["steps"][0]["conditions"][0]

    def test_message_sits_below_the_row_not_inside_it(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)

        page._perform_validation(cond)

        label = cond["feedback_label"]
        assert label.text() == "Invalid regex syntax"
        assert not label.isHidden()
        # Not one more cell in the horizontal row, past the delete button.
        assert cond["row_layout"].indexOf(label) == -1
        outer = cond["widget"].layout()
        assert outer.itemAt(0).layout() is cond["row_layout"]
        assert outer.itemAt(1).widget() is label

    def test_changing_the_operator_drops_a_stale_message(self, qtbot, analysis_df):
        page = RulesPage([self._rule()], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)
        page._perform_validation(cond)
        assert cond["feedback_label"].text()

        cond["op"].setCurrentText("contains")

        assert cond["feedback_label"].text() == ""
        assert cond["feedback_label"].isHidden()

    def test_unresolvable_field_reports_without_a_value_widget(self, qtbot, analysis_df):
        """The 'never match' message is about the field, not the value box, so a
        row with no value widget must still show it. No UI path reaches this
        state today -- the empty-check branch that would create it is dead code
        (design doc section 5, finding A) -- so the state is set directly here, to keep
        the guard from being reintroduced when that branch is fixed."""
        page = RulesPage([self._rule(field="item_count", operator="equals", value="2")], analysis_df)
        qtbot.addWidget(page)
        cond = self._condition(page)
        cond["feedback_label"].clear()
        cond["feedback_label"].hide()
        cond["value_widget"] = None

        assert page._check_field_resolvable(cond) is False

        assert "never match" in cond["feedback_label"].text()
        assert not cond["feedback_label"].isHidden()


class TestLegacyActionRoundTrip:
    """A rule using one of the three retired actions must survive an
    open-and-save with its type and value byte-identical. The editor flags
    it; the editor never rewrites it."""

    @pytest.mark.parametrize("legacy_type", ["ADD_TAG", "ADD_ORDER_TAG"])
    def test_legacy_action_survives_collect_untouched(self, qtbot, analysis_df, legacy_type):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": legacy_type, "value": "KEEP_ME"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action["type"] == legacy_type
        assert action["value"] == "KEEP_ME"

    def test_legacy_set_multi_tags_survives_collect_untouched(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "SET_MULTI_TAGS", "tags": ["A", "B"]}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        action = page.collect()["rules"][0]["steps"][0]["actions"][0]
        assert action["type"] == "SET_MULTI_TAGS"
        assert action["value"] == "A, B"

    def test_a_new_action_row_does_not_offer_the_retired_types(self, qtbot, analysis_df):
        from gui.settings.fields import LEGACY_ACTION_TYPES

        page = RulesPage([], analysis_df)
        qtbot.addWidget(page)
        page.add_rule_widget()
        rule_refs = page.rule_widgets[0]
        # add_action_row takes the *step* refs -- it appends to their
        # "actions_layout" / "actions". A blank rule always has exactly one step.
        page.add_action_row(rule_refs["steps"][0])

        combo = rule_refs["steps"][0]["actions"][-1]["type"]
        offered = {combo.itemText(i) for i in range(combo.count())}
        assert not (offered & set(LEGACY_ACTION_TYPES))
        assert "ADD_INTERNAL_TAG" in offered
        assert "REMOVE_INTERNAL_TAG" in offered

    def test_the_retired_type_is_offered_only_on_the_row_that_uses_it(self, qtbot, analysis_df):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [{"type": "ADD_TAG", "value": "T"}],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)

        combo = page.rule_widgets[0]["steps"][0]["actions"][0]["type"]
        assert combo.currentText() == "ADD_TAG"
        assert "ADD_TAG" in {combo.itemText(i) for i in range(combo.count())}


class TestLegacyActionFlag:
    def _page_with_action(self, qtbot, analysis_df, action):
        rule = {
            "name": "r", "level": "article",
            "steps": [{
                "conditions": [{"field": "SKU", "operator": "equals", "value": "x"}],
                "match": "ALL",
                "actions": [action],
            }],
        }
        page = RulesPage([rule], analysis_df)
        qtbot.addWidget(page)
        return page, page.rule_widgets[0]["steps"][0]["actions"][0]

    def test_legacy_action_row_explains_itself(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_TAG", "value": "T"})
        label = refs["legacy_label"]
        assert not label.isHidden()
        assert "Status_Note" in label.text()
        assert "ADD_INTERNAL_TAG" in label.text()

    def test_set_multi_tags_says_one_action_per_tag(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "SET_MULTI_TAGS", "tags": ["A", "B"]})
        assert "one ADD_INTERNAL_TAG per tag" in refs["legacy_label"].text()

    def test_current_action_row_is_not_flagged(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_INTERNAL_TAG", "value": "GIFT"})
        assert refs["legacy_label"].isHidden()
        assert refs["legacy_label"].text() == ""

    def test_switching_off_a_legacy_type_clears_the_flag(self, qtbot, analysis_df):
        page, refs = self._page_with_action(
            qtbot, analysis_df, {"type": "ADD_TAG", "value": "T"})
        refs["type"].setCurrentText("ADD_INTERNAL_TAG")
        assert refs["legacy_label"].isHidden()
