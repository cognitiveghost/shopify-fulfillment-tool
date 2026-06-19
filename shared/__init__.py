"""
Shared modules for Shopify Fulfillment Tool and Packing Tool.

This package contains unified components that work identically in both tools,
ensuring consistency and reducing code duplication.

Phase 1.4: Unified Statistics System
"""

from .stats_manager import StatsManager, StatsManagerError

# FileLockError removed — DB backend uses transactions instead of file locks
FileLockError = StatsManagerError  # alias kept for any stale import sites

__all__ = [
    'StatsManager',
    'StatsManagerError',
    'FileLockError',
]

__version__ = '1.0.0'
