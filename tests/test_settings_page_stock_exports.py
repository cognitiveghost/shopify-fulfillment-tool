import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.stock_exports import StockExportsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_stock_exports_page_round_trips_its_configs(qapp):
    configs = [
        {
            "name": "Daily",
            "output_filename": "daily.csv",
            "filters": [{"field": "Tags", "operator": "==", "value": "hot"}],
        }
    ]
    page = StockExportsPage(configs, pd.DataFrame())
    assert page.collect() == {"stock_export_configs": configs}


def test_stock_exports_page_starts_empty_with_no_configs(qapp):
    page = StockExportsPage([], pd.DataFrame())
    assert page.collect() == {"stock_export_configs": []}
