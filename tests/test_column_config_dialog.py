"""
Tests for Column Configuration Dialog

Tests the UI dialog for managing table column visibility and order.

Phase 4 of table customization feature.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtCore import Qt

from gui.column_config_dialog import ColumnConfigDialog
from gui.table_config_manager import TableConfig, TableConfigManager


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["ABC123", "DEF456", "GHI789"],
        "Product_Name": ["Product A", "Product B", "Product C"],
        "Quantity": [1, 2, 3],
        "Has_SKU": [np.nan, np.nan, np.nan],  # Empty column
        "Stock": [10, 20, 30],
        "Warehouse_Name": ["WH1", "WH2", "WH3"]
    })


@pytest.fixture
def mock_profile_manager():
    """Create a mock ProfileManager."""
    pm = MagicMock()
    pm.load_client_config.return_value = {
        "ui_settings": {
            "table_view": {
                "version": 1,
                "active_view": "Default",
                "views": {
                    "Default": {
                        "visible_columns": {
                            "Order_Number": True,
                            "SKU": True,
                            "Product_Name": True,
                            "Quantity": True,
                            "Has_SKU": False,
                            "Stock": True,
                            "Warehouse_Name": True
                        },
                        "column_order": ["Order_Number", "SKU", "Product_Name", "Quantity", "Has_SKU", "Stock", "Warehouse_Name"],
                        "column_widths": {},
                        "auto_hide_empty": True,
                        "locked_columns": ["Order_Number"]
                    },
                    "Custom View": {
                        "visible_columns": {
                            "Order_Number": True,
                            "SKU": True,
                            "Product_Name": False,
                            "Quantity": True,
                            "Has_SKU": False,
                            "Stock": True,
                            "Warehouse_Name": False
                        },
                        "column_order": ["Order_Number", "SKU", "Quantity", "Product_Name", "Has_SKU", "Stock", "Warehouse_Name"],
                        "column_widths": {},
                        "auto_hide_empty": True,
                        "locked_columns": ["Order_Number"]
                    }
                }
            }
        }
    }
    pm.save_client_config = MagicMock()
    return pm


@pytest.fixture
def mock_main_window(sample_dataframe):
    """Create a mock MainWindow."""
    mw = MagicMock()
    mw.current_client_id = "M"
    mw.analysis_results_df = sample_dataframe
    mw.tableView = MagicMock()
    return mw


@pytest.fixture
def table_config_manager(mock_main_window, mock_profile_manager):
    """Create a TableConfigManager for testing."""
    tcm = TableConfigManager(mock_main_window, mock_profile_manager)
    # Load default config
    tcm.load_config("M")
    return tcm


@pytest.fixture
def dialog(qapp, table_config_manager, mock_main_window):
    """Create a ColumnConfigDialog for testing."""
    dialog = ColumnConfigDialog(table_config_manager, parent=None, main_window=mock_main_window)
    yield dialog
    dialog.close()


class TestColumnConfigDialogInitialization:
    """Test dialog initialization."""

    def test_dialog_created(self, dialog):
        """Test that dialog is created successfully."""
        assert dialog is not None
        assert dialog.windowTitle() == "Manage Table Columns"

    def test_dialog_has_all_widgets(self, dialog):
        """Test that all expected widgets are created."""
        # Search input
        assert hasattr(dialog, 'search_input')
        assert dialog.search_input is not None

        # Column list
        assert hasattr(dialog, 'column_list')
        assert dialog.column_list is not None

        # Reorder buttons
        assert hasattr(dialog, 'up_button')
        assert hasattr(dialog, 'down_button')

        # Visibility controls
        assert hasattr(dialog, 'show_all_button')
        assert hasattr(dialog, 'hide_all_button')
        assert hasattr(dialog, 'auto_hide_checkbox')

        # View management
        assert hasattr(dialog, 'view_combo')
        assert hasattr(dialog, 'save_view_button')
        assert hasattr(dialog, 'delete_view_button')

        # Reset and dialog buttons
        assert hasattr(dialog, 'reset_button')
        assert hasattr(dialog, 'cancel_button')
        assert hasattr(dialog, 'apply_button')

    def test_dialog_loads_columns(self, dialog, sample_dataframe):
        """Test that columns are loaded into the list."""
        assert dialog.column_list.count() == len(sample_dataframe.columns)

        # Check that Order_Number is first and bold (locked)
        first_item = dialog.column_list.item(0)
        assert first_item.text() == "Order_Number"
        assert first_item.font().bold()

    def test_dialog_loads_views(self, dialog):
        """Test that views are loaded into the combo box."""
        assert dialog.view_combo.count() >= 1
        assert dialog.view_combo.findText("Default") >= 0

    def test_auto_hide_checkbox_state(self, dialog):
        """Test that auto-hide checkbox reflects current config."""
        config = dialog.table_config_manager.get_current_config()
        assert dialog.auto_hide_checkbox.isChecked() == config.auto_hide_empty


class TestColumnSearch:
    """Test column search/filter functionality."""

    def test_search_shows_matching_columns(self, dialog):
        """Test that search filters columns correctly."""
        # Initial state: all visible
        visible_count = sum(1 for i in range(dialog.column_list.count())
                          if not dialog.column_list.item(i).isHidden())
        assert visible_count == dialog.column_list.count()

        # Search for "SKU"
        dialog.search_input.setText("SKU")

        # Check that only matching columns are visible
        visible_items = []
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            if not item.isHidden():
                visible_items.append(item.text())

        assert "SKU" in visible_items
        assert "Has_SKU" in visible_items
        assert "Product_Name" not in visible_items

    def test_search_case_insensitive(self, dialog):
        """Test that search is case-insensitive."""
        dialog.search_input.setText("sku")

        visible_items = []
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            if not item.isHidden():
                visible_items.append(item.text())

        assert "SKU" in visible_items
        assert "Has_SKU" in visible_items

    def test_search_clear_shows_all(self, dialog):
        """Test that clearing search shows all columns."""
        # Search for something
        dialog.search_input.setText("SKU")

        # Clear search
        dialog.search_input.clear()

        # All columns should be visible
        visible_count = sum(1 for i in range(dialog.column_list.count())
                          if not dialog.column_list.item(i).isHidden())
        assert visible_count == dialog.column_list.count()


class TestColumnVisibilityToggle:
    """Test column visibility checkbox functionality."""

    def test_check_column_changes_state(self, dialog):
        """Test that checking/unchecking a column updates state."""
        # Find a non-locked column
        item = dialog.column_list.item(1)  # SKU
        assert item.text() == "SKU"

        original_state = item.checkState()

        # Toggle state
        new_state = Qt.Unchecked if original_state == Qt.Checked else Qt.Checked
        item.setCheckState(new_state)

        assert item.checkState() == new_state

    def test_cannot_uncheck_locked_column(self, dialog):
        """Test that locked columns cannot be unchecked."""
        # Order_Number is locked
        item = dialog.column_list.item(0)
        assert item.text() == "Order_Number"

        # Try to uncheck (should remain checked due to handler)
        dialog._is_loading = False  # Ensure handler is active

        # Mock the warning dialog to prevent it from showing
        with patch.object(QMessageBox, 'warning'):
            item.setCheckState(Qt.Unchecked)

        # Verify it's checked again
        assert item.checkState() == Qt.Checked

    def test_show_all_checks_all_columns(self, dialog):
        """Test that Show All button checks all columns."""
        # Uncheck some columns first
        for i in range(1, 3):
            item = dialog.column_list.item(i)
            item.setCheckState(Qt.Unchecked)

        # Click Show All
        dialog._on_show_all()

        # All columns should be checked
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            assert item.checkState() == Qt.Checked

    def test_hide_all_unchecks_except_locked(self, dialog):
        """Test that Hide All button unchecks all except locked columns."""
        # Click Hide All
        dialog._on_hide_all()

        # Check results
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            if item.text() == "Order_Number":
                # Locked column should remain checked
                assert item.checkState() == Qt.Checked
            else:
                # Other columns should be unchecked
                assert item.checkState() == Qt.Unchecked


class TestColumnReorder:
    """Test column reordering functionality."""

    def test_move_up_reorders_column(self, dialog):
        """Test that Move Up button reorders columns."""
        # Select third item
        dialog.column_list.setCurrentRow(2)
        third_item_text = dialog.column_list.item(2).text()

        # Move up
        dialog._on_move_up()

        # Check that item moved to position 1
        assert dialog.column_list.item(1).text() == third_item_text
        assert dialog.column_list.currentRow() == 1

    def test_move_down_reorders_column(self, dialog):
        """Test that Move Down button reorders columns."""
        # Select second item
        dialog.column_list.setCurrentRow(1)
        second_item_text = dialog.column_list.item(1).text()

        # Move down
        dialog._on_move_down()

        # Check that item moved to position 2
        assert dialog.column_list.item(2).text() == second_item_text
        assert dialog.column_list.currentRow() == 2

    def test_cannot_move_locked_column(self, dialog):
        """Test that locked columns cannot be moved."""
        # Select Order_Number (locked)
        dialog.column_list.setCurrentRow(0)

        # Try to move down (should show warning and not move)
        with patch.object(QMessageBox, 'warning'):
            dialog._on_move_down()

        # Verify Order_Number is still at position 0
        assert dialog.column_list.item(0).text() == "Order_Number"

    def test_cannot_move_to_locked_position(self, dialog):
        """Test that columns cannot be moved to position 0 (locked)."""
        # Select second item
        dialog.column_list.setCurrentRow(1)
        second_item_text = dialog.column_list.item(1).text()

        # Try to move up (should show warning and not move)
        with patch.object(QMessageBox, 'warning'):
            dialog._on_move_up()

        # Verify item is still at position 1
        assert dialog.column_list.item(1).text() == second_item_text

    def test_move_up_button_disabled_at_top(self, dialog):
        """Test that Move Up button is disabled at top."""
        dialog.column_list.setCurrentRow(0)
        assert not dialog.up_button.isEnabled()

    def test_move_down_button_disabled_at_bottom(self, dialog):
        """Test that Move Down button is disabled at bottom."""
        last_row = dialog.column_list.count() - 1
        dialog.column_list.setCurrentRow(last_row)
        assert not dialog.down_button.isEnabled()


class TestViewManagement:
    """Test view save/load/delete functionality."""

    def test_load_view_changes_config(self, dialog):
        """Test that loading a view updates the UI."""
        # Load Default view first
        dialog.view_combo.setCurrentText("Default")

        # Get column states
        default_states = {}
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            default_states[item.text()] = item.checkState()

        # Load Custom View
        if dialog.view_combo.findText("Custom View") >= 0:
            dialog.view_combo.setCurrentText("Custom View")

            # Get column states after loading
            custom_states = {}
            for i in range(dialog.column_list.count()):
                item = dialog.column_list.item(i)
                custom_states[item.text()] = item.checkState()

            # States should be different for some columns
            assert default_states != custom_states

    def test_save_view_creates_new_view(self, dialog):
        """Test that Save View As creates a new view."""
        # Mock input dialog
        with patch.object(QInputDialog, 'getText', return_value=("Test View", True)):
            with patch.object(QMessageBox, 'information'):
                dialog._on_save_view()

        # Verify view was saved
        views = dialog.table_config_manager.list_views()
        assert "Test View" in views

    def test_save_view_overwrites_existing(self, dialog):
        """Test that saving over existing view requires confirmation."""
        # Mock input dialog to return existing view name
        with patch.object(QInputDialog, 'getText', return_value=("Default", True)):
            # Mock confirmation dialog (user clicks Yes)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                with patch.object(QMessageBox, 'information'):
                    dialog._on_save_view()

        # View should still exist
        views = dialog.table_config_manager.list_views()
        assert "Default" in views

    def test_save_view_cancel_on_overwrite(self, dialog):
        """Test that canceling overwrite doesn't save."""
        # Get original config
        original_views = dialog.table_config_manager.list_views()

        # Mock input dialog to return existing view name
        with patch.object(QInputDialog, 'getText', return_value=("Default", True)):
            # Mock confirmation dialog (user clicks No)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
                dialog._on_save_view()

        # Views should be unchanged
        current_views = dialog.table_config_manager.list_views()
        assert original_views == current_views

    def test_delete_view_removes_view(self, dialog):
        """Test that Delete View removes a view."""
        # First create a test view
        test_view_name = "View To Delete"
        with patch.object(QInputDialog, 'getText', return_value=(test_view_name, True)):
            with patch.object(QMessageBox, 'information'):
                dialog._on_save_view()

        # Select the test view
        index = dialog.view_combo.findText(test_view_name)
        if index >= 0:
            dialog.view_combo.setCurrentIndex(index)

            # Delete it
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                dialog._on_delete_view()

            # Verify view was deleted
            views = dialog.table_config_manager.list_views()
            assert test_view_name not in views

    def test_cannot_delete_default_view(self, dialog):
        """Test that Default view cannot be deleted."""
        # Select Default view
        dialog.view_combo.setCurrentText("Default")

        # Try to delete (should show warning)
        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog._on_delete_view()
            mock_warning.assert_called_once()

        # Default should still exist
        views = dialog.table_config_manager.list_views()
        assert "Default" in views

    def test_delete_button_disabled_for_default(self, dialog):
        """Test that delete button is disabled for Default view."""
        dialog.view_combo.setCurrentText("Default")
        assert not dialog.delete_view_button.isEnabled()

    def test_delete_button_enabled_for_custom_view(self, dialog):
        """Test that delete button is enabled for custom views."""
        if dialog.view_combo.findText("Custom View") >= 0:
            dialog.view_combo.setCurrentText("Custom View")
            assert dialog.delete_view_button.isEnabled()


class TestResetToDefault:
    """Test reset to default functionality."""

    def test_reset_restores_default_config(self, dialog):
        """Test that Reset to Default restores default configuration."""
        # Modify some settings
        for i in range(1, 3):
            item = dialog.column_list.item(i)
            item.setCheckState(Qt.Unchecked)

        dialog.auto_hide_checkbox.setChecked(False)

        # Reset
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            dialog._on_reset()

        # Check that settings are restored
        # All columns should be visible by default
        for i in range(dialog.column_list.count()):
            item = dialog.column_list.item(i)
            assert item.checkState() == Qt.Checked

        # Auto-hide should be True by default
        assert dialog.auto_hide_checkbox.isChecked()

    def test_reset_cancel_keeps_changes(self, dialog):
        """Test that canceling reset keeps changes."""
        # Modify a setting
        item = dialog.column_list.item(1)
        item.setCheckState(Qt.Unchecked)

        # Try to reset but cancel
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            dialog._on_reset()

        # Changes should remain
        assert item.checkState() == Qt.Unchecked


class TestApplyConfiguration:
    """Test applying configuration."""

    def test_apply_saves_config(self, dialog):
        """Test that Apply button saves configuration."""
        # Modify some settings
        item = dialog.column_list.item(1)
        item.setCheckState(Qt.Unchecked)

        # Apply
        with patch.object(dialog, 'accept') as mock_accept:
            dialog._on_apply()
            mock_accept.assert_called_once()

        # Verify config was saved
        config = dialog.table_config_manager.get_current_config()
        assert config.visible_columns["SKU"] == False

    def test_apply_emits_signal(self, dialog):
        """Test that Apply emits config_applied signal."""
        signal_emitted = False

        def on_signal():
            nonlocal signal_emitted
            signal_emitted = True

        dialog.config_applied.connect(on_signal)

        # Apply
        with patch.object(dialog, 'accept'):
            dialog._on_apply()

        assert signal_emitted

    def test_apply_without_client_shows_warning(self, dialog):
        """Test that Apply without client shows warning."""
        # Remove client_id
        dialog.parent_window.current_client_id = None

        # Try to apply
        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog._on_apply()
            mock_warning.assert_called_once()

    def test_cancel_closes_without_saving(self, dialog):
        """Test that Cancel button closes without saving."""
        # Get original config
        original_config = dialog.table_config_manager.get_current_config()

        # Modify settings
        item = dialog.column_list.item(1)
        original_state = item.checkState()
        new_state = Qt.Unchecked if original_state == Qt.Checked else Qt.Checked
        item.setCheckState(new_state)

        # Cancel
        with patch.object(dialog, 'reject') as mock_reject:
            dialog.cancel_button.click()
            mock_reject.assert_called_once()

        # Config should be unchanged
        current_config = dialog.table_config_manager.get_current_config()
        assert current_config.visible_columns == original_config.visible_columns


class TestAutoHideToggle:
    """Test auto-hide toggle functionality."""

    def test_auto_hide_toggle_changes_state(self, dialog):
        """Test that toggling auto-hide changes the checkbox state."""
        original_state = dialog.auto_hide_checkbox.isChecked()

        # Toggle
        dialog.auto_hide_checkbox.setChecked(not original_state)

        # Verify state changed
        assert dialog.auto_hide_checkbox.isChecked() == (not original_state)

    def test_auto_hide_saved_in_config(self, dialog):
        """Test that auto-hide setting is saved in configuration."""
        # Set auto-hide to False
        dialog.auto_hide_checkbox.setChecked(False)

        # Apply
        with patch.object(dialog, 'accept'):
            dialog._on_apply()

        # Verify saved
        config = dialog.table_config_manager.get_current_config()
        assert config.auto_hide_empty == False


class TestUIState:
    """Test UI state management."""

    def test_buttons_enabled_disabled_correctly(self, dialog):
        """Test that buttons are enabled/disabled based on selection."""
        # Select first item (Order_Number, can't move up)
        dialog.column_list.setCurrentRow(0)
        assert not dialog.up_button.isEnabled()
        assert dialog.down_button.isEnabled()

        # Select middle item
        dialog.column_list.setCurrentRow(3)
        assert dialog.up_button.isEnabled()
        assert dialog.down_button.isEnabled()

        # Select last item (can't move down)
        last_row = dialog.column_list.count() - 1
        dialog.column_list.setCurrentRow(last_row)
        assert dialog.up_button.isEnabled()
        assert not dialog.down_button.isEnabled()

    def test_no_selection_disables_move_buttons(self, dialog):
        """Test that no selection disables move buttons."""
        dialog.column_list.setCurrentRow(-1)  # No selection
        # Buttons should be disabled (or at least up button)
        assert not dialog.up_button.isEnabled()


class TestBug1ShowAllAutoHide:
    """Test Bug 1 fix: Show All should disable auto-hide."""

    def test_show_all_disables_auto_hide(self, dialog):
        """Show All should uncheck the auto-hide checkbox."""
        # Start with auto-hide enabled
        dialog.auto_hide_checkbox.setChecked(True)
        assert dialog.auto_hide_checkbox.isChecked()

        # Click Show All
        dialog._on_show_all()

        # Auto-hide should be disabled
        assert not dialog.auto_hide_checkbox.isChecked()

    def test_show_all_checks_all_items(self, dialog):
        """Show All should check all items including previously hidden ones."""
        # First hide all
        dialog._on_hide_all()

        # Verify some are unchecked
        unchecked = sum(
            1 for i in range(dialog.column_list.count())
            if dialog.column_list.item(i).checkState() == Qt.Unchecked
        )
        assert unchecked > 0

        # Show All
        dialog._on_show_all()

        # All should be checked
        for i in range(dialog.column_list.count()):
            assert dialog.column_list.item(i).checkState() == Qt.Checked

    def test_show_all_then_apply_keeps_auto_hide_off(self, dialog):
        """After Show All + Apply, auto_hide_empty should be False in saved config."""
        dialog.auto_hide_checkbox.setChecked(True)
        dialog._on_show_all()

        with patch.object(dialog, 'accept'):
            dialog._on_apply()

        config = dialog.table_config_manager.get_current_config()
        assert config.auto_hide_empty is False


class TestBug2ApplyViewName:
    """Test Bug 2 fix: Apply should save to the selected view, not always Default."""

    def test_apply_saves_to_selected_view(self, dialog):
        """Apply should save to the currently selected view in combo."""
        # Select Custom View
        index = dialog.view_combo.findText("Custom View")
        assert index >= 0, "Custom View should exist in combo"
        dialog.view_combo.setCurrentIndex(index)

        # Apply
        with patch.object(dialog, 'accept'):
            dialog._on_apply()

        # Verify save_config was called with "Custom View" view name
        save_calls = dialog.table_config_manager.pm.save_client_config.call_args_list
        assert len(save_calls) > 0
        last_saved_config = save_calls[-1][0][1]  # second arg to save_client_config
        active_view = last_saved_config["ui_settings"]["table_view"]["active_view"]
        assert active_view == "Custom View"

    def test_apply_with_default_saves_to_default(self, dialog):
        """Apply with Default selected should save to Default."""
        # Ensure Default is selected
        index = dialog.view_combo.findText("Default")
        dialog.view_combo.setCurrentIndex(index)

        with patch.object(dialog, 'accept'):
            dialog._on_apply()

        save_calls = dialog.table_config_manager.pm.save_client_config.call_args_list
        assert len(save_calls) > 0
        last_saved_config = save_calls[-1][0][1]
        active_view = last_saved_config["ui_settings"]["table_view"]["active_view"]
        assert active_view == "Default"
