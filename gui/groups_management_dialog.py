"""Groups Management Dialog for creating/editing/deleting client groups.

This dialog provides a UI for managing custom client groups with color assignment.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from gui.theme_manager import get_theme_manager
from shopify_tool.groups_manager import GroupsManager, GroupsManagerError

logger = logging.getLogger(__name__)


class GroupsManagementDialog(QDialog):
    """Dialog for managing client groups.

    Features:
    - List existing groups with name, color, and client count
    - Create new groups with name and color picker
    - Edit existing groups
    - Delete groups with client unassignment
    """

    def __init__(self, groups_manager: GroupsManager, profile_manager, parent=None):
        """Initialize GroupsManagementDialog.

        Args:
            groups_manager: GroupsManager instance
            profile_manager: ProfileManager instance for client queries
            parent: Parent widget
        """
        super().__init__(parent)
        self.groups_manager = groups_manager
        self.profile_manager = profile_manager

        self.setWindowTitle("Manage Client Groups")
        self.setModal(True)
        self.setMinimumSize(600, 400)

        self._setup_ui()
        self._load_groups()

    def _setup_ui(self):
        """Create dialog layout."""
        layout = QVBoxLayout(self)

        # Table for groups
        self.groups_table = QTableWidget()
        self.groups_table.setColumnCount(4)
        self.groups_table.setHorizontalHeaderLabels(["Name", "Color", "Clients", "ID"])
        self.groups_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.groups_table.setSelectionMode(QTableWidget.SingleSelection)
        self.groups_table.setEditTriggers(QTableWidget.NoEditTriggers)

        # Set column widths
        header = self.groups_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # Color
        header.setSectionResizeMode(2, QHeaderView.Fixed)  # Clients
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # ID
        self.groups_table.setColumnWidth(1, 80)
        self.groups_table.setColumnWidth(2, 80)
        self.groups_table.setColumnWidth(3, 200)

        # Hide ID column (used internally)
        self.groups_table.setColumnHidden(3, True)

        layout.addWidget(self.groups_table)

        # Buttons layout
        buttons_layout = QHBoxLayout()

        self.create_btn = QPushButton("Create Group")
        self.create_btn.clicked.connect(self._create_group)
        buttons_layout.addWidget(self.create_btn)

        self.edit_btn = QPushButton("Edit Group")
        self.edit_btn.clicked.connect(self._edit_group)
        self.edit_btn.setEnabled(False)
        buttons_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete Group")
        self.delete_btn.clicked.connect(self._delete_group)
        self.delete_btn.setEnabled(False)
        buttons_layout.addWidget(self.delete_btn)

        buttons_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(self.close_btn)

        layout.addLayout(buttons_layout)

        # Connect table selection changed
        self.groups_table.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_groups(self):
        """Load groups into table."""
        theme = get_theme_manager().get_current_theme()
        self.groups_table.setRowCount(0)

        try:
            groups = self.groups_manager.list_groups()

            for group in groups:
                group_id = group.get("id")
                name = group.get("name", "Unknown")
                color = group.get("color", theme.accent_blue)

                # Count clients in this group
                clients_in_group = self.groups_manager.get_clients_in_group(
                    group_id, self.profile_manager
                )
                client_count = len(clients_in_group)

                # Add row
                row = self.groups_table.rowCount()
                self.groups_table.insertRow(row)

                # Name
                name_item = QTableWidgetItem(name)
                self.groups_table.setItem(row, 0, name_item)

                # Color (visual indicator)
                color_item = QTableWidgetItem()
                color_item.setBackground(QColor(color))
                color_item.setText(color)
                self.groups_table.setItem(row, 1, color_item)

                # Client count
                count_item = QTableWidgetItem(str(client_count))
                count_item.setTextAlignment(Qt.AlignCenter)
                self.groups_table.setItem(row, 2, count_item)

                # ID (hidden)
                id_item = QTableWidgetItem(group_id)
                self.groups_table.setItem(row, 3, id_item)

            logger.info(f"Loaded {len(groups)} groups into table")

        except Exception as e:
            logger.exception("Failed to load groups")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to load groups:\n{e!s}"
            )

    def _on_selection_changed(self):
        """Handle table selection change."""
        has_selection = len(self.groups_table.selectedItems()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _get_selected_group_id(self) -> str | None:
        """Get selected group ID.

        Returns:
            Group ID or None if no selection
        """
        selected_rows = self.groups_table.selectionModel().selectedRows()
        if not selected_rows:
            return None

        row = selected_rows[0].row()
        group_id_item = self.groups_table.item(row, 3)  # ID column
        return group_id_item.text() if group_id_item else None

    def _create_group(self):
        """Create new group."""
        theme = get_theme_manager().get_current_theme()
        # Get group name
        name, ok = QInputDialog.getText(
            self,
            "Create Group",
            "Enter group name:"
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Get color
        color = QColorDialog.getColor(
            QColor(theme.accent_blue),  # Default blue
            self,
            "Select Group Color"
        )

        if not color.isValid():
            return

        color_hex = color.name()

        # Create group
        try:
            group_id = self.groups_manager.create_group(name, color_hex)
            logger.info(f"Created group: {name} (ID: {group_id}, Color: {color_hex})")

            QMessageBox.information(
                self,
                "Success",
                f"Group '{name}' created successfully!"
            )

            # Reload table
            self._load_groups()

        except GroupsManagerError as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to create group:\n{e!s}"
            )
        except Exception as e:
            logger.exception("Unexpected error creating group")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred:\n{e!s}"
            )

    def _edit_group(self):
        """Edit selected group."""
        theme = get_theme_manager().get_current_theme()
        group_id = self._get_selected_group_id()
        if not group_id:
            return

        # Get current group data
        group = self.groups_manager.get_group(group_id)
        if not group:
            QMessageBox.warning(self, "Error", "Group not found.")
            return

        current_name = group.get("name", "")
        current_color = group.get("color", theme.accent_blue)

        # Get new name
        name, ok = QInputDialog.getText(
            self,
            "Edit Group",
            "Enter new group name:",
            text=current_name
        )

        if not ok:
            return

        name = name.strip() if name else None

        # Get new color
        color = QColorDialog.getColor(
            QColor(current_color),
            self,
            "Select Group Color"
        )

        color_hex = color.name() if color.isValid() else None

        # Update group (if any changes)
        if name == current_name:
            name = None  # No change
        if color_hex == current_color:
            color_hex = None  # No change

        if name is None and color_hex is None:
            QMessageBox.information(self, "No Changes", "No changes were made.")
            return

        try:
            self.groups_manager.update_group(group_id, name=name, color=color_hex)
            logger.info(f"Updated group: {group_id}")

            QMessageBox.information(
                self,
                "Success",
                "Group updated successfully!"
            )

            # Reload table
            self._load_groups()

        except GroupsManagerError as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to update group:\n{e!s}"
            )
        except Exception as e:
            logger.exception("Unexpected error updating group")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred:\n{e!s}"
            )

    def _delete_group(self):
        """Delete selected group."""
        group_id = self._get_selected_group_id()
        if not group_id:
            return

        # Get group data for confirmation
        group = self.groups_manager.get_group(group_id)
        if not group:
            QMessageBox.warning(self, "Error", "Group not found.")
            return

        name = group.get("name", "Unknown")

        # Count clients in group
        clients_in_group = self.groups_manager.get_clients_in_group(
            group_id, self.profile_manager
        )
        client_count = len(clients_in_group)

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Delete Group",
            f"Delete group '{name}'?\n\n"
            f"This will unassign {client_count} client(s) from this group.\n"
            f"Clients will not be deleted.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Delete group
        try:
            self.groups_manager.delete_group(group_id, self.profile_manager)
            logger.info(f"Deleted group: {name} (ID: {group_id})")

            QMessageBox.information(
                self,
                "Success",
                f"Group '{name}' deleted successfully!\n"
                f"{client_count} client(s) unassigned."
            )

            # Reload table
            self._load_groups()

        except GroupsManagerError as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to delete group:\n{e!s}"
            )
        except Exception as e:
            logger.exception("Unexpected error deleting group")
            QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred:\n{e!s}"
            )
