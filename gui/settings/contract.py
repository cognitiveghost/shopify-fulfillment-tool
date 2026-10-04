"""What SettingsWindow asks of a settings page, with no widget attached.

Every page is a draft: it meets this with no widget (gui/settings/
page_state.py and the *_state.py modules beside it), and its values are drawn
by the web page. No Qt import.
"""

import json

UNCOLLECTABLE = "<uncollectable>"


class FileProblem(Exception):
    """An import or export that failed in a way the operator can act on.

    The host shows `headline` and `detail` as they are. Any other exception
    is logged and shown as "Details are in Logs."
    """

    def __init__(self, headline: str, detail: str):
        super().__init__(headline)
        self.headline = headline
        self.detail = detail


class PageContract:
    """One page in the settings window.

    On save the window calls validate() then collect() on every page in turn.
    No page writes to disk by itself: Save is the one write, and Cancel
    discards.

    collect() returns {config_key: value}, and each value REPLACES
    config_data[key] outright -- the window does not merge. A page that
    owns a dict sub-tree must therefore mutate and return the live dict it
    was constructed with, so keys it does not render survive the save.
    Returning a freshly built dict silently drops them.

    collect() runs at any time, not only during a save: the window's
    unsaved check calls it after every edit. A page mutating
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

    def blocker(self) -> str | None:
        """What stops a save right now, as the words that fit
        "<blocker> in <page> to save."

        None when nothing does. Checked on every edit, so it must be cheap. A
        page whose checks are not cheap returns None and reports through
        validate() when Save is pressed.
        """
        return None

    def blocker_key(self) -> str:
        """The data-key of the control blocker() is about; "" when the page
        has none to point at."""
        return ""

    def snapshot(self) -> str:
        """This page's values as one comparable string.

        Override only when collect() returns a dict another page also writes
        into (see MappingDraft): otherwise an edit on that page marks this
        one unsaved too.
        """
        return json.dumps(self.collect(), sort_keys=True, default=str)

    def mark_clean(self, snapshot: str | None = None) -> None:
        """Take the current values as the ones the page opened with.

        After a save the window passes the snapshot it took when the write
        began, so an edit made while the write ran still reads unsaved.
        """
        self._clean_snapshot = self._safe_snapshot() if snapshot is None else snapshot

    def current_snapshot(self) -> str:
        """The values right now, for mark_clean() to take later."""
        return self._safe_snapshot()

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
