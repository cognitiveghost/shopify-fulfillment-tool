"""Widget-level tests for Analysis Results 1b (spec §10 tests 9-11)."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.order_detail_pane import OrderDetailPane
from gui.orders_view import order_lines, orders_frame


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def lines_df():
    return pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "Destination_Country": "DE",
             "SKU": "AAA", "Product_Name": "Widget", "Quantity": 2,
             "System_note": "", "Notes": "leave at door", "Internal_Tags": "[]"},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "Shipping_Provider": "DHL", "Destination_Country": "DE",
             "SKU": "BBB", "Product_Name": "Gadget", "Quantity": 1,
             "System_note": "", "Notes": "leave at door", "Internal_Tags": "[]"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "Shipping_Provider": "DPD", "Destination_Country": "FR",
             "SKU": "CCC", "Product_Name": "Doohickey", "Quantity": 4,
             "System_note": "Cannot fulfill: insufficient stock for CCC",
             "Notes": "", "Internal_Tags": "[]"},
        ]
    )


def test_pane_shows_the_orders_lines(app, lines_df):
    """Spec §10 test 11."""
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)

    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))

    assert "1001" in pane.header_label.text()
    assert pane.lines_table.model().rowCount() == 2
    assert pane.tag_panel.selected_order == "1001"


def test_pane_shows_the_blocker_only_when_there_is_one(app, lines_df):
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)

    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))
    assert not pane.blocker_label.isVisible() or pane.blocker_label.text() == ""

    pane.set_order("1002", orders.loc["1002"], order_lines(lines_df, "1002"))
    assert "insufficient stock for CCC" in pane.blocker_label.text()


def test_pane_clear_empties_everything(app, lines_df):
    pane = OrderDetailPane()
    orders = orders_frame(lines_df).set_index("Order_Number", drop=False)
    pane.set_order("1001", orders.loc["1001"], order_lines(lines_df, "1001"))

    pane.clear()

    assert pane.lines_table.model() is None or pane.lines_table.model().rowCount() == 0
    assert pane.tag_panel.selected_order is None


@pytest.fixture
def main_window(app):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


def test_order_frame_row_count_reaches_the_view(app, lines_df, main_window):
    """Spec §10 test 9."""
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    assert main_window.tableView.model().rowCount() == 2  # orders, not lines


def test_filtering_by_a_sku_keeps_its_order_visible(app, lines_df, main_window):
    """Spec §10 test 10: SKU is not a column any more, but still findable."""
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    main_window.proxy_model.set_text_filter("BBB")

    assert main_window.tableView.model().rowCount() == 1


def test_search_column_is_hidden_from_the_view(app, lines_df, main_window):
    from gui.orders_view import SEARCH_COLUMN

    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    frame = main_window.proxy_model.sourceModel()._dataframe
    column = frame.columns.get_loc(SEARCH_COLUMN)
    assert main_window.tableView.isColumnHidden(column)


def test_selecting_a_row_fills_the_pane_and_the_selection_helper(
    app, lines_df, main_window
):
    """Spec §10 test 11, at the window level."""
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    main_window.tableView.selectRow(0)

    assert "1001" in main_window.order_detail_pane.header_label.text()
    assert main_window.order_detail_pane.lines_table.model().rowCount() == 2

    selected = main_window.selection_helper.get_selected_orders_data()
    assert set(selected["Order_Number"]) == {"1001"}


def test_clearing_the_selection_clears_the_pane(app, lines_df, main_window):
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)
    main_window.tableView.selectRow(0)

    main_window.tableView.clearSelection()

    assert main_window.order_detail_pane.header_label.text() == "No order selected"
    assert not main_window.selection_helper.has_selection()


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


def _with_config(main_window):
    """An in-memory TableConfig. load_config() would need a real client on disk."""
    from gui.table_config_manager import TableConfig

    main_window.table_config_manager._current_config = TableConfig()
    main_window.table_config_manager._current_client_id = None
    return main_window.table_config_manager


# --- Stage C review regressions -------------------------------------------
# Each of these covers a surface that kept addressing the *line* frame after
# the view switched to the order frame.


def test_filtering_by_a_named_column_searches_that_column(app, lines_df, main_window):
    """The combo carries column names; positions differ between the frames."""
    main_window.analysis_results_df = lines_df
    main_window._update_all_views()

    selector = main_window.filter_column_selector
    index = selector.findData("Shipping_Provider")
    assert index > 0, "Shipping_Provider must be offered as a filter column"
    selector.setCurrentIndex(index)
    main_window.filter_input.setText("DHL")
    main_window.filter_table()

    assert main_window.tableView.model().rowCount() == 1

    # A line-level column is not offered: it lives in the pane now.
    assert selector.findData("SKU") == -1


def test_hiding_a_column_from_the_header_menu_hides_that_column(
    app, lines_df, main_window
):
    """The header section index must resolve against the order frame."""
    from gui.orders_view import SEARCH_COLUMN

    _with_config(main_window)
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    view_df = main_window.ui_manager.results_view_frame()
    assert SEARCH_COLUMN not in view_df.columns

    column_name = "Shipping_Provider"
    section = view_df.columns.get_loc(column_name)
    main_window.table_config_manager.toggle_column_visibility(
        main_window.tableView, column_name, view_df
    )

    assert main_window.tableView.isColumnHidden(section)


def test_selection_survives_a_data_refresh(app, lines_df, main_window):
    """Every tag add and status change rebuilds the model underneath."""
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)
    main_window.tableView.selectRow(0)
    assert set(main_window.selection_helper.get_selected_orders_data()["Order_Number"]) == {"1001"}

    main_window.ui_manager.update_results_table(lines_df)

    selected = main_window.selection_helper.get_selected_orders_data()
    assert set(selected["Order_Number"]) == {"1001"}
    assert "1001" in main_window.order_detail_pane.header_label.text()


def test_the_pane_tag_dropdown_is_populated(app, lines_df, main_window):
    """load_predefined_tags lost its only caller when toggle_tag_panel went."""
    main_window.active_profile_config = {
        "tag_categories": {"Priority": {"tags": ["RUSH", "VIP"]}}
    }
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)

    combo = main_window.tag_management_panel.predefined_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert any("RUSH" in label for label in labels), labels


def test_the_pane_hides_a_line_column_the_client_hid(app, lines_df, main_window):
    """Spec §4: the saved config keeps its meaning, split across two surfaces."""
    _with_config(main_window)
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.update_results_table(lines_df)
    main_window.table_config_manager.set_column_visibility(
        main_window.tableView, "Product_Name", False, main_window.ui_manager.results_view_frame()
    )

    lines = main_window._pane_lines("1001")

    assert "Product_Name" not in lines.columns
    assert "SKU" in lines.columns


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
