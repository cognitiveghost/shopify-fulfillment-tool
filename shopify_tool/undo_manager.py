"""
Undo Manager for DataFrame Operations

Manages undo history for DataFrame modifications:
- Records operations after execution (stores affected rows before modification)
- Restores previous DataFrame state
- Persists history to operations_history.json
- Clears "future" operations after new action following undo
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


class UndoManager:
    """Manages undo history for DataFrame operations.

    Only stores affected rows (not full DataFrame) for memory efficiency.
    Supports multi-level undo (up to max_history operations back), not just
    the last operation.
    """

    def __init__(self, main_window):
        """Initialize with reference to MainWindow.

        Args:
            main_window: Reference to MainWindow instance
        """
        self.main_window = main_window
        self.log = logging.getLogger(__name__)

        # History structure
        self.operations = []
        self.current_position = 0
        self.max_history = 20

        # Load existing history if available
        self._load_history()

    def record_operation(
        self,
        operation_type: str,
        description: str,
        params: dict[str, Any],
        affected_rows_before: pd.DataFrame
    ):
        """Record operation AFTER it executes.

        Args:
            operation_type: Type of operation (toggle_status, add_tag, remove_item, remove_order)
            description: Human-readable description
            params: Dict with operation parameters
            affected_rows_before: DataFrame rows before modification
        """
        try:
            # Clear any "future" operations (redo history) when new operation is recorded
            if self.current_position < len(self.operations):
                self.operations = self.operations[:self.current_position]
                self.log.info(f"Cleared {len(self.operations) - self.current_position} future operations")

            # Convert DataFrame to serializable format
            affected_rows_serialized = affected_rows_before.to_dict('records') if not affected_rows_before.empty else []

            # Get current stats for reference
            stats_before = None
            if hasattr(self.main_window, 'analysis_stats') and self.main_window.analysis_stats:
                stats_before = self.main_window.analysis_stats.copy()

            # Capture context (client_id and session_path)
            current_client_id = getattr(self.main_window, 'current_client_id', None)
            current_session_path = str(self.main_window.session_path) if self.main_window.session_path else None

            # Create operation record
            operation_id = len(self.operations) + 1
            operation = {
                "id": operation_id,
                "timestamp": datetime.now().astimezone().isoformat(),
                "type": operation_type,
                "description": description,
                "params": params,
                "affected_rows_before": affected_rows_serialized,
                "stats_before": stats_before,
                # Context tracking
                "client_id": current_client_id,
                "session_path": current_session_path
            }

            # Add to history
            self.operations.append(operation)
            self.current_position = len(self.operations)

            # Limit history size
            if len(self.operations) > self.max_history:
                removed = self.operations.pop(0)
                self.current_position -= 1
                self.log.info(f"Removed oldest operation (limit {self.max_history}): {removed['description']}")

            # Save to file
            self._save_history()

            self.log.info(f"Recorded operation #{operation_id}: {description}")

        except Exception:
            self.log.exception("Failed to record operation")

    def can_undo(self) -> bool:
        """Check if undo is possible.

        Returns:
            True if there are operations to undo
        """
        return self.current_position > 0 and len(self.operations) > 0

    def get_undo_description(self) -> str | None:
        """Get description of operation that would be undone.

        Returns:
            Description string or None if no undo available
        """
        if self.can_undo():
            return self.operations[self.current_position - 1].get("description", "Unknown operation")
        return None

    def undo(self) -> tuple[bool, str]:
        """Undo last operation.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.can_undo():
            return False, "Nothing to undo"

        try:
            # Get operation to undo
            operation = self.operations[self.current_position - 1]

            # Validate context before undoing
            operation_client_id = operation.get("client_id")
            operation_session_path = operation.get("session_path")
            current_client_id = getattr(self.main_window, 'current_client_id', None)
            current_session_path = str(self.main_window.session_path) if self.main_window.session_path else None

            # Check if operation belongs to current context
            if operation_client_id and operation_client_id != current_client_id:
                self.log.warning(
                    f"Undo blocked: operation from CLIENT_{operation_client_id}, "
                    f"current client is CLIENT_{current_client_id}"
                )
                return False, "Cannot undo: operation from different client"

            if operation_session_path and operation_session_path != current_session_path:
                self.log.warning(
                    f"Undo blocked: operation from session {operation_session_path}, "
                    f"current session is {current_session_path}"
                )
                return False, "Cannot undo: operation from different session"

            operation_type = operation["type"]
            params = operation["params"]
            affected_rows_serialized = operation["affected_rows_before"]

            self.log.info(f"Undoing operation: {operation['description']}")

            # Convert serialized rows back to DataFrame
            affected_rows_before = pd.DataFrame(affected_rows_serialized)

            # Perform undo based on operation type
            if operation_type == "toggle_status":
                success = self._undo_toggle_status(params, affected_rows_before)
            elif operation_type == "add_tag":
                success = self._undo_add_tag(params, affected_rows_before)
            elif operation_type == "add_internal_tag":
                success = self._undo_add_internal_tag(params, affected_rows_before)
            elif operation_type == "remove_internal_tag":
                success = self._undo_add_internal_tag(params, affected_rows_before)  # Same logic
            elif operation_type == "remove_item":
                success = self._undo_remove_item(params, affected_rows_before)
            elif operation_type == "remove_order":
                success = self._undo_remove_order(params, affected_rows_before)
            # Bulk operations
            elif operation_type == "bulk_change_status":
                success = self._undo_bulk_change_status(params, affected_rows_before)
            elif operation_type == "bulk_add_tag":
                success = self._undo_bulk_add_tag(params, affected_rows_before)
            elif operation_type == "bulk_remove_tag":
                success = self._undo_bulk_remove_tag(params, affected_rows_before)
            elif operation_type == "bulk_remove_sku":
                success = self._undo_bulk_remove_sku(params, affected_rows_before)
            elif operation_type == "bulk_remove_orders_with_sku":
                success = self._undo_bulk_remove_orders_with_sku(params, affected_rows_before)
            elif operation_type == "bulk_delete_orders":
                success = self._undo_bulk_delete_orders(params, affected_rows_before)
            else:
                return False, f"Unknown operation type: {operation_type}"

            if success:
                # Move position back
                self.current_position -= 1

                # Restore stats if available
                if operation.get("stats_before"):
                    self.main_window.analysis_stats = operation["stats_before"]

                # Save updated history
                self._save_history()

                return True, f"Undone: {operation['description']}"
            else:
                return False, f"Failed to undo: {operation['description']}"

        except Exception as e:
            self.log.exception("Undo failed")
            return False, f"Undo failed: {e!s}"

    def _undo_toggle_status(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo toggle status operation.

        Args:
            params: Operation parameters
            affected_rows_before: Rows before toggle

        Returns:
            True if successful
        """
        try:
            order_number = params["order_number"]

            # Get current DataFrame
            df = self.main_window.analysis_results_df

            # Find rows for this order
            mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()

            if not mask.any():
                self.log.warning(f"Order {order_number} not found in DataFrame")
                return False

            # Restore the affected columns from before state
            # Key columns that change: Order_Fulfillment_Status
            df.loc[mask, "Order_Fulfillment_Status"] = affected_rows_before["Order_Fulfillment_Status"].values[0]

            self.main_window.analysis_results_df = df
            self.log.info(f"Restored status for order {order_number}")

            return True

        except Exception:
            self.log.exception("Failed to undo toggle status")
            return False

    def _undo_add_tag(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo add tag operation.

        Args:
            params: Operation parameters
            affected_rows_before: Rows before tag addition

        Returns:
            True if successful
        """
        try:
            order_number = params["order_number"]

            # Get current DataFrame
            df = self.main_window.analysis_results_df

            # Find rows for this order
            mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()

            if not mask.any():
                self.log.warning(f"Order {order_number} not found in DataFrame")
                return False

            # Restore Status_Note from before state
            if "Status_Note" in affected_rows_before.columns:
                for idx, original_idx in enumerate(df[mask].index):
                    if idx < len(affected_rows_before):
                        df.loc[original_idx, "Status_Note"] = affected_rows_before.iloc[idx]["Status_Note"]

            self.main_window.analysis_results_df = df
            self.log.info(f"Restored tags for order {order_number}")

            return True

        except Exception:
            self.log.exception("Failed to undo add tag")
            return False

    def _undo_add_internal_tag(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo add internal tag operation.

        Args:
            params: Operation parameters
            affected_rows_before: Rows before tag addition

        Returns:
            True if successful
        """
        try:
            order_number = params["order_number"]

            # Get current DataFrame
            df = self.main_window.analysis_results_df

            # Find rows for this order
            mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()

            if not mask.any():
                self.log.warning(f"Order {order_number} not found in DataFrame")
                return False

            # Restore Internal_Tags from before state
            if "Internal_Tags" in affected_rows_before.columns:
                for idx, original_idx in enumerate(df[mask].index):
                    if idx < len(affected_rows_before):
                        df.loc[original_idx, "Internal_Tags"] = affected_rows_before.iloc[idx]["Internal_Tags"]

            self.main_window.analysis_results_df = df
            self.log.info(f"Restored internal tags for order {order_number}")

            return True

        except Exception:
            self.log.exception("Failed to undo add internal tag")
            return False

    def _undo_remove_item(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo remove item operation.

        Args:
            params: Operation parameters
            affected_rows_before: Row before removal

        Returns:
            True if successful
        """
        try:
            # Restore the removed row by concatenating it back
            self.main_window.analysis_results_df = pd.concat(
                [self.main_window.analysis_results_df, affected_rows_before],
                ignore_index=True
            )

            order_number = params.get("order_number", "unknown")
            sku = params.get("sku", "unknown")
            self.log.info(f"Restored item {sku} to order {order_number}")

            return True

        except Exception:
            self.log.exception("Failed to undo remove item")
            return False

    def _undo_remove_order(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo remove order operation.

        Args:
            params: Operation parameters
            affected_rows_before: All rows of order before removal

        Returns:
            True if successful
        """
        try:
            # Restore all removed rows by concatenating them back
            self.main_window.analysis_results_df = pd.concat(
                [self.main_window.analysis_results_df, affected_rows_before],
                ignore_index=True
            )

            order_number = params.get("order_number", "unknown")
            self.log.info(f"Restored order {order_number} with {len(affected_rows_before)} items")

            return True

        except Exception:
            self.log.exception("Failed to undo remove order")
            return False

    def _get_history_path(self) -> Path | None:
        """Get path to operations_history.json.

        Returns:
            Path object or None if no active session
        """
        if not self.main_window.session_path:
            return None

        session_path = Path(self.main_window.session_path)
        analysis_dir = session_path / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        return analysis_dir / "operations_history.json"

    def _save_history(self):
        """Save history to operations_history.json."""
        try:
            history_path = self._get_history_path()

            if not history_path:
                self.log.debug("No active session, skipping history save")
                return

            history_data = {
                "operations": self.operations,
                "current_position": self.current_position,
                "max_history": self.max_history
            }

            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)

            self.log.debug(f"Saved history to {history_path}")

        except Exception:
            self.log.exception("Failed to save history")

    def _load_history(self):
        """Load history from operations_history.json."""
        try:
            history_path = self._get_history_path()

            if not history_path or not history_path.exists():
                self.log.debug("No history file found")
                return

            with open(history_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)

            self.operations = history_data.get("operations", [])
            self.current_position = history_data.get("current_position", 0)
            self.max_history = history_data.get("max_history", 20)

            self.log.info(f"Loaded {len(self.operations)} operations from history")

        except json.JSONDecodeError as e:
            self.log.warning(f"Corrupted history file, starting fresh: {e}")
            self.operations = []
            self.current_position = 0
        except Exception:
            self.log.exception("Failed to load history")
            self.operations = []
            self.current_position = 0

    def clear_history(self):
        """Clear all undo history."""
        self.operations = []
        self.current_position = 0
        self._save_history()
        self.log.info("Cleared undo history")

    def reset_for_session(self):
        """Reset undo history when switching sessions or clients.

        Called when:
        - Switching clients (load_client_config, on_client_changed)
        - Loading a different session
        - Creating a new session

        This prevents cross-session/cross-client undo operations.
        """
        self.operations = []
        self.current_position = 0
        # Don't save - let new session create fresh history file
        self.log.info("Reset undo history for new session/client")

    def reload_session_history(self):
        """Reload undo history for the current session.

        Called when:
        - Loading an existing session
        - Returning to a previous session

        This restores undo operations from the session's history file.
        """
        self.operations = []
        self.current_position = 0
        self._load_history()
        self.log.info(f"Reloaded undo history: {len(self.operations)} operations")

    # ============================================================================
    # BULK OPERATION UNDO HANDLERS
    # ============================================================================

    def _undo_bulk_change_status(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk status change operation.

        Args:
            params: Operation parameters
            affected_rows_before: Rows before status change

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # affected_rows_before round-trips through JSON (to_dict('records') /
            # pd.DataFrame(...)) between record and undo, which discards its original
            # pandas index and replaces it with a fresh 0..n-1 range. That range does
            # NOT correspond to positions in the live DataFrame, so restoring by index
            # label silently writes into unrelated rows. Match by Order_Number instead
            # (same approach as _undo_toggle_status), since status is order-level.
            df = self.main_window.analysis_results_df
            restored = 0
            for order_number, group in affected_rows_before.groupby("Order_Number"):
                original_status = group["Order_Fulfillment_Status"].iloc[0]
                if pd.isna(original_status):
                    continue
                mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
                if mask.any():
                    df.loc[mask, "Order_Fulfillment_Status"] = original_status
                    restored += 1

            self.main_window.analysis_results_df = df
            self.log.info(f"Undid bulk status change for {restored} orders")
            return restored > 0

        except Exception:
            self.log.exception("Failed to undo bulk status change")
            return False

    def _undo_bulk_add_tag(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk tag addition.

        Args:
            params: Operation parameters
            affected_rows_before: Rows before tag addition (representative rows only)

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # See _undo_bulk_change_status: affected_rows_before's index is not
            # meaningful after the record/undo JSON round-trip. Match by
            # Order_Number and restore the order's first current row (mirrors
            # which row the original bulk_add_tag/bulk_remove_tag wrote to).
            df = self.main_window.analysis_results_df
            restored = 0
            for order_number, group in affected_rows_before.groupby("Order_Number"):
                order_mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
                order_rows = df.index[order_mask]
                if not len(order_rows):
                    continue
                if "Internal_Tags" in group.columns:
                    for idx, original_idx in enumerate(order_rows):
                        if idx < len(group):
                            df.loc[original_idx, "Internal_Tags"] = group["Internal_Tags"].iloc[idx]
                restored += 1

            self.main_window.analysis_results_df = df
            self.log.info(f"Undid bulk add tag for {restored} orders")
            return restored > 0

        except Exception:
            self.log.exception("Failed to undo bulk add tag")
            return False

    def _undo_bulk_remove_tag(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk tag removal with order-level forward-fill.

        Args:
            params: Operation parameters (includes order_numbers for forward-fill)
            affected_rows_before: Rows before tag removal (representative rows only)

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # See _undo_bulk_change_status: match by Order_Number, not the
            # (JSON-round-trip-reset) DataFrame index.
            df = self.main_window.analysis_results_df
            restored = 0
            for order_number, group in affected_rows_before.groupby("Order_Number"):
                order_mask = df["Order_Number"].astype(str).str.strip() == str(order_number).strip()
                order_rows = df.index[order_mask]
                if not len(order_rows):
                    continue
                if "Internal_Tags" in group.columns:
                    for idx, original_idx in enumerate(order_rows):
                        if idx < len(group):
                            df.loc[original_idx, "Internal_Tags"] = group["Internal_Tags"].iloc[idx]
                restored += 1

            self.main_window.analysis_results_df = df
            self.log.info(f"Undid bulk remove tag for {restored} orders")
            return restored > 0

        except Exception:
            self.log.exception("Failed to undo bulk remove tag")
            return False

    def _undo_bulk_remove_sku(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk SKU removal.

        Args:
            params: Operation parameters
            affected_rows_before: Removed rows to restore

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # Restore removed rows
            self.main_window.analysis_results_df = pd.concat(
                [self.main_window.analysis_results_df, affected_rows_before],
                ignore_index=True
            )

            sku = params.get("sku", "unknown")
            removed_count = params.get("removed_count", len(affected_rows_before))
            self.log.info(f"Restored {removed_count} items with SKU {sku}")

            return True

        except Exception:
            self.log.exception("Failed to undo bulk SKU removal")
            return False

    def _undo_bulk_remove_orders_with_sku(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk order removal (orders containing SKU).

        Args:
            params: Operation parameters
            affected_rows_before: Removed rows to restore

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # Restore removed rows
            self.main_window.analysis_results_df = pd.concat(
                [self.main_window.analysis_results_df, affected_rows_before],
                ignore_index=True
            )

            removed_orders = params.get("removed_orders", 0)
            removed_items = params.get("removed_items", len(affected_rows_before))
            self.log.info(f"Restored {removed_orders} orders ({removed_items} items)")

            return True

        except Exception:
            self.log.exception("Failed to undo bulk order removal")
            return False

    def _undo_bulk_delete_orders(self, params: dict, affected_rows_before: pd.DataFrame) -> bool:
        """Undo bulk order deletion.

        Args:
            params: Operation parameters
            affected_rows_before: Deleted rows to restore

        Returns:
            True if successful
        """
        try:
            if affected_rows_before.empty:
                self.log.warning("No affected rows to restore")
                return False

            # Restore deleted rows
            self.main_window.analysis_results_df = pd.concat(
                [self.main_window.analysis_results_df, affected_rows_before],
                ignore_index=True
            )

            deleted_orders = params.get("deleted_orders", 0)
            deleted_items = params.get("deleted_items", len(affected_rows_before))
            self.log.info(f"Restored {deleted_orders} deleted orders ({deleted_items} items)")

            return True

        except Exception:
            self.log.exception("Failed to undo bulk delete")
            return False
