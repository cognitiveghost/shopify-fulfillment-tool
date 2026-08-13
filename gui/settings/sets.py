"""Sets/bundles: SKUs decoded into their component SKUs at fulfillment time.

Self-saving: every Add/Edit/Delete/Import/Export mutates the set_decoders
dict handed in at construction (the same object the window holds under
config_data["set_decoders"]) directly, so there is nothing left to collect()
by the time the window's save runs.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage
from gui.theme_manager import font_css, get_theme_manager, set_button_role
from shopify_tool.set_decoder import export_sets_to_csv, import_sets_from_csv


class SetsPage(SettingsPage):
    """Set/bundle definitions, stored under config_data["set_decoders"]."""

    def __init__(self, set_decoders: dict, parent=None):
        super().__init__(parent)
        self.set_decoders = set_decoders

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        main_layout.addWidget(FormSection("Set/Bundle Definitions"))

        # Search box
        self.sets_search = QLineEdit()
        self.sets_search.setPlaceholderText("Search by SKU or components...")
        self.sets_search.setClearButtonEnabled(True)
        self.sets_search.textChanged.connect(self._filter_sets_table)
        main_layout.addWidget(self.sets_search)

        # Sets table
        self.sets_table = QTableWidget()
        self.sets_table.setColumnCount(3)
        self.sets_table.setHorizontalHeaderLabels(["Set SKU", "Components", "Actions"])

        # Configure columns
        header = self.sets_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Set SKU
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Components
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Actions
        self.sets_table.setColumnWidth(2, 150)

        self.sets_table.setAlternatingRowColors(True)
        self.sets_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        main_layout.addWidget(self.sets_table)

        # Buttons row
        buttons_layout = QHBoxLayout()

        add_btn = QPushButton("Add Set")
        set_button_role(add_btn, "secondary")
        add_btn.clicked.connect(self._add_set_dialog)
        buttons_layout.addWidget(add_btn)

        import_btn = QPushButton("Import from CSV")
        set_button_role(import_btn, "secondary")
        import_btn.clicked.connect(self._import_sets_from_csv)
        buttons_layout.addWidget(import_btn)

        export_btn = QPushButton("Export to CSV")
        set_button_role(export_btn, "secondary")
        export_btn.clicked.connect(self._export_sets_to_csv)
        buttons_layout.addWidget(export_btn)

        buttons_layout.addStretch()

        main_layout.addLayout(buttons_layout)

        # Tips
        tips_label = QLabel(
            "Tips:\n"
            "• CSV format: Set_SKU, Component_SKU, Component_Quantity\n"
            "• Sets are expanded before fulfillment simulation\n"
            "• Components must exist in your stock file"
        )
        theme = get_theme_manager().get_current_theme()
        tips_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')} margin-top: 10px;")
        tips_label.setWordWrap(True)
        main_layout.addWidget(tips_label)

        # Populate table with existing sets
        self._populate_sets_table()

    def _populate_sets_table(self):
        """Populate the sets table with current set definitions."""
        set_decoders = self.set_decoders

        self.sets_table.setRowCount(len(set_decoders))

        for row_idx, (set_sku, components) in enumerate(set_decoders.items()):
            # Set SKU column
            sku_item = QTableWidgetItem(set_sku)
            sku_item.setFlags(sku_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            self.sets_table.setItem(row_idx, 0, sku_item)

            # Components summary column
            if components:
                # Show first 5 components, then "..."
                comp_summary = ", ".join([
                    f"{comp['sku']}({comp['quantity']}x)"
                    for comp in components[:5]
                ])
                if len(components) > 5:
                    comp_summary += f" ... (+{len(components) - 5} more)"
            else:
                comp_summary = "(no components)"

            comp_item = QTableWidgetItem(comp_summary)
            comp_item.setFlags(comp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            self.sets_table.setItem(row_idx, 1, comp_item)

            # Actions column - Edit and Delete buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 2, 5, 2)
            actions_layout.setSpacing(5)

            edit_btn = QPushButton("Edit")
            set_button_role(edit_btn, "secondary")
            edit_btn.setMaximumWidth(70)
            edit_btn.clicked.connect(lambda checked, sku=set_sku: self._edit_set_dialog(sku))
            actions_layout.addWidget(edit_btn)

            delete_btn = QPushButton("Delete")
            set_button_role(delete_btn, "secondary")
            delete_btn.setMaximumWidth(70)
            delete_btn.clicked.connect(lambda checked, sku=set_sku: self._delete_set(sku))
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.sets_table.setCellWidget(row_idx, 2, actions_widget)

        # Re-apply search filter after repopulate
        if hasattr(self, 'sets_search'):
            self._filter_sets_table(self.sets_search.text())

    def _filter_sets_table(self, text: str):
        """Filter sets table rows by SKU or components text."""
        text = text.lower().strip()
        for row in range(self.sets_table.rowCount()):
            sku_item = self.sets_table.item(row, 0)
            comp_item = self.sets_table.item(row, 1)
            sku_text = sku_item.text().lower() if sku_item else ""
            comp_text = comp_item.text().lower() if comp_item else ""
            visible = not text or text in sku_text or text in comp_text
            self.sets_table.setRowHidden(row, not visible)

    def _add_set_dialog(self):
        """Show dialog to add a new set."""
        dialog = SetEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_sku, components = dialog.get_set_definition()

            # Debug: print what we got
            print(f"[DEBUG] Adding set '{set_sku}' with {len(components)} components:")
            for i, comp in enumerate(components):
                print(f"  {i+1}. {comp['sku']} x {comp['quantity']}")

            # Add to config
            self.set_decoders[set_sku] = components

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(
                self,
                "Success",
                f"Set '{set_sku}' added with {len(components)} components!"
            )

    def _edit_set_dialog(self, set_sku):
        """Show dialog to edit an existing set."""
        current_components = self.set_decoders.get(set_sku, [])

        dialog = SetEditorDialog(set_sku=set_sku, components=current_components, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_set_sku, new_components = dialog.get_set_definition()

            # Remove old SKU if changed
            if new_set_sku != set_sku:
                del self.set_decoders[set_sku]

            # Update with new definition
            self.set_decoders[new_set_sku] = new_components

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(self, "Success", f"Set '{new_set_sku}' updated successfully!")

    def _delete_set(self, set_sku):
        """Delete a set after confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete set '{set_sku}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.set_decoders[set_sku]
            self._populate_sets_table()
            QMessageBox.information(self, "Success", f"Set '{set_sku}' deleted successfully!")

    def _import_sets_from_csv(self):
        """Import sets from CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sets from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Import using set_decoder module
            imported_sets = import_sets_from_csv(file_path)

            if not imported_sets:
                QMessageBox.warning(self, "Warning", "No sets found in CSV file.")
                return

            # Ask user: Replace all or Merge
            reply = QMessageBox.question(
                self,
                "Import Mode",
                f"Found {len(imported_sets)} sets in CSV.\n\n"
                "Yes = Replace all existing sets\n"
                "No = Merge (update existing, add new)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Cancel:
                return

            if reply == QMessageBox.StandardButton.Yes:
                # Replace all
                self.set_decoders.clear()
                self.set_decoders.update(imported_sets)
            else:
                # Merge
                self.set_decoders.update(imported_sets)

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(
                self,
                "Success",
                f"Successfully imported {len(imported_sets)} sets from CSV!"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import sets from CSV:\n\n{e!s}"
            )

    def _export_sets_to_csv(self):
        """Export sets to CSV file."""
        set_decoders = self.set_decoders

        if not set_decoders:
            QMessageBox.warning(self, "Warning", "No sets to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sets to CSV",
            "sets_export.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Export using set_decoder module
            export_sets_to_csv(set_decoders, file_path)

            QMessageBox.information(
                self,
                "Success",
                f"Successfully exported {len(set_decoders)} sets to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export sets to CSV:\n\n{e!s}"
            )


class SetEditorDialog(QDialog):
    """Dialog for adding or editing a set/bundle definition."""

    def __init__(self, set_sku=None, components=None, parent=None):
        """
        Initialize the Set Editor Dialog.

        Args:
            set_sku: Set SKU (None for new set, or existing SKU for edit)
            components: List of components (for edit mode)
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Add Set" if set_sku is None else f"Edit Set: {set_sku}")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Set SKU input
        sku_layout = QFormLayout()
        self.set_sku_edit = QLineEdit(set_sku or "")
        self.set_sku_edit.setPlaceholderText("e.g., SET-WINTER-KIT")
        sku_layout.addRow("Set SKU:", self.set_sku_edit)
        layout.addLayout(sku_layout)

        # Components table
        components_label = QLabel("Components:")
        components_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(components_label)

        self.components_table = QTableWidget()
        self.components_table.setColumnCount(3)
        self.components_table.setHorizontalHeaderLabels(["Component SKU", "Quantity", "Remove"])

        # Configure columns
        header = self.components_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Component SKU
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Quantity
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Remove
        self.components_table.setColumnWidth(1, 100)
        self.components_table.setColumnWidth(2, 80)

        layout.addWidget(self.components_table)

        # Add component button
        add_comp_btn = QPushButton("+ Add Component")
        set_button_role(add_comp_btn, "secondary")
        # Use lambda to avoid passing 'checked' bool as first argument
        add_comp_btn.clicked.connect(lambda: self._add_component_row())
        layout.addWidget(add_comp_btn)

        # Populate with existing components if provided
        if components:
            for comp in components:
                self._add_component_row(comp.get("sku", ""), comp.get("quantity", 1))
        else:
            # Add one empty row for new sets
            self._add_component_row()

        # Tips
        tips_label = QLabel(
            "Tip: Components are SKUs that exist in your stock file.\n"
            "Quantity indicates how many of each component are in one set."
        )
        theme = get_theme_manager().get_current_theme()
        tips_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; {font_css('caption')} margin-top: 10px;")
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._validate_and_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _add_component_row(self, sku="", quantity=1):
        """Add a new row to the components table."""
        # Protection: if sku is bool (from button clicked signal), convert to empty string
        if isinstance(sku, bool):
            sku = ""

        row_idx = self.components_table.rowCount()
        self.components_table.insertRow(row_idx)

        # Component SKU
        sku_edit = QLineEdit(str(sku))  # Ensure it's a string
        sku_edit.setPlaceholderText("e.g., HAT-001")
        self.components_table.setCellWidget(row_idx, 0, sku_edit)

        # Quantity
        qty_spinbox = QSpinBox()
        qty_spinbox.setMinimum(1)
        qty_spinbox.setMaximum(9999)
        qty_spinbox.setValue(quantity)
        self.components_table.setCellWidget(row_idx, 1, qty_spinbox)

        # Remove button - використовуємо sender() щоб знайти правильний row
        remove_btn = QPushButton("Remove")
        set_button_role(remove_btn, "secondary")
        remove_btn.setMaximumWidth(60)
        remove_btn.clicked.connect(self._remove_component_row)
        self.components_table.setCellWidget(row_idx, 2, remove_btn)

    def _remove_component_row(self):
        """Remove a component row from the table."""
        # Знаходимо який button викликав цю функцію
        button = self.sender()
        if button:
            # Знаходимо row index цієї кнопки в таблиці
            for row in range(self.components_table.rowCount()):
                if self.components_table.cellWidget(row, 2) == button:
                    self.components_table.removeRow(row)
                    break

    def _validate_and_save(self):
        """Validate inputs and accept dialog if valid."""
        # Validate Set SKU
        set_sku = self.set_sku_edit.text().strip()
        if not set_sku:
            QMessageBox.warning(self, "Validation Error", "Set SKU cannot be empty!")
            return

        # Validate components
        components = []
        for row in range(self.components_table.rowCount()):
            sku_widget = self.components_table.cellWidget(row, 0)
            qty_widget = self.components_table.cellWidget(row, 1)

            if sku_widget and qty_widget:
                comp_sku = sku_widget.text().strip()
                comp_qty = qty_widget.value()

                if comp_sku:  # Only add non-empty SKUs
                    components.append({
                        "sku": comp_sku,
                        "quantity": comp_qty
                    })

        if not components:
            QMessageBox.warning(self, "Validation Error", "Set must have at least one component!")
            return

        # All valid, accept dialog
        self.accept()

    def get_set_definition(self):
        """
        Get the set definition from the dialog.

        Returns:
            Tuple of (set_sku, components_list)
        """
        set_sku = self.set_sku_edit.text().strip()
        components = []

        print(f"[DEBUG] get_set_definition: Reading {self.components_table.rowCount()} rows from table")

        for row in range(self.components_table.rowCount()):
            sku_widget = self.components_table.cellWidget(row, 0)
            qty_widget = self.components_table.cellWidget(row, 1)

            if sku_widget and qty_widget:
                comp_sku = sku_widget.text().strip()
                comp_qty = qty_widget.value()

                print(f"[DEBUG]   Row {row}: SKU='{comp_sku}', Qty={comp_qty}, Empty={not bool(comp_sku)}")

                if comp_sku:
                    components.append({
                        "sku": comp_sku,
                        "quantity": comp_qty
                    })
            else:
                print(f"[DEBUG]   Row {row}: widgets are None (sku_widget={sku_widget}, qty_widget={qty_widget})")

        print(f"[DEBUG] get_set_definition: Collected {len(components)} non-empty components")
        return set_sku, components
