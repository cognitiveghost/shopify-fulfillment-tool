"""The client list, and the actions that change it.

Extracted from gui/client_sidebar.py so the command bar's dropdown can show
pinned/group structure without CommandBar -- a gui/components/ widget that
owns no application state -- growing a ProfileManager.
"""

import logging

from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget

from gui.client_settings_dialog import ClientCreationDialog, ClientSettingsDialog
from gui.groups_management_dialog import GroupsManagementDialog
from gui.worker import Worker
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class ClientDirectory(QObject):
    """Loads the client list off the GUI thread and owns the client dialogs."""

    loaded = Signal(dict)
    clientCreated = Signal(str)

    def __init__(
        self,
        profile_manager: ProfileManager,
        groups_manager: GroupsManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.groups_manager = groups_manager
        self._refresh_workers = set()  # keeps in-flight refresh Workers alive

    def gather(self) -> dict:
        """All the file-server IO refresh() needs, with zero Qt object
        construction -- safe to run in a background Worker.
        """
        groups_data = self.groups_manager.load_groups()
        special_groups = groups_data.get("special_groups", {})
        custom_groups = self.groups_manager.list_groups()
        all_clients = self.profile_manager.list_clients()

        pinned_client_ids = set()
        card_data = {}
        for client_id in all_clients:
            ui_settings = self.profile_manager.get_ui_settings(client_id)
            if ui_settings.get("is_pinned", False):
                pinned_client_ids.add(client_id)
            card_data[client_id] = self.profile_manager.get_client_config_extended(client_id)

        group_members = {}
        for group in custom_groups:
            group_id = group.get("id")
            group_members[group_id] = self.groups_manager.get_clients_in_group(
                group_id, self.profile_manager
            )

        return {
            "special_groups": special_groups,
            "custom_groups": custom_groups,
            "all_clients": all_clients,
            "pinned_client_ids": pinned_client_ids,
            "group_members": group_members,
            "card_data": card_data,
        }

    def refresh(self) -> None:
        """Reload the client list off the GUI thread and emit `loaded`."""
        worker = Worker(self.gather)
        worker.signals.result.connect(self.loaded.emit)
        worker.signals.error.connect(self._on_refresh_error)
        # Tracked in a set, not a single slot: a bare local is collected the
        # instant this returns, which in this PySide6 build destroys the
        # QRunnable's unparented signals object before its queued result
        # reaches the main thread. A second refresh before the first
        # finishes must not drop the first worker's reference either.
        self._refresh_workers.add(worker)
        worker.signals.finished.connect(lambda: self._refresh_workers.discard(worker))
        QThreadPool.globalInstance().start(worker)

    def _on_refresh_error(self, error) -> None:
        _exctype, value, tb = error
        logger.error(f"Client directory refresh failed: {value}\n{tb}")
        QMessageBox.warning(self.parent(), "Refresh Error", f"Failed to refresh clients:\n{value!s}")

    def menu_for(self, client_id: str, parent: QWidget) -> QMenu:
        """Build the per-client context menu. The caller exec()s it."""
        menu = QMenu(parent)

        ui_settings = self.profile_manager.get_ui_settings(client_id)
        is_pinned = ui_settings.get("is_pinned", False)

        pin_action = menu.addAction("Unpin" if is_pinned else "Pin to Top")
        pin_action.triggered.connect(lambda: self._toggle_pin(client_id, parent))

        edit_action = menu.addAction("Edit Settings...")
        edit_action.triggered.connect(lambda: self._edit_client(client_id, parent))

        move_menu = menu.addMenu("Move to Group")
        move_menu.addAction("(No group)").triggered.connect(
            lambda: self._move_to_group(client_id, None, parent)
        )

        groups = self.groups_manager.list_groups()
        for group in groups:
            group_id = group.get("id")
            group_name = group.get("name", "Unknown")
            move_menu.addAction(group_name).triggered.connect(
                lambda checked, gid=group_id: self._move_to_group(client_id, gid, parent)
            )

        menu.addSeparator()

        delete_action = menu.addAction("Delete Client...")
        delete_action.triggered.connect(lambda: self._delete_client(client_id, parent))

        return menu

    def _toggle_pin(self, client_id: str, parent: QWidget) -> None:
        try:
            ui_settings = self.profile_manager.get_ui_settings(client_id)
            new_pin_state = not ui_settings.get("is_pinned", False)

            self.profile_manager.update_ui_settings(client_id, {"is_pinned": new_pin_state})

            logger.info(f"Toggled pin for CLIENT_{client_id}: {new_pin_state}")
            self.refresh()

        except Exception as e:
            logger.exception("Failed to toggle pin")
            QMessageBox.warning(parent, "Error", f"Failed to toggle pin:\n{e!s}")

    def _edit_client(self, client_id: str, parent: QWidget) -> None:
        dialog = ClientSettingsDialog(
            client_id=client_id,
            profile_manager=self.profile_manager,
            groups_manager=self.groups_manager,
            parent=parent,
        )

        if dialog.exec():
            self.refresh()

    def _move_to_group(self, client_id: str, group_id: str | None, parent: QWidget) -> None:
        try:
            self.profile_manager.update_ui_settings(client_id, {"group_id": group_id})

            group_name = "No group" if group_id is None else "group"
            logger.info(f"Moved CLIENT_{client_id} to {group_name}")
            self.refresh()

        except Exception as e:
            logger.exception("Failed to move client to group")
            QMessageBox.warning(parent, "Error", f"Failed to move client:\n{e!s}")

    def _delete_client(self, client_id: str, parent: QWidget) -> None:
        reply = QMessageBox.question(
            parent,
            "Delete Client",
            f"Delete CLIENT_{client_id}?\n\n"
            f"This will remove all configuration and session data.\n"
            f"This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                QMessageBox.information(
                    parent,
                    "Not Implemented",
                    "Client deletion is not yet implemented.\n"
                    "Please manually delete the client directory on the server.",
                )

            except Exception as e:
                logger.exception("Failed to delete client")
                QMessageBox.critical(parent, "Error", f"Failed to delete client:\n{e!s}")

    def open_groups_dialog(self, parent: QWidget) -> None:
        dialog = GroupsManagementDialog(
            groups_manager=self.groups_manager,
            profile_manager=self.profile_manager,
            parent=parent,
        )

        if dialog.exec():
            self.refresh()

    def open_create_client_dialog(self, parent: QWidget) -> None:
        dialog = ClientCreationDialog(
            profile_manager=self.profile_manager,
            groups_manager=self.groups_manager,
            parent=parent,
        )

        if dialog.exec():
            created_client_id = dialog.client_id_input.text().strip().upper()

            self.refresh()
            self.clientCreated.emit(created_client_id)

            logger.info(f"Created client: CLIENT_{created_client_id}")
