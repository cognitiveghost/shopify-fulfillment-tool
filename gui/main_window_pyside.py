import json
import logging
import os
import sys

import pandas as pd
from PySide6.QtCore import QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.actions_handler import ActionsHandler
from gui.components import show_error, toast
from gui.components.commandbar import BarState
from gui.file_handler import FileHandler
from gui.log_entry import LogEntry
from gui.log_handler import QtLogHandler
from gui.log_model import LogBufferModel
from gui.results_bridge import normalize_column_settings
from gui.selection_helper import SelectionHelper
from gui.ui_manager import UIManager
from gui.worker import Worker
from shared.atomic_write import atomic_write_json
from shopify_tool import fulfillment_history, session_state
from shopify_tool.analysis import recalculate_statistics
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import ProfileManager
from shopify_tool.session_manager import SessionManager
from shopify_tool.stock_ledger import with_stock_left
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

        self._geometry_settings = QSettings(
            "ShopifyFulfillmentTool", "MainWindowGeometry"
        )
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
        self.analysis_stats = None
        # current_state.pkl as this PC last loaded or saved it (ADR 0011).
        self._state_stamp = None
        self.threadpool = QThreadPool()
        self._client_load_workers = set()  # keeps in-flight client-switch Workers alive
        self._analysis_running = False  # Guard against duplicate analysis runs

        # Initialize new architecture managers
        self._init_managers()

        # Initialize undo manager
        self.undo_manager = UndoManager(self)

        # Initialize selection helper for bulk operations
        self.selection_helper = SelectionHelper(main_window=self)

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

    def recheck_connection(self) -> None:
        """The one way back from a degraded launch, in-session.

        GroupsManager captured base_path as a string, so a path that moved
        leaves it pointed at the old server and it has to be rebuilt.
        SessionManager holds the ProfileManager itself and follows it. ADR 0004.
        """
        if self.profile_manager.recheck_connection():
            self.groups_manager = GroupsManager(
                base_path=str(self.profile_manager.base_path)
            )
        self.connectionChanged.emit(self.is_connected())

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

            logger.info(
                "ProfileManager, SessionManager, and GroupsManager initialized successfully"
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
                self.push_tag_categories()
                self.current_client_id = client_id
                logger.info(f"Loaded configuration for CLIENT_{client_id}")

                # Sync the strategy radios (block signals to avoid spurious saves)
                if hasattr(self, "strategy_multi_item"):
                    mode = config.get("analysis_mode", "multi_first")
                    self.strategy_multi_item.blockSignals(True)
                    self.strategy_fifo.blockSignals(True)
                    if mode == "fifo":
                        self.strategy_fifo.setChecked(True)
                    else:
                        self.strategy_multi_item.setChecked(True)
                    self.strategy_multi_item.blockSignals(False)
                    self.strategy_fifo.blockSignals(False)

                # Update UI to reflect new client
                self.session_path_label.setText(
                    f"Client: CLIENT_{client_id} - No session started"
                )

                # Reset analysis data when switching clients
                self._reset_session_state()
                self.session_path = None
                self.command_bar.set_state(BarState.NO_SESSION)
                self.ui_manager._refresh_setup_panel()
                self.setup_stack.setCurrentIndex(
                    1 if self.is_connected() and self.current_client_id else 0
                )

                # Restore inventory memory checkbox state from config
                if hasattr(self, "inventory_memory_checkbox"):
                    inv_mem_cfg = config.get("inventory_memory", {})
                    self.inventory_memory_checkbox.blockSignals(True)
                    self.inventory_memory_checkbox.setChecked(
                        inv_mem_cfg.get("enabled", True)
                    )
                    self.inventory_memory_checkbox.setEnabled(True)
                    self.inventory_memory_checkbox.blockSignals(False)

                # Disable starting a new file pick until a session exists --
                # not the whole slot, which would also grey out an invalid
                # slot's recovery buttons.
                self.orders_slot.choose_button.setEnabled(False)
                self.orders_slot.choose_folder_button.setEnabled(False)
                self.stock_slot.choose_button.setEnabled(False)
                self.stock_slot.choose_folder_button.setEnabled(False)

                # Disable report buttons until new analysis
                self.run_analysis_button.setEnabled(False)
                if hasattr(self, "results_bridge"):
                    self.ui_manager.set_export_enabled(False)
                if hasattr(self, "add_product_button_tab2"):
                    self.add_product_button_tab2.setEnabled(False)

                self.log_activity("Client", f"Switched to CLIENT_{client_id}")
            else:
                logger.warning(f"Could not load configuration for CLIENT_{client_id}")
                show_error(
                    self,
                    f"CLIENT_{client_id}'s configuration couldn't be loaded",
                    "Details are in Logs.",
                )
        except Exception:
            logger.exception("Failed to load client config")
            show_error(
                self,
                f"CLIENT_{client_id}'s configuration couldn't be loaded",
                "Details are in Logs.",
            )

    def setup_logging(self):
        """Sets up the Qt-based logging handler.

        Initializes a `QtLogHandler` that emits a `LogEntry` for every record
        the root logger dispatches, routed to the Logs destination's
        Execution source.
        """
        self.log_handler = QtLogHandler()
        # Root logger level is owned by shared.logger.setup_logging
        # (called from ProfileManager, before this runs) - don't
        # override it back to INFO here, or FULFILLMENT_LOG_LEVEL=DEBUG
        # would silently have no effect.
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.entry_received.connect(self._on_log_entry)

    def _on_log_entry(self, entry):
        """A record from the root logger reaches the Execution source."""
        self.log_viewer.append(entry, LogBufferModel.EXECUTION)

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

        # Session setup card
        self.command_bar.sessionChosen.connect(self.on_session_selected)
        self.command_bar.browseAllRequested.connect(
            lambda: self.main_tabs.setCurrentIndex(2)
        )
        for slot, kind in (
            (self.orders_slot, "orders"),
            (self.stock_slot, "stock"),
        ):
            slot.chooseFileRequested.connect(
                getattr(self.file_handler, f"select_{kind}_file")
            )
            slot.chooseFolderRequested.connect(
                lambda k=kind: self.file_handler.select_folder(k)
            )
            slot.pathDropped.connect(
                lambda p, k=kind: self.file_handler.accept_dropped_path(k, p)
            )
            # Straight to the mapping page: the slot only offers this when a
            # column is unmapped, so landing on General is a search the user
            # has already told us the answer to.
            slot.mapColumnsRequested.connect(
                lambda k=kind: self.actions_handler.open_settings_window(
                    page=f"{k.capitalize()} Mapping"
                )
            )
            slot.changed.connect(self.file_handler.check_files_ready)
            slot.clearRequested.connect(lambda k=kind: self.file_handler.clear_file(k))

        # Session browser (new architecture)
        self.session_browser.session_selected.connect(self.on_session_selected)
        self.session_browser.multi_export_requested.connect(
            self.actions_handler.handle_multi_session_stock_export
        )
        self.session_browser.new_session_requested.connect(
            self.actions_handler.create_new_session
        )

        # Main actions
        self.run_analysis_button.clicked.connect(self.actions_handler.run_analysis)

        # Custom signals
        self.actions_handler.data_changed.connect(self._update_all_views)

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
            lambda: (
                self.run_analysis_button.click()
                if self.run_analysis_button.isEnabled()
                else None
            ),
        )

        # Add Ctrl+F shortcut for Filter
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_results_search)

        # Add Ctrl+Z shortcut for Undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_last_operation)

    def _focus_results_search(self):
        """Ctrl+F: the search field lives in the results document now."""
        self.main_tabs.setCurrentIndex(1)
        self.results_view.setFocus()
        self.results_bridge.focusSearchRequested.emit()

    def undo_last_operation(self):
        """Undo the last DataFrame modification."""
        if not self.undo_manager.can_undo():
            return

        success, message = self.undo_manager.undo()

        if success:
            # Reload current state from undo manager's restored DataFrame
            self._update_all_views()
            self.log_activity("Undo", message)
            self.save_session_state()

            # The button and the page's undoAvailable are both downstream of
            # can_undo(), and this is the one place that recomputes them.
            if hasattr(self, "actions_handler"):
                self.actions_handler._update_undo_button()

            # ADR 0007: a Qt toast lands behind the results view's native
            # surface, so an undo raised while that screen is showing has to
            # go into the document instead. Elsewhere the Qt toast is visible.
            results_view = getattr(self, "results_view", None)
            if results_view is not None and results_view.isVisible():
                self.results_bridge.raise_toast(message)
            else:
                toast(self, message)
        else:
            logger.error(f"Undo failed: {message}")
            show_error(self, "Undo didn't complete", "Details are in Logs.")

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

        # Session management and Settings both live in the command bar now --
        # New Session is state-owned (BarState.NO_SESSION) and Settings is in
        # the overflow, gated in _populate_overflow.

        # File loading -- gate the pick, not the whole slot (an invalid
        # slot's recovery buttons must stay usable regardless).
        self.orders_slot.choose_button.setEnabled(has_session)
        self.orders_slot.choose_folder_button.setEnabled(has_session)
        self.stock_slot.choose_button.setEnabled(has_session)
        self.stock_slot.choose_folder_button.setEnabled(has_session)

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

        # Reports and actions
        reports_enabled = has_session and has_analysis

        if hasattr(self, "results_bridge"):
            self.ui_manager.set_export_enabled(reports_enabled)
        if hasattr(self, "add_product_button_tab2"):
            self.add_product_button_tab2.setEnabled(has_analysis and has_stock)

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
        except Exception:
            logger.exception("Failed to save inventory memory toggle")
            toast(
                self,
                "Inventory memory wasn't saved. Details are in Logs.",
                role="error",
            )

    # --- Client and Session Management (New Architecture) ---
    def _load_client_data(self, client_id: str):
        """Worker-thread IO for a client switch.

        Returns (shopify_config, column_settings): the results table's saved
        column layout, normalized (Bundle 13 spec §7.3).
        """
        shopify_config = self.profile_manager.load_shopify_config(client_id)
        client_config = self.profile_manager.load_client_config(client_id) or {}
        column_settings = normalize_column_settings(
            (client_config.get("ui_settings") or {}).get("results_columns")
        )
        return shopify_config, column_settings

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
        worker.signals.finished.connect(
            lambda: self._client_load_workers.discard(worker)
        )
        self.threadpool.start(worker)

    def _on_client_data_loaded(self, client_id: str, result):
        """Apply client-switch IO results to the UI (main thread only)."""
        shopify_config, column_settings = result

        if client_id != self.current_client_id:
            # User switched again before this load finished -- discard stale result.
            logger.debug(f"Discarding stale client-load result for {client_id}")
            return

        if not shopify_config:
            logger.warning(f"Failed to load configuration for client {client_id}")
            show_error(
                self,
                f"CLIENT_{client_id}'s configuration couldn't be loaded",
                "Details are in Logs.",
            )
            return

        try:
            self.current_client_config = shopify_config

            # load_client_config() re-reads shopify_config via profile_manager --
            # now a cache hit, since _load_client_data() already warmed the mtime
            # cache above -- and applies every widget-facing side effect this
            # class depends on (active_profile_config, strategy radio sync,
            # inventory_memory_checkbox restore, per-client button enable/disable,
            # _update_all_views()). Dropping it (as a naive port of this method
            # might) would leave active_profile_config stale after every client
            # switch -- it's read throughout actions_handler.py/file_handler.py
            # for delimiters, column mappings, and tag categories.
            self.load_client_config(client_id)
            self.results_bridge.set_column_settings(column_settings)

            # load_client_config resets too, but only when the config loads.
            self._reset_session_state()
            self.session_path = None
            self.update_session_info_label()

            # Update session browser to show this client's sessions
            self.session_browser.set_client(client_id, auto_refresh=False)

            # Update the Recent Sessions quick-pick in the right panel (Tab 1)
            self.ui_manager.refresh_recent_sessions(client_id)

            self.update_ui_state()

            logger.info(f"Client {client_id} loaded successfully")

            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(f"CLIENT_{client_id} loaded", 2000)

        except Exception:
            logger.exception("Error applying loaded client data")
            show_error(self, "The client couldn't be switched", "Details are in Logs.")

    def _on_client_data_load_error(self, error):
        _exctype, value, tb = error
        logger.error(f"Error loading client data: {value}\n{tb}")
        show_error(self, "The client couldn't be switched", "Details are in Logs.")

    def schedule_results_columns_save(self, settings: dict):
        """Debounced: a drag sends a burst of layouts, the share gets one write."""
        self._pending_columns = (self.current_client_id, dict(settings))
        if not hasattr(self, "_columns_save_timer"):
            self._columns_save_timer = QTimer(self)
            self._columns_save_timer.setSingleShot(True)
            self._columns_save_timer.setInterval(500)
            self._columns_save_timer.timeout.connect(self._flush_results_columns)
        self._columns_save_timer.start()

    def _flush_results_columns(self):
        client_id, settings = self._pending_columns
        if not client_id:
            return
        # save_client_config locks the share and writes a backup on every call,
        # so a layout that came back to what is already stored writes nothing.
        if (client_id, settings) == getattr(self, "_written_columns", None):
            return
        self._written_columns = (client_id, dict(settings))
        worker = Worker(self._write_results_columns, client_id, settings)

        # A layout preference: a failed write is logged, and the next change retries.
        def failed(error):
            self._written_columns = None  # so the same layout can be retried
            logger.warning(f"The column layout wasn't saved: {error[1]}")

        worker.signals.error.connect(failed)
        self._columns_save_worker = worker  # see _client_load_worker for why
        QThreadPool.globalInstance().start(worker)

    def _write_results_columns(self, client_id: str, settings: dict):
        config = self.profile_manager.load_client_config(client_id) or {}
        config.setdefault("ui_settings", {})["results_columns"] = settings
        self.profile_manager.save_client_config(client_id, config)

    def push_tag_categories(self):
        """The profile's tag vocabulary, for the pane's "+ Tag" menu."""
        if hasattr(self, "results_bridge"):
            self.results_bridge.set_tag_categories(
                _normalize_tag_categories(
                    (self.active_profile_config or {}).get("tag_categories", {})
                )
            )

    def on_sidebar_refresh(self):
        """Handle manual client list refresh request."""
        try:
            self.client_directory.refresh()
            self.log_activity("UI", "Client list refreshed")
        except Exception:
            logger.exception("Client list refresh failed")
            show_error(self, "The client list didn't refresh", "Details are in Logs.")

    def on_session_selected(self, session_path: str):
        """Handle session selection from session browser.

        Args:
            session_path: Path to the selected session
        """
        logger.info(f"Session selected: {session_path}")
        self.load_existing_session(session_path)

    def save_session_state(self):
        """Save current analysis state to session directory.

        Saves both pickle (fast) and Excel (backup) formats.
        Only saves if session exists and analysis data is present.

        This method is called after every DataFrame modification to ensure
        state persistence across session reloads. A save another PC has made
        stale is refused, and a failed one is reported (ADR 0011).
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
            self._state_stamp = session_state.save_state(
                self.session_path,
                self.analysis_results_df,
                getattr(self, "_state_stamp", None),
            )
        except session_state.StaleSessionError:
            logger.warning(f"Refused a stale save to {self.session_path}")
            show_error(
                self,
                "Another PC changed this session",
                "Your change wasn't saved. Reopen the session from Sessions to "
                "load their changes, then make it again.",
            )
            return
        except Exception:
            logger.exception("Failed to save session state")
            show_error(
                self,
                "Your last change wasn't saved",
                "Check the connection to the server. Your next change saves "
                "everything on screen. Details are in Logs.",
            )
            return

        # History follows the saved state, not the run (ADR 0012). A failure
        # heals on the next save, which rewrites this session's rows whole.
        # ponytail: history write on the GUI thread; move to the threadpool with a
        # per-session coalescing queue if saves feel slow on the share
        try:
            fulfillment_history.record_session(
                fulfillment_history.history_path(
                    self.profile_manager, self.current_client_id
                ),
                Path(self.session_path).name,
                self.analysis_results_df,
            )
        except Exception:
            logger.exception("Failed to record fulfillment history")

        # current_state.pkl above is the state; these only mirror it, so a
        # failure here is logged, not shown.
        analysis_dir = Path(self.session_path) / "analysis"
        try:
            self.analysis_results_df.to_excel(analysis_dir / "current_state.xlsx", index=False)
            if self.analysis_stats:
                atomic_write_json(analysis_dir / "analysis_stats.json", self.analysis_stats)
        except Exception:
            logger.exception("Failed to write the session state backups")

        # The browser's Blocked column reads these counts (AUDIT-05-6).
        session_manager = getattr(self, "session_manager", None)
        if session_manager is not None:
            try:
                session_manager.update_session_info(
                    self.session_path, session_state.order_counts(self.analysis_results_df)
                )
            except Exception:
                logger.exception("Failed to update the session's order counts")

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

            # Before the read: a write landing between the two makes the next
            # save refuse needlessly, never overwrite (ADR 0011).
            self._state_stamp = session_state.state_stamp(session_path)

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
                    logger.warning(f"Failed to load pickle, trying Excel fallback: {e}")
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

    def _restore_session_inputs(self, session_path: str) -> None:
        """Point the stock path and slot at the file this session ran on.

        run_full_analysis copies both inputs into <session>/input/ under fixed
        names and records them in session_info.json. Without this, a resumed
        session had results but no stock_file_path, which left Add Product to
        Order greyed out with nothing on screen saying why. Only the stock
        file is restored -- see the loop below for why the orders file is not.
        """
        from pathlib import Path

        try:
            input_dir = self.session_manager.get_input_dir(session_path)
        except Exception:
            logger.exception("Could not resolve the session input directory")
            return

        info = self.session_manager.get_session_info(session_path) or {}
        # Stock only, deliberately. Restoring orders_file_path as well would
        # satisfy update_ui_state's has_orders and re-enable Run Analysis in a
        # resumed session -- and run_analysis reuses the open session_path, so
        # one click would overwrite that session's analysis state, discarding
        # the Add Product additions this very method exists to make reachable.
        # There is no confirm on that path. Owner's call, 2026-09-20.
        for kind, default_name in (("stock", "inventory.csv"),):
            recorded = info.get(f"{kind}_file") or default_name
            path = Path(input_dir) / recorded
            if not path.exists():
                continue
            setattr(self, f"{kind}_file_path", str(path))
            # validate_file drives the slot into its loaded or invalid face and
            # is the same call the file pickers make.
            self.file_handler.validate_file(kind)
        self.file_handler.check_files_ready()

    def _reset_session_state(self):
        """Forget the open session's orders, inputs, undo history and stamp.

        Every way into a session calls this first (AUDIT-05-2); without it the
        previous session's orders stayed loaded and exportable, and the next
        edit saved them into the new session. Leaves session_path to the
        caller.
        """
        self.analysis_results_df = None
        self.analysis_stats = None
        self._state_stamp = None
        self.orders_file_path = None
        self.stock_file_path = None
        self.orders_slot.clear()
        self.stock_slot.clear()
        if hasattr(self, "undo_manager"):
            self.undo_manager.reset_for_session()
        self._update_all_views()

    def load_existing_session(self, session_path: str):
        """Load data from an existing session.

        Args:
            session_path: Path to the session directory
        """

        try:
            self._reset_session_state()
            # Set as current session
            self.session_path = session_path
            session_name = os.path.basename(session_path)
            # Resuming a past session is the second way into SESSION; the
            # first is creating one. Both have to say so, or the bar shows
            # New Session while a session is open. Spec §3.1.
            self.command_bar.set_state(BarState.SESSION)
            # Before the analysis loads: a session without one must not keep
            # the previous session's chips.
            self.ui_manager.update_session_chips()

            # Reload undo history for this session
            if hasattr(self, "undo_manager"):
                self.undo_manager.reload_session_history()

            # Update session info labels
            self.update_session_info_label()

            # Load session info
            session_info = self.session_manager.get_session_info(session_path)

            if session_info:
                self._restore_session_inputs(session_path)

                # Try to load analysis data if it exists
                if self._load_session_analysis(session_path):
                    # Analysis loaded successfully; a session saved by an older
                    # build may hold a drifted Final_Stock (ADR 0010).
                    self.analysis_results_df = with_stock_left(self.analysis_results_df)
                    self._update_all_views()

                    # Auto-switch to Analysis Results tab (Tab 2)
                    self.main_tabs.setCurrentIndex(1)

                    self.log_activity("Session", f"Loaded session: {session_name}")
                    toast(
                        self,
                        f"Session {session_name} opened · "
                        f"{self.analysis_results_df['Order_Number'].nunique()} orders.",
                    )
                else:
                    # Session exists but no analysis yet
                    self.log_activity(
                        "Session", f"Opened session (no analysis): {session_name}"
                    )
                    toast(
                        self,
                        f"Session {session_name} opened. Run an analysis to see results.",
                        role="info",
                    )

                # Update UI state
                self.update_ui_state()

        except Exception:
            logger.exception("Failed to load session")
            show_error(self, "The session wasn't loaded", "Details are in Logs.")

    def _update_all_views(self):
        """Central slot to refresh every view after `analysis_results_df` changes.

        Statistics are recalculated here; the results document folds the line
        frame to orders and KPI numbers itself (gui/orders_view.py), so one
        push is the whole refresh.
        """
        if self.analysis_results_df is not None and not self.analysis_results_df.empty:
            try:
                self.analysis_stats = recalculate_statistics(self.analysis_results_df)
            except Exception:
                logger.exception("Failed to recalculate statistics")
                self.analysis_stats = None
        else:
            self.analysis_stats = None

        try:
            self.results_bridge.set_orders(self.analysis_results_df)
        except Exception:
            logger.exception("Failed to refresh the results document")
        finally:
            # Never skipped: a failed push must not leave the window stuck busy.
            self.ui_manager.set_ui_busy(False)

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
            toast(
                self,
                "The analysis mode wasn't saved. Details are in Logs.",
                role="error",
            )

    def log_activity(self, op_type, desc):
        """Records an operator action in the Logs destination.

        Signature is unchanged on purpose: actions_handler calls this from
        ten places and none of them should have to know the widget changed.

        Args:
            op_type (str): The type of operation (e.g., "Session", "Analysis").
            desc (str): A description of the activity.
        """
        self.log_viewer.append(
            LogEntry.activity(op_type, desc), LogBufferModel.ACTIVITY
        )

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
        # waitForDone only waits for the worker threads themselves to return;
        # it doesn't pump the event loop, so a result signal a worker already
        # queued (e.g. on_client_changed's client-load) is still sitting
        # undelivered. Deliver it now, while self and its children are still
        # alive, instead of leaving it to fire later against a torn-down
        # window (surfaced as "libshiboken: ... already deleted" in tests
        # that switch clients and close in the same run).
        QApplication.processEvents()
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
