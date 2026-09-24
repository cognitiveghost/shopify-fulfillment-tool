import logging
import os
import tempfile
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QFileDialog

from gui.components import ConfirmDialog, show_error
from shopify_tool import core
from shopify_tool.csv_utils import (
    AUTO_DELIMITER,
    merge_csv_files,
    resolve_delimiter,
)

# Folder mode used to ask for these with two checkboxes each, in the widget
# cluster Bundle 5 deleted. Spec §10.3 puts them back inside the loaded slot;
# until that slot UI exists they are the behaviour a warehouse actually wants
# -- pick a folder, get everything in it, once each.
# ponytail: constants, not settings. Bind them to the slot's toggles when
# §10.3's in-slot controls get built.
_FOLDER_SCAN_RECURSIVE = True


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

    def _delimiter_for(self, kind: str, path: str) -> str:
        """The delimiter `path` is read with: the client's override, or Auto."""
        settings = (self.mw.active_profile_config or {}).get("settings", {})
        return resolve_delimiter(path, settings.get(f"{kind}_csv_delimiter"), kind)

    def select_orders_file(self):
        """Opens a file dialog for the user to select the orders CSV file.

        After a file is selected, it updates the corresponding UI labels,
        triggers header validation for the file, and checks if the application
        is ready to run the analysis. The file is read with the client's
        delimiter setting: Auto detects it per file, an override is used as is.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Orders File", "", "CSV files (*.csv)"
        )
        if not filepath:
            return

        self.mw.orders_file_path = filepath
        self.log.info(f"Orders file selected: {filepath}")

        delimiter = self._delimiter_for("orders", filepath)

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
        delimiter setting: Auto detects it per file, an override is used as is.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Stock File", "", "CSV files (*.csv);;All Files (*)"
        )

        if not filepath:
            return

        self.mw.stock_file_path = filepath
        self.log.info(f"Stock file selected: {filepath}")

        delimiter = self._delimiter_for("stock", filepath)

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

        except Exception:
            self.log.exception("Failed to load stock CSV")
            show_error(
                self.mw,
                "The stock file wasn't loaded",
                f"Check the stock delimiter in Settings › General (it read {delimiter!r}), then choose the file again.",
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
                    if is_anomaly and not ConfirmDialog.ask(
                        self.mw,
                        title="Use this stock file?",
                        body=anomaly_msg,
                        verb="Use this stock file",
                    ):
                        # Cancel: clear the stock selection
                        self.clear_file("stock")
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
        from shopify_tool.csv_utils import normalize_sku

        # Normalise both sides, not just the new one: save_inventory_memory has
        # normalised its keys since #247, but a config written before that still
        # holds raw ones, and an un-normalised key would read as 0% overlap
        # forever -- the same bug, from the other direction.
        old_skus = {normalize_sku(k) for k in memory["skus"]}
        # pandas reads numeric SKUs as float64, so an un-normalised 5170.0 never
        # matched a stored "5170" and every overlap read as 0%.
        new_skus = (
            {normalize_sku(s) for s in new_stock_df["SKU"].unique()}
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
        new_total = core.inventory_total_units(new_stock_df)
        if old_total > 0 and abs(new_total - old_total) / old_total > 0.40:
            return (
                True,
                f"Total units changed by {(new_total - old_total) / old_total:+.0%} ({int(old_total)} → {int(new_total)}). Confirm?",
            )
        return False, ""

    def validate_file(self, file_type, summary: str | None = None):
        """Validates that a selected CSV file contains the required headers.

        It reads the required column names from the client-specific configuration
        and uses `core.validate_csv_headers` to perform the check. The result
        is displayed to the user via a status label with a tooltip
        providing details on failure.

        Args:
            file_type (str): The type of file to validate, either "orders" or
                             "stock".
            summary (str, optional): What the loaded slot should say instead
                of the single-file row/column count. Folder mode passes the
                merge's own summary, which the merged file cannot describe.
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

        delimiter = self._delimiter_for(file_type, path)
        self.log.info(f"Validating '{file_type}' file: {path}")
        is_valid, missing_cols = core.validate_csv_headers(
            path, required_cols, delimiter
        )

        slot = self.mw.orders_slot if file_type == "orders" else self.mw.stock_slot
        if is_valid:
            slot.set_loaded(path, summary or self._summary_for(path, required_cols))
            self.log.info(f"'{file_type}' file is valid.")
        else:
            present = core.read_csv_headers(path, delimiter)
            slot.set_invalid(path, missing_cols, present)
            self.log.warning(
                f"'{file_type}' file is invalid. Missing columns: "
                f"{', '.join(missing_cols)}"
            )

    def _summary_for(self, path, required_cols: list[str]) -> str:
        """ "1 842 rows · 4 columns matched" -- what the loaded slot shows.

        A row count is the one number that tells a supervisor they picked
        this morning's export and not last Friday's.
        """
        rows = core.count_csv_rows(path)
        return f"{rows:,} rows · {len(required_cols)} columns matched".replace(",", " ")

    def check_files_ready(self):
        """Checks if both orders and stock files are selected and valid.

        If both files have been selected and have passed validation, this
        method enables the main 'Run Analysis' button in the UI. Otherwise,
        the button remains disabled.
        """
        orders_ok = self.mw.orders_slot.is_valid
        stock_ok = self.mw.stock_slot.is_valid
        if orders_ok and stock_ok:
            self.mw.run_analysis_button.setEnabled(True)
            self.log.info("Both files are validated and ready for analysis.")
        else:
            self.mw.run_analysis_button.setEnabled(False)
        return orders_ok and stock_ok

    def clear_file(self, file_type: str) -> None:
        """Empty one slot: forget the path, reset the widget, re-gate the run.

        slot.clear() emits `changed` -> check_files_ready, but that only knows
        about the two slots. update_ui_state is the one that also knows
        inventory memory can stand in for a stock file, so without it the
        memory-mode user -- the very one who wants an unwanted stock file
        gone -- clears the slot and watches Run Analysis go grey for good.
        """
        setattr(self.mw, f"{file_type}_file_path", None)
        getattr(self.mw, f"{file_type}_slot").clear()
        self.mw.update_ui_state()
        self.log.info(f"Cleared the {file_type} slot")

    def accept_dropped_path(self, file_type: str, path: str) -> None:
        """A file or a folder was dropped on a FileSlot -- load it in place.

        Reuses validate_file() / load_folder(), the same routes the two
        buttons run after a selection, rather than a third validation path.
        A folder is a supported gesture, not a malformed file: without this
        branch it reaches pandas and raises IsADirectoryError.
        """
        if os.path.isdir(path):
            self.load_folder(file_type, path)
            return

        if file_type == "orders":
            self.mw.orders_file_path = path
        else:
            self.mw.stock_file_path = path
        self.validate_file(file_type)
        self.check_files_ready()

    # ============================================================
    # Folder Loading Support
    # ============================================================

    def select_folder(self, file_type: str) -> None:
        """Pick a folder of CSVs for this slot, then load it.

        The slot's own `Choose folder…` button is the only way in. There
        used to be two of these, one per file type, differing in nothing but
        which widgets they wrote to; now that both write to a FileSlot there
        is nothing left to differ in.
        """
        label = "Orders" if file_type == "orders" else "Stock"
        folder_path = QFileDialog.getExistingDirectory(
            self.mw, f"Select {label} Folder", "", QFileDialog.ShowDirsOnly
        )
        if not folder_path:
            return
        self.load_folder(file_type, folder_path)

    def load_folder(self, file_type: str, folder_path: str) -> None:
        """Scan, validate, merge and load a folder of CSVs into a slot.

        Split from select_folder so a dropped folder takes the same route as
        a picked one -- the slot accepts either gesture, and they must not
        be able to drift apart.
        """
        self.log.info(f"{file_type} folder selected: {folder_path}")

        csv_files = self.scan_folder_for_csv(folder_path, _FOLDER_SCAN_RECURSIVE)
        if not csv_files:
            show_error(
                self.mw,
                f"No CSV files in {folder_path}",
                "Choose a folder that holds the exported CSV files.",
            )
            return

        try:
            valid_files, invalid_files, total_rows = self.validate_multiple_files(
                csv_files, file_type
            )
        except Exception:
            self.log.exception("Error validating files")
            show_error(
                self.mw, "The files couldn't be validated", "Details are in Logs."
            )
            return

        if not valid_files:
            names = ", ".join(os.path.basename(f) for f, _m in invalid_files[:5])
            show_error(
                self.mw,
                f"None of the {len(csv_files)} files are valid",
                f"{names}. Details are in Logs.",
            )
            return

        if not self.show_file_preview(
            file_type, valid_files, invalid_files, total_rows
        ):
            return  # User cancelled

        try:
            merged_path, rows, skipped = self.merge_and_save_files(
                valid_files, file_type, folder_path
            )
        except Exception:
            self.log.exception("Failed to merge files")
            show_error(self.mw, "The files weren't merged", "Details are in Logs.")
            return

        if file_type == "orders":
            self.mw.orders_file_path = merged_path
            self.mw.orders_source_files = valid_files
            self._remember_orders_dataframe(merged_path)
        else:
            self.mw.stock_file_path = merged_path
            self.mw.stock_source_files = valid_files

        summary = f"{len(valid_files)} files merged · " + f"{rows:,} rows".replace(
            ",", " "
        )
        if skipped:
            noun = "order" if file_type == "orders" else "SKU"
            summary += f" · {skipped} overlapping {noun}{'' if skipped == 1 else 's'} skipped"
        if invalid_files:
            summary += f" · {len(invalid_files)} skipped"

        self.validate_file(file_type, summary=summary)
        self.check_files_ready()
        self.log.info(
            f"Successfully merged {len(valid_files)} files into {merged_path}"
        )

    def _remember_orders_dataframe(self, path: str) -> None:
        """Keep the merged orders in memory for column discovery.

        Failing here must not fail the merge: the file on disk is good, and
        the only thing lost is the settings screen's column suggestions.
        """
        try:
            delimiter = self._delimiter_for("orders", path)
            orders_df = pd.read_csv(path, delimiter=delimiter, encoding="utf-8-sig")
            self.mw.last_loaded_orders_df = orders_df.copy()
            self.log.info(
                f"Loaded merged orders DataFrame: {len(orders_df)} rows, "
                f"{len(orders_df.columns)} columns"
            )
        except Exception as e:
            self.log.warning(
                f"Failed to load merged orders DataFrame for column discovery: {e}"
            )
            self.mw.last_loaded_orders_df = None

    def scan_folder_for_csv(
        self, folder_path: str, recursive: bool = False, pattern: str = "*.csv"
    ) -> list[str]:
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
        self, file_paths: list[str], file_type: str
    ) -> tuple[list[str], list[tuple[str, list[str]]], int]:
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
        else:  # stock
            REQUIRED_INTERNAL = ["SKU", "Stock"]
            mappings = column_mappings.get("stock", {})

        # Get CSV column names that map to required internal names
        required_csv_cols = [
            csv_col
            for csv_col, internal_name in mappings.items()
            if internal_name in REQUIRED_INTERNAL
        ]

        self.log.info(f"Validating {len(file_paths)} {file_type} files...")
        self.log.info(f"Required columns: {required_csv_cols}")

        # Validate each file
        for filepath in file_paths:
            try:
                file_delimiter = self._delimiter_for(file_type, filepath)

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
                invalid_files.append((filepath, [f"Error: {e!s}"]))
                self.log.exception(f"  {os.path.basename(filepath)}")

        return valid_files, invalid_files, total_rows

    def show_file_preview(
        self,
        file_type: str,
        valid_files: list[str],
        invalid_files: list[tuple[str, list[str]]],
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

        thing = "An order" if file_type == "orders" else "A SKU"
        msg += f"{thing} found in more than one file is taken from the newest file.\n\n"

        n = len(valid_files)
        return ConfirmDialog.ask(
            self.mw, title=f"Merge {n} files?", body=msg, verb=f"Merge {n} files"
        )

    def merge_and_save_files(
        self, file_paths: list[str], file_type: str, original_folder: str
    ) -> tuple[str, int, int]:
        """
        Merge CSV files and save to temp location.

        A key found in several files is taken whole from the newest one
        (csv_utils.merge_csv_files: the owning-file rule).

        Args:
            file_paths: List of valid file paths
            file_type: "orders" or "stock"
            original_folder: Original folder path (for logging)

        Returns:
            (merged CSV path, rows written, distinct keys skipped from
            non-owning files)
        """
        config = self.mw.active_profile_config
        mappings = config.get("column_mappings", {}).get(file_type, {})

        # Force SKU columns to string type
        dtype_dict = {col: str for col, n in mappings.items() if n == "SKU"}

        owner_key = next(
            (
                c
                for c, n in mappings.items()
                if n == ("Order_Number" if file_type == "orders" else "SKU")
            ),
            None,
        )
        if owner_key is None:
            self.log.warning(
                f"No column mapped as the {file_type} key; merging without the owning-file rule"
            )
        setting = config.get("settings", {}).get(f"{file_type}_csv_delimiter")

        self.log.info(f"Merging {len(file_paths)} {file_type} files...")
        merged_df, skipped = merge_csv_files(
            file_paths,
            setting,
            file_type,
            dtype_dict=dtype_dict,
            add_source_column=True,
            owner_key=owner_key,
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
        # The merge is written in the override if there is one, else comma;
        # the analysis reads it back through the same setting.
        sep = "," if not setting or setting == AUTO_DELIMITER else setting
        merged_df.to_csv(merged_path, index=False, encoding="utf-8-sig", sep=sep)

        self.log.info(f"Saved merged file: {merged_path}")

        return str(merged_path), len(merged_df), skipped
