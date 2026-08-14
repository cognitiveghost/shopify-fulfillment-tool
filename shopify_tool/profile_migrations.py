"""Config migrations applied on load.

Split out of profile_manager.py, which was the largest backend file in the
repo. Each function mutates `config` in place and returns True when it
changed something -- the caller saves in that case.
"""

import copy
import logging
import os
from datetime import datetime

from shopify_tool.tag_manager import DEFAULT_TAG_CATEGORIES

logger = logging.getLogger(__name__)


def migrate_column_mappings_v1_to_v2(client_id: str, config: dict) -> bool:
    """Migrate column mappings from v1 to v2 format.

    V1 format (old):
        "column_mappings": {
            "orders_required": ["Order_Number", "SKU", ...],
            "stock_required": ["SKU", "Product_Name", ...]
        }

    V2 format (new):
        "column_mappings": {
            "version": 2,
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU", ...},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", ...}
        }

    Args:
        client_id (str): Client ID (for logging)
        config (Dict): Configuration dictionary to migrate (modified in-place)

    Returns:
        bool: True if migration was performed, False if already v2 or no column_mappings
    """
    if "column_mappings" not in config:
        logger.warning(f"No column_mappings found in config for CLIENT_{client_id}")
        return False

    column_mappings = config["column_mappings"]

    # Check if already v2
    if isinstance(column_mappings, dict) and "version" in column_mappings:
        version = column_mappings.get("version", 1)
        if version >= 2:
            logger.debug(f"Config already v{version} for CLIENT_{client_id}")
            return False

    # Check if v1 format (has orders_required/stock_required)
    is_v1 = (
        "orders_required" in column_mappings or "stock_required" in column_mappings
    )
    # A dict that already has 'orders'/'stock' mapping keys is v2-shaped --
    # it's just missing the 'version' tag (e.g. hand-edited, or written by
    # an older code path). Its real mapping must be preserved, not
    # silently discarded for the hardcoded default.
    looks_like_v2_shape = isinstance(column_mappings, dict) and (
        "orders" in column_mappings or "stock" in column_mappings
    )

    default_mappings = {
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
    }

    if is_v1:
        # True v1 format stores required-column lists, not an actual
        # field mapping -- the hardcoded default is the only sensible migration.
        logger.info(f"Migrating column mappings v1 → v2 for CLIENT_{client_id}")
        config["column_mappings"] = default_mappings
    elif looks_like_v2_shape:
        logger.info(
            f"Stamping missing 'version' on existing column_mappings for CLIENT_{client_id}"
        )
        column_mappings["version"] = 2
        config["column_mappings"] = column_mappings
    else:
        logger.warning(
            f"Unknown column_mappings format for CLIENT_{client_id}, applying default v2"
        )
        config["column_mappings"] = default_mappings

    # Add migration metadata
    config["_migration_info"] = {
        "migrated_at": datetime.now().astimezone().isoformat(),
        "from_version": 1,
        "to_version": 2,
        "migrated_by": os.environ.get("COMPUTERNAME", "Unknown"),
    }

    logger.info(f"Migration successful for CLIENT_{client_id}")
    return True


def migrate_add_tag_categories(client_id: str, config: dict) -> bool:
    """Add tag_categories to config if missing (creates v2 format).

    Args:
        client_id (str): Client ID (for logging)
        config (Dict): Configuration dictionary to migrate (modified in-place)

    Returns:
        bool: True if migration was performed, False if already exists
    """
    if "tag_categories" in config:
        logger.debug(f"tag_categories already exists for CLIENT_{client_id}")
        return False

    logger.info(
        f"Adding tag_categories (v2 format) to config for CLIENT_{client_id}"
    )

    # Add default tag categories in v2 format
    config["tag_categories"] = copy.deepcopy(DEFAULT_TAG_CATEGORIES)

    logger.info(f"Tag categories (v2) added for CLIENT_{client_id}")
    return True


def migrate_tag_categories_v1_to_v2(client_id: str, config: dict) -> bool:
    """Migrate tag_categories from v1 to v2 format.

    V1 format (old):
        "tag_categories": {
            "packaging": {"label": "...", "color": "...", "tags": []}
        }

    V2 format (new):
        "tag_categories": {
            "version": 2,
            "categories": {
                "packaging": {"label": "...", "color": "...", "tags": [], "order": 1, "sku_writeoff": {...}}
            }
        }

    Args:
        client_id (str): Client ID (for logging)
        config (Dict): Configuration dictionary to migrate (modified in-place)

    Returns:
        bool: True if migration was performed, False if already v2
    """
    tag_categories = config.get("tag_categories", {})

    # Check if already v2 format
    if "version" in tag_categories and tag_categories.get("version") == 2:
        logger.debug(f"tag_categories already in v2 format for CLIENT_{client_id}")
        return False

    if not tag_categories:
        logger.debug(f"No tag_categories to migrate for CLIENT_{client_id}")
        return False

    logger.info(f"Migrating tag_categories from v1 to v2 for CLIENT_{client_id}")

    # Migrate existing categories
    migrated_categories = {}
    order_counter = 1

    # Known categories with predefined order
    known_order = [
        "packaging",
        "priority",
        "status",
        "order_type",
        "accessories",
        "delivery",
        "custom",
    ]

    for category_id in known_order:
        if category_id in tag_categories:
            old_category = tag_categories[category_id]
            migrated_categories[category_id] = {
                "label": old_category.get("label", category_id.title()),
                "color": old_category.get("color", "#9E9E9E"),
                "order": order_counter,
                "tags": old_category.get("tags", []),
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
            order_counter += 1

    # Handle any custom categories not in known_order
    for category_id, category_config in tag_categories.items():
        if category_id not in migrated_categories and isinstance(
            category_config, dict
        ):
            migrated_categories[category_id] = {
                "label": category_config.get("label", category_id.title()),
                "color": category_config.get("color", "#9E9E9E"),
                "order": order_counter,
                "tags": category_config.get("tags", []),
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
            order_counter += 1
            logger.info(
                f"Migrated custom category '{category_id}' for CLIENT_{client_id}"
            )

    # Add new default categories if missing
    _defaults = DEFAULT_TAG_CATEGORIES["categories"]
    for category_id in ("order_type", "accessories", "delivery"):
        if category_id not in migrated_categories:
            migrated_categories[category_id] = copy.deepcopy(_defaults[category_id])
            migrated_categories[category_id]["order"] = order_counter
            order_counter += 1
            logger.info(f"Added '{category_id}' category for CLIENT_{client_id}")

    # Wrap in v2 structure
    config["tag_categories"] = {"version": 2, "categories": migrated_categories}

    logger.info(
        f"Tag categories migration to v2 successful for CLIENT_{client_id}: "
        f"{len(migrated_categories)} categories"
    )
    return True


def migrate_delimiter_config_v1_to_v2(client_id: str, config: dict) -> bool:
    """Migrate delimiter configuration from v1 to v2 format.

    V1 format (old):
        "settings": {
            "stock_delimiter": ";"
        }

    V2 format (new):
        "settings": {
            "stock_csv_delimiter": ";",
            "orders_csv_delimiter": ","
        }

    Args:
        client_id (str): Client ID (for logging)
        config (Dict): Configuration dictionary to migrate (modified in-place)

    Returns:
        bool: True if migration was performed, False if already v2
    """
    if "settings" not in config:
        logger.debug(f"No settings found in config for CLIENT_{client_id}")
        return False

    settings = config["settings"]
    migrated = False

    # Migrate stock_delimiter → stock_csv_delimiter
    if "stock_delimiter" in settings:
        if "stock_csv_delimiter" not in settings:
            settings["stock_csv_delimiter"] = settings["stock_delimiter"]
            logger.info(
                f"Migrated 'stock_delimiter' to 'stock_csv_delimiter' for CLIENT_{client_id}"
            )
            migrated = True
        del settings["stock_delimiter"]
        logger.info(f"Removed old 'stock_delimiter' key for CLIENT_{client_id}")
        migrated = True

    # Add orders_csv_delimiter if missing (with default value)
    if "orders_csv_delimiter" not in settings:
        settings["orders_csv_delimiter"] = ","
        logger.info(f"Added default 'orders_csv_delimiter' for CLIENT_{client_id}")
        migrated = True

    # Update config version if migration occurred
    if migrated:
        config["config_version"] = "2.1"
        config["migrated_at"] = datetime.now().astimezone().isoformat()
        logger.info(
            f"Delimiter migration successful for CLIENT_{client_id}, version: 2.1"
        )

    return migrated


def migrate_add_weight_config(client_id: str, config: dict) -> bool:
    """Add weight_config section if missing (new feature migration).

    Returns:
        bool: True if migration was performed, False if already present
    """
    if "weight_config" in config:
        return False

    config["weight_config"] = {
        "volumetric_divisor": 6000,
        "products": {},
        "boxes": [],
    }
    logger.info(f"Added default 'weight_config' for CLIENT_{client_id}")
    return True


def migrate_add_inventory_memory(client_id: str, config: dict) -> bool:
    """Add inventory_memory section if missing (new feature migration).

    Returns:
        bool: True if migration was performed, False if already present
    """
    if "inventory_memory" not in config:
        config["inventory_memory"] = {
            "enabled": False,
            "skus": {},
            "names": {},
            "last_updated": None,
            "total_units": 0,
        }
        logger.info(f"Added default 'inventory_memory' for CLIENT_{client_id}")
        return True

    # Backfill 'names' for configs saved before per-SKU name tracking existed.
    if "names" not in config["inventory_memory"]:
        config["inventory_memory"]["names"] = {}
        logger.info(f"Backfilled 'inventory_memory.names' for CLIENT_{client_id}")
        return True

    return False
