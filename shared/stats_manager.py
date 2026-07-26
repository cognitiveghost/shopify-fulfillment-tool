"""
Unified Statistics Manager for Shopify Tool and Packing Tool

Canonical version. This module lives in packing-tool/shared/ and is copied
into shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py — the two copies must stay
byte-identical. See shared/README.md.

Manages centralized statistics stored on the file server in
Stats/global_stats.json:
- Centralized storage on file server
- File locking for concurrent access from multiple PCs
- Separate tracking for analysis (Shopify Tool) and packing operations (Packing Tool)
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
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from shared.file_lock import locked_file, FileLockError
from shared.metadata_utils import get_current_timestamp, parse_timestamp


class StatsManagerError(Exception):
    """Base exception for StatsManager errors."""
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
        "total_labels_printed": 88,
        "by_client": {
            "M": {
                "orders_analyzed": 2100,
                "orders_packed": 1950,
                "sessions": 145,
                "labels_printed": 12
            }
        },
        "analysis_history": [...],          # Shopify Tool records
        "packing_history": [...],           # Packing Tool records
        "label_print_history": [...],       # Shopify Tool label prints
        "last_updated": "2025-11-05T14:30:00+02:00",
        "version": "2.0"
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

        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_default_stats(self) -> Dict[str, Any]:
        """Get default statistics structure."""
        return {
            "total_orders_analyzed": 0,
            "total_orders_packed": 0,
            "total_sessions": 0,
            "total_labels_printed": 0,
            "by_client": {},
            "analysis_history": [],
            "packing_history": [],
            "label_print_history": [],
            "last_updated": get_current_timestamp(),
            "version": "2.0",
        }

    def _load_stats(self) -> Dict[str, Any]:
        """Load statistics from file with file locking."""
        if not self.stats_file.exists():
            return self._get_default_stats()

        for attempt in range(self.max_retries):
            try:
                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        content = f.read()
                        if not content.strip():
                            return self._get_default_stats()

                        stats = json.loads(content)

                        if not isinstance(stats, dict):
                            return self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        return stats

            except json.JSONDecodeError:
                return self._get_default_stats()
            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to load stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

        return self._get_default_stats()

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        """Save statistics to file with file locking."""
        stats["last_updated"] = get_current_timestamp()

        for attempt in range(self.max_retries):
            try:
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)

                mode = 'r+' if self.stats_file.exists() else 'w+'
                with open(self.stats_file, mode, encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        f.truncate()
                        json.dump(stats, f, indent=4, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())

                return

            except (IOError, FileLockError) as e:
                if attempt == self.max_retries - 1:
                    raise StatsManagerError(f"Failed to save stats after {self.max_retries} attempts: {e}")
                time.sleep(self.retry_delay * (attempt + 1))

    def _atomic_update(self, update_func) -> None:
        """Perform an atomic update of statistics.

        NOTE: this deliberately does NOT delegate to
        shared.atomic_write.atomic_write_json's temp+os.replace() pattern.
        The advisory lock in locked_file() is held on this specific open
        file handle for the entire read-modify-write; replacing the file
        at this path with a new inode (what os.replace() does) would
        detach the lock from the file everyone else is waiting on. Instead,
        the new content is fully serialized to a throwaway temp file first
        (so a failure there never touches the locked original), and only
        written into the still-open, still-locked handle once it is known
        good. See tests/test_atomic_write.py::
        test_stats_manager_atomic_update_is_actually_crash_safe.
        """
        for attempt in range(self.max_retries):
            try:
                if not self.stats_file.exists():
                    self.stats_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.stats_file, 'w', encoding='utf-8') as f:
                        json.dump(self._get_default_stats(), f, indent=4)

                with open(self.stats_file, 'r+', encoding='utf-8') as f:
                    with locked_file(f):
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            try:
                                stats = json.loads(content)
                            except json.JSONDecodeError:
                                stats = self._get_default_stats()
                        else:
                            stats = self._get_default_stats()

                        if not isinstance(stats, dict):
                            stats = self._get_default_stats()

                        default = self._get_default_stats()
                        for key in default:
                            if key not in stats:
                                stats[key] = default[key]

                        update_func(stats)

                        stats["last_updated"] = get_current_timestamp()

                        tmp_fd, tmp_name = tempfile.mkstemp(
                            dir=self.stats_file.parent,
                            prefix=f".{self.stats_file.stem}_tmp_",
                            suffix=self.stats_file.suffix,
                        )
                        try:
                            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_f:
                                json.dump(stats, tmp_f, indent=4, ensure_ascii=False)
                            new_content = Path(tmp_name).read_text(encoding='utf-8')
                        finally:
                            try:
                                os.unlink(tmp_name)
                            except OSError:
                                pass

                        f.seek(0)
                        f.truncate()
                        f.write(new_content)
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
        """Record an analysis completion from Shopify Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier — derive with
                shared.session_id.derive_session_id(session_path)
            orders_count: Number of orders analyzed
            metadata: Optional additional metadata (e.g., fulfillable_orders,
                courier_breakdown)
        """
        def update(stats):
            stats["total_orders_analyzed"] += orders_count

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                }

            stats["by_client"][client_id]["orders_analyzed"] += orders_count

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "session_id": session_id,
                "orders_count": orders_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["analysis_history"].append(record)

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
        """Record a packing session completion from Packing Tool.

        Args:
            client_id: Client identifier (e.g., "M", "A", "B")
            session_id: Session identifier — derive with
                shared.session_id.derive_session_id(session_path)
            worker_id: Worker identifier (e.g., "001", "002")
            orders_count: Number of orders packed
            items_count: Number of items packed
            metadata: Optional additional metadata (e.g., duration, start_time, end_time)
        """
        def update(stats):
            stats["total_orders_packed"] += orders_count
            stats["total_sessions"] += 1

            if client_id not in stats["by_client"]:
                stats["by_client"][client_id] = {
                    "orders_analyzed": 0,
                    "orders_packed": 0,
                    "sessions": 0,
                }

            stats["by_client"][client_id]["orders_packed"] += orders_count
            stats["by_client"][client_id]["sessions"] += 1

            record = {
                "timestamp": get_current_timestamp(),
                "client_id": client_id,
                "session_id": session_id,
                "worker_id": worker_id,
                "orders_count": orders_count,
                "items_count": items_count,
            }

            if metadata:
                record["metadata"] = metadata

            stats["packing_history"].append(record)

            if len(stats["packing_history"]) > 1000:
                stats["packing_history"] = stats["packing_history"][-1000:]

        self._atomic_update(update)

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics summary."""
        stats = self._load_stats()
        return {
            "total_orders_analyzed": stats.get("total_orders_analyzed", 0),
            "total_orders_packed": stats.get("total_orders_packed", 0),
            "total_sessions": stats.get("total_sessions", 0),
            "last_updated": stats.get("last_updated"),
        }

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a specific client."""
        stats = self._load_stats()
        if client_id not in stats.get("by_client", {}):
            return {"orders_analyzed": 0, "orders_packed": 0, "sessions": 0}
        return stats["by_client"][client_id].copy()

    def get_all_clients_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all clients."""
        stats = self._load_stats()
        return stats.get("by_client", {}).copy()

    def get_analysis_history(
        self,
        client_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get analysis history with optional filtering (newest first)."""
        stats = self._load_stats()
        history = stats.get("analysis_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

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
        """Get packing history with optional filtering (newest first)."""
        stats = self._load_stats()
        history = stats.get("packing_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if worker_id:
            history = [h for h in history if h.get("worker_id") == worker_id]

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
        """Record a label print event from the SKU Label widget."""
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
                "timestamp": get_current_timestamp(),
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
        """Get label print history with optional filtering.

        start_date/end_date may be naive or timezone-aware (the GUI builds
        them from a QDate, which has no timezone concept). Naive values are
        assumed to be in the local timezone — the same convention
        get_current_timestamp() uses when writing records — so comparing
        them against the stored (timezone-aware) timestamps never raises
        "can't compare offset-naive and offset-aware datetimes".
        """
        stats = self._load_stats()
        history = stats.get("label_print_history", [])

        if client_id:
            history = [h for h in history if h.get("client_id") == client_id]

        if start_date:
            if start_date.tzinfo is None:
                start_date = start_date.astimezone()
            filtered = []
            for h in history:
                ts = parse_timestamp(h["timestamp"])
                if ts is not None and ts >= start_date:
                    filtered.append(h)
            history = filtered

        if end_date:
            end_dt = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            if end_dt.tzinfo is None:
                end_dt = end_dt.astimezone()
            filtered = []
            for h in history:
                ts = parse_timestamp(h["timestamp"])
                if ts is not None and ts <= end_dt:
                    filtered.append(h)
            history = filtered

        history.sort(key=lambda h: h.get("timestamp", ""), reverse=True)

        if limit:
            history = history[:limit]

        return history

    def get_label_stats(
        self,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get label printing summary statistics."""
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
        """Reset all statistics to default values.

        WARNING: This will delete all historical data. Use with caution.
        """
        default_stats = self._get_default_stats()
        self._save_stats(default_stats)


if __name__ == "__main__":
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        manager = StatsManager(tmp)

        manager.record_analysis(
            client_id="M",
            session_id="2025-11-05_1",
            orders_count=150,
            metadata={"fulfillable_orders": 142, "courier_breakdown": {"DHL": 80, "DPD": 62}},
        )
        manager.record_packing(
            client_id="M",
            session_id="2025-11-05_1",
            worker_id="001",
            orders_count=142,
            items_count=450,
            metadata={"duration_seconds": 9000},
        )
        manager.record_label_print(client_id="M", sku="SKU-1", copies=3)

        stats = manager._load_stats()
        assert stats["total_orders_analyzed"] == 150
        assert stats["total_orders_packed"] == 142
        assert stats["total_labels_printed"] == 3
        assert stats["by_client"]["M"]["sessions"] == 1
        assert stats["version"] == "2.0"

        global_stats = manager.get_global_stats()
        assert global_stats["total_orders_analyzed"] == 150
        assert global_stats["total_orders_packed"] == 142

        print("stats_manager self-check OK")
