import sys
import os
import json
import shutil
import pickle
import logging
from datetime import datetime

import pandas as pd
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QMenu, QTableWidgetItem, QLabel
from PySide6.QtCore import QThreadPool, QPoint, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QAction

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shopify_tool.utils import resource_path
from shopify_tool.analysis import recalculate_statistics
from shopify_tool.profile_manager import ProfileManager, NetworkError
from shopify_tool.session_manager import SessionManager
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.undo_manager import UndoManager
from shopify_tool.tag_manager import _normalize_tag_categories
from gui.log_handler import QtLogHandler
from gui.ui_manager import UIManager
from gui.file_handler import FileHandler
from gui.actions_handler import ActionsHandler
from gui.client_settings_dialog import ClientSelectorWidget
from gui.session_browser_widget import SessionBrowserWidget
from gui.profile_manager_dialog import ProfileManagerDialog
from gui.tag_management_panel import TagManagementPanel
from gui.selection_helper import SelectionHelper

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """The main window for the Shopify Fulfillment Tool application.

    This class encapsulates the main user interface and orchestrates the
    interactions between the UI elements, the data processing backend, and
    various handlers for files, actions, and UI management.

    Attributes:
        session_path (str): The directory path for the current work session.
        config (dict): The application's configuration settings.
        config_path (str): The path to the user's config.json file.
        orders_file_path (str): The path to the loaded orders CSV file.
        stock_file_path (str): The path to the loaded stock CSV file.
        analysis_results_df (pd.DataFrame): The main DataFrame holding the
            results of the fulfillment analysis.
        analysis_stats (dict): A dictionary of statistics derived from the
            analysis results.
        threadpool (QThreadPool): A thread pool for running background tasks.
        proxy_model (QSortFilterProxyModel): The proxy model for filtering and
            sorting the main results table.
        ui_manager (UIManager): Handles the creation and state of UI widgets.
        file_handler (FileHandler): Manages file selection and loading logic.
        actions_handler (ActionsHandler): Handles user actions like running
            analysis or generating reports.
    """

    def __init__(self):
        """Initializes the MainWindow, sets up UI, and connects signals."""
        super().__init__()
        self.setWindowTitle("Shopify Fulfillment Tool - New Architecture")
        self.setGeometry(100, 100, 1100, 900)

        # Core application attributes
        self.session_path = None
        self.current_client_id = None
        self.current_client_config = None
        self.active_profile_config = {}

        self.orders_file_path = None
        self.stock_file_path = None
        self.analysis_results_df = None
        self.analysis_stats = None
        self.threadpool = QThreadPool()
        self._analysis_running = False  # Guard against duplicate analysis runs

        # Table display attributes
        self.all_columns = []
        self.visible_columns = []
        self.is_syncing_selection = False

        # Models
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Search across all columns

        # Initialize new architecture managers
        self._init_managers()

        # Initialize undo manager
        self.undo_manager = UndoManager(self)

        # Initialize selection helper for bulk operations
        self.selection_helper = SelectionHelper(
            table_view=None,  # Will be set after UI creation
            proxy_model=self.proxy_model,
            main_window=self
        )

        # Initialize handlers
        self.ui_manager = UIManager(self)
        self.file_handler = FileHandler(self)
        self.actions_handler = ActionsHandler(self)

        # Setup UI and connect signals
        self.ui_manager.create_widgets()
        self.connect_signals()
        self.setup_logging()

    def _init_managers(self):
        """Initialize ProfileManager, SessionManager, and GroupsManager for the new architecture."""
        # ProfileManager now auto-detects environment:
        # 1. First checks FULFILLMENT_SERVER_PATH environment variable (dev mode)
        # 2. Falls back to default production path
        # This allows seamless switching between dev and production without code changes

        # Initialize ProfileManager with auto-detection (pass None or no argument)
        try:
            self.profile_manager = ProfileManager()  # Auto-detects from environment
            self.session_manager = SessionManager(self.profile_manager)

            # Initialize GroupsManager
            self.groups_manager = GroupsManager(
                base_path=str(self.profile_manager.base_path)
            )

            # Initialize TableConfigManager for table customization
            from gui.table_config_manager import TableConfigManager
            self.table_config_manager = TableConfigManager(self, self.profile_manager)

            logging.info("ProfileManager, SessionManager, GroupsManager, and TableConfigManager initialized successfully")
        except NetworkError as e:
            QMessageBox.critical(
                self,
                "Network Error",
                f"Cannot connect to file server:\n\n{str(e)}\n\n"
                f"The application will use offline mode with limited functionality."
            )
            # For now, exit the application if we can't connect
            # In the future, we could implement an offline mode
            QApplication.quit()
            return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize profile managers:\n{str(e)}"
            )
            QApplication.quit()
            return

    def load_client_config(self, client_id: str):
        """Load configuration for the selected client.

        Args:
            client_id: Client ID to load configuration for
        """
        if not client_id:
            return

        try:
            # Load shopify config for this client
            config = self.profile_manager.load_shopify_config(client_id)

            if config:
                self.active_profile_config = config
                self.current_client_id = client_id
                logging.info(f"Loaded configuration for CLIENT_{client_id}")

                # Update UI to reflect new client
                self.session_path_label.setText(f"Client: CLIENT_{client_id} - No session started")

                # Enable client-specific buttons
                self.new_session_btn.setEnabled(True)
                self.settings_button.setEnabled(True)

                # Reset analysis data when switching clients
                self.analysis_results_df = None
                self.analysis_stats = None
                self.session_path = None
                # Clear undo history when switching clients
                if hasattr(self, 'undo_manager'):
                    self.undo_manager.reset_for_session()
                self._update_all_views()

                # Disable file loading buttons until a session is created/selected
                self.load_orders_btn.setEnabled(False)
                self.load_stock_btn.setEnabled(False)

                # Disable report buttons until new analysis
                self.run_analysis_button.setEnabled(False)
                if hasattr(self, 'packing_list_button'):
                    self.packing_list_button.setEnabled(False)
                if hasattr(self, 'stock_export_button'):
                    self.stock_export_button.setEnabled(False)
                if hasattr(self, 'add_product_button'):
                    self.add_product_button.setEnabled(False)

                self.log_activity("Client", f"Switched to CLIENT_{client_id}")
            else:
                QMessageBox.warning(
                    self,
                    "Configuration Error",
                    f"Could not load configuration for CLIENT_{client_id}"
                )
        except Exception as e:
            logging.error(f"Failed to load client config: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load client configuration:\n{str(e)}"
            )

    def setup_logging(self):
        """Sets up the Qt-based logging handler.

        Initializes a `QtLogHandler` that emits a signal whenever a log
        message is received. This signal is connected to a slot that appends
        the message to the 'Execution Log' text box in the UI.
        """
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        self.log_handler.log_message_received.connect(self.execution_log_edit.appendPlainText)

    def connect_signals(self):
        """Connects all UI widget signals to their corresponding slots.

        This method centralizes all signal-slot connections for the main
        window, including button clicks, text changes, and custom signals
        from handler classes. This makes the UI event flow easier to trace.
        """
        # Client selection (new architecture) - use sidebar if it exists, otherwise fallback to client_selector
        if hasattr(self, 'client_sidebar'):
            self.client_sidebar.client_selected.connect(self.on_client_changed)
            self.client_sidebar.refresh_requested.connect(self.on_sidebar_refresh)
        elif hasattr(self, 'client_selector'):
            self.client_selector.client_changed.connect(self.on_client_changed)

        # Session browser (new architecture)
        self.session_browser.session_selected.connect(self.on_session_selected)

        # Session and file loading
        self.new_session_btn.clicked.connect(self.actions_handler.create_new_session)

        # Connect mode change signals
        self.orders_single_radio.toggled.connect(self.ui_manager.on_orders_mode_changed)
        self.stock_single_radio.toggled.connect(self.ui_manager.on_stock_mode_changed)

        # Connect file/folder selection buttons (will handle both modes)
        self.load_orders_btn.clicked.connect(self.file_handler.on_orders_select_clicked)
        self.load_stock_btn.clicked.connect(self.file_handler.on_stock_select_clicked)

        # Main actions
        self.run_analysis_button.clicked.connect(self.actions_handler.run_analysis)
        self.settings_button.clicked.connect(self.actions_handler.open_settings_window)
        self.add_product_button.clicked.connect(self.actions_handler.show_add_product_dialog)

        # Reports
        self.packing_list_button.clicked.connect(
            lambda: self.actions_handler.open_report_selection_dialog("packing_lists")
        )
        self.stock_export_button.clicked.connect(
            lambda: self.actions_handler.open_report_selection_dialog("stock_exports")
        )

        # Table interactions
        self.tableView.customContextMenuRequested.connect(self.show_context_menu)
        self.tableView.doubleClicked.connect(self.on_table_double_clicked)

        # Custom signals
        self.actions_handler.data_changed.connect(self._update_all_views)

        # Filter input
        self.filter_input.textChanged.connect(self.filter_table)
        self.filter_column_selector.currentIndexChanged.connect(self.filter_table)
        self.case_sensitive_checkbox.stateChanged.connect(self.filter_table)
        self.clear_filter_button.clicked.connect(self.clear_filter)
        self.tag_filter_combo.currentIndexChanged.connect(self.filter_table)

        # Add Ctrl+R shortcut for Run Analysis
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+R"), self,
                  lambda: self.run_analysis_button.click()
                          if self.run_analysis_button.isEnabled() else None)

        # Add Ctrl+F shortcut for Filter
        QShortcut(QKeySequence("Ctrl+F"), self,
                  lambda: self.filter_input.setFocus())

        # Add Ctrl+Z shortcut for Undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_last_operation)

        # Bulk operations toolbar signals
        if hasattr(self, 'bulk_toolbar'):
            self.bulk_toolbar.select_all_clicked.connect(self._on_bulk_select_all)
            self.bulk_toolbar.clear_selection_clicked.connect(self._on_bulk_clear_selection)
            self.bulk_toolbar.change_status_clicked.connect(self.actions_handler.bulk_change_status)
            self.bulk_toolbar.add_tag_clicked.connect(self.actions_handler.bulk_add_tag)
            self.bulk_toolbar.remove_tag_clicked.connect(self.actions_handler.bulk_remove_tag)
            self.bulk_toolbar.remove_sku_from_orders_clicked.connect(
                self.actions_handler.bulk_remove_sku_from_orders
            )
            self.bulk_toolbar.remove_orders_with_sku_clicked.connect(
                self.actions_handler.bulk_remove_orders_with_sku
            )
            self.bulk_toolbar.delete_orders_clicked.connect(self.actions_handler.bulk_delete_orders)
            self.bulk_toolbar.export_selection_clicked.connect(self.actions_handler.bulk_export_selection)

    def clear_filter(self):
        """Clears the filter input text box, tag filter, and resets proxy model."""
        self.filter_input.clear()
        if hasattr(self, 'tag_filter_combo'):
            self.tag_filter_combo.setCurrentIndex(0)  # Reset to "All Tags"

        # Reset proxy model filter state
        self.proxy_model.setFilterRegularExpression("")
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.invalidateFilter()

    def undo_last_operation(self):
        """Undo the last DataFrame modification."""
        if not self.undo_manager.can_undo():
            QMessageBox.information(self, "Undo", "Nothing to undo")
            return

        success, message = self.undo_manager.undo()

        if success:
            # Reload current state from undo manager's restored DataFrame
            self._update_all_views()
            self.log_activity("Undo", message)
            self.save_session_state()

            # Update undo button state
            if hasattr(self, 'undo_button'):
                self.undo_button.setEnabled(self.undo_manager.can_undo())
                # Update tooltip with next undo description
                next_undo = self.undo_manager.get_undo_description()
                if next_undo:
                    self.undo_button.setToolTip(f"Undo: {next_undo} (Ctrl+Z)")
                else:
                    self.undo_button.setToolTip("Undo last operation (Ctrl+Z)")

            QMessageBox.information(self, "Undo", message)
        else:
            QMessageBox.critical(self, "Undo Failed", message)

    def _apply_tag_operation(self, mask, description: str, params: dict, tag: str):
        """Apply add_tag to DataFrame rows matching mask, record undo, and refresh UI."""
        from shopify_tool.tag_manager import add_tag

        if "Internal_Tags" not in self.analysis_results_df.columns:
            self.analysis_results_df["Internal_Tags"] = "[]"

        affected_rows_before = self.analysis_results_df[mask].copy()
        self.analysis_results_df.loc[mask, "Internal_Tags"] = (
            self.analysis_results_df.loc[mask, "Internal_Tags"].apply(lambda t: add_tag(t, tag))
        )
        self.undo_manager.record_operation(
            operation_type="add_internal_tag",
            description=description,
            params=params,
            affected_rows_before=affected_rows_before
        )
        self.save_session_state()
        self._update_all_views()
        self.log_activity("Internal Tag", description)
        if hasattr(self, 'undo_button'):
            self.undo_button.setEnabled(True)
            self.undo_button.setToolTip(f"Undo: {description} (Ctrl+Z)")

    def _add_internal_tag(self, order_number: str, sku: str, tag: str):
        """Add internal tag to the specific row identified by order_number + sku."""
        mask = (
            (self.analysis_results_df["Order_Number"] == order_number) &
            (self.analysis_results_df["SKU"] == sku)
        )
        self._apply_tag_operation(
            mask,
            description=f"Add Internal Tag: {tag} to order {order_number} / {sku}",
            params={"order_number": order_number, "sku": sku, "tag": tag},
            tag=tag,
        )

    def add_internal_tag_to_order(self, order_number, tag):
        """Add an Internal Tag to all rows of an order (called from tag_management_panel signal)."""
        if self.analysis_results_df is None or self.analysis_results_df.empty:
            return
        mask = self.analysis_results_df["Order_Number"] == order_number
        self._apply_tag_operation(
            mask,
            description=f"Add Internal Tag: {tag} to order {order_number}",
            params={"order_number": order_number, "tag": tag},
            tag=tag,
        )
        if hasattr(self, 'tag_management_panel') and self.tag_management_panel.isVisible():
            self.on_selection_changed_for_tags()

    def remove_internal_tag_from_order(self, order_number, tag):
        """Remove an Internal Tag from all items in an order.

        Args:
            order_number: Order number to remove tag from
            tag: Tag to remove
        """
        from shopify_tool.tag_manager import remove_tag

        # Ensure Internal_Tags column exists
        if "Internal_Tags" not in self.analysis_results_df.columns:
            return

        # Get affected rows (all items in the order) BEFORE modification
        mask = self.analysis_results_df["Order_Number"] == order_number
        affected_rows_before = self.analysis_results_df[mask].copy()

        # Update tags for all items in the order
        current_tags = self.analysis_results_df.loc[mask, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: remove_tag(t, tag))
        self.analysis_results_df.loc[mask, "Internal_Tags"] = new_tags

        # Record operation for undo (AFTER modification)
        self.undo_manager.record_operation(
            operation_type="remove_internal_tag",
            description=f"Remove Internal Tag: {tag} from order {order_number}",
            params={
                "order_number": order_number,
                "tag": tag
            },
            affected_rows_before=affected_rows_before
        )

        # Save state and update UI
        self.save_session_state()
        self._update_all_views()
        self.log_activity("Internal Tag", f"Removed '{tag}' from order {order_number}")

        # Update undo button
        if hasattr(self, 'undo_button'):
            self.undo_button.setEnabled(True)
            self.undo_button.setToolTip(f"Undo: Remove Internal Tag: {tag} (Ctrl+Z)")

        # Update tag panel if visible
        if hasattr(self, 'tag_management_panel') and self.tag_management_panel.isVisible():
            self.on_selection_changed_for_tags()

    def on_selection_changed_for_tags(self):
        """Update tag management panel when table selection changes."""
        if not hasattr(self, 'tag_management_panel') or not self.tag_management_panel.isVisible():
            return

        if self.analysis_results_df is None or self.analysis_results_df.empty:
            self.tag_management_panel.set_selected_order(None, "[]")
            return

        # Get selected rows
        selected_indexes = self.tableView.selectionModel().selectedRows()
        if not selected_indexes:
            self.tag_management_panel.set_selected_order(None, "[]")
            return

        # Get first selected row
        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        row = source_index.row()

        if row < 0 or row >= len(self.analysis_results_df):
            self.tag_management_panel.set_selected_order(None, "[]")
            return

        # Get order number and current tags
        order_number = self.analysis_results_df.iloc[row]["Order_Number"]
        current_tags = self.analysis_results_df.iloc[row].get("Internal_Tags", "[]")

        self.tag_management_panel.set_selected_order(order_number, current_tags)

    def toggle_tag_panel(self):
        """Toggle tag management panel visibility."""
        if not hasattr(self, 'tag_management_panel'):
            return

        if self.tag_management_panel.isVisible():
            self.tag_management_panel.hide()
            self.toggle_tags_panel_btn.setChecked(False)
        else:
            self.tag_management_panel.show()
            self.toggle_tags_panel_btn.setChecked(True)

            # Load predefined tags from config
            if self.active_profile_config:
                tag_categories = self.active_profile_config.get("tag_categories", {})
                self.tag_management_panel.load_predefined_tags(tag_categories)

            # Update panel with current selection
            self.on_selection_changed_for_tags()

            # Connect table selection changed signal if not already connected
            if hasattr(self, 'tableView') and hasattr(self.tableView, 'selectionModel'):
                try:
                    self.tableView.selectionModel().selectionChanged.disconnect(self.on_selection_changed_for_tags)
                except:
                    pass  # Not connected yet
                self.tableView.selectionModel().selectionChanged.connect(self.on_selection_changed_for_tags)

    def open_column_config_dialog(self):
        """Open the Column Configuration Dialog."""
        if not hasattr(self, 'table_config_manager'):
            logger.warning("TableConfigManager not initialized")
            return

        if not hasattr(self, 'current_client_id') or not self.current_client_id:
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client before configuring columns."
            )
            return

        from gui.column_config_dialog import ColumnConfigDialog

        dialog = ColumnConfigDialog(self.table_config_manager, self)
        dialog.config_applied.connect(self._on_column_config_applied)
        dialog.exec()

    def _on_column_config_applied(self):
        """Handle column configuration applied signal."""
        logger.info("Column configuration has been applied")
        # Update hidden columns indicator in summary bar
        if hasattr(self, 'ui_manager'):
            self.ui_manager.update_hidden_columns_indicator()

    def toggle_bulk_mode(self):
        """Toggle bulk operations mode.

        When bulk mode is enabled:
        - Checkbox column is shown in the table
        - Bulk operations toolbar is visible
        - Selection state is tracked via SelectionHelper

        When bulk mode is disabled:
        - Checkbox column is hidden
        - Bulk operations toolbar is hidden
        - Selection is cleared
        """
        is_bulk_mode = self.toggle_bulk_mode_btn.isChecked()

        # Show/hide bulk toolbar
        if hasattr(self, 'bulk_toolbar'):
            self.bulk_toolbar.setVisible(is_bulk_mode)

        # Clear selection when toggling
        self.selection_helper.clear_selection()

        # Refresh table to show/hide checkboxes
        if self.analysis_results_df is not None and not self.analysis_results_df.empty:
            self.ui_manager.update_results_table(self.analysis_results_df)

        # Update button styling
        if is_bulk_mode:
            self.toggle_bulk_mode_btn.setText("Exit Bulk Mode")
            self.toggle_bulk_mode_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            self._update_bulk_toolbar_state()
            logging.info("Bulk mode enabled")
        else:
            self.toggle_bulk_mode_btn.setText("📦 Bulk Operations")
            self.toggle_bulk_mode_btn.setStyleSheet("")
            logging.info("Bulk mode disabled")

    def _update_bulk_toolbar_state(self):
        """Update bulk toolbar selection counter and button states."""
        if not hasattr(self, 'bulk_toolbar'):
            return

        orders_count, items_count = self.selection_helper.get_selection_summary()
        self.bulk_toolbar.update_selection_count(orders_count, items_count)
        self.bulk_toolbar.set_enabled(orders_count > 0)

    def _on_bulk_select_all(self):
        """Handle Select All button in bulk toolbar."""
        self.selection_helper.select_all()
        self._update_bulk_toolbar_state()
        self.tableView.viewport().update()  # Force repaint

    def _on_bulk_clear_selection(self):
        """Handle Clear button in bulk toolbar."""
        self.selection_helper.clear_selection()
        self._update_bulk_toolbar_state()
        self.tableView.viewport().update()  # Force repaint

    def update_session_info_label(self):
        """Update global header session info label."""
        if not self.session_path:
            self.session_info_label.setText("No session")
            return

        session_name = os.path.basename(self.session_path)
        self.session_info_label.setText(session_name)

        # Update session_path_label as well for compatibility
        self.session_path_label.setText(f"Session: {session_name}")

    def update_ui_state(self):
        """Update button states based on application state.

        Called after state changes (client selected, files loaded, analysis run).
        """
        has_client = bool(self.current_client_id)
        has_session = bool(self.session_path)
        has_orders = bool(getattr(self, 'orders_file_path', None))
        has_stock = bool(getattr(self, 'stock_file_path', None))
        has_analysis = hasattr(self, 'analysis_results_df') and self.analysis_results_df is not None

        # Session management
        self.new_session_btn.setEnabled(has_client)

        # Settings button (Tab 1 version)
        if hasattr(self, 'settings_button'):
            self.settings_button.setEnabled(has_client)
        # Settings button (Tab 2 version)
        if hasattr(self, 'settings_button_tab2'):
            self.settings_button_tab2.setEnabled(has_client)

        # File loading
        self.load_orders_btn.setEnabled(has_session)
        self.load_stock_btn.setEnabled(has_session)

        # Run Analysis button
        self.run_analysis_button.setEnabled(
            has_session and has_orders and has_stock
        )

        # Reports and actions (both Tab 1 and Tab 2 versions)
        reports_enabled = has_session and has_analysis

        # Tab 1 buttons
        if hasattr(self, 'packing_list_button'):
            self.packing_list_button.setEnabled(reports_enabled)
        if hasattr(self, 'stock_export_button'):
            self.stock_export_button.setEnabled(reports_enabled)
        if hasattr(self, 'add_product_button'):
            self.add_product_button.setEnabled(has_analysis)

        # Tab 2 buttons
        if hasattr(self, 'packing_list_button_tab2'):
            self.packing_list_button_tab2.setEnabled(reports_enabled)
        if hasattr(self, 'stock_export_button_tab2'):
            self.stock_export_button_tab2.setEnabled(reports_enabled)
        if hasattr(self, 'add_product_button_tab2'):
            self.add_product_button_tab2.setEnabled(has_analysis)
        if hasattr(self, 'configure_columns_button_tab2'):
            self.configure_columns_button_tab2.setEnabled(has_analysis)
        # Tags Manager button
        if hasattr(self, 'toggle_tags_panel_btn'):
            self.toggle_tags_panel_btn.setEnabled(has_analysis)

        # Bulk Operations button
        if hasattr(self, 'toggle_bulk_mode_btn'):
            self.toggle_bulk_mode_btn.setEnabled(has_analysis)

        # Open Session Folder button (enabled when session exists)
        if hasattr(self, 'open_session_folder_button'):
            self.open_session_folder_button.setEnabled(has_session)

        # Update status bar
        if has_analysis:
            self.statusBar().showMessage("Analysis complete - ready for export", 5000)
        elif has_session:
            self.statusBar().showMessage("Session active - load files to begin", 5000)
        elif has_client:
            self.statusBar().showMessage("Client selected - create or open a session", 5000)
        else:
            self.statusBar().showMessage("Ready - select a client to begin", 5000)

    # --- Client and Session Management (New Architecture) ---
    def on_client_changed(self, client_id: str):
        """Handle client selection change.

        Args:
            client_id: Newly selected client ID
        """
        logging.info(f"Client changed to: {client_id}")

        # Show loading status in status bar
        if hasattr(self, 'statusBar'):
            self.statusBar().showMessage(f"Loading CLIENT_{client_id}...", 5000)

        # Update sidebar active state if sidebar exists
        if hasattr(self, 'client_sidebar'):
            self.client_sidebar.set_active_client(client_id)

        # Update header label if it exists
        if hasattr(self, 'current_client_label'):
            self.current_client_label.setText(f"CLIENT_{client_id}")

        # Store current client ID
        self.current_client_id = client_id

        # Load configuration for this client
        try:
            self.current_client_config = self.profile_manager.load_shopify_config(client_id)
            if not self.current_client_config:
                QMessageBox.warning(
                    self,
                    "Configuration Error",
                    f"Failed to load configuration for client {client_id}"
                )
                return

            # Also load it via the existing method for backward compatibility
            self.load_client_config(client_id)

            # Load table configuration for this client
            if hasattr(self, 'table_config_manager'):
                self.table_config_manager.load_config(client_id)
                logging.info(f"Table configuration loaded for CLIENT_{client_id}")

            # Clear currently loaded files (they're for different client)
            self.orders_file_path = None
            self.stock_file_path = None
            self.orders_file_path_label.setText("No file loaded")
            self.stock_file_path_label.setText("No file loaded")
            self.orders_file_status_label.setText("")
            self.stock_file_status_label.setText("")

            # Clear session
            self.session_path = None
            # Clear undo history when switching clients
            if hasattr(self, 'undo_manager'):
                self.undo_manager.reset_for_session()
            self.update_session_info_label()

            # Update session browser to show this client's sessions
            # Don't auto-refresh here - let the second call handle it
            self.session_browser.set_client(client_id, auto_refresh=False)

            # Update session browser widget in right panel (Tab 1)
            # This one WILL refresh (eliminates duplicate refresh)
            if hasattr(self, 'session_browser_widget'):
                self.session_browser_widget.set_client(client_id)

            # Update UI state
            self.update_ui_state()

            logging.info(f"Client {client_id} loaded successfully")

            # Update status bar with success message
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"CLIENT_{client_id} loaded", 2000)

        except Exception as e:
            logging.error(f"Error changing client: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to change client: {str(e)}"
            )

    def on_sidebar_refresh(self):
        """Handle manual sidebar refresh request."""
        try:
            if hasattr(self, 'client_sidebar'):
                self.client_sidebar.refresh()
                self.log_activity("UI", "Client sidebar refreshed")
        except Exception as e:
            logging.error(f"Sidebar refresh failed: {e}")
            QMessageBox.warning(self, "Refresh Error", str(e))

    def on_session_selected(self, session_path: str):
        """Handle session selection from session browser.

        Args:
            session_path: Path to the selected session
        """
        logging.info(f"Session selected: {session_path}")

        reply = QMessageBox.question(
            self,
            "Open Session",
            f"Do you want to open this session?\n\n{session_path}\n\n"
            f"This will load any existing analysis data from the session.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.load_existing_session(session_path)

    def save_session_state(self):
        """Save current analysis state to session directory.

        Saves both pickle (fast) and Excel (backup) formats.
        Only saves if session exists and analysis data is present.

        This method is called after every DataFrame modification to ensure
        state persistence across session reloads.
        """
        from pathlib import Path

        # Check prerequisites
        if not self.session_path:
            logging.debug("No active session - skipping save_session_state")
            return

        if self.analysis_results_df is None or self.analysis_results_df.empty:
            logging.debug("No analysis data to save - skipping save_session_state")
            return

        try:
            session_path = Path(self.session_path)
            analysis_dir = session_path / "analysis"

            # Ensure analysis directory exists
            analysis_dir.mkdir(parents=True, exist_ok=True)

            # Define file paths
            pkl_path = analysis_dir / "current_state.pkl"
            xlsx_path = analysis_dir / "current_state.xlsx"
            stats_path = analysis_dir / "analysis_stats.json"

            # Save DataFrame to pickle (fast, primary format)
            logging.info(f"Saving session state to {pkl_path}")
            self.analysis_results_df.to_pickle(pkl_path)

            # Save DataFrame to Excel (backup, human-readable)
            logging.info(f"Saving session state backup to {xlsx_path}")
            self.analysis_results_df.to_excel(xlsx_path, index=False)

            # Save statistics to JSON
            if self.analysis_stats:
                logging.info(f"Saving statistics to {stats_path}")
                with open(stats_path, 'w', encoding='utf-8') as f:
                    json.dump(self.analysis_stats, f, indent=2, ensure_ascii=False)

            logging.info("Session state saved successfully")

        except Exception as e:
            # Don't block UI if save fails - just log the error
            logging.error(f"Failed to save session state: {e}", exc_info=True)

    def _load_session_analysis(self, session_path):
        """Load analysis data from session directory.

        Priority order:
        1. current_state.pkl (fastest, reflects latest modifications)
        2. current_state.xlsx (backup if pickle corrupted)
        3. analysis_report.xlsx (original analysis output)

        Args:
            session_path: Path to session directory (can be str or Path)

        Returns:
            True if loaded successfully, False otherwise
        """
        from pathlib import Path

        try:
            session_path = Path(session_path)
            analysis_dir = session_path / "analysis"

            # Priority 1: Try loading from current_state.pkl
            pkl_path = analysis_dir / "current_state.pkl"
            if pkl_path.exists():
                try:
                    logging.info(f"Loading session state from pickle: {pkl_path}")
                    self.analysis_results_df = pd.read_pickle(pkl_path)

                    # Load statistics from JSON if available
                    stats_path = analysis_dir / "analysis_stats.json"
                    if stats_path.exists():
                        logging.info(f"Loading statistics from: {stats_path}")
                        with open(stats_path, 'r', encoding='utf-8') as f:
                            self.analysis_stats = json.load(f)
                    else:
                        # Recalculate if stats file missing
                        logging.info("Statistics file not found - recalculating")
                        self.analysis_stats = recalculate_statistics(self.analysis_results_df)

                    logging.info(f"Loaded {len(self.analysis_results_df)} rows from current_state.pkl")
                    return True

                except Exception as e:
                    logging.warning(f"Failed to load pickle, trying Excel fallback: {e}")
                    # Continue to fallback options

            # Priority 2: Try loading from current_state.xlsx
            xlsx_path = analysis_dir / "current_state.xlsx"
            if xlsx_path.exists():
                try:
                    logging.info(f"Loading session state from Excel: {xlsx_path}")
                    self.analysis_results_df = pd.read_excel(xlsx_path)

                    # Load or recalculate statistics
                    stats_path = analysis_dir / "analysis_stats.json"
                    if stats_path.exists():
                        with open(stats_path, 'r', encoding='utf-8') as f:
                            self.analysis_stats = json.load(f)
                    else:
                        self.analysis_stats = recalculate_statistics(self.analysis_results_df)

                    logging.info(f"Loaded {len(self.analysis_results_df)} rows from current_state.xlsx")
                    return True

                except Exception as e:
                    logging.warning(f"Failed to load current_state.xlsx, trying original report: {e}")
                    # Continue to fallback

            # Priority 3: Fallback to original analysis_report.xlsx
            # Check for analysis_data.json first (indicates analysis was completed)
            analysis_data_file = analysis_dir / "analysis_data.json"

            if not analysis_data_file.exists():
                logging.warning(f"Analysis data not found: {analysis_data_file}")
                return False

            logging.info(f"Found analysis data: {analysis_data_file}")

            # Load the actual Excel report to get DataFrame
            report_file = analysis_dir / "fulfillment_analysis.xlsx"

            if not report_file.exists():
                # Try alternative name
                report_file = analysis_dir / "analysis_report.xlsx"

            if not report_file.exists():
                logging.warning(f"Analysis report not found: {report_file}")
                return False

            logging.info(f"Loading analysis from original report: {report_file}")

            # Load DataFrame from Excel
            self.analysis_results_df = pd.read_excel(report_file)

            # Recalculate statistics (no saved stats for original report)
            self.analysis_stats = recalculate_statistics(self.analysis_results_df)

            logging.info(f"Loaded {len(self.analysis_results_df)} rows from session")
            return True

        except Exception as e:
            logging.error(f"Failed to load session analysis: {e}", exc_info=True)
            return False

    def load_existing_session(self, session_path: str):
        """Load data from an existing session.

        Args:
            session_path: Path to the session directory
        """
        from pathlib import Path

        try:
            # Set as current session
            self.session_path = session_path
            session_name = os.path.basename(session_path)

            # Reload undo history for this session
            if hasattr(self, 'undo_manager'):
                self.undo_manager.reload_session_history()

            # Update session info labels
            self.update_session_info_label()

            # Load session info
            session_info = self.session_manager.get_session_info(session_path)

            if session_info:
                # Try to load analysis data if it exists
                if self._load_session_analysis(session_path):
                    # Analysis loaded successfully
                    self._update_all_views()

                    # Auto-switch to Analysis Results tab (Tab 2)
                    self.main_tabs.setCurrentIndex(1)

                    self.log_activity("Session", f"Loaded session: {session_name}")
                    QMessageBox.information(
                        self,
                        "Session Loaded",
                        f"Session loaded successfully:\n{session_name}\n\n"
                        f"Analysis data: {len(self.analysis_results_df)} rows"
                    )
                else:
                    # Session exists but no analysis yet
                    self.log_activity("Session", f"Opened session (no analysis): {session_name}")
                    QMessageBox.information(
                        self,
                        "Session Opened",
                        f"Session opened:\n{session_name}\n\n"
                        f"No analysis data found. You can run a new analysis."
                    )

                # Update UI state
                self.update_ui_state()

        except Exception as e:
            logging.error(f"Failed to load session: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load session:\n{str(e)}"
            )

    def filter_table(self):
        """Applies the current filter settings to the results table view.

        Reads the filter text, selected column, and case sensitivity setting
        from the UI controls and applies them to the `QSortFilterProxyModel`
        to update the visible rows in the table.
        """
        # Check if tag filter is active
        selected_tag = None
        if hasattr(self, 'tag_filter_combo'):
            selected_tag = self.tag_filter_combo.currentData()

        if selected_tag:
            # Tag filter is active - filter by Internal_Tags column
            # Find the Internal_Tags column index
            if self.analysis_results_df is not None and "Internal_Tags" in self.analysis_results_df.columns:
                col_index = self.analysis_results_df.columns.get_loc("Internal_Tags")

                # Use JSON-formatted tag as filter pattern (e.g., "URGENT")
                # This will match if the tag appears in the JSON array
                self.proxy_model.setFilterKeyColumn(col_index)
                self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitive)
                # Use regex pattern to match the tag within the JSON array
                # Pattern: "TAGNAME" (with quotes, as it appears in JSON)
                import re
                pattern = f'"{re.escape(selected_tag)}"'
                self.proxy_model.setFilterRegularExpression(pattern)
        else:
            # Regular text filter
            text = self.filter_input.text()
            column_index = self.filter_column_selector.currentIndex()

            # First item is "All Columns", so filter should be -1
            filter_column = column_index - 1

            case_sensitivity = Qt.CaseSensitive if self.case_sensitive_checkbox.isChecked() else Qt.CaseInsensitive

            self.proxy_model.setFilterKeyColumn(filter_column)
            self.proxy_model.setFilterCaseSensitivity(case_sensitivity)
            self.proxy_model.setFilterRegularExpression(text)

    def _update_all_views(self):
        """Central slot to refresh all UI components after data changes.

        This method is called whenever the main `analysis_results_df` is
        modified. It recalculates statistics, updates the main results table,
        refreshes the statistics tab, and repopulates the column filter
        dropdown. It acts as a single point of refresh for the UI.
        """
        # Update statistics ONLY if analysis results exist
        if self.analysis_results_df is not None and not self.analysis_results_df.empty:
            try:
                self.analysis_stats = recalculate_statistics(self.analysis_results_df)
                self.ui_manager.update_results_table(self.analysis_results_df)
                self.update_statistics_tab()
                # Update summary bar in Tab 2
                self.ui_manager.update_summary_bar()
            except Exception as e:
                logging.error(f"Failed to recalculate statistics: {e}", exc_info=True)
                self.analysis_stats = None
                self._clear_statistics_view()
        else:
            # No analysis results - clear statistics
            self.analysis_stats = None
            self._clear_statistics_view()
            self.ui_manager.update_results_table(pd.DataFrame())

        # Populate filter dropdown
        self.filter_column_selector.clear()
        self.filter_column_selector.addItem("All Columns")
        if self.analysis_results_df is not None and not self.analysis_results_df.empty:
            self.filter_column_selector.addItems(self.all_columns)
        self.ui_manager.set_ui_busy(False)
        # The column manager button is enabled within update_results_table

    def update_statistics_tab(self):
        """Populates the 'Statistics' tab with the latest analysis data."""
        if not self.analysis_stats:
            return

        # === 1. Session Totals cards ===
        if hasattr(self, 'stat_card_labels'):
            for key, lbl in self.stat_card_labels.items():
                lbl.setText(str(self.analysis_stats.get(key, "-")))

        # === 2. Courier cards ===
        if hasattr(self, 'courier_cards_layout'):
            while self.courier_cards_layout.count() > 1:
                item = self.courier_cards_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            courier_stats = self.analysis_stats.get("couriers_stats") or []
            for stats in courier_stats:
                card = self.ui_manager._make_courier_card(
                    stats.get("courier_id", "N/A"),
                    str(stats.get("orders_assigned", 0)),
                    str(stats.get("repeated_orders_found", 0)),
                )
                self.courier_cards_layout.insertWidget(
                    self.courier_cards_layout.count() - 1, card
                )

        # === 3. Tag cards (Fulfillable + Not Fulfillable) ===
        from shopify_tool.tag_manager import get_tag_color
        tag_cats = _normalize_tag_categories(
            self.active_profile_config.get("tag_categories", {})
            if self.active_profile_config else {}
        )

        def _populate_tag_layout(layout_attr, breakdown_key):
            layout = getattr(self, layout_attr, None)
            if layout is None:
                return
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            breakdown = self.analysis_stats.get(breakdown_key) or {}
            for tag, count in breakdown.items():
                color = get_tag_color(tag, tag_cats)
                card = self.ui_manager._make_tag_card(tag, str(count), color=color)
                layout.insertWidget(layout.count() - 1, card)

        _populate_tag_layout("tags_fulfillable_layout", "tags_breakdown_fulfillable")
        _populate_tag_layout("tags_not_fulfillable_layout", "tags_breakdown_not_fulfillable")

        # === 4. SKU table ===
        if hasattr(self, 'sku_table'):
            self.sku_table.setRowCount(0)
            sku_summary = self.analysis_stats.get("sku_summary") or []
            for row_idx, sku_data in enumerate(sku_summary):
                self.sku_table.insertRow(row_idx)

                num_item = QTableWidgetItem(str(row_idx + 1))
                num_item.setTextAlignment(Qt.AlignCenter)
                self.sku_table.setItem(row_idx, 0, num_item)

                self.sku_table.setItem(row_idx, 1, QTableWidgetItem(str(sku_data.get("SKU", "N/A"))))

                product = sku_data.get("Warehouse_Name", "")
                if not product or (hasattr(pd, 'isna') and pd.isna(product)):
                    product = sku_data.get("Product_Name", "N/A")
                self.sku_table.setItem(row_idx, 2, QTableWidgetItem(str(product)))

                for col_idx, key in enumerate(
                    ["Total_Quantity", "Fulfillable_Items", "Not_Fulfillable_Items"], start=3
                ):
                    val_item = QTableWidgetItem(str(sku_data.get(key, 0)))
                    val_item.setTextAlignment(Qt.AlignCenter)
                    self.sku_table.setItem(row_idx, col_idx, val_item)

            self.sku_table.resizeColumnToContents(0)
            self.sku_table.resizeColumnToContents(1)

    def _clear_statistics_view(self):
        """Clear statistics display when no analysis results."""
        if hasattr(self, 'stat_card_labels'):
            for lbl in self.stat_card_labels.values():
                lbl.setText("-")

        if hasattr(self, 'courier_cards_layout'):
            while self.courier_cards_layout.count() > 1:
                item = self.courier_cards_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        for layout_attr in ('tags_fulfillable_layout', 'tags_not_fulfillable_layout'):
            layout = getattr(self, layout_attr, None)
            if layout is not None:
                while layout.count() > 1:
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

        if hasattr(self, 'sku_table'):
            self.sku_table.setRowCount(0)

    def log_activity(self, op_type, desc):
        """Adds a new entry to the 'Activity Log' table in the UI.

        Args:
            op_type (str): The type of operation (e.g., "Session", "Analysis").
            desc (str): A description of the activity.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.activity_log_table.insertRow(0)
        self.activity_log_table.setItem(0, 0, QTableWidgetItem(current_time))
        self.activity_log_table.setItem(0, 1, QTableWidgetItem(op_type))
        self.activity_log_table.setItem(0, 2, QTableWidgetItem(desc))

    def on_table_double_clicked(self, index: QModelIndex):
        """Handles double-click events on the results table.

        A double-click on a row triggers the toggling of the fulfillment
        status for the corresponding order.

        Args:
            index (QModelIndex): The model index of the cell that was
                double-clicked.
        """
        if not index.isValid():
            return

        source_index = self.proxy_model.mapToSource(index)
        source_model = self.proxy_model.sourceModel()

        # We need the original, unfiltered dataframe for this operation
        order_number_col_idx = source_model.get_column_index("Order_Number")
        order_number = source_model.index(source_index.row(), order_number_col_idx).data()

        if order_number:
            self.actions_handler.toggle_fulfillment_status_for_order(order_number)

    def show_context_menu(self, pos: QPoint):
        """Shows a context menu for the results table view.

        The menu is populated with actions relevant to the clicked row,
        such as changing order status, copying data, or removing items/orders.

        Args:
            pos (QPoint): The position where the right-click occurred, in the
                table's viewport coordinates.
        """
        if self.analysis_results_df is None or self.analysis_results_df.empty:
            return
        table = self.sender()
        index = table.indexAt(pos)
        if index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            source_model = self.proxy_model.sourceModel()

            order_col_idx = source_model.get_column_index("Order_Number")
            sku_col_idx = source_model.get_column_index("SKU")

            order_number = source_model.index(source_index.row(), order_col_idx).data()
            sku = source_model.index(source_index.row(), sku_col_idx).data()

            if not order_number:
                return

            from PySide6.QtWidgets import QStyle
            from functools import partial

            menu = QMenu()

            # Add actions with icons from QStyle
            # Change Status
            change_status_action = QAction(
                self.style().standardIcon(QStyle.SP_BrowserReload),
                "Change Status",
                self
            )
            change_status_action.triggered.connect(
                partial(self.actions_handler.toggle_fulfillment_status_for_order, order_number)
            )
            menu.addAction(change_status_action)

            # Add Tag
            add_tag_action = QAction(
                self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                "Add Tag Manually...",
                self
            )
            add_tag_action.triggered.connect(
                partial(self.actions_handler.add_tag_manually, order_number)
            )
            menu.addAction(add_tag_action)

            # Internal Tags submenu
            tags_menu = menu.addMenu("Internal Tags")
            tags_menu.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))

            # Get tag categories from config
            tag_categories = self.active_profile_config.get("tag_categories", {})
            # Normalize to handle both v1 and v2 formats
            tag_categories = _normalize_tag_categories(tag_categories)

            for category, config in tag_categories.items():
                category_label = config.get("label", category)
                category_menu = tags_menu.addMenu(category_label)

                for tag in config.get("tags", []):
                    add_tag_action = QAction(f"Add {tag}", self)
                    # Use partial to properly bind order_number, sku and tag values
                    add_tag_action.triggered.connect(
                        partial(self._add_internal_tag, order_number, sku, tag)
                    )
                    category_menu.addAction(add_tag_action)

            menu.addSeparator()

            # Remove Item
            remove_item_action = QAction(
                self.style().standardIcon(QStyle.SP_DialogCancelButton),
                f"Remove Item {sku} from Order",
                self
            )
            remove_item_action.triggered.connect(
                partial(self.actions_handler.remove_item_from_order, order_number, sku)
            )
            menu.addAction(remove_item_action)

            # Remove Order
            remove_order_action = QAction(
                self.style().standardIcon(QStyle.SP_TrashIcon),
                f"Remove Entire Order {order_number}",
                self
            )
            remove_order_action.triggered.connect(
                partial(self.actions_handler.remove_entire_order, order_number)
            )
            menu.addAction(remove_order_action)

            menu.addSeparator()

            # Copy Order Number
            copy_order_action = QAction(
                self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                "Copy Order Number",
                self
            )
            copy_order_action.triggered.connect(
                partial(QApplication.clipboard().setText, str(order_number))
            )
            menu.addAction(copy_order_action)

            # Copy SKU
            copy_sku_action = QAction(
                self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                "Copy SKU",
                self
            )
            copy_sku_action.triggered.connect(
                partial(QApplication.clipboard().setText, str(sku))
            )
            menu.addAction(copy_sku_action)

            menu.exec(table.viewport().mapToGlobal(pos))

    def closeEvent(self, event):
        """Handles the application window being closed.

        Saves the current analysis DataFrame and visible columns to a session
        pickle file, allowing the user to restore their work later.

        Args:
            event: The close event.
        """
        # Session data is now managed by SessionManager on the server
        # No need to save local session files
        event.accept()


if __name__ == "__main__":
    if "pytest" in sys.modules or os.environ.get("CI"):
        QApplication.setPlatform("offscreen")
    app = QApplication(sys.argv)
    window = MainWindow()
    if QApplication.platformName() != "offscreen":
        window.show()
        sys.exit(app.exec())
    else:
        print("Running in offscreen mode for verification.")
