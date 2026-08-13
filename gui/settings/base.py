"""The contract between SettingsWindow and its pages."""

from PySide6.QtWidgets import QWidget


class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. Pages that
    persist their own data immediately (Sets, Column Config) inherit both
    defaults and contribute nothing to the window's single write.

    collect() returns {config_key: value}, and each value REPLACES
    config_data[key] outright -- the window does not merge. A page that
    owns a dict sub-tree must therefore mutate and return the live dict it
    was constructed with, so keys it does not render survive the save.
    Returning a freshly built dict silently drops them.

    collect() writing into config_data before the window assigns is safe by
    construction: save_settings() runs validate() across every page before
    calling collect() on any of them, so no page mutates during a save a
    later page will block. config_data is a deep copy, so a failed server
    write cannot reach the caller's config either.
    """

    def collect(self) -> dict:
        """The config keys this page owns. Each value replaces config_data[key]."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). A False here blocks the save."""
        return True, []
