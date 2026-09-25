import logging
import os
from datetime import datetime

import pandas as pd
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from gui.components import ConfirmDialog, show_error, toast
from gui.components.commandbar import BarState
from gui.selection_helper import order_number_mask
from gui.settings import SettingsWindow
from gui.tag_categories_dialog import TagCategoriesDialog
from gui.worker import Worker
from shopify_tool import core, packing_lists, stock_export, stock_ledger
from shopify_tool.analysis import toggle_order_fulfillment
from shopify_tool.csv_utils import AUTO_DELIMITER, resolve_delimiter
from shopify_tool.profile_manager import ProfileManagerError
from shopify_tool.session_manager import SessionManagerError


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


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
        self._stats_workers = set()  # keeps in-flight stats-recording Workers alive

    def create_new_session(self):
        """Creates a new session using SessionManager.

        Uses the SessionManager to create a new session for the current client.
        Upon successful creation, it enables the file loading buttons in the UI.
        """
        if not self.mw.current_client_id:
            self.log.warning("create_new_session called with no client selected")
            return

        try:
            # Show progress dialog during session creation (can be slow on UNC paths)
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QProgressDialog

            progress = QProgressDialog("Creating new session...", None, 0, 0, self.mw)
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("New Session")
            progress.show()

            try:
                # Use SessionManager to create session
                session_path = self.mw.session_manager.create_session(
                    self.mw.current_client_id
                )
            finally:
                progress.close()

            self.mw.session_path = session_path
            self.mw.command_bar.set_state(BarState.SESSION)
            self.mw.ui_manager.update_session_chips()

            # Update session info labels
            if hasattr(self.mw, "update_session_info_label"):
                self.mw.update_session_info_label()

            # Refresh session browser to show the new session
            if hasattr(self.mw, "session_browser"):
                self.mw.session_browser.refresh_sessions()

            # Refresh the Recent Sessions quick-pick in the right panel (Tab 1)
            if hasattr(self.mw, "ui_manager"):
                self.mw.ui_manager.refresh_recent_sessions(self.mw.current_client_id)

            # Update UI state
            if hasattr(self.mw, "update_ui_state"):
                self.mw.update_ui_state()

            session_name = os.path.basename(session_path)
            self.mw.log_activity("Session", f"New session created: {session_name}")
            self.log.info(f"New session created: {session_path}")

            toast(self.mw, f"Session {session_name} created.")

        except SessionManagerError:
            self.log.exception("Session manager error creating session")
            show_error(self.mw, "The session wasn't created", "Details are in Logs.")
        except (OSError, PermissionError):
            self.log.exception("File system error creating session")
            show_error(
                self.mw,
                "The session wasn't created",
                "Check that the server share is reachable, then create the session again.",
            )
        except Exception:
            self.log.exception("Unexpected error creating new session")
            show_error(self.mw, "The session wasn't created", "Details are in Logs.")

    def run_analysis(self):
        """Triggers the main fulfillment analysis in a background thread.

        It creates a `Worker` to run the `core.run_full_analysis` function,
        preventing the UI from freezing. It connects the worker's signals
        to the appropriate slots for handling completion or errors.
        """
        if not self.mw.session_path:
            self.log.warning("run_analysis called with no session")
            return

        if not self.mw.current_client_id:
            self.log.warning("run_analysis called with no client selected")
            return

        # Prevent double-run: if UI is already busy, analysis is still running
        if hasattr(self.mw, "_analysis_running") and self.mw._analysis_running:
            self.log.warning(
                "Analysis already in progress — ignoring duplicate run request"
            )
            return

        self.mw._analysis_running = True
        self.mw.command_bar.set_state(BarState.RUNNING)
        self.mw.ui_manager.set_ui_busy(True)
        self.log.info("Starting analysis thread.")
        stock_delimiter = self.mw.active_profile_config.get("settings", {}).get(
            "stock_csv_delimiter", AUTO_DELIMITER
        )
        orders_delimiter = self.mw.active_profile_config.get("settings", {}).get(
            "orders_csv_delimiter", AUTO_DELIMITER
        )

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
        self.mw.command_bar.set_state(BarState.SESSION)
        # Here, not in _update_all_views: the chips read session_info and stat
        # the stock copy over the share, which every tag or undo would repeat.
        self.mw.ui_manager.update_session_chips()
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
            self.mw.log_activity(
                "Analysis", f"Analysis complete. Report saved to: {result_msg}"
            )

            # Inventory memory is persisted by core.run_full_analysis using the
            # true post-fulfillment Final_Stock (groupby('SKU').last()). Do not
            # re-save it here — an extra write using .first() would store the
            # pre-depletion stock and over-promise fulfillment on the next run.

            # ========================================
            # RECORD STATISTICS TO SERVER
            # ========================================
            # StatsManager.record_analysis() performs blocking network I/O
            # (file lock, read/write, fsync) over the UNC file share -- a
            # fixed cost per call, independent of batch size. This method is
            # a Qt result-signal slot, so it always runs on the GUI thread;
            # doing that I/O inline here froze the UI on every analysis run.
            # See docs/superpowers/specs/2026-08-09-packaging-unlock-and-perf-audit-design.md
            # (Track A). The cheap in-memory counts below stay inline (not
            # the freeze source); only the network write is backgrounded.
            orders_count = (
                len(df["Order_Number"].unique()) if "Order_Number" in df.columns else 0
            )
            items_count = len(df)

            fulfillable_orders = 0
            if "Order_Fulfillment_Status" in df.columns:
                fulfillable_df = df[df["Order_Fulfillment_Status"] == "Fulfillable"]
                fulfillable_orders = (
                    len(fulfillable_df["Order_Number"].unique())
                    if not fulfillable_df.empty
                    else 0
                )

            self._record_analysis_stats_async(
                orders_count, items_count, fulfillable_orders
            )
            # ========================================
            # END STATISTICS RECORDING
            # ========================================

            # Auto-switch to Analysis Results tab (Tab 2)
            if hasattr(self.mw, "main_tabs"):
                self.mw.main_tabs.setCurrentIndex(1)

            # Update UI state
            if hasattr(self.mw, "update_ui_state"):
                self.mw.update_ui_state()

            # Raised two lines after switching to the Results tab, so it is a
            # Results-screen toast and belongs in the document (ADR 0007).
            self._results_toast("Analysis complete.")
        else:
            self.log.error(f"Analysis failed: {result_msg}")
            show_error(self.mw, "The analysis didn't finish", "Details are in Logs.")

    def _record_analysis_stats_async(
        self, orders_count, items_count, fulfillable_orders
    ):
        """Fires off StatsManager.record_analysis() on a background thread.

        StatsManager performs blocking network I/O over the UNC file share --
        see on_analysis_complete for why this must never run inline on the Qt
        main thread.
        """
        base_path = str(self.mw.profile_manager.base_path)
        session_path = self.mw.session_path
        client_id = self.mw.current_client_id

        worker = Worker(
            self._record_analysis_stats_job,
            base_path,
            session_path,
            client_id,
            orders_count,
            items_count,
            fulfillable_orders,
        )
        # Keep a strong reference until the worker finishes -- a bare local
        # var would let the unparented WorkerSignals object get garbage
        # collected before Qt dispatches its queued signals (same failure
        # mode documented on _client_load_workers in main_window_pyside.py).
        self._stats_workers.add(worker)
        worker.signals.finished.connect(lambda: self._stats_workers.discard(worker))
        self.mw.threadpool.start(worker)

    def _record_analysis_stats_job(
        self,
        base_path,
        session_path,
        client_id,
        orders_count,
        items_count,
        fulfillable_orders,
    ):
        """Background-thread body: writes analysis stats to the shared server file."""
        try:
            from shared.session_id import derive_session_id
            from shared.stats_manager import StatsManager

            self.log.info("Recording analysis statistics to server...")

            stats_mgr = StatsManager(base_path=base_path)
            session_name = (
                derive_session_id(session_path) if session_path else "unknown"
            )

            stats_mgr.record_analysis(
                client_id=client_id,
                session_id=session_name,
                orders_count=orders_count,
                metadata={
                    "items_count": items_count,
                    "fulfillable_orders": fulfillable_orders,
                },
            )

            self.log.info(
                f"Statistics recorded: {orders_count} orders, {items_count} items, {fulfillable_orders} fulfillable"
            )
        except Exception:
            # Don't fail the analysis if stats recording fails
            self.log.exception("Failed to record statistics")

    def on_task_error(self, error):
        """Handles the 'error' signal from any worker thread.

        Logs the exception and displays a critical error message to the user.

        Args:
            error (tuple): A tuple containing the exception type, value, and
                traceback.
        """
        _exctype, value, tb = error
        self.log.error(
            f"An unexpected error occurred in a background task: {value}\n{tb}",
        )
        show_error(self.mw, "A background task failed", "Details are in Logs.")

    def open_settings_window(self, page: str | None = None):
        """Opens the settings window for the active client.

        Args:
            page (str, optional): Nav entry to open on, e.g. "Orders Mapping".
                Defaults to whichever page was open last.
        """
        if not self.mw.current_client_id:
            self.log.warning("open_settings_window called with no client selected")
            return

        # Reload fresh config
        try:
            fresh_config = self.mw.profile_manager.load_shopify_config(
                self.mw.current_client_id
            )

            if not fresh_config:
                raise ProfileManagerError("Failed to load configuration")

        except Exception:
            self.log.exception("Failed to load settings")
            show_error(self.mw, "Settings couldn't be opened", "Details are in Logs.")
            return

        # Open settings with fresh data

        settings_win = SettingsWindow(
            client_id=self.mw.current_client_id,
            client_config=fresh_config,  # Fresh data
            profile_manager=self.mw.profile_manager,
            analysis_df=self.mw.analysis_results_df,
            parent=self.mw,
            initial_page=page,
        )

        if settings_win.exec():
            # The window has already toasted "Settings saved".
            try:
                self.mw.active_profile_config = (
                    self.mw.profile_manager.load_shopify_config(
                        self.mw.current_client_id
                    )
                )
                self.mw.push_tag_categories()

                self.log.info("Re-validating files with updated settings...")
                if self.mw.orders_file_path:
                    self.mw.file_handler.validate_file("orders")
                if self.mw.stock_file_path:
                    self.mw.file_handler.validate_file("stock")

                self.log.info("Settings updated and files re-validated successfully")

            except Exception:
                self.log.exception("Error updating config after save")
                show_error(
                    self.mw,
                    "Settings were saved but didn't reload",
                    "Restart the app to use them. Details are in Logs.",
                )

    def open_tag_categories_dialog(self):
        """Opens the tag categories management dialog."""
        if not self.mw.current_client_id:
            self.log.warning(
                "open_tag_categories_dialog called with no client selected"
            )
            return

        if not self.mw.active_profile_config:
            self.log.warning(
                "open_tag_categories_dialog called with no configuration loaded"
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
                self.mw.push_tag_categories()

                # Save to file
                self.mw.profile_manager.save_shopify_config(
                    self.mw.current_client_id, self.mw.active_profile_config
                )

                self.log.info(
                    f"Tag categories updated for CLIENT_{self.mw.current_client_id}"
                )

            except Exception:
                self.log.exception("Error saving tag categories")
                # Still unsaved: the dialog neither toasts nor closes.
                dialog.panel.modified = True
                show_error(
                    dialog,
                    "Tag categories weren't saved",
                    "Check that the server share is reachable, then save again. "
                    "Details are in Logs.",
                )

        dialog.categories_updated.connect(on_categories_updated)
        dialog.exec()

    def open_generate_reports_dialog(self):
        """Opens the multi-select dialog for generating packing lists and
        stock exports in one pass."""
        self.log.info("Opening Generate Reports dialog")

        # Validate that analysis has been run
        if self.mw.analysis_results_df is None or self.mw.analysis_results_df.empty:
            self.log.warning(
                "open_generate_reports_dialog called with no analysis data"
            )
            return

        # Validate client and session
        if not self.mw.current_client_id:
            self.log.warning(
                "open_generate_reports_dialog called with no client selected"
            )
            return

        session_path = self.mw.session_path

        if not session_path:
            self.log.warning(
                "open_generate_reports_dialog called with no active session"
            )
            return

        # FIX: Reload fresh config before opening dialog
        try:
            fresh_config = self.mw.profile_manager.load_shopify_config(
                self.mw.current_client_id
            )

            if not fresh_config:
                raise ProfileManagerError("Failed to load configuration")

            # Update main window config
            self.mw.active_profile_config = fresh_config
            self.mw.push_tag_categories()

        except Exception:
            self.log.exception("Failed to load client configuration")
            show_error(self.mw, "Reports couldn't be generated", "Details are in Logs.")
            return

        packing_configs = fresh_config.get("packing_list_configs", [])
        stock_configs = fresh_config.get("stock_export_configs", [])

        if not packing_configs and not stock_configs:
            client_id = self.mw.current_client_id
            toast(
                self.mw,
                f"No reports are set up for CLIENT_{client_id}.",
                role="info",
                action_text="Open Settings",
                on_action=self.open_settings_window,
            )
            return

        from gui.report_selection_dialog import GenerateReportsDialog

        analysis_df = self.mw.analysis_results_df
        dialog = GenerateReportsDialog(
            packing_configs,
            stock_configs,
            analysis_df,
            self._apply_filters,
            parent=self.mw,
        )

        dialog.reportsSelected.connect(
            lambda batch: self._generate_reports(batch, session_path)
        )
        dialog.exec()

    def _generate_reports(self, batch, session_path):
        """Generate every report the dialog emitted.

        One report failing must not cost the user the others -- that is the
        whole point of generating them in one pass.
        """
        failures = []
        for report_config in batch:
            report_type = report_config.get("report_type")
            try:
                self._generate_single_report(report_type, report_config, session_path)
            except Exception:
                self.log.exception(f"Failed to generate {report_config.get('name')}")
                failures.append(report_config.get("name", "Unknown"))

        if failures:
            show_error(
                self.mw,
                "1 report wasn't generated"
                if len(failures) == 1
                else f"{len(failures)} reports weren't generated",
                ", ".join(failures) + ". Details are in Logs.",
            )

    def _apply_filters(self, df, filters):
        """Apply a report config's filters to a DataFrame.

        Kept as a method because report_selection_dialog receives it as
        apply_filters_fn. The logic lives in shopify_tool.report_filters so
        the preview, the JSON and both file writers cannot drift apart --
        they used to, and the preview could report a different number of
        orders than the file contained.

        Restricts to fulfillable orders first, exactly as both writers do.
        Sharing the evaluator alone was not enough: this path was handed the
        whole analysis frame, so the preview counted -- and the JSON handed
        to Packing Tool contained -- orders the XLSX excluded.

        Args:
            df: DataFrame to filter
            filters: List of filter dicts with 'field', 'operator', 'value'

        Returns:
            Filtered DataFrame
        """
        from shopify_tool.report_filters import apply_report_filters, fulfillable_only

        return apply_report_filters(fulfillable_only(df), filters)

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
        for order_num, group in df.groupby("Order_Number"):
            orders_data.append(build_packing_order_data(str(order_num), group))

        session_id = (
            os.path.basename(str(self.mw.session_path))
            if self.mw.session_path
            else "unknown"
        )

        return {
            "session_id": session_id,
            "created_at": datetime.now().astimezone().isoformat(),
            "total_orders": len(orders_data),
            "total_items": int(df["Quantity"].sum())
            if "Quantity" in df.columns
            else len(df),
            "orders": orders_data,
        }

    def _generate_single_report(self, report_type, report_config, session_path):
        """Generates a single report (XLSX + JSON for packing lists).

        Args:
            report_type (str): "packing_lists" or "stock_exports"
            report_config (dict): Report configuration with name, filters, etc.
            session_path (Path): Current session directory
        """
        import json
        from pathlib import Path

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
                    datestamp = datetime.now().astimezone().strftime("%Y-%m-%d")
                    base_filename = f"{report_name}_{datestamp}.xls"

            # Ensure correct extension
            if report_type == "packing_lists":
                if not base_filename.endswith(".xlsx"):
                    base_filename = base_filename.replace(".xls", ".xlsx")
            else:  # stock_exports or writeoff_reports
                if not base_filename.endswith(".xls"):
                    base_filename = base_filename + ".xls"

            output_file = str(output_dir / base_filename)

            # ========================================
            # GENERATE REPORT USING PROPER MODULES
            # ========================================
            # Set by a "separate" packaging write-off, which saves a second
            # file the status message below has to name.
            packaging_file = None

            if report_type == "packing_lists":
                self.log.info("Creating packing list using packing_lists module")

                # Get exclude_skus from config
                exclude_skus = report_config.get("exclude_skus", [])
                self.log.info(
                    f"[EXCLUDE_SKUS] Raw from config: {exclude_skus} (type: {type(exclude_skus)})"
                )

                if isinstance(exclude_skus, str):
                    exclude_skus = [
                        s.strip() for s in exclude_skus.split(",") if s.strip()
                    ]
                    self.log.info(f"[EXCLUDE_SKUS] After string split: {exclude_skus}")
                elif not isinstance(exclude_skus, list):
                    exclude_skus = []
                    self.log.warning(
                        "[EXCLUDE_SKUS] Unexpected type, reset to empty list"
                    )

                self.log.info(
                    f"[EXCLUDE_SKUS] Final value passed to packing_lists: {exclude_skus}"
                )

                # Use the proper packing_lists module
                # Pass UNFILTERED DataFrame - the module will apply filters itself
                packing_lists.create_packing_list(
                    analysis_df=self.mw.analysis_results_df,
                    output_file=output_file,
                    report_name=report_name,
                    filters=filters,
                    exclude_skus=exclude_skus,
                    columns=report_config.get("columns"),
                )

                self.log.info(f"Packing list XLSX created: {output_file}")

                # ========================================
                # CREATE JSON COPY FOR PACKING TOOL
                # ========================================
                json_filename = base_filename.replace(".xlsx", ".json")
                json_path = str(output_dir / json_filename)

                try:
                    # Apply filters to get data for JSON
                    filtered_df = self._apply_filters(
                        self.mw.analysis_results_df, filters
                    )

                    # ========================================
                    # Apply exclude_skus to DataFrame for JSON (same as XLSX)
                    # ========================================
                    if isinstance(exclude_skus, str):
                        exclude_skus_list = [
                            s.strip() for s in exclude_skus.split(",") if s.strip()
                        ]
                    elif isinstance(exclude_skus, list):
                        exclude_skus_list = exclude_skus
                    else:
                        exclude_skus_list = []

                    # Create DataFrame without excluded SKUs (same as XLSX)
                    json_df = filtered_df.copy()
                    if (
                        exclude_skus_list
                        and not json_df.empty
                        and "SKU" in json_df.columns
                    ):
                        self.log.info(
                            f"[JSON] Excluding SKUs from JSON: {exclude_skus_list}"
                        )
                        json_df = json_df[~json_df["SKU"].isin(exclude_skus_list)]
                        self.log.info(f"[JSON] Rows after exclude_skus: {len(json_df)}")

                    if not json_df.empty:
                        analysis_json = self._create_analysis_json(json_df)

                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(analysis_json, f, ensure_ascii=False, indent=2)

                        self.log.info(
                            f"Packing list JSON created (exclude_skus applied): {json_path}"
                        )
                    else:
                        self.log.warning(
                            "Skipping JSON creation - no data after filtering and exclude_skus"
                        )

                except Exception:
                    self.log.exception("Failed to create JSON")
                    # Don't fail the whole report if JSON fails

            elif report_type == "stock_exports":
                self.log.info("Creating stock export using stock_export module")

                # Get writeoff setting from report_config
                writeoff_mode = report_config.get("writeoff_mode", "off")
                tag_categories = self.mw.active_profile_config.get("tag_categories", {})

                # Use the proper stock_export module
                # Pass UNFILTERED DataFrame - the module will apply filters itself
                packaging_file = stock_export.create_stock_export(
                    analysis_df=self.mw.analysis_results_df,
                    output_file=output_file,
                    report_name=report_name,
                    filters=filters,
                    writeoff_mode=writeoff_mode,
                    tag_categories=tag_categories,
                )

                self.log.info(f"Stock export created: {output_file}")

            # ========================================
            # SUCCESS MESSAGE - Status bar instead of blocking dialog
            # ========================================
            # Show brief status message instead of blocking dialog
            saved = os.path.basename(output_file)
            if packaging_file:
                saved += f" + {os.path.basename(packaging_file)}"
            self.mw.statusBar().showMessage(
                f"Report saved: {saved}",
                5000,  # 5 seconds
            )
            self.log.info(f"Report generated: {output_file}")

            self.mw.log_activity("Report", f"Generated: {report_name}")

            # ========================================
            # UPDATE SESSION STATISTICS (packing lists count)
            # ========================================
            if (
                report_type == "packing_lists"
                and self.mw.session_path
                and self.mw.session_manager
            ):
                try:
                    # Count existing packing lists in session
                    packing_lists_dir = Path(session_path) / "packing_lists"
                    if packing_lists_dir.exists():
                        packing_lists_files = [
                            f.stem for f in packing_lists_dir.glob("*.json")
                        ]

                        # Get current statistics
                        session_info = self.mw.session_manager.get_session_info(
                            str(session_path)
                        )
                        if session_info:
                            current_stats = session_info.get("statistics", {})

                            # Update packing lists count and list
                            current_stats["packing_lists_count"] = len(
                                packing_lists_files
                            )
                            current_stats["packing_lists"] = sorted(packing_lists_files)

                            # Save updated statistics
                            self.mw.session_manager.update_session_info(
                                str(session_path), {"statistics": current_stats}
                            )
                            if hasattr(self.mw, "session_browser"):
                                self.mw.session_browser.mark_dirty()

                            self.log.info(
                                f"Updated session statistics: {len(packing_lists_files)} packing lists"
                            )
                except Exception as e:
                    self.log.warning(f"Failed to update session statistics: {e}")
                    # Don't fail the report if statistics update fails

        except Exception:
            self.log.exception(f"Failed to generate report '{report_name}'")
            show_error(
                self.mw, f"{report_name!r} wasn't generated", "Details are in Logs."
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
            self._order_mask(order_number)
        ].copy()

        success, result, updated_df = toggle_order_fulfillment(
            self.mw.analysis_results_df, order_number
        )
        if success:
            self.mw.analysis_results_df = updated_df

            mask = self._order_mask(order_number, updated_df)
            matching_rows = updated_df.loc[mask, "Order_Fulfillment_Status"]

            if matching_rows.empty:
                self.log.error(f"Order {order_number} not found after toggle operation")
                show_error(
                    self.mw,
                    f"Order {order_number}'s status didn't change",
                    "Details are in Logs.",
                )
                return

            new_status = matching_rows.iloc[0]

            # Record for undo
            self.mw.undo_manager.record_operation(
                "toggle_status",
                f"Toggled order {order_number} to '{new_status}'",
                {"order_number": order_number},
                affected_rows,
            )

            self.data_changed.emit()
            # Auto-save session state after modification
            self.mw.save_session_state()
            self._update_undo_button()
            self.mw.log_activity(
                "Manual Edit", f"Order {order_number} status changed to '{new_status}'."
            )
            self.log.info(f"Order {order_number} status changed to '{new_status}'.")
        else:
            self.log.warning(
                f"Failed to toggle status for order {order_number}: {result}"
            )
            show_error(self.mw, f"Order {order_number}'s status didn't change", result)

    def _order_mask(self, order_number, df=None):
        """Rows belonging to one order, in `df` or the analysis frame.

        See order_number_mask: the one matching rule for order numbers.
        """
        if df is None:
            df = self.mw.analysis_results_df
        return order_number_mask(df, [order_number])

    def _set_selection(self, order_numbers) -> None:
        """Act on exactly the orders the page counted, not on ambient state."""
        self.mw.selection_helper.set_selected_orders([str(n) for n in order_numbers])

    def _orders_tag_changed(self, current_tags, new_tags) -> int:
        """How many orders the tag write actually moved.

        The popover's verb counts the orders the write will change -- the
        selection minus the ones already carrying the tag on add, and only the
        ones carrying it on remove -- and spec 6 requires the toast to repeat
        that number rather than the size of the selection.
        """
        changed = new_tags.index[new_tags != current_tags]
        return int(self.mw.analysis_results_df.loc[changed, "Order_Number"].nunique())

    def _results_toast(self, text: str, undoable: bool = False) -> None:
        """The Results screen's toast lives in the document (ADR 0007)."""
        bridge = getattr(self.mw, "results_bridge", None)
        if bridge is not None:
            bridge.raise_toast(text, undoable=undoable)

    def set_order_fulfillable(self, order_number, fulfillable: bool):
        """The pane's Hold / Mark fulfillable. A no-op when already so, so a
        page that is one push behind cannot flip an order the wrong way."""
        df = self.mw.analysis_results_df
        if df is None or df.empty:
            return
        mask = self._order_mask(order_number)
        if not mask.any():
            self.log.warning(f"Order {order_number} is no longer in the analysis")
            return
        already = stock_ledger.is_fulfillable(df, order_number)
        if already != bool(fulfillable):
            self.toggle_fulfillment_status_for_order(order_number)

    def remove_line(self, order_number, line_index: int, sku):
        """The pane's Remove this line: the order's `line_index`-th line, in
        frame order, only while it still carries `sku`."""
        df = self.mw.analysis_results_df
        if df is None or df.empty:
            return
        labels = df.index[self._order_mask(order_number)]
        if not 0 <= line_index < len(labels):
            self.log.warning("Aborted line removal: the line is gone")
            return
        label = labels[line_index]
        own_sku = df.loc[label, "SKU"]
        own = "" if pd.isna(own_sku) else str(own_sku).strip()
        if own != str(sku).strip():
            self.log.warning("Aborted line removal: the line moved")
            return
        # The frame's own SKU value, so a no-SKU line (NaN) still matches.
        self.remove_item_from_order(order_number, own_sku, df.index.get_loc(label))

    def add_internal_tag(self, order_number, tag):
        self._change_internal_tag(order_number, tag, adding=True)

    def remove_internal_tag(self, order_number, tag):
        self._change_internal_tag(order_number, tag, adding=False)

    def _change_internal_tag(self, order_number, tag, adding: bool):
        """Restored from Bundle 12's deleted MainWindow._apply_tag_operation."""
        from shopify_tool.tag_manager import add_tag, has_tag, remove_tag

        tag = str(tag).strip()
        df = self.mw.analysis_results_df
        if not tag or df is None or df.empty:
            return
        mask = self._order_mask(order_number)
        if not mask.any():
            return
        if "Internal_Tags" not in df.columns:
            if not adding:
                return
            df["Internal_Tags"] = "[]"
        if (
            not adding
            and not df.loc[mask, "Internal_Tags"].map(lambda t: has_tag(t, tag)).any()
        ):
            return

        affected_rows_before = df[mask].copy()
        change = add_tag if adding else remove_tag
        df.loc[mask, "Internal_Tags"] = df.loc[mask, "Internal_Tags"].apply(
            lambda t: change(t, tag)
        )
        description = (
            f"Added internal tag '{tag}' to order {order_number}"
            if adding
            else f"Removed internal tag '{tag}' from order {order_number}"
        )
        self.mw.undo_manager.record_operation(
            "add_internal_tag" if adding else "remove_internal_tag",
            description,
            {"order_number": order_number, "tag": tag},
            affected_rows_before,
        )
        self.data_changed.emit()
        self.mw.save_session_state()
        self._update_undo_button()
        self.mw.log_activity("Internal Tag", description)

    def remove_item_from_order(
        self, order_number, sku, row_position, row_snapshot=None
    ):
        """Removes a single item (a row) from the analysis DataFrame.

        Args:
            order_number (str): The order number.
            sku (str): The SKU of the item to remove.
            row_position (int): The positional row index of the specific line
                the user clicked, as captured when the context menu opened.
                Orders can contain multiple lines sharing the same SKU, so
                matching on (order_number, sku) alone would remove every such
                line instead of just the one the user targeted.
            row_snapshot (dict, optional): Full row values captured at the
                same time as row_position. If the row at row_position no
                longer matches this snapshot exactly, the table changed
                (e.g. another duplicate-SKU line now sits at that position)
                and the removal is aborted rather than risk deleting the
                wrong line.
        """
        df = self.mw.analysis_results_df
        if not (0 <= row_position < len(df)):
            self.log.warning("Aborted item removal: clicked row is no longer valid")
            return

        row_label = df.index[row_position]
        order_number_str = str(order_number).strip()
        sku_str = str(sku).strip()
        if (
            str(df.loc[row_label, "Order_Number"]).strip() != order_number_str
            or str(df.loc[row_label, "SKU"]).strip() != sku_str
        ):
            self.log.warning("Aborted item removal: clicked row no longer matches")
            return

        if row_snapshot is not None:
            current_row = df.loc[row_label]
            if any(
                str(current_row.get(col)) != str(value)
                for col, value in row_snapshot.items()
            ):
                self.log.warning(
                    "Aborted item removal: clicked row no longer matches its snapshot"
                )
                return

        mask = df.index == row_label

        # Get affected rows BEFORE operation
        affected_rows = df[mask].copy()

        self.mw.analysis_results_df = df[~mask].reset_index(drop=True)

        # A no-SKU line matches on NaN by design, but "Removed item nan" is
        # not a sentence. The undo payload keeps the raw value either way.
        line_name = "a line with no SKU" if pd.isna(sku) else f"item {sku}"

        # Record for undo
        self.mw.undo_manager.record_operation(
            "remove_item",
            f"Removed {line_name} from order {order_number}",
            {"order_number": order_number, "sku": sku},
            affected_rows,
        )

        self.data_changed.emit()
        # Auto-save session state after modification
        self.mw.save_session_state()
        self._update_undo_button()
        self.mw.log_activity(
            "Data Edit", f"Removed {line_name} from order {order_number}."
        )
        self._results_toast(
            f"Removed {line_name} from order {order_number}.", undoable=True
        )

    def remove_entire_order(self, order_number):
        """Removes all rows associated with a given order number.

        Args:
            order_number (str): The order number to remove completely.
        """
        this_order = self._order_mask(order_number)

        # Get affected rows BEFORE operation
        affected_rows = self.mw.analysis_results_df[this_order].copy()

        order_mask = ~this_order

        self.mw.analysis_results_df = self.mw.analysis_results_df[
            order_mask
        ].reset_index(drop=True)

        # Record for undo
        self.mw.undo_manager.record_operation(
            "remove_order",
            f"Removed order {order_number}",
            {"order_number": order_number},
            affected_rows,
        )

        self.data_changed.emit()
        # Auto-save session state after modification
        self.mw.save_session_state()
        self._update_undo_button()
        self.mw.log_activity("Data Edit", f"Removed order {order_number}.")
        self._results_toast(f"Removed order {order_number}.", undoable=True)

    def show_add_product_dialog(self):
        """Show dialog to add product to order."""
        from PySide6.QtWidgets import QDialog

        from gui.add_product_dialog import AddProductDialog

        # Validate prerequisites
        if (
            not hasattr(self.mw, "analysis_results_df")
            or self.mw.analysis_results_df is None
        ):
            self.log.warning("show_add_product_dialog called with no analysis data")
            show_error(
                self.mw,
                "There are no analysis results to add a product to",
                "Run the analysis first.",
            )
            return

        if not hasattr(self.mw, "stock_file_path") or not self.mw.stock_file_path:
            self.log.warning("show_add_product_dialog called with no stock file")
            show_error(
                self.mw,
                "This session's stock file couldn't be found",
                "Load a stock file in Setup, then try again.",
            )
            return

        # Load stock DataFrame
        try:
            setting = self.mw.active_profile_config.get("settings", {}).get(
                "stock_csv_delimiter"
            )

            # Load raw stock file
            stock_df = pd.read_csv(
                self.mw.stock_file_path,
                delimiter=resolve_delimiter(self.mw.stock_file_path, setting, "stock"),
                encoding="utf-8-sig",
            )
            self.log.info(f"Loaded stock data: {len(stock_df)} rows")

            # Apply column mappings to convert to internal names
            column_mappings = self.mw.active_profile_config.get("column_mappings", {})
            if column_mappings:
                stock_mappings = column_mappings.get("stock", {})
                if stock_mappings:
                    # Only rename columns that exist in the DataFrame
                    stock_rename_map = {
                        csv_col: internal_col
                        for csv_col, internal_col in stock_mappings.items()
                        if csv_col in stock_df.columns and csv_col != internal_col
                    }
                    if stock_rename_map:
                        stock_df = stock_df.rename(columns=stock_rename_map)
                        self.log.info(f"Applied column mappings: {stock_rename_map}")

            # Normalize SKU column to string
            if "SKU" in stock_df.columns:
                from shopify_tool.csv_utils import normalize_sku

                stock_df["SKU"] = stock_df["SKU"].apply(normalize_sku)

        except Exception:
            self.log.exception("Failed to load stock file")
            show_error(
                self.mw, "The stock file couldn't be loaded", "Details are in Logs."
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
            self.log.info(
                f"Loaded base stock for {len(live_stock)} SKUs from stock file"
            )

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
            self.log.info(
                f"Updated with Final_Stock for analysis SKUs. Total: {len(live_stock)} SKUs"
            )
        else:
            self.log.warning(
                "No Final_Stock column in analysis results, using base stock only"
            )

        # Show dialog
        try:
            dialog = AddProductDialog(
                parent=self.mw,
                analysis_df=self.mw.analysis_results_df,
                stock_df=stock_df,
                live_stock=live_stock,
                low_stock_threshold=self.mw.active_profile_config.get(
                    "settings", {}
                ).get("low_stock_threshold", 5),
            )
        except Exception:
            self.log.exception("Add Product dialog could not be built")
            show_error(
                self.mw, "Add Product couldn't be opened", "Details are in Logs."
            )
            return

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
            show_error(
                self.mw,
                f"{sku} wasn't added",
                f"Order {order_num} isn't in this analysis.",
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
            [self.mw.analysis_results_df, pd.DataFrame([new_row])], ignore_index=True
        )

        self.log.info("Row added to analysis_results_df")

        # Step 6: Recalculate fulfillment for THIS ORDER ONLY
        self._recalculate_order_fulfillment(order_num)

        # Step 7: Save to session
        self._save_manual_addition(product_data)

        # Step 8: Emit data changed signal
        self.data_changed.emit()

        # Step 9: Auto-save session state after modification
        self.mw.save_session_state()

        # Step 10: Show success message. This verb hangs off the Results
        # screen's overflow menu, so its toast belongs in the document too
        # (ADR 0007).
        self._results_toast(f"Added {quantity}x {sku} to order {order_num}.")

        self.mw.log_activity(
            "Manual Addition", f"Added {quantity}x {sku} to order {order_num}"
        )

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
                self.log.debug(
                    f"  {sku}: need {required_qty}, have {available} - NOT OK"
                )
                break
            else:
                self.log.debug(f"  {sku}: need {required_qty}, have {available} - OK")

        # Update fulfillment status for ALL items in this order
        new_status = "Fulfillable" if can_fulfill else "Not Fulfillable"

        # Convert Order_Number to string for comparison (might be int/float)
        self.mw.analysis_results_df.loc[
            self.mw.analysis_results_df["Order_Number"].astype(str)
            == str(order_number),
            "Order_Fulfillment_Status",
        ] = new_status

        # If fulfillable, update Final_Stock (simulate allocation)
        if can_fulfill:
            for _, item in order_items.iterrows():
                sku = item["SKU"]
                qty = item["Quantity"]
                new_stock = live_stock.get(sku, 0) - qty
                # Update Final_Stock for ALL rows with this SKU
                self.mw.analysis_results_df.loc[
                    self.mw.analysis_results_df["SKU"] == sku, "Final_Stock"
                ] = new_stock

            self.log.info(f"Order {order_number} marked as Fulfillable, stock updated")
        else:
            self.log.info(f"Order {order_number} marked as Not Fulfillable")

    def _save_manual_addition(self, product_data):
        """Save manual addition to session file."""
        import json

        if not hasattr(self.mw, "session_path") or not self.mw.session_path:
            self.log.warning("No active session, manual addition not saved")
            return

        # Path to manual_additions.json
        additions_file = os.path.join(self.mw.session_path, "manual_additions.json")

        # Load existing additions
        if os.path.exists(additions_file):
            try:
                with open(additions_file, "r", encoding="utf-8") as f:
                    additions = json.load(f)
            except Exception:
                self.log.exception("Failed to load manual additions")
                additions = []
        else:
            additions = []

        # Add new entry
        additions.append(
            {
                "order_number": product_data["order_number"],
                "sku": product_data["sku"],
                "product_name": product_data["product_name"],
                "quantity": product_data["quantity"],
                "timestamp": datetime.now().astimezone().isoformat(),
            }
        )

        # Save back
        try:
            with open(additions_file, "w", encoding="utf-8") as f:
                json.dump(additions, f, indent=2, ensure_ascii=False)
            self.log.info(f"Saved manual addition to {additions_file}")
        except Exception:
            self.log.exception("Failed to save manual additions")

    def _update_undo_button(self):
        """Update undo button state and tooltip."""
        if hasattr(self.mw, "undo_button"):
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

        bridge = getattr(self.mw, "results_bridge", None)
        if bridge is not None:
            bridge.set_undo_available(self.mw.undo_manager.can_undo())

    # ============================================================================
    # BULK OPERATIONS
    # ============================================================================

    def bulk_change_status(self, order_numbers, is_fulfillable: bool):
        """Change fulfillment status for the given orders."""
        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return

        orders_count, items_count = self.mw.selection_helper.get_selection_summary()
        status_text = "Fulfillable" if is_fulfillable else "Not Fulfillable"

        # Get affected rows BEFORE modification
        affected_rows_before = self.mw.analysis_results_df.loc[selected_indexes].copy()

        self.mw.analysis_results_df.loc[
            selected_indexes, "Order_Fulfillment_Status"
        ] = status_text

        self.mw.undo_manager.record_operation(
            operation_type="bulk_change_status",
            description=f"Bulk Change Status: {orders_count} orders to {status_text}",
            params={
                "is_fulfillable": is_fulfillable,
                "affected_indexes": selected_indexes,
            },
            affected_rows_before=affected_rows_before,
        )

        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Changed status to {status_text} for {orders_count} orders ({items_count} items)",
        )
        self._update_undo_button()
        verb = "marked fulfillable" if is_fulfillable else "held"
        self._results_toast(f"{_plural(orders_count, 'order')} {verb}", undoable=True)

    def bulk_add_tag(self, order_numbers, tag):
        """Add an internal tag to the given orders, skipping ones that already carry it."""
        from shopify_tool.tag_manager import add_tag

        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return
        tag_value = str(tag)

        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        selected_df = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df["Order_Number"].unique()
        mask = self.mw.analysis_results_df["Order_Number"].isin(unique_orders)

        affected_rows_before = self.mw.analysis_results_df[mask].copy()

        if "Internal_Tags" not in self.mw.analysis_results_df.columns:
            self.mw.analysis_results_df["Internal_Tags"] = "[]"

        current_tags = self.mw.analysis_results_df.loc[mask, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: add_tag(t, tag_value))
        tagged_count = self._orders_tag_changed(current_tags, new_tags)
        self.mw.analysis_results_df.loc[mask, "Internal_Tags"] = new_tags

        self.mw.undo_manager.record_operation(
            operation_type="bulk_add_tag",
            description=f"Bulk Add Tag: '{tag_value}' to {orders_count} orders",
            params={
                "tag": tag_value,
                "order_numbers": unique_orders.tolist(),
            },
            affected_rows_before=affected_rows_before,
        )

        self.mw.save_session_state()
        self.mw._update_all_views()
        if hasattr(self.mw, "ui_manager"):
            self.mw.ui_manager._populate_tag_filter()

        self.mw.log_activity(
            "Bulk Operation",
            f"Added tag '{tag_value}' to {orders_count} orders ({items_count} items)",
        )
        self._update_undo_button()
        self._results_toast(
            f"{tag_value} added to {_plural(tagged_count, 'order')}", undoable=True
        )

    def bulk_remove_tag(self, order_numbers, tag):
        """Remove an internal tag from the given orders."""
        from shopify_tool.tag_manager import remove_tag

        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return
        tag_value = str(tag)

        orders_count, items_count = self.mw.selection_helper.get_selection_summary()

        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df_full["Order_Number"].unique()
        mask = self.mw.analysis_results_df["Order_Number"].isin(unique_orders)

        affected_rows_before = self.mw.analysis_results_df[mask].copy()

        current_tags = self.mw.analysis_results_df.loc[mask, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: remove_tag(t, tag_value))
        untagged_count = self._orders_tag_changed(current_tags, new_tags)
        self.mw.analysis_results_df.loc[mask, "Internal_Tags"] = new_tags

        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_tag",
            description=f"Bulk Remove Tag: '{tag_value}' from {orders_count} orders",
            params={
                "tag": tag_value,
                "order_numbers": unique_orders.tolist(),
            },
            affected_rows_before=affected_rows_before,
        )

        self.mw.save_session_state()
        self.mw._update_all_views()
        if hasattr(self.mw, "ui_manager"):
            self.mw.ui_manager._populate_tag_filter()

        self.mw.log_activity(
            "Bulk Operation",
            f"Removed tag '{tag_value}' from {orders_count} orders ({items_count} items)",
        )
        self._update_undo_button()
        self._results_toast(
            f"{tag_value} removed from {_plural(untagged_count, 'order')}",
            undoable=True,
        )

    def bulk_remove_sku_from_orders(self, order_numbers, sku):
        """Remove one SKU's lines from the given orders, keeping the orders."""
        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return
        sku_value = str(sku)
        orders_count, _ = self.mw.selection_helper.get_selection_summary()

        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]
        rows_to_remove = selected_df_full[selected_df_full["SKU"] == sku_value]
        affected_count = len(rows_to_remove)
        if affected_count == 0:
            return
        orders_touched = rows_to_remove["Order_Number"].nunique()

        if not ConfirmDialog.ask(
            self.mw,
            title=f"Remove {sku_value} from {_plural(orders_touched, 'order')}?",
            body=(
                f"{orders_touched} of the {orders_count} selected orders carry "
                "this SKU. Their other lines stay."
            ),
            verb="Remove the line",
        ):
            return

        affected_rows_before = rows_to_remove.copy()
        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(
            rows_to_remove.index
        )
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_sku",
            description=f"Bulk Remove SKU: '{sku_value}' ({affected_count} items)",
            params={"sku": sku_value, "removed_count": affected_count},
            affected_rows_before=affected_rows_before,
        )

        self.mw.selection_helper.clear_selection()
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Removed SKU '{sku_value}' ({affected_count} items) from selected orders",
        )
        self._update_undo_button()
        self._results_toast(
            f"{sku_value} removed from {_plural(orders_touched, 'order')}",
            undoable=True,
        )

    def bulk_remove_orders_with_sku(self, order_numbers, sku):
        """Remove whole orders that contain a SKU, not just its lines."""
        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return
        sku_value = str(sku)

        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]
        orders_with_sku = selected_df_full[selected_df_full["SKU"] == sku_value][
            "Order_Number"
        ].unique()
        if len(orders_with_sku) == 0:
            return

        rows_to_remove = selected_df_full[
            selected_df_full["Order_Number"].isin(orders_with_sku)
        ]
        items_count = len(rows_to_remove)
        orders_word = _plural(len(orders_with_sku), "order")

        if not ConfirmDialog.ask(
            self.mw,
            title=f"Remove {orders_word} containing {sku_value}?",
            body=(
                f"This deletes {orders_word} ({_plural(items_count, 'item')}) "
                "entirely, not just the SKU."
            ),
            verb=f"Remove {orders_word}",
        ):
            return

        affected_rows_before = rows_to_remove.copy()
        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(
            rows_to_remove.index
        )
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_orders_with_sku",
            description=f"Bulk Remove Orders with SKU: '{sku_value}' ({len(orders_with_sku)} orders)",
            params={
                "sku": sku_value,
                "removed_orders": len(orders_with_sku),
                "removed_items": items_count,
            },
            affected_rows_before=affected_rows_before,
        )

        self.mw.selection_helper.clear_selection()
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation",
            f"Removed {len(orders_with_sku)} orders ({items_count} items) containing SKU '{sku_value}'",
        )
        self._update_undo_button()
        self._results_toast(
            f"{orders_word} containing {sku_value} removed", undoable=True
        )

    def bulk_delete_orders(self, order_numbers):
        """Exclude the given orders from the run, after a confirm."""
        self._set_selection(order_numbers)
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()
        if not selected_indexes:
            return
        orders_count, items_count = self.mw.selection_helper.get_selection_summary()
        orders_word = _plural(orders_count, "order")

        if not ConfirmDialog.ask(
            self.mw,
            title=f"Exclude {orders_word} from the run?",
            body=(
                "They leave this session's results and its reports. "
                "Undo brings them back."
            ),
            verb=f"Exclude {orders_word}",
        ):
            return

        affected_rows_before = self.mw.analysis_results_df.loc[selected_indexes].copy()

        self.mw.analysis_results_df = self.mw.analysis_results_df.drop(selected_indexes)
        self.mw.analysis_results_df = self.mw.analysis_results_df.reset_index(drop=True)

        self.mw.undo_manager.record_operation(
            operation_type="bulk_delete_orders",
            description=f"Bulk Delete: {orders_count} orders ({items_count} items)",
            params={"deleted_orders": orders_count, "deleted_items": items_count},
            affected_rows_before=affected_rows_before,
        )

        self.mw.selection_helper.clear_selection()
        self.mw.save_session_state()
        self.mw._update_all_views()
        self.mw.log_activity(
            "Bulk Operation", f"Deleted {orders_count} orders ({items_count} items)"
        )
        self._update_undo_button()
        self._results_toast(f"{orders_word} excluded from the run", undoable=True)

    def handle_multi_session_stock_export(self, session_paths: list):
        """Export combined stock summary from multiple sessions.

        Args:
            session_paths: List of session directory path strings.
        """
        from pathlib import Path

        from shopify_tool.stock_export import merge_session_stock_exports

        if not self.mw.current_client_id:
            self.log.warning(
                "handle_multi_session_stock_export called with no client selected"
            )
            return

        session_path_objs = [Path(p) for p in session_paths if Path(p).exists()]
        if len(session_path_objs) < 2:
            # Not a disabled-action guard: the button needs 2+ selected, so
            # sessions went missing on the share after they were listed.
            missing = len(session_paths) - len(session_path_objs)
            self.log.warning(
                f"Combined stock export: {missing} of {len(session_paths)} session folders not found"
            )
            show_error(
                self.mw,
                "The stock exports weren't combined",
                f"{missing} of the selected sessions couldn't be found. Check "
                "that the server share is reachable, then try again.",
            )
            return

        combined_df = merge_session_stock_exports(
            session_path_objs, self.mw.current_client_id
        )

        if combined_df.empty:
            show_error(
                self.mw,
                "Nothing to combine",
                "None of the selected sessions has a stock export. Generate one in each session first.",
            )
            return

        filename, _ = QFileDialog.getSaveFileName(
            self.mw,
            "Save Combined Stock Export",
            f"combined_stock_{len(session_path_objs)}_sessions.xls",
            "Excel 97-2003 (*.xls)",
        )
        if not filename:
            return

        if not filename.endswith(".xls"):
            filename += ".xls"

        try:
            import xlwt

            workbook = xlwt.Workbook()
            sheet = workbook.add_sheet("Sheet1")
            for col_num, value in enumerate(combined_df.columns):
                sheet.write(0, col_num, value)
            for row_num, row in combined_df.iterrows():
                for col_num, value in enumerate(row):
                    sheet.write(row_num + 1, col_num, value)
            workbook.save(filename)
            toast(
                self.mw, f"Combined stock export saved: {os.path.basename(filename)}."
            )
            self.mw.log_activity(
                "Export",
                f"Combined stock export: {len(combined_df)} SKUs from {len(session_path_objs)} sessions",
            )
        except Exception:
            self.log.exception("Failed to save combined stock export")
            show_error(
                self.mw,
                "The combined stock export wasn't saved",
                "Details are in Logs.",
            )

    def bulk_export_selection(self, order_numbers, format_type: str):
        """Export the given orders' rows to a file the user names."""
        from pathlib import Path

        self._set_selection(order_numbers)
        selected_df = self.mw.selection_helper.get_selected_orders_data()
        if selected_df.empty:
            return

        orders_count, _items_count = self.mw.selection_helper.get_selection_summary()

        if format_type == "xlsx":
            file_filter = "Excel Files (*.xlsx)"
            default_name = f"selection_{orders_count}_orders.xlsx"
        else:
            file_filter = "CSV Files (*.csv)"
            default_name = f"selection_{orders_count}_orders.csv"

        if self.mw.session_path:
            default_dir = Path(self.mw.session_path) / "exports"
            default_dir.mkdir(exist_ok=True)
            default_path = str(default_dir / default_name)
        else:
            default_path = default_name

        file_path, _ = QFileDialog.getSaveFileName(
            self.mw, "Export Selected Orders", default_path, file_filter
        )
        if not file_path:
            return

        try:
            if format_type == "xlsx":
                selected_df.to_excel(file_path, index=False, engine="openpyxl")
            else:
                selected_df.to_csv(file_path, index=False, encoding="utf-8")
        except Exception as e:
            self.log.exception("Bulk export failed")
            show_error(self.mw, "The selection wasn't exported", str(e))
            return

        self.mw.log_activity(
            "Bulk Operation",
            f"Exported {orders_count} orders to {format_type.upper()}: {Path(file_path).name}",
        )
        self._results_toast(
            f"{_plural(orders_count, 'order')} exported to {Path(file_path).name}",
            undoable=False,
        )
