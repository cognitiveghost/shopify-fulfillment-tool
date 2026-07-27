from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ProfileManagerDialog(QDialog):
    """A dialog for managing settings profiles (add, rename, delete).

    This dialog provides the user interface for managing their settings
    profiles. It interacts directly with the profile management methods
    (e.g., `create_profile`, `rename_profile`) exposed by the `MainWindow`.

    Attributes:
        parent (MainWindow): A reference to the main window, used to access
            profile data and management functions.
        list_widget (QListWidget): The widget that displays the list of
            available profiles.
    """
    def __init__(self, parent):
        """Initializes the ProfileManagerDialog.

        Args:
            parent (MainWindow): The main window instance.
        """
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Manage Profiles")
        self.setMinimumSize(400, 300)

        main_layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.populate_profiles()
        main_layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        add_btn = QPushButton("Add New...")
        rename_btn = QPushButton("Rename...")
        delete_btn = QPushButton("Delete")

        button_layout.addWidget(add_btn)
        button_layout.addWidget(rename_btn)
        button_layout.addWidget(delete_btn)
        main_layout.addLayout(button_layout)

        add_btn.clicked.connect(self.add_profile)
        rename_btn.clicked.connect(self.rename_profile)
        delete_btn.clicked.connect(self.delete_profile)

        self.list_widget.setCurrentRow(0)

    def populate_profiles(self):
        """Clears and repopulates the list of profiles from the main config."""
        self.list_widget.clear()
        profile_names = sorted(self.parent.config.get("profiles", {}).keys())
        for name in profile_names:
            item = QListWidgetItem(name)
            self.list_widget.addItem(item)

    def add_profile(self):
        """Handles the 'Add New' button click.

        Prompts the user for a new profile name and calls the main window's
        `create_profile` method.
        """
        new_name, ok = QInputDialog.getText(self, "Add Profile", "Enter new profile name:")
        if ok and new_name:
            # Create a new profile by copying the currently active one
            base_profile = self.parent.active_profile_name
            if self.parent.create_profile(new_name, base_profile_name=base_profile):
                self.populate_profiles()
                # Optionally, switch to the new profile
                self.parent.set_active_profile(new_name)

    def rename_profile(self):
        """Handles the 'Rename' button click.

        Prompts the user for a new name for the selected profile and calls
        the main window's `rename_profile` method.
        """
        current_item = self.list_widget.currentItem()
        if not current_item:
            return

        old_name = current_item.text()
        new_name, ok = QInputDialog.getText(self, "Rename Profile", f"Enter new name for '{old_name}':", text=old_name)

        if ok and new_name and new_name != old_name and self.parent.rename_profile(old_name, new_name):
            self.populate_profiles()
            self.parent.update_profile_combo()

    def delete_profile(self):
        """Handles the 'Delete' button click.

        Asks for confirmation and then calls the main window's
        `delete_profile` method for the selected profile.
        """
        current_item = self.list_widget.currentItem()
        if not current_item:
            return

        name_to_delete = current_item.text()

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Are you sure you want to permanently delete the profile '{name_to_delete}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes and self.parent.delete_profile(name_to_delete):
            self.populate_profiles()
            self.parent.update_profile_combo()
