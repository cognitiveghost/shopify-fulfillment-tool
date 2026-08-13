"""The contract between SettingsWindow and its pages."""

from PySide6.QtWidgets import QWidget


class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. Pages that
    persist their own data immediately (Sets, Column Config) inherit both
    defaults and contribute nothing to the window's single write.
    """

    def collect(self) -> dict:
        """The config keys this page owns, merged into config_data on save."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). A False here blocks the save."""
        return True, []
