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

import contextlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from shared.atomic_write import atomic_write_json

logger = logging.getLogger("ShopifyToolLogger")


class SessionManagerError(Exception):
    """Base exception for SessionManager errors."""


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
    SESSION_SUBDIRS: ClassVar[list[str]] = [
        "input",
        "analysis",
        "packing_lists",
        "stock_exports",
        "reference_labels",  # For PDF reference label processing
        "barcodes"  # NEW: For barcode labels (Feature #5)
    ]

    # Valid session statuses
    VALID_STATUSES: ClassVar[list[str]] = ["active", "completed", "abandoned", "archived"]

    # Per-client session index cache filename (see docs/superpowers/specs/2026-07-27-ui-responsiveness-design.md)
    INDEX_FILENAME: ClassVar[str] = "session_index.json"

    def __init__(self, profile_manager):
        """Initialize SessionManager with ProfileManager.

        Args:
            profile_manager: ProfileManager instance for accessing file server paths
        """
        self.profile_manager = profile_manager
        self.sessions_root = profile_manager.get_sessions_root()

        logger.info("SessionManager initialized")

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

        # mkdir without exist_ok is the claim. Two PCs can derive one name
        # from a stale listing (SMB caches it ~10 s) and only one mkdir wins;
        # the loser takes the next number rather than touching that folder
        # (AUDIT-05-1). Counting on from the name, not re-listing, because
        # the listing is what was stale.
        date, _, number = self._generate_unique_session_name(
            client_sessions_dir
        ).rpartition("_")
        for n in range(int(number), int(number) + 10):
            session_path = client_sessions_dir / f"{date}_{n}"
            try:
                session_path.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise SessionManagerError(
                f"No free session name for CLIENT_{client_id} on {date}"
            )
        session_name = session_path.name

        # Past this point the folder is ours, so the cleanup below can only
        # ever remove what this call created.
        try:
            # Create subdirectories
            for subdir in self.SESSION_SUBDIRS:
                (session_path / subdir).mkdir()

            # Create session_info.json
            session_info = {
                "created_by_tool": "shopify",
                "created_at": datetime.now().astimezone().isoformat(),
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
                "last_modified": datetime.now().astimezone().isoformat()
            }

            session_info_path = session_path / "session_info.json"
            atomic_write_json(session_info_path, session_info, indent=2)

            try:
                self._upsert_index_entry(session_path, session_info)
            except Exception:
                logger.exception(f"Failed to update session index for {session_path}")
            self.profile_manager.invalidate_metadata_cache(client_id)

            logger.info(f"Session created: CLIENT_{client_id}/{session_name}")
            return str(session_path)

        except Exception as e:
            logger.exception("Failed to create session")
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
        today = datetime.now().astimezone().strftime("%Y-%m-%d")

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
        status_filter: str | None = None
    ) -> list[dict]:
        """List all sessions for a client.

        Reads the per-client session_index.json cache instead of opening every
        session's session_info.json (see docs/superpowers/specs/2026-07-27-ui-responsiveness-design.md).
        Folders whose mtime no longer matches their entry are reread first
        (see _refresh_index).

        Args:
            client_id (str): Client ID
            status_filter (str, optional): Filter by status ("active", "completed", etc.)

        Returns:
            List[Dict]: List of session info dictionaries, sorted by creation date (newest first)
                Each dict contains session metadata including session_name, status, created_at
        """
        client_id = client_id.upper()
        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            return []

        entries = self._read_index(client_sessions_dir)
        if entries is None:
            entries = self._rebuild_index(client_sessions_dir)
        else:
            entries = self._refresh_index(client_sessions_dir, entries)

        sessions = []
        for entry in entries:
            if entry.get("_no_session_info"):
                continue
            session_info = {k: v for k, v in entry.items() if not k.startswith("_")}
            session_info["session_path"] = str(client_sessions_dir / session_info["session_name"])
            if status_filter and session_info.get("status") != status_filter:
                continue
            sessions.append(session_info)

        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions

    @contextlib.contextmanager
    def _exclusive_lock(self, lock_path: Path):
        """Blocking exclusive lock on an arbitrary sidecar `.lock` file.

        Without this, two near-simultaneous read-modify-write cycles on the
        file `lock_path` guards each read the same on-disk snapshot before
        either writes back, and one update silently loses the other's change.
        """
        with open(lock_path, "a+") as lock_file:
            locked = False
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                locked = True
                yield
            finally:
                # Release only a lock this call took (AUDIT-07-L4).
                if locked and os.name == "nt":
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif locked:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @contextlib.contextmanager
    def _locked_session_info(self, session_path_obj: Path):
        """Blocking exclusive lock spanning a session_info.json read-modify-write."""
        with self._exclusive_lock(session_path_obj / "session_info.json.lock"):
            yield

    def get_session_info(self, session_path: str) -> dict | None:
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

        except Exception:
            logger.exception("Failed to load session info")
            return None

    def _index_lock_path(self, client_sessions_dir: Path) -> Path:
        return client_sessions_dir / f"{self.INDEX_FILENAME}.lock"

    def _read_index(self, client_sessions_dir: Path) -> list[dict] | None:
        """Read the raw index file, or None if it doesn't exist / is unreadable."""
        index_path = client_sessions_dir / self.INDEX_FILENAME
        if not index_path.exists():
            return None
        try:
            with open(index_path, encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            logger.exception("Failed to read session index, treating as missing")
            return None
        if not isinstance(entries, list):
            logger.warning("Session index is not a list, treating as missing")
            return None
        return [e for e in entries if isinstance(e, dict)]

    def _listing(self, client_sessions_dir: Path) -> dict[str, float]:
        """{folder name: st_mtime} for every session folder, from one listing.

        scandir, not iterdir: on Windows the directory listing already
        carries the timestamps, so DirEntry.stat() costs no extra network
        round trip on the share.
        """
        listing = {}
        with os.scandir(client_sessions_dir) as it:
            for item in it:
                try:
                    if item.is_dir():
                        listing[item.name] = item.stat().st_mtime
                except OSError:
                    continue
        return listing

    def _index_entry(self, session_dir: Path, dir_mtime: float) -> dict:
        """One index entry, read from the folder's session_info.json.

        `_dir_mtime` is the folder's mtime from the listing taken before the
        read, so a write that lands during the read shows up as a change on
        the next listing. The entry is keyed by the folder's name, which is
        what list_client_sessions builds the session path from.

        A folder whose session_info.json is missing or unreadable (a manual
        archive, a half-deleted session) gets a marker entry instead, so it
        is read again only when its mtime changes. list_client_sessions
        never returns markers.
        """
        info = self.get_session_info(str(session_dir))
        if not info:
            return {"session_name": session_dir.name, "_dir_mtime": dir_mtime, "_no_session_info": True}
        info.pop("session_path", None)
        info["session_name"] = session_dir.name
        info["_dir_mtime"] = dir_mtime
        return info

    @staticmethod
    def _index_matches(listing: dict[str, float], entries: list[dict]) -> bool:
        """True if every folder has exactly one entry with its current mtime."""
        if len(entries) != len(listing):
            return False
        for entry in entries:
            name = entry.get("session_name")
            if name not in listing or entry.get("_dir_mtime") != listing[name]:
                return False
        return True

    def _refresh_index(self, client_sessions_dir: Path, entries: list[dict]) -> list[dict]:
        """Reread only the session folders that changed since the index saw them.

        Each entry records its folder's mtime (`_dir_mtime`). Packing Tool
        writes session_info.json as temp-file + rename (see
        shared.atomic_write), which bumps the folder's mtime, so its writes
        show up here as a changed entry. This class's own writers record the
        folder's mtime after the write they mirror, so they never cause a
        reread. The comparison is per entry and by equality: clocks that
        disagree between PCs no longer matter, and a mismatch costs one
        reread, never wrong data. A legacy entry without `_dir_mtime` counts
        as changed, so the first listing after the upgrade rereads each
        session once.

        Nothing changed means no lock and no write.
        """
        if self._index_matches(self._listing(client_sessions_dir), entries):
            return entries

        with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
            current = self._read_index(client_sessions_dir) or []
            listing = self._listing(client_sessions_dir)
            by_name = {e.get("session_name"): e for e in current}
            refreshed = []
            for name, dir_mtime in listing.items():
                entry = by_name.get(name)
                if entry is None or entry.get("_dir_mtime") != dir_mtime:
                    entry = self._index_entry(client_sessions_dir / name, dir_mtime)
                refreshed.append(entry)
            self._write_index(client_sessions_dir, refreshed)
        return refreshed

    def _write_index(self, client_sessions_dir: Path, entries: list[dict]) -> None:
        index_path = client_sessions_dir / self.INDEX_FILENAME
        atomic_write_json(index_path, entries)

    def _scan_sessions(self, client_sessions_dir: Path) -> list[dict]:
        """Full folder scan (the old list_client_sessions behavior) -- used only
        by _rebuild_index, never on the normal read path."""
        return [
            self._index_entry(client_sessions_dir / name, dir_mtime)
            for name, dir_mtime in self._listing(client_sessions_dir).items()
        ]

    def _rebuild_index(self, client_sessions_dir: Path) -> list[dict]:
        """Full scan + persist. Called when no index exists yet, or it is
        unreadable; a readable index is refreshed entry by entry instead
        (see _refresh_index).

        Scan and write both happen under the index lock: an unlocked scan
        could read a stale snapshot, then overwrite a concurrent
        _upsert_index_entry() write for an unrelated session with that
        stale data once the lock is finally taken for the write.
        """
        with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
            entries = self._scan_sessions(client_sessions_dir)
            self._write_index(client_sessions_dir, entries)
        return entries

    def _upsert_index_entry(self, session_path_obj: Path, session_info: dict) -> None:
        """Insert or replace one session's entry in its client's index.

        Best-effort: index-write failures are logged, not raised, since the
        index is a read-side cache and must never block the session_info.json
        write it mirrors.

        Called after that write, so the folder's mtime recorded here already
        includes it and the next listing sees no change.
        """
        try:
            client_sessions_dir = session_path_obj.parent
            entry = dict(session_info)
            entry.pop("session_path", None)
            session_name = session_path_obj.name
            entry["session_name"] = session_name
            with contextlib.suppress(OSError):
                entry["_dir_mtime"] = os.stat(session_path_obj).st_mtime
            with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
                entries = self._read_index(client_sessions_dir) or []
                entries = [e for e in entries if e.get("session_name") != session_name]
                entries.append(entry)
                self._write_index(client_sessions_dir, entries)
        except Exception:
            logger.exception(f"Failed to update session index for {session_path_obj}")

    def update_session_status(self, session_path: str, status: str, manual: bool = False) -> bool:
        """Update session status in session_info.json.

        Args:
            session_path (str): Full path to session directory
            status (str): New status ("active", "completed", "abandoned")
            manual (bool): True when a human set this status. Records
                `status_manually_set`, which stops session_lifecycle from
                ever managing this session's status again.

        Returns:
            bool: True if updated successfully

        Raises:
            SessionManagerError: If status is invalid or update fails
        """
        if status not in self.VALID_STATUSES:
            raise SessionManagerError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )

        session_path_obj = Path(session_path)

        with self._locked_session_info(session_path_obj):
            session_info = self.get_session_info(session_path)
            if not session_info:
                raise SessionManagerError(f"Session not found: {session_path}")

            # Update status
            session_info["status"] = status
            session_info["status_updated_at"] = datetime.now().astimezone().isoformat()
            if manual:
                session_info["status_manually_set"] = True

            # Save back
            session_info_path = session_path_obj / "session_info.json"

            try:
                # Remove computed fields
                session_info.pop("session_path", None)

                atomic_write_json(session_info_path, session_info, indent=2)

                try:
                    self._upsert_index_entry(session_path_obj, session_info)
                except Exception:
                    logger.exception(f"Failed to update session index for {session_path_obj}")
                logger.info(f"Session status updated to '{status}': {session_path}")
                return True

            except Exception as e:
                logger.exception("Failed to update session status")
                raise SessionManagerError(f"Failed to update session status: {e}")

    def apply_status_updates(self, client_id: str, updates: dict) -> int:
        """Set many sessions' statuses with a single index rewrite.

        `update_session_status` rewrites the whole client index per call, so
        applying a backlog one session at a time is O(N^2) in bytes written
        over a UNC share. Each session_info.json still takes its own lock,
        but the index is written once.

        That lock serializes this class against itself only: Packing Tool's
        update_session_metadata() read-modify-writes the same file without
        taking the sidecar lock, so its packing_progress write and this
        status write can still lose each other in the few ms between read
        and write. Both sides re-derive on the next refresh, so the cost is
        a stale field, not lost order data. Closing it properly means
        teaching Packing Tool to take the same lock.

        Best-effort per session: one unwritable session is logged and skipped
        and the rest still apply. Never raises; a session list that will not
        load is worse than one carrying a stale status.

        Returns the number of sessions actually updated.
        """
        if not updates:
            return 0

        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id.upper()}"
        applied = {}

        for session_name, status in updates.items():
            if status not in self.VALID_STATUSES:
                logger.warning(f"Skipping invalid status '{status}' for {session_name}")
                continue
            session_path_obj = client_sessions_dir / session_name
            try:
                with self._locked_session_info(session_path_obj):
                    session_info = self.get_session_info(str(session_path_obj))
                    if not session_info:
                        logger.warning(f"Skipping missing session: {session_path_obj}")
                        continue
                    session_info["status"] = status
                    session_info["status_updated_at"] = datetime.now().astimezone().isoformat()
                    session_info.pop("session_path", None)
                    # Atomic: this path writes ~N files unattended (41 on the
                    # first archive pass). A torn session_info.json makes
                    # get_session_info return None, which drops the session
                    # out of the browser entirely and breaks Packing Tool's
                    # read of the same file.
                    atomic_write_json(session_path_obj / "session_info.json", session_info, indent=2)
                    session_info["session_name"] = session_name
                    with contextlib.suppress(OSError):
                        session_info["_dir_mtime"] = os.stat(session_path_obj).st_mtime
                applied[session_name] = session_info
            except Exception:
                logger.exception(f"Failed to apply status to {session_path_obj}")

        if not applied:
            return 0

        # One lock, one rewrite -- the reason this method exists.
        try:
            with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
                entries = self._read_index(client_sessions_dir) or []
                entries = [e for e in entries if e.get("session_name") not in applied]
                entries.extend(applied.values())
                self._write_index(client_sessions_dir, entries)
        except Exception:
            logger.exception(f"Failed to rewrite session index for CLIENT_{client_id}")
            # Drop the index so the next read rebuilds from disk. Without
            # this the derive pass stops being self-limiting: the session
            # files say "archived" while the stale index keeps serving
            # "active", so every refresh re-derives and rewrites the same N
            # sessions forever, and a full rebuild is the one way back that
            # does not depend on this failing write path.
            with contextlib.suppress(OSError):
                (client_sessions_dir / self.INDEX_FILENAME).unlink()

        logger.info(f"Applied {len(applied)} automatic status updates for CLIENT_{client_id}")
        return len(applied)

    def restore_session_fields(self, session_path: str, fields: dict) -> bool:
        """Put stored fields back exactly: the Browse page's Undo.

        Each key in `fields` is set to its value; a value of None removes the
        key. Nothing is stamped, so `last_updated` and `status_updated_at` end
        up as the caller hands them in -- a session that was Stale before the
        change is Stale again after the Undo.

        Args:
            session_path (str): Full path to session directory
            fields (Dict): The fields to restore; None removes a key

        Returns:
            bool: True if restored successfully

        Raises:
            SessionManagerError: If a status is invalid, the session is not
                found, or the write fails
        """
        status = fields.get("status")
        if status is not None and status not in self.VALID_STATUSES:
            raise SessionManagerError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )

        session_path_obj = Path(session_path)

        with self._locked_session_info(session_path_obj):
            session_info = self.get_session_info(session_path)
            if not session_info:
                raise SessionManagerError(f"Session not found: {session_path}")

            for key, value in fields.items():
                if value is None:
                    session_info.pop(key, None)
                else:
                    session_info[key] = value

            try:
                # Remove computed fields
                session_info.pop("session_path", None)

                atomic_write_json(
                    session_path_obj / "session_info.json", session_info, indent=2
                )
                self._upsert_index_entry(session_path_obj, session_info)
                logger.info(f"Session fields restored: {session_path}")
                return True

            except Exception as e:
                logger.exception("Failed to restore session fields")
                raise SessionManagerError(f"Failed to restore session fields: {e}")


    def update_session_info(self, session_path: str, updates: dict) -> bool:
        """Update session metadata with arbitrary fields.

        Args:
            session_path (str): Full path to session directory
            updates (Dict): Dictionary of fields to update

        Returns:
            bool: True if updated successfully

        Raises:
            SessionManagerError: If update fails
        """
        session_path_obj = Path(session_path)

        with self._locked_session_info(session_path_obj):
            session_info = self.get_session_info(session_path)
            if not session_info:
                raise SessionManagerError(f"Session not found: {session_path}")

            # Apply updates
            session_info.update(updates)
            session_info["last_updated"] = datetime.now().astimezone().isoformat()

            # Save back
            session_info_path = session_path_obj / "session_info.json"

            try:
                # Remove computed fields
                session_info.pop("session_path", None)

                atomic_write_json(session_info_path, session_info, indent=2)

                try:
                    self._upsert_index_entry(session_path_obj, session_info)
                except Exception:
                    logger.exception(f"Failed to update session index for {session_path_obj}")
                logger.info(f"Session info updated: {session_path}")
                return True

            except Exception as e:
                logger.exception("Failed to update session info")
                raise SessionManagerError(f"Failed to update session info: {e}")

    def append_to_session_list(self, session_path: str, field: str, value) -> bool:
        """Atomically append value to a list field in session_info.json.

        update_session_info()'s lock only protects its own read-modify-write;
        a caller that reads the list itself (e.g. via get_session_info),
        appends locally, and then calls update_session_info() with the whole
        new list is still racing every other caller doing the same for a
        DIFFERENT value on the same field (e.g. two packing lists generated
        back to back) -- each reads a list that doesn't yet contain the
        other's addition, and whichever writes last wins. Reading the list
        fresh inside this method's own lock closes that gap.

        Returns:
            bool: True if value was appended, False if it was already present
        """
        session_path_obj = Path(session_path)

        with self._locked_session_info(session_path_obj):
            session_info = self.get_session_info(session_path)
            if not session_info:
                raise SessionManagerError(f"Session not found: {session_path}")

            current_list = session_info.get(field, [])
            if value in current_list:
                return False

            session_info[field] = current_list + [value]
            session_info["last_updated"] = datetime.now().astimezone().isoformat()

            session_info_path = session_path_obj / "session_info.json"
            try:
                session_info.pop("session_path", None)

                atomic_write_json(session_info_path, session_info, indent=2)

                try:
                    self._upsert_index_entry(session_path_obj, session_info)
                except Exception:
                    logger.exception(f"Failed to update session index for {session_path_obj}")
                logger.info(f"Session info updated: appended '{value}' to '{field}'")
                return True

            except Exception as e:
                logger.exception("Failed to update session info")
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
        session_path_obj = Path(session_path).resolve()

        try:
            session_path_obj.relative_to(self.sessions_root.resolve())
        except ValueError:
            raise SessionManagerError(
                f"Refusing to delete path outside sessions root: {session_path}"
            )

        if not session_path_obj.exists():
            logger.warning(f"Session not found for deletion: {session_path}")
            return False

        try:
            import shutil
            shutil.rmtree(session_path_obj)
            logger.info(f"Session deleted: {session_path}")
            return True

        except Exception as e:
            logger.exception("Failed to delete session")
            raise SessionManagerError(f"Failed to delete session: {e}")

    def calculate_session_statistics(self, session_path: str) -> dict:
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
