"""
Shared modules for Shopify Fulfillment Tool and Packing Tool.

This package contains unified components that work identically in both
tools. Canonical copy lives in packing-tool/shared/; synced into
shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py.
"""

from .file_lock import FileLockError
from .stats_manager import StatsManager, StatsManagerError

__all__ = [
    'FileLockError',
    'StatsManager',
    'StatsManagerError',
]

__version__ = '2.0.0'
