"""
Custom QComboBox that ignores wheel events to prevent accidental value changes.

This prevents users from accidentally changing combo box values when scrolling
through the window, which is a common UX issue in dense forms.
"""

import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QComboBox

logger = logging.getLogger(__name__)


class WheelIgnoreComboBox(QComboBox):
    """
    QComboBox subclass that ignores mouse wheel events.

    This prevents accidental value changes when the user scrolls through
    a form or window. The combo box will only change values when explicitly
    clicked and an item is selected.

    Usage:
        combo = WheelIgnoreComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3"])

    Benefits:
    - Prevents accidental filter changes in reports
    - Prevents accidental rule condition changes
    - Better UX in dense forms with many combo boxes
    - User must explicitly click to change value
    """

    def __init__(self, parent=None):
        """
        Initialize the wheel-ignoring combo box.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        # Enable focus policy to ensure proper keyboard navigation
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        """
        Override wheelEvent to ignore wheel scrolling.

        When the combo box has focus, we ignore the wheel event completely.
        This prevents the value from changing when scrolling through the form.

        Args:
            event: QWheelEvent from mouse wheel
        """
        # Ignore the wheel event completely
        event.ignore()
        logger.debug("Wheel event ignored on combo box")

    def focusInEvent(self, event):
        """
        Override focusInEvent to handle focus properly.

        We still want keyboard navigation to work, so we accept focus events.

        Args:
            event: QFocusEvent
        """
        super().focusInEvent(event)
        # Install event filter to catch wheel events even without focus
        self.installEventFilter(self)

    def focusOutEvent(self, event):
        """
        Override focusOutEvent to clean up.

        Args:
            event: QFocusEvent
        """
        super().focusOutEvent(event)
        # Remove event filter
        self.removeEventFilter(self)

    def eventFilter(self, obj, event):
        """
        Event filter to catch wheel events even without focus.

        Args:
            obj: Object that generated the event
            event: The event

        Returns:
            True if event should be filtered out, False otherwise
        """
        if obj == self and event.type() == QEvent.Wheel:
            # Block wheel events even when combo box doesn't have focus
            event.ignore()
            return True
        return super().eventFilter(obj, event)
