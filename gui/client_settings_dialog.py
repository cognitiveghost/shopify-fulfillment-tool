"""The client creation dialog. Editing a client's profile is the Client settings
window's Profile page (gui/settings/window.py)."""

import logging

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
    QVBoxLayout,
)

from gui.components import InlineMessage, show_error, toast
from gui.theme_manager import apply_dialog_button_roles, font_css, get_theme_manager
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
