"""Tag management utilities for Internal_Tags column."""

import hashlib
import json
from functools import lru_cache

import pandas as pd

DEFAULT_TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "packaging": {
            "label": "Packaging",
            "color": "#4CAF50",
            "order": 1,
            "tags": ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "priority": {
            "label": "Priority",
            "color": "#FF9800",
            "order": 2,
            "tags": ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "status": {
            "label": "Status",
            "color": "#2196F3",
            "order": 3,
            "tags": ["CHECKED", "PROBLEM", "VERIFIED"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "order_type": {
            "label": "Order Type",
            "color": "#9C27B0",
            "order": 4,
            "tags": ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "accessories": {
            "label": "Accessories",
            "color": "#E91E63",
            "order": 5,
            "tags": ["STICKER", "BUSINESS_CARD", "GIFT_BOX"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "delivery": {
            "label": "Delivery",
            "color": "#FF5722",
            "order": 6,
            "tags": [],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        # ponytail: 'custom' is the fallback bucket get_tag_category() returns
        # for any unrecognized tag. order 999 keeps it last; the dialog's order
        # spinbox maxes out at 999, so do not raise this value.
        "custom": {
            "label": "Other",
            "color": "#9E9E9E",
            "order": 999,
            "tags": [],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
    },
}


def parse_tags(tags_value) -> list[str]:
    """
    Parse Internal_Tags value to list.

    Args:
        tags_value: String, list, or NaN

    Returns:
        List of tag strings
    """
    # Check list first (before pd.isna which fails on lists)
    if isinstance(tags_value, list):
        return tags_value

    if pd.isna(tags_value) or tags_value == "":
        return []

    if isinstance(tags_value, str):
        try:
            # Try parsing as JSON
            parsed = json.loads(tags_value)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            pass

    return []


def serialize_tags(tags: list[str]) -> str:
    """
    Serialize tag list to JSON string.

    Args:
        tags: List of tag strings

    Returns:
        JSON string representation
    """
    if not tags:
        return "[]"

    # Remove duplicates while preserving order
    unique_tags = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)

    return json.dumps(unique_tags)


def merge_tags(tags_values: list) -> str:
    """
    Merge Internal_Tags values from multiple rows (e.g. an order's line
    items) into one deduped JSON string.

    Each value may be anything parse_tags() accepts (native list or JSON
    string) -- callers must not hand-roll string splitting on these values,
    since they're serialized lists, not flat comma-separated text.

    Args:
        tags_values: Internal_Tags values from the rows to merge

    Returns:
        JSON string representation (see serialize_tags)
    """
    merged = []
    for value in tags_values:
        for tag in parse_tags(value):
            if tag not in merged:
                merged.append(tag)

    return serialize_tags(merged)


def add_tag(current_tags_value, new_tag: str) -> str:
    """
    Add tag to existing tags (prevents duplicates).

    Args:
        current_tags_value: Current Internal_Tags value
        new_tag: Tag to add

    Returns:
        Updated JSON string
    """
    tags = parse_tags(current_tags_value)

    if new_tag not in tags:
        tags.append(new_tag)

    return serialize_tags(tags)


def remove_tag(current_tags_value, tag_to_remove: str) -> str:
    """
    Remove tag from existing tags.

    Args:
        current_tags_value: Current Internal_Tags value
        tag_to_remove: Tag to remove

    Returns:
        Updated JSON string
    """
    tags = parse_tags(current_tags_value)

    if tag_to_remove in tags:
        tags.remove(tag_to_remove)

    return serialize_tags(tags)


def has_tag(tags_value, tag: str) -> bool:
    """Check if tags contain specific tag."""
    tags = parse_tags(tags_value)
    return tag in tags


def expand_to_order_rows(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Expand a row mask to cover every row of every order it touches.

    Internal_Tags is order-level, not line-level, but ``df`` has one row per
    order line -- callers that only know about a subset of an order's rows
    (a single clicked SKU line, a rule match on one line, etc.) must expand
    to the full order before writing Internal_Tags, or different lines of
    the same order end up with inconsistent tags.

    Args:
        df: DataFrame with an "Order_Number" column.
        mask: Boolean row mask (any subset of df's rows).

    Returns:
        Boolean mask covering every row whose Order_Number matches at least
        one row in the input mask.
    """
    order_numbers = df.loc[mask, "Order_Number"].unique()
    return df["Order_Number"].isin(order_numbers)


def get_tag_category(tag: str, tag_categories: dict) -> str | None:
    """
    Determine category of a tag.

    Args:
        tag: Tag string
        tag_categories: Config dict with tag categories (v1 or v2 format)

    Returns:
        Category name or "custom" if not found
    """
    # Normalize to handle both v1 and v2 formats
    categories = _normalize_tag_categories(tag_categories)

    for category, config in categories.items():
        if tag in config.get("tags", []):
            return category

    return "custom"


def get_tag_color(tag: str, tag_categories: dict) -> str:
    """
    Get display color for a tag.

    Args:
        tag: Tag string
        tag_categories: Config dict with tag categories (v1 or v2 format)

    Returns:
        Hex color code
    """
    # Normalize to handle both v1 and v2 formats
    categories = _normalize_tag_categories(tag_categories)

    category = get_tag_category(tag, tag_categories)
    return categories.get(category, {}).get("color", "#9E9E9E")


# ============================================================================
# V2 Format Support & Performance Optimization
# ============================================================================


def get_config_hash(tag_categories: dict) -> str:
    """
    Generate stable hash of tag_categories config for cache invalidation.

    Args:
        tag_categories: Config dict with tag categories

    Returns:
        MD5 hash of sorted config JSON
    """
    # Sort keys for stable hash
    config_str = json.dumps(tag_categories, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()


def _normalize_tag_categories(tag_categories: dict) -> dict:
    """
    Normalize tag_categories to always return v2 format.

    Handles both v1 and v2 formats:
    - v1: {"category": {"label": ..., "tags": []}}
    - v2: {"version": 2, "categories": {"category": {"label": ..., "tags": []}}}

    Args:
        tag_categories: Config dict (v1 or v2)

    Returns:
        Dict in v2 format (categories only)
    """
    if not tag_categories:
        return {}

    # Check if v2 format
    if "version" in tag_categories and "categories" in tag_categories:
        return tag_categories["categories"]

    # v1 format - return as is (it's already the categories dict)
    return tag_categories


@lru_cache(maxsize=512)
def get_tag_category_cached(tag: str, config_hash: str, config_json: str) -> str | None:
    """
    Cached version of get_tag_category for performance.

    Args:
        tag: Tag string
        config_hash: Hash from get_config_hash() for cache invalidation
        config_json: JSON string of tag_categories config

    Returns:
        Category name or "custom" if not found
    """
    # Parse config from JSON (needed because dicts aren't hashable)
    tag_categories = json.loads(config_json)
    categories = _normalize_tag_categories(tag_categories)

    for category_id, config in categories.items():
        if tag in config.get("tags", []):
            return category_id

    return "custom"


def get_category_tags(category_id: str, tag_categories: dict) -> list[str]:
    """
    Get list of tags for a specific category.

    Args:
        category_id: Category identifier
        tag_categories: Config dict with tag categories (v1 or v2)

    Returns:
        List of tag strings in the category
    """
    categories = _normalize_tag_categories(tag_categories)
    return categories.get(category_id, {}).get("tags", [])


def validate_tag_categories_v2(config: dict) -> tuple[bool, list[str]]:
    """
    Validate tag_categories v2 structure.

    Checks:
    - Has "version" and "categories" keys
    - No duplicate tags across categories
    - Each category has required fields (label, color, tags, order)
    - Colors are valid hex codes

    Args:
        config: tag_categories dict to validate

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []

    # Check v2 structure
    if "version" not in config:
        errors.append("Missing 'version' field in tag_categories")

    if "categories" not in config:
        errors.append("Missing 'categories' field in tag_categories")
        return False, errors

    categories = config["categories"]

    if not isinstance(categories, dict):
        errors.append("'categories' must be a dictionary")
        return False, errors

    # Track tags to check for duplicates
    tag_to_category = {}

    # Validate each category
    for category_id, category_config in categories.items():
        if not isinstance(category_config, dict):
            errors.append(f"Category '{category_id}' config must be a dictionary")
            continue

        # Check required fields
        required_fields = ["label", "color", "tags", "order"]
        for field in required_fields:
            if field not in category_config:
                errors.append(f"Category '{category_id}' missing required field '{field}'")

        # Only when present -- a missing label is already reported above, and
        # reporting it twice just makes the dialog's error box noisier.
        label = category_config.get("label")
        if "label" in category_config and (not isinstance(label, str) or not label.strip()):
            errors.append(f"Category '{category_id}' has an empty label")

        # Validate color format (basic check)
        color = category_config.get("color", "")
        if color and not (color.startswith("#") and len(color) == 7):
            errors.append(f"Category '{category_id}' has invalid color format: {color}")

        # Validate tags
        tags = category_config.get("tags", [])
        if not isinstance(tags, list):
            errors.append(f"Category '{category_id}' tags must be a list")
            continue

        # Check for duplicate tags
        for tag in tags:
            if tag in tag_to_category:
                errors.append(
                    f"Duplicate tag '{tag}' found in categories "
                    f"'{tag_to_category[tag]}' and '{category_id}'"
                )
            else:
                tag_to_category[tag] = category_id

        # Validate order is int
        order = category_config.get("order")
        if order is not None and not isinstance(order, int):
            errors.append(f"Category '{category_id}' order must be an integer")

        # Validate sku_writeoff structure if present
        sku_writeoff = category_config.get("sku_writeoff", {})
        if sku_writeoff:
            if not isinstance(sku_writeoff, dict):
                errors.append(f"Category '{category_id}' sku_writeoff must be a dictionary")
            else:
                if "enabled" not in sku_writeoff:
                    errors.append(f"Category '{category_id}' sku_writeoff missing 'enabled' field")

                mappings = sku_writeoff.get("mappings", {})
                if not isinstance(mappings, dict):
                    errors.append(f"Category '{category_id}' sku_writeoff mappings must be a dictionary")
                else:
                    # Validate each mapping
                    for tag, sku_list in mappings.items():
                        if not isinstance(sku_list, list):
                            errors.append(
                                f"Category '{category_id}' sku_writeoff mapping for tag '{tag}' "
                                f"must be a list"
                            )
                            continue

                        for sku_item in sku_list:
                            if not isinstance(sku_item, dict):
                                errors.append(
                                    f"Category '{category_id}' sku_writeoff item for tag '{tag}' "
                                    f"must be a dictionary"
                                )
                                continue

                            if "sku" not in sku_item:
                                errors.append(
                                    f"Category '{category_id}' sku_writeoff item for tag '{tag}' "
                                    f"missing 'sku' field"
                                )

                            if "quantity" not in sku_item:
                                errors.append(
                                    f"Category '{category_id}' sku_writeoff item for tag '{tag}' "
                                    f"missing 'quantity' field"
                                )
                            elif not isinstance(sku_item["quantity"], (int, float)):
                                errors.append(
                                    f"Category '{category_id}' sku_writeoff item for tag '{tag}' "
                                    f"quantity must be a number"
                                )
                            elif sku_item["quantity"] <= 0:
                                errors.append(
                                    f"Category '{category_id}' sku_writeoff item for tag '{tag}' "
                                    f"quantity must be positive"
                                )

    return len(errors) == 0, errors
