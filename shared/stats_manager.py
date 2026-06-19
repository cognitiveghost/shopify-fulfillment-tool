"""Unified Statistics Manager — PostgreSQL backend.

Replaces global_stats.json with direct inserts/queries against
analysis_events, packing_events, label_print_events tables.

Public API is identical to the previous JSON-file implementation.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shopify_tool.db_manager import get_db

logger = logging.getLogger("ShopifyToolLogger")


class StatsManagerError(Exception):
    """Base exception for StatsManager errors."""


FileLockError = StatsManagerError  # alias — DB backend has no file locks


class StatsManager:
    """Statistics tracking backed by PostgreSQL event tables."""

    def __init__(self, base_path: str, max_retries: int = 5, retry_delay: float = 0.1):
        # base_path kept for API compatibility; not used for storage any more
        self.base_path = Path(base_path)
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        logger.info("StatsManager (PostgreSQL) initialised")

    # ── Write ──────────────────────────────────────────────────────────────

    def record_analysis(
        self,
        client_id: str,
        session_id: str,
        orders_count: int,
        metadata: Optional[Dict] = None,
    ) -> None:
        get_db().execute(
            "INSERT INTO analysis_events (client_id, session_name, orders_count, metadata) "
            "VALUES (%s,%s,%s,%s)",
            (client_id, session_id, orders_count, json.dumps(metadata or {})),
        )
        logger.debug("Recorded analysis: client=%s session=%s orders=%d", client_id, session_id, orders_count)

    def record_packing(
        self,
        client_id: str,
        session_id: str,
        worker_id: Optional[str],
        orders_count: int,
        items_count: int,
        metadata: Optional[Dict] = None,
    ) -> None:
        get_db().execute(
            "INSERT INTO packing_events "
            "(client_id, session_name, worker_id, orders_count, items_count, metadata) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (client_id, session_id, worker_id, orders_count, items_count,
             json.dumps(metadata or {})),
        )
        logger.debug("Recorded packing: client=%s session=%s orders=%d", client_id, session_id, orders_count)

    def record_label_print(self, client_id: str, sku: str, copies: int) -> None:
        get_db().execute(
            "INSERT INTO label_print_events (client_id, sku, copies) VALUES (%s,%s,%s)",
            (client_id, sku, copies),
        )

    # ── Global aggregates ──────────────────────────────────────────────────

    def get_global_stats(self) -> Dict[str, Any]:
        db = get_db()
        a = db.fetchone("SELECT COALESCE(SUM(orders_count), 0) AS total FROM analysis_events")
        p = db.fetchone("SELECT COALESCE(SUM(orders_count), 0) AS total FROM packing_events")
        s = db.fetchone("SELECT COUNT(DISTINCT session_name || client_id) AS total FROM packing_events")
        lp = db.fetchone("SELECT COALESCE(SUM(copies), 0) AS total FROM label_print_events")
        return {
            "total_orders_analyzed": int(a["total"]) if a else 0,
            "total_orders_packed": int(p["total"]) if p else 0,
            "total_sessions": int(s["total"]) if s else 0,
            "total_labels_printed": int(lp["total"]) if lp else 0,
            "last_updated": datetime.now().isoformat(),
        }

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        db = get_db()
        a = db.fetchone(
            "SELECT COALESCE(SUM(orders_count), 0) AS total FROM analysis_events WHERE client_id = %s",
            (client_id,),
        )
        p = db.fetchone(
            "SELECT COALESCE(SUM(orders_count), 0) AS total, "
            "       COUNT(DISTINCT session_name) AS sessions "
            "FROM packing_events WHERE client_id = %s",
            (client_id,),
        )
        lp = db.fetchone(
            "SELECT COALESCE(SUM(copies), 0) AS total FROM label_print_events WHERE client_id = %s",
            (client_id,),
        )
        return {
            "orders_analyzed": int(a["total"]) if a else 0,
            "orders_packed": int(p["total"]) if p else 0,
            "sessions": int(p["sessions"]) if p else 0,
            "labels_printed": int(lp["total"]) if lp else 0,
        }

    def get_all_clients_stats(self) -> Dict[str, Dict]:
        a_rows = get_db().fetchall(
            "SELECT client_id, SUM(orders_count) AS orders_analyzed "
            "FROM analysis_events GROUP BY client_id"
        )
        p_rows = get_db().fetchall(
            "SELECT client_id, SUM(orders_count) AS orders_packed, "
            "       COUNT(DISTINCT session_name) AS sessions "
            "FROM packing_events GROUP BY client_id"
        )
        lp_rows = get_db().fetchall(
            "SELECT client_id, SUM(copies) AS labels_printed "
            "FROM label_print_events GROUP BY client_id"
        )
        result: Dict[str, Dict] = {}
        for r in a_rows:
            result.setdefault(r["client_id"], {})["orders_analyzed"] = int(r["orders_analyzed"])
        for r in p_rows:
            result.setdefault(r["client_id"], {}).update({
                "orders_packed": int(r["orders_packed"]),
                "sessions": int(r["sessions"]),
            })
        for r in lp_rows:
            result.setdefault(r["client_id"], {})["labels_printed"] = int(r["labels_printed"])
        # Fill zeros for missing keys
        for v in result.values():
            v.setdefault("orders_analyzed", 0)
            v.setdefault("orders_packed", 0)
            v.setdefault("sessions", 0)
            v.setdefault("labels_printed", 0)
        return result

    # ── History queries ────────────────────────────────────────────────────

    def get_analysis_history(
        self, client_id: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict]:
        sql = "SELECT client_id, session_name AS session_id, orders_count, metadata, created_at AS timestamp FROM analysis_events"
        params: list = []
        if client_id:
            sql += " WHERE client_id = %s"
            params.append(client_id)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = get_db().fetchall(sql, params or None)
        return [self._fmt_event(r) for r in rows]

    def get_packing_history(
        self,
        client_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        clauses, params = [], []
        if client_id:
            clauses.append("client_id = %s")
            params.append(client_id)
        if worker_id:
            clauses.append("worker_id = %s")
            params.append(worker_id)
        sql = (
            "SELECT client_id, session_name AS session_id, worker_id, "
            "       orders_count, items_count, metadata, created_at AS timestamp "
            "FROM packing_events"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = get_db().fetchall(sql, params or None)
        return [self._fmt_event(r) for r in rows]

    def get_label_print_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        clauses, params = [], []
        if client_id:
            clauses.append("client_id = %s")
            params.append(client_id)
        if start_date:
            clauses.append("created_at >= %s")
            params.append(start_date)
        if end_date:
            # extend to end of day like old implementation
            end_eod = end_date.replace(hour=23, minute=59, second=59)
            clauses.append("created_at <= %s")
            params.append(end_eod)
        sql = "SELECT client_id, sku, copies, created_at AS timestamp FROM label_print_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = get_db().fetchall(sql, params or None)
        return [self._fmt_event(r) for r in rows]

    def get_label_stats(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        where = "WHERE client_id = %s" if client_id else ""
        params = (client_id,) if client_id else None

        total_row = get_db().fetchone(
            f"SELECT COALESCE(SUM(copies), 0) AS total FROM label_print_events {where}",
            params,
        )
        sku_rows = get_db().fetchall(
            f"SELECT sku, SUM(copies) AS cnt FROM label_print_events {where} "
            "GROUP BY sku ORDER BY cnt DESC",
            params,
        )
        total = int(total_row["total"]) if total_row else 0
        sku_breakdown = {r["sku"]: int(r["cnt"]) for r in sku_rows}
        top_sku = sku_rows[0]["sku"] if sku_rows else None
        return {
            "total_labels_printed": total,
            "unique_skus": len(sku_breakdown),
            "top_sku": top_sku,
            "sku_breakdown": sku_breakdown,
        }

    # ── Misc ───────────────────────────────────────────────────────────────

    def reset_stats(self) -> None:
        """WARNING: Deletes all historical event data."""
        db = get_db()
        db.execute("DELETE FROM analysis_events")
        db.execute("DELETE FROM packing_events")
        db.execute("DELETE FROM label_print_events")
        logger.warning("All stats reset (DB event tables truncated)")

    # ── Internal ───────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_event(row: Dict) -> Dict:
        ts = row.get("timestamp")
        out = dict(row)
        out["timestamp"] = ts.isoformat() if ts else None
        # Deserialize metadata if it came back as a string
        meta = out.get("metadata")
        if isinstance(meta, str):
            try:
                out["metadata"] = json.loads(meta)
            except (ValueError, TypeError):
                out["metadata"] = {}
        return out
