"""Widget-level tests for Analysis Results 1b (spec §10 tests 9-11)."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.orders_view import orders_frame


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(app):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


def test_the_workaround_code_is_gone():
    """These existed only to fake order-level behaviour over a line table."""
    import importlib

    for module in ("gui.checkbox_delegate", "gui.order_group_delegate"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_no_bulk_mode_and_no_tag_panel_toggle(app, main_window):
    assert not hasattr(main_window, "toggle_bulk_mode")
    assert not hasattr(main_window, "toggle_tag_panel")
    assert not hasattr(main_window, "toggle_bulk_mode_btn")
    assert not hasattr(main_window, "toggle_tags_panel_btn")


def test_a_lot_batch_number_is_still_findable(app):
    """cell_search_text, not cell_display_text: a lot cell renders as "1 lot"."""
    import json

    df = pd.DataFrame(
        [
            {
                "Order_Number": "1001",
                "SKU": "AAA",
                "Lot_Details": json.dumps([{"batch": "B7", "expiry": "2026-12-30"}]),
            },
            {"Order_Number": "1002", "SKU": "BBB", "Lot_Details": "[]"},
        ]
    )

    orders = orders_frame(df)
    from gui.orders_view import SEARCH_COLUMN

    assert "B7" in orders.loc[orders["Order_Number"] == "1001", SEARCH_COLUMN].iloc[0]
