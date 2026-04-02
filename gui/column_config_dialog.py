"""
Column Configuration Dialog

Provides UI for managing table column visibility, order, and views.

Phase 4 of table customization feature.
"""

import logging
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QLabel,
    QMessageBox,
    QInputDialog,
    QGroupBox,
    QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from gui.theme_manager import get_theme_manager

logger = logging.getLogger(__name__)


class ColumnConfigPanel(QWidget):
    """Embeddable panel for configuring table column visibility and order.

    Can be used inside a QDialog (ColumnConfigDialog) or embedded directly
    into a QTabWidget (e.g., SettingsWindow).
    """

    config_applied = Signal()

    def __init__(self, table_config_manager, main_window=None, parent=None):
        """
        Initialize the Column Configuration Panel.

        Args:
            table_config_manager: TableConfigManager instance
            main_window: MainWindow reference (for analysis_results_df, tableView, etc.)
            parent: Parent widget
        """
        super().__init__(parent)
        self.table_config_manager = table_config_manager
        # parent_window kept for backward-compat within the methods below
        self.parent_window = main_window

        self._original_config = None
        self._original_view_name = None
        self._current_columns: List[str] = []
        self._is_loading = False

        self.additional_columns_config: List[dict] = []

        self._init_ui()
        self._connect_signals()
        self._load_current_config()

    def _init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)

        # Search section
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter columns...")
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)

        # Column list section
        list_group = QGroupBox("Columns")
        list_layout = QVBoxLayout()

        self.column_list = QListWidget()
        self.column_list.setSelectionMode(QListWidget.SingleSelection)
        list_layout.addWidget(self.column_list)

        # Reorder buttons
        reorder_layout = QHBoxLayout()
        self.up_button = QPushButton("↑ Move Up")
        self.down_button = QPushButton("↓ Move Down")
        reorder_layout.addWidget(self.up_button)
        reorder_layout.addWidget(self.down_button)
        list_layout.addLayout(reorder_layout)

        list_group.setLayout(list_layout)
        main_layout.addWidget(list_group)

        # Visibility controls section
        visibility_group = QGroupBox("Visibility Controls")
        visibility_layout = QVBoxLayout()

        visibility_buttons_layout = QHBoxLayout()
        self.show_all_button = QPushButton("Show All")
        self.hide_all_button = QPushButton("Hide All")
        visibility_buttons_layout.addWidget(self.show_all_button)
        visibility_buttons_layout.addWidget(self.hide_all_button)
        visibility_layout.addLayout(visibility_buttons_layout)

        self.auto_hide_checkbox = QCheckBox("Auto-hide empty columns")
        self.auto_hide_checkbox.setToolTip(
            "Automatically hide columns that contain no data"
        )
        visibility_layout.addWidget(self.auto_hide_checkbox)

        visibility_group.setLayout(visibility_layout)
        main_layout.addWidget(visibility_group)

        # View management section
        view_group = QGroupBox("View Management")
        view_layout = QVBoxLayout()

        view_select_layout = QHBoxLayout()
        view_label = QLabel("Active View:")
        self.view_combo = QComboBox()
        view_select_layout.addWidget(view_label)
        view_select_layout.addWidget(self.view_combo, 1)
        view_layout.addLayout(view_select_layout)

        view_buttons_layout = QHBoxLayout()
        self.save_view_button = QPushButton("Save View As...")
        self.delete_view_button = QPushButton("Delete View")
        view_buttons_layout.addWidget(self.save_view_button)
        view_buttons_layout.addWidget(self.delete_view_button)
        view_layout.addLayout(view_buttons_layout)

        view_group.setLayout(view_layout)
        main_layout.addWidget(view_group)

        # Additional Columns Section
        additional_group = QGroupBox("Additional CSV Columns")
        additional_layout = QVBoxLayout()

        info_label = QLabel(
            "Configure additional columns from your CSV file to include in analysis.\n"
            "These columns are not in the standard mapping but can be preserved if needed."
        )
        info_label.setWordWrap(True)
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        additional_layout.addWidget(info_label)

        self.scan_csv_button = QPushButton("Scan Current CSV for Available Columns")
        self.scan_csv_button.clicked.connect(self._on_scan_csv)
        additional_layout.addWidget(self.scan_csv_button)

        self.additional_columns_list = QListWidget()
        self.additional_columns_list.setMaximumHeight(200)
        additional_layout.addWidget(self.additional_columns_list)

        additional_buttons = QHBoxLayout()
        self.enable_all_additional_button = QPushButton("Enable All")
        self.enable_all_additional_button.clicked.connect(self._on_enable_all_additional)
        self.disable_all_additional_button = QPushButton("Disable All")
        self.disable_all_additional_button.clicked.connect(self._on_disable_all_additional)
        additional_buttons.addWidget(self.enable_all_additional_button)
        additional_buttons.addWidget(self.disable_all_additional_button)
        additional_buttons.addStretch()
        additional_layout.addLayout(additional_buttons)

        additional_group.setLayout(additional_layout)
        main_layout.addWidget(additional_group)

        # Reset + Apply row
        action_layout = QHBoxLayout()
        self.reset_button = QPushButton("Reset to Default")
        self.reset_button.setToolTip("Reset all columns to default visibility and order")
        action_layout.addWidget(self.reset_button)
        action_layout.addStretch()
        self.apply_button = QPushButton("Apply Column Configuration")
        self.apply_button.setDefault(True)
        action_layout.addWidget(self.apply_button)
        main_layout.addLayout(action_layout)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        self.search_input.textChanged.connect(self._on_search_changed)

        self.column_list.itemChanged.connect(self._on_item_changed)
        self.column_list.currentRowChanged.connect(self._update_button_states)

        self.up_button.clicked.connect(self._on_move_up)
        self.down_button.clicked.connect(self._on_move_down)

        self.show_all_button.clicked.connect(self._on_show_all)
        self.hide_all_button.clicked.connect(self._on_hide_all)
        self.auto_hide_checkbox.toggled.connect(self._on_auto_hide_toggled)

        self.view_combo.currentTextChanged.connect(self._on_view_changed)
        self.save_view_button.clicked.connect(self._on_save_view)
        self.delete_view_button.clicked.connect(self._on_delete_view)

        self.reset_button.clicked.connect(self._on_reset)
        self.apply_button.clicked.connect(self.apply_config)

    def _load_current_config(self):
        """Load the current table configuration."""
        if not hasattr(self.parent_window, 'current_client_id'):
            logger.warning("No client selected, using default config")
            return

        client_id = self.parent_window.current_client_id
        self._is_loading = True

        try:
            config = self.table_config_manager.get_current_config()
            if config is None:
                config = self.table_config_manager.load_config(client_id)

            self._original_config = config
            self._original_view_name = self.table_config_manager.get_current_view_name()

            self.auto_hide_checkbox.setChecked(config.auto_hide_empty)

            self._load_views()
            self._load_columns(config)
            self._load_additional_columns_config()

        finally:
            self._is_loading = False

    def _load_views(self):
        """Load available views into the combo box."""
        self._is_loading = True
        try:
            self.view_combo.clear()
            views = self.table_config_manager.list_views()

            if not views:
                views = ["Default"]

            self.view_combo.addItems(views)

            current_view = self.table_config_manager.get_current_view_name()
            index = self.view_combo.findText(current_view)
            if index >= 0:
                self.view_combo.setCurrentIndex(index)

            self._update_delete_button_state()

        finally:
            self._is_loading = False

    def _load_columns(self, config):
        """Load columns into the list widget."""
        self.column_list.clear()
        self._current_columns = []

        if hasattr(self.parent_window, 'analysis_results_df') and \
           self.parent_window.analysis_results_df is not None:
            df = self.parent_window.analysis_results_df
            all_columns = df.columns.tolist()
        else:
            all_columns = config.column_order if config.column_order else list(config.visible_columns.keys())

        if config.column_order:
            ordered_columns = [col for col in config.column_order if col in all_columns]
            for col in all_columns:
                if col not in ordered_columns:
                    ordered_columns.append(col)
            columns = ordered_columns
        else:
            columns = all_columns

        for col_name in columns:
            item = QListWidgetItem(col_name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

            is_visible = config.visible_columns.get(col_name, True)
            item.setCheckState(Qt.Checked if is_visible else Qt.Unchecked)

            if col_name in config.locked_columns:
                item.setToolTip("⚠ Locked column (always visible and first)")
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.column_list.addItem(item)
            self._current_columns.append(col_name)

        self._update_button_states()

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        text = text.lower()

        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            column_name = item.text()

            if text in column_name.lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

    def _on_item_changed(self, item: QListWidgetItem):
        """Handle item check state change."""
        if self._is_loading:
            return

        column_name = item.text()
        config = self.table_config_manager.get_current_config()

        if column_name in config.locked_columns and item.checkState() == Qt.Unchecked:
            self._is_loading = True
            item.setCheckState(Qt.Checked)
            self._is_loading = False

            QMessageBox.warning(
                self,
                "Cannot Hide Column",
                f"Column '{column_name}' is locked and cannot be hidden."
            )

    def _on_move_up(self):
        """Move selected column up in the order."""
        current_row = self.column_list.currentRow()
        if current_row <= 0:
            return

        config = self.table_config_manager.get_current_config()
        item = self.column_list.currentItem()
        column_name = item.text()

        if column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Column '{column_name}' is locked and cannot be moved."
            )
            return

        if current_row == 1 and "Order_Number" in config.locked_columns:
            target_col = self.column_list.item(0).text()
            if target_col == "Order_Number":
                QMessageBox.warning(
                    self,
                    "Cannot Move Column",
                    "Cannot move column before locked 'Order_Number' column."
                )
                return

        item = self.column_list.takeItem(current_row)
        self.column_list.insertItem(current_row - 1, item)
        self.column_list.setCurrentRow(current_row - 1)

        self._current_columns.insert(current_row - 1, self._current_columns.pop(current_row))

    def _on_move_down(self):
        """Move selected column down in the order."""
        current_row = self.column_list.currentRow()
        if current_row < 0 or current_row >= self.column_list.count() - 1:
            return

        config = self.table_config_manager.get_current_config()
        item = self.column_list.currentItem()
        column_name = item.text()

        if column_name in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                f"Column '{column_name}' is locked and cannot be moved."
            )
            return

        if current_row == 0 and "Order_Number" in config.locked_columns:
            QMessageBox.warning(
                self,
                "Cannot Move Column",
                "Cannot move locked column."
            )
            return

        item = self.column_list.takeItem(current_row)
        self.column_list.insertItem(current_row + 1, item)
        self.column_list.setCurrentRow(current_row + 1)

        self._current_columns.insert(current_row + 1, self._current_columns.pop(current_row))

    def _on_show_all(self):
        """Show all columns and disable auto-hide."""
        self._is_loading = True
        try:
            for i in range(self.column_list.count()):
                item = self.column_list.item(i)
                item.setCheckState(Qt.Checked)
        finally:
            self._is_loading = False

        self.auto_hide_checkbox.setChecked(False)

    def _on_hide_all(self):
        """Hide all columns (except locked ones)."""
        config = self.table_config_manager.get_current_config()

        self._is_loading = True
        try:
            for i in range(self.column_list.count()):
                item = self.column_list.item(i)
                column_name = item.text()

                if column_name in config.locked_columns:
                    continue

                item.setCheckState(Qt.Unchecked)
        finally:
            self._is_loading = False

    def _on_auto_hide_toggled(self, checked: bool):
        """Handle auto-hide toggle."""
        pass

    def _on_view_changed(self, view_name: str):
        """Handle view selection change."""
        if self._is_loading or not view_name:
            return

        config = self.table_config_manager.load_view(view_name)
        if config:
            self._is_loading = True
            try:
                self.auto_hide_checkbox.setChecked(config.auto_hide_empty)
                self._load_columns(config)
            finally:
                self._is_loading = False

        self._update_delete_button_state()

    def _on_save_view(self):
        """Save current configuration as a named view."""
        view_name, ok = QInputDialog.getText(
            self,
            "Save View As",
            "Enter view name:",
            text=""
        )

        if not ok or not view_name.strip():
            return

        view_name = view_name.strip()

        existing_views = self.table_config_manager.list_views()
        if view_name in existing_views:
            reply = QMessageBox.question(
                self,
                "Overwrite View",
                f"View '{view_name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        config = self._get_config_from_ui()

        try:
            self.table_config_manager.save_view(view_name, config)
            logger.info(f"View '{view_name}' saved successfully")

            self._load_views()
            index = self.view_combo.findText(view_name)
            if index >= 0:
                self.view_combo.setCurrentIndex(index)

            QMessageBox.information(
                self,
                "View Saved",
                f"View '{view_name}' has been saved successfully."
            )
        except Exception as e:
            logger.error(f"Failed to save view '{view_name}': {e}")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save view: {str(e)}"
            )

    def _on_delete_view(self):
        """Delete the currently selected view."""
        view_name = self.view_combo.currentText()

        if not view_name or view_name == "Default":
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Cannot delete the Default view."
            )
            return

        reply = QMessageBox.question(
            self,
            "Delete View",
            f"Are you sure you want to delete view '{view_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        try:
            self.table_config_manager.delete_view(view_name)
            logger.info(f"View '{view_name}' deleted successfully")

            self._load_views()
            index = self.view_combo.findText("Default")
            if index >= 0:
                self.view_combo.setCurrentIndex(index)

        except Exception as e:
            logger.error(f"Failed to delete view '{view_name}': {e}")
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete view: {str(e)}"
            )

    def _on_reset(self):
        """Reset to default configuration."""
        reply = QMessageBox.question(
            self,
            "Reset to Default",
            "This will reset all columns to default visibility and order. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        if hasattr(self.parent_window, 'analysis_results_df') and \
           self.parent_window.analysis_results_df is not None:
            df = self.parent_window.analysis_results_df
            columns = df.columns.tolist()
        else:
            columns = self._current_columns

        default_config = self.table_config_manager.get_default_config(columns)

        self._is_loading = True
        try:
            self.auto_hide_checkbox.setChecked(default_config.auto_hide_empty)
            self._load_columns(default_config)
        finally:
            self._is_loading = False

    def revert_config(self):
        """Revert to the original view (called on cancel)."""
        if self._original_view_name and hasattr(self.parent_window, 'current_client_id'):
            client_id = self.parent_window.current_client_id
            if client_id:
                self.table_config_manager.load_config(client_id, self._original_view_name)
                logger.info(f"Restored original view: {self._original_view_name}")

    def apply_config(self):
        """Apply the current configuration (save + update table view)."""
        try:
            config = self._get_config_from_ui()

            if hasattr(self.parent_window, 'current_client_id') and self.parent_window.current_client_id:
                client_id = self.parent_window.current_client_id
                view_name = self.view_combo.currentText() or "Default"
                self.table_config_manager.save_config(client_id, config, view_name)

                if hasattr(self, 'additional_columns_config'):
                    if self.additional_columns_config:
                        logger.debug("Syncing UI checkbox states to config before saving...")
                        self._sync_ui_to_config()

                    enabled_cols = [col for col in self.additional_columns_config if col.get('enabled', False)]
                    disabled_cols = [col for col in self.additional_columns_config if not col.get('enabled', False)]

                    logger.debug(f"Saving additional columns config: {len(self.additional_columns_config)} columns")
                    logger.debug(f"  Enabled: {len(enabled_cols)} - {[col['csv_name'] for col in enabled_cols]}")
                    logger.debug(f"  Disabled: {len(disabled_cols)}")

                    client_config = self.table_config_manager.pm.load_client_config(client_id)

                    if "ui_settings" not in client_config:
                        client_config["ui_settings"] = {}
                    if "table_view" not in client_config["ui_settings"]:
                        client_config["ui_settings"]["table_view"] = {}

                    client_config["ui_settings"]["table_view"]["additional_columns"] = self.additional_columns_config

                    self.table_config_manager.pm.save_client_config(client_id, client_config)
                    logger.info(f"✓ Saved additional columns: {len(enabled_cols)} enabled ({', '.join([col['csv_name'] for col in enabled_cols])})")

                if hasattr(self.parent_window, 'tableView') and \
                   hasattr(self.parent_window, 'analysis_results_df') and \
                   self.parent_window.analysis_results_df is not None:
                    self.table_config_manager.apply_config_to_view(
                        self.parent_window.tableView,
                        self.parent_window.analysis_results_df
                    )

                logger.info("Column configuration applied successfully")

                if hasattr(self, 'additional_columns_config') and any(col.get('enabled', False) for col in self.additional_columns_config):
                    QMessageBox.information(
                        self,
                        "Configuration Saved",
                        "Table configuration has been saved.\n\n"
                        "Note: If you changed additional columns, you must re-run the analysis "
                        "to see the changes in the results table."
                    )

                self.config_applied.emit()

            else:
                QMessageBox.warning(
                    self,
                    "No Client Selected",
                    "Please select a client before applying configuration."
                )

        except Exception as e:
            logger.error(f"Failed to apply configuration: {e}")
            QMessageBox.critical(
                self,
                "Apply Failed",
                f"Failed to apply configuration: {str(e)}"
            )

    def _get_config_from_ui(self):
        """Create TableConfig from current UI state."""
        from gui.table_config_manager import TableConfig

        visible_columns = {}
        column_order = []

        for i in range(self.column_list.count()):
            item = self.column_list.item(i)
            column_name = item.text()
            is_visible = item.checkState() == Qt.Checked

            visible_columns[column_name] = is_visible
            column_order.append(column_name)

        current_config = self.table_config_manager.get_current_config()
        if current_config is None:
            current_config = self.table_config_manager.get_default_config(column_order)

        config = TableConfig(
            version=1,
            visible_columns=visible_columns,
            column_order=column_order,
            column_widths=current_config.column_widths.copy(),
            auto_hide_empty=self.auto_hide_checkbox.isChecked(),
            locked_columns=current_config.locked_columns.copy()
        )

        return config

    def _update_button_states(self):
        """Update enabled state of reorder buttons."""
        current_row = self.column_list.currentRow()
        count = self.column_list.count()

        self.up_button.setEnabled(current_row > 0)
        self.down_button.setEnabled(current_row >= 0 and current_row < count - 1)

    def _update_delete_button_state(self):
        """Update enabled state of delete view button."""
        view_name = self.view_combo.currentText()
        self.delete_view_button.setEnabled(view_name != "Default" and bool(view_name))

    def _on_scan_csv(self):
        """Scan current analysis dataframe for additional columns."""
        main_window = self.table_config_manager.mw

        if not hasattr(main_window, 'last_loaded_orders_df') or main_window.last_loaded_orders_df is None:
            QMessageBox.information(
                self,
                "No CSV Loaded",
                "Please load an orders CSV file first, then open this dialog to scan for additional columns."
            )
            return

        if hasattr(self, 'additional_columns_config') and self.additional_columns_config:
            self._sync_ui_to_config()

        orders_df = main_window.last_loaded_orders_df

        client_id = main_window.current_client_id
        shopify_config = self.table_config_manager.pm.load_shopify_config(client_id)
        column_mappings = shopify_config.get("column_mappings", {})

        if hasattr(self, 'additional_columns_config') and self.additional_columns_config:
            current_additional = self.additional_columns_config
        else:
            client_config = self.table_config_manager.pm.load_client_config(client_id)
            current_additional = client_config.get("ui_settings", {}).get("table_view", {}).get("additional_columns", [])

        from shopify_tool.csv_utils import discover_additional_columns
        discovered = discover_additional_columns(orders_df, column_mappings, current_additional)

        self._populate_additional_columns_list(discovered)

        self.additional_columns_config = discovered

        available_count = sum(1 for col in discovered if col["exists_in_df"])
        QMessageBox.information(
            self,
            "Scan Complete",
            f"Found {available_count} additional columns available in the current CSV file.\n\n"
            f"Check the columns you want to include in your analysis, then click Apply."
        )

    def _populate_additional_columns_list(self, columns_config: List[dict]):
        """Populate the additional columns list widget."""
        self.additional_columns_list.clear()

        for col_config in columns_config:
            item = QListWidgetItem()

            widget = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(4, 2, 4, 2)

            checkbox = QCheckBox(col_config["csv_name"])
            checkbox.setChecked(col_config["enabled"])
            checkbox.setProperty("internal_name", col_config["internal_name"])
            checkbox.stateChanged.connect(self._on_additional_column_toggled)

            order_level_cb = QCheckBox("Order-Level")
            order_level_cb.setChecked(col_config["is_order_level"])
            order_level_cb.setProperty("internal_name", col_config["internal_name"])
            order_level_cb.setToolTip("If checked, this column will be forward-filled for multi-item orders")
            order_level_cb.stateChanged.connect(self._on_order_level_toggled)

            layout.addWidget(checkbox)
            layout.addStretch()
            layout.addWidget(order_level_cb)

            if not col_config["exists_in_df"]:
                not_found_label = QLabel("(not in current CSV)")
                theme = get_theme_manager().get_current_theme()
                not_found_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
                layout.addWidget(not_found_label)
                checkbox.setEnabled(False)

            widget.setLayout(layout)

            item.setSizeHint(widget.sizeHint())
            self.additional_columns_list.addItem(item)
            self.additional_columns_list.setItemWidget(item, widget)

    def _load_additional_columns_config(self):
        """Load existing additional columns configuration from client config."""
        if not hasattr(self.parent_window, 'current_client_id') or not self.parent_window.current_client_id:
            logger.debug("No client selected, skipping additional columns load")
            return

        try:
            client_id = self.parent_window.current_client_id
            client_config = self.table_config_manager.pm.load_client_config(client_id)

            if not client_config:
                logger.debug("No client config found")
                return

            existing_additional = client_config.get("ui_settings", {}).get("table_view", {}).get("additional_columns", [])

            if existing_additional:
                self.additional_columns_config = existing_additional
                self._populate_additional_columns_list(existing_additional)
                logger.info(f"Loaded {len(existing_additional)} additional columns from client config")
            else:
                logger.debug("No additional columns configuration found for this client")

        except Exception as e:
            logger.warning(f"Failed to load additional columns configuration: {e}")

    def _on_additional_column_toggled(self, state):
        """Handle checkbox state change for additional column."""
        checkbox = self.sender()
        internal_name = checkbox.property("internal_name")
        csv_name = checkbox.text()
        is_enabled = (state == Qt.CheckState.Checked)

        for col in self.additional_columns_config:
            if col["internal_name"] == internal_name:
                col["enabled"] = is_enabled
                logger.debug(f"Toggled '{csv_name}' ({internal_name}): enabled={is_enabled}")
                break

    def _on_order_level_toggled(self, state):
        """Handle order-level checkbox state change."""
        checkbox = self.sender()
        internal_name = checkbox.property("internal_name")

        for col in self.additional_columns_config:
            if col["internal_name"] == internal_name:
                col["is_order_level"] = (state == Qt.CheckState.Checked)
                break

    def _on_enable_all_additional(self):
        """Enable all additional columns that exist in current CSV."""
        for col in self.additional_columns_config:
            if col["exists_in_df"]:
                col["enabled"] = True
        self._populate_additional_columns_list(self.additional_columns_config)

    def _on_disable_all_additional(self):
        """Disable all additional columns."""
        for col in self.additional_columns_config:
            col["enabled"] = False
        self._populate_additional_columns_list(self.additional_columns_config)

    def _sync_ui_to_config(self):
        """Sync current UI checkbox states back to self.additional_columns_config."""
        if not hasattr(self, 'additional_columns_config') or not self.additional_columns_config:
            return

        ui_states = {}

        for i in range(self.additional_columns_list.count()):
            item = self.additional_columns_list.item(i)
            widget = self.additional_columns_list.itemWidget(item)

            if widget is None:
                continue

            checkboxes = widget.findChildren(QCheckBox)
            if len(checkboxes) >= 2:
                main_checkbox = checkboxes[0]
                order_level_checkbox = checkboxes[1]

                internal_name = main_checkbox.property("internal_name")
                if internal_name:
                    ui_states[internal_name] = {
                        "enabled": main_checkbox.isChecked(),
                        "is_order_level": order_level_checkbox.isChecked()
                    }

        changes_count = 0
        for col in self.additional_columns_config:
            internal_name = col["internal_name"]
            if internal_name in ui_states:
                old_enabled = col["enabled"]
                new_enabled = ui_states[internal_name]["enabled"]

                col["enabled"] = new_enabled
                col["is_order_level"] = ui_states[internal_name]["is_order_level"]

                if old_enabled != new_enabled:
                    changes_count += 1
                    logger.debug(f"  Synced '{col['csv_name']}': {old_enabled} -> {new_enabled}")

        if changes_count > 0:
            logger.debug(f"Synced {changes_count} checkbox state changes from UI")

        logger.debug(f"Synced UI state to config: {len(ui_states)} columns updated")


class ColumnConfigDialog(QDialog):
    """Dialog wrapper around ColumnConfigPanel for standalone use."""

    config_applied = Signal()

    def __init__(self, table_config_manager, parent=None):
        """
        Initialize the Column Configuration Dialog.

        Args:
            table_config_manager: TableConfigManager instance
            parent: Parent widget (MainWindow)
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Table Columns")
        self.setMinimumSize(600, 700)
        self.setModal(True)

        main_layout = QVBoxLayout(self)

        self.panel = ColumnConfigPanel(table_config_manager, main_window=parent, parent=self)
        # Remove the panel's built-in Apply button (dialog has its own)
        self.panel.apply_button.hide()
        self.panel.reset_button.hide()
        main_layout.addWidget(self.panel)

        # Dialog-level buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.reset_button = QPushButton("Reset to Default")
        self.reset_button.setToolTip("Reset all columns to default visibility and order")
        self.reset_button.clicked.connect(self.panel._on_reset)
        button_layout.addWidget(self.reset_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)

        main_layout.addLayout(button_layout)

        # Close dialog when panel successfully applies
        self.panel.config_applied.connect(self._on_panel_applied)

    def _on_panel_applied(self):
        """Called when panel.config_applied is emitted."""
        self.config_applied.emit()
        self.accept()

    def _on_apply(self):
        """Trigger panel apply (dialog will close via signal)."""
        self.panel.apply_config()

    def _on_cancel(self):
        """Cancel changes and restore original view."""
        self.panel.revert_config()
        self.reject()
