"""
Unified Statistics Manager for Shopify Tool and Packing Tool

This module provides a unified statistics tracking system that works identically
in both the Shopify Fulfillment Tool and Packing Tool. It manages centralized
statistics stored on the file server in Stats/global_stats.json.

Phase 1.4: Unified Statistics System
- Centralized storage on file server
- File locking for concurrent access from multiple PCs
- Separate tracking for analysis (Shopify) and packing operations
- Per-client statistics breakdown
- Thread-safe and process-safe operations

Usage:
    # In Shopify Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_analysis(
        client_id="M",
        session_id="2025-11-05_1",
        orders_count=150,
        metadata={...}
    )

    # In Packing Tool
    stats_manager = StatsManager(base_path)
    stats_manager.record_packing(
        client_id="M",
        session_id="2025-11-05_1",
        worker_id="001",
        orders_count=142,
        items_count=450,
        metadata={...}
    )
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

# Platform-specific file locking
try:
    import msvcrt
    WINDOWS_LOCKING_AVAILABLE = True
except ImportError:
    WINDOWS_LOCKING_AVAILABLE = False

try:
    import fcntl
    UNIX_LOCKING_AVAILABLE = True
except ImportError:
    UNIX_LOCKING_AVAILABLE = False


class StatsManagerError(Exception):
    """Base exception for StatsManager errors."""
    pass


class FileLockError(StatsManagerError):
    """Raised when file locking fails."""
    pass


class StatsManager:
    """
    Unified statistics manager for both Shopify Tool and Packing Tool.

    Manages centralized statistics stored in Stats/global_stats.json on the
    file server. Provides thread-safe and process-safe operations using
    file locking.

    Structure of global_stats.json:
    {
        "total_orders_analyzed": 5420,      # From Shopify Tool
        "total_orders_packed": 4890,        # From Packing Tool
        "total_sessions": 312,
        "by_client": {
            "M": {
                "orders_analyzed": 2100,
                "orders_packed": 1950,
                "sessions": 145
            }
        },
        "analysis_history": [...],          # Shopify Tool records
        "packing_history": [...],           # Packing Tool records
        "last_updated": "2025-11-05T14:30:00"
    }

    Attributes:
        base_path (Path): Base path to 0UFulfilment directory
        stats_file (Path): Path to global_stats.json
        max_retries (int): Maximum number of retry attempts for file operations
        retry_delay (float): Delay in seconds between retries
    """

    def __init__(
        self,
        base_path: str,
        max_retries: int = 5,
        retry_delay: float = 0.1
    ):
        """
        Initialize the StatsManager.

        Args:
            base_path: Path to 0UFulfilment directory (e.g., \\\\server\\...\\0UFulfilment)
            max_retries: Maximum number of retry attempts for locked files
            retry_delay: Delay in seconds between retry attempts
        """
        self.base_path = Path(base_path)
        self.stats_file = self.base_path / "Stats" / "global_stats.json"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Ensure Stats directory exists
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_default_stats(self) -> Dict[str, Any]:
        """
        Get default statistics structure.

        Returns:
            Dictionary with default statistics structure
        """
        return {
            "total_orders_analyzed": 0,
            "total_orders_packed": 0,
            "total_sessions": 0,
            "total_labels_printed": 0,
            "by_client": {},
            "analysis_history": [],
            "packing_history": [],
            "label_print_history": [],
            "last_updated": datetime.now().isoformat(),
            "version": "1.0"
        }

    @contextmanager
    def _lock_file(self, file_handle, timeout: float = 5.0):
        """
        Context manager for file locking with timeout.

        Args:
            file_handle: Open file handle
            timeout: Maximum time to wait for lock in seconds

        Raises:
            FileLockError: If unable to acquire lock within timeout
        """
        start_time = time.time()
        locked = False

        try:
            if WINDOWS_LOCKING_AVAILABLE:
                # Windows file locking
                while time.time() - start_time < timeout:
                    try:
                        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                        locked = True
                        break
                    except OSError:
                        time.sleep(self.retry_delay)

                if not locked:
                    raise FileLockError(f"Could not acquire lock within {timeout} seconds")

            elif UNIX_LOCKING_AVAILABLE:
                # Unix file locking
                while time.time() - start_time < timeout:
                    try:
                        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    except IOError:
                        time.sleep(self.retry_delay)

                if not locked:
                    raise FileLockError(f"Could not acquire lock within {timeout} seconds")

            yield

        finally:
            if locked:
                try:
                    if WINDOWS_LOCKING_AVAILABLE:
                        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    elif UNIX_LOCKING_AVAILABLE:
                        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass  # Ignore unlock errors

    def _load_stats(self) -> Dict[str, Any]:
        """
        Load statistics from file with file locking.

        Returns:
            Dictionary with statistics data

        Raises:
            StatsManagerError: If unable to load statistics after retries
        """
        if not self.stats_file.exists():
            return self._get_default_stats()

        for attempt in range(self.max_retries):
            try:
                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with self._lock_file(f):
                        f.seek(0)
                        content = f.read()
                        if not content.strip():
                            return self._get_default_stats()

                        stats = json.loads(content)

                        # Validate structure
                        if not isinstance(stats, dict):
                            return self._get_default_stats()

                        # Ensure all required keys exist
                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        return stats

            except json.JSONDecodeError as e:
                # Corrupted JSON - return default stats without retrying
                return self._get_default_stats()
            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to load stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

        return self._get_default_stats()

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        """
        Save statistics to file with file locking.

        Args:
            stats: Statistics dictionary to save

        Raises:
            StatsManagerError: If unable to save statistics after retries
        """
        # Update timestamp
        stats["last_updated"] = datetime.now().isoformat()

        for attempt in range(self.max_retries):
            try:
                # Ensure directory exists
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)

                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with self._lock_file(f):
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())  # Ensure write to disk

                return

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to save stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def _atomic_update(self, update_func) -> None:
        """
        Perform an atomic update of statistics.

        Args:
            update_func: Function that takes stats dict and modifies it
        """
        for attempt in range(self.max_retries):
            try:
                # Ensure file exists
                if not self.stats_file.exists():
                    self.stats_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.stats_file, 'w', encoding='utf-8') as f:
                        json.dump(self._get_default_stats(), f, indent=4)

                # Open file and hold lock for entire operation
                with open(self.stats_file, 'r+', encoding='utf-8') as f:
                    with self._lock_file(f):
                        # Load
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            try:
                                stats = json.loads(content)
                            except json.JSONDecodeError:
                                stats = self._get_default_stats()
                        else:
                            stats = self._get_default_stats()

                        # Validate and ensure structure
                        if not isinstance(stats, dict):
                            stats = self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        # Modify (call user function)
                        update_func(stats)

                        # Update timestamp
                        stats["last_updated"] = datetime.now().isoformat()

                        # Save
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())

                return  # Success

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to update stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def record_analysis(
        self,
        client_id: str,
        session_id: str,
        orders_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record an analysis completion from Shopify Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier (e.g., "2025-11-05_1")
            orders_count: Number of orders analyzed
            metadata: Optional additional metadata (e.g., fulfillable_orders, courier_breakdown)

        Example:
            stats_manager.record_analysis(
                client_id="M",
                session_id="2025-11-05_1",
                orders_count=150,
                metadata={
                    "fulfillable_orders": 142,
                    "courier_breakdown": {"DHL": 80, "DPD": 62}
                }
            )
        """
        def update(stats):
            # Update global counters
            stats["total_orders_analyzed"] += orders_count

            # Update client stats
            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0
                }

            stats["by_client"][client_id]["orders_analyzed"] += orders_count

            # Add to analysis history
            record = {
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "session_id": session_id,
                "orders_count": orders_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["analysis_history"].append(record)

            # Keep only last 1000 records to prevent file bloat
            if len(stats["analysis_history"]) > 1000:
                stats["analysis_history"] = stats["analysis_history"][-1000:]

        self._atomic_update(update)

    def record_packing(
        self,
        client_id: str,
        session_id: str,
        worker_id: Optional[str],
        orders_count: int,
        items_count: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a packing session completion from Packing Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier (e.g., "2025-11-05_1")
            worker_id: Worker identifier (e.g., "001", "002")
            orders_count: Number of orders packed
            items_count: Number of items packed
            metadata: Optional additional metadata (e.g., duration, start_time, end_time)

        Example:
            stats_manager.record_packing(
                client_id="M",
                session_id="2025-11-05_1",
                worker_id="001",
                orders_count=142,
                items_count=450,
                metadata={
                    "start_time": "2025-11-05T10:00:00",
                    "end_time": "2025-11-05T12:30:00",
                    "duration_seconds": 9000
                }
            )
        """
        def update(stats):
            # Update global counters
            stats["total_orders_packed"] += orders_count
            stats["total_sessions"] += 1

            # Update client stats
            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0
                }

            stats["by_client"][client_id]["orders_packed"] += orders_count
            stats["by_client"][client_id]["sessions"] += 1

            # Add to packing history
            record = {
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "session_id": session_id,
                "worker_id": worker_id,
                "orders_count": orders_count,
                "items_count": items_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["packing_history"].append(record)

            # Keep only last 1000 records to prevent file bloat
            if len(stats["packing_history"]) > 1000:
                stats["packing_history"] = stats["packing_history"][-1000:]

        self._atomic_update(update)

    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global statistics summary.

        Returns:
            Dictionary with global statistics:
            {
                "total_orders_analyzed": 5420,
                "total_orders_packed": 4890,
                "total_sessions": 312,
                "last_updated": "2025-11-05T14:30:00"
            }
        """
        stats = self._load_stats()

        return {
            "total_orders_analyzed": stats.get("total_orders_analyzed", 0),
            "total_orders_packed": stats.get("total_orders_packed", 0),
            "total_sessions": stats.get("total_sessions", 0),
            "last_updated": stats.get("last_updated")
        }

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """
        Get statistics for a specific client.

        Args:
            client_id: Client identifier

        Returns:
            Dictionary with client statistics:
            {
                "orders_analyzed": 2100,
                "orders_packed": 1950,
                "sessions": 145
            }
        """
        stats = self._load_stats()

        if client_id not in stats.get("by_client", {}):
            return {
                "orders_analyzed": 0,
                "orders_packed": 0,
                "sessions": 0
            }

        return stats["by_client"][client_id].copy()

    def get_all_clients_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all clients.

        Returns:
            Dictionary mapping client IDs to their statistics
        """
        stats = self._load_stats()
        return stats.get("by_client", {}).copy()

    def get_analysis_history(
        self,
        client_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get analysis history with optional filtering.

        Args:
            client_id: Filter by client ID (None for all clients)
            limit: Maximum number of records to return (newest first)

        Returns:
            List of analysis records
        """
        stats = self._load_stats()
        history = stats.get("analysis_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        # Sort by timestamp (newest first)
        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_packing_history(
        self,
        client_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get packing history with optional filtering.

        Args:
            client_id: Filter by client ID (None for all clients)
            worker_id: Filter by worker ID (None for all workers)
            limit: Maximum number of records to return (newest first)

        Returns:
            List of packing records
        """
        stats = self._load_stats()
        history = stats.get("packing_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if worker_id:
            history = [h for h in history if h.get("worker_id") == worker_id]

        # Sort by timestamp (newest first)
        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def record_label_print(
        self,
        client_id: str,
        sku: str,
        copies: int,
    ) -> None:
        """
        Record a label print event from SKU Label widget.

        Args:
            client_id: Client identifier (e.g., "M", "A")
            sku: SKU that was printed
            copies: Number of copies printed
        """
        def update(stats):
            stats["total_labels_printed"] += copies

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                    "labels_printed": 0,
                }
            client = stats["by_client"][client_id]
            if "labels_printed" not in client:
                client["labels_printed"] = 0
            client["labels_printed"] += copies

            record = {
                "timestamp": datetime.now().isoformat(),
                "client_id": client_id,
                "sku": sku,
                "copies": copies,
            }
            stats["label_print_history"].append(record)

            if len(stats["label_print_history"]) > 1000:
                stats["label_print_history"] = stats["label_print_history"][-1000:]

        self._atomic_update(update)

    def get_label_print_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get label print history with optional filtering.

        Args:
            client_id: Filter by client ID (None for all clients)
            start_date: Filter records on or after this datetime
            end_date: Filter records on or before this datetime (inclusive, extended to end of day)
            limit: Maximum number of records to return (newest first)

        Returns:
            List of label print records
        """
        stats = self._load_stats()
        history = stats.get("label_print_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if start_date:
            history = [
                h for h in history
                if datetime.fromisoformat(h["timestamp"]) >= start_date
            ]

        if end_date:
            end_dt = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            history = [
                h for h in history
                if datetime.fromisoformat(h["timestamp"]) <= end_dt
            ]

        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_label_stats(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get label printing summary statistics.

        Args:
            client_id: Filter by client ID (None for all clients)

        Returns:
            Dictionary with:
            {
                "total_labels_printed": N,
                "unique_skus": N,
                "top_sku": "SKU" or None,
                "sku_breakdown": {"SKU": total_copies, ...}
            }
        """
        history = self.get_label_print_history(client_id=client_id)

        sku_counts: Dict[str, int] = {}
        for record in history:
            sku = record.get("sku", "Unknown")
            sku_counts[sku] = sku_counts.get(sku, 0) + record.get("copies", 1)

        total = sum(sku_counts.values())
        top_sku = max(sku_counts, key=sku_counts.get) if sku_counts else None

        return {
            "total_labels_printed": total,
            "unique_skus": len(sku_counts),
            "top_sku": top_sku,
            "sku_breakdown": sku_counts,
        }

    def reset_stats(self) -> None:
        """
        Reset all statistics to default values.

        WARNING: This will delete all historical data. Use with caution.
        """
        default_stats = self._get_default_stats()
        self._save_stats(default_stats)


# Example usage
if __name__ == "__main__":
    # Example for testing
    base_path = r"\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment"

    # Create manager
    manager = StatsManager(base_path)

    # Record analysis (Shopify Tool)
    manager.record_analysis(
        client_id="M",
        session_id="2025-11-05_1",
        orders_count=150,
        metadata={
            "fulfillable_orders": 142,
            "courier_breakdown": {"DHL": 80, "DPD": 62}
        }
    )

    # Record packing (Packing Tool)
    manager.record_packing(
        client_id="M",
        session_id="2025-11-05_1",
        worker_id="001",
        orders_count=142,
        items_count=450,
        metadata={
            "duration_seconds": 9000
        }
    )

    # Get statistics
    global_stats = manager.get_global_stats()
    print(f"Global stats: {global_stats}")

    client_stats = manager.get_client_stats("M")
    print(f"Client M stats: {client_stats}")
