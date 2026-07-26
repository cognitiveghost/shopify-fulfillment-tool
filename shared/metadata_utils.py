"""
Metadata Utilities

Shared functions for metadata handling across the application.
Provides standardized timestamp handling and backward compatibility loaders.

Version: 1.3.0
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_current_timestamp() -> str:
    """Get current timestamp in ISO 8601 format with timezone

    Returns:
        str: Timestamp like "2025-11-20T14:15:00+02:00"

    Example:
        >>> ts = get_current_timestamp()
        >>> print(ts)
        "2025-11-20T14:15:00+02:00"
    """
    return datetime.now().astimezone().isoformat()


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO timestamp to datetime object

    Handles both timezone-aware and timezone-naive timestamps for
    backward compatibility. Always returns timezone-aware datetime.

    Args:
        timestamp_str: ISO 8601 timestamp

    Returns:
        datetime (timezone-aware) or None if invalid

    Example:
        >>> dt = parse_timestamp("2025-11-20T14:15:00+02:00")
        >>> print(dt)
        datetime.datetime(2025, 11, 20, 14, 15, 0, tzinfo=...)
    """
    if not timestamp_str:
        return None

    try:
        dt = datetime.fromisoformat(timestamp_str)
        # If naive (no timezone), assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        # Try without timezone for backward compat
        try:
            # Handle 'Z' suffix (UTC)
            if timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # Try parsing without timezone (assume UTC)
            dt = datetime.fromisoformat(timestamp_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse timestamp '{timestamp_str}': {e}")
            return None


def calculate_duration(start: str, end: str) -> int:
    """Calculate duration between two timestamps

    Args:
        start: Start timestamp (ISO 8601)
        end: End timestamp (ISO 8601)

    Returns:
        int: Duration in seconds, or 0 if parsing fails

    Example:
        >>> duration = calculate_duration(
        ...     "2025-11-20T10:00:00+02:00",
        ...     "2025-11-20T12:30:00+02:00"
        ... )
        >>> print(duration)
        9000
    """
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)

    if not start_dt or not end_dt:
        return 0

    return int((end_dt - start_dt).total_seconds())


def load_session_summary(path: Path) -> Dict[str, Any]:
    """Load session summary in v1.3.0 format

    Args:
        path: Path to session_summary.json

    Returns:
        dict: Session summary in v1.3.0 format

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If file is not in v1.3.0 format

    Example:
        >>> summary = load_session_summary(Path("session_summary.json"))
        >>> print(summary['version'])
        "1.3.0"
    """
    if not path.exists():
        raise FileNotFoundError(f"Session summary not found: {path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Corrupted session summary at {path}: {e}")
        raise

    # Check version
    version = data.get('version')
    if version != '1.3.0':
        raise ValueError(f"Unsupported session summary version: {version}. Expected v1.3.0")

    # Validate structure and ensure all fields present
    logger.debug(f"Loading session summary v1.3.0 from {path}")
    validated = _validate_v1_3_0_format(data)

    return validated


def _validate_v1_3_0_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and fill missing fields in v1.3.0 format

    Args:
        data: Session summary data

    Returns:
        dict: Validated data with default values for missing fields
    """
    # Required fields with defaults
    defaults = {
        'version': '1.3.0',
        'session_id': '',
        'session_type': 'unknown',
        'client_id': '',
        'packing_list_name': '',
        'worker_id': None,
        'worker_name': 'Unknown',
        'pc_name': '',
        'started_at': '',
        'completed_at': '',
        'duration_seconds': 0,
        'total_orders': 0,
        'completed_orders': 0,
        'total_items': 0,
        'unique_skus': 0,
        'metrics': {
            'avg_time_per_order': 0,
            'avg_time_per_item': 0,
            'fastest_order_seconds': 0,
            'slowest_order_seconds': 0,
            'orders_per_hour': 0,
            'items_per_hour': 0
        },
        'orders': []
    }

    # Fill missing fields with defaults
    for key, default_value in defaults.items():
        if key not in data:
            data[key] = default_value

    # Ensure metrics has all required fields
    if isinstance(data.get('metrics'), dict):
        for metric_key, metric_default in defaults['metrics'].items():
            if metric_key not in data['metrics']:
                data['metrics'][metric_key] = metric_default
    else:
        data['metrics'] = defaults['metrics']

    return data
