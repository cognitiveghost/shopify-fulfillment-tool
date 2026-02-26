"""Client Settings Dialog for editing client profiles.

This module provides dialogs for creating and editing client profiles with
tabbed interface for Basic Info, Appearance, Statistics, and Advanced settings.
"""

import logging
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox,
    QDialog, QVBoxLayout, QLineEdit, QDialogButtonBox, QFormLayout,
    QTabWidget, QCheckBox, QColorDialog, QTextEdit
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor

from shopify_tool.profile_manager import ProfileManager, ValidationError, ProfileManagerError
from shopify_tool.groups_manager import GroupsManager
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from gui.theme_manager import get_theme_manager


logger = logging.getLogger(__name__)


class ClientCreationDialog(QDialog):
    """Dialog for creating a new client profile."""

    def __init__(
        self,
        profile_manager: ProfileManager,
        groups_manager: Optional[GroupsManager] = None,
        parent=None
    ):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.groups_manager = groups_manager
        self.setWindowTitle("Create New Client")
        self.setModal(True)
        self.setMinimumWidth(400)

        # Create layout
        layout = QVBoxLayout(self)

        # Form layout for inputs
        form_layout = QFormLayout()

        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("e.g., M, A, B")
        self.client_id_input.setToolTip(
            "Client ID (letters, numbers, underscore only)\n"
            "Max 20 characters\n"
            "Don't include 'CLIENT_' prefix"
        )
        form_layout.addRow("Client ID:", self.client_id_input)

        self.client_name_input = QLineEdit()
        self.client_name_input.setPlaceholderText("e.g., M Cosmetics")
        self.client_name_input.setToolTip("Full name of the client")
        form_layout.addRow("Client Name:", self.client_name_input)

        # Group dropdown
        self.group_combo = QComboBox()
        self.group_combo.addItem("(No group)", None)
        self.group_combo.setToolTip("Assign client to a group")
        form_layout.addRow("Group:", self.group_combo)

        # Color picker
        color_layout = QHBoxLayout()
        self.color_display = QLabel()
        self.color_display.setFixedSize(40, 30)
        theme = get_theme_manager().get_current_theme()
        self.color_display.setStyleSheet(f"border: 1px solid {theme.border}; background-color: #4CAF50;")
        color_layout.addWidget(self.color_display)

        self.color_button = QPushButton("Choose Color")
        self.color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()

        self.current_color = "#4CAF50"  # Default
        form_layout.addRow("Color:", color_layout)

        # Pin checkbox
        self.pin_checkbox = QCheckBox("Pin to top of sidebar")
        form_layout.addRow("Pinned:", self.pin_checkbox)

        layout.addLayout(form_layout)

        # Load groups (will disable combo if manager not provided)
        self._load_groups()

        # Add info label
        info_label = QLabel(
            "This will create a new client profile with default Shopify configuration.\n"
            "You can customize it later in Profile Settings."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10pt; padding: 10px;")
        layout.addWidget(info_label)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _choose_color(self):
        """Open color picker dialog."""
        current_color = QColor(self.current_color)
        color = QColorDialog.getColor(current_color, self, "Choose Client Color")

        if color.isValid():
            self.current_color = color.name()
            self.color_display.setStyleSheet(
                f"background-color: {self.current_color}; border: 1px solid #ccc;"
            )

    def _load_groups(self):
        """Load available groups into dropdown."""
        if not self.groups_manager:
            self.group_combo.setEnabled(False)
            return

        groups = self.groups_manager.list_groups()
        for group in groups:
            self.group_combo.addItem(
                group.get("name", "Unknown"),
                group.get("id")
            )

    def validate_and_accept(self):
        """Validate inputs and create client profile."""
        client_id = self.client_id_input.text().strip()
        client_name = self.client_name_input.text().strip()

        # Validate inputs
        if not client_id:
            QMessageBox.warning(self, "Validation Error", "Client ID is required.")
            return

        if not client_name:
            QMessageBox.warning(self, "Validation Error", "Client Name is required.")
            return

        # Validate client ID format
        is_valid, error_msg = ProfileManager.validate_client_id(client_id)
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", error_msg)
            return

        # Try to create client profile
        try:
            success = self.profile_manager.create_client_profile(client_id, client_name)
            if success:
                # Update ui_settings with optional fields
                ui_settings = {
                    "is_pinned": self.pin_checkbox.isChecked(),
                    "group_id": self.group_combo.currentData(),
                    "custom_color": self.current_color,
                    "custom_badges": [],
                    "display_order": 0
                }
                self.profile_manager.update_ui_settings(client_id, ui_settings)

                QMessageBox.information(
                    self,
                    "Success",
                    f"Client profile 'CLIENT_{client_id.upper()}' created successfully!"
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Profile Exists",
                    f"Client profile 'CLIENT_{client_id.upper()}' already exists."
                )
        except (ValidationError, ProfileManagerError) as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create client profile:\n{str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error creating client: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred:\n{str(e)}"
            )


class ClientSelectorWidget(QWidget):
    """Widget for selecting active client and managing client profiles.

    Provides:
    - Dropdown to select active client
    - "Manage Clients" button to create new clients
    - Signal when client selection changes

    Signals:
        client_changed: Emitted when client selection changes (client_id: str)
    """

    client_changed = Signal(str)  # Emits client_id

    def __init__(self, profile_manager: ProfileManager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.current_client_id = None

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Label
        label = QLabel("Client:")
        label.setToolTip("Select the active client")
        layout.addWidget(label)

        # Client dropdown
        self.client_combo = WheelIgnoreComboBox()
        self.client_combo.setMinimumWidth(150)
        self.client_combo.setToolTip("Select active client to work with")
        self.client_combo.currentTextChanged.connect(self._on_client_changed)
        layout.addWidget(self.client_combo, 1)

        # Manage clients button
        self.manage_btn = QPushButton("Manage Clients")
        self.manage_btn.setToolTip("Create or manage client profiles")
        self.manage_btn.clicked.connect(self._open_manage_dialog)
        layout.addWidget(self.manage_btn)

        # Load clients
        self.refresh_clients()

        logger.info("ClientSelectorWidget initialized")

    def refresh_clients(self):
        """Reload client list from profile manager."""
        try:
            # Save current selection
            current_client = self.client_combo.currentText()

            # Block signals to avoid triggering client_changed multiple times
            self.client_combo.blockSignals(True)
            self.client_combo.clear()

            # Load clients
            clients = self.profile_manager.list_clients()

            if not clients:
                self.client_combo.addItem("(No clients available)")
                self.client_combo.setEnabled(False)
                logger.warning("No clients found on file server")
            else:
                self.client_combo.addItems(clients)
                self.client_combo.setEnabled(True)

                # Restore previous selection if it still exists
                if current_client in clients:
                    self.client_combo.setCurrentText(current_client)

            # Re-enable signals
            self.client_combo.blockSignals(False)

            # Manually trigger client changed if we have clients
            if clients:
                self._on_client_changed(self.client_combo.currentText())

        except Exception as e:
            logger.error(f"Failed to refresh clients: {e}", exc_info=True)
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to load clients from server:\n{str(e)}"
            )

    def _on_client_changed(self, client_id: str):
        """Handle client selection change."""
        if not client_id or client_id == "(No clients available)":
            return

        if client_id != self.current_client_id:
            self.current_client_id = client_id
            logger.info(f"Client changed to: {client_id}")
            self.client_changed.emit(client_id)

    def _open_manage_dialog(self):
        """Open dialog for managing clients."""
        dialog = ClientCreationDialog(self.profile_manager, self)
        if dialog.exec():
            # Refresh client list after successful creation
            self.refresh_clients()

    def get_current_client_id(self) -> str:
        """Get currently selected client ID.

        Returns:
            str: Current client ID or empty string if none selected
        """
        text = self.client_combo.currentText()
        if text == "(No clients available)":
            return ""
        return text

    def set_current_client_id(self, client_id: str):
        """Set the currently selected client.

        Args:
            client_id: Client ID to select
        """
        index = self.client_combo.findText(client_id)
        if index >= 0:
            self.client_combo.setCurrentIndex(index)


class ClientSettingsDialog(QDialog):
    """Dialog for editing client settings with tabbed interface.

    Features:
    - Basic Info tab: Name, Shopify config
    - Appearance tab: Pin checkbox, Group selector, Color picker, Badges
    - Statistics tab: Readonly stats (sessions, last session)
    - Advanced tab: Column mappings, rules (placeholder for future)
    """

    def __init__(
        self,
        client_id: str,
        profile_manager: ProfileManager,
        groups_manager: Optional[GroupsManager] = None,
        parent=None
    ):
        """Initialize ClientSettingsDialog.

        Args:
            client_id: Client ID to edit
            profile_manager: ProfileManager instance
            groups_manager: Optional GroupsManager for group selection
            parent: Parent widget
        """
        super().__init__(parent)
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.groups_manager = groups_manager

        self.setWindowTitle(f"Client Settings - CLIENT_{client_id}")
        self.setModal(True)
        self.setMinimumSize(600, 500)

        # Load config
        self.config = self.profile_manager.load_client_config(client_id)
        if not self.config:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load config for CLIENT_{client_id}"
            )
            self.reject()
            return

        self.shopify_config = self.profile_manager.load_shopify_config(client_id)
        self.ui_settings = self.config.get("ui_settings", {})
        self.metadata = self.profile_manager.calculate_metadata(client_id)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        """Create dialog layout with tabs."""
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()

        # Tab 1: Basic Info
        self.basic_tab = self._create_basic_tab()
        self.tabs.addTab(self.basic_tab, "Basic Info")

        # Tab 2: Appearance
        self.appearance_tab = self._create_appearance_tab()
        self.tabs.addTab(self.appearance_tab, "Appearance")

        # Tab 3: Statistics
        self.statistics_tab = self._create_statistics_tab()
        self.tabs.addTab(self.statistics_tab, "Statistics")

        # Tab 4: Advanced (placeholder)
        self.advanced_tab = self._create_advanced_tab()
        self.tabs.addTab(self.advanced_tab, "Advanced")

        layout.addWidget(self.tabs)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_basic_tab(self) -> QWidget:
        """Create Basic Info tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Client ID (readonly)
        self.client_id_label = QLabel(f"CLIENT_{self.client_id}")
        self.client_id_label.setStyleSheet("font-weight: bold;")
        layout.addRow("Client ID:", self.client_id_label)

        # Client Name
        self.client_name_input = QLineEdit()
        layout.addRow("Client Name:", self.client_name_input)

        # Info label
        info_label = QLabel(
            "Basic client information.\n"
            "Shopify configuration is managed in the Advanced tab."
        )
        info_label.setWordWrap(True)
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 10px;")
        layout.addRow(info_label)

        return widget

    def _create_appearance_tab(self) -> QWidget:
        """Create Appearance tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        theme = get_theme_manager().get_current_theme()

        # Pin checkbox
        self.pin_checkbox = QCheckBox("Pin this client to top of sidebar")
        layout.addRow("Pinned:", self.pin_checkbox)

        # Group selector
        self.group_combo = QComboBox()
        self.group_combo.addItem("(No group)", None)  # Default
        layout.addRow("Group:", self.group_combo)

        # Color picker
        color_layout = QHBoxLayout()
        self.color_display = QLabel()
        self.color_display.setFixedSize(40, 30)
        self.color_display.setStyleSheet(f"border: 1px solid {theme.border};")
        color_layout.addWidget(self.color_display)

        self.color_button = QPushButton("Choose Color")
        self.color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()

        layout.addRow("Custom Color:", color_layout)

        # Badges input
        self.badges_input = QLineEdit()
        self.badges_input.setPlaceholderText("e.g., VIP, PRIORITY (comma-separated)")
        layout.addRow("Custom Badges:", self.badges_input)

        # Info label
        info_label = QLabel(
            "Customize how this client appears in the sidebar.\n"
            "Badges are displayed next to the client name."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 10px;")
        layout.addRow(info_label)

        return widget

    def _create_statistics_tab(self) -> QWidget:
        """Create Statistics tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        theme = get_theme_manager().get_current_theme()

        # Total sessions (readonly)
        self.total_sessions_label = QLabel()
        layout.addRow("Total Sessions:", self.total_sessions_label)

        # Last session date (readonly)
        self.last_session_label = QLabel()
        layout.addRow("Last Session Date:", self.last_session_label)

        # Last accessed (readonly)
        self.last_accessed_label = QLabel()
        layout.addRow("Last Accessed:", self.last_accessed_label)

        # Info label
        info_label = QLabel(
            "Client statistics are calculated from session data.\n"
            "These values are read-only and update automatically."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; padding: 10px;")
        layout.addRow(info_label)

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create Advanced tab (placeholder)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_label = QLabel(
            "Advanced settings (column mappings, rules) will be available here in future updates.\n\n"
            "For now, use the main Settings window to configure these options."
        )
        info_label.setWordWrap(True)
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 10pt; padding: 20px;")
        layout.addWidget(info_label)
        layout.addStretch()

        return widget

    def _load_data(self):
        """Load data into form fields."""
        # Basic Info
        self.client_name_input.setText(self.config.get("client_name", ""))

        # Appearance
        self.pin_checkbox.setChecked(self.ui_settings.get("is_pinned", False))

        # Load groups
        if self.groups_manager:
            groups = self.groups_manager.list_groups()
            for group in groups:
                self.group_combo.addItem(group.get("name", "Unknown"), group.get("id"))

            # Select current group
            current_group_id = self.ui_settings.get("group_id")
            if current_group_id:
                index = self.group_combo.findData(current_group_id)
                if index >= 0:
                    self.group_combo.setCurrentIndex(index)

        # Color
        custom_color = self.ui_settings.get("custom_color", "#4CAF50")
        self.current_color = custom_color
        self._update_color_display(custom_color)

        # Badges
        custom_badges = self.ui_settings.get("custom_badges", [])
        badges_text = ", ".join(custom_badges) if custom_badges else ""
        self.badges_input.setText(badges_text)

        # Statistics (readonly)
        total_sessions = self.metadata.get("total_sessions", 0)
        self.total_sessions_label.setText(str(total_sessions))

        last_session = self.metadata.get("last_session_date")
        self.last_session_label.setText(last_session or "Never")

        last_accessed = self.metadata.get("last_accessed")
        self.last_accessed_label.setText(last_accessed or "Unknown")

    def _choose_color(self):
        """Open color picker dialog."""
        current_color = QColor(self.current_color)
        color = QColorDialog.getColor(current_color, self, "Choose Custom Color")

        if color.isValid():
            self.current_color = color.name()
            self._update_color_display(self.current_color)

    def _update_color_display(self, color_hex: str):
        """Update color display label.

        Args:
            color_hex: Hex color string (e.g., "#4CAF50")
        """
        self.color_display.setStyleSheet(
            f"background-color: {color_hex}; border: 1px solid #ccc;"
        )

    def _save_and_accept(self):
        """Save changes and close dialog."""
        try:
            # Update config
            self.config["client_name"] = self.client_name_input.text().strip()

            # Update ui_settings
            self.config["ui_settings"]["is_pinned"] = self.pin_checkbox.isChecked()
            self.config["ui_settings"]["group_id"] = self.group_combo.currentData()
            self.config["ui_settings"]["custom_color"] = self.current_color

            # Parse badges
            badges_text = self.badges_input.text().strip()
            if badges_text:
                badges = [b.strip() for b in badges_text.split(",") if b.strip()]
            else:
                badges = []
            self.config["ui_settings"]["custom_badges"] = badges

            # Save config
            success = self.profile_manager.save_client_config(self.client_id, self.config)

            if success:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Settings for CLIENT_{self.client_id} saved successfully!"
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Failed to save client settings. Please try again."
                )

        except Exception as e:
            logger.error(f"Failed to save client settings: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while saving:\n{str(e)}"
            )
