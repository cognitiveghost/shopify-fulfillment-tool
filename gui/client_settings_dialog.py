"""Client Settings Dialog for editing client profiles.

This module provides dialogs for creating and editing client profiles with
tabbed interface for Basic Info, Appearance, Statistics, and Advanced settings.
"""

import logging

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components import InlineMessage, show_error, toast
from gui.theme_manager import apply_dialog_button_roles, font_css, get_theme_manager
from gui.worker import Worker
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import (
    ProfileManager,
    ProfileManagerError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class ClientCreationDialog(QDialog):
    """Dialog for creating a new client profile."""

    def __init__(
        self,
        profile_manager: ProfileManager,
        groups_manager: GroupsManager | None = None,
        parent=None,
        clients: list[tuple[str, str]] | None = None,
        archived_ids: list[str] | None = None,
    ):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.groups_manager = groups_manager
        self._live = {cid.upper() for cid, _name in clients or []}
        self._archived = {cid.upper() for cid in archived_ids or []}
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

        self.client_id_error = InlineMessage(self)
        form_layout.addRow("", self.client_id_error)
        self.client_id_input.textChanged.connect(self._check_id)

        self.client_name_input = QLineEdit()
        self.client_name_input.setPlaceholderText("e.g., M Cosmetics")
        self.client_name_input.setToolTip("Full name of the client")
        form_layout.addRow("Client Name:", self.client_name_input)

        self.client_name_error = InlineMessage(self)
        form_layout.addRow("", self.client_name_error)
        self.client_name_input.textChanged.connect(self.client_name_error.clear)

        # Copy settings from: Defaults, then every live client
        self.copy_combo = QComboBox()
        self.copy_combo.addItem("Defaults", None)
        for cid, name in clients or []:
            label = f"{name}  ({cid})" if name and name != cid else cid
            self.copy_combo.addItem(label, cid)
        self.copy_combo.setToolTip("Start from another client's settings")
        form_layout.addRow("Copy settings from:", self.copy_combo)

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
        self.color_display.setStyleSheet(
            f"border: 1px solid {theme.border}; background-color: {theme.status_success};"
        )
        color_layout.addWidget(self.color_display)

        self.color_button = QPushButton("Choose Color")
        self.color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()

        self.current_color = theme.status_success  # Default
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
        info_label.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('body')} padding: 10px;"
        )
        layout.addWidget(info_label)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create_button = button_box.button(QDialogButtonBox.Ok)
        apply_dialog_button_roles(button_box)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self._check_id("")  # Create starts disabled

    def _check_id(self, text: str) -> None:
        """Show the first problem with the ID as you type; Create waits for none."""
        cid = text.strip().upper()
        problem = ""
        if cid:
            ok, message = ProfileManager.validate_client_id(cid)
            if not ok:
                problem = message
            elif cid in self._live:
                problem = f"CLIENT_{cid} already exists."
            elif cid in self._archived:
                problem = f"CLIENT_{cid} is archived. Restore it from Archived clients."
        if problem:
            self.client_id_error.show_message(problem)
        else:
            self.client_id_error.clear()
        self.create_button.setEnabled(bool(cid) and not problem)

    def _choose_color(self):
        """Open color picker dialog."""
        theme = get_theme_manager().get_current_theme()
        current_color = QColor(self.current_color)
        color = QColorDialog.getColor(current_color, self, "Choose Client Color")

        if color.isValid():
            self.current_color = color.name()
            self.color_display.setStyleSheet(
                f"background-color: {self.current_color}; border: 1px solid {theme.border_subtle};"
            )

    def _load_groups(self):
        """Load available groups into dropdown."""
        if not self.groups_manager:
            self.group_combo.setEnabled(False)
            return

        groups = self.groups_manager.list_groups()
        for group in groups:
            self.group_combo.addItem(group.get("name", "Unknown"), group.get("id"))

    def validate_and_accept(self):
        """Validate inputs and create client profile."""
        client_id = self.client_id_input.text().strip()
        client_name = self.client_name_input.text().strip()

        # Validate inputs
        if not client_id:
            self.client_id_error.show_message("Enter a client ID.")
            return

        if not client_name:
            self.client_name_error.show_message("Enter a client name.")
            return

        # Validate client ID format
        is_valid, error_msg = ProfileManager.validate_client_id(client_id)
        if not is_valid:
            self.client_id_error.show_message(error_msg)
            return

        # Try to create client profile
        try:
            success = self.profile_manager.create_client_profile(
                client_id,
                client_name,
                ui_settings={
                    "is_pinned": self.pin_checkbox.isChecked(),
                    "group_id": self.group_combo.currentData(),
                    "custom_color": self.current_color,
                },
                copy_from=self.copy_combo.currentData(),
            )
            if success:
                self.accept()
                if self.parent() is not None:
                    toast(self.parent(), f"Client CLIENT_{client_id.upper()} created.")
            else:
                self.client_id_error.show_message(
                    f"CLIENT_{client_id.upper()} already exists or is archived."
                )
        except (ValidationError, ProfileManagerError):
            logger.exception("Failed to create client profile")
            show_error(
                self, "The client profile wasn't created", "Details are in Logs."
            )
        except Exception:
            logger.exception("Unexpected error creating client")
            show_error(
                self, "The client profile wasn't created", "Details are in Logs."
            )


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
        groups_manager: GroupsManager | None = None,
        parent=None,
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
        self._save_worker = None  # keeps the in-flight save Worker alive
        self._is_saving = False

        self.setWindowTitle(f"Client Profile - CLIENT_{client_id}")
        self.setModal(True)
        self.setMinimumSize(600, 500)

        # Load config
        self.config = self.profile_manager.load_client_config(client_id)
        if not self.config:
            logger.warning(f"Failed to load config for CLIENT_{client_id}")
            if self.parent() is not None:
                show_error(
                    self.parent(),
                    f"CLIENT_{client_id} settings couldn't be loaded",
                    "Check that the server share is reachable, then open the settings again.",
                )
            self.reject()
            return

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

        layout.addWidget(self.tabs)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        apply_dialog_button_roles(button_box)
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
        info_label.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')} padding: 10px;"
        )
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
        info_label.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')} padding: 10px;"
        )
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
        info_label.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')} padding: 10px;"
        )
        layout.addRow(info_label)

        return widget

    def _load_data(self):
        """Load data into form fields."""
        theme = get_theme_manager().get_current_theme()
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
        custom_color = self.ui_settings.get("custom_color", theme.status_success)
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
            color_hex: Hex color string (e.g., theme.accent_green)
        """
        theme = get_theme_manager().get_current_theme()
        self.color_display.setStyleSheet(
            f"background-color: {color_hex}; border: 1px solid {theme.border_subtle};"
        )

    def reject(self):
        if self._is_saving:
            return
        super().reject()

    def _save_and_accept(self):
        """Gather form data on the GUI thread, save in the background."""
        try:
            badges_text = self.badges_input.text().strip()
            badges = (
                [b.strip() for b in badges_text.split(",") if b.strip()]
                if badges_text
                else []
            )

            self.save_button.setEnabled(False)
            self.save_button.setText("Saving...")
            self._is_saving = True

            worker = Worker(
                self.profile_manager.update_client_profile,
                self.client_id,
                self.client_name_input.text().strip(),
                {
                    "is_pinned": self.pin_checkbox.isChecked(),
                    "group_id": self.group_combo.currentData(),
                    "custom_color": self.current_color,
                    "custom_badges": badges,
                },
            )
            worker.signals.result.connect(self._on_save_result)
            worker.signals.error.connect(self._on_save_error)
            # Keep a strong reference until the worker finishes -- a bare
            # local var is garbage-collected the instant this method returns,
            # which (in this PySide6 build) destroys the QRunnable's
            # unparented signals object before its queued result reaches the
            # main thread. See MainWindow._client_load_worker for the
            # verified repro.
            self._save_worker = worker
            QThreadPool.globalInstance().start(worker)

        except Exception:
            logger.exception("Failed to save client settings")
            self._is_saving = False
            self.save_button.setEnabled(True)
            self.save_button.setText("Save")
            show_error(self, "The settings weren't saved", "Details are in Logs.")

    def _on_save_result(self, success: bool):
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            self.accept()
            if self.parent() is not None:
                toast(self.parent(), f"CLIENT_{self.client_id} settings saved.")
        else:
            show_error(
                self,
                "The settings weren't saved",
                "Check that the server share is reachable, then save again.",
            )

    def _on_save_error(self, error):
        _exctype, value, _tb = error
        logger.error("Failed to save client settings", exc_info=value)
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        show_error(self, "The settings weren't saved", "Details are in Logs.")
