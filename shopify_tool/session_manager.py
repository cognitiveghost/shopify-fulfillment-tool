"""Session Manager for Shopify Fulfillment Tool — PostgreSQL backend.

Session metadata is stored in the `sessions` table.
Physical files (CSV, XLSX, PDFs, barcodes) remain on the file server.

Public API is identical to the previous JSON-file implementation.

Directory Structure (unchanged, file server):
    Sessions/CLIENT_{ID}/{YYYY-MM-DD_N}/
        ├── input/            source files
        ├── analysis/         analysis_data.json etc.
        ├── packing_lists/    generated xlsx
        ├── stock_exports/
        ├── reference_labels/
        └── barcodes/
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from shopify_tool.db_manager import get_db

logger = logging.getLogger("ShopifyToolLogger")


class SessionManagerError(Exception):
    """Base exception for SessionManager errors."""


class SessionManager:
    """Session lifecycle management backed by PostgreSQL."""

    SESSION_SUBDIRS = [
        "input",
        "analysis",
        "packing_lists",
        "stock_exports",
        "reference_labels",
        "barcodes",
    ]

    VALID_STATUSES = ["active", "completed", "abandoned", "archived"]

    def __init__(self, profile_manager):
        self.profile_manager = profile_manager
        self.sessions_root = profile_manager.get_sessions_root()
        logger.info("SessionManager (PostgreSQL) initialised")

    # ── Session creation ───────────────────────────────────────────────────

    def create_session(self, client_id: str) -> str:
        """Create a new session (DB row + file server dirs).

        Returns:
            Full path string to the session directory.
        """
        client_id = client_id.upper()
        if not self.profile_manager.client_exists(client_id):
            raise SessionManagerError(f"Client does not exist: CLIENT_{client_id}")

        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"
        client_sessions_dir.mkdir(parents=True, exist_ok=True)

        session_name = self._generate_unique_session_name(client_id)
        session_path = client_sessions_dir / session_name

        try:
            session_path.mkdir(parents=True)
            for subdir in self.SESSION_SUBDIRS:
                (session_path / subdir).mkdir()

            now = datetime.now()
            pc_name = os.environ.get("COMPUTERNAME", "Unknown")

            get_db().execute(
                """
                INSERT INTO sessions
                    (client_id, session_name, status, pc_name,
                     analysis_completed, created_at, last_modified)
                VALUES (%s,%s,'active',%s, false, %s, %s)
                """,
                (client_id, session_name, pc_name, now, now),
            )

            logger.info("Session created: CLIENT_%s/%s", client_id, session_name)
            return str(session_path)

        except Exception as e:
            logger.error("Failed to create session: %s", e)
            if session_path.exists():
                shutil.rmtree(session_path, ignore_errors=True)
            raise SessionManagerError(f"Failed to create session: {e}")

    def _generate_unique_session_name(self, client_id: str) -> str:
        """Return next available {YYYY-MM-DD_N} name for today (queries DB)."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = get_db().fetchone(
            "SELECT COALESCE(MAX(CAST(split_part(session_name, '_', 2) AS INTEGER)), 0) AS max_n "
            "FROM sessions "
            "WHERE client_id = %s AND session_name LIKE %s",
            (client_id, f"{today}_%"),
        )
        next_n = (row["max_n"] if row else 0) + 1
        return f"{today}_{next_n}"

    # ── Path helpers (file server) — unchanged ─────────────────────────────

    def get_session_path(self, client_id: str, session_name: str) -> Path:
        return self.sessions_root / f"CLIENT_{client_id.upper()}" / session_name

    def get_session_subdirectory(self, session_path: str, subdir_name: str) -> Path:
        if subdir_name not in self.SESSION_SUBDIRS:
            raise SessionManagerError(
                f"Invalid subdirectory: {subdir_name}. Must be one of {self.SESSION_SUBDIRS}"
            )
        subdir_path = Path(session_path) / subdir_name
        if not subdir_path.exists():
            raise SessionManagerError(f"Subdirectory not found: {subdir_path}")
        return subdir_path

    def get_input_dir(self, session_path: str) -> Path:
        return self.get_session_subdirectory(session_path, "input")

    def get_analysis_dir(self, session_path: str) -> Path:
        return self.get_session_subdirectory(session_path, "analysis")

    def get_packing_lists_dir(self, session_path: str) -> Path:
        return self.get_session_subdirectory(session_path, "packing_lists")

    def get_stock_exports_dir(self, session_path: str) -> Path:
        return self.get_session_subdirectory(session_path, "stock_exports")

    def get_reference_labels_dir(self, session_path: str) -> Path:
        return self.get_session_subdirectory(session_path, "reference_labels")

    def get_barcodes_dir(self, session_path: str) -> Path:
        return Path(session_path) / "barcodes"

    def get_packing_list_barcode_dir(self, session_path: str, packing_list_name: str) -> Path:
        return self.get_barcodes_dir(session_path) / packing_list_name

    def get_barcode_history_file(self, session_path: str, packing_list_name: str) -> Path:
        return self.get_packing_list_barcode_dir(session_path, packing_list_name) / "barcode_history.json"

    # ── Session queries ────────────────────────────────────────────────────

    def list_client_sessions(
        self, client_id: str, status_filter: Optional[str] = None
    ) -> List[Dict]:
        """Return list of session dicts, newest first."""
        client_id = client_id.upper()
        if status_filter:
            rows = get_db().fetchall(
                "SELECT * FROM sessions WHERE client_id = %s AND status = %s "
                "ORDER BY created_at DESC",
                (client_id, status_filter),
            )
        else:
            rows = get_db().fetchall(
                "SELECT * FROM sessions WHERE client_id = %s ORDER BY created_at DESC",
                (client_id,),
            )
        infos = [self._row_to_info(r) for r in rows]
        for info in infos:
            info["session_path"] = str(
                self.sessions_root / f"CLIENT_{client_id}" / info["session_name"]
            )
        return infos

    def get_session_info(self, session_path: str) -> Optional[Dict]:
        """Load session info from DB (identified by path)."""
        session_path_obj = Path(session_path)
        session_name = session_path_obj.name
        # Infer client_id from path (…/CLIENT_M/2026-01-01_1)
        parent_name = session_path_obj.parent.name  # e.g. CLIENT_M
        client_id = parent_name.replace("CLIENT_", "") if parent_name.startswith("CLIENT_") else None

        if client_id:
            row = get_db().fetchone(
                "SELECT * FROM sessions WHERE client_id = %s AND session_name = %s",
                (client_id, session_name),
            )
        else:
            row = None

        if row is None:
            # Fallback: try reading the legacy session_info.json if it exists on disk
            session_info_path = session_path_obj / "session_info.json"
            if session_info_path.exists():
                try:
                    with open(session_info_path, "r", encoding="utf-8") as f:
                        info = json.load(f)
                    info["session_path"] = session_path
                    return info
                except Exception:
                    pass
            logger.warning("Session not found in DB: %s", session_path)
            return None

        info = self._row_to_info(row)
        info["session_path"] = session_path
        return info

    def session_exists(self, client_id: str, session_name: str) -> bool:
        row = get_db().fetchone(
            "SELECT 1 FROM sessions WHERE client_id = %s AND session_name = %s",
            (client_id.upper(), session_name),
        )
        return row is not None

    # ── Session updates ────────────────────────────────────────────────────

    def update_session_status(self, session_path: str, status: str) -> bool:
        if status not in self.VALID_STATUSES:
            raise SessionManagerError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )
        session_path_obj = Path(session_path)
        session_name = session_path_obj.name
        client_id = session_path_obj.parent.name.replace("CLIENT_", "")

        try:
            row = get_db().fetchone(
                "UPDATE sessions SET status = %s, status_updated_at = now(), "
                "last_modified = now() "
                "WHERE client_id = %s AND session_name = %s RETURNING id",
                (status, client_id, session_name),
            )
            if row is None:
                raise SessionManagerError(f"Session not found: {session_path}")
            logger.info("Session status → '%s': %s", status, session_path)
            return True
        except SessionManagerError:
            raise
        except Exception as e:
            logger.error("update_session_status failed: %s", e)
            raise SessionManagerError(f"Failed to update session status: {e}")

    def update_session_info(self, session_path: str, updates: Dict) -> bool:
        """Apply arbitrary field updates to the sessions row."""
        session_path_obj = Path(session_path)
        session_name = session_path_obj.name
        client_id = session_path_obj.parent.name.replace("CLIENT_", "")

        # Map dict keys to DB columns
        col_map = {
            "orders_file": "orders_file",
            "stock_file": "stock_file",
            "analysis_completed": "analysis_completed",
            "packing_lists_generated": "packing_lists_generated",
            "stock_exports_generated": "stock_exports_generated",
            "comments": "comments",
            "status": "status",
            # statistics sub-fields
            "total_orders": "total_orders",
            "total_items": "total_items",
            "packing_lists_count": "packing_lists_count",
        }

        # Flatten statistics if present
        flat = dict(updates)
        if "statistics" in flat:
            stats = flat.pop("statistics")
            flat.update({k: v for k, v in stats.items() if k in col_map})
        # Handle packing_lists within statistics
        if "packing_lists" in flat:
            flat["packing_list_names"] = flat.pop("packing_lists")

        sets, vals = [], []
        for key, value in flat.items():
            col = col_map.get(key)
            if col:
                sets.append(f"{col} = %s")
                vals.append(value)
        if not sets:
            return True

        sets.append("last_modified = now()")
        vals.extend([client_id, session_name])

        try:
            row = get_db().fetchone(
                f"UPDATE sessions SET {', '.join(sets)} "
                "WHERE client_id = %s AND session_name = %s RETURNING id",
                vals,
            )
            if row is None:
                raise SessionManagerError(f"Session not found: {session_path}")
            logger.info("Session info updated: %s", session_path)
            return True
        except SessionManagerError:
            raise
        except Exception as e:
            logger.error("update_session_info failed: %s", e)
            raise SessionManagerError(f"Failed to update session info: {e}")

    def delete_session(self, session_path: str) -> bool:
        """Delete session from DB and remove files from server."""
        session_path_obj = Path(session_path)
        session_name = session_path_obj.name
        client_id = session_path_obj.parent.name.replace("CLIENT_", "")

        try:
            row = get_db().fetchone(
                "DELETE FROM sessions WHERE client_id = %s AND session_name = %s RETURNING id",
                (client_id, session_name),
            )
            if row is None:
                logger.warning("Session not found for deletion: %s", session_path)
                return False
            if session_path_obj.exists():
                shutil.rmtree(session_path_obj)
            logger.info("Session deleted: %s", session_path)
            return True
        except Exception as e:
            logger.error("delete_session failed: %s", e)
            raise SessionManagerError(f"Failed to delete session: {e}")

    # ── Statistics (still file-based — reads analysis_data.json + scans dirs) ─

    def calculate_session_statistics(self, session_path: str) -> Dict:
        session_path_obj = Path(session_path)
        stats = {
            "total_orders": 0,
            "total_items": 0,
            "packing_lists_count": 0,
            "packing_lists": [],
        }
        try:
            analysis_data_path = session_path_obj / "analysis" / "analysis_data.json"
            if analysis_data_path.exists():
                with open(analysis_data_path, "r", encoding="utf-8") as f:
                    analysis_data = json.load(f)
                orders = analysis_data.get("orders", [])
                stats["total_orders"] = len(orders)
                stats["total_items"] = sum(
                    len(o.get("items", [])) for o in orders
                )

            pl_dir = session_path_obj / "packing_lists"
            if pl_dir.exists():
                pl_files = [
                    f.stem for f in pl_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in (".xlsx", ".xls")
                ]
                stats["packing_lists"] = pl_files
                stats["packing_lists_count"] = len(pl_files)
        except Exception as e:
            logger.warning("calculate_session_statistics error: %s", e)
        return stats

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _row_to_info(row: Dict) -> Dict:
        """Convert a DB row dict to the legacy session_info dict shape."""
        created_at = row.get("created_at")
        last_modified = row.get("last_modified")
        status_updated_at = row.get("status_updated_at")
        return {
            "created_by_tool": "shopify",
            "created_at": created_at.isoformat() if created_at else None,
            "client_id": row["client_id"],
            "session_name": row["session_name"],
            "status": row.get("status", "active"),
            "pc_name": row.get("pc_name", "Unknown"),
            "orders_file": row.get("orders_file"),
            "stock_file": row.get("stock_file"),
            "analysis_completed": bool(row.get("analysis_completed", False)),
            "packing_lists_generated": list(row.get("packing_lists_generated") or []),
            "stock_exports_generated": list(row.get("stock_exports_generated") or []),
            "statistics": {
                "total_orders": row.get("total_orders", 0),
                "total_items": row.get("total_items", 0),
                "packing_lists_count": row.get("packing_lists_count", 0),
                "packing_lists": list(row.get("packing_list_names") or []),
            },
            "comments": row.get("comments", ""),
            "last_modified": last_modified.isoformat() if last_modified else None,
            "status_updated_at": status_updated_at.isoformat() if status_updated_at else None,
        }
