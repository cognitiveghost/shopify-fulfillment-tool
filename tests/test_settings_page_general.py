import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.general import GeneralPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_general_page_round_trips_its_settings(qapp):
    settings = {
        "stock_csv_delimiter": "|",
        "orders_csv_delimiter": ";",
        "low_stock_threshold": 12,
        "repeat_detection_days": 30,
    }
    page = GeneralPage(settings)
    assert page.collect() == {"settings": settings}


def test_general_page_falls_back_to_defaults(qapp):
    page = GeneralPage({})
    assert page.collect()["settings"] == {
        "stock_csv_delimiter": ";",
        "orders_csv_delimiter": ",",
        "low_stock_threshold": 5,
        "repeat_detection_days": 1,
    }
