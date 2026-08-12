import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.rules import RulesPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_rules_page_round_trips_its_rules(qapp):
    rules = [
        {
            "name": "Flag big orders",
            "priority": 1,
            "level": "order",
            "steps": [
                {
                    "conditions": [
                        {"field": "item_count", "operator": "is greater than", "value": "5"}
                    ],
                    "match": "ALL",
                    "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                }
            ],
        }
    ]
    page = RulesPage(rules, pd.DataFrame())
    assert page.collect() == {"rules": rules}


def test_rules_page_starts_empty_with_no_rules(qapp):
    page = RulesPage([], pd.DataFrame())
    assert page.collect() == {"rules": []}
