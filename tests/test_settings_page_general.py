import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.general import GeneralPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def sample_settings():
    return {
        "stock_csv_delimiter": "|",
        "orders_csv_delimiter": ";",
        "low_stock_threshold": 12,
        "repeat_detection_days": 30,
    }


def test_general_page_round_trips_its_settings(qapp):
    settings = sample_settings()
    expected = dict(settings)
    page = GeneralPage(settings)
    # Compare against a copy taken before construction: the page holds the
    # live dict, so comparing collect() to `settings` compares an object to
    # itself and passes for any implementation.
    assert page.collect() == {"settings": expected}


def test_general_page_writes_every_key_it_owns(qapp):
    """The live-dict contract means a key the page stops writing survives in
    the dict it was handed -- so round-trip tests cannot see the drop. Detach
    the page from that dict and only what collect() actively writes remains."""
    page = GeneralPage(sample_settings())
    page._settings = {}

    assert set(page.collect()["settings"]) == {
        "stock_csv_delimiter", "orders_csv_delimiter",
        "low_stock_threshold", "repeat_detection_days",
    }


def test_general_page_falls_back_to_defaults(qapp):
    page = GeneralPage({})
    assert page.collect()["settings"] == {
        "stock_csv_delimiter": ";",
        "orders_csv_delimiter": ",",
        "low_stock_threshold": 5,
        "repeat_detection_days": 1,
    }
