"""One-time migration: import existing JSON files from the file server into PostgreSQL.

Usage:
    python scripts/import_json_to_postgres.py --server-path "\\\\SERVER\\Share\\0UFulfilment"
    # or use FULFILLMENT_SERVER_PATH env var:
    python scripts/import_json_to_postgres.py

    # Only specific clients:
    python scripts/import_json_to_postgres.py --client ACME --client TESTCO

    # Preview without writing:
    python scripts/import_json_to_postgres.py --dry-run

    # Override DB URL:
    python scripts/import_json_to_postgres.py --database-url "postgresql://user:pass@host/db"

Import order:
    1. groups.json           → groups
    2. CLIENT_*/client_config.json  → clients + client_ui_settings
    3. CLIENT_*/shopify_config.json → all config sub-tables
    4. Sessions/CLIENT_*/*/session_info.json → sessions
    5. Stats/global_stats.json → analysis_events + packing_events + label_print_events
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Add project root to path so we can import shopify_tool
sys.path.insert(0, str(Path(__file__).parent.parent))

from shopify_tool.db_manager import get_db, reset_db
from shopify_tool.profile_manager import ProfileManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_ts(s):
    """Parse ISO timestamp string or return None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _j(path: Path) -> dict:
    """Load JSON file, return {} on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read %s: %s", path, e)
        return {}


def _test_db_connection(dsn: Optional[str] = None) -> bool:
    """Verify DB is reachable before starting the migration."""
    try:
        import psycopg2
        conn = psycopg2.connect(dsn or os.environ.get(
            "DATABASE_URL", "postgresql://postgres:root@localhost/fulfillment_db"
        ))
        conn.close()
        return True
    except Exception as e:
        logger.error("Cannot connect to PostgreSQL: %s", e)
        return False


def _known_group_ids(dry_run: bool) -> Set[str]:
    """Return set of group IDs currently in the groups table."""
    if dry_run:
        return set()
    try:
        rows = get_db().fetchall("SELECT id FROM groups")
        return {r["id"] for r in rows}
    except Exception:
        return set()


# ── Import functions ───────────────────────────────────────────────────────


def import_groups(groups_path: Path, dry_run: bool = False) -> int:
    """Import groups.json → groups table."""
    data = _j(groups_path)
    groups = data.get("groups", [])
    if not groups:
        logger.info("  No groups found in %s", groups_path)
        return 0

    imported = 0
    for g in groups:
        gid = g.get("id")
        if not gid:
            continue
        if dry_run:
            logger.info("  [DRY-RUN] Would import group: %s (%s)", gid, g.get("name"))
        else:
            get_db().execute(
                """
                INSERT INTO groups (id, name, color, display_order, collapsible, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    name          = EXCLUDED.name,
                    color         = EXCLUDED.color,
                    display_order = EXCLUDED.display_order,
                    updated_at    = EXCLUDED.updated_at
                """,
                (gid, g.get("name", "Unnamed"),
                 g.get("color", "#2196F3"),
                 g.get("display_order", 0),
                 g.get("collapsible", True),
                 _parse_ts(g.get("created_at")),
                 _parse_ts(g.get("updated_at"))),
            )
        imported += 1
    return imported


def import_client_config(
    client_id: str,
    config_path: Path,
    valid_group_ids: Set[str],
    dry_run: bool = False,
) -> bool:
    """Import client_config.json → clients + client_ui_settings."""
    data = _j(config_path)
    if not data:
        return False

    client_name = data.get("client_name", client_id)
    created_at = _parse_ts(data.get("created_at"))
    created_by = data.get("created_by", "import")

    ui = data.get("ui_settings", {})
    table_view = ui.get("table_view", {})
    last_acc = _parse_ts(data.get("metadata", {}).get("last_accessed"))

    # Guard FK: nullify group_id if it doesn't exist in groups table
    group_id = ui.get("group_id")
    if group_id and group_id not in valid_group_ids:
        logger.warning(
            "  CLIENT_%s: group_id '%s' not found in groups table — setting to NULL",
            client_id, group_id,
        )
        group_id = None

    if dry_run:
        logger.info("  [DRY-RUN] Would import client_config: CLIENT_%s (%s)", client_id, client_name)
        return True

    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (client_id, client_name, created_at, created_by)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (client_id) DO UPDATE SET
                    client_name = EXCLUDED.client_name,
                    created_by  = EXCLUDED.created_by
                """,
                (client_id, client_name, created_at, created_by),
            )
            cur.execute(
                """
                INSERT INTO client_ui_settings
                    (client_id, is_pinned, group_id, custom_color,
                     custom_badges, display_order, table_view, last_accessed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (client_id) DO UPDATE SET
                    is_pinned     = EXCLUDED.is_pinned,
                    group_id      = EXCLUDED.group_id,
                    custom_color  = EXCLUDED.custom_color,
                    custom_badges = EXCLUDED.custom_badges,
                    display_order = EXCLUDED.display_order,
                    table_view    = EXCLUDED.table_view,
                    last_accessed = EXCLUDED.last_accessed
                """,
                (client_id,
                 ui.get("is_pinned", False),
                 group_id,
                 ui.get("custom_color", "#4CAF50"),
                 ui.get("custom_badges", []),
                 ui.get("display_order", 0),
                 json.dumps(table_view),
                 last_acc),
            )
    return True


def import_shopify_config(
    client_id: str, config_path: Path, dry_run: bool = False
) -> bool:
    """Import shopify_config.json → all config sub-tables."""
    import traceback as _tb

    data = _j(config_path)
    if not data:
        return False

    # Apply legacy migrations so data is in v2 format before writing
    pm = ProfileManager.__new__(ProfileManager)  # no __init__
    pm._migrate_column_mappings_v1_to_v2(client_id, data)
    pm._migrate_delimiter_config_v1_to_v2(client_id, data)
    pm._migrate_add_tag_categories(client_id, data)
    pm._migrate_tag_categories_v1_to_v2(client_id, data)
    pm._migrate_add_weight_config(client_id, data)
    pm._migrate_add_sku_label_config(client_id, data)

    if dry_run:
        logger.info("  [DRY-RUN] Would import shopify_config: CLIENT_%s", client_id)
        return True

    db = get_db()
    try:
        with db.conn() as conn:
            with conn.cursor() as cur:
                # Ensure client row exists (in case client_config.json is missing)
                cur.execute(
                    "INSERT INTO clients (client_id, client_name) VALUES (%s,%s) "
                    "ON CONFLICT (client_id) DO NOTHING",
                    (client_id, data.get("client_name", client_id)),
                )
                pm._upsert_shopify_config(cur, client_id, data)
    except Exception as e:
        logger.warning("  FAILED shopify_config CLIENT_%s: %s", client_id, e)
        logger.warning("  Traceback for CLIENT_%s:\n%s", client_id, _tb.format_exc())
        logger.warning(
            "  CONFIG KEYS for CLIENT_%s: %s", client_id,
            {k: type(v).__name__ for k, v in data.items()}
        )
        return False
    return True


def import_sessions(
    sessions_root: Path,
    client_filter: Optional[List[str]] = None,
    dry_run: bool = False,
) -> int:
    """Walk Sessions/CLIENT_*/*/ and import session_info.json files."""
    imported = 0
    skipped = 0

    for client_dir in sorted(sessions_root.iterdir()):
        if not client_dir.is_dir() or not client_dir.name.startswith("CLIENT_"):
            continue
        client_id = client_dir.name.replace("CLIENT_", "", 1)

        if client_filter and client_id not in client_filter:
            continue

        for session_dir in sorted(client_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            info_path = session_dir / "session_info.json"
            if not info_path.exists():
                continue

            info = _j(info_path)
            if not info:
                continue

            session_name = info.get("session_name", session_dir.name)
            stats = info.get("statistics", {})

            if dry_run:
                logger.info(
                    "  [DRY-RUN] Would import session: CLIENT_%s / %s", client_id, session_name
                )
                imported += 1
                continue

            try:
                get_db().execute(
                    """
                    INSERT INTO sessions
                        (client_id, session_name, status, pc_name,
                         analysis_completed, orders_file, stock_file,
                         packing_lists_generated, stock_exports_generated,
                         total_orders, total_items, packing_lists_count,
                         packing_list_names, comments, created_at, last_modified,
                         status_updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (client_id, session_name) DO NOTHING
                    """,
                    (client_id, session_name,
                     info.get("status", "active"),
                     info.get("pc_name", "import"),
                     bool(info.get("analysis_completed", False)),
                     info.get("orders_file"),
                     info.get("stock_file"),
                     info.get("packing_lists_generated", []),
                     info.get("stock_exports_generated", []),
                     stats.get("total_orders", 0),
                     stats.get("total_items", 0),
                     stats.get("packing_lists_count", 0),
                     stats.get("packing_lists", []),
                     info.get("comments", ""),
                     _parse_ts(info.get("created_at")),
                     _parse_ts(info.get("last_modified") or info.get("last_updated")),
                     _parse_ts(info.get("status_updated_at"))),
                )
                imported += 1
            except Exception as e:
                logger.warning("  Skipped session %s/%s: %s", client_id, session_name, e)
                skipped += 1

    if skipped:
        logger.warning("  Skipped %d sessions due to errors (see warnings above)", skipped)
    return imported


def import_global_stats(
    stats_path: Path,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Import global_stats.json history arrays → event tables."""
    data = _j(stats_path)
    if not data:
        return {"analysis": 0, "packing": 0, "labels": 0}

    counts: Dict[str, int] = {"analysis": 0, "packing": 0, "labels": 0}
    errors: Dict[str, int] = {"analysis": 0, "packing": 0, "labels": 0}

    if dry_run:
        counts["analysis"] = len(data.get("analysis_history", []))
        counts["packing"] = len(data.get("packing_history", []))
        counts["labels"] = len(data.get("label_print_history", []))
        logger.info(
            "  [DRY-RUN] Would import: %d analysis / %d packing / %d label events",
            counts["analysis"], counts["packing"], counts["labels"],
        )
        return counts

    db = get_db()

    for ev in data.get("analysis_history", []):
        try:
            db.execute(
                "INSERT INTO analysis_events "
                "(client_id, session_name, orders_count, metadata, created_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (ev.get("client_id", "unknown"),
                 ev.get("session_id", "unknown"),
                 ev.get("orders_count", 0),
                 json.dumps(ev.get("metadata") or {}),
                 _parse_ts(ev.get("timestamp"))),
            )
            counts["analysis"] += 1
        except Exception as e:
            errors["analysis"] += 1
            logger.debug("  analysis_event skip (%s/%s): %s",
                         ev.get("client_id"), ev.get("session_id"), e)

    for ev in data.get("packing_history", []):
        try:
            db.execute(
                "INSERT INTO packing_events "
                "(client_id, session_name, worker_id, orders_count, items_count, "
                " metadata, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (ev.get("client_id", "unknown"),
                 ev.get("session_id", "unknown"),
                 ev.get("worker_id"),
                 ev.get("orders_count", 0),
                 ev.get("items_count", 0),
                 json.dumps(ev.get("metadata") or {}),
                 _parse_ts(ev.get("timestamp"))),
            )
            counts["packing"] += 1
        except Exception as e:
            errors["packing"] += 1
            logger.debug("  packing_event skip (%s/%s): %s",
                         ev.get("client_id"), ev.get("session_id"), e)

    for ev in data.get("label_print_history", []):
        try:
            db.execute(
                "INSERT INTO label_print_events "
                "(client_id, sku, copies, created_at) "
                "VALUES (%s,%s,%s,%s)",
                (ev.get("client_id", "unknown"),
                 ev.get("sku", "unknown"),
                 ev.get("copies", 1),
                 _parse_ts(ev.get("timestamp"))),
            )
            counts["labels"] += 1
        except Exception as e:
            errors["labels"] += 1
            logger.debug("  label_event skip (%s): %s", ev.get("client_id"), e)

    if any(errors.values()):
        logger.warning(
            "  Stats import errors (likely FK violations for unknown client_ids): "
            "analysis=%d  packing=%d  labels=%d",
            errors["analysis"], errors["packing"], errors["labels"],
        )

    return counts


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import JSON data from file server into PostgreSQL"
    )
    parser.add_argument(
        "--server-path",
        default=os.environ.get("FULFILLMENT_SERVER_PATH", ""),
        help="Base path to fulfillment server directory",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="PostgreSQL DSN (overrides DATABASE_URL env var and local config)",
    )
    parser.add_argument(
        "--client",
        action="append",
        dest="clients",
        metavar="CLIENT_ID",
        help="Only import this client (can be repeated, e.g. --client ACME --client TEST)",
    )
    parser.add_argument(
        "--skip-sessions", action="store_true", help="Skip session import"
    )
    parser.add_argument(
        "--skip-stats", action="store_true", help="Skip global_stats.json import"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be imported without writing to the DB",
    )
    args = parser.parse_args()

    # ── Validate server path ───────────────────────────────────────────────
    base = Path(args.server_path) if args.server_path else None
    if not base or not base.exists():
        logger.error("Server path does not exist or was not provided: %s", base)
        logger.error("Set FULFILLMENT_SERVER_PATH env var or use --server-path")
        sys.exit(1)

    clients_dir = base / "Clients"
    sessions_dir = base / "Sessions"
    stats_dir = base / "Stats"

    # ── Validate DB connection ─────────────────────────────────────────────
    if args.dry_run:
        logger.info("DRY-RUN mode — no data will be written to the database")
    else:
        dsn = args.database_url
        logger.info("Testing database connection...")
        if not _test_db_connection(dsn):
            sys.exit(1)
        if dsn:
            reset_db(dsn)
        logger.info("Database connection OK")

    client_filter = [c.upper() for c in args.clients] if args.clients else None
    if client_filter:
        logger.info("Client filter: %s", ", ".join(client_filter))

    logger.info("=" * 60)
    logger.info("Importing JSON data from: %s", base)
    logger.info("=" * 60)

    # 1. groups.json
    groups_path = clients_dir / "groups.json"
    if groups_path.exists():
        n = import_groups(groups_path, dry_run=args.dry_run)
        logger.info("[1/5] Groups imported: %d", n)
    else:
        logger.info("[1/5] groups.json not found, skipping")

    # Collect valid group IDs for FK guard (after importing groups)
    valid_group_ids = _known_group_ids(dry_run=args.dry_run)

    # 2. client_config.json
    logger.info("[2/5] Importing client configs...")
    client_count = 0
    client_errors = 0
    if clients_dir.exists():
        for client_dir in sorted(clients_dir.iterdir()):
            if not client_dir.is_dir() or not client_dir.name.startswith("CLIENT_"):
                continue
            client_id = client_dir.name.replace("CLIENT_", "", 1)
            if client_filter and client_id not in client_filter:
                continue
            cc_path = client_dir / "client_config.json"
            if cc_path.exists():
                try:
                    ok = import_client_config(
                        client_id, cc_path, valid_group_ids, dry_run=args.dry_run
                    )
                    if ok:
                        client_count += 1
                        logger.info("  client_config: CLIENT_%s", client_id)
                except Exception as e:
                    logger.warning("  FAILED client_config CLIENT_%s: %s", client_id, e)
                    client_errors += 1
    logger.info("  Total: %d clients (%d errors)", client_count, client_errors)

    # 3. shopify_config.json
    logger.info("[3/5] Importing shopify configs...")
    shopify_count = 0
    shopify_errors = 0
    if clients_dir.exists():
        for client_dir in sorted(clients_dir.iterdir()):
            if not client_dir.is_dir() or not client_dir.name.startswith("CLIENT_"):
                continue
            client_id = client_dir.name.replace("CLIENT_", "", 1)
            if client_filter and client_id not in client_filter:
                continue
            sc_path = client_dir / "shopify_config.json"
            if sc_path.exists():
                ok = import_shopify_config(client_id, sc_path, dry_run=args.dry_run)
                if ok:
                    shopify_count += 1
                    logger.info("  shopify_config: CLIENT_%s", client_id)
                else:
                    shopify_errors += 1
    logger.info("  Total: %d shopify configs (%d errors)", shopify_count, shopify_errors)

    # 4. session_info.json files
    if not args.skip_sessions:
        logger.info("[4/5] Importing sessions...")
        if sessions_dir.exists():
            n = import_sessions(sessions_dir, client_filter=client_filter, dry_run=args.dry_run)
            logger.info("  Total sessions imported: %d", n)
        else:
            logger.info("  Sessions directory not found, skipping")
    else:
        logger.info("[4/5] Sessions skipped (--skip-sessions)")

    # 5. global_stats.json
    if not args.skip_stats:
        stats_path = stats_dir / "global_stats.json"
        if stats_path.exists():
            logger.info("[5/5] Importing global stats history...")
            counts = import_global_stats(stats_path, dry_run=args.dry_run)
            logger.info(
                "  analysis_events: %d  packing_events: %d  label_print_events: %d",
                counts["analysis"], counts["packing"], counts["labels"],
            )
        else:
            logger.info("[5/5] global_stats.json not found, skipping")
    else:
        logger.info("[5/5] Stats skipped (--skip-stats)")

    logger.info("=" * 60)
    if args.dry_run:
        logger.info("DRY-RUN complete. No data was written.")
    else:
        logger.info("Migration complete.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
