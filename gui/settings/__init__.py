"""Settings window and its pages.

The window (window.py) owns the left-nav, the page stack and saving; each
page module owns one settings surface and exposes it through SettingsPage.
"""

from gui.settings.window import SettingsWindow

__all__ = ["SettingsWindow"]
