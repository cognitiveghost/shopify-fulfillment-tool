"""The contract between SettingsWindow and its Qt pages."""

from PySide6.QtWidgets import QWidget

from gui.settings.contract import UNCOLLECTABLE, PageContract

__all__ = ["UNCOLLECTABLE", "SettingsPage"]


class SettingsPage(PageContract, QWidget):
    """A settings page that is a widget: the window shows it in the nav stack.

    Everything the window asks of it is PageContract (gui/settings/contract.py).
    """
