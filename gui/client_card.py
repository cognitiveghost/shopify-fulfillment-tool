"""Client Card Widget for sidebar display.

This widget displays an individual client as a card with metadata,
badges, and visual indicators for active state.
"""

import logging
from typing import Any

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from gui.theme_manager import get_theme_manager

logger = logging.getLogger(__name__)


class ClientCard(QWidget):
    """Individual client display card for sidebar.

    Displays:
    - Client name (bold if active)
    - Last session date
    - Session count
    - Custom badges

    Features:
    - Click → confirmation dialog → emit client_selected signal
    - Right-click → emit context_menu_requested signal
    - Active state: green 4px left border + bold name
    - Hover state: light gray background

    Signals:
        client_selected: Emitted when client is clicked (client_id: str)
        context_menu_requested: Emitted on right-click (client_id: str, position: QPoint)
    """

    client_selected = Signal(str)  # client_id
    context_menu_requested = Signal(str, QPoint)  # client_id, position

    def __init__(
        self,
        client_id: str,
        client_name: str,
        metadata: dict[str, Any],
        ui_settings: dict[str, Any],
        is_active: bool = False,
        parent=None
    ):
        """Initialize ClientCard.

        Args:
            client_id: Client ID (e.g., "M")
            client_name: Display name (e.g., "M Cosmetics")
            metadata: Dict with total_sessions, last_session_date, last_accessed
            ui_settings: Dict with is_pinned, custom_color, custom_badges
            is_active: Whether this is the currently active client
            parent: Parent widget
        """
        super().__init__(parent)
        self.client_id = client_id
        self.client_name = client_name
        self.metadata = metadata
        self.ui_settings = ui_settings
        self._is_active = is_active

        self.setFixedHeight(70)
        self.setCursor(Qt.PointingHandCursor)

        # Create layout
        self._setup_ui()

        # Connect to theme changes
        theme_manager = get_theme_manager()
        theme_manager.theme_changed.connect(self._update_style)

        # Apply initial style
        self._update_style()

    def _setup_ui(self):
        """Create widget layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Content layout (vertical)
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)

        # Row 1: Client name
        self.name_label = QLabel(f"CLIENT_{self.client_id}")
        # Font size set here, color will be set in _update_style()
        content_layout.addWidget(self.name_label)

        # Row 2: Last session date
        last_session = self.metadata.get("last_session_date")
        last_session_text = f"Last: {last_session}" if last_session else "Last: Never"
        self.last_session_label = QLabel(last_session_text)
        # Style will be set in _update_style()
        content_layout.addWidget(self.last_session_label)

        # Row 3: Sessions count + badges
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)

        total_sessions = self.metadata.get("total_sessions", 0)
        self.sessions_label = QLabel(f"Sessions: {total_sessions}")
        # Style will be set in _update_style()
        stats_layout.addWidget(self.sessions_label)

        # Add badges
        custom_badges = self.ui_settings.get("custom_badges", [])
        if custom_badges:
            badges_text = " ".join(custom_badges)
            self.badges_label = QLabel(badges_text)
            # Style will be set in _update_style()
            stats_layout.addWidget(self.badges_label)
        else:
            self.badges_label = None

        stats_layout.addStretch()
        content_layout.addLayout(stats_layout)

        main_layout.addLayout(content_layout, 1)

    def _update_style(self):
        """Update widget styling based on active/hover state and current theme."""
        theme = get_theme_manager().get_current_theme()

        # Base style with theme colors
        base_style = f"""
            ClientCard {{
                background-color: {theme.background_elevated};
                border-radius: 8px;
                color: {theme.text};
            }}
            ClientCard:hover {{
                background-color: {theme.hover};
            }}
        """

        # Add active state border
        if self._is_active:
            active_style = f"""
                ClientCard {{
                    border-left: 4px solid {theme.active_border};
                    background-color: {theme.active_background};
                }}
            """
            self.setStyleSheet(base_style + active_style)
            self.name_label.setStyleSheet(f"font-size: 12pt; font-weight: bold; color: {theme.text};")
        else:
            self.setStyleSheet(base_style)
            self.name_label.setStyleSheet(f"font-size: 12pt; color: {theme.text};")

        # Update secondary text colors
        self.last_session_label.setStyleSheet(f"font-size: 9pt; color: {theme.text_secondary};")
        self.sessions_label.setStyleSheet(f"font-size: 9pt; color: {theme.text_secondary};")

        # Update badge color (always orange accent)
        if self.badges_label:
            self.badges_label.setStyleSheet(f"font-size: 9pt; color: {theme.accent_orange}; font-weight: bold;")

    def set_active(self, is_active: bool):
        """Set active state.

        Args:
            is_active: Whether this client is active
        """
        if self._is_active != is_active:
            self._is_active = is_active
            self._update_style()

    def is_active(self) -> bool:
        """Get active state.

        Returns:
            bool: True if this client is active
        """
        return self._is_active

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse click events.

        Left-click: Show confirmation dialog, then emit client_selected
        Right-click: Emit context_menu_requested
        """
        if event.button() == Qt.LeftButton:
            # Show confirmation dialog
            reply = QMessageBox.question(
                self,
                "Switch Client",
                f"Switch to CLIENT_{self.client_id}?\n\n"
                f"This will clear the current session.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.client_selected.emit(self.client_id)

        elif event.button() == Qt.RightButton:
            # Emit context menu requested
            global_pos = self.mapToGlobal(event.pos())
            self.context_menu_requested.emit(self.client_id, global_pos)

        super().mousePressEvent(event)

    def update_metadata(self, metadata: dict[str, Any]):
        """Update metadata and refresh display.

        Args:
            metadata: New metadata dict
        """
        self.metadata = metadata

        # Update last session label
        last_session = metadata.get("last_session_date")
        last_session_text = f"Last: {last_session}" if last_session else "Last: Never"
        self.last_session_label.setText(last_session_text)

        # Update sessions count
        total_sessions = metadata.get("total_sessions", 0)
        self.sessions_label.setText(f"Sessions: {total_sessions}")

    def update_ui_settings(self, ui_settings: dict[str, Any]):
        """Update UI settings and refresh display.

        Args:
            ui_settings: New UI settings dict
        """
        self.ui_settings = ui_settings

        # Update badges
        custom_badges = ui_settings.get("custom_badges", [])
        if custom_badges:
            badges_text = " ".join(custom_badges)
            if self.badges_label:
                self.badges_label.setText(badges_text)
            else:
                # Create badges label if it didn't exist
                theme = get_theme_manager().get_current_theme()
                self.badges_label = QLabel(badges_text)
                self.badges_label.setStyleSheet(f"font-size: 9pt; color: {theme.accent_orange}; font-weight: bold;")
                # Add to stats layout (last child of content layout)
                content_layout = self.layout().itemAt(0).layout()
                stats_layout = content_layout.itemAt(2).layout()
                stats_layout.insertWidget(1, self.badges_label)
        else:
            if self.badges_label:
                self.badges_label.hide()
