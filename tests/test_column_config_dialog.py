"""Regression test: Manage Table Columns list must group columns under
category header rows (grouped-list redesign, Phase 5 Item 1) without
breaking the underlying visible/order round-trip. Root cause risk: switching
list items to show display names instead of raw column names would break
every call site that read item.text() as the column name -- this locks in
item.data(Qt.UserRole) as the source of truth instead.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.column_config_dialog import _CATEGORY_HEADER_MARKER, ColumnConfigPanel
from gui.table_config_manager import TableConfig


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _make_panel(columns, locked_columns=None):
    config = TableConfig(
        visible_columns={col: True for col in columns},
        column_order=columns,
        locked_columns=locked_columns if locked_columns is not None else ["Order_Number"],
    )
    tcm = Mock()
    tcm.get_current_config.return_value = config
    tcm.get_current_view_name.return_value = "Default"
    tcm.list_views.return_value = ["Default"]
    tcm.pm.load_client_config.return_value = {}
    main_window = Mock()
    main_window.current_client_id = "TESTCLIENT"
    main_window.analysis_results_df = None
    return ColumnConfigPanel(tcm, main_window=main_window)


def test_columns_are_grouped_under_category_headers():
    panel = _make_panel(["Order_Number", "SKU", "Fulfillable", "Tags"])

    categories_seen = [
        panel.column_list.item(i).text()
        for i in range(panel.column_list.count())
        if panel.column_list.item(i).data(Qt.UserRole) == _CATEGORY_HEADER_MARKER
    ]

    assert categories_seen == ["Order Info", "Product Info", "Fulfillment", "Tags & Lot"]


def test_get_config_from_ui_skips_header_rows():
    panel = _make_panel(["Order_Number", "SKU", "Fulfillable"])

    config = panel._get_config_from_ui()

    assert set(config.column_order) == {"Order_Number", "SKU", "Fulfillable"}
    assert _CATEGORY_HEADER_MARKER not in config.column_order


def test_move_up_is_blocked_at_the_top_of_a_category_group():
    panel = _make_panel(["SKU", "Product_Name"])  # both "Product Info"

    # row 0 = "Product Info" header, row 1 = SKU, row 2 = Product_Name.
    # Product_Name moving up swaps with SKU -- allowed.
    panel.column_list.setCurrentRow(2)
    panel._on_move_up()
    assert panel.column_list.item(1).data(Qt.UserRole) == "Product_Name"

    # Now at row 1, directly under the header -- moving up again must no-op
    # instead of swapping with the header row.
    panel._on_move_up()
    assert panel.column_list.item(1).data(Qt.UserRole) == "Product_Name"


def test_move_up_is_blocked_above_a_locked_column(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    panel = _make_panel(["Order_Number", "Name"])  # both "Order Info"

    # row 0 = header, row 1 = Order_Number (locked), row 2 = Name.
    panel.column_list.setCurrentRow(2)
    panel._on_move_up()

    assert panel.column_list.item(1).data(Qt.UserRole) == "Order_Number"
    assert panel.column_list.item(2).data(Qt.UserRole) == "Name"


def test_locked_column_tooltip_still_shows_raw_name():
    panel = _make_panel(["Order_Number"])

    item = panel.column_list.item(1)  # row 0 = "Order Info" header
    assert item.data(Qt.UserRole) == "Order_Number"
    assert "Order_Number" in item.toolTip()


def test_search_matches_the_display_name_the_user_can_see():
    """"Name" renders as "Order Name" -- searching the visible label has to
    find it, or the box no longer matches what the list shows.
    """
    panel = _make_panel(["Order_Number", "Name"])

    panel._on_search_changed("order name")

    # row 0 = "Order Info" header, row 1 = Order_Number, row 2 = Name.
    assert panel.column_list.item(2).isHidden() is False


def test_search_still_matches_the_raw_column_name():
    panel = _make_panel(["Order_Number", "Name"])

    panel._on_search_changed("order_number")

    assert panel.column_list.item(1).isHidden() is False
    assert panel.column_list.item(2).isHidden() is True


def test_the_panels_apply_button_is_not_a_primary():
    """The panel is embedded twice, and marking its Apply primary is wrong in both.

    In ColumnConfigDialog the panel's Apply is hidden in favour of the button
    box's; on Settings -> Column Configuration it would sit beside the settings
    window's own Save, giving that page two primaries.
    """
    panel = _make_panel(["Order_Number", "SKU"])
    assert panel.apply_button.property("role") is None


def test_apply_is_the_column_dialogs_one_primary():
    from PySide6.QtWidgets import QPushButton

    from gui.column_config_dialog import ColumnConfigDialog

    tcm = Mock()
    tcm.get_current_config.return_value = TableConfig(
        visible_columns={"Order_Number": True},
        column_order=["Order_Number"],
        locked_columns=["Order_Number"],
    )
    tcm.get_current_view_name.return_value = "Default"
    tcm.list_views.return_value = ["Default"]
    tcm.pm.load_client_config.return_value = {}
    main_window = Mock()
    main_window.current_client_id = "TESTCLIENT"
    main_window.analysis_results_df = None

    dialog = ColumnConfigDialog(tcm, main_window=main_window)
    try:
        primaries = [
            b.text() for b in dialog.findChildren(QPushButton)
            if b.property("role") == "primary"
        ]
        # Reset/Cancel/Apply carry no AcceptRole, so the shared dialog helper
        # cannot reach Apply -- it is marked directly.
        assert primaries == ["Apply"]
    finally:
        dialog.deleteLater()
