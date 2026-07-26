"""Table Configuration Manager

Manages table view configuration including column visibility, order, and widths.
Configuration is stored per-client in client_config.json under ui_settings.table_view.

Author: Claude Code
Date: 2026-02-03
"""

import logging
from dataclasses import asdict, dataclass, field

import pandas as pd
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTableView

logger = logging.getLogger(__name__)


@dataclass
class TableConfig:
    """Configuration for table view appearance and behavior.

    Attributes:
        version: Config format version (for future migrations)
        visible_columns: Mapping of column names to visibility state
        column_order: Ordered list of column names (logical order)
        column_widths: Mapping of column names to width in pixels
        auto_hide_empty: Whether to automatically hide empty columns
        locked_columns: Columns that cannot be hidden or reordered
    """
    version: int = 1
    visible_columns: dict[str, bool] = field(default_factory=dict)
    column_order: list[str] = field(default_factory=list)
    column_widths: dict[str, int] = field(default_factory=dict)
    auto_hide_empty: bool = True
    locked_columns: list[str] = field(default_factory=lambda: ["Order_Number"])

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TableConfig":
        """Create config from dictionary (JSON deserialization)."""
        return cls(
            version=data.get("version", 1),
            visible_columns=data.get("visible_columns", {}),
            column_order=data.get("column_order", []),
            column_widths=data.get("column_widths", {}),
            auto_hide_empty=data.get("auto_hide_empty", True),
            locked_columns=data.get("locked_columns", ["Order_Number"])
        )


class TableConfigManager:
    """Manages table view configuration for the results table.

    Responsibilities:
    - Load/save table configuration from client_config.json
    - Apply configuration to QTableView (visibility, order, widths)
    - Detect empty columns for auto-hide
    - Manage multiple named views per client
    - Debounced saving on column resize/move

    Attributes:
        mw: MainWindow instance
        pm: ProfileManager instance
        _current_config: Currently active TableConfig
        _current_client_id: ID of currently selected client
        _save_timer: QTimer for debounced config saving
        _pending_save: Flag indicating save is pending
    """

    DEBOUNCE_DELAY_MS = 500  # Delay before saving after resize/move

    def __init__(self, main_window, profile_manager):
        """Initialize TableConfigManager.

        Args:
            main_window: MainWindow instance
            profile_manager: ProfileManager instance for config persistence
        """
        self.mw = main_window
        self.pm = profile_manager
        self._current_config: TableConfig | None = None
        self._current_client_id: str | None = None
        self._current_view_name: str = "Default"

        # Store references for signal handlers
        self._current_table_view: QTableView | None = None
        self._current_df: pd.DataFrame | None = None

        # Flag to suppress signal handlers during bulk config application
        self._applying_config = False

        # Setup debounced save timer
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._perform_save)
        self._pending_save = False

    def load_config(self, client_id: str, view_name: str = "Default") -> TableConfig:
        """Load table configuration for a client.

        Args:
            client_id: Client ID to load config for
            view_name: Name of the view to load (default: "Default")

        Returns:
            TableConfig instance

        Raises:
            Exception: If config loading fails (logs warning, returns default)
        """
        self._current_client_id = client_id
        self._current_view_name = view_name

        try:
            # Load full client config
            client_config = self.pm.load_client_config(client_id)

            # Extract table_view section
            ui_settings = client_config.get("ui_settings", {})
            table_view_settings = ui_settings.get("table_view", {})

            # Get active view name if not specified
            if view_name == "Default" and "active_view" in table_view_settings:
                view_name = table_view_settings["active_view"]
                self._current_view_name = view_name

            # Get views dictionary
            views = table_view_settings.get("views", {})

            # Load specific view or create default
            if view_name in views:
                view_data = views[view_name]
                self._current_config = TableConfig.from_dict(view_data)
                logger.debug(f"Loaded table view '{view_name}' for CLIENT_{client_id}")
            else:
                # View doesn't exist, create default
                logger.info(f"View '{view_name}' not found for CLIENT_{client_id}, creating default")
                self._current_config = TableConfig()

            # Clean up any corrupted zero-width entries from prior bug
            if self._current_config.column_widths:
                zero_width_cols = [k for k, v in self._current_config.column_widths.items() if v <= 0]
                for col in zero_width_cols:
                    del self._current_config.column_widths[col]
                if zero_width_cols:
                    logger.debug(f"Cleaned up {len(zero_width_cols)} zero-width entries: {zero_width_cols}")

            return self._current_config

        except Exception as e:
            logger.warning(f"Failed to load table config for CLIENT_{client_id}: {e}")
            logger.warning("Using default table configuration")
            self._current_config = TableConfig()
            return self._current_config

    def save_config(self, client_id: str, config: TableConfig, view_name: str = "Default"):
        """Save table configuration for a client.

        Args:
            client_id: Client ID to save config for
            config: TableConfig to save
            view_name: Name of the view to save (default: "Default")

        Raises:
            Exception: If config saving fails (logs error)
        """
        try:
            # Load full client config
            client_config = self.pm.load_client_config(client_id)

            # Ensure ui_settings.table_view structure exists
            if "ui_settings" not in client_config:
                client_config["ui_settings"] = {}
            if "table_view" not in client_config["ui_settings"]:
                client_config["ui_settings"]["table_view"] = {
                    "version": 1,
                    "active_view": view_name,
                    "views": {}
                }

            table_view_settings = client_config["ui_settings"]["table_view"]

            # Ensure views dict exists
            if "views" not in table_view_settings:
                table_view_settings["views"] = {}

            # Save view data
            table_view_settings["views"][view_name] = config.to_dict()

            # Update active view
            table_view_settings["active_view"] = view_name

            # Persist to file
            self.pm.save_client_config(client_id, client_config)

            # Update cached config if this is the current client
            if client_id == self._current_client_id:
                self._current_config = config
                self._current_view_name = view_name

            logger.debug(f"Saved table view '{view_name}' for CLIENT_{client_id}")

        except Exception as e:
            logger.error(f"Failed to save table config for CLIENT_{client_id}: {e}", exc_info=True)
            raise

    def get_default_config(self, columns: list[str]) -> TableConfig:
        """Create default configuration for given columns.

        Args:
            columns: List of column names from DataFrame

        Returns:
            TableConfig with all columns visible in default order
        """
        config = TableConfig()

        # All columns visible by default
        config.visible_columns = {col: True for col in columns}

        # Default order = DataFrame order
        config.column_order = columns.copy()

        # No widths specified = auto-size
        config.column_widths = {}

        # Auto-hide empty columns enabled
        config.auto_hide_empty = True

        # Order_Number is locked
        config.locked_columns = ["Order_Number"]

        return config

    def apply_config_to_view(self, table_view: QTableView, df: pd.DataFrame):
        """Apply configuration to QTableView.

        This method:
        1. Applies column order (moveSection before visibility to avoid conflicts)
        2. Detects empty columns (if auto-hide enabled)
        3. Applies column visibility
        4. Applies column widths

        Signal handlers (on_column_resized, on_column_moved) are suppressed
        during this method to prevent feedback loops that corrupt the config.

        Args:
            table_view: QTableView to configure
            df: DataFrame being displayed
        """
        if self._current_config is None:
            logger.warning("No config loaded, skipping apply_config_to_view")
            return

        # Suppress signal handlers during bulk config application
        self._applying_config = True
        try:
            self._apply_config_to_view_impl(table_view, df)
        finally:
            self._applying_config = False

    def _apply_config_to_view_impl(self, table_view: QTableView, df: pd.DataFrame):
        """Internal implementation of apply_config_to_view."""
        # Store references for signal handlers
        self._current_table_view = table_view
        self._current_df = df

        # Get column names from DataFrame
        df_columns = df.columns.tolist()

        # If config is empty (first load), create default config
        if not self._current_config.visible_columns:
            logger.debug("Config is empty, initializing with defaults")
            self._current_config = self.get_default_config(df_columns)
            # Save default config
            if self._current_client_id:
                self.save_config(
                    self._current_client_id,
                    self._current_config,
                    self._current_view_name
                )
        else:
            # Config exists, but check for new columns from DataFrame
            config_columns = set(self._current_config.visible_columns.keys())
            new_columns = [col for col in df_columns if col not in config_columns]

            if new_columns:
                logger.info(f"Found {len(new_columns)} new columns in DataFrame, adding to config: {new_columns}")

                # Add new columns as visible by default
                for col in new_columns:
                    self._current_config.visible_columns[col] = True

                # Add new columns to end of column_order
                self._current_config.column_order.extend(new_columns)

                # Save updated config
                if self._current_client_id:
                    self.save_config(
                        self._current_client_id,
                        self._current_config,
                        self._current_view_name
                    )
                    logger.debug(f"Saved updated config with {len(new_columns)} new columns")

        # Apply column order FIRST (before visibility to avoid moveSection
        # interacting with already-hidden sections)
        self.apply_column_order(table_view, df)

        # Detect empty columns for auto-hide
        empty_columns = []
        if self._current_config.auto_hide_empty:
            empty_columns = self.detect_empty_columns(df)
            logger.debug(f"Detected {len(empty_columns)} empty columns: {empty_columns}")

        # Apply visibility to header
        header = table_view.horizontalHeader()
        model = table_view.model()

        if model is None:
            logger.warning("Table model is None, cannot apply visibility")
            return

        # Get source model (unwrap proxy if present)
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes
        checkbox_offset = 1 if has_checkbox else 0

        # Apply visibility to each column
        for col_name in df_columns:
            # Find column index in model
            try:
                col_index = df_columns.index(col_name)
            except ValueError:
                logger.warning(f"Column '{col_name}' not found in DataFrame")
                continue

            col_index += checkbox_offset

            # Determine visibility
            is_visible = self._current_config.visible_columns.get(col_name, True)

            # Auto-hide overrides visibility for empty columns
            if col_name in empty_columns and col_name not in self._current_config.locked_columns:
                is_visible = False

            # Locked columns are always visible
            if col_name in self._current_config.locked_columns:
                is_visible = True

            # Apply visibility
            header.setSectionHidden(col_index, not is_visible)

        # Force header to recalculate layout after visibility changes
        header.updateGeometries()

        # Apply column widths (only non-zero values)
        self.apply_column_widths(table_view, df)

        logger.debug(f"Applied table config to view for {len(df_columns)} columns")

    def apply_column_order(self, table_view: QTableView, df: pd.DataFrame):
        """Apply column order configuration to table.

        Uses QHeaderView.moveSection() to reorder columns visually.
        Order_Number is locked at position 0 and cannot be moved.

        Args:
            table_view: QTableView to configure
            df: DataFrame being displayed
        """
        if self._current_config is None or not self._current_config.column_order:
            return

        header = table_view.horizontalHeader()
        model = table_view.model()

        if model is None:
            return

        # Get source model
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Get DataFrame columns
        df_columns = df.columns.tolist()

        # Check if checkbox column exists
        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes
        checkbox_offset = 1 if has_checkbox else 0

        # Build mapping from column name to logical index
        col_to_logical = {}
        for i, col_name in enumerate(df_columns):
            logical_idx = i + checkbox_offset
            col_to_logical[col_name] = logical_idx

        # Apply order from config
        # Start from position after checkbox (if exists)
        target_visual_pos = checkbox_offset

        for col_name in self._current_config.column_order:
            if col_name not in col_to_logical:
                continue

            logical_idx = col_to_logical[col_name]

            # Get current visual position
            current_visual_pos = header.visualIndex(logical_idx)

            # Move to target position if different
            if current_visual_pos != target_visual_pos:
                header.moveSection(current_visual_pos, target_visual_pos)
                logger.debug(f"Moved column '{col_name}' from visual pos {current_visual_pos} to {target_visual_pos}")

            target_visual_pos += 1

        logger.debug("Applied column order")

    def has_saved_column_widths(self) -> bool:
        """Return True if there are saved column widths in the current config."""
        return (
            self._current_config is not None
            and bool(self._current_config.column_widths)
        )

    def apply_column_widths(self, table_view: QTableView, df: pd.DataFrame):
        """Apply column width configuration to table.

        Uses QHeaderView.resizeSection() to set column widths.

        Args:
            table_view: QTableView to configure
            df: DataFrame being displayed
        """
        if self._current_config is None or not self._current_config.column_widths:
            return

        header = table_view.horizontalHeader()
        model = table_view.model()

        if model is None:
            return

        # Get source model
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Get DataFrame columns
        df_columns = df.columns.tolist()

        # Check if checkbox column exists
        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes
        checkbox_offset = 1 if has_checkbox else 0

        # Apply widths from config (skip zero-width entries that would hide columns)
        for col_name, width in self._current_config.column_widths.items():
            if col_name not in df_columns:
                continue
            if width <= 0:
                continue

            # Get logical index
            col_index = df_columns.index(col_name) + checkbox_offset

            # Set width
            header.resizeSection(col_index, width)
            logger.debug(f"Set column '{col_name}' width to {width}px")

        logger.debug("Applied column widths")

    def auto_fit_column_widths(self, table_view: QTableView, df: pd.DataFrame):
        """Auto-resize all visible columns to fit their content.

        Args:
            table_view: QTableView to resize columns for
            df: DataFrame being displayed
        """
        if self._current_config is None:
            return

        header = table_view.horizontalHeader()
        model = table_view.model()
        if model is None:
            return

        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes
        checkbox_offset = 1 if has_checkbox else 0

        df_columns = df.columns.tolist()

        for i, col_name in enumerate(df_columns):
            col_index = i + checkbox_offset
            if not header.isSectionHidden(col_index):
                table_view.resizeColumnToContents(col_index)
                # Update config with new width
                new_width = header.sectionSize(col_index)
                self._current_config.column_widths[col_name] = new_width

        # Save updated widths (debounced)
        if self._current_client_id:
            self._pending_save = True
            self._save_timer.start(self.DEBOUNCE_DELAY_MS)

        logger.info("Auto-fit column widths applied")

    def get_column_name_from_logical_index(self, logical_index: int, df: pd.DataFrame, table_view: QTableView) -> str | None:
        """Get column name from logical index.

        Args:
            logical_index: Logical index in the model
            df: DataFrame being displayed
            table_view: QTableView

        Returns:
            Column name or None if index is invalid
        """
        model = table_view.model()
        if model is None:
            return None

        # Get source model
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Check if checkbox column exists
        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes

        # Adjust for checkbox column
        if has_checkbox:
            if logical_index == 0:
                return None  # Checkbox column
            logical_index -= 1

        # Get DataFrame columns
        df_columns = df.columns.tolist()

        if logical_index < 0 or logical_index >= len(df_columns):
            return None

        return df_columns[logical_index]

    def detect_empty_columns(self, df: pd.DataFrame) -> list[str]:
        """Detect columns that are completely empty.

        A column is considered empty if:
        - All values are NaN, OR
        - All values are empty strings ("")

        Args:
            df: DataFrame to analyze

        Returns:
            List of column names that are empty
        """
        empty_cols = []

        for col in df.columns:
            series = df[col]

            # Check if all NaN
            if series.isna().all():
                empty_cols.append(col)
                continue

            # Check if all empty strings
            # Convert to string first to handle mixed types
            str_series = series.astype(str)
            if (str_series == "").all() or (str_series == "nan").all():
                empty_cols.append(col)

        return empty_cols

    def on_column_resized(self, logical_index: int, old_width: int, new_width: int):
        """Handle column resize event (debounced save).

        Called when user resizes a column. Saves config after debounce delay.
        Suppressed during bulk config application and for zero-width events.

        Args:
            logical_index: Logical index of resized column
            old_width: Previous width in pixels
            new_width: New width in pixels
        """
        # Skip during bulk config application (prevents feedback loop)
        if self._applying_config:
            return

        # Skip zero-width events (caused by hiding columns)
        if new_width <= 0:
            return

        if self._current_config is None or self._current_client_id is None:
            return

        if self._current_table_view is None or self._current_df is None:
            return

        # Get column name from logical index
        column_name = self.get_column_name_from_logical_index(
            logical_index,
            self._current_df,
            self._current_table_view
        )

        if column_name is None:
            return  # Checkbox column or invalid index

        # Update width in config
        self._current_config.column_widths[column_name] = new_width
        logger.debug(f"Column '{column_name}' resized to {new_width}px")

        # Schedule debounced save
        self._pending_save = True
        self._save_timer.start(self.DEBOUNCE_DELAY_MS)

    def on_column_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        """Handle column move event (debounced save).

        Called when user reorders columns. Saves config after debounce delay.
        Prevents moving Order_Number from position 0.
        Suppressed during bulk config application.

        Args:
            logical_index: Logical index of moved column
            old_visual_index: Previous visual position
            new_visual_index: New visual position
        """
        # Skip during bulk config application (prevents feedback loop)
        if self._applying_config:
            return

        if self._current_config is None or self._current_client_id is None:
            return

        if self._current_table_view is None or self._current_df is None:
            return

        # Get column name from logical index
        column_name = self.get_column_name_from_logical_index(
            logical_index,
            self._current_df,
            self._current_table_view
        )

        if column_name is None:
            return  # Checkbox column or invalid index

        # Check if trying to move a locked column or move a column to position 0
        header = self._current_table_view.horizontalHeader()
        model = self._current_table_view.model()

        # Get source model
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Check if checkbox column exists
        has_checkbox = hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes
        checkbox_offset = 1 if has_checkbox else 0

        # Locked columns (Order_Number) must stay at position after checkbox
        if column_name in self._current_config.locked_columns:
            if new_visual_index != checkbox_offset:
                # Revert move
                header.moveSection(new_visual_index, old_visual_index)
                logger.warning(f"Cannot move locked column '{column_name}' from position {checkbox_offset}")
                return

        # Don't allow moving to the locked position (after checkbox)
        if new_visual_index == checkbox_offset and column_name not in self._current_config.locked_columns:
            # Revert move
            header.moveSection(new_visual_index, old_visual_index)
            logger.warning(f"Position {checkbox_offset} is reserved for locked column")
            return

        # Update column order in config
        # Get current visual order
        df_columns = self._current_df.columns.tolist()
        new_order = []

        for visual_pos in range(checkbox_offset, header.count()):
            logical_idx = header.logicalIndex(visual_pos)
            col_name = self.get_column_name_from_logical_index(
                logical_idx,
                self._current_df,
                self._current_table_view
            )
            if col_name:
                new_order.append(col_name)

        self._current_config.column_order = new_order
        logger.debug(f"Column '{column_name}' moved, new order: {new_order}")

        # Schedule debounced save
        self._pending_save = True
        self._save_timer.start(self.DEBOUNCE_DELAY_MS)

    def _perform_save(self):
        """Perform the actual config save (called by debounce timer)."""
        if not self._pending_save:
            return

        if self._current_config is None or self._current_client_id is None:
            logger.warning("Cannot perform save: no config or client ID")
            return

        try:
            self.save_config(
                self._current_client_id,
                self._current_config,
                self._current_view_name
            )
            self._pending_save = False
            logger.debug("Debounced save completed")
        except Exception as e:
            logger.error(f"Failed to perform debounced save: {e}", exc_info=True)

    # Column visibility management methods (Phase 2)

    def toggle_column_visibility(self, table_view: QTableView, column_name: str, df: pd.DataFrame):
        """Toggle visibility of a specific column.

        Args:
            table_view: QTableView to update
            column_name: Name of column to toggle
            df: DataFrame being displayed

        Returns:
            bool: New visibility state (True if now visible, False if now hidden)
        """
        if self._current_config is None:
            logger.warning("No config loaded, cannot toggle visibility")
            return True

        # Check if column is locked
        if column_name in self._current_config.locked_columns:
            logger.warning(f"Cannot hide locked column: {column_name}")
            return True

        # Get current visibility
        current_visibility = self._current_config.visible_columns.get(column_name, True)

        # Toggle visibility
        new_visibility = not current_visibility
        self._current_config.visible_columns[column_name] = new_visibility

        # Apply to view
        self._apply_single_column_visibility(table_view, column_name, new_visibility, df)

        # Verify the change actually took effect and force-correct if needed
        self._verify_section_visibility(table_view, column_name, new_visibility, df)

        # Save config
        if self._current_client_id:
            self.save_config(
                self._current_client_id,
                self._current_config,
                self._current_view_name
            )

        logger.info(f"Toggled column '{column_name}' visibility: {new_visibility}")
        return new_visibility

    def set_column_visibility(self, table_view: QTableView, column_name: str, visible: bool, df: pd.DataFrame):
        """Set visibility of a specific column.

        Args:
            table_view: QTableView to update
            column_name: Name of column to show/hide
            visible: True to show, False to hide
            df: DataFrame being displayed
        """
        if self._current_config is None:
            logger.warning("No config loaded, cannot set visibility")
            return

        # Check if column is locked and trying to hide
        if not visible and column_name in self._current_config.locked_columns:
            logger.warning(f"Cannot hide locked column: {column_name}")
            return

        # Update visibility
        self._current_config.visible_columns[column_name] = visible

        # Apply to view
        self._apply_single_column_visibility(table_view, column_name, visible, df)

        # Verify the change actually took effect and force-correct if needed
        self._verify_section_visibility(table_view, column_name, visible, df)

        # Save config
        if self._current_client_id:
            self.save_config(
                self._current_client_id,
                self._current_config,
                self._current_view_name
            )

        logger.info(f"Set column '{column_name}' visibility: {visible}")

    def _apply_single_column_visibility(self, table_view: QTableView, column_name: str, visible: bool, df: pd.DataFrame):
        """Apply visibility to a single column.

        Args:
            table_view: QTableView to update
            column_name: Name of column
            visible: True to show, False to hide
            df: DataFrame being displayed
        """
        header = table_view.horizontalHeader()
        model = table_view.model()

        if model is None:
            logger.warning("Table model is None, cannot apply visibility")
            return

        # Get source model (unwrap proxy if present)
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Get DataFrame columns
        df_columns = df.columns.tolist()

        # Find column index
        try:
            col_index = df_columns.index(column_name)
        except ValueError:
            logger.warning(f"Column '{column_name}' not found in DataFrame")
            return

        # Adjust index if model has checkbox column
        if hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes:
            col_index += 1

        # Apply visibility
        header.setSectionHidden(col_index, not visible)

        # When showing a column, ensure it has a non-zero width
        # (width may have been set to 0 by prior hide/resize feedback)
        if visible:
            current_width = header.sectionSize(col_index)
            if current_width <= 0:
                table_view.resizeColumnToContents(col_index)
                logger.debug(f"Restored width for column '{column_name}' (was 0)")

        # Force header layout recalculation and repaint
        header.updateGeometries()
        header.viewport().update()
        table_view.viewport().update()

        logger.debug(f"Applied visibility to column '{column_name}' (index {col_index}): {visible}")

    def _verify_section_visibility(self, table_view: QTableView, column_name: str, expected_visible: bool, df: pd.DataFrame):
        """Verify header section visibility matches expected state; force-correct if mismatched.

        Args:
            table_view: QTableView to check
            column_name: Column name to verify
            expected_visible: Expected visibility state
            df: DataFrame being displayed
        """
        header = table_view.horizontalHeader()
        model = table_view.model()
        if model is None:
            return

        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        df_columns = df.columns.tolist()
        try:
            col_index = df_columns.index(column_name)
        except ValueError:
            return

        if hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes:
            col_index += 1

        actual_hidden = header.isSectionHidden(col_index)
        if actual_hidden == expected_visible:  # Mismatch: hidden when should be visible (or vice versa)
            logger.warning(
                f"Visibility mismatch for '{column_name}' (index {col_index}): "
                f"expected {'visible' if expected_visible else 'hidden'}, "
                f"got {'hidden' if actual_hidden else 'visible'}. Force-correcting."
            )
            header.setSectionHidden(col_index, not expected_visible)
            header.updateGeometries()
            header.viewport().update()
            table_view.viewport().update()

    def get_column_visibility(self, column_name: str) -> bool:
        """Get current visibility state of a column.

        Args:
            column_name: Name of column

        Returns:
            bool: True if visible, False if hidden
        """
        if self._current_config is None:
            return True

        return self._current_config.visible_columns.get(column_name, True)

    def get_hidden_columns(self, df: pd.DataFrame) -> list[str]:
        """Get list of currently hidden columns.

        Args:
            df: DataFrame being displayed

        Returns:
            List of column names that are hidden
        """
        if self._current_config is None:
            return []

        df_columns = df.columns.tolist()
        hidden = []

        for col in df_columns:
            if not self.get_column_visibility(col):
                hidden.append(col)

        return hidden

    def show_all_columns(self, table_view: QTableView, df: pd.DataFrame):
        """Show all columns (except auto-hidden empty columns).

        Args:
            table_view: QTableView to update
            df: DataFrame being displayed
        """
        if self._current_config is None:
            logger.warning("No config loaded, cannot show all columns")
            return

        # Set all columns to visible and disable auto-hide
        for col in df.columns.tolist():
            self._current_config.visible_columns[col] = True
        self._current_config.auto_hide_empty = False

        # Re-apply config
        self.apply_config_to_view(table_view, df)

        # Save config
        if self._current_client_id:
            self.save_config(
                self._current_client_id,
                self._current_config,
                self._current_view_name
            )

        logger.info("Showed all columns")

    # Methods for managing named views (Phase 4)

    def get_current_config(self) -> TableConfig | None:
        """Get the currently loaded configuration.

        Returns:
            Current TableConfig or None if not loaded
        """
        return self._current_config

    def get_current_view_name(self) -> str:
        """Get the name of the currently active view.

        Returns:
            Current view name (default: "Default")
        """
        return self._current_view_name

    def list_views(self, client_id: str | None = None) -> list[str]:
        """List all saved view names for a client.

        Args:
            client_id: Client ID (uses current client if None)

        Returns:
            List of view names
        """
        if client_id is None:
            client_id = self._current_client_id

        if client_id is None:
            logger.warning("No client selected, cannot list views")
            return []

        return self._list_views_impl(client_id)

    def _list_views_impl(self, client_id: str) -> list[str]:
        """List all saved view names for a client (internal implementation).

        Args:
            client_id: Client ID

        Returns:
            List of view names
        """
        try:
            client_config = self.pm.load_client_config(client_id)
            ui_settings = client_config.get("ui_settings", {})
            table_view_settings = ui_settings.get("table_view", {})
            views = table_view_settings.get("views", {})
            return list(views.keys())
        except Exception as e:
            logger.error(f"Failed to list views for CLIENT_{client_id}: {e}", exc_info=True)
            return []

    def load_view(self, view_name: str, client_id: str | None = None) -> TableConfig | None:
        """Load a specific named view.

        Args:
            view_name: View name to load
            client_id: Client ID (uses current client if None)

        Returns:
            TableConfig if view exists, None otherwise
        """
        if client_id is None:
            client_id = self._current_client_id

        if client_id is None:
            logger.warning("No client selected, cannot load view")
            return None

        return self.load_config(client_id, view_name)

    def _load_view_legacy(self, client_id: str, view_name: str) -> TableConfig | None:
        """Load a specific named view (legacy method for tests).

        Args:
            client_id: Client ID
            view_name: View name to load

        Returns:
            TableConfig if view exists, None otherwise
        """
        return self.load_config(client_id, view_name)

    def save_view(self, view_name: str, config: TableConfig, client_id: str | None = None):
        """Save a named view.

        Args:
            view_name: View name to save
            config: TableConfig to save
            client_id: Client ID (uses current client if None)
        """
        if client_id is None:
            client_id = self._current_client_id

        if client_id is None:
            logger.warning("No client selected, cannot save view")
            raise ValueError("No client selected")

        self.save_config(client_id, config, view_name)
        self._current_view_name = view_name

    def delete_view(self, view_name: str, client_id: str | None = None):
        """Delete a named view.

        Args:
            view_name: View name to delete
            client_id: Client ID (uses current client if None)

        Raises:
            ValueError: If trying to delete "Default" view or no client selected
        """
        if view_name == "Default":
            raise ValueError("Cannot delete Default view")

        if client_id is None:
            client_id = self._current_client_id

        if client_id is None:
            logger.warning("No client selected, cannot delete view")
            raise ValueError("No client selected")

        try:
            client_config = self.pm.load_client_config(client_id)
            ui_settings = client_config.get("ui_settings", {})
            table_view_settings = ui_settings.get("table_view", {})
            views = table_view_settings.get("views", {})

            if view_name in views:
                del views[view_name]
                self.pm.save_client_config(client_id, client_config)
                logger.info(f"Deleted view '{view_name}' for CLIENT_{client_id}")

                # If we deleted the current view, switch to Default
                if self._current_view_name == view_name:
                    self._current_view_name = "Default"
                    self.load_config(client_id, "Default")
            else:
                logger.warning(f"View '{view_name}' not found for CLIENT_{client_id}")

        except Exception as e:
            logger.error(f"Failed to delete view '{view_name}' for CLIENT_{client_id}: {e}", exc_info=True)
            raise
