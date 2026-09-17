"""Sets/bundles: SKUs decoded into their component SKUs at fulfillment time.

Every Add/Edit/Delete/Import mutates the set_decoders dict handed in at
construction -- the same object the window holds under
config_data["set_decoders"] -- and collect() returns that dict. Nothing
reaches disk until the window's Save.
"""

import logging
from pathlib import Path

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
    QMenu,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.components.error_banner import show_error
from gui.components.form_section import FormSection
from gui.components.inline_message import InlineMessage
from gui.settings.base import SettingsPage
from gui.theme_manager import (
    apply_dialog_button_roles,
    font_css,
    set_button_role,
)
from shared.components.toast import toast
from shared.theme import on_theme_changed
from shopify_tool.set_decoder import export_sets_to_csv, import_sets_from_csv

logger = logging.getLogger(__name__)


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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Actions
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

        self.import_button = QPushButton("Import from CSV")
        set_button_role(self.import_button, "secondary")
        import_menu = QMenu(self.import_button)
        merge_action = import_menu.addAction("Add and update sets…")
        merge_action.triggered.connect(
            lambda _checked=False: self._import_sets_from_csv(replace=False)
        )
        replace_action = import_menu.addAction("Replace all sets…")
        replace_action.triggered.connect(
            lambda _checked=False: self._import_sets_from_csv(replace=True)
        )
        self.import_button.setMenu(import_menu)
        buttons_layout.addWidget(self.import_button)

        self.export_button = QPushButton("Export to CSV")
        set_button_role(self.export_button, "secondary")
        self.export_button.clicked.connect(self._export_sets_to_csv)
        buttons_layout.addWidget(self.export_button)

        buttons_layout.addStretch()

        main_layout.addLayout(buttons_layout)

        # Tips
        tips_label = QLabel(
            "Tips:\n"
            "• CSV format: Set_SKU, Component_SKU, Component_Quantity\n"
            "• Sets are expanded before fulfillment simulation\n"
            "• Components must exist in your stock file"
        )
        on_theme_changed(
            tips_label,
            lambda t: tips_label.setStyleSheet(
                f"color: {t.text_secondary}; {font_css('caption')} margin-top: 10px;"
            ),
        )
        tips_label.setWordWrap(True)
        main_layout.addWidget(tips_label)

        # Populate table with existing sets
        self._populate_sets_table()

    def collect(self) -> dict:
        return {"set_decoders": self.set_decoders}

    def _populate_sets_table(self):
        """Populate the sets table with current set definitions."""
        set_decoders = self.set_decoders

        self.sets_table.setRowCount(len(set_decoders))

        for row_idx, (set_sku, components) in enumerate(set_decoders.items()):
            # Set SKU column
            sku_item = QTableWidgetItem(set_sku)
            sku_item.setFlags(
                sku_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # Read-only
            self.sets_table.setItem(row_idx, 0, sku_item)

            # Components summary column
            if components:
                # Show first 5 components, then "..."
                comp_summary = ", ".join(
                    [f"{comp['sku']}({comp['quantity']}x)" for comp in components[:5]]
                )
                if len(components) > 5:
                    comp_summary += f" ... (+{len(components) - 5} more)"
            else:
                comp_summary = "(no components)"

            comp_item = QTableWidgetItem(comp_summary)
            comp_item.setFlags(
                comp_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # Read-only
            self.sets_table.setItem(row_idx, 1, comp_item)

            # Actions column - Edit and Delete buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 2, 5, 2)
            actions_layout.setSpacing(5)

            edit_btn = QPushButton("Edit")
            set_button_role(edit_btn, "secondary")
            edit_btn.setMaximumWidth(70)
            edit_btn.clicked.connect(
                lambda checked, sku=set_sku: self._edit_set_dialog(sku)
            )
            actions_layout.addWidget(edit_btn)

            delete_btn = QPushButton("Delete")
            set_button_role(delete_btn, "secondary")
            delete_btn.setMaximumWidth(70)
            delete_btn.clicked.connect(
                lambda checked, sku=set_sku: self._delete_set(sku)
            )
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.sets_table.setCellWidget(row_idx, 2, actions_widget)

        # Re-apply search filter after repopulate
        if hasattr(self, "sets_search"):
            self._filter_sets_table(self.sets_search.text())
        self.export_button.setEnabled(bool(self.set_decoders))

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
        dialog = SetEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_sku, components = dialog.get_set_definition()
            self.set_decoders[set_sku] = components
            self._populate_sets_table()

    def _edit_set_dialog(self, set_sku):
        current_components = self.set_decoders.get(set_sku, [])
        dialog = SetEditorDialog(
            set_sku=set_sku, components=current_components, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_set_sku, new_components = dialog.get_set_definition()
            if new_set_sku != set_sku:
                del self.set_decoders[set_sku]
            self.set_decoders[new_set_sku] = new_components
            self._populate_sets_table()

    def _delete_set(self, set_sku):
        """No confirm: the settings window's Cancel undoes it."""
        del self.set_decoders[set_sku]
        self._populate_sets_table()

    def _import_sets_from_csv(self, replace: bool):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Sets from CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return
        name = Path(file_path).name
        try:
            imported_sets = import_sets_from_csv(file_path)
        except Exception:
            logger.exception(f"Failed to import sets from {file_path}")
            show_error(self, "The sets weren't imported", "Details are in Logs.")
            return
        if not imported_sets:
            show_error(
                self,
                f"No sets found in {name}",
                "Each row needs Set_SKU, Component_SKU and Component_Quantity.",
            )
            return

        if replace:
            self.set_decoders.clear()
        self.set_decoders.update(imported_sets)
        self._populate_sets_table()
        if replace:
            toast(self, f"Replaced all sets with {len(imported_sets)} from {name}")
        else:
            toast(self, f"Imported {len(imported_sets)} sets from {name}")

    def _export_sets_to_csv(self):
        """Disabled while there are no sets (see _populate_sets_table)."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sets to CSV",
            "sets_export.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return
        try:
            export_sets_to_csv(self.set_decoders, file_path)
        except Exception:
            logger.exception(f"Failed to export sets to {file_path}")
            show_error(self, "The sets weren't exported", "Details are in Logs.")
            return
        toast(self, f"Exported {len(self.set_decoders)} sets to {Path(file_path).name}")


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

        self.sku_message = InlineMessage()
        layout.addWidget(self.sku_message)
        self.set_sku_edit.textChanged.connect(self.sku_message.clear)

        # Components table
        components_label = QLabel("Components:")
        components_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(components_label)

        self.components_table = QTableWidget()
        self.components_table.setColumnCount(3)
        self.components_table.setHorizontalHeaderLabels(
            ["Component SKU", "Quantity", "Remove"]
        )

        # Configure columns
        header = self.components_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Component SKU
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Quantity
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Remove
        self.components_table.setColumnWidth(1, 100)
        self.components_table.setColumnWidth(2, 80)

        layout.addWidget(self.components_table)

        self.components_message = InlineMessage()
        layout.addWidget(self.components_message)

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
        on_theme_changed(
            tips_label,
            lambda t: tips_label.setStyleSheet(
                f"color: {t.text_secondary}; font-style: italic; {font_css('caption')} margin-top: 10px;"
            ),
        )
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        apply_dialog_button_roles(button_box)
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
        """Explain problems under the field they name; accept when there are none."""
        self.sku_message.clear()
        self.components_message.clear()
        if not self.set_sku_edit.text().strip():
            self.sku_message.show_message("Enter the set's SKU.")
            return
        if not self.get_set_definition()[1]:
            self.components_message.show_message(
                "Add at least one component with a SKU."
            )
            return
        self.accept()

    def get_set_definition(self):
        """(set_sku, components_list) as currently entered."""
        set_sku = self.set_sku_edit.text().strip()
        components = []

        for row in range(self.components_table.rowCount()):
            sku_widget = self.components_table.cellWidget(row, 0)
            qty_widget = self.components_table.cellWidget(row, 1)

            if sku_widget and qty_widget:
                comp_sku = sku_widget.text().strip()
                comp_qty = qty_widget.value()

                if comp_sku:
                    components.append({"sku": comp_sku, "quantity": comp_qty})

        return set_sku, components
