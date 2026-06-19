"""Profile Manager for Shopify Fulfillment Tool — PostgreSQL backend.

All config and metadata is stored in PostgreSQL (fulfillment_db).
Binary/generated files (CSV, XLSX, PDFs, barcodes) remain on the file server.

Public API is identical to the previous JSON-file implementation so callers
(gui/, shopify_tool/core.py) require no changes.
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from shopify_tool.db_manager import get_db

logger = logging.getLogger("ShopifyToolLogger")


# ── Exceptions (same names, same semantics) ────────────────────────────────

class ProfileManagerError(Exception):
    """Base exception for ProfileManager errors."""


class NetworkError(ProfileManagerError):
    """Raised when file server is not accessible."""


class ValidationError(ProfileManagerError):
    """Raised when validation fails."""


# ── Manager ────────────────────────────────────────────────────────────────

class ProfileManager:
    """Manages client profiles backed by PostgreSQL.

    Config data → PostgreSQL tables.
    File-server paths → still returned for session files, CSVs, XLSXs, etc.
    """

    # In-process cache: {cache_key: (data, datetime)}
    _config_cache: Dict[str, Tuple[Dict, datetime]] = {}
    CACHE_TIMEOUT_SECONDS = 60

    METADATA_CACHE_TIMEOUT_SECONDS = 300

    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = self._get_base_path()

        self.base_path = Path(base_path)

        if self._is_dev_environment():
            logger.info("DEV MODE - file server: %s", self.base_path)
        else:
            logger.info("PRODUCTION MODE - file server: %s", self.base_path)

        self.clients_dir = self.base_path / "Clients"
        self.sessions_dir = self.base_path / "Sessions"
        self.stats_dir = self.base_path / "Stats"
        self.logs_dir = self.base_path / "Logs" / "shopify_tool"

        self._metadata_cache: Dict[str, Tuple[Dict, datetime]] = {}

        self.connection_timeout = 5
        self.is_network_available = self._test_connection()

        if not self.is_network_available:
            raise NetworkError(
                f"Cannot connect to file server at {self.base_path}\n\n"
                "Please check:\n"
                "1. Network connection\n"
                "2. File server is online\n"
                "3. Path is correct and accessible"
            )

        logger.info("ProfileManager (PostgreSQL) initialised, base: %s", self.base_path)

    # ── Environment helpers ────────────────────────────────────────────────

    def _get_base_path(self) -> str:
        env_path = os.environ.get("FULFILLMENT_SERVER_PATH")
        if env_path:
            return env_path
        return r"\\192.168.88.101\_Fulfilment_\0UFulfilment"

    def _is_dev_environment(self) -> bool:
        return "FULFILLMENT_SERVER_PATH" in os.environ

    def _test_connection(self) -> bool:
        """Verify the file server is writable (for session/CSV files)."""
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.clients_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            test = self.base_path / ".connection_test"
            test.touch(exist_ok=True)
            _ = test.exists()
            logger.info("File server OK: %s", self.base_path)
            return True
        except (PermissionError, OSError) as e:
            logger.error("File server FAILED: %s", e)
            return False
        except Exception as e:
            logger.error("File server FAILED (unexpected): %s", e, exc_info=True)
            return False

    # ── Validation ─────────────────────────────────────────────────────────

    @staticmethod
    def validate_client_id(client_id: str) -> Tuple[bool, str]:
        if not client_id:
            return False, "Client ID cannot be empty"
        if len(client_id) > 20:
            return False, "Client ID too long (max 20 characters)"
        if not re.match(r"^[A-Z0-9_]+$", client_id.upper()):
            return False, "Client ID can only contain letters, numbers, and underscore"
        if client_id.upper().startswith("CLIENT_"):
            return False, "Don't include 'CLIENT_' prefix, it will be added automatically"
        reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                    "LPT1", "LPT2", "LPT3", "LPT4"]
        if client_id.upper() in reserved:
            return False, f"'{client_id}' is a reserved system name"
        return True, ""

    # ── Client CRUD ────────────────────────────────────────────────────────

    def list_clients(self) -> List[str]:
        """Return sorted list of client IDs (without CLIENT_ prefix)."""
        try:
            rows = get_db().fetchall("SELECT client_id FROM clients ORDER BY client_id")
            return [r["client_id"] for r in rows]
        except Exception as e:
            logger.error("list_clients DB error: %s", e)
            return []

    def client_exists(self, client_id: str) -> bool:
        client_id = client_id.upper()
        row = get_db().fetchone(
            "SELECT 1 FROM clients WHERE client_id = %s", (client_id,)
        )
        return row is not None

    def create_client_profile(self, client_id: str, client_name: str) -> bool:
        """Create a new client with default config in PostgreSQL + file server dirs."""
        is_valid, error_msg = self.validate_client_id(client_id)
        if not is_valid:
            raise ValidationError(error_msg)

        client_id = client_id.upper()

        if self.client_exists(client_id):
            logger.warning("Client profile already exists: CLIENT_%s", client_id)
            return False

        db = get_db()
        default_cfg = self._create_default_shopify_config(client_id, client_name)
        default_ui = self._get_default_ui_settings()
        created_by = os.environ.get("COMPUTERNAME", "Unknown")
        now = datetime.now()

        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    # clients
                    cur.execute(
                        "INSERT INTO clients (client_id, client_name, created_at, created_by) "
                        "VALUES (%s, %s, %s, %s)",
                        (client_id, client_name, now, created_by),
                    )
                    # settings
                    s = default_cfg["settings"]
                    cur.execute(
                        "INSERT INTO client_settings "
                        "(client_id, low_stock_threshold, stock_csv_delimiter, "
                        " orders_csv_delimiter, repeat_detection_days, default_printer) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (client_id,
                         s.get("low_stock_threshold", 5),
                         s.get("stock_csv_delimiter", ","),
                         s.get("orders_csv_delimiter", ","),
                         s.get("repeat_detection_days", 30),
                         default_cfg.get("sku_label_config", {}).get("default_printer", "")),
                    )
                    # column mappings
                    cm = default_cfg.get("column_mappings", {})
                    for mtype in ("orders", "stock"):
                        for ext, internal in cm.get(mtype, {}).items():
                            cur.execute(
                                "INSERT INTO client_column_mappings "
                                "(client_id, mapping_type, external_field, internal_field) "
                                "VALUES (%s,%s,%s,%s)",
                                (client_id, mtype, ext, internal),
                            )
                    # courier mappings
                    for name, conf in default_cfg.get("courier_mappings", {}).items():
                        cur.execute(
                            "INSERT INTO client_courier_mappings "
                            "(client_id, courier_name, patterns, case_sensitive) "
                            "VALUES (%s,%s,%s,%s)",
                            (client_id, name,
                             conf.get("patterns", []),
                             conf.get("case_sensitive", False)),
                        )
                    # tag categories + tags + sku_writeoff
                    tc = default_cfg.get("tag_categories", {}).get("categories", {})
                    for cat_key, cat in tc.items():
                        cur.execute(
                            "INSERT INTO client_tag_categories "
                            "(client_id, category_key, label, color, display_order, sku_writeoff_enabled) "
                            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                            (client_id, cat_key,
                             cat.get("label", cat_key),
                             cat.get("color", "#9E9E9E"),
                             cat.get("order", 999),
                             cat.get("sku_writeoff", {}).get("enabled", False)),
                        )
                        cat_id = cur.fetchone()[0]
                        for tag in cat.get("tags", []):
                            cur.execute(
                                "INSERT INTO client_tags (category_id, tag_name) VALUES (%s,%s)",
                                (cat_id, tag),
                            )
                        for sku, tag_name in cat.get("sku_writeoff", {}).get("mappings", {}).items():
                            cur.execute(
                                "INSERT INTO client_tag_sku_mappings "
                                "(category_id, sku, tag_name) VALUES (%s,%s,%s)",
                                (cat_id, sku, tag_name),
                            )
                    # weight config
                    wc = default_cfg.get("weight_config", {})
                    cur.execute(
                        "INSERT INTO client_weight_config (client_id, volumetric_divisor) "
                        "VALUES (%s,%s)",
                        (client_id, wc.get("volumetric_divisor", 6000)),
                    )
                    # packing configs (empty by default)
                    cur.execute(
                        "INSERT INTO client_packing_configs "
                        "(client_id, packing_list_configs, stock_export_configs) "
                        "VALUES (%s,%s,%s)",
                        (client_id,
                         json.dumps(default_cfg.get("packing_list_configs", [])),
                         json.dumps(default_cfg.get("stock_export_configs", []))),
                    )
                    # ui settings
                    cur.execute(
                        "INSERT INTO client_ui_settings "
                        "(client_id, is_pinned, group_id, custom_color, "
                        " custom_badges, display_order, table_view) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (client_id,
                         default_ui.get("is_pinned", False),
                         default_ui.get("group_id"),
                         default_ui.get("custom_color", "#4CAF50"),
                         default_ui.get("custom_badges", []),
                         default_ui.get("display_order", 0),
                         json.dumps(default_ui.get("table_view", {}))),
                    )

            # Create session sub-directory on file server for file storage
            session_client_dir = self.sessions_dir / f"CLIENT_{client_id}"
            session_client_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Client profile created: CLIENT_%s", client_id)
            return True

        except Exception as e:
            logger.error("Failed to create client profile CLIENT_%s: %s", client_id, e)
            raise ProfileManagerError(f"Failed to create client profile: {e}")

    # ── Config loaders ─────────────────────────────────────────────────────

    def load_shopify_config(self, client_id: str) -> Optional[Dict]:
        """Load shopify config from DB, reconstructing the legacy dict shape."""
        client_id = client_id.upper()
        cache_key = f"shopify_{client_id}"

        if cache_key in self._config_cache:
            cached_data, cached_time = self._config_cache[cache_key]
            age = (datetime.now() - cached_time).total_seconds()
            if age < self.CACHE_TIMEOUT_SECONDS:
                return cached_data

        db = get_db()
        row = db.fetchone(
            "SELECT c.client_name, c.created_at, s.low_stock_threshold, s.stock_csv_delimiter, "
            "       s.orders_csv_delimiter, s.repeat_detection_days, s.default_printer, "
            "       s.updated_at "
            "FROM clients c "
            "LEFT JOIN client_settings s ON s.client_id = c.client_id "
            "WHERE c.client_id = %s",
            (client_id,),
        )
        if row is None:
            logger.warning("Shopify config not found in DB: CLIENT_%s", client_id)
            return None

        # column_mappings
        cm_rows = db.fetchall(
            "SELECT mapping_type, external_field, internal_field "
            "FROM client_column_mappings WHERE client_id = %s",
            (client_id,),
        )
        orders_map: Dict = {}
        stock_map: Dict = {}
        for r in cm_rows:
            if r["mapping_type"] == "orders":
                orders_map[r["external_field"]] = r["internal_field"]
            else:
                stock_map[r["external_field"]] = r["internal_field"]

        # courier_mappings
        cr_rows = db.fetchall(
            "SELECT courier_name, patterns, case_sensitive "
            "FROM client_courier_mappings WHERE client_id = %s",
            (client_id,),
        )
        courier_mappings: Dict = {}
        for r in cr_rows:
            courier_mappings[r["courier_name"]] = {
                "patterns": list(r["patterns"]),
                "case_sensitive": r["case_sensitive"],
            }

        # rules
        rule_rows = db.fetchall(
            "SELECT rule_definition FROM client_rules "
            "WHERE client_id = %s ORDER BY display_order",
            (client_id,),
        )
        rules = [r["rule_definition"] for r in rule_rows]

        # tag_categories
        cat_rows = db.fetchall(
            "SELECT id, category_key, label, color, display_order, sku_writeoff_enabled "
            "FROM client_tag_categories WHERE client_id = %s ORDER BY display_order",
            (client_id,),
        )
        categories: Dict = {}
        for cr in cat_rows:
            tag_rows = db.fetchall(
                "SELECT tag_name FROM client_tags WHERE category_id = %s", (cr["id"],)
            )
            sku_rows = db.fetchall(
                "SELECT sku, tag_name FROM client_tag_sku_mappings WHERE category_id = %s",
                (cr["id"],),
            )
            categories[cr["category_key"]] = {
                "label": cr["label"],
                "color": cr["color"],
                "order": cr["display_order"],
                "tags": [t["tag_name"] for t in tag_rows],
                "sku_writeoff": {
                    "enabled": cr["sku_writeoff_enabled"],
                    "mappings": {r["sku"]: r["tag_name"] for r in sku_rows},
                },
            }

        # set_decoders
        sd_rows = db.fetchall(
            "SELECT set_sku, component_sku, quantity "
            "FROM client_set_decoders WHERE client_id = %s",
            (client_id,),
        )
        set_decoders: Dict = {}
        for r in sd_rows:
            set_decoders.setdefault(r["set_sku"], []).append(
                {"sku": r["component_sku"], "quantity": r["quantity"]}
            )

        # weight_config
        wc_row = db.fetchone(
            "SELECT volumetric_divisor FROM client_weight_config WHERE client_id = %s",
            (client_id,),
        )
        prod_rows = db.fetchall(
            "SELECT sku, weight_kg, length_cm, width_cm, height_cm "
            "FROM client_products WHERE client_id = %s",
            (client_id,),
        )
        box_rows = db.fetchall(
            "SELECT name, weight_kg, length_cm, width_cm, height_cm "
            "FROM client_boxes WHERE client_id = %s",
            (client_id,),
        )
        products: Dict = {}
        for r in prod_rows:
            entry: Dict = {}
            if r["weight_kg"] is not None:
                entry["weight"] = float(r["weight_kg"])
            if r["length_cm"] is not None:
                entry["dimensions"] = {
                    "length": float(r["length_cm"]),
                    "width": float(r["width_cm"]),
                    "height": float(r["height_cm"]),
                }
            products[r["sku"]] = entry
        boxes = []
        for r in box_rows:
            b: Dict = {"name": r["name"]}
            if r["weight_kg"] is not None:
                b["weight"] = float(r["weight_kg"])
            if r["length_cm"] is not None:
                b["dimensions"] = {
                    "length": float(r["length_cm"]),
                    "width": float(r["width_cm"]),
                    "height": float(r["height_cm"]),
                }
            boxes.append(b)

        # sku_label_config
        sku_label_rows = db.fetchall(
            "SELECT sku, label_name FROM client_sku_labels WHERE client_id = %s",
            (client_id,),
        )

        # packing configs
        pc_row = db.fetchone(
            "SELECT packing_list_configs, stock_export_configs "
            "FROM client_packing_configs WHERE client_id = %s",
            (client_id,),
        )

        created_at = row["created_at"]
        updated_at = row["updated_at"]
        config = {
            "client_id": client_id,
            "client_name": row["client_name"],
            "created_at": created_at.isoformat() if created_at else None,
            "last_updated": updated_at.isoformat() if updated_at else None,
            "column_mappings": {
                "version": 2,
                "orders": orders_map,
                "stock": stock_map,
            },
            "courier_mappings": courier_mappings,
            "settings": {
                "low_stock_threshold": row["low_stock_threshold"] or 5,
                "stock_csv_delimiter": row["stock_csv_delimiter"] or ",",
                "orders_csv_delimiter": row["orders_csv_delimiter"] or ",",
                "repeat_detection_days": row["repeat_detection_days"] or 30,
            },
            "rules": rules,
            "order_rules": rules,
            "packing_list_configs": pc_row["packing_list_configs"] if pc_row else [],
            "stock_export_configs": pc_row["stock_export_configs"] if pc_row else [],
            "set_decoders": set_decoders,
            "packaging_rules": [],
            "weight_config": {
                "volumetric_divisor": wc_row["volumetric_divisor"] if wc_row else 6000,
                "products": products,
                "boxes": boxes,
            },
            "tag_categories": {"version": 2, "categories": categories},
            "sku_label_config": {
                "sku_to_label": {r["sku"]: r["label_name"] for r in sku_label_rows},
                "default_printer": row["default_printer"] or "",
            },
        }

        self._config_cache[cache_key] = (config, datetime.now())
        return config

    def save_shopify_config(self, client_id: str, config: Dict) -> bool:
        """Decompose the config dict into normalised DB rows (single transaction)."""
        client_id = client_id.upper()

        if not self.client_exists(client_id):
            raise ProfileManagerError(f"Client profile does not exist: CLIENT_{client_id}")

        db = get_db()
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    self._upsert_shopify_config(cur, client_id, config)

            # Invalidate cache
            self._config_cache.pop(f"shopify_{client_id}", None)
            logger.info("Shopify config saved for CLIENT_%s", client_id)
            return True

        except Exception as e:
            logger.error("save_shopify_config failed for CLIENT_%s: %s", client_id, e)
            raise ProfileManagerError(f"Failed to save config: {e}")

    # ── Type-coercion helpers (guards against non-standard old JSON formats) ──

    @staticmethod
    def _coerce_str(v, default: str = "") -> str:
        """Return v as a string; handle dicts/lists from old JSON formats."""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # e.g. {"field": "Order_Number"} → extract "field" value
            for key in ("field", "name", "value"):
                if key in v:
                    return str(v[key])
            return json.dumps(v)
        if v is None:
            return default
        return str(v)

    @staticmethod
    def _coerce_int(v, default: int = 0) -> int:
        """Return v as int; extract from dict if needed."""
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, dict):
            for key in ("value", "threshold", "days"):
                if key in v:
                    try:
                        return int(v[key])
                    except (TypeError, ValueError):
                        pass
            return default
        if v is None:
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(v, default: bool = False) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, dict):
            for key in ("value", "enabled"):
                if key in v:
                    return bool(v[key])
            return default
        if v is None:
            return default
        return bool(v)

    @staticmethod
    def _coerce_str_list(v) -> list:
        """Ensure v is a list of strings (TEXT[] safe for psycopg2)."""
        if not isinstance(v, list):
            return []
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # e.g. {"pattern": "dhl", "flags": []} → take first string-valued key
                for key in ("pattern", "name", "value"):
                    if key in item and isinstance(item[key], str):
                        result.append(item[key])
                        break
                else:
                    result.append(json.dumps(item))
            elif item is not None:
                result.append(str(item))
        return result

    def _upsert_shopify_config(self, cur, client_id: str, config: Dict) -> None:
        """Write all shopify_config sub-sections to their tables (cursor must be in transaction)."""
        s = config.get("settings", {})
        slc = config.get("sku_label_config", {})

        # client_settings
        cur.execute(
            """
            INSERT INTO client_settings
                (client_id, low_stock_threshold, stock_csv_delimiter,
                 orders_csv_delimiter, repeat_detection_days, default_printer, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (client_id) DO UPDATE SET
                low_stock_threshold   = EXCLUDED.low_stock_threshold,
                stock_csv_delimiter   = EXCLUDED.stock_csv_delimiter,
                orders_csv_delimiter  = EXCLUDED.orders_csv_delimiter,
                repeat_detection_days = EXCLUDED.repeat_detection_days,
                default_printer       = EXCLUDED.default_printer,
                updated_at            = now()
            """,
            (client_id,
             self._coerce_int(s.get("low_stock_threshold"), 5),
             self._coerce_str(s.get("stock_csv_delimiter"), ","),
             self._coerce_str(s.get("orders_csv_delimiter"), ","),
             self._coerce_int(s.get("repeat_detection_days"), 30),
             self._coerce_str(slc.get("default_printer", ""))),
        )

        # column_mappings — full replace
        cur.execute("DELETE FROM client_column_mappings WHERE client_id = %s", (client_id,))
        cm = config.get("column_mappings", {})
        for mtype in ("orders", "stock"):
            for ext, internal in cm.get(mtype, {}).items():
                if not isinstance(ext, str):
                    continue
                cur.execute(
                    "INSERT INTO client_column_mappings "
                    "(client_id, mapping_type, external_field, internal_field) "
                    "VALUES (%s,%s,%s,%s)",
                    (client_id, mtype, ext, self._coerce_str(internal)),
                )

        # courier_mappings — full replace
        cur.execute("DELETE FROM client_courier_mappings WHERE client_id = %s", (client_id,))
        for name, conf in config.get("courier_mappings", {}).items():
            if not isinstance(conf, dict):
                # old format: {"DHL": ["pattern1", "pattern2"]} — conf is a list
                patterns = self._coerce_str_list(conf if isinstance(conf, list) else [])
                case_sensitive = False
            else:
                patterns = self._coerce_str_list(conf.get("patterns", []))
                case_sensitive = self._coerce_bool(conf.get("case_sensitive", False))
            cur.execute(
                "INSERT INTO client_courier_mappings "
                "(client_id, courier_name, patterns, case_sensitive) "
                "VALUES (%s,%s,%s,%s)",
                (client_id, name, patterns, case_sensitive),
            )

        # rules — full replace (cascade delete via FK would also work)
        cur.execute("DELETE FROM client_rules WHERE client_id = %s", (client_id,))
        for idx, rule in enumerate(config.get("rules", [])):
            cur.execute(
                "INSERT INTO client_rules (client_id, rule_definition, display_order) "
                "VALUES (%s,%s,%s)",
                (client_id, json.dumps(rule), idx),
            )

        # tag_categories — full replace (cascades to tags + sku_mappings)
        cur.execute(
            "DELETE FROM client_tag_categories WHERE client_id = %s", (client_id,)
        )
        tc = config.get("tag_categories", {}).get("categories", {})
        for cat_key, cat in tc.items():
            if not isinstance(cat, dict):
                continue
            sku_writeoff = cat.get("sku_writeoff", {})
            if not isinstance(sku_writeoff, dict):
                sku_writeoff = {}
            cur.execute(
                "INSERT INTO client_tag_categories "
                "(client_id, category_key, label, color, display_order, sku_writeoff_enabled) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (client_id, cat_key,
                 self._coerce_str(cat.get("label", cat_key), cat_key),
                 self._coerce_str(cat.get("color", "#9E9E9E"), "#9E9E9E"),
                 self._coerce_int(cat.get("order"), 999),
                 self._coerce_bool(sku_writeoff.get("enabled", False))),
            )
            cat_id = cur.fetchone()[0]
            for tag in cat.get("tags", []):
                tag_str = self._coerce_str(tag)
                if tag_str:
                    cur.execute(
                        "INSERT INTO client_tags (category_id, tag_name) VALUES (%s,%s)",
                        (cat_id, tag_str),
                    )
            mappings = sku_writeoff.get("mappings", {})
            if isinstance(mappings, dict):
                for sku, tag_name in mappings.items():
                    cur.execute(
                        "INSERT INTO client_tag_sku_mappings "
                        "(category_id, sku, tag_name) VALUES (%s,%s,%s)",
                        (cat_id, self._coerce_str(sku), self._coerce_str(tag_name)),
                    )

        # set_decoders — full replace
        cur.execute("DELETE FROM client_set_decoders WHERE client_id = %s", (client_id,))
        for set_sku, components in config.get("set_decoders", {}).items():
            if isinstance(components, dict):
                # old format: {"component_sku": quantity, ...}
                items = [{"sku": k, "quantity": v} for k, v in components.items()]
            elif isinstance(components, list):
                items = components
            else:
                continue
            for comp in items:
                if not isinstance(comp, dict):
                    continue
                cur.execute(
                    "INSERT INTO client_set_decoders "
                    "(client_id, set_sku, component_sku, quantity) VALUES (%s,%s,%s,%s)",
                    (client_id, set_sku, comp["sku"], int(comp.get("quantity", 1))),
                )

        # weight_config
        wc = config.get("weight_config", {})
        cur.execute(
            """
            INSERT INTO client_weight_config (client_id, volumetric_divisor)
            VALUES (%s,%s)
            ON CONFLICT (client_id) DO UPDATE SET
                volumetric_divisor = EXCLUDED.volumetric_divisor
            """,
            (client_id, wc.get("volumetric_divisor", 6000)),
        )
        cur.execute("DELETE FROM client_products WHERE client_id = %s", (client_id,))
        for sku, prod in wc.get("products", {}).items():
            dims = prod.get("dimensions", {})
            cur.execute(
                "INSERT INTO client_products "
                "(client_id, sku, weight_kg, length_cm, width_cm, height_cm) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (client_id, sku,
                 prod.get("weight"),
                 dims.get("length"), dims.get("width"), dims.get("height")),
            )
        cur.execute("DELETE FROM client_boxes WHERE client_id = %s", (client_id,))
        for box in wc.get("boxes", []):
            dims = box.get("dimensions", {})
            cur.execute(
                "INSERT INTO client_boxes "
                "(client_id, name, weight_kg, length_cm, width_cm, height_cm) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (client_id, box["name"],
                 box.get("weight"),
                 dims.get("length"), dims.get("width"), dims.get("height")),
            )

        # sku_labels — full replace
        cur.execute("DELETE FROM client_sku_labels WHERE client_id = %s", (client_id,))
        for sku, label_name in slc.get("sku_to_label", {}).items():
            cur.execute(
                "INSERT INTO client_sku_labels (client_id, sku, label_name) VALUES (%s,%s,%s)",
                (client_id, self._coerce_str(sku), self._coerce_str(label_name)),
            )

        # packing configs
        cur.execute(
            """
            INSERT INTO client_packing_configs
                (client_id, packing_list_configs, stock_export_configs, updated_at)
            VALUES (%s,%s,%s, now())
            ON CONFLICT (client_id) DO UPDATE SET
                packing_list_configs = EXCLUDED.packing_list_configs,
                stock_export_configs = EXCLUDED.stock_export_configs,
                updated_at           = now()
            """,
            (client_id,
             json.dumps(config.get("packing_list_configs", [])),
             json.dumps(config.get("stock_export_configs", []))),
        )

    # ── client_config (ui_settings) ────────────────────────────────────────

    def load_client_config(self, client_id: str) -> Optional[Dict]:
        """Load client config (used for ui_settings, metadata)."""
        client_id = client_id.upper()
        db = get_db()

        c_row = db.fetchone(
            "SELECT client_id, client_name, created_at, created_by "
            "FROM clients WHERE client_id = %s",
            (client_id,),
        )
        if c_row is None:
            logger.warning("Client config not found: CLIENT_%s", client_id)
            return None

        ui_row = db.fetchone(
            "SELECT is_pinned, group_id, custom_color, custom_badges, "
            "       display_order, table_view, last_accessed "
            "FROM client_ui_settings WHERE client_id = %s",
            (client_id,),
        )

        config: Dict = {
            "client_id": c_row["client_id"],
            "client_name": c_row["client_name"],
            "created_at": c_row["created_at"].isoformat() if c_row["created_at"] else None,
            "created_by": c_row["created_by"],
        }

        if ui_row:
            config["ui_settings"] = {
                "is_pinned": ui_row["is_pinned"],
                "group_id": ui_row["group_id"],
                "custom_color": ui_row["custom_color"] or "#4CAF50",
                "custom_badges": list(ui_row["custom_badges"] or []),
                "display_order": ui_row["display_order"] or 0,
                "table_view": ui_row["table_view"] or self._get_default_ui_settings()["table_view"],
            }
            if ui_row["last_accessed"]:
                config["metadata"] = {"last_accessed": ui_row["last_accessed"].isoformat()}
        else:
            config["ui_settings"] = self._get_default_ui_settings()

        return config

    def save_client_config(self, client_id: str, config: Dict) -> bool:
        """Persist ui_settings (and last_accessed) to PostgreSQL."""
        client_id = client_id.upper()
        if not self.client_exists(client_id):
            raise ProfileManagerError(f"Client does not exist: CLIENT_{client_id}")

        ui = config.get("ui_settings", {})
        last_accessed_str = config.get("metadata", {}).get("last_accessed")
        last_accessed = None
        if last_accessed_str:
            try:
                last_accessed = datetime.fromisoformat(last_accessed_str)
            except (ValueError, TypeError):
                pass

        try:
            get_db().execute(
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
                 ui.get("group_id"),
                 ui.get("custom_color", "#4CAF50"),
                 ui.get("custom_badges", []),
                 ui.get("display_order", 0),
                 json.dumps(ui.get("table_view", {})),
                 last_accessed),
            )
            logger.info("Client config saved for CLIENT_%s", client_id)
            return True
        except Exception as e:
            logger.error("save_client_config failed for CLIENT_%s: %s", client_id, e)
            raise ProfileManagerError(f"Failed to save client config: {e}")

    # ── UI settings helpers ────────────────────────────────────────────────

    def get_ui_settings(self, client_id: str) -> Dict[str, Any]:
        config = self.load_client_config(client_id)
        if config is None:
            return {
                "is_pinned": False,
                "group_id": None,
                "custom_color": "#4CAF50",
                "custom_badges": [],
                "display_order": 0,
            }
        return config.get("ui_settings", {
            "is_pinned": False,
            "group_id": None,
            "custom_color": "#4CAF50",
            "custom_badges": [],
            "display_order": 0,
        })

    def update_ui_settings(self, client_id: str, ui_settings: Dict[str, Any]) -> bool:
        config = self.load_client_config(client_id)
        if config is None:
            raise ProfileManagerError(f"Client profile not found: CLIENT_{client_id}")
        current_ui = config.get("ui_settings", {})
        current_ui.update(ui_settings)
        config["ui_settings"] = current_ui
        return self.save_client_config(client_id, config)

    # ── Metadata ───────────────────────────────────────────────────────────

    def calculate_metadata(self, client_id: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Count sessions + last date from the DB sessions table."""
        client_id = client_id.upper()
        cache_key = f"CLIENT_{client_id}"

        if not force_refresh and cache_key in self._metadata_cache:
            cached_data, cached_time = self._metadata_cache[cache_key]
            age = (datetime.now() - cached_time).total_seconds()
            if age < self.METADATA_CACHE_TIMEOUT_SECONDS:
                return cached_data

        try:
            row = get_db().fetchone(
                "SELECT COUNT(*) AS total_sessions, "
                "       MAX(created_at) AS last_session_ts "
                "FROM sessions WHERE client_id = %s",
                (client_id,),
            )
            total = int(row["total_sessions"]) if row else 0
            last_ts = row["last_session_ts"] if row else None
            last_date = last_ts.strftime("%Y-%m-%d") if last_ts else None
        except Exception as e:
            logger.warning("calculate_metadata DB error for CLIENT_%s: %s", client_id, e)
            total, last_date = 0, None

        metadata = {
            "total_sessions": total,
            "last_session_date": last_date,
            "last_accessed": datetime.now().isoformat(),
        }
        self._metadata_cache[cache_key] = (metadata, datetime.now())
        return metadata

    def invalidate_metadata_cache(self, client_id: Optional[str] = None) -> None:
        if client_id:
            self._metadata_cache.pop(f"CLIENT_{client_id.upper()}", None)
        else:
            self._metadata_cache.clear()

    def update_last_accessed(self, client_id: str) -> bool:
        try:
            get_db().execute(
                "INSERT INTO client_ui_settings (client_id, last_accessed) "
                "VALUES (%s, now()) "
                "ON CONFLICT (client_id) DO UPDATE SET last_accessed = now()",
                (client_id.upper(),),
            )
            return True
        except Exception as e:
            logger.warning("update_last_accessed failed for CLIENT_%s: %s", client_id, e)
            return False

    def get_client_config_extended(self, client_id: str) -> Dict[str, Any]:
        config = self.load_client_config(client_id)
        if config is None:
            return {}
        config["metadata"] = self.calculate_metadata(client_id)
        return config

    # ── Set/bundle helpers ─────────────────────────────────────────────────

    def get_set_decoders(self, client_id: str) -> Dict:
        rows = get_db().fetchall(
            "SELECT set_sku, component_sku, quantity "
            "FROM client_set_decoders WHERE client_id = %s",
            (client_id.upper(),),
        )
        result: Dict = {}
        for r in rows:
            result.setdefault(r["set_sku"], []).append(
                {"sku": r["component_sku"], "quantity": r["quantity"]}
            )
        return result

    def save_set_decoders(self, client_id: str, set_decoders: Dict) -> bool:
        client_id = client_id.upper()
        db = get_db()
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM client_set_decoders WHERE client_id = %s", (client_id,)
                    )
                    for set_sku, components in set_decoders.items():
                        for comp in components:
                            cur.execute(
                                "INSERT INTO client_set_decoders "
                                "(client_id, set_sku, component_sku, quantity) "
                                "VALUES (%s,%s,%s,%s)",
                                (client_id, set_sku, comp["sku"], int(comp.get("quantity", 1))),
                            )
            self._config_cache.pop(f"shopify_{client_id}", None)
            logger.info("Set decoders saved for CLIENT_%s: %d sets", client_id, len(set_decoders))
            return True
        except Exception as e:
            logger.error("save_set_decoders failed: %s", e)
            raise ProfileManagerError(f"Failed to save set decoders: {e}")

    def add_set(self, client_id: str, set_sku: str, components: List[Dict]) -> bool:
        if not set_sku or not isinstance(set_sku, str):
            raise ValidationError("set_sku must be a non-empty string")
        if not components or not isinstance(components, list):
            raise ValidationError("components must be a non-empty list")
        for idx, comp in enumerate(components):
            if not isinstance(comp, dict):
                raise ValidationError(f"Component {idx} must be a dictionary")
            if "sku" not in comp or not comp["sku"]:
                raise ValidationError(f"Component {idx} missing 'sku' field")
            if "quantity" not in comp:
                raise ValidationError(f"Component {idx} missing 'quantity' field")
            try:
                qty = int(comp["quantity"])
                if qty <= 0:
                    raise ValidationError(f"Component {idx} quantity must be positive")
            except (ValueError, TypeError):
                raise ValidationError(f"Component {idx} quantity must be an integer")

        decoders = self.get_set_decoders(client_id)
        decoders[set_sku] = components
        return self.save_set_decoders(client_id, decoders)

    def delete_set(self, client_id: str, set_sku: str) -> bool:
        decoders = self.get_set_decoders(client_id)
        if set_sku not in decoders:
            logger.warning("Set '%s' not found for CLIENT_%s", set_sku, client_id)
            return False
        del decoders[set_sku]
        return self.save_set_decoders(client_id, decoders)

    # ── Path accessors (unchanged — file server still used for files) ──────

    def get_clients_root(self) -> Path:
        return self.clients_dir

    def get_sessions_root(self) -> Path:
        return self.sessions_dir

    def get_stats_path(self) -> Path:
        return self.stats_dir

    def get_logs_path(self) -> Path:
        return self.logs_dir

    def get_client_directory(self, client_id: str) -> Path:
        return self.clients_dir / f"CLIENT_{client_id.upper()}"

    # ── Static helpers (unchanged) ─────────────────────────────────────────

    @staticmethod
    def _get_default_ui_settings() -> Dict:
        return {
            "is_pinned": False,
            "group_id": None,
            "custom_color": "#4CAF50",
            "custom_badges": [],
            "display_order": 0,
            "table_view": {
                "version": 1,
                "active_view": "Default",
                "views": {
                    "Default": {
                        "visible_columns": {},
                        "column_order": [],
                        "column_widths": {},
                        "auto_hide_empty": True,
                        "locked_columns": ["Order_Number"],
                    }
                },
                "additional_columns": [],
            },
        }

    @staticmethod
    def _create_default_shopify_config(client_id: str, client_name: str) -> Dict:
        return {
            "client_id": client_id,
            "client_name": client_name,
            "created_at": datetime.now().isoformat(),
            "column_mappings": {
                "version": 2,
                "orders": {
                    "Name": "Order_Number",
                    "Lineitem sku": "SKU",
                    "Lineitem quantity": "Quantity",
                    "Lineitem name": "Product_Name",
                    "Shipping Method": "Shipping_Method",
                    "Shipping Country": "Shipping_Country",
                    "Tags": "Tags",
                    "Notes": "Notes",
                    "Total": "Total_Price",
                    "Subtotal": "Subtotal",
                },
                "stock": {
                    "Артикул": "SKU",
                    "Име": "Product_Name",
                    "Наличност": "Stock",
                    "Годност": "Expiry_Date",
                    "Партида": "Batch",
                },
            },
            "courier_mappings": {
                "DHL": {"patterns": ["dhl", "dhl express", "dhl_express"], "case_sensitive": False},
                "DPD": {"patterns": ["dpd", "dpd bulgaria"], "case_sensitive": False},
                "Speedy": {"patterns": ["speedy"], "case_sensitive": False},
            },
            "settings": {
                "low_stock_threshold": 5,
                "stock_csv_delimiter": ";",
                "orders_csv_delimiter": ",",
                "repeat_detection_days": 1,
            },
            "rules": [],
            "order_rules": [],
            "packing_list_configs": [],
            "stock_export_configs": [],
            "set_decoders": {},
            "packaging_rules": [],
            "weight_config": {"volumetric_divisor": 6000, "products": {}, "boxes": []},
            "tag_categories": {
                "version": 2,
                "categories": {
                    "packaging": {
                        "label": "Пакетаж", "color": "#4CAF50", "order": 1,
                        "tags": ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "priority": {
                        "label": "Пріоритет", "color": "#FF9800", "order": 2,
                        "tags": ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "status": {
                        "label": "Статус", "color": "#2196F3", "order": 3,
                        "tags": ["CHECKED", "PROBLEM", "VERIFIED"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "order_type": {
                        "label": "Тип замовлення", "color": "#9C27B0", "order": 4,
                        "tags": ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "accessories": {
                        "label": "Додатки", "color": "#E91E63", "order": 5,
                        "tags": ["STICKER", "BUSINESS_CARD", "GIFT_BOX"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "delivery": {
                        "label": "Кур'єр/Доставка", "color": "#FF5722", "order": 6,
                        "tags": ["NOVA_POSHTA", "UKRPOSHTA", "SELF_PICKUP"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "custom": {
                        "label": "Інші", "color": "#9E9E9E", "order": 999,
                        "tags": [],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                },
            },
            "sku_label_config": {"sku_to_label": {}, "default_printer": ""},
        }

    # ── Migration helpers kept for JSON import script compatibility ─────────
    # (called by scripts/import_json_to_postgres.py when reading old JSON files)

    def _migrate_column_mappings_v1_to_v2(self, client_id: str, config: Dict) -> bool:
        if "column_mappings" not in config:
            return False
        column_mappings = config["column_mappings"]
        if isinstance(column_mappings, dict) and column_mappings.get("version", 1) >= 2:
            return False
        config["column_mappings"] = {
            "version": 2,
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
                       "Lineitem quantity": "Quantity", "Lineitem name": "Product_Name",
                       "Shipping Method": "Shipping_Method", "Shipping Country": "Shipping_Country",
                       "Tags": "Tags", "Notes": "Notes", "Total": "Total_Price",
                       "Subtotal": "Subtotal"},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
        }
        return True

    def _migrate_add_tag_categories(self, client_id: str, config: Dict) -> bool:
        if "tag_categories" in config:
            return False
        config["tag_categories"] = self._create_default_shopify_config(
            client_id, ""
        )["tag_categories"]
        return True

    def _migrate_tag_categories_v1_to_v2(self, client_id: str, config: Dict) -> bool:
        tc = config.get("tag_categories", {})
        if tc.get("version") == 2:
            return False
        if not tc:
            return False

        _defaults = self._create_default_shopify_config("", "")["tag_categories"]["categories"]
        known_order = ["packaging", "priority", "status", "order_type", "accessories", "delivery", "custom"]
        cats: Dict = {}
        idx = 1

        # Phase 1: migrate existing known categories in defined order
        for key in known_order:
            if key in tc and isinstance(tc[key], dict):
                old = tc[key]
                cats[key] = {
                    "label": old.get("label", key.title()),
                    "color": old.get("color", "#9E9E9E"),
                    "order": idx,
                    "tags": old.get("tags", []),
                    "sku_writeoff": {"enabled": False, "mappings": {}},
                }
                idx += 1

        # Phase 2: preserve custom (non-known) categories from old config
        for key, val in tc.items():
            if key not in known_order and isinstance(val, dict):
                cats[key] = {
                    "label": val.get("label", key.title()),
                    "color": val.get("color", "#9E9E9E"),
                    "order": idx,
                    "tags": val.get("tags", []),
                    "sku_writeoff": {"enabled": False, "mappings": {}},
                }
                idx += 1

        # Phase 3: add new default categories that weren't in old config
        for key in known_order:
            if key not in tc and key in _defaults:
                default = _defaults[key]
                cats[key] = {
                    "label": default["label"],
                    "color": default["color"],
                    "order": idx,
                    "tags": default.get("tags", []),
                    "sku_writeoff": {"enabled": False, "mappings": {}},
                }
                idx += 1

        config["tag_categories"] = {"version": 2, "categories": cats}
        return True

    def _migrate_delimiter_config_v1_to_v2(self, client_id: str, config: Dict) -> bool:
        if "settings" not in config:
            return False
        s = config["settings"]
        migrated = False
        if "stock_delimiter" in s:
            s.setdefault("stock_csv_delimiter", s.pop("stock_delimiter"))
            migrated = True
        if "orders_csv_delimiter" not in s:
            s["orders_csv_delimiter"] = ","
            migrated = True
        return migrated

    def _migrate_add_weight_config(self, client_id: str, config: Dict) -> bool:
        if "weight_config" in config:
            return False
        config["weight_config"] = {"volumetric_divisor": 6000, "products": {}, "boxes": []}
        return True

    def _migrate_add_sku_label_config(self, client_id: str, config: Dict) -> bool:
        if "sku_label_config" in config:
            return False
        config["sku_label_config"] = {"sku_to_label": {}, "default_printer": ""}
        return True

    def _migrate_add_ui_settings(self, client_id: str, config: Dict) -> bool:
        if "ui_settings" in config:
            return False
        config["ui_settings"] = self._get_default_ui_settings()
        return True
