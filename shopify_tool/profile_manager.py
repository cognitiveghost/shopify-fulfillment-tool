"""Profile Manager for Shopify Fulfillment Tool.

This module provides centralized management of client profiles on a network file server.
Based on the architecture from Packing Tool with adaptations for Shopify-specific needs.

Key Features:
    - Client profile management (CRUD operations)
    - Configuration caching with TTL (60 seconds)
    - File locking for safe concurrent access
    - Network connectivity testing
    - Automatic backups of configurations
    - Validation of client IDs and configurations
"""

import copy
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from shared.logger import setup_logging
from shared.server_connection import resolve_server_path, test_path_reachable
from shopify_tool.profile_migrations import (
    migrate_add_inventory_memory,
    migrate_add_tag_categories,
    migrate_add_weight_config,
    migrate_column_mappings_v1_to_v2,
    migrate_delimiter_config_v1_to_v2,
    migrate_tag_categories_v1_to_v2,
)

logger = logging.getLogger("ShopifyToolLogger")


# Custom Exceptions
class ProfileManagerError(Exception):
    """Base exception for ProfileManager errors."""



class NetworkError(ProfileManagerError):
    """Raised when file server is not accessible."""



class ValidationError(ProfileManagerError):
    """Raised when validation fails."""



PROD_SERVER_PATH = r"\\192.168.88.101\_Fulfilment_\0UFulfilment"


class ProfileManager:
    """Manages client profiles and centralized configuration on file server.

    This class handles:
    - Loading and saving client configurations
    - Caching configs with time-based invalidation
    - File locking for concurrent write protection
    - Network connectivity testing
    - Automatic backup creation

    Attributes:
        base_path (Path): Root path on file server (e.g., \\\\server\\share\\0UFulfilment)
        clients_dir (Path): Directory containing client profiles
        sessions_dir (Path): Directory containing session data
        stats_dir (Path): Directory for statistics
        logs_dir (Path): Directory for centralized logs
        connection_timeout (int): Timeout for network operations in seconds
        is_network_available (bool): Whether file server is accessible
    """

    # Class-level cache: key → (data, mtime_float). mtime-based invalidation is more
    # correct than TTL — no stale reads after a write, no unnecessary re-reads within a window.
    # Key includes base_path so multiple instances with different roots don't collide.
    _config_cache: ClassVar[dict[str, tuple[dict, float]]] = {}

    # Class-level constants for metadata cache
    METADATA_CACHE_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self, base_path: str | None = None):
        """Initialize ProfileManager with automatic environment detection.

        Args:
            base_path: Base path to fulfillment directory.
                       If None, attempts to auto-detect from:
                       1. FULFILLMENT_SERVER_PATH environment variable (dev mode)
                       2. Path saved via the Server Connection UI
                       3. Default production path (\\\\192.168.88.101\\...)

        Raises:
            NetworkError: If file server is not accessible
        """
        # Auto-detect base path if not provided
        if base_path is None:
            base_path = self._get_base_path()

        self.base_path = Path(base_path)

        # Per-process log file on the same server base_path resolved to -
        # previously this never happened at all: shopify_tool/__init__.py
        # called the old setup_logging() at package-import time with no
        # base_path, so centralized JSON logging silently wrote to a
        # local ./logs/ folder instead of the network share.
        log_level_str = os.environ.get("FULFILLMENT_LOG_LEVEL", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        setup_logging("ShopifyTool", str(self.base_path), level=log_level, retention_days=30)

        # Log which environment we're using
        if self._is_dev_environment():
            logger.info(f"🔧 DEV MODE - Using local mock server: {self.base_path}")
        else:
            logger.info(f"🏭 PRODUCTION MODE - Using network server: {self.base_path}")

        self.clients_dir = self.base_path / "Clients"
        self.sessions_dir = self.base_path / "Sessions"
        self.stats_dir = self.base_path / "Stats"
        self.logs_dir = self.base_path / "Logs" / "shopify_tool"

        # Instance-level metadata cache
        self._metadata_cache: dict[str, tuple[dict, datetime]] = {}

        self.connection_timeout = 5
        self.is_network_available = self._test_connection()

        if not self.is_network_available:
            raise NetworkError(
                f"Cannot connect to file server at {self.base_path}\n\n"
                f"Please check:\n"
                f"1. Network connection\n"
                f"2. File server is online\n"
                f"3. Path is correct and accessible"
            )

        logger.info(f"ProfileManager initialized with base path: {self.base_path}")

    def _get_base_path(self) -> str:
        """Get base path with automatic environment detection.

        Priority:
            1. FULFILLMENT_SERVER_PATH environment variable (for dev)
            2. Path saved via the Server Connection UI
            3. Default production path

        Returns:
            Base path string
        """
        path = resolve_server_path("ShopifyTool", "FULFILLMENT_SERVER_PATH", PROD_SERVER_PATH)
        logger.info(f"Using server path: {path}")
        return path

    def _is_dev_environment(self) -> bool:
        """Check if running in development environment.

        Returns:
            True if FULFILLMENT_SERVER_PATH environment variable is set
        """
        return "FULFILLMENT_SERVER_PATH" in os.environ

    def _test_connection(self) -> bool:
        """Test if file server is accessible.

        Creates base directories, then verifies write access via the shared
        touch-file check.

        Returns:
            bool: True if server is accessible, False otherwise
        """
        try:
            # Create base directories if they don't exist
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.clients_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.exception("Network connection FAILED - Permission denied")
            return False
        except OSError:
            logger.exception("Network connection FAILED - OS error (network issue?)")
            return False
        except Exception:
            logger.exception(
                "Network connection FAILED - Unexpected error"
            )
            return False

        if test_path_reachable(str(self.base_path), self.connection_timeout):
            logger.info(f"Network connection OK: {self.base_path}")
            return True
        logger.error(f"Network connection FAILED: {self.base_path}")
        return False

    @staticmethod
    def validate_client_id(client_id: str) -> tuple[bool, str]:
        """Validate client ID format.

        Rules:
            - Not empty
            - Max 20 characters
            - Only alphanumeric and underscore
            - No "CLIENT_" prefix (will be added automatically)
            - Not a Windows reserved name

        Args:
            client_id (str): Client ID to validate

        Returns:
            Tuple[bool, str]: (is_valid, error_message)
                If valid: (True, "")
                If invalid: (False, "error description")
        """
        if not client_id:
            return False, "Client ID cannot be empty"

        if len(client_id) > 20:
            return False, "Client ID too long (max 20 characters)"

        if not re.match(r"^[A-Z0-9_]+$", client_id.upper()):
            return False, "Client ID can only contain letters, numbers, and underscore"

        if client_id.upper().startswith("CLIENT_"):
            return (
                False,
                "Don't include 'CLIENT_' prefix, it will be added automatically",
            )

        # Windows reserved names
        reserved = [
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
        ]
        if client_id.upper() in reserved:
            return False, f"'{client_id}' is a reserved system name"

        return True, ""

    def list_clients(self) -> list[str]:
        """Get list of available client IDs.

        Returns:
            List[str]: List of client IDs (without CLIENT_ prefix)
                Example: ["M", "A", "B"]
        """
        try:
            if not self.clients_dir.exists():
                self.clients_dir.mkdir(parents=True, exist_ok=True)
                return []

            clients = []
            for item in self.clients_dir.iterdir():
                if item.is_dir() and item.name.startswith("CLIENT_"):
                    client_id = item.name[len("CLIENT_"):]
                    clients.append(client_id)

            return sorted(clients)

        except PermissionError:
            logger.exception("Permission denied accessing clients directory")
            return []
        except OSError:
            logger.exception("File system error listing clients")
            return []
        except Exception:
            logger.exception("Unexpected error listing clients")
            return []

    def create_client_profile(self, client_id: str, client_name: str) -> bool:
        """Create a new client profile with default configuration.

        Creates directory structure:
            Clients/CLIENT_{ID}/
                ├── client_config.json      # General config
                ├── shopify_config.json     # Shopify-specific config
                └── backups/                # Config backups

        Args:
            client_id (str): Client ID (e.g., "M")
            client_name (str): Full client name (e.g., "M Cosmetics")

        Returns:
            bool: True if created successfully, False if already exists

        Raises:
            ValidationError: If client_id is invalid
            ProfileManagerError: If creation fails
        """
        # Validate client ID
        is_valid, error_msg = self.validate_client_id(client_id)
        if not is_valid:
            raise ValidationError(error_msg)

        client_id = client_id.upper()
        client_dir = self.clients_dir / f"CLIENT_{client_id}"

        # Check if already exists
        if client_dir.exists():
            logger.warning(f"Client profile already exists: CLIENT_{client_id}")
            return False

        try:
            # Create directory structure
            client_dir.mkdir(parents=True)
            (client_dir / "backups").mkdir()

            # Create general client config
            client_config = {
                "client_id": client_id,
                "client_name": client_name,
                "created_at": datetime.now().astimezone().isoformat(),
                "created_by": os.environ.get("COMPUTERNAME", "Unknown"),
            }

            config_path = client_dir / "client_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(client_config, f, indent=2)

            # Create default shopify config
            shopify_config = self._create_default_shopify_config(client_id, client_name)

            shopify_config_path = client_dir / "shopify_config.json"
            with open(shopify_config_path, "w", encoding="utf-8") as f:
                json.dump(shopify_config, f, indent=2)

            # Create session directory
            session_client_dir = self.sessions_dir / f"CLIENT_{client_id}"
            session_client_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Client profile created: CLIENT_{client_id}")
            return True

        except Exception as e:
            logger.exception("Failed to create client profile")
            # Cleanup on failure
            if client_dir.exists():
                shutil.rmtree(client_dir, ignore_errors=True)
            raise ProfileManagerError(f"Failed to create client profile: {e}")

    @staticmethod
    def _create_default_shopify_config(client_id: str, client_name: str) -> dict:
        """Create default Shopify configuration.

        Can be called without an instance for dev/test setup scripts.

        Args:
            client_id (str): Client ID
            client_name (str): Client name

        Returns:
            Dict: Default configuration structure
        """
        return {
            "client_id": client_id,
            "client_name": client_name,
            "created_at": datetime.now().astimezone().isoformat(),
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
                "DHL": {
                    "patterns": ["dhl", "dhl express", "dhl_express"],
                    "case_sensitive": False,
                },
                "DPD": {"patterns": ["dpd", "dpd bulgaria"], "case_sensitive": False},
                "Speedy": {"patterns": ["speedy"], "case_sensitive": False},
            },
            "analysis_mode": "multi_first",
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
                        "label": "Пакетаж",
                        "color": "#4CAF50",
                        "order": 1,
                        "tags": ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "priority": {
                        "label": "Пріоритет",
                        "color": "#FF9800",
                        "order": 2,
                        "tags": ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "status": {
                        "label": "Статус",
                        "color": "#2196F3",
                        "order": 3,
                        "tags": ["CHECKED", "PROBLEM", "VERIFIED"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "order_type": {
                        "label": "Тип замовлення",
                        "color": "#9C27B0",
                        "order": 4,
                        "tags": ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "accessories": {
                        "label": "Додатки",
                        "color": "#E91E63",
                        "order": 5,
                        "tags": ["STICKER", "BUSINESS_CARD", "GIFT_BOX"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "delivery": {
                        "label": "Кур'єр/Доставка",
                        "color": "#FF5722",
                        "order": 6,
                        "tags": ["NOVA_POSHTA", "UKRPOSHTA", "SELF_PICKUP"],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                    "custom": {
                        "label": "Інші",
                        "color": "#9E9E9E",
                        "order": 999,
                        "tags": [],
                        "sku_writeoff": {"enabled": False, "mappings": {}},
                    },
                },
            },
            "inventory_memory": {
                "enabled": False,
                "skus": {},
                "names": {},
                "last_updated": None,
                "total_units": 0,
            },
        }

    def load_client_config(self, client_id: str) -> dict | None:
        """Load general configuration for a client, with mtime-based caching.

        Cache is invalidated by file mtime rather than TTL: no stale reads after
        another PC saves a change, and no unnecessary re-reads while the file is
        stable. Mirrors load_shopify_config()'s cache exactly.

        Automatically migrates old configs to add ui_settings if missing.

        Args:
            client_id (str): Client ID

        Returns:
            Optional[Dict]: Configuration dictionary or None if not found
        """
        client_id = client_id.upper()
        cache_key = f"{self.base_path}::client_{client_id}"
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "client_config.json"

        if not config_path.exists():
            logger.warning(f"Client config not found: CLIENT_{client_id}")
            return None

        try:
            current_mtime = config_path.stat().st_mtime
        except OSError:
            current_mtime = None

        if current_mtime is not None and cache_key in self._config_cache:
            cached_data, cached_mtime = self._config_cache[cache_key]
            if cached_mtime == current_mtime:
                logger.debug(f"Using cached client config for {client_id}")
                return copy.deepcopy(cached_data)

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Check if migrations are needed
            migrated = self._migrate_add_ui_settings(client_id, config)

            if migrated:
                # If config was migrated, save it immediately
                self.save_client_config(client_id, config)
                logger.info(f"Config migrations completed for CLIENT_{client_id}")
                # save_client_config() invalidates cache_key; re-stat so this
                # call still populates the cache with the post-migration mtime.
                try:
                    current_mtime = config_path.stat().st_mtime
                except OSError:
                    current_mtime = None

            if current_mtime is not None:
                self._config_cache[cache_key] = (copy.deepcopy(config), current_mtime)

            return config

        except PermissionError:
            logger.exception(
                f"Permission denied reading client config for CLIENT_{client_id}"
            )
            return None
        except json.JSONDecodeError:
            logger.exception(f"Invalid JSON in client config for CLIENT_{client_id}")
            return None
        except Exception:
            logger.exception(
                f"Unexpected error loading client config for CLIENT_{client_id}",
            )
            return None

    def load_shopify_config(self, client_id: str) -> dict | None:
        """Load Shopify configuration for a client with mtime-based caching.

        Cache is invalidated by file mtime rather than TTL: no stale reads after
        another PC saves a change, and no unnecessary re-reads while the file is stable.

        Args:
            client_id (str): Client ID

        Returns:
            Optional[Dict]: Shopify configuration or None if not found
        """
        client_id = client_id.upper()
        cache_key = f"{self.base_path}::shopify_{client_id}"
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "shopify_config.json"

        if not config_path.exists():
            logger.warning(f"Shopify config not found: CLIENT_{client_id}")
            return None

        # Check cache against current file mtime
        try:
            current_mtime = config_path.stat().st_mtime
        except OSError:
            current_mtime = None

        if current_mtime is not None and cache_key in self._config_cache:
            cached_data, cached_mtime = self._config_cache[cache_key]
            if cached_mtime == current_mtime:
                logger.debug(f"Using cached shopify config for {client_id}")
                return copy.deepcopy(cached_data)

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Check if migrations are needed
            migrated_mappings = migrate_column_mappings_v1_to_v2(client_id, config)
            migrated_delimiters = migrate_delimiter_config_v1_to_v2(client_id, config)
            migrated_tag_categories = migrate_add_tag_categories(client_id, config)
            migrated_tag_categories_v2 = migrate_tag_categories_v1_to_v2(
                client_id, config
            )
            migrated_weight = migrate_add_weight_config(client_id, config)
            migrated_inv_memory = migrate_add_inventory_memory(client_id, config)

            if (
                migrated_mappings
                or migrated_delimiters
                or migrated_tag_categories
                or migrated_tag_categories_v2
                or migrated_weight
                or migrated_inv_memory
            ):
                self.save_shopify_config(client_id, config)
                logger.info(f"Config migrations completed for CLIENT_{client_id}")
                # save_shopify_config() invalidates cache_key; re-stat so this
                # call still populates the cache with the post-migration mtime.
                try:
                    current_mtime = config_path.stat().st_mtime
                except OSError:
                    current_mtime = None

            if current_mtime is not None:
                self._config_cache[cache_key] = (copy.deepcopy(config), current_mtime)

            return config

        except Exception:
            logger.exception("Failed to load shopify config")
            return None

    def save_shopify_config(self, client_id: str, config: dict) -> bool:
        """Save Shopify configuration with file locking and backup.

        Uses file locking to prevent concurrent write conflicts.
        Creates automatic backup before saving.

        Args:
            client_id (str): Client ID
            config (Dict): Configuration to save

        Returns:
            bool: True if saved successfully

        Raises:
            ProfileManagerError: If save fails
        """
        client_id = client_id.upper()
        client_dir = self.clients_dir / f"CLIENT_{client_id}"
        config_path = client_dir / "shopify_config.json"

        if not client_dir.exists():
            raise ProfileManagerError(
                f"Client profile does not exist: CLIENT_{client_id}"
            )

        # Create backup before saving
        if config_path.exists():
            self._create_backup(client_id, config_path, "shopify_config")

        # Update timestamp
        config["last_updated"] = datetime.now().astimezone().isoformat()
        config["updated_by"] = os.environ.get("COMPUTERNAME", "Unknown")

        # Calculate config size and metrics for logging
        start_time = time.perf_counter()
        json_str = json.dumps(config, indent=2, ensure_ascii=False)
        config_size = len(json_str.encode("utf-8"))
        num_sets = len(config.get("set_decoders", {}))

        logger.info(
            f"Saving config for CLIENT_{client_id}: "
            f"{config_size:,} bytes, {num_sets} sets"
        )

        max_retries = 5  # Reduced from 10 to minimize UI blocking
        retry_delay = 0.5  # Reduced from 1.0s (total worst case: 2.5s instead of 10s)
        timeout_seconds = 5  # Maximum time for entire save operation

        for attempt in range(max_retries):
            # Check timeout to avoid blocking UI for too long
            if time.perf_counter() - start_time > timeout_seconds:
                logger.error(
                    f"Save operation timed out after {timeout_seconds}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                break

            try:
                # Use platform-specific file locking
                if os.name == "nt":  # Windows
                    success = self._save_with_windows_lock(config_path, config)
                else:  # Unix-like
                    success = self._save_with_unix_lock(config_path, config)

                if success:
                    # Invalidate cache
                    cache_key = f"{self.base_path}::shopify_{client_id}"
                    self._config_cache.pop(cache_key, None)

                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(
                        f"Config saved successfully for CLIENT_{client_id} "
                        f"in {elapsed_ms:.2f}ms (attempt {attempt + 1}/{max_retries})"
                    )
                    return True
                else:
                    # File lock failed, retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Save failed (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {retry_delay}s: File is locked"
                        )
                        time.sleep(retry_delay)

            except OSError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Save failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    time.sleep(retry_delay)
                else:
                    logger.exception(
                        f"Save failed after {max_retries} attempts, "
                        f"config size: {config_size:,} bytes, {num_sets} sets"
                    )
                    raise ProfileManagerError(
                        "Configuration is locked by another user. Please try again."
                    )

        logger.error(
            f"Save failed after {max_retries} attempts, "
            f"config size: {config_size:,} bytes, {num_sets} sets"
        )
        return False

    # --- Set/Bundle Management Methods ---

    def save_inventory_memory(
        self, client_id: str, stock_dict: dict, config: dict | None = None, names_dict: dict | None = None
    ) -> bool:
        """Persist final stock snapshot to shopify_config inventory_memory section.

        Args:
            names_dict: Optional {sku: warehouse_display_name}. When omitted,
                the previously-saved names are left untouched (so a caller
                that only has quantities on hand doesn't wipe out names saved
                by an earlier run).
        """
        if not stock_dict:
            logger.warning(
                f"save_inventory_memory called with an empty stock_dict for "
                f"CLIENT_{client_id}; skipping to avoid erasing the existing snapshot"
            )
            return False

        # ponytail: read-modify-write; ceiling is concurrent PC writes can still clobber
        # enabled between load and save. Upgrade: hold file lock across load+save.
        # Pass config to skip the extra disk read when the caller already holds it.
        if config is None:
            config = self.load_shopify_config(client_id) or {}
        # Use update() so enabled (and any future keys) come from the freshly loaded config
        config.setdefault("inventory_memory", {})
        from .csv_utils import normalize_sku

        updates = {
            # Keep zero-qty SKUs: dropping them shrinks old_skus overlap ratio and can
            # trigger a false 'Wrong client file?' anomaly on the next stock load.
            "skus": {normalize_sku(k): float(v) for k, v in stock_dict.items()},
            "last_updated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "total_units": int(sum(v for v in stock_dict.values() if v > 0)),
        }
        if names_dict is not None:
            updates["names"] = {str(k): str(v) for k, v in names_dict.items()}
        config["inventory_memory"].update(updates)
        return self.save_shopify_config(client_id, config)

    def get_inventory_memory(self, client_id: str) -> dict:
        """Return inventory_memory dict; empty dict if not set."""
        config = self.load_shopify_config(client_id) or {}
        return config.get("inventory_memory", {})

    def get_set_decoders(self, client_id: str) -> dict:
        """Get set/bundle decoder definitions for a client.

        Args:
            client_id (str): Client ID

        Returns:
            Dict: Set decoders dictionary in format:
                  {"SET-SKU": [{"sku": "COMP-1", "quantity": 1}, ...]}
                  Returns empty dict if no sets defined
        """
        config = self.load_shopify_config(client_id)
        if not config:
            return {}

        return config.get("set_decoders", {})

    def save_set_decoders(self, client_id: str, set_decoders: dict) -> bool:
        """Save set/bundle decoder definitions for a client.

        Args:
            client_id (str): Client ID
            set_decoders (Dict): Set decoders dictionary

        Returns:
            bool: True if saved successfully

        Raises:
            ProfileManagerError: If save fails
        """
        config = self.load_shopify_config(client_id)
        if not config:
            raise ProfileManagerError(f"Cannot load config for CLIENT_{client_id}")

        config["set_decoders"] = set_decoders

        success = self.save_shopify_config(client_id, config)
        if success:
            logger.info(
                f"Set decoders saved for CLIENT_{client_id}: {len(set_decoders)} sets"
            )

        return success

    def add_set(
        self, client_id: str, set_sku: str, components: list[dict[str, Any]]
    ) -> bool:
        """Add or update a set/bundle definition.

        Args:
            client_id (str): Client ID
            set_sku (str): Set SKU to add/update
            components (List[Dict]): List of components, each with 'sku' and 'quantity'
                                    Example: [{"sku": "COMP-1", "quantity": 1}, ...]

        Returns:
            bool: True if added/updated successfully

        Raises:
            ValidationError: If validation fails
            ProfileManagerError: If save fails
        """
        # Validation
        if not set_sku or not isinstance(set_sku, str):
            raise ValidationError("set_sku must be a non-empty string")

        if not components or not isinstance(components, list):
            raise ValidationError("components must be a non-empty list")

        # Validate each component
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
                    raise ValidationError(
                        f"Component {idx} quantity must be positive, got {qty}"
                    )
            except (ValueError, TypeError):
                raise ValidationError(f"Component {idx} quantity must be an integer")

        # Load current sets
        set_decoders = self.get_set_decoders(client_id)

        # Add/update set
        set_decoders[set_sku] = components

        # Save
        success = self.save_set_decoders(client_id, set_decoders)
        if success:
            logger.info(
                f"Set '{set_sku}' added/updated for CLIENT_{client_id} with {len(components)} components"
            )

        return success

    def delete_set(self, client_id: str, set_sku: str) -> bool:
        """Delete a set/bundle definition.

        Args:
            client_id (str): Client ID
            set_sku (str): Set SKU to delete

        Returns:
            bool: True if deleted, False if set didn't exist

        Raises:
            ProfileManagerError: If save fails
        """
        # Load current sets
        set_decoders = self.get_set_decoders(client_id)

        # Check if set exists
        if set_sku not in set_decoders:
            logger.warning(f"Set '{set_sku}' not found for CLIENT_{client_id}")
            return False

        # Remove set
        del set_decoders[set_sku]

        # Save
        success = self.save_set_decoders(client_id, set_decoders)
        if success:
            logger.info(f"Set '{set_sku}' deleted for CLIENT_{client_id}")

        return success

    def _save_with_windows_lock(self, file_path: Path, data: dict) -> bool:
        """Save file with Windows file locking (locks entire file).

        Args:
            file_path (Path): Path to file
            data (Dict): Data to save

        Returns:
            bool: True if saved successfully
        """
        import msvcrt

        # Write to temp file first
        temp_path = file_path.with_suffix(".tmp")

        try:
            # Pre-serialize to know exact size
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            file_size = len(json_str.encode("utf-8"))

            logger.debug(f"Attempting to save config, size: {file_size:,} bytes")

            with open(temp_path, "w", encoding="utf-8") as f:
                # Try to acquire exclusive lock for entire file
                try:
                    # Ensure file position is at start before locking
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, file_size)
                    logger.debug(f"Lock acquired for {file_size:,} bytes")
                except OSError as e:
                    logger.warning(f"Lock failed: {e}")
                    return False

                try:
                    # Write pre-serialized JSON
                    f.write(json_str)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                    logger.debug("File written and flushed successfully")
                finally:
                    # Unlock with same size - must seek to start first
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, file_size)
                    logger.debug("Lock released")

            # Atomic move
            logger.debug(f"Renaming {temp_path.name} → {file_path.name}")
            shutil.move(str(temp_path), str(file_path))
            logger.debug(f"Config saved successfully: {file_path.name}")
            return True

        except Exception:
            logger.exception("Failed to save with Windows lock")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _save_with_unix_lock(self, file_path: Path, data: dict) -> bool:
        """Save file with Unix file locking.

        Args:
            file_path (Path): Path to file
            data (Dict): Data to save

        Returns:
            bool: True if saved successfully
        """
        import fcntl

        # Write to temp file first
        temp_path = file_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                # Try to acquire exclusive lock
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return False

                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Atomic move
            shutil.move(str(temp_path), str(file_path))
            return True

        except Exception:
            logger.exception("Failed to save with Unix lock")
            if temp_path.exists():
                temp_path.unlink()
            return False

    def _create_backup(self, client_id: str, file_path: Path, file_type: str):
        """Create timestamped backup of a configuration file.

        Keeps only last 10 backups to prevent unbounded growth.

        Args:
            client_id (str): Client ID
            file_path (Path): Path to file to backup
            file_type (str): Type of file (e.g., "shopify_config")
        """
        try:
            backup_dir = self.clients_dir / f"CLIENT_{client_id}" / "backups"
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{file_type}_{timestamp}.json"

            shutil.copy2(file_path, backup_path)

            # Keep only last 10 backups
            backups = sorted(backup_dir.glob(f"{file_type}_*.json"))
            for old_backup in backups[:-10]:
                old_backup.unlink()

            logger.debug(f"Backup created: {backup_path.name}")

        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")

    @staticmethod
    def _get_default_ui_settings() -> dict:
        """Return default ui_settings including table_view for client_config.

        Can be called without an instance for dev/test setup scripts.

        Returns:
            Dict: Default ui_settings structure
        """
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

    def _migrate_add_ui_settings(self, client_id: str, config: dict) -> bool:
        """Add ui_settings section if missing, including table_view.

        Args:
            client_id: Client ID (for logging)
            config: Configuration dictionary to migrate (modified in-place)

        Returns:
            bool: True if migration was performed, False if no migration needed
        """
        migrated = False

        defaults = self._get_default_ui_settings()

        # Add ui_settings if missing
        if "ui_settings" not in config:
            # Start with all defaults except table_view (added separately below)
            config["ui_settings"] = {
                k: v for k, v in defaults.items() if k != "table_view"
            }
            logger.info(f"Added ui_settings for CLIENT_{client_id}")
            migrated = True

        # Add table_view section to ui_settings if missing
        if "table_view" not in config["ui_settings"]:
            config["ui_settings"]["table_view"] = defaults["table_view"]
            logger.info(f"Added table_view settings for CLIENT_{client_id}")
            migrated = True

        return migrated

    def save_client_config(self, client_id: str, config: dict) -> bool:
        """Save client_config.json with file locking and backup.

        Similar to save_shopify_config but for client_config.json.
        Uses file locking to prevent concurrent write conflicts.
        Creates automatic backup before saving.

        Args:
            client_id: Client ID
            config: Configuration dict

        Returns:
            bool: True if saved successfully

        Raises:
            ProfileManagerError: If save fails after retries
        """
        client_id = client_id.upper()
        client_dir = self.clients_dir / f"CLIENT_{client_id}"
        config_path = client_dir / "client_config.json"

        if not client_dir.exists():
            raise ProfileManagerError(
                f"Client profile does not exist: CLIENT_{client_id}"
            )

        # Create backup before saving
        if config_path.exists():
            self._create_backup(client_id, config_path, "client_config")

        # Update timestamp
        config["last_updated"] = datetime.now().astimezone().isoformat()
        config["updated_by"] = os.environ.get("COMPUTERNAME", "Unknown")

        max_retries = 5  # Reduced from 10 to minimize UI blocking
        retry_delay = 0.5  # Reduced from 1.0s (total worst case: 2.5s instead of 10s)
        timeout_seconds = 5  # Maximum time for entire save operation
        start_time = time.perf_counter()

        for attempt in range(max_retries):
            # Check timeout to avoid blocking UI for too long
            if time.perf_counter() - start_time > timeout_seconds:
                logger.error(
                    f"Client config save timed out after {timeout_seconds}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                break

            try:
                # Use platform-specific file locking
                if os.name == "nt":  # Windows
                    success = self._save_with_windows_lock(config_path, config)
                else:  # Unix-like
                    success = self._save_with_unix_lock(config_path, config)

                if success:
                    # Invalidate cache
                    cache_key = f"{self.base_path}::client_{client_id}"
                    self._config_cache.pop(cache_key, None)

                    logger.info(
                        f"Client config saved successfully for CLIENT_{client_id} "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    return True
                else:
                    # File lock failed, retry
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Save failed (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {retry_delay}s: File is locked"
                        )
                        time.sleep(retry_delay)

            except OSError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Save failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    time.sleep(retry_delay)
                else:
                    error_msg = f"Failed to save client config after {max_retries} attempts: {e}"
                    logger.exception(error_msg)
                    raise ProfileManagerError(error_msg)

        # If we get here, all retries failed
        error_msg = f"Failed to save client config after {max_retries} attempts"
        logger.error(error_msg)
        raise ProfileManagerError(error_msg)

    def update_ui_settings(self, client_id: str, ui_settings: dict[str, Any]) -> bool:
        """Update client UI settings with partial updates support.

        Args:
            client_id: Client ID
            ui_settings: Dict with optional keys:
                - is_pinned (bool)
                - group_id (str | None)
                - custom_color (str)
                - custom_badges (List[str])
                - display_order (int)

        Returns:
            bool: True if saved successfully

        Raises:
            ProfileManagerError: If client doesn't exist or save fails

        Example:
            pm.update_ui_settings("M", {"is_pinned": True})
        """
        # Load current config
        config = self.load_client_config(client_id)
        if config is None:
            raise ProfileManagerError(f"Client profile not found: CLIENT_{client_id}")

        # Ensure ui_settings section exists
        if "ui_settings" not in config:
            config["ui_settings"] = {
                "is_pinned": False,
                "group_id": None,
                "custom_color": "#4CAF50",
                "custom_badges": [],
                "display_order": 0,
            }

        # Merge updates (partial update)
        for key, value in ui_settings.items():
            config["ui_settings"][key] = value

        # Save
        return self.save_client_config(client_id, config)

    def update_client_profile(
        self,
        client_id: str,
        name: str | None = None,
        ui_settings: dict[str, Any] | None = None,
    ) -> bool:
        """Update only the client-profile fields the caller owns.

        Loads fresh, merges the supplied keys, saves once. Callers holding a
        config they read minutes ago must go through this rather than writing
        that config back wholesale -- otherwise a pin toggle or group move made
        in between is silently reverted.

        Args:
            client_id: Client ID
            name: New client_name, or None to leave it alone
            ui_settings: Partial ui_settings to merge, or None

        Returns:
            bool: True if saved successfully

        Raises:
            ProfileManagerError: If the client doesn't exist or the save fails
        """
        config = self.load_client_config(client_id)
        if config is None:
            raise ProfileManagerError(f"Client profile not found: CLIENT_{client_id}")

        if name is not None:
            config["client_name"] = name

        if ui_settings:
            config.setdefault("ui_settings", self._get_default_ui_settings())
            config["ui_settings"].update(ui_settings)

        return self.save_client_config(client_id, config)

    def get_ui_settings(self, client_id: str) -> dict[str, Any]:
        """Get client UI settings.

        Returns default values if not set:
        {
            "is_pinned": False,
            "group_id": None,
            "custom_color": "#4CAF50",
            "custom_badges": [],
            "display_order": 0
        }

        Args:
            client_id: Client ID

        Returns:
            Dict with ui_settings
        """
        config = self.load_client_config(client_id)

        if config is None:
            # Return defaults if client doesn't exist
            return {
                "is_pinned": False,
                "group_id": None,
                "custom_color": "#4CAF50",
                "custom_badges": [],
                "display_order": 0,
            }

        # Return ui_settings or defaults
        return config.get(
            "ui_settings",
            {
                "is_pinned": False,
                "group_id": None,
                "custom_color": "#4CAF50",
                "custom_badges": [],
                "display_order": 0,
            },
        )

    def calculate_metadata(
        self, client_id: str, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Calculate client metadata from filesystem with 5-minute caching.

        Args:
            client_id: Client ID
            force_refresh: If True, bypass cache and recalculate

        Returns:
            Dict with total_sessions, last_session_date, last_accessed
        """
        import re
        import time

        client_id = client_id.upper()
        cache_key = f"CLIENT_{client_id}"

        # Check cache (unless force refresh)
        if not force_refresh and cache_key in self._metadata_cache:
            cached_data, cached_time = self._metadata_cache[cache_key]
            age_seconds = (datetime.now().astimezone() - cached_time).total_seconds()

            if age_seconds < self.METADATA_CACHE_TIMEOUT_SECONDS:
                logger.debug(
                    f"Metadata cache HIT for {cache_key} "
                    f"(age: {age_seconds:.1f}s, TTL: {self.METADATA_CACHE_TIMEOUT_SECONDS}s)"
                )
                return cached_data

        # Cache miss - calculate metadata
        start_time = time.time()
        sessions_dir = self.sessions_dir / cache_key

        if not sessions_dir.exists():
            metadata = {
                "total_sessions": 0,
                "last_session_date": None,
                "last_accessed": datetime.now().astimezone().isoformat(),
            }
            self._metadata_cache[cache_key] = (metadata, datetime.now().astimezone())
            return metadata

        try:
            session_folders = [
                d
                for d in sessions_dir.iterdir()
                if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_\d+", d.name)
            ]

            total_sessions = len(session_folders)

            last_session_date = None
            if session_folders:
                latest = max(session_folders, key=lambda d: d.name)
                date_part = latest.name.split("_")[0]
                last_session_date = date_part

            metadata = {
                "total_sessions": total_sessions,
                "last_session_date": last_session_date,
                "last_accessed": datetime.now().astimezone().isoformat(),
            }

            self._metadata_cache[cache_key] = (metadata, datetime.now().astimezone())

            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(f"Metadata calculated for {cache_key} in {elapsed_ms:.1f}ms")

            return metadata

        except Exception as e:
            logger.warning(f"Failed to calculate metadata for {cache_key}: {e}")
            metadata = {
                "total_sessions": 0,
                "last_session_date": None,
                "last_accessed": datetime.now().astimezone().isoformat(),
            }
            self._metadata_cache[cache_key] = (metadata, datetime.now().astimezone())
            return metadata

    def invalidate_metadata_cache(self, client_id: str | None = None):
        """Invalidate metadata cache.

        Args:
            client_id: Specific client to invalidate, or None to clear all
        """
        if client_id:
            cache_key = f"CLIENT_{client_id.upper()}"
            if cache_key in self._metadata_cache:
                del self._metadata_cache[cache_key]
                logger.debug(f"Invalidated metadata cache for {cache_key}")
        else:
            self._metadata_cache.clear()
            logger.debug("Cleared entire metadata cache")

    def update_last_accessed(self, client_id: str) -> bool:
        """Update last_accessed timestamp in metadata.

        Args:
            client_id: Client ID

        Returns:
            bool: True if updated successfully
        """
        config = self.load_client_config(client_id)
        if config is None:
            logger.warning(f"Cannot update last_accessed: CLIENT_{client_id} not found")
            return False

        # Ensure metadata section exists
        if "metadata" not in config:
            config["metadata"] = {}

        # Update timestamp
        config["metadata"]["last_accessed"] = datetime.now().astimezone().isoformat()

        # Save
        return self.save_client_config(client_id, config)

    def get_client_config_extended(self, client_id: str) -> dict[str, Any]:
        """Load client config with ui_settings and metadata merged.

        Automatically adds default ui_settings if missing.
        Calculates metadata on demand.

        Args:
            client_id: Client ID

        Returns:
            Dict with client_config.json + ui_settings + metadata
        """
        # Load base config
        config = self.load_client_config(client_id)

        if config is None:
            logger.warning(f"Client config not found: CLIENT_{client_id}")
            return {}

        # Ensure ui_settings exists (should be added by load_client_config migration)
        if "ui_settings" not in config:
            config["ui_settings"] = {
                "is_pinned": False,
                "group_id": None,
                "custom_color": "#4CAF50",
                "custom_badges": [],
                "display_order": 0,
            }

        # Calculate and add metadata
        config["metadata"] = self.calculate_metadata(client_id)

        return config

    def get_clients_root(self) -> Path:
        """Get path to clients root directory.

        Returns:
            Path: Path to Clients/ directory
        """
        return self.clients_dir

    def get_sessions_root(self) -> Path:
        """Get path to sessions root directory.

        Returns:
            Path: Path to Sessions/ directory
        """
        return self.sessions_dir

    def get_stats_path(self) -> Path:
        """Get path to statistics directory.

        Returns:
            Path: Path to Stats/ directory
        """
        return self.stats_dir

    def get_logs_path(self) -> Path:
        """Get path to logs directory.

        Returns:
            Path: Path to Logs/shopify_tool/ directory
        """
        return self.logs_dir

    def get_client_directory(self, client_id: str) -> Path:
        """Get path to client's directory.

        Args:
            client_id (str): Client ID

        Returns:
            Path: Path to client directory
        """
        client_id = client_id.upper()
        return self.clients_dir / f"CLIENT_{client_id}"

    def client_exists(self, client_id: str) -> bool:
        """Check if client profile exists.

        Args:
            client_id (str): Client ID

        Returns:
            bool: True if client exists
        """
        client_id = client_id.upper()
        client_dir = self.clients_dir / f"CLIENT_{client_id}"
        return client_dir.exists()
