"""
PostgreSQL connection pool for the fulfillment tool.

Usage in managers:
    from shopify_tool.db_manager import get_db

    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ...", (param,))
            rows = cur.fetchall()

The pool is a singleton initialised once per process.
Connection string is read from DATABASE_URL env var with a sensible default.
ThreadedConnectionPool is safe for concurrent QThread access.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

_DEFAULT_DSN = "postgresql://postgres:root@localhost/fulfillment_db"

# Per-PC local config: %LOCALAPPDATA%\ShopifyFulfillment\db_connection.json
_LOCAL_CONFIG_PATH = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "ShopifyFulfillment"
    / "db_connection.json"
)

_instance: "DatabaseManager | None" = None


def load_local_dsn() -> str | None:
    """Return DSN saved by the DB settings dialog, or None if not set."""
    try:
        if _LOCAL_CONFIG_PATH.exists():
            data = json.loads(_LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("dsn") or None
    except Exception as e:
        logger.warning("Could not read local DB config: %s", e)
    return None


def save_local_dsn(dsn: str) -> None:
    """Persist DSN to the per-PC local config file."""
    _LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_CONFIG_PATH.write_text(
        json.dumps({"dsn": dsn}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("DB DSN saved to %s", _LOCAL_CONFIG_PATH)


def _resolve_dsn(explicit: str | None = None) -> str:
    """DSN priority: explicit arg → DATABASE_URL env → local config file → default."""
    if explicit:
        return explicit
    if env := os.environ.get("DATABASE_URL"):
        return env
    if local := load_local_dsn():
        return local
    return _DEFAULT_DSN


class DatabaseManager:
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = _resolve_dsn(dsn)
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=self._dsn,
        )
        logger.info("DB pool created (%s)", self._dsn.split("@")[-1])

    # ── Connection context manager ─────────────────────────────────────────

    @contextlib.contextmanager
    def conn(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Yield a connection from the pool; auto-commit/rollback + return."""
        c = self._pool.getconn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            self._pool.putconn(c)

    # ── Convenience helpers ────────────────────────────────────────────────

    def execute(self, sql: str, params=None) -> None:
        """Run a statement that returns no rows."""
        with self.conn() as c:
            with c.cursor() as cur:
                cur.execute(sql, params)

    def fetchone(self, sql: str, params=None) -> dict | None:
        """Return the first row as a dict, or None."""
        with self.conn() as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None

    def fetchall(self, sql: str, params=None) -> list[dict]:
        """Return all rows as a list of dicts."""
        with self.conn() as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        self._pool.closeall()
        logger.info("DB pool closed")


def get_db() -> DatabaseManager:
    """Return the process-wide DatabaseManager singleton."""
    global _instance
    if _instance is None:
        _instance = DatabaseManager()
    return _instance


def reset_db(dsn: str | None = None) -> DatabaseManager:
    """Replace the singleton — used in tests to point at a test DB."""
    global _instance
    if _instance is not None:
        _instance.close()
    _instance = DatabaseManager(dsn)
    return _instance
