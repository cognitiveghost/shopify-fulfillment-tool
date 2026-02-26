import os
import logging
from datetime import datetime
import pandas as pd

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QInputDialog

from gui.worker import Worker
from shopify_tool import core
from shopify_tool.analysis import toggle_order_fulfillment
from shopify_tool import packing_lists
from shopify_tool import stock_export
from shopify_tool.session_manager import SessionManagerError
from gui.settings_window_pyside import SettingsWindow
from gui.report_selection_dialog import ReportSelectionDialog
from gui.tag_categories_dialog import TagCategoriesDialog


class ActionsHandler(QObject):
    """Handles application logic triggered by user actions from the UI.

    This class acts as an intermediary between the `MainWindow` (UI) and the
    backend `shopify_tool` modules. It contains slots that are connected to
    UI widget signals (e.g., button clicks). When a signal is received, the
    handler executes the corresponding application logic, such as running an
    analysis, generating a report, or modifying data.

    It uses a `QThreadPool` to run long-running tasks (like analysis and
    report generation) in the background to keep the UI responsive.

    Signals:
        data_changed: Emitted whenever the main analysis DataFrame is modified,
                      signaling the UI to refresh its views.

    Attributes:
        mw (MainWindow): A reference to the main window instance.
        log (logging.Logger): A logger for this class.
    """

    data_changed = Signal()

    def __init__(self, main_window):
        """Initializes the ActionsHandler.

        Args:
            main_window (MainWindow): The main window instance that this
                handler will manage actions for.
        """
        super().__init__()
        self.mw = main_window
        self.log = logging.getLogger(__name__)

    def create_new_session(self):
        """Creates a new session using SessionManager.

        Uses the SessionManager to create a new session for the current client.
        Upon successful creation, it enables the file loading buttons in the UI.
        """
        if not self.mw.current_client_id:
            QMessageBox.warning(
                self.mw,
                "No Client Selected",
                "Please select a client before creating a session."
            )
            return

        try:
            # Show progress dialog during session creation (can be slow on UNC paths)
            from PySide6.QtWidgets import QProgressDialog
            from PySide6.QtCore import Qt
            progress = QProgressDialog("Creating new session...", None, 0, 0, self.mw)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("New Session")
            progress.show()

            try:
                # Use SessionManager to create session
                session_path = self.mw.session_manager.create_session(self.mw.current_client_id)
            finally:
                progress.close()

            self.mw.session_path = session_path

            # Update session info labels
            if hasattr(self.mw, 'update_session_info_label'):
                self.mw.update_session_info_label()

            # Refresh session browser to show the new session
            if hasattr(self.mw, 'session_browser'):
                self.mw.session_browser.refresh_sessions()

            # Refresh session browser widget in right panel (Tab 1)
            if hasattr(self.mw, 'session_browser_widget'):
                self.mw.session_browser_widget.refresh_sessions()

            # Update UI state
            if hasattr(self.mw, 'update_ui_state'):
                self.mw.update_ui_state()

            session_name = os.path.basename(session_path)
            self.mw.log_activity("Session", f"New session created: {session_name}")
            self.log.info(f"New session created: {session_path}")

            QMessageBox.information(
                self.mw,
                "Session Created",
                f"New session created successfully:\n\n{session_name}\n\n"
                f"You can now load Orders and Stock files."
            )

        except SessionManagerError as e:
            self.log.error(f"Session manager error creating session: {e}", exc_info=True)
            QMessageBox.critical(
                self.mw,
                "Session Error",
                f"Could not create a new session.\n\n{e}"
            )
        except (OSError, PermissionError) as e:
            self.log.error(f"File system error creating session: {e}")
            QMessageBox.critical(
                self.mw,
                "File System Error",
                f"Could not create session due to file system error.\n\n{e}"
            )
        except Exception as e:
            self.log.error(f"Unexpected error creating new session: {e}", exc_info=True)
            QMessageBox.critical(
                self.mw,
                "Unexpected Error",
                f"An unexpected error occurred.\n\nError: {e}"
            )

    def run_analysis(self):
        """Triggers the main fulfillment analysis in a background thread.

        It creates a `Worker` to run the `core.run_full_analysis` function,
        preventing the UI from freezing. It connects the worker's signals
        to the appropriate slots for handling completion or errors.
        """
        if not self.mw.session_path:
            QMessageBox.critical(self.mw, "Session Error", "Please create a new session before running an analysis.")
            return

        if not self.mw.current_client_id:
            QMessageBox.critical(self.mw, "Client Error", "No client selected.")
            return

        # Prevent double-run: if UI is already busy, analysis is still running
        if hasattr(self.mw, '_analysis_running') and self.mw._analysis_running:
            self.log.warning("Analysis already in progress — ignoring duplicate run request")
            return

        self.mw._analysis_running = True
        self.mw.ui_manager.set_ui_busy(True)
        self.log.info("Starting analysis thread.")
        stock_delimiter = self.mw.active_profile_config.get("settings", {}).get("stock_csv_delimiter", ";")
        orders_delimiter = self.mw.active_profile_config.get("settings", {}).get("orders_csv_delimiter", ",")

        worker = Worker(
            core.run_full_analysis,
            self.mw.stock_file_path,
            self.mw.orders_file_path,
            None,  # output_dir_path (not used in session mode)
            stock_delimiter,
            orders_delimiter,
            self.mw.active_profile_config,
            client_id=self.mw.current_client_id,
            session_manager=self.mw.session_manager,
            profile_manager=self.mw.profile_manager,
            session_path=self.mw.session_path,
        )
        worker.signals.result.connect(self.on_analysis_complete)
        worker.signals.error.connect(self.on_task_error)
        worker.signals.finished.connect(self._on_analysis_finished)
        self.mw.threadpool.start(worker)

    def _on_analysis_finished(self):
        """Reset analysis-running guard and update UI after analysis finishes."""
        self.mw._analysis_running = False
        self.mw.ui_manager.set_ui_busy(False)

    def on_analysis_complete(self, result):
        """Handles the 'result' signal from the analysis worker thread.

        If the analysis was successful, it updates the main DataFrame,
        emits the `data_changed` signal to refresh the UI, and logs the
        activity. If it failed, it displays a critical error message.

        Args:
            result (tuple): The tuple returned by `core.run_full_analysis`.
        """
        self.log.info("Analysis thread finished.")
        success, result_msg, df, stats = result
        if success:
            self.mw.analysis_results_df = df
            self.mw.analysis_stats = stats
            self.data_changed.emit()
            self.mw.log_activity("Analysis", f"Analysis complete. Report saved to: {result_msg}")

            # ========================================
            # NEW: RECORD STATISTICS TO SERVER
            # ========================================
            try:
                from pathlib import Path
                from shared.stats_manager import StatsManager

                self.log.info("Recording analysis statistics to server...")

                stats_mgr = StatsManager(
                    base_path=str(self.mw.profile_manager.base_path)
                )

                # Get session info
                session_name = Path(self.mw.session_path).name if self.mw.session_path else "unknown"

                # Count unique orders and items
                orders_count = len(df['Order_Number'].unique()) if 'Order_Number' in df.columns else 0
                items_count = len(df)

                # Calculate fulfillable orders for metadata
                fulfillable_orders = 0
                if 'Order_Fulfillment_Status' in df.columns:
                    fulfillable_df = df[df['Order_Fulfillment_Status'] == 'Fulfillable']
                    fulfillable_orders = len(fulfillable_df['Order_Number'].unique()) if not fulfillable_df.empty else 0

                # Record to stats
                stats_mgr.record_analysis(
                    client_id=self.mw.current_client_id,
                    session_id=session_name,
                    orders_count=orders_count,
                    metadata={
                        "items_count": items_count,
                        "fulfillable_orders": fulfillable_orders
                    }
                )

                self.log.info(f"Statistics recorded: {orders_count} orders, {items_count} items, {fulfillable_orders} fulfillable")

            except Exception as e:
                # Don't fail the analysis if stats recording fails
                self.log.error(f"Failed to record statistics: {e}", exc_info=True)
                # Continue with normal flow
            # ========================================
            # END STATISTICS RECORDING
            # ========================================

            # Update sequential order map after analysis
            try:
                from shopify_tool.sequential_order import generate_sequential_order_map

                generate_sequential_order_map(
                    self.mw.analysis_results_df,
                    Path(self.mw.session_path),
                    force_regenerate=False  # Preserve existing numbering
                )
            except Exception as e:
                self.log.error(f"Failed to update sequential order map: {e}")

            # Auto-switch to Analysis Results tab (Tab 2)
            if hasattr(self.mw, 'main_tabs'):
                self.mw.main_tabs.setCurrentIndex(1)

            # Update UI state
            if hasattr(self.mw, 'update_ui_state'):
                self.mw.update_ui_state()

            QMessageBox.information(
                self.mw,
                "Analysis Complete",
                f"Analysis completed successfully!\n\n"
                f"Results are now visible in the Analysis Results tab."
            )
        else:
            self.log.error(f"Analysis failed: {result_msg}")
            QMessageBox.critical(self.mw, "Analysis Error", f"An error occurred during analysis:\n{result_msg}")

    def on_task_error(self, error):
        """Handles the 'error' signal from any worker thread.

        Logs the exception and displays a critical error message to the user.

        Args:
            error (tuple): A tuple containing the exception type, value, and
                traceback.
        """
        exctype, value, tb = error
        self.log.error(f"An unexpected error occurred in a background task: {value}\n{tb}", exc_info=True)
        msg = f"An unexpected error occurred in a background task:\n{value}\n\nTraceback:\n{tb}"
        QMessageBox.critical(self.mw, "Task Exception", msg)

    def open_settings_window(self):
        """Opens the settings window for the active client."""
        if not self.mw.current_client_id:
            QMessageBox.warning(
                self.mw,
                "No Client Selected",
                "Please select a client first."
            )
            return

        # Reload fresh config
        try:
            fresh_config = self.mw.profile_manager.load_shopify_config(
                self.mw.current_client_id
            )

            if not fresh_config:
                raise Exception("Failed to load configuration")

        except Exception as e:
            QMessageBox.critical(
                self.mw,
                "Error",
                f"Failed to load settings:\n{str(e)}"
            )
            return

        # Open settings with fresh data
        from gui.settings_window_pyside import SettingsWindow

        settings_win = SettingsWindow(
            client_id=self.mw.current_client_id,
            client_config=fresh_config,  # Fresh data
            profile_manager=self.mw.profile_manager,
            analysis_df=self.mw.analysis_results_df,
            parent=self.mw
        )

        if settings_win.exec():
            # Settings saved successfully
            try:
                # Reload config in MainWindow
                self.mw.active_profile_config = self.mw.profile_manager.load_shopify_config(
                    self.mw.current_client_id
                )

                # Re-validate files with new settings
                self.log.info("Re-validating files with updated settings...")

                if self.mw.orders_file_path:
                    self.mw.file_handler.validate_file("orders")

                if self.mw.stock_file_path:
                    self.mw.file_handler.validate_file("stock")

                # Success message
                QMessageBox.information(
                    self.mw,
                    "Settings Updated",
                    "Settings saved successfully!\n\n"
                    "Files have been re-validated with new configuration."
                )

                self.log.info("Settings updated and files re-validated successfully")

            except Exception as e:
                self.log.error(f"Error updating config after save: {e}")
                QMessageBox.warning(
                    self.mw,
                    "Warning",
                    f"Settings were saved, but failed to reload configuration:\n{str(e)}\n\n"
                    "Please restart the application."
                )

    def open_tag_categories_dialog(self):
        """Opens the tag categories management dialog."""
        if not self.mw.current_client_id:
            QMessageBox.warning(
                self.mw,
                "No Client Selected",
                "Please select a client before managing tag categories."
            )
            return

        if not self.mw.active_profile_config:
            QMessageBox.warning(
                self.mw,
                "No Configuration Loaded",
                "Please load a client configuration first."
            )
            return

        # Get current tag_categories
        tag_categories = self.mw.active_profile_config.get("tag_categories", {})

        # Open dialog
        dialog = TagCategoriesDialog(tag_categories, parent=self.mw)

        # Connect signal to save changes
        def on_categories_updated(updated_categories):
            """Handle categories update."""
            try:
                # Update config
                self.mw.active_profile_config["tag_categories"] = updated_categories

                # Save to file
                self.mw.profile_manager.save_shopify_config(
                    self.mw.current_client_id,
                    self.mw.active_profile_config
                )

                self.log.info(f"Tag categories updated for CLIENT_{self.mw.current_client_id}")

                # Refresh tag delegate so new tags get correct colors immediately
                if hasattr(self.mw, 'tag_delegate') and self.mw.tag_delegate is not None:
                    self.mw.tag_delegate.tag_categories = updated_categories

            except Exception as e:
                self.log.error(f"Error saving tag categories: {e}")
                QMessageBox.critical(
                    self.mw,
                    "Save Error",
                    f"Failed to save tag categories:\n{str(e)}"
                )

        dialog.categories_updated.connect(on_categories_updated)
        dialog.exec()

    def open_report_selection_dialog(self, report_type):
        """Opens dialog for selecting which reports to generate.

        Args:
            report_type (str): Either "packing_lists" or "stock_exports"
        """
        self.log.info(f"Opening report selection dialog: {report_type}")

        # Validate that analysis has been run
        if self.mw.analysis_results_df is None or self.mw.analysis_results_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Analysis Data",
                "Please run analysis first before generating reports."
            )
            return

        # Validate client and session
        if not self.mw.current_client_id:
            QMessageBox.warning(
                self.mw,
                "No Client Selected",
                "Please select a client."
            )
            return

        session_path = self.mw.session_path

        if not session_path:
            QMessageBox.warning(
                self.mw,
                "No Active Session",
                "No active session. Please create a new session or open an existing one."
            )
            return

        # ✅ FIX: Reload fresh config before opening dialog
        try:
            fresh_config = self.mw.profile_manager.load_shopify_config(
                self.mw.current_client_id
            )

            if not fresh_config:
                raise Exception("Failed to load configuration")

            # Update main window config
            self.mw.active_profile_config = fresh_config

        except Exception as e:
            QMessageBox.critical(
                self.mw,
                "Configuration Error",
                f"Failed to load client configuration:\n{str(e)}"
            )
            return

        # ✅ FIX: Use correct config keys
        if report_type == "packing_lists":
            config_key = "packing_list_configs"  # Correct key
        elif report_type == "stock_exports":
            config_key = "stock_export_configs"  # Correct key
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        report_configs = fresh_config.get(config_key, [])

        if not report_configs:
            QMessageBox.information(
                self.mw,
                "No Reports Configured",
                f"No {report_type.replace('_', ' ')} are configured for this client.\n\n"
                f"Please configure them in Client Settings."
            )
            return

        # Open selection dialog
        from gui.report_selection_dialog import ReportSelectionDialog

        dialog = ReportSelectionDialog(report_type, report_configs, self.mw)
        dialog.reportSelected.connect(
            lambda rc: self._generate_single_report(report_type, rc, session_path)
        )
        dialog.exec()

    def _apply_filters(self, df, filters):
        """Apply filters from report config to DataFrame.

        Args:
            df: DataFrame to filter
            filters: List of filter dicts with 'field', 'operator', 'value'

        Returns:
            Filtered DataFrame
        """
        filtered_df = df.copy()

        for filt in filters:
            field = filt.get("field")
            operator = filt.get("operator")
            value = filt.get("value")

            if not field or field not in filtered_df.columns:
                continue

            try:
                if operator == "==":
                    filtered_df = filtered_df[filtered_df[field] == value]
                elif operator == "!=":
                    filtered_df = filtered_df[filtered_df[field] != value]
                elif operator == "in":
                    values = [v.strip() for v in value.split(',')]
                    filtered_df = filtered_df[filtered_df[field].isin(values)]
                elif operator == "not in":
                    values = [v.strip() for v in value.split(',')]
                    filtered_df = filtered_df[~filtered_df[field].isin(values)]
                elif operator == "contains":
                    filtered_df = filtered_df[filtered_df[field].astype(str).str.contains(value, na=False)]
            except Exception as e:
                self.log.warning(f"Failed to apply filter {field} {operator} {value}: {e}")

        return filtered_df

    def _create_analysis_json(self, df):
        """Convert DataFrame to packing list JSON format for Packing Tool.

        Uses build_packing_order_data() from core to ensure canonical field
        names match analysis_data.json — both files always have identical
        order metadata structure.

        Args:
            df: Filtered DataFrame with orders data

        Returns:
            dict: JSON structure for Packing Tool
        """
        from datetime import datetime
        from shopify_tool.core import build_packing_order_data

        orders_data = []
        for order_num, group in df.groupby('Order_Number'):
            orders_data.append(build_packing_order_data(str(order_num), group))

        session_id = os.path.basename(str(self.mw.session_path)) if self.mw.session_path else "unknown"

        return {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "total_orders": len(orders_data),
            "total_items": int(df['Quantity'].sum()) if 'Quantity' in df.columns else len(df),
            "orders": orders_data
        }

    def _generate_single_report(self, report_type, report_config, session_path):
        """Generates a single report (XLSX + JSON for packing lists).

        Args:
            report_type (str): "packing_lists" or "stock_exports"
            report_config (dict): Report configuration with name, filters, etc.
            session_path (Path): Current session directory
        """
        from pathlib import Path
        import json

        report_name = report_config.get("name", "Unknown")
        self.log.info(f"Generating {report_type}: {report_name}")
        self.mw.log_activity("Report", f"Generating report: {report_name}")

        try:
            # Create output directory
            if report_type == "packing_lists":
                output_dir = Path(session_path) / "packing_lists"
            elif report_type == "stock_exports":
                output_dir = Path(session_path) / "stock_exports"
            else:
                raise ValueError(f"Unknown report type: {report_type}")

            output_dir.mkdir(parents=True, exist_ok=True)

            # ========================================
            # GET FILTERS AND CONFIG
            # ========================================
            filters = report_config.get("filters", [])

            # ========================================
            # DETERMINE OUTPUT FILENAME
            # ========================================
            base_filename = report_config.get("output_filename", "")

            if not base_filename:
                # Generate default filename
                if report_type == "packing_lists":
                    base_filename = f"{report_name}.xlsx"
                else:
                    # Add timestamp for stock exports and writeoff reports
                    datestamp = datetime.now().strftime("%Y-%m-%d")
                    base_filename = f"{report_name}_{datestamp}.xls"

            # Ensure correct extension
            if report_type == "packing_lists":
                if not base_filename.endswith('.xlsx'):
                    base_filename = base_filename.replace('.xls', '.xlsx')
            else:  # stock_exports or writeoff_reports
                if not base_filename.endswith('.xls'):
                    base_filename = base_filename + '.xls'

            output_file = str(output_dir / base_filename)

            # ========================================
            # GENERATE REPORT USING PROPER MODULES
            # ========================================
            if report_type == "packing_lists":
                self.log.info(f"Creating packing list using packing_lists module")

                # Get exclude_skus from config
                exclude_skus = report_config.get("exclude_skus", [])
                self.log.info(f"[EXCLUDE_SKUS] Raw from config: {exclude_skus} (type: {type(exclude_skus)})")

                if isinstance(exclude_skus, str):
                    exclude_skus = [s.strip() for s in exclude_skus.split(',') if s.strip()]
                    self.log.info(f"[EXCLUDE_SKUS] After string split: {exclude_skus}")
                elif not isinstance(exclude_skus, list):
                    exclude_skus = []
                    self.log.warning(f"[EXCLUDE_SKUS] Unexpected type, reset to empty list")

                self.log.info(f"[EXCLUDE_SKUS] Final value passed to packing_lists: {exclude_skus}")

                # Use the proper packing_lists module
                # Pass UNFILTERED DataFrame - the module will apply filters itself
                packing_lists.create_packing_list(
                    analysis_df=self.mw.analysis_results_df,
                    output_file=output_file,
                    report_name=report_name,
                    filters=filters,
                    exclude_skus=exclude_skus
                )

                self.log.info(f"Packing list XLSX created: {output_file}")

                # ========================================
                # CREATE JSON COPY FOR PACKING TOOL
                # ========================================
                json_filename = base_filename.replace('.xlsx', '.json')
                json_path = str(output_dir / json_filename)

                try:
                    # Apply filters to get data for JSON
                    filtered_df = self._apply_filters(self.mw.analysis_results_df, filters)

                    # ========================================
                    # Apply exclude_skus to DataFrame for JSON (same as XLSX)
                    # ========================================
                    if isinstance(exclude_skus, str):
                        exclude_skus_list = [s.strip() for s in exclude_skus.split(',') if s.strip()]
                    elif isinstance(exclude_skus, list):
                        exclude_skus_list = exclude_skus
                    else:
                        exclude_skus_list = []

                    # Create DataFrame without excluded SKUs (same as XLSX)
                    json_df = filtered_df.copy()
                    if exclude_skus_list and not json_df.empty and 'SKU' in json_df.columns:
                        self.log.info(f"[JSON] Excluding SKUs from JSON: {exclude_skus_list}")
                        json_df = json_df[~json_df["SKU"].isin(exclude_skus_list)]
                        self.log.info(f"[JSON] Rows after exclude_skus: {len(json_df)}")

                    if not json_df.empty:
                        analysis_json = self._create_analysis_json(json_df)

                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(analysis_json, f, ensure_ascii=False, indent=2)

                        self.log.info(f"Packing list JSON created (exclude_skus applied): {json_path}")
                    else:
                        self.log.warning(f"Skipping JSON creation - no data after filtering and exclude_skus")

                except Exception as e:
                    self.log.error(f"Failed to create JSON: {e}", exc_info=True)
                    # Don't fail the whole report if JSON fails

            elif report_type == "stock_exports":
                self.log.info(f"Creating stock export using stock_export module")

                # Get writeoff setting from report_config
                apply_writeoff = report_config.get("apply_writeoff", False)
                tag_categories = self.mw.active_profile_config.get("tag_categories", {})

                # Use the proper stock_export module
                # Pass UNFILTERED DataFrame - the module will apply filters itself
                stock_export.create_stock_export(
                    analysis_df=self.mw.analysis_results_df,
                    output_file=output_file,
                    report_name=report_name,
                    filters=filters,
                    apply_writeoff=apply_writeoff,
                    tag_categories=tag_categories
                )

                self.log.info(f"Stock export created: {output_file}")

            # ========================================
            # SUCCESS MESSAGE - Status bar instead of blocking dialog
            # ========================================
            # Show brief status message instead of blocking dialog
            self.mw.statusBar().showMessage(
                f"✅ Report saved: {os.path.basename(output_file)}",
                5000  # 5 seconds
            )
            self.log.info(f"Report generated: {output_file}")

            self.mw.log_activity("Report", f"Generated: {report_name}")

            # ========================================
            # UPDATE SESSION STATISTICS (packing lists count)
            # ========================================
            if report_type == "packing_lists" and self.mw.session_path and self.mw.session_manager:
                try:
                    # Count existing packing lists in session
                    packing_lists_dir = Path(session_path) / "packing_lists"
                    if packing_lists_dir.exists():
                        packing_lists_files = [f.stem for f in packing_lists_dir.glob("*.json")]

                        # Get current statistics
                        session_info = self.mw.session_manager.get_session_info(str(session_path))
                        if session_info:
                            current_stats = session_info.get("statistics", {})

                            # Update packing lists count and list
                            current_stats["packing_lists_count"] = len(packing_lists_files)
                            current_stats["packing_lists"] = sorted(packing_lists_files)

                            # Save updated statistics
                            self.mw.session_manager.update_session_info(str(session_path), {
                                "statistics": current_stats
                            })

                            self.log.info(f"Updated session statistics: {len(packing_lists_files)} packing lists")
                except Exception as e:
                    self.log.warning(f"Failed to update session statistics: {e}")
                    # Don't fail the report if statistics update fails

        except Exception as e:
            self.log.error(f"Failed to generate report '{report_name}': {e}", exc_info=True)
            QMessageBox.critical(
                self.mw,
                "Generation Failed",
                f"Failed to generate report '{report_name}':\n\n{str(e)}"
            )


    def generate_writeoff_report(self):
        """Generate writeoff report directly (single button, no dialog)."""
        from pathlib import Path
        from datetime import datetime

        self.log.info("Generating writeoff report")

        # Validate that analysis has been run
        if self.mw.analysis_results_df is None or self.mw.analysis_results_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Analysis Data",
                "Please run analysis first before generating writeoff report."
            )
            return

        # Validate session
        if not self.mw.session_path:
            QMessageBox.warning(
                self.mw,
                "No Active Session",
                "No active session. Please create a new session first."
            )
            return

        try:
            # Create writeoff_report directory in session
            writeoff_dir = Path(self.mw.session_path) / "writeoff_report"
            writeoff_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d")
            output_file = writeoff_dir / f"writeoff_{timestamp}.xls"

            # Get tag categories
            tag_categories = self.mw.active_profile_config.get("tag_categories", {})

            # Generate report using sku_writeoff module
            from shopify_tool.sku_writeoff import generate_writeoff_report
            generate_writeoff_report(
                self.mw.analysis_results_df,
                tag_categories,
                str(output_file)
            )

            # Show success message in status bar
            self.mw.statusBar().showMessage(
                f"✅ Writeoff report saved: {output_file.name}",
                5000  # 5 seconds
            )
            self.log.info(f"Writeoff report created: {output_file}")
            self.mw.log_activity("Report", "Generated writeoff report")

        except Exception as e:
            self.log.error(f"Failed to generate writeoff report: {e}", exc_info=True)
            QMessageBox.critical(
                self.mw,
                "Generation Failed",
                f"Failed to generate writeoff report:\n\n{str(e)}"
            )

    def toggle_fulfillment_status_for_order(self, order_number):
        """Toggles the fulfillment status of all items in a given order.

        Calls the `analysis.toggle_order_fulfillment` function and updates
        the UI if the change is successful.

        Args:
            order_number (str): The order number to modify.
        """
        # Get affected rows BEFORE operation
        affected_rows = self.mw.analysis_results_df[
            self.mw.analysis_results_df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
        ].copy()

        success, result, updated_df = toggle_order_fulfillment(self.mw.analysis_results_df, order_number)
        if success:
            self.mw.analysis_results_df = updated_df

            # Use consistent filtering approach with type conversion and strip
            mask = updated_df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
            matching_rows = updated_df.loc[mask, "Order_Fulfillment_Status"]

            if matching_rows.empty:
                self.log.error(f"Order {order_number} not found after toggle operation")
                QMessageBox.critical(self.mw, "Error", f"Order {order_number} not found after status change")
                return

            new_status = matching_rows.iloc[0]

            # Record for undo
            self.mw.undo_manager.record_operation(
                "toggle_status",
                f"Toggled order {order_number} to '{new_status}'",
                {"order_number": order_number},
                affected_rows
            )

            self.data_changed.emit()
            # Auto-save session state after modification
            self.mw.save_session_state()
            self._update_undo_button()
            self.mw.log_activity("Manual Edit", f"Order {order_number} status changed to '{new_status}'.")
            self.log.info(f"Order {order_number} status changed to '{new_status}'.")
        else:
            self.log.warning(f"Failed to toggle status for order {order_number}: {result}")
            QMessageBox.critical(self.mw, "Error", result)

    def add_tag_manually(self, order_number):
        """Opens a dialog to add a manual tag to an order's 'Status_Note'.

        Args:
            order_number (str): The order number to add the tag to.
        """
        tag_to_add, ok = QInputDialog.getText(self.mw, "Add Manual Tag", "Enter tag to add:")
        if ok and tag_to_add:
            # Get affected rows BEFORE operation
            affected_rows = self.mw.analysis_results_df[
                self.mw.analysis_results_df["Order_Number"] == order_number
            ].copy()

            order_rows_indices = self.mw.analysis_results_df[
                self.mw.analysis_results_df["Order_Number"] == order_number
            ].index
            if "Status_Note" not in self.mw.analysis_results_df.columns:
                self.mw.analysis_results_df["Status_Note"] = ""
            for index in order_rows_indices:
                current_notes = self.mw.analysis_results_df.loc[index, "Status_Note"]
                if pd.isna(current_notes) or current_notes == "":
                    new_notes = tag_to_add
                elif tag_to_add not in current_notes.split(","):
                    new_notes = f"{current_notes}, {tag_to_add}"
                else:
                    new_notes = current_notes
                self.mw.analysis_results_df.loc[index, "Status_Note"] = new_notes

            # Record for undo
            self.mw.undo_manager.record_operation(
                "add_tag",
                f"Added tag '{tag_to_add}' to order {order_number}",
                {"order_number": order_number, "tag": tag_to_add},
                affected_rows
            )

            self.data_changed.emit()
            # Auto-save session state after modification
            self.mw.save_session_state()
            self._update_undo_button()
            self.mw.log_activity("Manual Tag", f"Added note '{tag_to_add}' to order {order_number}.")

    def remove_item_from_order(self, order_number, sku):
        """Removes a single item (a row) from the analysis DataFrame.

        Args:
            order_number (str): The order number.
            sku (str): The SKU of the item to remove.
        """
        reply = QMessageBox.question(
            self.mw,
            "Confirm Delete",
            f"Are you sure you want to remove item {sku} from order {order_number}?\nThis can be undone with Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Find and remove the specific row by order number and SKU
            # Convert to string for comparison to handle int/float order numbers
            order_number_str = str(order_number).strip()
            sku_str = str(sku).strip()
            order_mask = self.mw.analysis_results_df["Order_Number"].astype(str).str.strip() == order_number_str
            sku_mask = self.mw.analysis_results_df["SKU"].astype(str).str.strip() == sku_str
            mask = order_mask & sku_mask

            # Get affected rows BEFORE operation
            affected_rows = self.mw.analysis_results_df[mask].copy()

            self.mw.analysis_results_df = self.mw.analysis_results_df[~mask].reset_index(drop=True)

            # Record for undo
            self.mw.undo_manager.record_operation(
                "remove_item",
                f"Removed item {sku} from order {order_number}",
                {"order_number": order_number, "sku": sku},
                affected_rows
            )

            self.data_changed.emit()
            # Auto-save session state after modification
            self.mw.save_session_state()
            self._update_undo_button()
            self.mw.log_activity("Data Edit", f"Removed item {sku} from order {order_number}.")

    def remove_entire_order(self, order_number):
        """Removes all rows associated with a given order number.

        Args:
            order_number (str): The order number to remove completely.
        """
        reply = QMessageBox.question(
            self.mw,
            "Confirm Delete",
            f"Are you sure you want to remove the entire order {order_number}?\nThis can be undone with Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Convert to string for comparison to handle int/float order numbers
            order_number_str = str(order_number).strip()

            # Get affected rows BEFORE operation
            affected_rows = self.mw.analysis_results_df[
                self.mw.analysis_results_df["Order_Number"].astype(str).str.strip() == order_number_str
            ].copy()

            order_mask = self.mw.analysis_results_df["Order_Number"].astype(str).str.strip() != order_number_str

            self.mw.analysis_results_df = self.mw.analysis_results_df[order_mask].reset_index(drop=True)

            # Record for undo
            self.mw.undo_manager.record_operation(
                "remove_order",
                f"Removed order {order_number}",
                {"order_number": order_number},
                affected_rows
            )

            self.data_changed.emit()
            # Auto-save session state after modification
            self.mw.save_session_state()
            self._update_undo_button()
            self.mw.log_activity("Data Edit", f"Removed order {order_number}.")

    def show_add_product_dialog(self):
        """Show dialog to add product to order."""
        from gui.add_product_dialog import AddProductDialog
        from PySide6.QtWidgets import QDialog

        # Validate prerequisites
        if not hasattr(self.mw, 'analysis_results_df') or self.mw.analysis_results_df is None:
            QMessageBox.warning(
                self.mw,
                "No Analysis",
                "Please run analysis first before adding products."
            )
            return

        if not hasattr(self.mw, 'stock_file_path') or not self.mw.stock_file_path:
            QMessageBox.warning(
                self.mw,
                "No Stock Data",
                "Stock file must be loaded to add products."
            )
            return

        # Load stock DataFrame
        try:
            stock_delimiter = self.mw.active_profile_config.get("settings", {}).get("stock_csv_delimiter", ";")

            # Load raw stock file
            stock_df = pd.read_csv(
                self.mw.stock_file_path,
                delimiter=stock_delimiter,
                encoding='utf-8-sig'
            )
            self.log.info(f"Loaded stock data: {len(stock_df)} rows")

            # Apply column mappings to convert to internal names
            column_mappings = self.mw.active_profile_config.get("column_mappings", {})
            if column_mappings:
                stock_mappings = column_mappings.get("stock", {})
                if stock_mappings:
                    # Only rename columns that exist in the DataFrame
                    stock_rename_map = {csv_col: internal_col for csv_col, internal_col in stock_mappings.items()
                                       if csv_col in stock_df.columns and csv_col != internal_col}
                    if stock_rename_map:
                        stock_df = stock_df.rename(columns=stock_rename_map)
                        self.log.info(f"Applied column mappings: {stock_rename_map}")

            # Normalize SKU column to string
            if "SKU" in stock_df.columns:
                from shopify_tool.csv_utils import normalize_sku
                stock_df["SKU"] = stock_df["SKU"].apply(normalize_sku)

        except Exception as e:
            self.log.error(f"Failed to load stock file: {e}", exc_info=True)
            QMessageBox.critical(
                self.mw,
                "Error Loading Stock",
                f"Could not load stock file.\n\nError: {e}"
            )
            return

        # Create live_stock tracking dict
        # Start with base stock from stock file, then override with Final_Stock
        live_stock = {}

        # First, populate with base stock quantities from stock_df
        if "Stock" in stock_df.columns:
            for _, row in stock_df.iterrows():
                sku = row.get("SKU")
                stock_qty = row.get("Stock", 0)
                if pd.notna(sku) and pd.notna(stock_qty):
                    try:
                        live_stock[str(sku).strip()] = int(stock_qty)
                    except (ValueError, TypeError):
                        live_stock[str(sku).strip()] = 0
            self.log.info(f"Loaded base stock for {len(live_stock)} SKUs from stock file")

        # Then, override with Final_Stock values from analysis (more current)
        if "Final_Stock" in self.mw.analysis_results_df.columns:
            for _, row in self.mw.analysis_results_df.iterrows():
                sku = row["SKU"]
                final_stock = row["Final_Stock"]
                if pd.notna(sku) and pd.notna(final_stock):
                    try:
                        live_stock[str(sku).strip()] = int(final_stock)
                    except (ValueError, TypeError):
                        pass  # Keep base stock value if Final_Stock is invalid
            self.log.info(f"Updated with Final_Stock for analysis SKUs. Total: {len(live_stock)} SKUs")
        else:
            self.log.warning("No Final_Stock column in analysis results, using base stock only")

        # Show dialog
        dialog = AddProductDialog(
            parent=self.mw,
            analysis_df=self.mw.analysis_results_df,
            stock_df=stock_df,
            live_stock=live_stock
        )

        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            if result:
                self._add_product_to_order(result, stock_df, live_stock)

    def _add_product_to_order(self, product_data, stock_df, live_stock):
        """
        Add manually added product to order.

        CRITICAL: Does NOT re-run full analysis!
        Instead: Recalculates fulfillment ONLY for this order.

        Args:
            product_data: dict {
                "order_number": str,
                "sku": str,
                "product_name": str,
                "quantity": int
            }
            stock_df: DataFrame with stock data
            live_stock: dict with current stock levels
        """
        order_num = product_data["order_number"]
        sku = product_data["sku"]
        quantity = product_data["quantity"]

        self.log.info(f"Adding {quantity}x {sku} to order {order_num}")

        # Step 1: Get existing row as template
        # Convert Order_Number to string for comparison (might be int/float)
        existing_rows = self.mw.analysis_results_df[
            self.mw.analysis_results_df["Order_Number"].astype(str) == str(order_num)
        ]

        if existing_rows.empty:
            self.log.error(f"Order {order_num} not found")
            QMessageBox.critical(
                self.mw,
                "Error",
                f"Order {order_num} not found in analysis."
            )
            return

        template_row = existing_rows.iloc[0].copy()

        # Step 2: Create new row
        new_row = template_row.copy()
        new_row["SKU"] = sku
        new_row["Product_Name"] = product_data["product_name"]
        new_row["Quantity"] = quantity
        new_row["Source"] = "Manual"
        new_row["Original_SKU"] = sku
        new_row["Original_Quantity"] = quantity
        new_row["Is_Set_Component"] = False

        # Set Warehouse_Name from stock if available
        # Convert SKU to string for comparison (might be int/float)
        stock_row = stock_df[stock_df["SKU"].astype(str).str.strip() == sku]
        if not stock_row.empty and "Product_Name" in stock_row.columns:
            new_row["Warehouse_Name"] = stock_row.iloc[0]["Product_Name"]
        else:
            new_row["Warehouse_Name"] = product_data["product_name"]

        # Step 3: Lookup stock value
        if not stock_row.empty and "Stock" in stock_row.columns:
            initial_stock = stock_row.iloc[0]["Stock"]
            new_row["Stock"] = initial_stock
        else:
            new_row["Stock"] = 0
            initial_stock = 0

        # Step 4: Get current live stock
        current_live_stock = live_stock.get(sku, initial_stock)
        new_row["Final_Stock"] = current_live_stock

        # Step 5: Append to DataFrame
        self.mw.analysis_results_df = pd.concat(
            [self.mw.analysis_results_df, pd.DataFrame([new_row])],
            ignore_index=True
        )

        self.log.info(f"Row added to analysis_results_df")

        # Step 6: Recalculate fulfillment for THIS ORDER ONLY
        self._recalculate_order_fulfillment(order_num)

        # Step 7: Save to session
        self._save_manual_addition(product_data)

        # Step 8: Emit data changed signal
        self.data_changed.emit()

        # Step 9: Auto-save session state after modification
        self.mw.save_session_state()

        # Step 10: Show success message
        QMessageBox.information(
            self.mw,
            "Product Added",
            f"Product {sku} ({quantity}x) added to order {order_num}.\n\n"
            "Fulfillment status has been updated."
        )

        self.mw.log_activity("Manual Addition", f"Added {quantity}x {sku} to order {order_num}")

    def _recalculate_order_fulfillment(self, order_number):
        """
        Recalculate fulfillment status for ONE specific order.

        CRITICAL: Does NOT touch other orders or re-run analysis!
        This preserves repeated order detection logic.

        Args:
            order_number: Order to recalculate
        """
        self.log.info(f"Recalculating fulfillment for order {order_number}")

        # Get all items for this order
        # Convert Order_Number to string for comparison (might be int/float)
        order_items = self.mw.analysis_results_df[
            self.mw.analysis_results_df["Order_Number"].astype(str) == str(order_number)
        ]

        # Rebuild live stock tracking from Final_Stock
        live_stock = {}
        for _, row in self.mw.analysis_results_df.iterrows():
            sku = row["SKU"]
            final_stock = row["Final_Stock"]
            if pd.notna(sku) and pd.notna(final_stock):
                live_stock[sku] = final_stock

        # Check if all items can be fulfilled with current live stock
        can_fulfill = True

        for _, item in order_items.iterrows():
            sku = item["SKU"]
            required_qty = item["Quantity"]
            available = live_stock.get(sku, 0)

            if required_qty > available:
                can_fulfill = False
                self.log.debug(f"  {sku}: need {required_qty}, have {available} - NOT OK")
                break
            else:
                self.log.debug(f"  {sku}: need {required_qty}, have {available} - OK")

        # Update fulfillment status for ALL items in this order
        new_status = "Fulfillable" if can_fulfill else "Not Fulfillable"

        # Convert Order_Number to string for comparison (might be int/float)
        self.mw.analysis_results_df.loc[
            self.mw.analysis_results_df["Order_Number"].astype(str) == str(order_number),
            "Order_Fulfillment_Status"
        ] = new_status

        # If fulfillable, update Final_Stock (simulate allocation)
        if can_fulfill:
            for _, item in order_items.iterrows():
                sku = item["SKU"]
                qty = item["Quantity"]
                new_stock = live_stock.get(sku, 0) - qty
                # Update Final_Stock for ALL rows with this SKU
                self.mw.analysis_results_df.loc[
                    self.mw.analysis_results_df["SKU"] == sku,
                    "Final_Stock"
                ] = new_stock

            self.log.info(f"Order {order_number} marked as Fulfillable, stock updated")
        else:
            self.log.info(f"Order {order_number} marked as Not Fulfillable")

    def _save_manual_addition(self, product_data):
        """Save manual addition to session file."""
        import json

        if not hasattr(self.mw, 'session_path') or not self.mw.session_path:
            self.log.warning("No active session, manual addition not saved")
            return

        # Path to manual_additions.json
        additions_file = os.path.join(self.mw.session_path, "manual_additions.json")

        # Load existing additions
        if os.path.exists(additions_file):
            try:
                with open(additions_file, 'r', encoding='utf-8') as f:
                    additions = json.load(f)
            except Exception as e:
                self.log.error(f"Failed to load manual additions: {e}")
                additions = []
        else:
            additions = []

        # Add new entry
        additions.append({
            "order_number": product_data["order_number"],
            "sku": product_data["sku"],
            "product_name": product_data["product_name"],
            "quantity": product_data["quantity"],
            "timestamp": datetime.now().isoformat()
        })

        # Save back
        try:
            with open(additions_file, 'w', encoding='utf-8') as f:
                json.dump(additions, f, indent=2, ensure_ascii=False)
            self.log.info(f"Saved manual addition to {additions_file}")
        except Exception as e:
            self.log.error(f"Failed to save manual additions: {e}")

    def _update_undo_button(self):
        """Update undo button state and tooltip."""
        if hasattr(self.mw, 'undo_button'):
            can_undo = self.mw.undo_manager.can_undo()
            self.mw.undo_button.setEnabled(can_undo)

            # Update tooltip with next undo description
            if can_undo:
                next_undo = self.mw.undo_manager.get_undo_description()
                if next_undo:
                    self.mw.undo_button.setToolTip(f"Undo: {next_undo} (Ctrl+Z)")
                else:
                    self.mw.undo_button.setToolTip("Undo last operation (Ctrl+Z)")
            else:
                self.mw.undo_button.setToolTip("Undo last operation (Ctrl+Z)")

    # ============================================================================
    # BULK OPERATIONS
    # ============================================================================

    def bulk_change_status(self, is_fulfillable: bool):
        """Change fulfillment status for all selected orders.

        Args:
            is_fulfillable: True for Fulfillable, False for Not Fulfillable
        """
        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get summary
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()
        status_text = "Fulfillable" if is_fulfillable else "Not Fulfillable"

        # Confirmation dialog
        reply = QMessageBox.question(
            self.mw,
            "Confirm Bulk Status Change",
            f"Change status to '{status_text}' for:\n"
            f"- {orders_count} orders\n"
            f"- {items_count} total items\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        affected_rows_before = self.mw.analysis_results_df.loc[selected_indexes].copy()

        # Perform bulk status change
        new_status = "Fulfillable" if is_fulfillable else "Not Fulfillable"
        self.mw.analysis_results_df.loc[selected_indexes, "Order_Fulfillment_Status"] = new_status

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_change_status",
            description=f"Bulk Change Status: {orders_count} orders to {status_text}",
            params={
                "is_fulfillable": is_fulfillable,
                "affected_indexes": selected_indexes
            },
            affected_rows_before=affected_rows_before
        )

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Changed status to {status_text} for {orders_count} orders ({items_count} items)"
        )

        # Update undo button
        self._update_undo_button()

    def bulk_add_tag(self):
        """Add Internal Tag to all selected orders."""
        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get tag categories from config
        from shopify_tool.tag_manager import _normalize_tag_categories
        tag_categories = self.mw.active_profile_config.get("tag_categories", {})

        # Build tag selection dialog
        all_tags = []
        # Normalize to handle both v1 and v2 formats
        categories = _normalize_tag_categories(tag_categories)
        for category, config in categories.items():
            category_label = config.get("label", category)
            for tag in config.get("tags", []):
                all_tags.append(f"{category_label}: {tag}")

        all_tags.append("--- Custom Tag ---")

        tag, ok = QInputDialog.getItem(
            self.mw,
            "Select Tag",
            "Choose tag to add to selected orders:",
            all_tags,
            0,
            False
        )

        if not ok:
            return

        # Handle custom tag
        if tag == "--- Custom Tag ---":
            custom_tag, ok = QInputDialog.getText(
                self.mw,
                "Custom Tag",
                "Enter custom tag:"
            )
            if not ok or not custom_tag.strip():
                return
            tag_value = custom_tag.strip()
        else:
            # Extract tag value from "Category: Tag" format
            tag_value = tag.split(": ", 1)[1] if ": " in tag else tag

        # Get summary
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        # Confirmation
        reply = QMessageBox.question(
            self.mw,
            "Confirm Bulk Add Tag",
            f"Add tag '{tag_value}' to:\n"
            f"- {orders_count} orders\n"
            f"- {items_count} total items\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        from shopify_tool.tag_manager import add_tag

        selected_indexes = self.mw.selection_helper.get_selected_source_rows()

        # Get unique orders and their first row (order-level operation)
        selected_df = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df['Order_Number'].unique()

        # Get first row index for each unique order (representative row)
        representative_indexes = []
        for order_num in unique_orders:
            order_rows = self.mw.analysis_results_df[
                self.mw.analysis_results_df['Order_Number'] == order_num
            ].index.tolist()
            if order_rows:
                representative_indexes.append(order_rows[0])

        # Store affected rows BEFORE modification (only representatives)
        affected_rows_before = self.mw.analysis_results_df.loc[representative_indexes].copy()

        # Ensure Internal_Tags column exists
        if "Internal_Tags" not in self.mw.analysis_results_df.columns:
            self.mw.analysis_results_df["Internal_Tags"] = "[]"

        # Apply tag to representative rows only (first row of each order)
        current_tags = self.mw.analysis_results_df.loc[representative_indexes, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: add_tag(t, tag_value))
        self.mw.analysis_results_df.loc[representative_indexes, "Internal_Tags"] = new_tags

        # Record undo operation (with representative indexes)
        self.mw.undo_manager.record_operation(
            operation_type="bulk_add_tag",
            description=f"Bulk Add Tag: '{tag_value}' to {orders_count} orders",
            params={
                "tag": tag_value,
                "affected_indexes": representative_indexes,
                "order_numbers": unique_orders.tolist()
            },
            affected_rows_before=affected_rows_before
        )

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()

        # Refresh tag filter with new tags
        if hasattr(self.mw, 'ui_manager'):
            self.mw.ui_manager._populate_tag_filter()

        self.mw.log_activity(
            "Bulk Operation",
            f"Added tag '{tag_value}' to {orders_count} orders ({items_count} items)"
        )

        # Update undo button
        self._update_undo_button()

    def bulk_remove_tag(self):
        """Remove Internal Tag from all selected orders."""
        from shopify_tool.tag_manager import parse_tags, remove_tag

        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get all unique tags from selected orders
        all_tags = set()
        if "Internal_Tags" in selected_df.columns:
            for tags_json in selected_df["Internal_Tags"]:
                tags = parse_tags(tags_json)
                all_tags.update(tags)

        if not all_tags:
            QMessageBox.information(
                self.mw,
                "No Tags",
                "Selected orders have no Internal Tags."
            )
            return

        # Tag selection dialog
        tag, ok = QInputDialog.getItem(
            self.mw,
            "Select Tag to Remove",
            "Choose tag to remove from selected orders:",
            sorted(list(all_tags)),
            0,
            False
        )

        if not ok:
            return

        # Get summary
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        # Confirmation
        reply = QMessageBox.question(
            self.mw,
            "Confirm Bulk Remove Tag",
            f"Remove tag '{tag}' from:\n"
            f"- {orders_count} orders\n"
            f"- {items_count} total items\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()

        # Get unique orders and their first row (order-level operation)
        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df_full['Order_Number'].unique()

        # Get first row index for each unique order (representative row)
        representative_indexes = []
        for order_num in unique_orders:
            order_rows = self.mw.analysis_results_df[
                self.mw.analysis_results_df['Order_Number'] == order_num
            ].index.tolist()
            if order_rows:
                representative_indexes.append(order_rows[0])

        # Store affected rows BEFORE modification (only representatives)
        affected_rows_before = self.mw.analysis_results_df.loc[representative_indexes].copy()

        # Apply tag removal to representative rows only (first row of each order)
        current_tags = self.mw.analysis_results_df.loc[representative_indexes, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: remove_tag(t, tag))
        self.mw.analysis_results_df.loc[representative_indexes, "Internal_Tags"] = new_tags

        # Record undo operation (with representative indexes)
        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_tag",
            description=f"Bulk Remove Tag: '{tag}' from {orders_count} orders",
            params={
                "tag": tag,
                "affected_indexes": representative_indexes,
                "order_numbers": unique_orders.tolist()
            },
            affected_rows_before=affected_rows_before
        )

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()

        # Refresh tag filter after removing tags
        if hasattr(self.mw, 'ui_manager'):
            self.mw.ui_manager._populate_tag_filter()

        self.mw.log_activity(
            "Bulk Operation",
            f"Removed tag '{tag}' from {orders_count} orders ({items_count} items)"
        )

        # Update undo button
        self._update_undo_button()

    def bulk_remove_sku_from_orders(self):
        """Remove specific SKU from all selected orders."""
        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get all unique SKUs from selected orders
        unique_skus = sorted(selected_df["SKU"].unique())

        # SKU selection dialog
        sku, ok = QInputDialog.getItem(
            self.mw,
            "Select SKU to Remove",
            "Choose SKU to remove from selected orders:",
            [str(s) for s in unique_skus],
            0,
            False
        )

        if not ok:
            return

        # Find affected rows (items with this SKU in selected orders)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]

        rows_to_remove = selected_df_full[selected_df_full["SKU"] == sku]
        affected_count = len(rows_to_remove)

        if affected_count == 0:
            QMessageBox.information(
                self.mw,
                "No Items Found",
                f"SKU '{sku}' not found in selected orders."
            )
            return

        # Confirmation
        reply = QMessageBox.question(
            self.mw,
            "Confirm SKU Removal",
            f"Remove {affected_count} items with SKU '{sku}' from selected orders?\n\n"
            f"This will remove the SKU from orders but keep the orders.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        affected_rows_before = rows_to_remove.copy()

        # Perform removal
        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(rows_to_remove.index)
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_sku",
            description=f"Bulk Remove SKU: '{sku}' ({affected_count} items)",
            params={
                "sku": sku,
                "removed_count": affected_count
            },
            affected_rows_before=affected_rows_before
        )

        # Clear selection (indexes changed after removal)
        self.mw.selection_helper.clear_selection()

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Removed SKU '{sku}' ({affected_count} items) from selected orders"
        )

        # Update toolbar state
        if hasattr(self.mw, '_update_bulk_toolbar_state'):
            self.mw._update_bulk_toolbar_state()

        # Update undo button
        self._update_undo_button()

    def bulk_remove_orders_with_sku(self):
        """Remove entire orders that contain specific SKU."""
        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get all unique SKUs from selected orders
        unique_skus = sorted(selected_df["SKU"].unique())

        # SKU selection dialog
        sku, ok = QInputDialog.getItem(
            self.mw,
            "Select SKU",
            "Remove all orders containing this SKU:",
            [str(s) for s in unique_skus],
            0,
            False
        )

        if not ok:
            return

        # Find all orders containing this SKU
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]

        # Get order numbers that contain this SKU
        orders_with_sku = selected_df_full[selected_df_full["SKU"] == sku]["Order_Number"].unique()

        if len(orders_with_sku) == 0:
            QMessageBox.information(
                self.mw,
                "No Orders Found",
                f"No selected orders contain SKU '{sku}'."
            )
            return

        # Find all items in these orders
        rows_to_remove = selected_df_full[selected_df_full["Order_Number"].isin(orders_with_sku)]
        items_count = len(rows_to_remove)

        # Confirmation
        reply = QMessageBox.question(
            self.mw,
            "Confirm Order Removal",
            f"Remove {len(orders_with_sku)} orders ({items_count} items) containing SKU '{sku}'?\n\n"
            f"This will delete entire orders, not just the SKU.",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        affected_rows_before = rows_to_remove.copy()

        # Perform removal
        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(rows_to_remove.index)
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_orders_with_sku",
            description=f"Bulk Remove Orders with SKU: '{sku}' ({len(orders_with_sku)} orders)",
            params={
                "sku": sku,
                "removed_orders": len(orders_with_sku),
                "removed_items": items_count
            },
            affected_rows_before=affected_rows_before
        )

        # Clear selection
        self.mw.selection_helper.clear_selection()

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Removed {len(orders_with_sku)} orders ({items_count} items) containing SKU '{sku}'"
        )

        # Update toolbar state
        if hasattr(self.mw, '_update_bulk_toolbar_state'):
            self.mw._update_bulk_toolbar_state()

        # Update undo button
        self._update_undo_button()

    def bulk_delete_orders(self):
        """Delete all selected orders."""
        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get summary
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        # Confirmation dialog
        reply = QMessageBox.question(
            self.mw,
            "Confirm Bulk Delete",
            f"DELETE {orders_count} orders ({items_count} total items)?\n\n"
            f"This action can be undone with Ctrl+Z.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # Default to No
        )

        if reply != QMessageBox.Yes:
            return

        # Get affected rows BEFORE modification
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        affected_rows_before = self.mw.analysis_results_df.loc[selected_indexes].copy()

        # Perform deletion
        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(selected_indexes)
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_delete_orders",
            description=f"Bulk Delete: {orders_count} orders ({items_count} items)",
            params={
                "deleted_orders": orders_count,
                "deleted_items": items_count
            },
            affected_rows_before=affected_rows_before
        )

        # Clear selection
        self.mw.selection_helper.clear_selection()

        # Update UI
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Deleted {orders_count} orders ({items_count} items)"
        )

        # Update toolbar state
        if hasattr(self.mw, '_update_bulk_toolbar_state'):
            self.mw._update_bulk_toolbar_state()

        # Update undo button
        self._update_undo_button()

    def bulk_export_selection(self, format_type: str):
        """Export selected rows to file.

        Args:
            format_type: 'xlsx' or 'csv'
        """
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        selected_df = self.mw.selection_helper.get_selected_orders_data()

        if selected_df.empty:
            QMessageBox.warning(
                self.mw,
                "No Selection",
                "Please select orders first."
            )
            return

        # Get summary
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        # File dialog
        if format_type == 'xlsx':
            file_filter = "Excel Files (*.xlsx)"
            default_name = f"selection_{orders_count}_orders.xlsx"
        else:
            file_filter = "CSV Files (*.csv)"
            default_name = f"selection_{orders_count}_orders.csv"

        # Suggest saving in session exports folder
        if self.mw.session_path:
            default_dir = Path(self.mw.session_path) / "exports"
            default_dir.mkdir(exist_ok=True)
            default_path = str(default_dir / default_name)
        else:
            default_path = default_name

        file_path, _ = QFileDialog.getSaveFileName(
            self.mw,
            "Export Selected Orders",
            default_path,
            file_filter
        )

        if not file_path:
            return

        try:
            # Export based on format
            if format_type == 'xlsx':
                selected_df.to_excel(file_path, index=False, engine='openpyxl')
            else:
                selected_df.to_csv(file_path, index=False, encoding='utf-8')

            QMessageBox.information(
                self.mw,
                "Export Successful",
                f"Exported {orders_count} orders ({items_count} items) to:\n{file_path}"
            )

            self.mw.log_activity(
                "Bulk Operation",
                f"Exported {orders_count} orders to {format_type.upper()}: {Path(file_path).name}"
            )

        except Exception as e:
            QMessageBox.critical(
                self.mw,
                "Export Failed",
                f"Failed to export selection:\n{str(e)}"
            )
            self.log.error(f"Bulk export failed: {e}", exc_info=True)
