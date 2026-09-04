import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd
from PySide6.QtCore import QModelIndex, QPoint, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.actions_handler import ActionsHandler
from gui.components.commandbar import BarState
from gui.file_handler import FileHandler
from gui.log_handler import QtLogHandler
from gui.pandas_model import FulfillmentFilterProxy
from gui.selection_helper import SelectionHelper
from gui.ui_manager import UIManager
from gui.worker import Worker
from shared.icons import icon
from shopify_tool.analysis import recalculate_statistics
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import ProfileManager
from shopify_tool.session_manager import SessionManager
from shopify_tool.tag_manager import _normalize_tag_categories
from shopify_tool.undo_manager import UndoManager

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

    # One boolean, one signal, and every control that would touch the share is
    # driven from it. See CONTEXT.md, "Connection state".
    connectionChanged = Signal(bool)

    def __init__(self):
        """Initializes the MainWindow, sets up UI, and connects signals."""
        super().__init__()
        self.setWindowTitle("Shopify Fulfillment Tool - New Architecture")

        from PySide6.QtCore import QSettings

        from shared.theme import restore_window_geometry
        self._geometry_settings = QSettings("ShopifyFulfillmentTool", "MainWindowGeometry")
        if not restore_window_geometry(self, self._geometry_settings):
            self.setGeometry(100, 100, 1100, 900)

        # Core application attributes
        self.session_path = None
        self.current_client_id = None
        self.current_client_config = None
        self.active_profile_config = {}

        self.orders_file_path = None
        self.stock_file_path = None
        self.analysis_results_df = None
        # The display projection of analysis_results_df, one row per order.
        self.orders_df = None
        self.analysis_stats = None
        self.threadpool = QThreadPool()
        self._client_load_workers = set()  # keeps in-flight client-switch Workers alive
        self._analysis_running = False  # Guard against duplicate analysis runs

        # Table display attributes
        self.all_columns = []
        self.visible_columns = []
        self.is_syncing_selection = False

        # Models
        # Parented: an unowned proxy outlives the window that made it and
        # keeps pointing at the source PandasModel Qt already freed.
        self.proxy_model = FulfillmentFilterProxy(self)

        # Initialize new architecture managers
        self._init_managers()

        # Initialize undo manager
        self.undo_manager = UndoManager(self)

        # Initialize selection helper for bulk operations
        self.selection_helper = SelectionHelper(
            table_view=None,  # Will be set after UI creation
            proxy_model=self.proxy_model,
            main_window=self,
        )

        # Initialize handlers
        self.ui_manager = UIManager(self)
        self.file_handler = FileHandler(self)
        self.actions_handler = ActionsHandler(self)

        # Setup UI and connect signals
        self.ui_manager.create_widgets()
        self.connect_signals()
        self.setup_logging()

        # Emitted once the widgets exist, so every slot has something to
        # disable. Re-emitted by the Server Connection dialog on success.
        self.connectionChanged.emit(self.is_connected())

    def is_connected(self) -> bool:
        return bool(getattr(self.profile_manager, "is_network_available", False))

    def _init_managers(self):
        """Initialize ProfileManager, SessionManager, and GroupsManager for the new architecture."""
        # ProfileManager now auto-detects environment:
        # 1. First checks FULFILLMENT_SERVER_PATH environment variable (dev mode)
        # 2. Then a path saved via the Server Connection UI
        # 3. Falls back to default production path
        # This allows seamless switching between dev and production without code changes

        # An unreachable share no longer quits the app -- the window opens
        # degraded and connectionChanged(False) drives the disabled controls.
        # The recovery prompt is still reachable: it is what "Server
        # connection..." in the overflow opens. ADR 0004.
        try:
            self.profile_manager = ProfileManager(require_connection=False)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize profile managers:\n{e!s}",
            )
            QApplication.quit()
            return

        try:
            self.session_manager = SessionManager(self.profile_manager)

            # Initialize GroupsManager
            self.groups_manager = GroupsManager(
                base_path=str(self.profile_manager.base_path)
            )

            # Initialize TableConfigManager for table customization
            from gui.table_config_manager import TableConfigManager

            self.table_config_manager = TableConfigManager(self, self.profile_manager)

            logger.info(
                "ProfileManager, SessionManager, GroupsManager, and TableConfigManager initialized successfully"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to initialize profile managers:\n{e!s}",
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
                logger.info(f"Loaded configuration for CLIENT_{client_id}")

                # Sync analysis mode combo (block signals to avoid spurious saves)
                if hasattr(self, "analysis_mode_combo"):
                    mode = config.get("analysis_mode", "multi_first")
                    idx = 1 if mode == "fifo" else 0
                    self.analysis_mode_combo.blockSignals(True)
                    self.analysis_mode_combo.setCurrentIndex(idx)
                    self.analysis_mode_combo.blockSignals(False)

                # Update UI to reflect new client
                self.session_path_label.setText(
                    f"Client: CLIENT_{client_id} - No session started"
                )

                # Enable client-specific buttons
                self.new_session_btn.setEnabled(True)
                self.settings_button.setEnabled(True)

                # Reset analysis data when switching clients
                self.analysis_results_df = None
                self.analysis_stats = None
                self.session_path = None
                self.command_bar.set_state(BarState.NO_SESSION)
                self.ui_manager._refresh_setup_panel()
                self.setup_stack.setCurrentIndex(
                    1 if self.is_connected() and self.current_client_id else 0
                )
                # Clear undo history when switching clients
                if hasattr(self, "undo_manager"):
                    self.undo_manager.reset_for_session()
                self._update_all_views()

                # Restore inventory memory checkbox state from config
                if hasattr(self, "inventory_memory_checkbox"):
                    inv_mem_cfg = config.get("inventory_memory", {})
                    self.inventory_memory_checkbox.blockSignals(True)
                    self.inventory_memory_checkbox.setChecked(
                        inv_mem_cfg.get("enabled", True)
                    )
                    self.inventory_memory_checkbox.setEnabled(True)
                    self.inventory_memory_checkbox.blockSignals(False)

                # Disable file loading buttons until a session is created/selected
                self.load_orders_btn.setEnabled(False)
                self.load_stock_btn.setEnabled(False)

                # Disable report buttons until new analysis
                self.run_analysis_button.setEnabled(False)
                if hasattr(self, "generate_reports_button"):
                    self.generate_reports_button.setEnabled(False)
                if hasattr(self, "add_product_button"):
                    self.add_product_button.setEnabled(False)

                self.log_activity("Client", f"Switched to CLIENT_{client_id}")
            else:
                QMessageBox.warning(
                    self,
                    "Configuration Error",
                    f"Could not load configuration for CLIENT_{client_id}",
                )
        except Exception as e:
            logger.exception("Failed to load client config")
            QMessageBox.critical(
                self, "Error", f"Failed to load client configuration:\n{e!s}"
            )

    def setup_logging(self):
        """Sets up the Qt-based logging handler.

        Initializes a `QtLogHandler` that emits a signal whenever a log
        message is received. This signal is connected to a slot that appends
        the message to the 'Execution Log' text box in the UI.
        """
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        # Root logger level is owned by shared.logger.setup_logging
        # (called from ProfileManager, before this runs) - don't
        # override it back to INFO here, or FULFILLMENT_LOG_LEVEL=DEBUG
        # would silently have no effect.
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.log_message_received.connect(
            self.execution_log_edit.appendPlainText
        )

    def connect_signals(self):
        """Connects all UI widget signals to their corresponding slots.

        This method centralizes all signal-slot connections for the main
        window, including button clicks, text changes, and custom signals
        from handler classes. This makes the UI event flow easier to trace.
        """
        # Client selection
        from gui.client_directory import ClientDirectory

        self.client_directory = ClientDirectory(
            self.profile_manager, self.groups_manager, parent=self
        )
        self.client_directory.loaded.connect(self.command_bar.set_clients_from)
        self.client_directory.clientCreated.connect(self.on_client_changed)
        self.command_bar.clientChanged.connect(self.on_client_changed)
        self.command_bar.clientChanged.connect(
            lambda _c: self.ui_manager._populate_overflow(self.command_bar)
        )
        self.command_bar.clientMenuRequested.connect(self._on_client_menu_requested)
        self.command_bar.createClientRequested.connect(
            lambda: self.client_directory.open_create_client_dialog(self)
        )
        self.command_bar.manageGroupsRequested.connect(
            lambda: self.client_directory.open_groups_dialog(self)
        )
        # The sidebar's refresh button is now a dropdown row: on the shared
        # file server a client added from another PC has no other way in
        # short of restarting the app.
        self.command_bar.refreshRequested.connect(self.on_sidebar_refresh)
        self.client_directory.refresh()

        # Session browser (new architecture)
        self.session_browser.session_selected.connect(self.on_session_selected)
        self.session_browser.multi_export_requested.connect(
            self.actions_handler.handle_multi_session_stock_export
        )

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
        self.add_product_button.clicked.connect(
            self.actions_handler.show_add_product_dialog
        )
        self.analysis_mode_combo.currentIndexChanged.connect(
            self._on_analysis_mode_changed
        )

        # Reports
        self.generate_reports_button.clicked.connect(
            self.actions_handler.open_generate_reports_dialog
        )

        # Table interactions
        self.tableView.customContextMenuRequested.connect(self.show_context_menu)
        self.tableView.doubleClicked.connect(self.on_table_double_clicked)
        self.order_detail_pane.lines_table.customContextMenuRequested.connect(
            self.show_line_context_menu
        )

        # Custom signals
        self.actions_handler.data_changed.connect(self._update_all_views)

        # Filter input. Typing is debounced so we don't re-scan the whole
        # DataFrame on every keystroke; the other controls fire immediately.
        self._filter_debounce = QTimer(self)
        self._filter_debounce.setSingleShot(True)
        self._filter_debounce.setInterval(200)
        self._filter_debounce.timeout.connect(self.filter_table)
        self.filter_input.textChanged.connect(self._filter_debounce.start)
        self.filter_column_selector.currentIndexChanged.connect(self.filter_table)
        self.case_sensitive_checkbox.stateChanged.connect(self.filter_table)
        self.tag_filter_combo.currentIndexChanged.connect(self.filter_table)

        # Inventory memory toggle
        if hasattr(self, "inventory_memory_checkbox"):
            self.inventory_memory_checkbox.stateChanged.connect(
                self._on_inventory_memory_toggled
            )

        # Add Ctrl+R shortcut for Run Analysis
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(
            QKeySequence("Ctrl+R"),
            self,
            lambda: self.run_analysis_button.click()
            if self.run_analysis_button.isEnabled()
            else None,
        )

        # Add Ctrl+F shortcut for Filter
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.filter_input.setFocus())

        # Add Ctrl+Z shortcut for Undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_last_operation)

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
            if hasattr(self, "undo_button"):
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
            self.analysis_results_df.loc[mask, "Internal_Tags"].apply(
                lambda t: add_tag(t, tag)
            )
        )
        self.undo_manager.record_operation(
            operation_type="add_internal_tag",
            description=description,
            params=params,
            affected_rows_before=affected_rows_before,
        )
        self.save_session_state()
        self._update_all_views()
        self.log_activity("Internal Tag", description)
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(True)
            self.undo_button.setToolTip(f"Undo: {description} (Ctrl+Z)")

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
        if (
            hasattr(self, "tag_management_panel")
            and self.tag_management_panel.isVisible()
        ):
            self.on_results_selection_changed()

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
            params={"order_number": order_number, "tag": tag},
            affected_rows_before=affected_rows_before,
        )

        # Save state and update UI
        self.save_session_state()
        self._update_all_views()
        self.log_activity("Internal Tag", f"Removed '{tag}' from order {order_number}")

        # Update undo button
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(True)
            self.undo_button.setToolTip(f"Undo: Remove Internal Tag: {tag} (Ctrl+Z)")

        # Update tag panel if visible
        if (
            hasattr(self, "tag_management_panel")
            and self.tag_management_panel.isVisible()
        ):
            self.on_results_selection_changed()

    def on_results_selection_changed(self):
        """One order row selected -> pane shows it; every selected order's
        lines go into SelectionHelper, which is what the bulk actions read."""
        from gui.orders_view import ORDER_KEY

        orders_df = getattr(self, "orders_df", None)
        if orders_df is None or orders_df.empty:
            self.order_detail_pane.clear()
            self.selection_helper.clear_selection()
            self._update_selection_bar_state()
            return

        column = orders_df.columns.get_loc(ORDER_KEY)
        selected = []
        for index in self.tableView.selectionModel().selectedRows():
            source_row = self.proxy_model.mapToSource(index).row()
            selected.append(orders_df.iat[source_row, column])

        self.selection_helper.set_selected_orders(selected)
        self._update_selection_bar_state()

        current = self.tableView.selectionModel().currentIndex()
        if not selected or not current.isValid():
            self.order_detail_pane.clear()
            return

        source_row = self.proxy_model.mapToSource(current).row()
        order_number = orders_df.iat[source_row, column]
        self.order_detail_pane.set_order(
            order_number,
            orders_df.iloc[source_row],
            self._pane_lines(order_number),
        )

    def _pane_lines(self, order_number):
        """The order's lines, minus any line-level column the client hid.

        Spec section 4: the saved column config keeps its meaning, split across
        the order table and the pane. Falls back to every column rather than
        showing an empty table if the config hides all of them.
        """
        from gui.orders_view import order_lines

        lines = order_lines(self.analysis_results_df, order_number)
        manager = getattr(self, "table_config_manager", None)
        if manager is None or lines.empty:
            return lines
        keep = [col for col in lines.columns if manager.get_column_visibility(col)]
        return lines[keep] if keep else lines

    def open_column_config_dialog(self):
        """Open the Column Configuration Dialog."""
        if not hasattr(self, "table_config_manager"):
            logger.warning("TableConfigManager not initialized")
            return

        if not hasattr(self, "current_client_id") or not self.current_client_id:
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client before configuring columns.",
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
        if hasattr(self, "ui_manager"):
            self.ui_manager.update_hidden_columns_indicator()

    def _update_selection_bar_state(self):
        """Show the bar, and name what is selected, or hide it."""
        if not hasattr(self, "selection_bar"):
            return

        orders_count, items_count = self.selection_helper.get_selection_summary()
        self.selection_bar.set_selection(
            "" if orders_count == 0
            else f"{orders_count} orders · {items_count} items selected"
        )

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
        has_orders = bool(getattr(self, "orders_file_path", None))
        has_stock = bool(getattr(self, "stock_file_path", None))
        has_analysis = (
            hasattr(self, "analysis_results_df")
            and self.analysis_results_df is not None
        )

        # Session management
        self.new_session_btn.setEnabled(has_client)

        # Settings button (Tab 1 version)
        if hasattr(self, "settings_button"):
            self.settings_button.setEnabled(has_client)
        # Settings button (Tab 2 version)
        if hasattr(self, "settings_button_tab2"):
            self.settings_button_tab2.setEnabled(has_client)

        # File loading
        self.load_orders_btn.setEnabled(has_session)
        self.load_stock_btn.setEnabled(has_session)

        # Run Analysis button — memory mode allows skipping the stock file ONLY
        # when memory is enabled AND actually holds a stored stock snapshot.
        # An enabled-but-empty memory has no stock to reconstruct from, so every
        # order would be marked Not Fulfillable — require a stock file instead.
        inv_memory_has_skus = (
            hasattr(self, "inventory_memory_checkbox")
            and self.inventory_memory_checkbox.isChecked()
            and bool(
                (self.active_profile_config or {})
                .get("inventory_memory", {})
                .get("skus")
            )
        )
        self.run_analysis_button.setEnabled(
            has_session and has_orders and (has_stock or inv_memory_has_skus)
        )

        # Reports and actions (both Tab 1 and Tab 2 versions)
        reports_enabled = has_session and has_analysis

        # Tab 1 buttons
        if hasattr(self, "generate_reports_button"):
            self.generate_reports_button.setEnabled(reports_enabled)
        if hasattr(self, "add_product_button"):
            self.add_product_button.setEnabled(has_analysis)

        # Tab 2 buttons
        if hasattr(self, "generate_reports_button_tab2"):
            self.generate_reports_button_tab2.setEnabled(reports_enabled)
        if hasattr(self, "add_product_button_tab2"):
            self.add_product_button_tab2.setEnabled(has_analysis)
        if hasattr(self, "configure_columns_button_tab2"):
            self.configure_columns_button_tab2.setEnabled(has_analysis)

        # Open Session Folder button (enabled when session exists)
        if hasattr(self, "open_session_folder_button"):
            self.open_session_folder_button.setEnabled(has_session)

        # Update status bar
        if has_analysis:
            self.statusBar().showMessage("Analysis complete - ready for export", 5000)
        elif has_session:
            self.statusBar().showMessage("Session active - load files to begin", 5000)
        elif has_client:
            self.statusBar().showMessage(
                "Client selected - create or open a session", 5000
            )
        else:
            self.statusBar().showMessage("Ready - select a client to begin", 5000)

    def _on_inventory_memory_toggled(self, state: int):
        """Persist the inventory memory enabled flag when the checkbox is toggled."""
        if not self.current_client_id or not self.active_profile_config:
            return
        try:
            enabled = bool(state)
            inv_mem = self.active_profile_config.get("inventory_memory", {})
            inv_mem["enabled"] = enabled
            self.active_profile_config["inventory_memory"] = inv_mem
            self.profile_manager.save_shopify_config(
                self.current_client_id, self.active_profile_config
            )
            logger.info(
                f"Inventory memory {'enabled' if enabled else 'disabled'} for CLIENT_{self.current_client_id}"
            )
            # Re-evaluate run button (memory mode may unlock it)
            if hasattr(self, "update_ui_state"):
                self.update_ui_state()
        except Exception as e:
            logger.warning(f"Failed to save inventory memory toggle: {e}")

    # --- Client and Session Management (New Architecture) ---
    def _load_client_data(self, client_id: str):
        """Pure IO for a client switch -- no UI calls, safe to run in a Worker.

        Returns (shopify_config, table_config). table_config is None if
        table_config_manager isn't set up yet (mirrors the existing
        `hasattr(self, "table_config_manager")` guard).
        """
        shopify_config = self.profile_manager.load_shopify_config(client_id)
        table_config = None
        if hasattr(self, "table_config_manager"):
            table_config = self.table_config_manager.load_config(client_id)
        return shopify_config, table_config

    def _on_client_menu_requested(self, client_id: str, position):
        """The bar has no ProfileManager, so it asks for the menu here."""
        self.client_directory.menu_for(client_id, self).exec(position)

    def on_client_changed(self, client_id: str):
        """Handle client selection change.

        Args:
            client_id: Newly selected client ID
        """
        logger.info(f"Client changed to: {client_id}")

        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(f"Loading CLIENT_{client_id}...", 5000)

        if hasattr(self, "command_bar") and (
            self.command_bar.current_client() != client_id
        ):
            self.command_bar.set_current_client(client_id)

        self.current_client_id = client_id

        worker = Worker(self._load_client_data, client_id)
        worker.signals.result.connect(
            lambda result, cid=client_id: self._on_client_data_loaded(cid, result)
        )
        worker.signals.error.connect(self._on_client_data_load_error)
        # Keep a strong reference until the worker finishes: a bare local var
        # gets garbage-collected the instant this method returns, which -- in
        # this PySide6 build -- destroys the QRunnable's unparented
        # WorkerSignals object before its already-queued cross-thread result
        # signal is dispatched to the main thread, silently dropping the
        # client switch. Verified via a minimal repro; the existing bare
        # `worker = Worker(...)` pattern elsewhere in this codebase
        # (e.g. barcode_generator_widget.py) has the same latent exposure.
        # Tracked in a set, not a single slot: a second switch before this one
        # finishes must not drop the first worker's reference out from under it.
        self._client_load_workers.add(worker)
        worker.signals.finished.connect(lambda: self._client_load_workers.discard(worker))
        self.threadpool.start(worker)

    def _on_client_data_loaded(self, client_id: str, result):
        """Apply client-switch IO results to the UI (main thread only)."""
        shopify_config, table_config = result

        if client_id != self.current_client_id:
            # User switched again before this load finished -- discard stale result.
            logger.debug(f"Discarding stale client-load result for {client_id}")
            return

        if not shopify_config:
            QMessageBox.warning(
                self,
                "Configuration Error",
                f"Failed to load configuration for client {client_id}",
            )
            return

        try:
            self.current_client_config = shopify_config

            # load_client_config() re-reads shopify_config via profile_manager --
            # now a cache hit, since _load_client_data() already warmed the mtime
            # cache above -- and applies every widget-facing side effect this
            # class depends on (active_profile_config, analysis_mode_combo sync,
            # inventory_memory_checkbox restore, per-client button enable/disable,
            # _update_all_views()). Dropping it (as a naive port of this method
            # might) would leave active_profile_config stale after every client
            # switch -- it's read throughout actions_handler.py/file_handler.py
            # for delimiters, column mappings, and tag categories.
            self.load_client_config(client_id)

            if table_config is not None:
                logger.info(f"Table configuration loaded for CLIENT_{client_id}")

            # Clear currently loaded files (they're for different client)
            self.orders_file_path = None
            self.stock_file_path = None
            self.orders_file_path_label.setText("No file loaded")
            self.stock_file_path_label.setText("No file loaded")
            self.orders_file_status_label.setText("")
            self.stock_file_status_label.setText("")

            # Clear session
            self.session_path = None
            if hasattr(self, "undo_manager"):
                self.undo_manager.reset_for_session()
            self.update_session_info_label()

            # Update session browser to show this client's sessions
            self.session_browser.set_client(client_id, auto_refresh=False)

            # Update the Recent Sessions quick-pick in the right panel (Tab 1)
            self.ui_manager.refresh_recent_sessions(client_id)

            self.update_ui_state()

            logger.info(f"Client {client_id} loaded successfully")

            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(f"CLIENT_{client_id} loaded", 2000)

        except Exception as e:
            logger.exception("Error applying loaded client data")
            QMessageBox.critical(self, "Error", f"Failed to change client: {e!s}")

    def _on_client_data_load_error(self, error):
        _exctype, value, tb = error
        logger.error(f"Error loading client data: {value}\n{tb}")
        QMessageBox.critical(self, "Error", f"Failed to change client: {value!s}")

    def on_sidebar_refresh(self):
        """Handle manual client list refresh request."""
        try:
            self.client_directory.refresh()
            self.log_activity("UI", "Client list refreshed")
        except Exception as e:
            logger.exception("Client list refresh failed")
            QMessageBox.warning(self, "Refresh Error", str(e))

    def on_session_selected(self, session_path: str):
        """Handle session selection from session browser.

        Args:
            session_path: Path to the selected session
        """
        logger.info(f"Session selected: {session_path}")

        reply = QMessageBox.question(
            self,
            "Open Session",
            f"Do you want to open this session?\n\n{session_path}\n\n"
            f"This will load any existing analysis data from the session.",
            QMessageBox.Yes | QMessageBox.No,
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
            logger.debug("No active session - skipping save_session_state")
            return

        if self.analysis_results_df is None or self.analysis_results_df.empty:
            logger.debug("No analysis data to save - skipping save_session_state")
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
            logger.info(f"Saving session state to {pkl_path}")
            self.analysis_results_df.to_pickle(pkl_path)

            # Save DataFrame to Excel (backup, human-readable)
            logger.info(f"Saving session state backup to {xlsx_path}")
            self.analysis_results_df.to_excel(xlsx_path, index=False)

            # Save statistics to JSON
            if self.analysis_stats:
                logger.info(f"Saving statistics to {stats_path}")
                with open(stats_path, "w", encoding="utf-8") as f:
                    json.dump(self.analysis_stats, f, indent=2, ensure_ascii=False)

            logger.info("Session state saved successfully")

        except Exception:
            # Don't block UI if save fails - just log the error
            logger.exception("Failed to save session state")

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
                    logger.info(f"Loading session state from pickle: {pkl_path}")
                    self.analysis_results_df = pd.read_pickle(pkl_path)

                    # Load statistics from JSON if available
                    stats_path = analysis_dir / "analysis_stats.json"
                    if stats_path.exists():
                        logger.info(f"Loading statistics from: {stats_path}")
                        with open(stats_path, "r", encoding="utf-8") as f:
                            self.analysis_stats = json.load(f)
                    else:
                        # Recalculate if stats file missing
                        logger.info("Statistics file not found - recalculating")
                        self.analysis_stats = recalculate_statistics(
                            self.analysis_results_df
                        )

                    logger.info(
                        f"Loaded {len(self.analysis_results_df)} rows from current_state.pkl"
                    )
                    return True

                except Exception as e:
                    logger.warning(
                        f"Failed to load pickle, trying Excel fallback: {e}"
                    )
                    # Continue to fallback options

            # Priority 2: Try loading from current_state.xlsx
            xlsx_path = analysis_dir / "current_state.xlsx"
            if xlsx_path.exists():
                try:
                    logger.info(f"Loading session state from Excel: {xlsx_path}")
                    self.analysis_results_df = pd.read_excel(xlsx_path)

                    # Load or recalculate statistics
                    stats_path = analysis_dir / "analysis_stats.json"
                    if stats_path.exists():
                        with open(stats_path, "r", encoding="utf-8") as f:
                            self.analysis_stats = json.load(f)
                    else:
                        self.analysis_stats = recalculate_statistics(
                            self.analysis_results_df
                        )

                    logger.info(
                        f"Loaded {len(self.analysis_results_df)} rows from current_state.xlsx"
                    )
                    return True

                except Exception as e:
                    logger.warning(
                        f"Failed to load current_state.xlsx, trying original report: {e}"
                    )
                    # Continue to fallback

            # Priority 3: Fallback to original analysis_report.xlsx
            # Check for analysis_data.json first (indicates analysis was completed)
            analysis_data_file = analysis_dir / "analysis_data.json"

            if not analysis_data_file.exists():
                logger.warning(f"Analysis data not found: {analysis_data_file}")
                return False

            logger.info(f"Found analysis data: {analysis_data_file}")

            # Load the actual Excel report to get DataFrame
            report_file = analysis_dir / "fulfillment_analysis.xlsx"

            if not report_file.exists():
                # Try alternative name
                report_file = analysis_dir / "analysis_report.xlsx"

            if not report_file.exists():
                logger.warning(f"Analysis report not found: {report_file}")
                return False

            logger.info(f"Loading analysis from original report: {report_file}")

            # Load DataFrame from Excel
            self.analysis_results_df = pd.read_excel(report_file)

            # Recalculate statistics (no saved stats for original report)
            self.analysis_stats = recalculate_statistics(self.analysis_results_df)

            logger.info(f"Loaded {len(self.analysis_results_df)} rows from session")
            return True

        except Exception:
            logger.exception("Failed to load session analysis")
            return False

    def load_existing_session(self, session_path: str):
        """Load data from an existing session.

        Args:
            session_path: Path to the session directory
        """

        try:
            # Set as current session
            self.session_path = session_path
            session_name = os.path.basename(session_path)

            # Reload undo history for this session
            if hasattr(self, "undo_manager"):
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
                        f"Analysis data: {len(self.analysis_results_df)} rows",
                    )
                else:
                    # Session exists but no analysis yet
                    self.log_activity(
                        "Session", f"Opened session (no analysis): {session_name}"
                    )
                    QMessageBox.information(
                        self,
                        "Session Opened",
                        f"Session opened:\n{session_name}\n\n"
                        f"No analysis data found. You can run a new analysis.",
                    )

                # Update UI state
                self.update_ui_state()

        except Exception as e:
            logger.exception("Failed to load session")
            QMessageBox.critical(self, "Error", f"Failed to load session:\n{e!s}")

    def filter_table(self):
        """Applies the current filter settings to the results table view.

        Reads the filter text, selected column, and case sensitivity setting
        from the UI controls and applies them to the proxy model. The text
        filter and tag filter are combined (ANDed), so the user can narrow by
        tag and text at the same time.
        """
        selected_tag = None
        if hasattr(self, "tag_filter_combo"):
            selected_tag = self.tag_filter_combo.currentData()

        # The proxy resolves df_col positionally against the frame the table
        # shows -- the order frame. Resolve by name, never by combo position:
        # the two frames have different column sets and different order.
        df_col = -1
        column_name = self.filter_column_selector.currentData()
        orders_df = getattr(self, "orders_df", None)
        if column_name and orders_df is not None and column_name in orders_df.columns:
            df_col = orders_df.columns.get_loc(column_name)

        self.proxy_model.set_text_filter(
            self.filter_input.text(),
            df_col=df_col,
            case_sensitive=self.case_sensitive_checkbox.isChecked(),
        )
        self.proxy_model.set_tag_filter(selected_tag)
        self.ui_manager.update_filter_count()

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
            except Exception:
                logger.exception("Failed to recalculate statistics")
                self.analysis_stats = None
                self._clear_statistics_view()
        else:
            # No analysis results - clear statistics
            self.analysis_stats = None
            self._clear_statistics_view()
            self.ui_manager.update_results_table(pd.DataFrame())

        self.ui_manager.update_kpi_strip()

        # Populate filter dropdown
        # Offer the columns the table actually shows. Line-level columns are not
        # here on purpose -- they are in the pane, and "All Columns" still finds
        # an order by its SKUs through the hidden search column.
        self.filter_column_selector.clear()
        self.filter_column_selector.addItem("All Columns", None)
        orders_df = getattr(self, "orders_df", None)
        if orders_df is not None and not orders_df.empty:
            from gui.orders_view import HIDDEN_COLUMNS

            for col in orders_df.columns:
                if col not in HIDDEN_COLUMNS:
                    self.filter_column_selector.addItem(col, col)
        self.ui_manager.set_ui_busy(False)
        # The column manager button is enabled within update_results_table

    def update_statistics_tab(self):
        """Populates the 'Statistics' tab with the latest analysis data."""
        if not self.analysis_stats:
            return

        # === 1. Session Totals cards ===
        if hasattr(self, "stat_card_labels"):
            for key, lbl in self.stat_card_labels.items():
                lbl.setText(str(self.analysis_stats.get(key, "-")))

        # === 2. Courier cards ===
        if hasattr(self, "courier_cards_layout"):
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
            if self.active_profile_config
            else {}
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
        _populate_tag_layout(
            "tags_not_fulfillable_layout", "tags_breakdown_not_fulfillable"
        )

        # === 4. SKU table ===
        if hasattr(self, "sku_table"):
            self.sku_table.setSortingEnabled(False)
            self.sku_table.setRowCount(0)
            sku_summary = self.analysis_stats.get("sku_summary") or []
            for row_idx, sku_data in enumerate(sku_summary):
                self.sku_table.insertRow(row_idx)

                # Numeric columns store real ints, not strings -- a
                # QTableWidgetItem built from str() sorts lexicographically,
                # which orders 10 before 2.
                num_item = QTableWidgetItem()
                num_item.setData(Qt.DisplayRole, row_idx + 1)
                num_item.setTextAlignment(Qt.AlignCenter)
                self.sku_table.setItem(row_idx, 0, num_item)

                self.sku_table.setItem(
                    row_idx, 1, QTableWidgetItem(str(sku_data.get("SKU", "N/A")))
                )

                product = sku_data.get("Warehouse_Name", "")
                if not product or (hasattr(pd, "isna") and pd.isna(product)):
                    product = sku_data.get("Product_Name", "N/A")
                self.sku_table.setItem(row_idx, 2, QTableWidgetItem(str(product)))

                for col_idx, key in enumerate(
                    ["Total_Quantity", "Fulfillable_Items", "Not_Fulfillable_Items"],
                    start=3,
                ):
                    raw = sku_data.get(key, 0)
                    if raw is None or (hasattr(pd, "isna") and pd.isna(raw)):
                        raw = 0
                    val_item = QTableWidgetItem()
                    val_item.setData(Qt.DisplayRole, int(raw))
                    val_item.setTextAlignment(Qt.AlignCenter)
                    self.sku_table.setItem(row_idx, col_idx, val_item)

            self.sku_table.resizeColumnToContents(0)
            self.sku_table.resizeColumnToContents(1)
            self.sku_table.setSortingEnabled(True)
            if hasattr(self, "sku_search_input"):
                self.sku_search_input.clear()

    def _on_sku_search_changed(self, text: str):
        """Filter the SKU Summary table by SKU/product substring."""
        text = text.strip().lower()
        for row in range(self.sku_table.rowCount()):
            sku_item = self.sku_table.item(row, 1)
            product_item = self.sku_table.item(row, 2)
            sku_text = sku_item.text().lower() if sku_item else ""
            product_text = product_item.text().lower() if product_item else ""
            matches = not text or text in sku_text or text in product_text
            self.sku_table.setRowHidden(row, not matches)

    def _clear_statistics_view(self):
        """Clear statistics display when no analysis results."""
        if hasattr(self, "stat_card_labels"):
            for lbl in self.stat_card_labels.values():
                lbl.setText("-")

        if hasattr(self, "courier_cards_layout"):
            while self.courier_cards_layout.count() > 1:
                item = self.courier_cards_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        for layout_attr in ("tags_fulfillable_layout", "tags_not_fulfillable_layout"):
            layout = getattr(self, layout_attr, None)
            if layout is not None:
                while layout.count() > 1:
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

        if hasattr(self, "sku_table"):
            self.sku_table.setRowCount(0)

    def _on_analysis_mode_changed(self, index: int):
        """Save the analysis mode selection to shopify_config when the combo changes."""
        if not self.current_client_id:
            return
        mode = "fifo" if index == 1 else "multi_first"
        self.active_profile_config["analysis_mode"] = mode
        try:
            self.profile_manager.save_shopify_config(
                self.current_client_id, self.active_profile_config
            )
            logger.debug(
                f"Saved analysis_mode={mode!r} for CLIENT_{self.current_client_id}"
            )
        except Exception:
            logger.exception("Failed to save analysis_mode")

    def log_activity(self, op_type, desc):
        """Adds a new entry to the 'Activity Log' table in the UI.

        Args:
            op_type (str): The type of operation (e.g., "Session", "Analysis").
            desc (str): A description of the activity.
        """
        current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
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

        orders_df = getattr(self, "orders_df", None)
        if orders_df is None or orders_df.empty:
            return

        source_row = self.proxy_model.mapToSource(index).row()
        order_number = orders_df.iat[source_row, orders_df.columns.get_loc("Order_Number")]

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
        if not index.isValid():
            return

        orders_df = getattr(self, "orders_df", None)
        if orders_df is None or orders_df.empty:
            return

        source_row = self.proxy_model.mapToSource(index).row()
        order_number = orders_df.iat[source_row, orders_df.columns.get_loc("Order_Number")]

        if not order_number:
            return

        from functools import partial

        menu = QMenu()

        # Change Status
        change_status_action = QAction(
            icon("refresh-cw"),
            "Change Status",
            self,
        )
        change_status_action.triggered.connect(
            partial(
                self.actions_handler.toggle_fulfillment_status_for_order,
                order_number,
            )
        )
        menu.addAction(change_status_action)

        # Add Tag
        add_tag_action = QAction(
            icon("tag"),
            "Add Tag Manually...",
            self,
        )
        add_tag_action.triggered.connect(
            partial(self.actions_handler.add_tag_manually, order_number)
        )
        menu.addAction(add_tag_action)

        # Internal Tags submenu
        tags_menu = menu.addMenu("Internal Tags")
        tags_menu.setIcon(icon("tags"))

        # Get tag categories from config
        tag_categories = self.active_profile_config.get("tag_categories", {})
        # Normalize to handle both v1 and v2 formats
        tag_categories = _normalize_tag_categories(tag_categories)

        for category, config in tag_categories.items():
            category_label = config.get("label", category)
            category_menu = tags_menu.addMenu(category_label)

            for tag in config.get("tags", []):
                add_tag_action = QAction(f"Add {tag}", self)
                add_tag_action.triggered.connect(
                    partial(self.add_internal_tag_to_order, order_number, tag)
                )
                category_menu.addAction(add_tag_action)

        menu.addSeparator()

        # Remove Order
        remove_order_action = QAction(
            icon("trash-2"),
            f"Remove Entire Order {order_number}",
            self,
        )
        remove_order_action.triggered.connect(
            partial(self.actions_handler.remove_entire_order, order_number)
        )
        menu.addAction(remove_order_action)

        menu.addSeparator()

        # Copy Order Number
        copy_order_action = QAction(
            icon("copy"),
            "Copy Order Number",
            self,
        )
        copy_order_action.triggered.connect(
            partial(QApplication.clipboard().setText, str(order_number))
        )
        menu.addAction(copy_order_action)

        menu.exec(table.viewport().mapToGlobal(pos))

    def show_line_context_menu(self, pos: QPoint):
        """Per-line actions, on the line itself.

        The old table-level version had to guess which line a right-click on an
        order meant, and carried a row snapshot to notice when it had guessed on
        a row that moved. The snapshot guard stays -- it now guards a click on
        the thing it acts on.
        """
        from functools import partial

        table = self.order_detail_pane.lines_table
        index = table.indexAt(pos)
        if not index.isValid():
            return

        lines = table.model()._dataframe
        row = index.row()
        sku = lines.iloc[row]["SKU"]
        order_number = self.order_detail_pane._order_number
        row_label = lines.index[row]
        row_position = self.analysis_results_df.index.get_loc(row_label)
        row_snapshot = self.analysis_results_df.loc[row_label].to_dict()

        menu = QMenu()
        remove_item_action = QAction(
            icon("circle-minus"), f"Remove Item {sku} from Order", self
        )
        remove_item_action.triggered.connect(
            partial(
                self.actions_handler.remove_item_from_order,
                order_number,
                sku,
                row_position,
                row_snapshot,
            )
        )
        menu.addAction(remove_item_action)

        copy_sku_action = QAction(icon("copy"), f"Copy SKU {sku}", self)
        copy_sku_action.triggered.connect(
            lambda: QApplication.clipboard().setText(str(sku))
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
        from shared.theme import save_window_geometry
        try:
            save_window_geometry(self, self._geometry_settings)
        except Exception as e:
            logger.warning(f"Failed to save window geometry: {e}")
        # Session data is now managed by SessionManager on the server
        # No need to save local session files
        # Give background workers (e.g. stats recording) a bounded window to
        # finish their network I/O so closing right after an analysis run
        # doesn't kill a write mid-flight -- bounded so a hung write can't
        # hang shutdown.
        self.threadpool.waitForDone(2000)
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
