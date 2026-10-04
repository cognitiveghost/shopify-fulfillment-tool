"""Settings window and its pages.

The window (window.py) owns the left-nav and saving. Each page is a draft
(page_state.py, rules_state.py, sets_state.py, weight_state.py,
reports_state.py, tags_state.py): its values with no widget, drawn by the web
tier through web_host.py and meeting PageContract (contract.py).
"""

from gui.settings.window import SettingsWindow

__all__ = ["SettingsWindow"]
