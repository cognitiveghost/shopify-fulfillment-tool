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
        assert page._check_field_resolvable(cond_refs) is False
        assert "border" in cond_refs["field"].styleSheet()

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
