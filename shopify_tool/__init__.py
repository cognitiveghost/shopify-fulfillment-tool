"""
Shopify Fulfillment Tool

Version: 1.8.9.6
"""

__version__ = "1.8.9.6"

from .logger_config import setup_logging

# Ensure logging is configured as soon as the package is imported
setup_logging()
