"""Groups Manager for Shopify Fulfillment Tool — PostgreSQL backend.

Groups allow categorising clients into named collections for navigation.
All persistence is in the `groups` and `client_ui_settings` tables.
Public API is identical to the previous JSON-file implementation.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from shopify_tool.db_manager import get_db

logger = logging.getLogger("ShopifyToolLogger")


class GroupsManagerError(Exception):
    """Base exception for GroupsManager errors."""


class GroupsManager:
    """CRUD operations for client groups backed by PostgreSQL."""

    # Special virtual group IDs — never stored in the DB, synthesised on list_groups()
    _SPECIAL_GROUPS = {
        "pinned": {
            "id": "pinned",
            "name": "Pinned",
            "color": "#FFC107",
            "display_order": -1,
            "collapsible": False,
        },
        "all": {
            "id": "all",
            "name": "All Clients",
            "color": "#9E9E9E",
            "display_order": 999,
            "collapsible": True,
        },
    }

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.clients_dir = self.base_path / "Clients"
        self.clients_dir.mkdir(parents=True, exist_ok=True)
        # No file to initialise — DB is the source of truth.
        logger.info("GroupsManager (PostgreSQL) initialised")

    # ── Read ───────────────────────────────────────────────────────────────

    def load_groups(self) -> Dict[str, Any]:
        """Return groups dict in the legacy shape (for compatibility)."""
        rows = get_db().fetchall(
            "SELECT id, name, color, display_order, collapsible, "
            "       created_at, updated_at "
            "FROM groups ORDER BY display_order"
        )
        groups = []
        for r in rows:
            groups.append({
                "id": r["id"],
                "name": r["name"],
                "color": r["color"],
                "display_order": r["display_order"],
                "collapsible": r["collapsible"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            })
        return {
            "version": "1.0",
            "groups": groups,
            "special_groups": {k: dict(v) for k, v in self._SPECIAL_GROUPS.items()},
            "last_updated": datetime.now().isoformat(),
        }

    def list_groups(self) -> List[Dict]:
        """Return all user-defined groups sorted by display_order."""
        return self.load_groups()["groups"]

    def get_group(self, group_id: str) -> Optional[Dict]:
        row = get_db().fetchone(
            "SELECT id, name, color, display_order, collapsible, created_at, updated_at "
            "FROM groups WHERE id = %s",
            (group_id,),
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "display_order": row["display_order"],
            "collapsible": row["collapsible"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    def get_clients_in_group(self, group_id: str, profile_manager) -> List[str]:
        """Return client IDs (without CLIENT_ prefix) assigned to group_id."""
        rows = get_db().fetchall(
            "SELECT client_id FROM client_ui_settings WHERE group_id = %s",
            (group_id,),
        )
        return [r["client_id"] for r in rows]

    # ── Write ──────────────────────────────────────────────────────────────

    def save_groups(self, groups_data: Dict) -> bool:
        """Sync the full groups list from the legacy dict shape back into the DB."""
        db = get_db()
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    for g in groups_data.get("groups", []):
                        cur.execute(
                            """
                            INSERT INTO groups
                                (id, name, color, display_order, collapsible, updated_at)
                            VALUES (%s,%s,%s,%s,%s, now())
                            ON CONFLICT (id) DO UPDATE SET
                                name          = EXCLUDED.name,
                                color         = EXCLUDED.color,
                                display_order = EXCLUDED.display_order,
                                collapsible   = EXCLUDED.collapsible,
                                updated_at    = now()
                            """,
                            (g["id"], g["name"], g.get("color", "#2196F3"),
                             g.get("display_order", 0), g.get("collapsible", True)),
                        )
            return True
        except Exception as e:
            logger.error("save_groups failed: %s", e)
            raise GroupsManagerError(f"Failed to save groups: {e}")

    def create_group(self, name: str, color: str = "#2196F3") -> str:
        """Create a new group, return its UUID string.

        Raises GroupsManagerError if name is empty or already exists (case-insensitive).
        """
        if not name or not name.strip():
            raise GroupsManagerError("Group name cannot be empty")
        name = name.strip()

        # Uniqueness check
        existing = get_db().fetchone(
            "SELECT id FROM groups WHERE lower(name) = lower(%s)", (name,)
        )
        if existing:
            raise GroupsManagerError(f"Group '{name}' already exists")

        # Auto display_order = max + 1
        row = get_db().fetchone("SELECT COALESCE(MAX(display_order), 0) AS mx FROM groups")
        display_order = (row["mx"] if row else 0) + 1

        group_id = str(uuid.uuid4())
        get_db().execute(
            "INSERT INTO groups (id, name, color, display_order) VALUES (%s,%s,%s,%s)",
            (group_id, name, color, display_order),
        )
        logger.info("Group created: %s (%s)", name, group_id)
        return group_id

    def update_group(
        self,
        group_id: str,
        name: str = None,
        color: str = None,
    ) -> bool:
        if group_id in self._SPECIAL_GROUPS:
            raise GroupsManagerError(f"Cannot modify special group '{group_id}'")

        if name is not None:
            conflict = get_db().fetchone(
                "SELECT id FROM groups WHERE lower(name) = lower(%s) AND id != %s",
                (name, group_id),
            )
            if conflict:
                raise GroupsManagerError(f"Group name '{name}' already exists")

        # Build dynamic SET clause
        fields, values = [], []
        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if color is not None:
            fields.append("color = %s")
            values.append(color)
        if not fields:
            return True  # nothing to update

        fields.append("updated_at = now()")
        values.append(group_id)
        row = get_db().fetchone(
            f"UPDATE groups SET {', '.join(fields)} WHERE id = %s RETURNING id", values
        )
        if row is None:
            raise GroupsManagerError(f"Group not found: {group_id}")
        logger.info("Group updated: %s", group_id)
        return True

    def delete_group(self, group_id: str, profile_manager=None) -> bool:
        if group_id in self._SPECIAL_GROUPS:
            raise GroupsManagerError(f"Cannot delete special group '{group_id}'")

        if not self.get_group(group_id):
            raise GroupsManagerError(f"Group not found: {group_id}")

        db = get_db()
        with db.conn() as conn:
            with conn.cursor() as cur:
                # Unassign all clients from this group
                cur.execute(
                    "UPDATE client_ui_settings SET group_id = NULL WHERE group_id = %s",
                    (group_id,),
                )
                cur.execute("DELETE FROM groups WHERE id = %s", (group_id,))

        logger.info("Group deleted: %s", group_id)
        return True
