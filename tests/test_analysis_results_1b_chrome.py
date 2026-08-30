"""Spec §9 tests 10-14: the restyled Analysis Results screen."""

import pandas as pd
import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from gui.orders_view import HIDDEN_COLUMNS
from gui.status_edge_delegate import StatusEdgeDelegate


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lines_df():
    """3 orders / 4 lines / 8 items. 1 fulfillable, 2 blocked, 1003 a repeat."""
    return pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "AAA", "Quantity": 2,
             "System_note": "", "Internal_Tags": "[]"},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "BBB", "Quantity": 1,
             "System_note": "", "Internal_Tags": "[]"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "SKU": "CCC", "Quantity": 4,
             "System_note": "Cannot fulfill: insufficient stock for CCC",
             "Internal_Tags": "[]"},
            {"Order_Number": "1003", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DHL", "SKU": "DDD", "Quantity": 1,
             "System_note": "Repeat customer; Cannot fulfill: out of stock",
             "Internal_Tags": "[]"},
        ]
    )


@pytest.fixture
def main_window(app):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


@pytest.fixture
def loaded(main_window, lines_df):
    """The window with the frame loaded, exactly as _update_all_views does it.

    The in-memory TableConfig is load-bearing, not decoration: without it
    apply_config_to_view() returns early on "No config loaded", so the second
    hide loop in results_view_frame() -- the one that exists *because* the
    config re-walks the frame -- is never reached and the hidden-column test
    passes on the first loop alone.
    """
    from gui.table_config_manager import TableConfig

    main_window.table_config_manager._current_config = TableConfig()
    main_window.table_config_manager._current_client_id = None
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)
    main_window.ui_manager.update_kpi_strip()
    return main_window


def test_both_tables_paint_the_status_edge(loaded):
    assert isinstance(loaded.tableView.itemDelegate(), StatusEdgeDelegate)
    lines = loaded.order_detail_pane.lines_table
    assert isinstance(lines.itemDelegate(), StatusEdgeDelegate)


def test_the_derived_columns_are_hidden_from_the_table(loaded):
    orders_df = loaded.orders_df
    for name in HIDDEN_COLUMNS:
        assert name in orders_df.columns
        column = orders_df.columns.get_loc(name)
        assert loaded.tableView.isColumnHidden(column)


def test_the_derived_columns_are_not_offered_as_filter_scopes(loaded):
    selector = loaded.filter_column_selector
    offered = {selector.itemData(i) for i in range(selector.count())}
    for name in HIDDEN_COLUMNS:
        assert name not in offered


def test_the_kpi_strip_reads_em_dashes_before_any_load(main_window):
    for card in main_window.kpi_cards.values():
        assert card.value_label.text() == "—"


def test_the_kpi_strip_counts_orders_fulfillable_blocked_and_items(loaded):
    """The fixture: 3 orders, 1 fulfillable, 2 blocked, 4 lines summing to 8."""
    cards = loaded.kpi_cards
    assert cards["orders"].value_label.text() == "3"
    assert cards["fulfillable"].value_label.text() == "1"
    assert cards["blocked"].value_label.text() == "2"
    assert cards["items"].value_label.text() == "8"


def test_the_summary_label_is_gone(main_window):
    assert not hasattr(main_window, "summary_label")


def test_filter_input_is_the_filter_bars_search_field(main_window):
    assert main_window.filter_input is main_window.filter_bar.search_field


def test_the_count_shows_the_total_with_no_filter(loaded):
    assert loaded.filter_bar.count_label.text() == "3 orders"


def test_the_count_narrows_while_a_filter_is_active(loaded):
    loaded.filter_input.setText("DPD")
    loaded.filter_table()
    assert loaded.filter_bar.count_label.text() == "1 of 3 orders"


def test_the_clear_button_is_gone(main_window):
    assert not hasattr(main_window, "clear_filter_button")


def test_the_overflow_holds_the_five_screen_level_actions(main_window):
    actions = main_window.results_overflow_button.menu().actions()
    assert [a for a in actions if not a.isSeparator()] == [
        main_window.add_product_button_tab2,
        main_window.configure_columns_button_tab2,
        main_window.settings_button_tab2,
        main_window.undo_button,
        main_window.theme_toggle_btn,
    ]
    assert all(isinstance(a, QAction) for a in actions if not a.isSeparator())


def test_the_existing_enable_calls_still_drive_the_overflow(main_window):
    """main_window_pyside.py:662-701 sets these; QAction takes setEnabled too."""
    main_window.settings_button_tab2.setEnabled(False)
    assert not main_window.settings_button_tab2.isEnabled()
    main_window.settings_button_tab2.setEnabled(True)
    assert main_window.settings_button_tab2.isEnabled()


def test_generate_reports_stays_a_button_bound_to_the_command_bar(main_window):
    from PySide6.QtWidgets import QPushButton

    assert isinstance(main_window.generate_reports_button_tab2, QPushButton)
    assert main_window.generate_reports_button_tab2.isHidden()


def test_the_selection_bar_is_hidden_with_nothing_selected(loaded):
    loaded._update_selection_bar_state()
    assert loaded.selection_bar.isHidden()


def test_selecting_a_row_shows_the_bar_and_names_the_selection(loaded):
    loaded.tableView.selectRow(0)
    loaded._update_selection_bar_state()
    assert not loaded.selection_bar.isHidden()
    assert "order" in loaded.selection_bar.count_label.text()


def test_select_all_is_gone_and_ctrl_a_does_the_job(loaded):
    assert not hasattr(loaded, "_on_bulk_select_all")
    loaded.tableView.selectAll()
    orders, _items = loaded.selection_helper.get_selection_summary()
    assert orders == 3


def test_the_bulk_operations_toolbar_module_is_gone():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("gui.bulk_operations_toolbar")
