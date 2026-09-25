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
        "stock_csv_delimiter",
        "orders_csv_delimiter",
        "low_stock_threshold",
    }


def test_general_page_falls_back_to_defaults(qapp):
    page = GeneralPage({})
    assert page.collect()["settings"] == {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }


def test_repeat_window_setting_is_gone_but_a_saved_value_survives(qapp):
    """Repeat compares sessions now (ADR 0012). The page no longer offers the
    window, and an old saved value is left in the config untouched."""
    page = GeneralPage(sample_settings())
    assert not hasattr(page, "repeat_days_input")
    assert page.collect()["settings"]["repeat_detection_days"] == 30


def test_auto_and_tab_round_trip(qapp):
    settings = {
        **sample_settings(),
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "\t",
    }
    expected = dict(settings)
    assert GeneralPage(settings).collect() == {"settings": expected}


def test_unknown_delimiter_survives_a_round_trip(qapp):
    settings = {**sample_settings(), "orders_csv_delimiter": "::"}
    expected = dict(settings)
    assert GeneralPage(settings).collect() == {"settings": expected}


def test_delimiters_are_offered_as_a_list(qapp):
    page = GeneralPage({})
    assert [page.orders_delimiter_combo.itemData(i) for i in range(5)] == [
        "auto",
        ",",
        ";",
        "\t",
        "|",
    ]
