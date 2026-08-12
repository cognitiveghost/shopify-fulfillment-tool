import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.packing_lists import PackingListsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_packing_lists_page_round_trips_its_configs(qapp):
    configs = [
        {
            "name": "Main",
            "output_filename": "main.xlsx",
            "filters": [{"field": "SKU", "operator": "contains", "value": "AB"}],
            "exclude_skus": ["X1", "X2"],
        }
    ]
    page = PackingListsPage(configs, pd.DataFrame())
    assert page.collect() == {"packing_list_configs": configs}


def test_packing_lists_page_starts_empty_with_no_configs(qapp):
    page = PackingListsPage([], pd.DataFrame())
    assert page.collect() == {"packing_list_configs": []}
