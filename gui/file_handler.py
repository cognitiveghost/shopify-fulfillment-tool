import os
import logging
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox, QListWidgetItem
from PySide6.QtGui import QColor

from shopify_tool import core


class FileHandler:
    """Handles file selection dialogs, validation, and loading logic.

    This class encapsulates the functionality related to file I/O initiated
    by the user, such as selecting orders and stock files. It interacts with
    the `QFileDialog` to get file paths and then triggers validation on those
    files.

    Attributes:
        mw (MainWindow): A reference to the main window instance.
        log (logging.Logger): A logger for this class.
    """

    def __init__(self, main_window):
        """Initializes the FileHandler.

        Args:
            main_window (MainWindow): The main window instance that this
                handler will manage file operations for.
        """
        self.mw = main_window
        self.log = logging.getLogger(__name__)

    def select_orders_file(self):
        """Opens a file dialog for the user to select the orders CSV file.

        After a file is selected, it updates the corresponding UI labels,
        triggers header validation for the file, and checks if the application
        is ready to run the analysis. Auto-detects delimiter and prompts user
        if detected delimiter differs from configured one.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Orders File", "", "CSV files (*.csv)"
        )
        if not filepath:
            return

        self.mw.orders_file_path = filepath
        self.mw.orders_file_path_label.setText(os.path.basename(filepath))
        self.log.info(f"Orders file selected: {filepath}")

        # Get delimiter from config (default to comma for Shopify exports)
        config = self.mw.active_profile_config
        config_delimiter = config.get("settings", {}).get("orders_csv_delimiter", ",")

        # Auto-detect delimiter
        from shopify_tool.csv_utils import detect_csv_delimiter

        try:
            detected_delimiter, method = detect_csv_delimiter(filepath)
            self.log.info(
                f"Orders file: detected delimiter '{detected_delimiter}' using {method}"
            )
        except FileNotFoundError as e:
            self.log.error(f"Orders file not found for delimiter detection: {e}")
            detected_delimiter = ","  # fallback to comma
        except PermissionError as e:
            self.log.error(f"Permission denied reading orders file: {e}")
            detected_delimiter = ","  # fallback to comma
        except UnicodeDecodeError as e:
            self.log.error(f"Encoding error in orders file: {e}")
            detected_delimiter = ","  # fallback to comma
        except Exception as e:
            self.log.error(
                f"Unexpected error detecting delimiter for orders: {e}", exc_info=True
            )
            detected_delimiter = ","  # fallback to comma

        # Determine which delimiter to use
        delimiter = detected_delimiter  # Default to detected

        # If detected differs from config, prompt user
        if detected_delimiter != config_delimiter:
            result = QMessageBox.question(
                self.mw,
                "Delimiter Detected",
                f"Detected delimiter: '{detected_delimiter}'\n"
                f"Configured delimiter: '{config_delimiter}'\n\n"
                f"Which delimiter should be used for orders file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if result == QMessageBox.StandardButton.Yes:
                delimiter = detected_delimiter
                self.log.info(f"Using detected delimiter: '{delimiter}'")

                # Offer to update config
                update = QMessageBox.question(
                    self.mw,
                    "Update Settings",
                    f"Would you like to save '{delimiter}' as default orders delimiter?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if update == QMessageBox.StandardButton.Yes:
                    self.mw.active_profile_config["settings"][
                        "orders_csv_delimiter"
                    ] = delimiter
                    # Save config through ProfileManager
                    client_id = self.mw.active_profile_config.get("client_id")
                    if client_id and hasattr(self.mw, "profile_manager"):
                        self.mw.profile_manager.save_shopify_config(
                            client_id, self.mw.active_profile_config
                        )
                        self.log.info(f"Saved orders delimiter '{delimiter}' to config")
            else:
                delimiter = config_delimiter
                self.log.info(f"Using configured orders delimiter: '{delimiter}'")

        # Load and store original orders DataFrame for column discovery
        try:
            import pandas as pd

            orders_df = pd.read_csv(filepath, delimiter=delimiter, encoding="utf-8-sig")
            self.mw.last_loaded_orders_df = orders_df.copy()
            self.log.info(
                f"Loaded orders DataFrame: {len(orders_df)} rows, {len(orders_df.columns)} columns"
            )
        except Exception as e:
            self.log.warning(
                f"Failed to load orders DataFrame for column discovery: {e}"
            )
            # Don't fail the file selection, just skip storing the DataFrame
            self.mw.last_loaded_orders_df = None

        self.validate_file("orders")
        self.check_files_ready()

    def select_stock_file(self):
        """Opens file dialog for stock CSV selection and loads file.

        After a file is selected, it validates the file with the correct
        delimiter from the client configuration. Auto-detects delimiter
        and prompts user if detected delimiter differs from configured one.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Stock File", "", "CSV files (*.csv);;All Files (*)"
        )

        if not filepath:
            return

        self.mw.stock_file_path = filepath
        self.mw.stock_file_path_label.setText(os.path.basename(filepath))
        self.log.info(f"Stock file selected: {filepath}")

        # Get delimiter from config
        config = self.mw.active_profile_config
        config_delimiter = config.get("settings", {}).get("stock_csv_delimiter", ";")

        # Auto-detect delimiter
        from shopify_tool.csv_utils import detect_csv_delimiter

        try:
            detected_delimiter, method = detect_csv_delimiter(filepath)
            self.log.info(f"Detected delimiter '{detected_delimiter}' using {method}")
        except FileNotFoundError as e:
            self.log.error(f"Stock file not found for delimiter detection: {e}")
            detected_delimiter = ";"  # fallback
        except PermissionError as e:
            self.log.error(f"Permission denied reading stock file: {e}")
            detected_delimiter = ";"  # fallback
        except UnicodeDecodeError as e:
            self.log.error(f"Encoding error in stock file: {e}")
            detected_delimiter = ";"  # fallback
        except Exception as e:
            self.log.error(
                f"Unexpected error detecting delimiter for stock: {e}", exc_info=True
            )
            detected_delimiter = ";"  # fallback

        # Determine which delimiter to use
        delimiter = detected_delimiter  # Default to detected

        # If detected differs from config, prompt user
        if detected_delimiter != config_delimiter:
            result = QMessageBox.question(
                self.mw,
                "Delimiter Detected",
                f"Detected delimiter: '{detected_delimiter}'\n"
                f"Configured delimiter: '{config_delimiter}'\n\n"
                f"Which delimiter should be used?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if result == QMessageBox.StandardButton.Yes:
                delimiter = detected_delimiter
                self.log.info(f"Using detected delimiter: '{delimiter}'")

                # Offer to update config
                update = QMessageBox.question(
                    self.mw,
                    "Update Settings",
                    f"Would you like to save '{delimiter}' as default stock delimiter?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if update == QMessageBox.StandardButton.Yes:
                    self.mw.active_profile_config["settings"]["stock_csv_delimiter"] = (
                        delimiter
                    )
                    # Save config through ProfileManager
                    client_id = self.mw.active_profile_config.get("client_id")
                    if client_id and hasattr(self.mw, "profile_manager"):
                        self.mw.profile_manager.save_shopify_config(
                            client_id, self.mw.active_profile_config
                        )
                        self.log.info(f"Saved delimiter '{delimiter}' to config")
            else:
                delimiter = config_delimiter
                self.log.info(f"Using configured delimiter: '{delimiter}'")

        # Try to load CSV with determined delimiter to verify it's readable
        # Force SKU columns to string type to prevent float conversion
        try:
            # Get SKU columns from config to force as string
            column_mappings = self.mw.active_profile_config.get("column_mappings", {})
            stock_mappings = column_mappings.get("stock", {})
            sku_columns = [
                csv_col
                for csv_col, internal_name in stock_mappings.items()
                if internal_name == "SKU"
            ]
            dtype_dict = {col: str for col in sku_columns}

            stock_df = pd.read_csv(
                filepath, delimiter=delimiter, encoding="utf-8-sig", dtype=dtype_dict
            )
            self.log.info(
                f"Loaded stock CSV with delimiter '{delimiter}': {len(stock_df)} rows"
            )

        except Exception as e:
            self.log.error(f"Failed to load stock CSV: {e}")
            QMessageBox.critical(
                self.mw,
                "File Load Error",
                f"Failed to load stock file:\n{str(e)}\n\n"
                f"Make sure the delimiter is set correctly in Settings.\n"
                f"Current delimiter: '{delimiter}'",
            )
            return

        # Anomaly check against saved inventory memory and update snapshot
        client_id = (
            self.mw.active_profile_config.get("client_id")
            if self.mw.active_profile_config
            else None
        )
        if client_id and hasattr(self.mw, "profile_manager"):
            try:
                column_mappings = self.mw.active_profile_config.get(
                    "column_mappings", {}
                )
                stock_mappings = column_mappings.get("stock", {})
                sku_col = next(
                    (c for c, n in stock_mappings.items() if n == "SKU"), None
                )
                stock_col = next(
                    (c for c, n in stock_mappings.items() if n == "Stock"), None
                )

                # Build an internal-name view of stock for anomaly check and snapshot
                mapped_df = stock_df.copy()
                rename_map = {}
                if sku_col and sku_col in mapped_df.columns:
                    rename_map[sku_col] = "SKU"
                if stock_col and stock_col in mapped_df.columns:
                    rename_map[stock_col] = "Stock"
                if rename_map:
                    mapped_df = mapped_df.rename(columns=rename_map)

                memory = self.mw.profile_manager.get_inventory_memory(client_id)
                if memory.get("enabled", False):
                    is_anomaly, anomaly_msg = self._check_inventory_anomaly(
                        mapped_df, memory
                    )
                    if is_anomaly:
                        reply = QMessageBox.warning(
                            self.mw,
                            "Inventory Anomaly Detected",
                            f"{anomaly_msg}\n\nContinue with this stock file?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No,
                        )
                        if reply != QMessageBox.Yes:
                            # Cancel: clear the stock selection
                            self.mw.stock_file_path = None
                            self.mw.stock_file_path_label.setText("Stock file not selected")
                            self.mw.stock_file_status_label.setText("")
                            self.check_files_ready()
                            return

                # Memory is updated with Final Stock after analysis (not raw stock on load)
            except Exception as e:
                self.log.warning(f"Inventory memory check/update failed: {e}")

        # Validate headers
        self.validate_file("stock")
        self.check_files_ready()

    def _check_inventory_anomaly(
        self, new_stock_df: pd.DataFrame, memory: dict
    ) -> tuple:
        """Check whether a freshly loaded stock file looks wrong compared to saved memory.

        Returns:
            (is_anomaly: bool, message: str)
        """
        if not memory.get("skus"):
            return False, ""
        old_skus = set(memory["skus"])
        new_skus = (
            set(new_stock_df["SKU"].unique())
            if "SKU" in new_stock_df.columns
            else set()
        )
        overlap = len(old_skus & new_skus) / max(len(old_skus), 1)
        if overlap < 0.5:
            return (
                True,
                f"Only {overlap:.0%} SKU overlap with saved inventory ({len(old_skus)} known SKUs). Wrong client file?",
            )
        old_total = memory.get("total_units", 0)
        new_total = (
            new_stock_df["Stock"].sum() if "Stock" in new_stock_df.columns else 0
        )
        if old_total > 0 and abs(new_total - old_total) / old_total > 0.40:
            return (
                True,
                f"Total units changed by {(new_total - old_total) / old_total:+.0%} ({int(old_total)} → {int(new_total)}). Confirm?",
            )
        return False, ""

    def validate_file(self, file_type):
        """Validates that a selected CSV file contains the required headers.

        It reads the required column names from the client-specific configuration
        and uses `core.validate_csv_headers` to perform the check. The result
        is displayed to the user via a status label with a tooltip
        providing details on failure.

        Args:
            file_type (str): The type of file to validate, either "orders" or
                             "stock".
        """
        # Get client config from main window
        if not self.mw.current_client_id or not self.mw.current_client_config:
            self.log.warning("No client selected or config not loaded")
            return

        client_config = self.mw.current_client_config
        column_mappings = client_config.get("column_mappings", {})

        # Define which internal names are required
        REQUIRED_INTERNAL_ORDERS = [
            "Order_Number",
            "SKU",
            "Quantity",
            "Shipping_Method",
        ]
        REQUIRED_INTERNAL_STOCK = ["SKU", "Stock"]

        if file_type == "orders":
            path = self.mw.orders_file_path
            label = self.mw.orders_file_status_label
            delimiter = ","

            # Get CSV column names from v2 mappings
            orders_mappings = column_mappings.get("orders", {})

            # Backward compatibility: check for v1 format
            if not orders_mappings and "orders_required" in column_mappings:
                # V1 format - use default Shopify column names
                required_cols = [
                    "Name",
                    "Lineitem sku",
                    "Lineitem quantity",
                    "Shipping Method",
                ]
            else:
                # V2 format - extract CSV column names that map to required internal names
                required_cols = [
                    csv_col
                    for csv_col, internal in orders_mappings.items()
                    if internal in REQUIRED_INTERNAL_ORDERS
                ]

        else:  # stock
            path = self.mw.stock_file_path
            label = self.mw.stock_file_status_label
            delimiter = client_config.get("settings", {}).get(
                "stock_csv_delimiter", ";"
            )

            # Get CSV column names from v2 mappings
            stock_mappings = column_mappings.get("stock", {})

            # Backward compatibility: check for v1 format
            if not stock_mappings and "stock_required" in column_mappings:
                # V1 format - use default Bulgarian column names
                required_cols = ["Артикул", "Наличност"]
            else:
                # V2 format - extract CSV column names that map to required internal names
                required_cols = [
                    csv_col
                    for csv_col, internal in stock_mappings.items()
                    if internal in REQUIRED_INTERNAL_STOCK
                ]

        if not path:
            self.log.warning(f"Validation skipped for '{file_type}': path is missing.")
            return

        self.log.info(f"Validating '{file_type}' file: {path}")
        is_valid, missing_cols = core.validate_csv_headers(
            path, required_cols, delimiter
        )

        if is_valid:
            label.setText("✓")
            label.setStyleSheet("color: green; font-weight: bold;")
            label.setToolTip("File is valid.")
            self.log.info(f"'{file_type}' file is valid.")
        else:
            label.setText("✗")
            label.setStyleSheet("color: red; font-weight: bold;")
            tooltip_text = f"Missing columns: {', '.join(missing_cols)}"
            label.setToolTip(tooltip_text)
            self.log.warning(f"'{file_type}' file is invalid. {tooltip_text}")

    def check_files_ready(self):
        """Checks if both orders and stock files are selected and valid.

        If both files have been selected and have passed validation, this
        method enables the main 'Run Analysis' button in the UI. Otherwise,
        the button remains disabled.
        """
        orders_ok = (
            self.mw.orders_file_path and self.mw.orders_file_status_label.text() == "✓"
        )
        stock_ok = (
            self.mw.stock_file_path and self.mw.stock_file_status_label.text() == "✓"
        )
        if orders_ok and stock_ok:
            self.mw.run_analysis_button.setEnabled(True)
            self.log.info("Both files are validated and ready for analysis.")
        else:
            self.mw.run_analysis_button.setEnabled(False)

    # ============================================================
    # Folder Loading Support (New)
    # ============================================================

    def on_orders_select_clicked(self):
        """Handle orders select button click (adapts to mode)."""
        is_folder_mode = self.mw.orders_folder_radio.isChecked()

        if is_folder_mode:
            self.select_orders_folder()
        else:
            self.select_orders_file()

    def on_stock_select_clicked(self):
        """Handle stock select button click (adapts to mode)."""
        is_folder_mode = self.mw.stock_folder_radio.isChecked()

        if is_folder_mode:
            self.select_stock_folder()
        else:
            self.select_stock_file()

    def select_orders_folder(self):
        """
        Handle orders folder selection with multiple CSV files.

        Workflow:
        1. Open folder dialog
        2. Scan for CSV files
        3. Validate all files
        4. Show preview
        5. Merge files
        6. Save to temp
        7. Store merged path
        """
        # 1. Open folder dialog
        folder_path = QFileDialog.getExistingDirectory(
            self.mw, "Select Orders Folder", "", QFileDialog.ShowDirsOnly
        )

        if not folder_path:
            return

        self.log.info(f"Orders folder selected: {folder_path}")

        # 2. Scan for CSV files
        recursive = self.mw.orders_recursive_checkbox.isChecked()
        csv_files = self.scan_folder_for_csv(folder_path, recursive)

        if not csv_files:
            QMessageBox.warning(
                self.mw,
                "No Files Found",
                f"No CSV files found in folder:\n{folder_path}",
            )
            return

        self.log.info(f"Found {len(csv_files)} CSV files")

        # 3. Validate all files
        try:
            valid_files, invalid_files, total_rows = self.validate_multiple_files(
                csv_files, "orders"
            )
        except Exception as e:
            QMessageBox.critical(
                self.mw, "Validation Error", f"Error validating files:\n{str(e)}"
            )
            return

        # 4. Check if any valid files
        if not valid_files:
            msg = f"All {len(csv_files)} files are invalid.\n\n"
            msg += "Invalid files:\n"
            for filepath, missing in invalid_files[:5]:  # Show first 5
                msg += (
                    f"  • {os.path.basename(filepath)}: missing {', '.join(missing)}\n"
                )

            QMessageBox.critical(self.mw, "No Valid Files", msg)
            return

        # 5. Show preview and confirm
        if not self.show_file_preview("orders", valid_files, invalid_files, total_rows):
            return  # User cancelled

        # 6. Merge files
        try:
            merged_path = self.merge_and_save_files(valid_files, "orders", folder_path)
        except Exception as e:
            QMessageBox.critical(
                self.mw, "Merge Failed", f"Failed to merge files:\n{str(e)}"
            )
            return

        # 7. Store merged path and update UI
        self.mw.orders_file_path = merged_path
        self.mw.orders_source_files = valid_files  # Store for reference

        # Load and store original orders DataFrame for column discovery
        try:
            import pandas as pd

            delimiter = self.mw.active_profile_config.get("settings", {}).get(
                "orders_csv_delimiter", ","
            )
            orders_df = pd.read_csv(
                merged_path, delimiter=delimiter, encoding="utf-8-sig"
            )
            self.mw.last_loaded_orders_df = orders_df.copy()
            self.log.info(
                f"Loaded merged orders DataFrame: {len(orders_df)} rows, {len(orders_df.columns)} columns"
            )
        except Exception as e:
            self.log.warning(
                f"Failed to load merged orders DataFrame for column discovery: {e}"
            )
            # Don't fail the merge, just skip storing the DataFrame
            self.mw.last_loaded_orders_df = None

        # Update UI
        self.mw.orders_file_path_label.setText(
            f"{len(valid_files)} files merged ({total_rows} rows)"
        )

        # Update file list widget
        self.mw.orders_file_list_widget.clear()
        for filepath in valid_files:
            item = QListWidgetItem(f"{os.path.basename(filepath)}")
            item.setForeground(QColor("green"))
            self.mw.orders_file_list_widget.addItem(item)

        for filepath, missing in invalid_files:
            item = QListWidgetItem(
                f"{os.path.basename(filepath)} (missing: {', '.join(missing)})"
            )
            item.setForeground(QColor("red"))
            self.mw.orders_file_list_widget.addItem(item)

        self.mw.orders_file_count_label.setText(
            f"Total: {len(valid_files)} valid, {len(invalid_files)} invalid, {total_rows} rows"
        )

        # Validate merged file
        self.validate_file("orders")

        # Check if ready to run analysis
        self.check_files_ready()

        self.log.info(
            f"Successfully merged {len(valid_files)} files into {merged_path}"
        )

    def select_stock_folder(self):
        """
        Handle stock folder selection with multiple CSV files.

        Workflow is same as select_orders_folder but for stock files.
        """
        # 1. Open folder dialog
        folder_path = QFileDialog.getExistingDirectory(
            self.mw, "Select Stock Folder", "", QFileDialog.ShowDirsOnly
        )

        if not folder_path:
            return

        self.log.info(f"Stock folder selected: {folder_path}")

        # 2. Scan for CSV files
        recursive = self.mw.stock_recursive_checkbox.isChecked()
        csv_files = self.scan_folder_for_csv(folder_path, recursive)

        if not csv_files:
            QMessageBox.warning(
                self.mw,
                "No Files Found",
                f"No CSV files found in folder:\n{folder_path}",
            )
            return

        self.log.info(f"Found {len(csv_files)} CSV files")

        # 3. Validate all files
        try:
            valid_files, invalid_files, total_rows = self.validate_multiple_files(
                csv_files, "stock"
            )
        except Exception as e:
            QMessageBox.critical(
                self.mw, "Validation Error", f"Error validating files:\n{str(e)}"
            )
            return

        # 4. Check if any valid files
        if not valid_files:
            msg = f"All {len(csv_files)} files are invalid.\n\n"
            msg += "Invalid files:\n"
            for filepath, missing in invalid_files[:5]:  # Show first 5
                msg += (
                    f"  • {os.path.basename(filepath)}: missing {', '.join(missing)}\n"
                )

            QMessageBox.critical(self.mw, "No Valid Files", msg)
            return

        # 5. Show preview and confirm
        if not self.show_file_preview("stock", valid_files, invalid_files, total_rows):
            return  # User cancelled

        # 6. Merge files
        try:
            merged_path = self.merge_and_save_files(valid_files, "stock", folder_path)
        except Exception as e:
            QMessageBox.critical(
                self.mw, "Merge Failed", f"Failed to merge files:\n{str(e)}"
            )
            return

        # 7. Store merged path and update UI
        self.mw.stock_file_path = merged_path
        self.mw.stock_source_files = valid_files  # Store for reference

        # Update UI
        self.mw.stock_file_path_label.setText(
            f"{len(valid_files)} files merged ({total_rows} rows)"
        )

        # Update file list widget
        self.mw.stock_file_list_widget.clear()
        for filepath in valid_files:
            item = QListWidgetItem(f"{os.path.basename(filepath)}")
            item.setForeground(QColor("green"))
            self.mw.stock_file_list_widget.addItem(item)

        for filepath, missing in invalid_files:
            item = QListWidgetItem(
                f"{os.path.basename(filepath)} (missing: {', '.join(missing)})"
            )
            item.setForeground(QColor("red"))
            self.mw.stock_file_list_widget.addItem(item)

        self.mw.stock_file_count_label.setText(
            f"Total: {len(valid_files)} valid, {len(invalid_files)} invalid, {total_rows} rows"
        )

        # Validate merged file
        self.validate_file("stock")

        # Check if ready to run analysis
        self.check_files_ready()

        self.log.info(
            f"Successfully merged {len(valid_files)} files into {merged_path}"
        )

    def scan_folder_for_csv(
        self, folder_path: str, recursive: bool = False, pattern: str = "*.csv"
    ) -> List[str]:
        """
        Scan folder for CSV files.

        Args:
            folder_path: Folder to scan
            recursive: Include subfolders
            pattern: File pattern (default: *.csv)

        Returns:
            List of CSV file paths (sorted by name)
        """
        folder = Path(folder_path)

        if recursive:
            csv_files = list(folder.rglob(pattern))
        else:
            csv_files = list(folder.glob(pattern))

        # Sort by filename
        csv_files.sort(key=lambda p: p.name.lower())

        # Convert to strings
        result = [str(f) for f in csv_files]

        self.log.info(
            f"Scanned folder (recursive={recursive}): found {len(result)} files"
        )

        return result

    def validate_multiple_files(
        self, file_paths: List[str], file_type: str
    ) -> Tuple[List[str], List[Tuple[str, List[str]]], int]:
        """
        Validate multiple CSV files.

        Args:
            file_paths: List of file paths to validate
            file_type: "orders" or "stock"

        Returns:
            Tuple: (valid_files, invalid_files, total_rows)
                valid_files: List of valid file paths
                invalid_files: List of (filepath, missing_columns)
                total_rows: Total rows across all valid files
        """
        valid_files = []
        invalid_files = []
        total_rows = 0

        # Get config
        config = self.mw.active_profile_config
        column_mappings = config.get("column_mappings", {})

        # Get required columns based on file type
        if file_type == "orders":
            REQUIRED_INTERNAL = ["Order_Number", "SKU", "Quantity", "Shipping_Method"]
            mappings = column_mappings.get("orders", {})
            delimiter_key = "orders_csv_delimiter"
            default_delimiter = ","
        else:  # stock
            REQUIRED_INTERNAL = ["SKU", "Stock"]
            mappings = column_mappings.get("stock", {})
            delimiter_key = "stock_csv_delimiter"
            default_delimiter = ";"

        # Get CSV column names that map to required internal names
        required_csv_cols = [
            csv_col
            for csv_col, internal_name in mappings.items()
            if internal_name in REQUIRED_INTERNAL
        ]

        # Get delimiter from config
        delimiter = config.get("settings", {}).get(delimiter_key, default_delimiter)

        self.log.info(f"Validating {len(file_paths)} {file_type} files...")
        self.log.info(f"Required columns: {required_csv_cols}")

        # Validate each file
        for filepath in file_paths:
            try:
                # Auto-detect delimiter for this file
                from shopify_tool.csv_utils import detect_csv_delimiter

                detected_delimiter, _ = detect_csv_delimiter(filepath)

                # Use detected delimiter
                file_delimiter = detected_delimiter

                # Validate headers
                is_valid, missing_cols = core.validate_csv_headers(
                    filepath, required_csv_cols, file_delimiter
                )

                if is_valid:
                    valid_files.append(filepath)

                    # Count rows
                    df = pd.read_csv(
                        filepath, delimiter=file_delimiter, encoding="utf-8-sig"
                    )
                    total_rows += len(df)

                    self.log.info(f"  {os.path.basename(filepath)}: {len(df)} rows")
                else:
                    invalid_files.append((filepath, missing_cols))
                    self.log.warning(
                        f"  {os.path.basename(filepath)}: missing {missing_cols}"
                    )

            except Exception as e:
                invalid_files.append((filepath, [f"Error: {str(e)}"]))
                self.log.error(f"  {os.path.basename(filepath)}: {e}")

        return valid_files, invalid_files, total_rows

    def show_file_preview(
        self,
        file_type: str,
        valid_files: List[str],
        invalid_files: List[Tuple[str, List[str]]],
        total_rows: int,
    ) -> bool:
        """
        Show preview dialog with file list.

        Returns:
            True if user confirms, False if cancelled
        """
        msg = f"Found {len(valid_files) + len(invalid_files)} CSV files\n\n"

        msg += f"Valid: {len(valid_files)} files ({total_rows} rows)\n"
        if invalid_files:
            msg += f"Invalid: {len(invalid_files)} files\n"

        msg += "\n"

        # Show first 10 valid files
        if valid_files:
            msg += "Valid files:\n"
            for filepath in valid_files[:10]:
                msg += f"  • {os.path.basename(filepath)}\n"
            if len(valid_files) > 10:
                msg += f"  ... and {len(valid_files) - 10} more\n"
            msg += "\n"

        # Show first 5 invalid files
        if invalid_files:
            msg += "Invalid files:\n"
            for filepath, missing in invalid_files[:5]:
                msg += (
                    f"  • {os.path.basename(filepath)}: missing {', '.join(missing)}\n"
                )
            if len(invalid_files) > 5:
                msg += f"  ... and {len(invalid_files) - 5} more\n"
            msg += "\n"

        # Duplicate warning (if applicable)
        remove_duplicates = getattr(
            self.mw, f"{file_type}_remove_duplicates_checkbox", None
        )
        if remove_duplicates and remove_duplicates.isChecked():
            msg += "Duplicates will be removed (keep first occurrence)\n\n"

        msg += f"Continue with {len(valid_files)} valid files?"

        reply = QMessageBox.question(
            self.mw, "Confirm Merge", msg, QMessageBox.Yes | QMessageBox.No
        )

        return reply == QMessageBox.Yes

    def merge_and_save_files(
        self, file_paths: List[str], file_type: str, original_folder: str
    ) -> str:
        """
        Merge CSV files and save to temp location.

        Args:
            file_paths: List of valid file paths
            file_type: "orders" or "stock"
            original_folder: Original folder path (for logging)

        Returns:
            Path to merged CSV file
        """
        from shopify_tool.csv_utils import merge_csv_files

        # Get config
        config = self.mw.active_profile_config
        column_mappings = config.get("column_mappings", {})

        # Get settings based on file type
        if file_type == "orders":
            delimiter = config.get("settings", {}).get("orders_csv_delimiter", ",")

            # Get SKU columns to force as string type
            orders_mappings = column_mappings.get("orders", {})
            sku_columns = [
                csv_col
                for csv_col, internal_name in orders_mappings.items()
                if internal_name == "SKU"
            ]
            dtype_dict = {col: str for col in sku_columns}

            # Dynamically find duplicate key columns from mappings
            # For orders: check duplicates on Order_Number + SKU
            duplicate_keys = []
            for csv_col, internal_name in orders_mappings.items():
                if internal_name in ["Order_Number", "SKU"]:
                    duplicate_keys.append(csv_col)

            remove_dups_checkbox = self.mw.orders_remove_duplicates_checkbox
        else:  # stock
            delimiter = config.get("settings", {}).get("stock_csv_delimiter", ";")

            # Get SKU columns to force as string type
            stock_mappings = column_mappings.get("stock", {})
            sku_columns = [
                csv_col
                for csv_col, internal_name in stock_mappings.items()
                if internal_name == "SKU"
            ]
            dtype_dict = {col: str for col in sku_columns}

            # Try to find the SKU column name from mappings
            sku_col_name = None
            for csv_col, internal_name in stock_mappings.items():
                if internal_name == "SKU":
                    sku_col_name = csv_col
                    break

            duplicate_keys = [sku_col_name] if sku_col_name else []
            remove_dups_checkbox = self.mw.stock_remove_duplicates_checkbox

        # Merge files
        self.log.info(f"Merging {len(file_paths)} {file_type} files...")
        self.log.info(f"Duplicate keys for {file_type}: {duplicate_keys}")
        self.log.info(f"Remove duplicates: {remove_dups_checkbox.isChecked()}")

        merged_df = merge_csv_files(
            file_paths,
            delimiter=delimiter,
            dtype_dict=dtype_dict,
            add_source_column=True,
            remove_duplicates=remove_dups_checkbox.isChecked(),
            duplicate_keys=duplicate_keys
            if (remove_dups_checkbox.isChecked() and duplicate_keys)
            else None,
        )

        self.log.info(f"Merge complete: {len(merged_df)} rows")

        # Save to temp location
        # Use session path if available, otherwise temp dir
        if hasattr(self.mw, "session_path") and self.mw.session_path:
            temp_dir = Path(self.mw.session_path) / "input"
            temp_dir.mkdir(parents=True, exist_ok=True)
        else:
            temp_dir = Path(tempfile.gettempdir())

        merged_filename = f"merged_{file_type}.csv"
        merged_path = temp_dir / merged_filename

        # Save
        merged_df.to_csv(merged_path, index=False, encoding="utf-8-sig")

        self.log.info(f"Saved merged file: {merged_path}")

        return str(merged_path)
