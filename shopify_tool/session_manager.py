"""Session Manager for Shopify Fulfillment Tool.

This module manages the lifecycle of client-specific fulfillment sessions.
It handles session creation, directory organization, and metadata management.

Key Features:
    - Create timestamped session directories ({YYYY-MM-DD_N})
    - Automatic creation of session subdirectories
    - Session metadata management via session_info.json
    - List and query existing sessions
    - Update session status and metadata

Directory Structure:
    Sessions/CLIENT_{ID}/{YYYY-MM-DD_N}/
        ├── session_info.json       # Session metadata
        ├── input/                  # Source files (orders.csv, stock.csv)
        ├── analysis/               # Analysis results and reports
        ├── packing_lists/          # Generated packing lists per courier
        └── stock_exports/          # Stock writeoff exports
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("ShopifyToolLogger")


class SessionManagerError(Exception):
    """Base exception for SessionManager errors."""
    pass


class SessionManager:
    """Manages the lifecycle of client-specific fulfillment sessions.

    This class handles:
    - Creating new sessions with unique timestamped names
    - Setting up session directory structure
    - Managing session metadata (session_info.json)
    - Listing and querying sessions
    - Updating session status

    Attributes:
        profile_manager: ProfileManager instance for accessing paths
    """

    # Session subdirectories
    SESSION_SUBDIRS = [
        "input",
        "analysis",
        "packing_lists",
        "stock_exports",
        "reference_labels",  # For PDF reference label processing
        "barcodes"  # NEW: For barcode labels (Feature #5)
    ]

    # Valid session statuses
    VALID_STATUSES = ["active", "completed", "abandoned", "archived"]

    # Class-level caches (mtime-based, shared across instances)
    _sessions_index_cache: Dict[str, Tuple[Dict, float]] = {}
    _registry_cache: Dict[str, Tuple[Dict, float]] = {}
    _cache_lock = threading.Lock()

    def __init__(self, profile_manager):
        """Initialize SessionManager with ProfileManager.

        Args:
            profile_manager: ProfileManager instance for accessing file server paths
        """
        self.profile_manager = profile_manager
        self.sessions_root = profile_manager.get_sessions_root()

        logger.info("SessionManager initialized")

    # ------------------------------------------------------------------
    # Session Index (shopify_sessions_index.json)
    # ------------------------------------------------------------------

    def _get_sessions_index_path(self, client_id: str) -> Path:
        return self.sessions_root / f"CLIENT_{client_id}" / "shopify_sessions_index.json"

    def get_registry_path(self, client_id: str) -> Path:
        """Return the path to the Packer Tool's registry_index.json for a client."""
        return self.sessions_root / f"CLIENT_{client_id}" / "registry_index.json"

    def _read_sessions_index(self, client_id: str) -> Optional[Dict]:
        """Read sessions index with mtime-based cache. Returns None if missing/corrupt."""
        index_path = self._get_sessions_index_path(client_id)
        if not index_path.exists():
            return None
        try:
            mtime = index_path.stat().st_mtime
            with SessionManager._cache_lock:
                cached = SessionManager._sessions_index_cache.get(client_id)
                if cached and cached[1] == mtime:
                    return cached[0]
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with SessionManager._cache_lock:
                SessionManager._sessions_index_cache[client_id] = (data, mtime)
            return data
        except Exception as e:
            logger.warning(f"Failed to read sessions index for {client_id}: {e}")
            return None

    def _write_sessions_index(self, client_id: str, index_data: Dict) -> bool:
        """Atomically write sessions index using temp-file rename.

        Uses a PID-unique temp filename to avoid collisions between concurrent
        writers, then retries os.replace() on transient Windows locking errors.
        """
        index_path = self._get_sessions_index_path(client_id)
        tmp_path = index_path.with_name(f"shopify_sessions_index.{uuid.uuid4().hex[:12]}.tmp")
        try:
            index_data["last_updated"] = datetime.now().isoformat()
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2)
            # Retry os.replace() — Windows can refuse if another reader has the
            # destination file open momentarily (WinError 32 / WinError 5).
            for attempt in range(4):
                try:
                    os.replace(str(tmp_path), str(index_path))
                    break
                except OSError:
                    if attempt == 3:
                        raise
                    time.sleep(0.05)
            mtime = index_path.stat().st_mtime
            with SessionManager._cache_lock:
                SessionManager._sessions_index_cache[client_id] = (index_data, mtime)
            return True
        except Exception as e:
            logger.warning(f"Failed to write sessions index for {client_id}: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def _make_index_entry(self, session_info: Dict) -> Dict:
        """Extract the fields stored per-session in the index."""
        stats = session_info.get("statistics", {})
        return {
            "session_name": session_info.get("session_name", ""),
            "created_at": session_info.get("created_at", ""),
            "status": session_info.get("status", "active"),
            "orders_count": stats.get("total_orders", 0),
            "items_count": stats.get("total_items", 0),
            "fulfillable_orders": session_info.get("fulfillable_orders", 0),
            "not_fulfillable_orders": session_info.get("not_fulfillable_orders", 0),
            "packing_lists_count": stats.get("packing_lists_count", 0),
            "packing_lists": stats.get("packing_lists", []),
            "comments": session_info.get("comments", ""),
            "last_modified": session_info.get("last_modified", session_info.get("last_updated", "")),
        }

    def _update_index_entry(self, client_id: str, session_name: str, session_info: Dict) -> None:
        """Update a single session entry in the index (fire-and-forget, non-fatal)."""
        try:
            index = self._read_sessions_index(client_id)
            if index is None:
                index = {"version": "1.0", "client_id": client_id, "sessions": {}}
            index["sessions"][session_name] = self._make_index_entry(session_info)
            self._write_sessions_index(client_id, index)
        except Exception as e:
            logger.debug(f"Index update skipped for {client_id}/{session_name}: {e}")

    def _build_sessions_index(self, client_id: str) -> Dict:
        """Rebuild sessions index by scanning all session directories."""
        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"
        index: Dict = {"version": "1.0", "client_id": client_id, "sessions": {}}
        if not client_sessions_dir.exists():
            return index
        for item in client_sessions_dir.iterdir():
            if not item.is_dir():
                continue
            session_info = self.get_session_info(str(item))
            if session_info:
                # Use the actual folder name as the key so session_path is always correct,
                # even if session_info["session_name"] was manually edited.
                index["sessions"][item.name] = self._make_index_entry(session_info)
        self._write_sessions_index(client_id, index)
        logger.debug(f"Sessions index rebuilt for {client_id}: {len(index['sessions'])} sessions")
        return index

    # ------------------------------------------------------------------
    # Packer Tool Registry Reader
    # ------------------------------------------------------------------

    def read_packing_registry(self, client_id: str) -> Dict:
        """Read Packer Tool's registry_index.json with mtime-based cache."""
        registry_path = self.get_registry_path(client_id)
        if not registry_path.exists():
            return {}
        try:
            mtime = registry_path.stat().st_mtime
            with SessionManager._cache_lock:
                cached = SessionManager._registry_cache.get(client_id)
                if cached and cached[1] == mtime:
                    return cached[0]
            with open(registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with SessionManager._cache_lock:
                SessionManager._registry_cache[client_id] = (data, mtime)
            return data
        except Exception as e:
            logger.warning(f"Failed to read packing registry for {client_id}: {e}")
            return {}

    def get_session_packing_summary(self, client_id: str, session_id: str) -> Dict:
        """Aggregate packing data for a session from the Packer Tool registry.

        The registry keys use format "session_id::packing_list_name", so we
        collect all entries whose key starts with "{session_id}::".

        Returns:
            dict with keys: pack_status, packed_orders, total_orders,
                            worker_names, packing_lists, last_pack_activity
        """
        registry = self.read_packing_registry(client_id)
        prefix = f"{session_id}::"

        session_entries = {
            k: v for k, v in registry.get("sessions", {}).items()
            if k.startswith(prefix)
        }
        available_entries = {
            k: v for k, v in registry.get("available_lists", {}).items()
            if k.startswith(prefix)
        }

        if not session_entries and not available_entries:
            return {
                "pack_status": "not_started",
                "packed_orders": 0,
                "total_orders": 0,
                "worker_names": [],
                "packing_lists": [],
                "last_pack_activity": "",
            }

        total_packed = 0
        total_orders = 0
        workers: set = set()
        packing_list_names: set = set()
        last_activity = ""

        for entry in session_entries.values():
            packing_list_names.add(entry.get("packing_list_name", ""))
            total_packed += entry.get("completed_orders", 0)
            total_orders += entry.get("total_orders", 0)
            worker = entry.get("worker_name")
            if worker:
                workers.add(worker)
            activity = entry.get("last_updated", "")
            if activity > last_activity:
                last_activity = activity

        for av in available_entries.values():
            packing_list_names.add(av.get("packing_list_name", ""))
            if total_orders == 0:
                total_orders = av.get("total_orders", 0)

        statuses = {e.get("status", "unknown") for e in session_entries.values()}
        if "in_progress" in statuses:
            pack_status = "in_progress"
        elif session_entries and all(s == "completed" for s in statuses):
            pack_status = "completed"
        elif session_entries:
            pack_status = "partial"
        else:
            pack_status = "available"  # lists exist in available_lists but none started

        return {
            "pack_status": pack_status,
            "packed_orders": total_packed,
            "total_orders": total_orders,
            "worker_names": sorted(workers),
            "packing_lists": sorted(packing_list_names - {""}),
            "last_pack_activity": last_activity,
        }

    def create_session(self, client_id: str) -> str:
        """Create a new session for a client.

        Creates a timestamped directory with format {YYYY-MM-DD_N} where N is
        an incrementing number for multiple sessions on the same day.

        Also creates:
        - Session subdirectories (input/, analysis/, etc.)
        - session_info.json with initial metadata

        Args:
            client_id (str): Client ID (e.g., "M")

        Returns:
            str: Full path to created session directory

        Raises:
            SessionManagerError: If session creation fails
        """
        client_id = client_id.upper()

        # Verify client exists
        if not self.profile_manager.client_exists(client_id):
            raise SessionManagerError(f"Client does not exist: CLIENT_{client_id}")

        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"
        client_sessions_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique session name
        session_name = self._generate_unique_session_name(client_sessions_dir)
        session_path = client_sessions_dir / session_name

        try:
            # Create session directory
            session_path.mkdir(parents=True)

            # Create subdirectories
            for subdir in self.SESSION_SUBDIRS:
                (session_path / subdir).mkdir()

            # Create session_info.json
            session_info = {
                "created_by_tool": "shopify",
                "created_at": datetime.now().isoformat(),
                "client_id": client_id,
                "session_name": session_name,
                "status": "active",
                "pc_name": os.environ.get('COMPUTERNAME', 'Unknown'),
                "orders_file": None,
                "stock_file": None,
                "analysis_completed": False,
                "packing_lists_generated": [],
                "stock_exports_generated": [],
                "statistics": {
                    "total_orders": 0,
                    "total_items": 0,
                    "packing_lists_count": 0,
                    "packing_lists": []
                },
                "comments": "",
                "last_modified": datetime.now().isoformat()
            }

            session_info_path = session_path / "session_info.json"
            with open(session_info_path, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2)

            logger.info(f"Session created: CLIENT_{client_id}/{session_name}")
            self._update_index_entry(client_id, session_name, session_info)
            return str(session_path)

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            # Cleanup on failure
            if session_path.exists():
                import shutil
                shutil.rmtree(session_path, ignore_errors=True)
            raise SessionManagerError(f"Failed to create session: {e}")

    def _generate_unique_session_name(self, client_sessions_dir: Path) -> str:
        """Generate unique session name with format {YYYY-MM-DD_N}.

        Finds the next available number for today's date.

        Args:
            client_sessions_dir (Path): Client's sessions directory

        Returns:
            str: Unique session name (e.g., "2025-11-05_1")
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Find existing sessions for today
        existing_sessions = []
        if client_sessions_dir.exists():
            for item in client_sessions_dir.iterdir():
                if item.is_dir() and item.name.startswith(today):
                    existing_sessions.append(item.name)

        # Find next available number
        if not existing_sessions:
            return f"{today}_1"

        # Extract numbers from existing sessions
        numbers = []
        for session_name in existing_sessions:
            try:
                # Format: YYYY-MM-DD_N
                parts = session_name.split('_')
                if len(parts) >= 2:  # Should have at least date_number
                    # Last part should be the number
                    number = int(parts[-1])
                    numbers.append(number)
            except (ValueError, IndexError):
                continue

        # Get next number
        next_number = max(numbers) + 1 if numbers else 1
        return f"{today}_{next_number}"

    def get_session_path(self, client_id: str, session_name: str) -> Path:
        """Get full path to a session directory.

        Args:
            client_id (str): Client ID
            session_name (str): Session name (e.g., "2025-11-05_1")

        Returns:
            Path: Full path to session directory
        """
        client_id = client_id.upper()
        return self.sessions_root / f"CLIENT_{client_id}" / session_name

    def list_client_sessions(
        self,
        client_id: str,
        status_filter: Optional[str] = None
    ) -> List[Dict]:
        """List all sessions for a client.

        Uses shopify_sessions_index.json for fast loading (O(1) reads).
        Falls back to full directory scan and rebuilds the index if the index
        is missing or the sessions directory has been modified since the index.

        Args:
            client_id (str): Client ID
            status_filter (str, optional): Filter by status ("active", "completed", etc.)

        Returns:
            List[Dict]: List of session info dictionaries, sorted by creation date (newest first)
        """
        client_id = client_id.upper()
        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            return []

        # Determine whether the index is usable or needs a rebuild.
        # Compare folder names rather than directory mtime: on a multi-PC network
        # share the directory mtime changes whenever any session file is modified,
        # causing unnecessary full rebuilds.  A single iterdir() call (no file I/O
        # per session) tells us if folders were added or removed.
        index = self._read_sessions_index(client_id)
        if index is not None:
            try:
                actual_names = {item.name for item in client_sessions_dir.iterdir() if item.is_dir()}
                indexed_names = set(index.get("sessions", {}).keys())
                if actual_names != indexed_names:
                    index = None  # Rebuild only when session folders are added or removed
            except Exception:
                index = None

        if index is None:
            logger.debug(f"Building sessions index for {client_id}")
            index = self._build_sessions_index(client_id)

        # Build result list from index entries
        sessions = []
        for session_name, entry in index.get("sessions", {}).items():
            if status_filter and entry.get("status") != status_filter:
                continue
            sessions.append({
                "session_name": entry["session_name"],
                "client_id": client_id,
                "created_at": entry["created_at"],
                "status": entry["status"],
                "comments": entry.get("comments", ""),
                "session_path": str(client_sessions_dir / session_name),
                "statistics": {
                    "total_orders": entry.get("orders_count", 0),
                    "total_items": entry.get("items_count", 0),
                    "fulfillable_orders": entry.get("fulfillable_orders", 0),
                    "not_fulfillable_orders": entry.get("not_fulfillable_orders", 0),
                    "packing_lists_count": entry.get("packing_lists_count", 0),
                    "packing_lists": entry.get("packing_lists", []),
                },
            })

        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions

    def get_session_info(self, session_path: str) -> Optional[Dict]:
        """Load session metadata from session_info.json.

        Args:
            session_path (str): Full path to session directory

        Returns:
            Optional[Dict]: Session info dictionary or None if not found/invalid
        """
        session_path_obj = Path(session_path)
        session_info_path = session_path_obj / "session_info.json"

        if not session_info_path.exists():
            logger.warning(f"Session info not found: {session_path}")
            return None

        try:
            with open(session_info_path, 'r', encoding='utf-8') as f:
                session_info = json.load(f)

            # Add full path to info
            session_info["session_path"] = str(session_path_obj)

            # Calculate statistics if missing (backwards compatibility)
            if "statistics" not in session_info:
                session_info["statistics"] = self.calculate_session_statistics(session_path)

            # Ensure comments field exists
            if "comments" not in session_info:
                session_info["comments"] = ""

            return session_info

        except Exception as e:
            logger.error(f"Failed to load session info: {e}")
            return None

    def update_session_status(self, session_path: str, status: str) -> bool:
        """Update session status in session_info.json.

        Args:
            session_path (str): Full path to session directory
            status (str): New status ("active", "completed", "abandoned")

        Returns:
            bool: True if updated successfully

        Raises:
            SessionManagerError: If status is invalid or update fails
        """
        if status not in self.VALID_STATUSES:
            raise SessionManagerError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )

        session_info = self.get_session_info(session_path)
        if not session_info:
            raise SessionManagerError(f"Session not found: {session_path}")

        # Update status
        session_info["status"] = status
        session_info["status_updated_at"] = datetime.now().isoformat()

        # Save back
        session_path_obj = Path(session_path)
        session_info_path = session_path_obj / "session_info.json"

        try:
            # Remove computed fields
            session_info.pop("session_path", None)

            with open(session_info_path, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2)

            logger.info(f"Session status updated to '{status}': {session_path}")
            # Update index entry
            session_info["session_path"] = session_path
            client_id = session_info.get("client_id", "")
            session_name = session_info.get("session_name", session_path_obj.name)
            if client_id:
                self._update_index_entry(client_id, session_name, session_info)
            return True

        except Exception as e:
            logger.error(f"Failed to update session status: {e}")
            raise SessionManagerError(f"Failed to update session status: {e}")

    def update_session_info(self, session_path: str, updates: Dict) -> bool:
        """Update session metadata with arbitrary fields.

        Args:
            session_path (str): Full path to session directory
            updates (Dict): Dictionary of fields to update

        Returns:
            bool: True if updated successfully

        Raises:
            SessionManagerError: If update fails
        """
        session_info = self.get_session_info(session_path)
        if not session_info:
            raise SessionManagerError(f"Session not found: {session_path}")

        # Apply updates
        session_info.update(updates)
        session_info["last_updated"] = datetime.now().isoformat()

        # Save back
        session_path_obj = Path(session_path)
        session_info_path = session_path_obj / "session_info.json"

        try:
            # Remove computed fields
            session_info.pop("session_path", None)

            with open(session_info_path, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2)

            logger.info(f"Session info updated: {session_path}")
            # Update index entry
            session_info["session_path"] = session_path
            client_id = session_info.get("client_id", "")
            session_name = session_info.get("session_name", session_path_obj.name)
            if client_id:
                self._update_index_entry(client_id, session_name, session_info)
            return True

        except Exception as e:
            logger.error(f"Failed to update session info: {e}")
            raise SessionManagerError(f"Failed to update session info: {e}")

    def get_session_subdirectory(self, session_path: str, subdir_name: str) -> Path:
        """Get path to a session subdirectory.

        Args:
            session_path (str): Full path to session directory
            subdir_name (str): Subdirectory name ("input", "analysis", etc.)

        Returns:
            Path: Full path to subdirectory

        Raises:
            SessionManagerError: If subdirectory doesn't exist
        """
        if subdir_name not in self.SESSION_SUBDIRS:
            raise SessionManagerError(
                f"Invalid subdirectory: {subdir_name}. "
                f"Must be one of {self.SESSION_SUBDIRS}"
            )

        subdir_path = Path(session_path) / subdir_name

        if not subdir_path.exists():
            raise SessionManagerError(f"Subdirectory not found: {subdir_path}")

        return subdir_path

    def get_input_dir(self, session_path: str) -> Path:
        """Get path to session input directory."""
        return self.get_session_subdirectory(session_path, "input")

    def get_analysis_dir(self, session_path: str) -> Path:
        """Get path to session analysis directory."""
        return self.get_session_subdirectory(session_path, "analysis")

    def get_packing_lists_dir(self, session_path: str) -> Path:
        """Get path to session packing_lists directory."""
        return self.get_session_subdirectory(session_path, "packing_lists")

    def get_stock_exports_dir(self, session_path: str) -> Path:
        """Get path to session stock_exports directory."""
        return self.get_session_subdirectory(session_path, "stock_exports")

    def get_reference_labels_dir(self, session_path: str) -> Path:
        """
        Get path to session reference_labels directory.

        Args:
            session_path: Session path

        Returns:
            Path: Path to reference_labels subdirectory

        Example:
            >>> manager.get_reference_labels_dir("Sessions/CLIENT_M/2025-01-15_1")
            Path("Sessions/CLIENT_M/2025-01-15_1/reference_labels")
        """
        return self.get_session_subdirectory(session_path, "reference_labels")

    def get_barcodes_dir(self, session_path: str) -> Path:
        """
        Get path to session barcodes directory.

        Args:
            session_path: Session path

        Returns:
            Path: Path to barcodes subdirectory

        Example:
            >>> sm.get_barcodes_dir("Sessions/CLIENT_M/2026-01-16_1")
            Path("Sessions/CLIENT_M/2026-01-16_1/barcodes")
        """
        return Path(session_path) / "barcodes"

    def get_packing_list_barcode_dir(self, session_path: str, packing_list_name: str) -> Path:
        """
        Get path to barcode directory for specific packing list.

        Each packing list has its own barcode subdirectory to organize labels.

        Args:
            session_path: Session path
            packing_list_name: Name of packing list (e.g., "DHL_Orders")

        Returns:
            Path: Path to packing list's barcode subdirectory

        Example:
            >>> sm.get_packing_list_barcode_dir("Sessions/CLIENT_M/2026-01-16_1", "DHL_Orders")
            Path("Sessions/CLIENT_M/2026-01-16_1/barcodes/DHL_Orders")
        """
        return self.get_barcodes_dir(session_path) / packing_list_name

    def get_barcode_history_file(self, session_path: str, packing_list_name: str) -> Path:
        """
        Get path to barcode history JSON file for specific packing list.

        Args:
            session_path: Session path
            packing_list_name: Name of packing list

        Returns:
            Path: Path to barcode_history.json
        """
        return self.get_packing_list_barcode_dir(session_path, packing_list_name) / "barcode_history.json"

    def session_exists(self, client_id: str, session_name: str) -> bool:
        """Check if a session exists.

        Args:
            client_id (str): Client ID
            session_name (str): Session name

        Returns:
            bool: True if session exists
        """
        session_path = self.get_session_path(client_id, session_name)
        return session_path.exists() and session_path.is_dir()

    def delete_session(self, session_path: str) -> bool:
        """Delete a session directory.

        WARNING: This permanently deletes all session data.

        Args:
            session_path (str): Full path to session directory

        Returns:
            bool: True if deleted successfully

        Raises:
            SessionManagerError: If deletion fails
        """
        session_path_obj = Path(session_path)

        if not session_path_obj.exists():
            logger.warning(f"Session not found for deletion: {session_path}")
            return False

        try:
            import shutil
            shutil.rmtree(session_path_obj)
            logger.info(f"Session deleted: {session_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            raise SessionManagerError(f"Failed to delete session: {e}")

    def calculate_session_statistics(self, session_path: str) -> Dict:
        """Calculate session statistics by scanning session directory.

        Reads analysis_data.json for orders/items count and scans packing_lists
        directory for generated packing lists.

        Args:
            session_path (str): Full path to session directory

        Returns:
            dict: {
                "total_orders": int,
                "total_items": int,
                "packing_lists_count": int,
                "packing_lists": list[str]
            }
        """
        session_path_obj = Path(session_path)
        statistics = {
            "total_orders": 0,
            "total_items": 0,
            "packing_lists_count": 0,
            "packing_lists": []
        }

        try:
            # Try to read analysis_data.json for orders/items count
            analysis_dir = session_path_obj / "analysis"
            analysis_data_path = analysis_dir / "analysis_data.json"

            if analysis_data_path.exists():
                with open(analysis_data_path, 'r', encoding='utf-8') as f:
                    analysis_data = json.load(f)

                # Count unique orders and total items
                if isinstance(analysis_data, list):
                    statistics["total_items"] = len(analysis_data)
                    # Count unique Order_Number values
                    order_numbers = set()
                    for item in analysis_data:
                        if "Order_Number" in item:
                            order_numbers.add(item["Order_Number"])
                    statistics["total_orders"] = len(order_numbers)

            # Count packing lists
            packing_lists_dir = session_path_obj / "packing_lists"
            if packing_lists_dir.exists():
                packing_lists = [f.stem for f in packing_lists_dir.glob("*.json")]
                statistics["packing_lists"] = sorted(packing_lists)
                statistics["packing_lists_count"] = len(packing_lists)

        except Exception as e:
            logger.warning(f"Failed to calculate statistics for {session_path}: {e}")

        return statistics
