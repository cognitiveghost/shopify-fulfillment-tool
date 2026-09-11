"""The contract between SettingsWindow and its pages."""

import json

from PySide6.QtWidgets import QWidget

UNCOLLECTABLE = "<uncollectable>"


class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. No page writes to
    disk by itself: Save is the one write, and Cancel discards.

    collect() returns {config_key: value}, and each value REPLACES
    config_data[key] outright -- the window does not merge. A page that
    owns a dict sub-tree must therefore mutate and return the live dict it
    was constructed with, so keys it does not render survive the save.
    Returning a freshly built dict silently drops them.

    collect() runs at any time, not only during a save: the window's
    unsaved check calls it every few hundred milliseconds. A page mutating
    its live dict mid-edit is fine -- config_data is a deep copy that only
    reaches disk through Save, which re-collects every page after all of
    them validate -- but collect() must have no other side effects.
    """

    def collect(self) -> dict:
        """The config keys this page owns. Each value replaces config_data[key]."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). A False here blocks the save."""
        return True, []

    def snapshot(self) -> str:
        """This page's values as one comparable string.

        Override only when collect() returns a dict another page also writes
        into (see _MappingPageBase): otherwise an edit on that page marks
        this one unsaved too.
        """
        return json.dumps(self.collect(), sort_keys=True, default=str)

    def mark_clean(self) -> None:
        """Take the current values as the ones the page opened with."""
        self._clean_snapshot = self._safe_snapshot()

    def is_dirty(self) -> bool:
        """Whether the values differ from the ones taken at mark_clean()."""
        clean = getattr(self, "_clean_snapshot", None)
        return clean is not None and self._safe_snapshot() != clean

    def _safe_snapshot(self) -> str:
        try:
            return self.snapshot()
        except Exception:
            # A half-typed value collect() cannot parse is still an unsaved edit.
            return UNCOLLECTABLE
