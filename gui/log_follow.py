"""Whether the log viewer is following its own tail, and what it missed.

Pure state, no Qt: driving a real QScrollBar in a test proves the widget
scrolls, not that the rule is right. The rule is the part that breaks.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""


class FollowState:
    """Follow the newest entry, but only while the user is already there."""

    def __init__(self) -> None:
        self.following = True
        self.pending = 0

    def scrolled(self, at_bottom: bool) -> None:
        """The view's scrollbar moved. At the bottom means follow again."""
        self.following = at_bottom
        if at_bottom:
            self.pending = 0

    def appended(self) -> None:
        """An entry arrived. Counted only when the user is not watching."""
        if not self.following:
            self.pending += 1

    def jumped_to_latest(self) -> None:
        """The user pressed Jump to latest."""
        self.following = True
        self.pending = 0
