import logging
import os
import tempfile
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QFileDialog

from gui.components import ConfirmDialog
from gui.setup_state import FILE_NOUN, MAPPING_PAGE
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

# What each kind of file must carry, and the column that counts its orders or
# its SKUs.
_REQUIRED = {
    "orders": ("Order_Number", "SKU", "Quantity", "Shipping_Method"),
    "stock": ("SKU", "Stock"),
}
_KEY = {"orders": "Order_Number", "stock": "SKU"}
# A v1 profile names no columns: these are the defaults it meant.
_V1_COLUMNS = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method",
    },
    "stock": {"Артикул": "SKU", "Наличност": "Stock"},
}


def _columns(config: dict | None, kind: str) -> dict:
    """CSV column -> internal name, for the columns this client maps."""
    mappings = (config or {}).get("column_mappings", {})
    columns = mappings.get(kind, {})
    if not columns and f"{kind}_required" in mappings:
        return _V1_COLUMNS[kind]
    return columns


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
        """Opens a file dialog for the orders CSV, then loads what was chosen."""
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Orders File", "", "CSV files (*.csv)"
        )
        if filepath:
            self.load_file("orders", filepath)

    def select_stock_file(self):
        """Opens a file dialog for the stock CSV, then loads what was chosen."""
        filepath, _ = QFileDialog.getOpenFileName(
            self.mw, "Select Stock File", "", "CSV files (*.csv);;All Files (*)"
        )
        if filepath:
            self.load_file("stock", filepath)

    def load_file(self, kind: str, path: str) -> None:
        """A picked or a dropped path, loaded into its slot. One route for both.

        A folder is a supported gesture, not a malformed file. The file is
        read with the client's delimiter setting: Auto detects it per file,
        an override is used as is.
        """
        if not self.mw.session_path:
            self.log.warning(f"load_file({kind!r}) called with no session open")
            return
        if os.path.isdir(path):
            self.load_folder(kind, path)
            return

        setattr(self.mw, f"{kind}_file_path", path)
        self.log.info(f"{kind} file selected: {path}")
        if kind == "orders":
            # For column discovery in Client settings; a failure here must not
            # fail the load.
            self._remember_orders_dataframe(path)
        elif not self._stock_file_usable(path):
            return
        self.validate_file(kind)

    def _fail(self, kind: str, path, title: str, text: str, fix_page: str = "") -> None:
        """The file cannot be used: say so in its card and forget its path."""
        setattr(self.mw, f"{kind}_file_path", None)
        getattr(self.mw, f"{kind}_slot").set_problem(path, title, text, fix_page)

    def _stock_file_usable(self, path: str) -> bool:
        """Read the stock file once and check it against inventory memory.

        False when it cannot be read (its card says why) or when the operator
        turned it down at the anomaly check (its slot is emptied).
        """
        delimiter = ""
        try:
            delimiter = self._delimiter_for("stock", path)
            # SKU columns as text, so a numeric SKU is not read as a float.
            dtype = {
                column: str
                for column, name in _columns(self.mw.active_profile_config, "stock").items()
                if name == "SKU"
            }
            stock_df = pd.read_csv(
                path, delimiter=delimiter, encoding="utf-8-sig", dtype=dtype
            )
            self.log.info(
                f"Loaded stock CSV with delimiter '{delimiter}': {len(stock_df)} rows"
            )
        except Exception:
            self.log.exception("Failed to load stock CSV")
            self._fail(
                "stock",
                path,
                "The stock file couldn't be read",
                f"It was read with “{delimiter}” as the delimiter. Check the stock "
                "delimiter in Client settings › General, then replace the file.",
                "General",
            )
            return False

        client_id = (self.mw.active_profile_config or {}).get("client_id")
        if client_id and hasattr(self.mw, "profile_manager"):
            try:
                stock_mappings = _columns(self.mw.active_profile_config, "stock")
                # An internal-name view of the stock file for the anomaly check.
                rename_map = {
                    column: name
                    for column, name in stock_mappings.items()
                    if name in ("SKU", "Stock") and column in stock_df.columns
                }
                mapped_df = stock_df.rename(columns=rename_map)

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
                        self.clear_file("stock")
                        return False
                # Memory is updated with Final Stock after analysis, not on load.
            except Exception as e:
                self.log.warning(f"Inventory memory check/update failed: {e}")
        return True

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

    def validate_file(self, file_type, loaded: dict | None = None):
        """Checks a selected CSV for its mapped columns and writes its slot.

        The required column names come from the client's column mappings.
        A valid file loads the slot with its row count, its orders or SKUs
        and its delimiter; anything else is a problem the card explains.

        Args:
            file_type (str): "orders" or "stock".
            loaded (dict, optional): For a folder merge, what the merged file
                cannot say about itself: name, parts, note, delimiter.
        """
        if not self.mw.current_client_id or not self.mw.active_profile_config:
            self.log.warning("No client selected or config not loaded")
            return

        path = getattr(self.mw, f"{file_type}_file_path")
        if not path:
            self.log.warning(f"Validation skipped for '{file_type}': path is missing.")
            return

        columns = _columns(self.mw.active_profile_config, file_type)
        required_cols = [c for c, name in columns.items() if name in _REQUIRED[file_type]]
        key_column = next(
            (c for c, name in columns.items() if name == _KEY[file_type]), None
        )

        delimiter = self._delimiter_for(file_type, path)
        self.log.info(f"Validating '{file_type}' file: {path}")
        is_valid, missing_cols = core.validate_csv_headers(
            path, required_cols, delimiter
        )

        slot = getattr(self.mw, f"{file_type}_slot")
        if loaded is None and slot.is_folder and slot.path == Path(path):
            # Re-validating a merged folder (after a settings save): the
            # merged file cannot say it was a folder, the slot still can.
            loaded = {
                "name": slot.name,
                "parts": slot.parts,
                "note": slot.note,
                "delimiter": slot.delimiter,
            }
        if is_valid:
            rows, keys = core.csv_row_stats(path, delimiter, key_column)
            facts = {"rows": rows, "keys": keys, "delimiter": delimiter}
            facts.update(loaded or {})
            slot.set_loaded(path, **facts)
            self.log.info(f"'{file_type}' file is valid.")
            return

        present = core.read_csv_headers(path, delimiter)
        if not present:
            # No header row at all: missing, a directory, not a CSV.
            self._fail(
                file_type,
                path,
                f"The {FILE_NOUN[file_type]} couldn't be read",
                "Check that it still exists and is a CSV export, then replace it.",
            )
        else:
            slot.set_invalid(
                path,
                missing_cols,
                present,
                columns,
                rows=core.count_csv_rows(path, delimiter),
                delimiter=delimiter,
            )
        self.log.warning(
            f"'{file_type}' file is invalid. Missing columns: {', '.join(missing_cols)}"
        )

    def check_files_ready(self):
        """Whether both slots hold a usable file.

        Run analysis is gated by setup_state (gui/setup_state.py), which also
        knows that inventory memory can stand in for a stock file; this is
        only the plain question.
        """
        return self.mw.orders_slot.is_valid and self.mw.stock_slot.is_valid

    def clear_file(self, file_type: str) -> None:
        """Empty one slot: forget the path, reset the record, re-gate the run."""
        setattr(self.mw, f"{file_type}_file_path", None)
        getattr(self.mw, f"{file_type}_slot").clear()
        self.mw.update_ui_state()
        self.log.info(f"Cleared the {file_type} slot")

    def accept_dropped_path(self, file_type: str, path: str) -> None:
        """A file or a folder was dropped on a file card: the same route a pick takes."""
        self.load_file(file_type, path)

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
        a picked one. Every way this can fail ends in the slot's card.
        """
        if not self.mw.session_path:
            self.log.warning(f"load_folder({file_type!r}) called with no session open")
            return
        self.log.info(f"{file_type} folder selected: {folder_path}")

        csv_files = self.scan_folder_for_csv(folder_path, _FOLDER_SCAN_RECURSIVE)
        if not csv_files:
            self._fail(
                file_type,
                folder_path,
                "No CSV files in this folder",
                "Choose a folder that holds the exported CSV files.",
            )
            return

        try:
            valid_files, invalid_files, total_rows, parts = self.validate_multiple_files(
                csv_files, file_type
            )
        except Exception:
            self.log.exception("Error validating files")
            self._fail(
                file_type, folder_path, "The files weren't merged", "Details are in Logs."
            )
            return

        if not valid_files:
            names = ", ".join(os.path.basename(f) for f, _m in invalid_files[:5])
            self._fail(
                file_type,
                folder_path,
                f"None of the {len(csv_files)} files can be used",
                f"{names}. Each is missing a mapped column.",
                MAPPING_PAGE[file_type],
            )
            return

        if not self.show_file_preview(
            file_type, valid_files, invalid_files, total_rows
        ):
            return  # User cancelled

        try:
            merged_path, _rows, skipped = self.merge_and_save_files(
                valid_files, file_type, folder_path
            )
        except Exception:
            self.log.exception("Failed to merge files")
            self._fail(
                file_type, folder_path, "The files weren't merged", "Details are in Logs."
            )
            return

        if file_type == "orders":
            self.mw.orders_file_path = merged_path
            self.mw.orders_source_files = valid_files
            self._remember_orders_dataframe(merged_path)
        else:
            self.mw.stock_file_path = merged_path
            self.mw.stock_source_files = valid_files

        notes = []
        if skipped:
            noun = "order" if file_type == "orders" else "SKU"
            notes.append(
                f"{skipped} overlapping {noun}{'' if skipped == 1 else 's'} skipped"
            )
        if invalid_files:
            n = len(invalid_files)
            notes.append(f"{n} file{'' if n == 1 else 's'} skipped")
        delimiters = {p["delimiter"] for p in parts}
        count = len(valid_files)

        self.validate_file(
            file_type,
            loaded={
                "name": f"{Path(folder_path).name}\\  ·  "
                f"{count} CSV{'' if count == 1 else 's'} merged",
                "parts": [{"name": p["name"], "rows": p["rows"]} for p in parts],
                "note": " · ".join(notes),
                "delimiter": delimiters.pop() if len(delimiters) == 1 else "mixed",
            },
        )
        self.log.info(f"Successfully merged {count} files into {merged_path}")

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
    ) -> tuple[list[str], list[tuple[str, list[str]]], int, list[dict]]:
        """
        Validate multiple CSV files.

        Args:
            file_paths: List of file paths to validate
            file_type: "orders" or "stock"

        Returns:
            Tuple: (valid_files, invalid_files, total_rows, parts)
                valid_files: List of valid file paths
                invalid_files: List of (filepath, missing_columns)
                total_rows: Total rows across all valid files
                parts: per valid file, its name, rows and delimiter
        """
        valid_files = []
        invalid_files = []
        total_rows = 0
        parts = []

        mappings = _columns(self.mw.active_profile_config, file_type)
        required_csv_cols = [
            csv_col for csv_col, name in mappings.items() if name in _REQUIRED[file_type]
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
                    parts.append(
                        {
                            "name": os.path.basename(filepath),
                            "rows": len(df),
                            "delimiter": file_delimiter,
                        }
                    )

                    self.log.info(f"  {os.path.basename(filepath)}: {len(df)} rows")
                else:
                    invalid_files.append((filepath, missing_cols))
                    self.log.warning(
                        f"  {os.path.basename(filepath)}: missing {missing_cols}"
                    )

            except Exception as e:
                invalid_files.append((filepath, [f"Error: {e!s}"]))
                self.log.exception(f"  {os.path.basename(filepath)}")

        return valid_files, invalid_files, total_rows, parts

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
