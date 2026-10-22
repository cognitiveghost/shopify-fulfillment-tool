"""Client creation, and the list of archived clients. Editing a client's profile
is the Client settings window's Profile page (gui/settings/window.py)."""

import logging
from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.components import InlineMessage, show_error, toast
from gui.theme_manager import apply_dialog_button_roles, font_css, get_theme_manager
from shared.i18n import _
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
        self.setWindowTitle(_("Create New Client"))
        self.setModal(True)
        self.setMinimumWidth(400)

        # Create layout
        layout = QVBoxLayout(self)

        # Form layout for inputs
        form_layout = QFormLayout()

        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText(_("e.g., M, A, B"))
        self.client_id_input.setToolTip(
            _(
                "Client ID (letters, numbers, underscore only)\n"
                "Max 20 characters\n"
                "Don't include 'CLIENT_' prefix"
            )
        )
        form_layout.addRow(_("Client ID:"), self.client_id_input)

        self.client_id_error = InlineMessage(self)
        form_layout.addRow("", self.client_id_error)
        self.client_id_input.textChanged.connect(self._check_id)

        self.client_name_input = QLineEdit()
        self.client_name_input.setPlaceholderText(_("e.g., M Cosmetics"))
        self.client_name_input.setToolTip(_("Full name of the client"))
        form_layout.addRow(_("Client Name:"), self.client_name_input)

        self.client_name_error = InlineMessage(self)
        form_layout.addRow("", self.client_name_error)
        self.client_name_input.textChanged.connect(self.client_name_error.clear)

        # Copy settings from: Defaults, then every live client
        self.copy_combo = QComboBox()
        self.copy_combo.addItem(_("Defaults"), None)
        for cid, name in clients or []:
            label = f"{name}  ({cid})" if name and name != cid else cid
            self.copy_combo.addItem(label, cid)
        self.copy_combo.setToolTip(_("Start from another client's settings"))
        form_layout.addRow(_("Copy settings from:"), self.copy_combo)

        # Group dropdown
        self.group_combo = QComboBox()
        self.group_combo.addItem(_("(No group)"), None)
        self.group_combo.setToolTip(_("Assign client to a group"))
        form_layout.addRow(_("Group:"), self.group_combo)

        # Color picker
        color_layout = QHBoxLayout()
        self.color_display = QLabel()
        self.color_display.setFixedSize(40, 30)
        theme = get_theme_manager().get_current_theme()
        self.color_display.setStyleSheet(
            f"border: 1px solid {theme.border}; background-color: {theme.status_success};"
        )
        color_layout.addWidget(self.color_display)

        self.color_button = QPushButton(_("Choose Color"))
        self.color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()

        self.current_color = theme.status_success  # Default
        form_layout.addRow(_("Color:"), color_layout)

        # Pin checkbox
        self.pin_checkbox = QCheckBox(_("Pin to top of sidebar"))
        form_layout.addRow(_("Pinned:"), self.pin_checkbox)

        layout.addLayout(form_layout)

        # Load groups (will disable combo if manager not provided)
        self._load_groups()

        # Add info label
        info_label = QLabel(
            _(
                "This will create a new client profile with default Shopify configuration.\n"
                "You can customize it later in Profile Settings."
            )
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
                problem = _("CLIENT_{cid} already exists.", cid=cid)
            elif cid in self._archived:
                problem = _(
                    "CLIENT_{cid} is archived. Restore it from Archived clients.", cid=cid
                )
        if problem:
            self.client_id_error.show_message(problem)
        else:
            self.client_id_error.clear()
        self.create_button.setEnabled(bool(cid) and not problem)

    def _choose_color(self):
        """Open color picker dialog."""
        theme = get_theme_manager().get_current_theme()
        current_color = QColor(self.current_color)
        color = QColorDialog.getColor(current_color, self, _("Choose Client Color"))

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
            self.client_id_error.show_message(_("Enter a client ID."))
            return

        if not client_name:
            self.client_name_error.show_message(_("Enter a client name."))
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
                    toast(
                        self.parent(),
                        _("Client CLIENT_{cid} created.", cid=client_id.upper()),
                    )
            else:
                self.client_id_error.show_message(
                    _(
                        "CLIENT_{cid} already exists or is archived.",
                        cid=client_id.upper(),
                    )
                )
        except (ValidationError, ProfileManagerError):
            logger.exception("Failed to create client profile")
            show_error(
                self,
                _("The client profile wasn't created"),
                _("Details are in Logs."),
            )
        except Exception:
            logger.exception("Unexpected error creating client")
            show_error(
                self,
                _("The client profile wasn't created"),
                _("Details are in Logs."),
            )


class ArchivedClientsDialog(QDialog):
    """The archived clients, each with a Restore. Spec A6.

    The caller runs the restore and calls remove_row() when it has worked.
    """

    def __init__(
        self, clients: list[dict], restore: Callable[[str], None], parent=None
    ):
        super().__init__(parent)
        self._restore = restore
        self.setWindowTitle(_("Archived clients"))
        self.setMinimumWidth(480)
        theme = get_theme_manager().get_current_theme()
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [_("Client ID"), _("Name"), _("Archived")]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        for client in clients:
            self._append(client)
        layout.addWidget(self.table)

        self.empty_label = QLabel(_("No archived clients."))
        self.empty_label.setStyleSheet(f"color: {theme.text_secondary};")
        layout.addWidget(self.empty_label)
        self._show_rows(bool(clients))

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.restore_button = QPushButton(_("Restore"))
        self.restore_button.clicked.connect(self._on_restore)
        button_box.addButton(self.restore_button, QDialogButtonBox.ActionRole)
        button_box.rejected.connect(self.reject)
        apply_dialog_button_roles(button_box)
        layout.addWidget(button_box)
        self._on_selection_changed()

    def _append(self, client: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        archived = (client.get("archived_at") or "")[:10]
        for column, text in enumerate(
            (client["client_id"], client.get("client_name", ""), archived)
        ):
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _show_rows(self, any_rows: bool) -> None:
        self.table.setVisible(any_rows)
        self.empty_label.setVisible(not any_rows)

    def _on_selection_changed(self) -> None:
        self.restore_button.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def _on_restore(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self._restore(self.table.item(row, 0).text())

    def remove_row(self, client_id: str) -> None:
        """Drop a restored client's row; say so when none are left."""
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == client_id:
                self.table.removeRow(row)
                break
        self._show_rows(self.table.rowCount() > 0)
