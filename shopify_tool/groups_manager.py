"""Groups Manager for Shopify Fulfillment Tool.

This module provides management of client groups for enhanced profile organization.
Groups allow categorizing clients into custom collections for easier navigation.

Key Features:
    - CRUD operations for custom groups
    - Special groups: "pinned" and "all" (immutable)
    - File locking for safe concurrent access
    - Automatic backups before destructive operations
    - UUID-based group identification
"""

import contextlib
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ShopifyToolLogger")


# Custom Exception
class GroupsManagerError(Exception):
    """Base exception for GroupsManager errors."""
    pass


class GroupsManager:
    """Manages client groups configuration.

    This class handles:
    - Loading and saving groups configuration
    - CRUD operations for custom groups
    - File locking for concurrent write protection
    - Automatic backup creation
    - Coordination with ProfileManager for client unassignment

    Attributes:
        base_path (Path): Root path on file server
        groups_path (Path): Path to groups.json file
    """

    def __init__(self, base_path: str):
        """Initialize GroupsManager with base path to fulfillment directory.

        Args:
            base_path: Base path to fulfillment directory
        """
        self.base_path = Path(base_path)
        self.clients_dir = self.base_path / "Clients"
        self.groups_path = self.clients_dir / "groups.json"

        # Ensure Clients directory exists
        self.clients_dir.mkdir(parents=True, exist_ok=True)

        # Initialize groups file
        # Always call load_groups to validate and handle corruption
        groups_data = self.load_groups()

        # If we got defaults back and file doesn't exist, save it
        if not self.groups_path.exists():
            self.save_groups(groups_data)

    def _create_default_groups(self) -> Dict[str, Any]:
        """Create default groups configuration with special groups.

        Returns:
            Dict containing default groups structure
        """
        return {
            "version": "1.0",
            "groups": [],
            "special_groups": {
                "pinned": {
                    "display_order": -1,
                    "name": "Pinned",
                    "color": "#FFC107",
                    "collapsible": False
                },
                "all": {
                    "display_order": 999,
                    "name": "All Clients",
                    "color": "#9E9E9E",
                    "collapsible": True
                }
            }
        }

    def load_groups(self) -> Dict[str, Any]:
        """Load groups configuration with corruption recovery.

        Returns:
            Dict containing groups data with structure:
            {
                "version": "1.0",
                "groups": [...],
                "special_groups": {...}
            }

        Note:
            Returns defaults if file doesn't exist or is corrupted
        """
        if not self.groups_path.exists():
            logger.info("groups.json not found, creating with defaults")
            return self._create_default_groups()

        try:
            with open(self.groups_path, 'r', encoding='utf-8') as f:
                groups_data = json.load(f)

            # Validate structure
            if "version" not in groups_data or "groups" not in groups_data:
                logger.warning("Invalid groups.json structure, recreating")
                backup_path = self.groups_path.with_suffix('.corrupted.bak')
                shutil.copy2(self.groups_path, backup_path)
                logger.info(f"Corrupted file backed up to {backup_path}")
                return self._create_default_groups()

            return groups_data

        except json.JSONDecodeError as e:
            logger.error(f"Corrupted JSON in groups.json: {e}")
            backup_path = self.groups_path.with_suffix('.corrupted.bak')
            shutil.copy2(self.groups_path, backup_path)
            logger.info(f"Corrupted file backed up to {backup_path}")
            return self._create_default_groups()
        except Exception as e:
            logger.error(f"Unexpected error loading groups: {e}", exc_info=True)
            return self._create_default_groups()

    def save_groups(self, groups_data: Dict[str, Any]) -> bool:
        """Save groups configuration with file locking and backup.

        Args:
            groups_data: Groups configuration dict

        Returns:
            bool: True if saved successfully

        Raises:
            GroupsManagerError: If save fails after retries
        """
        # Create backup before saving
        if self.groups_path.exists():
            self._create_backup()

        # Update timestamp
        groups_data["last_updated"] = datetime.now().isoformat()

        max_retries = 10
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                # Use platform-specific file locking
                if os.name == 'nt':  # Windows
                    success = self._save_with_windows_lock(self.groups_path, groups_data)
                else:  # Unix-like
                    success = self._save_with_unix_lock(self.groups_path, groups_data)

                if success:
                    logger.info(f"Groups configuration saved successfully (attempt {attempt + 1}/{max_retries})")
                    return True
                else:
                    # File lock failed, retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Save failed (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {retry_delay}s: File is locked"
                        )
                        time.sleep(retry_delay)

            except (IOError, OSError) as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Save failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    time.sleep(retry_delay)
                else:
                    error_msg = f"Failed to save groups configuration after {max_retries} attempts: {e}"
                    logger.error(error_msg)
                    raise GroupsManagerError(error_msg)

        # If we get here, all retries failed
        error_msg = f"Failed to save groups configuration after {max_retries} attempts"
        logger.error(error_msg)
        raise GroupsManagerError(error_msg)

    def _save_with_windows_lock(self, file_path: Path, data: Dict) -> bool:
        """Save file with Windows file locking (locks entire file).

        Args:
            file_path: Path to file
            data: Data to save

        Returns:
            bool: True if saved successfully
        """
        import msvcrt

        # Write to temp file first
        temp_path = file_path.with_suffix('.tmp')

        try:
            # Pre-serialize to know exact size
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            file_size = len(json_str.encode('utf-8'))

            with open(temp_path, 'w', encoding='utf-8') as f:
                # Try to acquire exclusive lock for entire file
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, file_size)
                except IOError:
                    return False

                try:
                    # Write pre-serialized JSON
                    f.write(json_str)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                finally:
                    # Unlock with same size - must seek to start first
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, file_size)

            # Atomic move
            shutil.move(str(temp_path), str(file_path))
            return True

        except Exception as e:
            logger.error(f"Failed to save with Windows lock: {e}", exc_info=True)
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _save_with_unix_lock(self, file_path: Path, data: Dict) -> bool:
        """Save file with Unix file locking.

        Args:
            file_path: Path to file
            data: Data to save

        Returns:
            bool: True if saved successfully
        """
        import fcntl

        # Write to temp file first
        temp_path = file_path.with_suffix('.tmp')

        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                # Try to acquire exclusive lock
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    return False

                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Atomic move
            shutil.move(str(temp_path), str(file_path))
            return True

        except Exception as e:
            logger.error(f"Failed to save with Unix lock: {e}", exc_info=True)
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _create_backup(self) -> None:
        """Create backup of groups.json before destructive operations.

        Keeps last 10 backups.
        """
        if not self.groups_path.exists():
            return

        backups_dir = self.clients_dir / "backups"
        backups_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backups_dir / f"groups_{timestamp}.json"

        try:
            shutil.copy2(self.groups_path, backup_path)
            logger.info(f"Backup created: {backup_path.name}")

            # Keep only last 10 backups
            backups = sorted(backups_dir.glob("groups_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old_backup in backups[10:]:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup.name}")

        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

    @contextlib.contextmanager
    def _locked_groups_rmw(self):
        """Blocking exclusive lock spanning a groups.json load-modify-save cycle.

        save_groups() only locks around its own write; without this, two
        near-simultaneous create/update/delete calls can each load the same
        stale snapshot and the second save silently clobbers the first.
        """
        lock_path = self.groups_path.with_suffix(".lock")
        lock_file = open(lock_path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()

    @staticmethod
    def _name_collides_with_special_group(groups_data: Dict[str, Any], name: str) -> bool:
        special_groups = groups_data.get("special_groups", {})
        return any(
            special.get("name", "").lower() == name.lower()
            for special in special_groups.values()
        )

    def create_group(self, name: str, color: str = "#2196F3") -> str:
        """Create new group.

        Args:
            name: Group name (must be unique)
            color: Hex color code (default: Material Blue)

        Returns:
            str: Generated group UUID

        Raises:
            GroupsManagerError: If name is empty or duplicate
        """
        if not name or not name.strip():
            raise GroupsManagerError("Group name cannot be empty")

        name = name.strip()

        with self._locked_groups_rmw():
            # Load current groups
            groups_data = self.load_groups()

            # Check for duplicate name (including built-in special groups)
            if self._name_collides_with_special_group(groups_data, name):
                raise GroupsManagerError(f"Group with name '{name}' already exists")
            for group in groups_data.get("groups", []):
                if group.get("name", "").lower() == name.lower():
                    raise GroupsManagerError(f"Group with name '{name}' already exists")

            # Generate UUID
            group_id = str(uuid.uuid4())

            # Calculate display_order (append to end)
            max_order = -1
            for group in groups_data.get("groups", []):
                order = group.get("display_order", 0)
                if order > max_order:
                    max_order = order
            display_order = max_order + 1

            # Create new group
            new_group = {
                "id": group_id,
                "name": name,
                "color": color,
                "display_order": display_order,
                "created_at": datetime.now().isoformat()
            }

            groups_data["groups"].append(new_group)

            # Save
            self.save_groups(groups_data)
            logger.info(f"Group created: {name} (ID: {group_id})")

            return group_id

    def update_group(self, group_id: str, name: str = None, color: str = None) -> bool:
        """Update existing group.

        Args:
            group_id: Group UUID
            name: New name (optional, must be unique)
            color: New color (optional, hex code)

        Returns:
            bool: True if updated successfully

        Raises:
            GroupsManagerError: If group doesn't exist or name is duplicate
        """
        with self._locked_groups_rmw():
            # Load current groups
            groups_data = self.load_groups()

            # Find group
            target_group = None
            for group in groups_data.get("groups", []):
                if group.get("id") == group_id:
                    target_group = group
                    break

            if target_group is None:
                raise GroupsManagerError(f"Group with ID '{group_id}' not found")

            # Check for duplicate name if updating name
            if name is not None:
                name = name.strip()
                if not name:
                    raise GroupsManagerError("Group name cannot be empty")

                if self._name_collides_with_special_group(groups_data, name):
                    raise GroupsManagerError(f"Group with name '{name}' already exists")
                for group in groups_data.get("groups", []):
                    if group.get("id") != group_id and group.get("name", "").lower() == name.lower():
                        raise GroupsManagerError(f"Group with name '{name}' already exists")

                target_group["name"] = name

            # Update color if provided
            if color is not None:
                target_group["color"] = color

            # Save
            self.save_groups(groups_data)
            logger.info(f"Group updated: {group_id}")

            return True

    def delete_group(self, group_id: str, profile_manager = None) -> bool:
        """Delete group and unassign all clients.

        Args:
            group_id: Group UUID to delete
            profile_manager: Optional ProfileManager for client updates.
                           If None, only deletes group (useful for testing).

        Returns:
            bool: True if deleted successfully

        Raises:
            GroupsManagerError: If special group or doesn't exist
        """
        # Validate not special group
        if group_id in ["pinned", "all"]:
            raise GroupsManagerError(f"Cannot delete special group: {group_id}")

        with self._locked_groups_rmw():
            # Load current groups
            groups_data = self.load_groups()

            # Check if group exists
            group_exists = any(group.get("id") == group_id for group in groups_data.get("groups", []))
            if not group_exists:
                raise GroupsManagerError(f"Group with ID '{group_id}' not found")

            # Unassign clients from this group
            if profile_manager:
                clients_in_group = self.get_clients_in_group(group_id, profile_manager)

                for client_id in clients_in_group:
                    try:
                        config = profile_manager.load_client_config(client_id)
                        if config and "ui_settings" in config:
                            if config["ui_settings"].get("group_id") == group_id:
                                config["ui_settings"]["group_id"] = None
                                profile_manager.save_client_config(client_id, config)
                                logger.info(f"Unassigned CLIENT_{client_id} from group {group_id}")
                    except Exception as e:
                        logger.error(f"Failed to unassign CLIENT_{client_id}: {e}")
                        # Continue with other clients

            # Remove group from groups.json
            groups_data["groups"] = [g for g in groups_data["groups"] if g.get("id") != group_id]

            # Save
            self.save_groups(groups_data)
            logger.info(f"Group deleted: {group_id}")

            return True

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get group by ID.

        Args:
            group_id: Group UUID

        Returns:
            Dict with group data or None if not found
        """
        groups_data = self.load_groups()

        for group in groups_data.get("groups", []):
            if group.get("id") == group_id:
                return group

        return None

    def list_groups(self) -> List[Dict[str, Any]]:
        """List all groups sorted by display_order.

        Returns:
            List of group dicts, sorted by display_order (ascending)
        """
        groups_data = self.load_groups()
        groups = groups_data.get("groups", [])

        # Sort by display_order
        sorted_groups = sorted(groups, key=lambda g: g.get("display_order", 0))

        return sorted_groups

    def get_clients_in_group(self, group_id: str, profile_manager) -> List[str]:
        """Get list of client IDs assigned to a group.

        Args:
            group_id: Group UUID
            profile_manager: ProfileManager instance for scanning clients

        Returns:
            List of client IDs (e.g., ["M", "ABC"])
        """
        clients_in_group = []
        all_clients = profile_manager.list_clients()

        for client_id in all_clients:
            try:
                config = profile_manager.load_client_config(client_id)
                if config and "ui_settings" in config:
                    if config["ui_settings"].get("group_id") == group_id:
                        clients_in_group.append(client_id)
            except Exception as e:
                logger.warning(f"Failed to check group for CLIENT_{client_id}: {e}")
                continue

        return clients_in_group
