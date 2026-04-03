"""Tag Categories Management Dialog for Internal Tags system.

This module provides UI for creating, editing, and managing tag categories
with support for v2 format including order, colors, and SKU writeoff configuration.
"""

import logging
from typing import Dict, Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QFormLayout, QSpinBox,
    QDialogButtonBox, QMessageBox, QColorDialog, QSplitter, QGroupBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDoubleSpinBox, QComboBox, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from shopify_tool.tag_manager import validate_tag_categories_v2
from gui.theme_manager import get_theme_manager

logger = logging.getLogger(__name__)


class TagCategoriesPanel(QWidget):
    """Embeddable panel for managing tag categories (v2 format).

    Can be used standalone inside a QDialog or embedded directly into
    a QTabWidget (e.g., SettingsWindow).
    """

    categories_updated = Signal(dict)

    def __init__(self, tag_categories: Dict, parent=None):
        super().__init__(parent)

        # Store original and working copy
        self.original_categories = tag_categories.copy()
        self.working_categories = tag_categories.copy()

        # Ensure v2 format
        if "version" not in self.working_categories:
            self.working_categories = {
                "version": 2,
                "categories": self.working_categories
            }

        self.current_category_id: Optional[str] = None
        self.modified = False

        self.theme = get_theme_manager().get_current_theme()

        self._init_ui()
        self._load_categories()

        get_theme_manager().theme_changed.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize the panel UI (splitter layout, no dialog buttons)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = self._create_categories_list_panel()
        splitter.addWidget(left_panel)

        right_panel = self._create_category_editor_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([320, 780])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, 1)

    def _create_categories_list_panel(self) -> QWidget:
        """Create left panel with categories list."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        header_label = QLabel("Categories")
        header_label.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 5px;")
        layout.addWidget(header_label)

        self.categories_list = QListWidget()
        self.categories_list.currentItemChanged.connect(self._on_category_selected)
        layout.addWidget(self.categories_list)

        buttons_layout = QHBoxLayout()

        self.new_category_btn = QPushButton("+ New")
        self.new_category_btn.setToolTip("Create new category")
        self.new_category_btn.clicked.connect(self._on_new_category)
        buttons_layout.addWidget(self.new_category_btn)

        self.delete_category_btn = QPushButton("Delete")
        self.delete_category_btn.setToolTip("Delete selected category")
        self.delete_category_btn.clicked.connect(self._on_delete_category)
        self.delete_category_btn.setEnabled(False)
        buttons_layout.addWidget(self.delete_category_btn)

        layout.addLayout(buttons_layout)

        return panel

    def _create_category_editor_panel(self) -> QWidget:
        """Create right panel with category editor."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.editor_header_label = QLabel("Category Editor")
        self.editor_header_label.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 5px;")
        layout.addWidget(self.editor_header_label)

        form_layout = QFormLayout()

        self.category_id_input = QLineEdit()
        self.category_id_input.setPlaceholderText("e.g., my_category")
        self.category_id_input.setToolTip(
            "Category ID (lowercase, underscores only)\n"
            "Cannot be changed for existing categories"
        )
        self.category_id_input.textChanged.connect(self._on_editor_changed)
        form_layout.addRow("Category ID:", self.category_id_input)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g., My Category")
        self.label_input.setToolTip("Display name for this category")
        self.label_input.textChanged.connect(self._on_editor_changed)
        form_layout.addRow("Display Label:", self.label_input)

        color_layout = QHBoxLayout()
        self.color_display = QLabel()
        self.color_display.setFixedSize(40, 30)
        self.color_display.setStyleSheet(f"border: 1px solid {self.theme.border}; background-color: {self.theme.border};")
        color_layout.addWidget(self.color_display)

        self.color_button = QPushButton("Choose Color")
        self.color_button.clicked.connect(self._choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()

        self.current_color = "#9E9E9E"
        form_layout.addRow("Color:", color_layout)

        self.order_spin = QSpinBox()
        self.order_spin.setMinimum(1)
        self.order_spin.setMaximum(999)
        self.order_spin.setValue(1)
        self.order_spin.setToolTip("Display order (lower numbers appear first)")
        self.order_spin.valueChanged.connect(self._on_editor_changed)
        form_layout.addRow("Display Order:", self.order_spin)

        layout.addLayout(form_layout)

        # Tags section
        tags_group = QGroupBox("Tags")
        tags_layout = QVBoxLayout(tags_group)

        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(150)
        tags_layout.addWidget(self.tags_list)

        tag_buttons_layout = QHBoxLayout()

        self.add_tag_btn = QPushButton("+ Add Tag")
        self.add_tag_btn.clicked.connect(self._on_add_tag)
        tag_buttons_layout.addWidget(self.add_tag_btn)

        self.remove_tag_btn = QPushButton("Remove Tag")
        self.remove_tag_btn.clicked.connect(self._on_remove_tag)
        self.remove_tag_btn.setEnabled(False)
        tag_buttons_layout.addWidget(self.remove_tag_btn)

        tag_buttons_layout.addStretch()

        tags_layout.addLayout(tag_buttons_layout)

        self.tags_list.itemSelectionChanged.connect(
            lambda: self.remove_tag_btn.setEnabled(len(self.tags_list.selectedItems()) > 0)
        )

        layout.addWidget(tags_group)

        # SKU Writeoff section
        writeoff_group = QGroupBox("SKU Writeoff")
        writeoff_layout = QVBoxLayout(writeoff_group)

        self.writeoff_enabled_checkbox = QCheckBox("Enable writeoff for this category")
        self.writeoff_enabled_checkbox.setToolTip(
            "When enabled, tags in this category can trigger automatic SKU writeoffs\n"
            "in stock exports (e.g., deduct packaging materials)"
        )
        self.writeoff_enabled_checkbox.stateChanged.connect(self._on_writeoff_enabled_changed)
        writeoff_layout.addWidget(self.writeoff_enabled_checkbox)

        mappings_label = QLabel("Writeoff Mappings:")
        mappings_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        writeoff_layout.addWidget(mappings_label)

        self.writeoff_mappings_table = QTableWidget()
        self.writeoff_mappings_table.setColumnCount(3)
        self.writeoff_mappings_table.setHorizontalHeaderLabels(["Tag", "SKU", "Quantity"])
        self.writeoff_mappings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.writeoff_mappings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.writeoff_mappings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.writeoff_mappings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.writeoff_mappings_table.setMaximumHeight(200)
        self.writeoff_mappings_table.setEnabled(False)
        self.writeoff_mappings_table.itemSelectionChanged.connect(
            self._update_remove_mapping_btn_state
        )
        writeoff_layout.addWidget(self.writeoff_mappings_table)

        mappings_buttons = QHBoxLayout()
        self.add_mapping_btn = QPushButton("+ Add Mapping")
        self.add_mapping_btn.clicked.connect(self._on_add_mapping)
        self.add_mapping_btn.setEnabled(False)
        mappings_buttons.addWidget(self.add_mapping_btn)

        self.remove_mapping_btn = QPushButton("Remove Mapping")
        self.remove_mapping_btn.clicked.connect(self._on_remove_mapping)
        self.remove_mapping_btn.setEnabled(False)
        mappings_buttons.addWidget(self.remove_mapping_btn)
        mappings_buttons.addStretch()

        writeoff_layout.addLayout(mappings_buttons)
        layout.addWidget(writeoff_group)

        layout.addStretch()

        self._set_editor_enabled(False)

        return panel

    # ------------------------------------------------------------------
    # Data management
    # ------------------------------------------------------------------

    def get_categories(self) -> Dict:
        """Return the current working categories dict (including pending edits)."""
        if self.current_category_id:
            self._save_editor_to_working_copy()
        return self.working_categories

    def _load_categories(self):
        """Load categories into the list widget."""
        self.categories_list.clear()

        categories = self.working_categories.get("categories", {})

        sorted_categories = sorted(
            categories.items(),
            key=lambda x: x[1].get("order", 999)
        )

        for category_id, category_config in sorted_categories:
            item = QListWidgetItem(category_config.get("label", category_id))
            item.setData(Qt.UserRole, category_id)
            color = category_config.get("color", "#9E9E9E")
            item.setBackground(QColor(color).lighter(180))
            self.categories_list.addItem(item)

    def _on_category_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle category selection change."""
        if current is None:
            self._set_editor_enabled(False)
            self.current_category_id = None
            return

        category_id = current.data(Qt.UserRole)
        self.current_category_id = category_id

        self._load_category_into_editor(category_id)
        self._set_editor_enabled(True)
        self.delete_category_btn.setEnabled(True)

    def _load_category_into_editor(self, category_id: str):
        """Load category data into editor fields."""
        categories = self.working_categories.get("categories", {})
        category = categories.get(category_id, {})

        self.category_id_input.blockSignals(True)
        self.label_input.blockSignals(True)
        self.order_spin.blockSignals(True)

        self.category_id_input.setText(category_id)
        self.category_id_input.setReadOnly(True)

        self.label_input.setText(category.get("label", ""))
        self.current_color = category.get("color", "#9E9E9E")
        self.color_display.setStyleSheet(f"border: 1px solid {self.theme.border}; background-color: {self.current_color};")
        self.order_spin.setValue(category.get("order", 1))

        self.tags_list.clear()
        for tag in category.get("tags", []):
            self.tags_list.addItem(tag)

        self.category_id_input.blockSignals(False)
        self.label_input.blockSignals(False)
        self.order_spin.blockSignals(False)

        sku_writeoff = category.get("sku_writeoff", {"enabled": False, "mappings": {}})

        self.writeoff_enabled_checkbox.blockSignals(True)

        enabled = sku_writeoff.get("enabled", False)
        self.writeoff_enabled_checkbox.setChecked(enabled)
        self.writeoff_mappings_table.setEnabled(enabled)
        self.add_mapping_btn.setEnabled(enabled)
        self.remove_mapping_btn.setEnabled(False)

        self.writeoff_mappings_table.setRowCount(0)
        mappings = sku_writeoff.get("mappings", {})

        for tag, sku_list in mappings.items():
            if not isinstance(sku_list, list):
                continue
            for item in sku_list:
                if not isinstance(item, dict):
                    continue
                if "sku" not in item or "quantity" not in item:
                    continue

                row_position = self.writeoff_mappings_table.rowCount()
                self.writeoff_mappings_table.insertRow(row_position)

                self.writeoff_mappings_table.setItem(row_position, 0, QTableWidgetItem(tag))
                self.writeoff_mappings_table.setItem(row_position, 1, QTableWidgetItem(item["sku"]))
                self.writeoff_mappings_table.setItem(row_position, 2, QTableWidgetItem(f"{item['quantity']:.2f}"))

        self.writeoff_enabled_checkbox.blockSignals(False)

        self.editor_header_label.setText(f"Editing: {category.get('label', category_id)}")

    def _on_theme_changed(self):
        """Handle theme changes."""
        self.theme = get_theme_manager().get_current_theme()
        if self.current_category_id:
            self.color_display.setStyleSheet(
                f"border: 1px solid {self.theme.border}; background-color: {self.current_color};"
            )

    def _set_editor_enabled(self, enabled: bool):
        """Enable/disable editor fields."""
        self.category_id_input.setEnabled(enabled)
        self.label_input.setEnabled(enabled)
        self.color_button.setEnabled(enabled)
        self.order_spin.setEnabled(enabled)
        self.tags_list.setEnabled(enabled)
        self.add_tag_btn.setEnabled(enabled)

        self.writeoff_enabled_checkbox.setEnabled(enabled)
        if enabled and self.writeoff_enabled_checkbox.isChecked():
            self.writeoff_mappings_table.setEnabled(True)
            self.add_mapping_btn.setEnabled(True)
        else:
            self.writeoff_mappings_table.setEnabled(False)
            self.add_mapping_btn.setEnabled(False)
            self.remove_mapping_btn.setEnabled(False)

        if not enabled:
            self.editor_header_label.setText("Category Editor")
            self.category_id_input.clear()
            self.label_input.clear()
            self.tags_list.clear()
            self.writeoff_mappings_table.setRowCount(0)
            self.writeoff_enabled_checkbox.setChecked(False)

    def _on_editor_changed(self):
        """Handle editor field changes."""
        if not self.current_category_id:
            return
        self._save_editor_to_working_copy()
        self.modified = True

    def _save_editor_to_working_copy(self):
        """Save current editor state to working copy."""
        if not self.current_category_id:
            return

        categories = self.working_categories.setdefault("categories", {})
        category = categories.setdefault(self.current_category_id, {})

        category["label"] = self.label_input.text()
        category["color"] = self.current_color
        category["order"] = self.order_spin.value()

        tags = []
        for i in range(self.tags_list.count()):
            tags.append(self.tags_list.item(i).text())
        category["tags"] = tags

        enabled = self.writeoff_enabled_checkbox.isChecked()

        mappings = {}
        for row in range(self.writeoff_mappings_table.rowCount()):
            tag_item = self.writeoff_mappings_table.item(row, 0)
            sku_item = self.writeoff_mappings_table.item(row, 1)
            quantity_item = self.writeoff_mappings_table.item(row, 2)

            if not tag_item or not sku_item or not quantity_item:
                continue

            tag = tag_item.text()
            sku = sku_item.text()
            quantity_str = quantity_item.text()

            try:
                quantity = float(quantity_str)
            except ValueError:
                logger.warning(f"Invalid quantity for writeoff mapping: {quantity_str}")
                quantity = 1.0

            if tag not in mappings:
                mappings[tag] = []

            mappings[tag].append({
                "sku": sku,
                "quantity": quantity
            })

        category["sku_writeoff"] = {
            "enabled": enabled,
            "mappings": mappings
        }

        current_item = self.categories_list.currentItem()
        if current_item:
            current_item.setText(category["label"])
            current_item.setBackground(QColor(self.current_color).lighter(180))

    def _choose_color(self):
        """Open color picker dialog."""
        color = QColorDialog.getColor(
            QColor(self.current_color),
            self,
            "Choose Category Color"
        )

        if color.isValid():
            self.current_color = color.name()
            self.color_display.setStyleSheet(
                f"border: 1px solid {self.theme.border}; background-color: {self.current_color};"
            )
            self._on_editor_changed()

    def _on_add_tag(self):
        """Handle add tag button click."""
        tag, ok = QInputDialog.getText(
            self,
            "Add Tag",
            "Enter tag name (UPPERCASE):",
            QLineEdit.Normal,
            ""
        )

        if ok and tag:
            tag = tag.strip().upper()

            if not tag:
                QMessageBox.warning(self, "Invalid Tag", "Tag cannot be empty.")
                return

            existing_tags = [self.tags_list.item(i).text() for i in range(self.tags_list.count())]
            if tag in existing_tags:
                QMessageBox.warning(self, "Duplicate Tag", f"Tag '{tag}' already exists in this category.")
                return

            if self._is_tag_in_other_categories(tag):
                QMessageBox.warning(
                    self,
                    "Duplicate Tag",
                    f"Tag '{tag}' already exists in another category.\n"
                    "Each tag can only belong to one category."
                )
                return

            self.tags_list.addItem(tag)
            self._on_editor_changed()

    def _on_remove_tag(self):
        """Handle remove tag button click."""
        selected_items = self.tags_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            self.tags_list.takeItem(self.tags_list.row(item))

        self._on_editor_changed()

    def _is_tag_in_other_categories(self, tag: str) -> bool:
        """Check if tag exists in other categories."""
        categories = self.working_categories.get("categories", {})

        for category_id, category_config in categories.items():
            if category_id == self.current_category_id:
                continue
            if tag in category_config.get("tags", []):
                return True

        return False

    def _update_remove_mapping_btn_state(self):
        """Update remove mapping button enabled state."""
        enabled = self.writeoff_enabled_checkbox.isChecked()
        has_selection = len(self.writeoff_mappings_table.selectedItems()) > 0
        self.remove_mapping_btn.setEnabled(enabled and has_selection)

    def _on_writeoff_enabled_changed(self, state):
        """Handle writeoff enabled checkbox state change."""
        enabled = (state == Qt.Checked)

        self.writeoff_mappings_table.setEnabled(enabled)
        self.add_mapping_btn.setEnabled(enabled)
        self._update_remove_mapping_btn_state()

        self._on_editor_changed()

    def _on_add_mapping(self):
        """Add a new writeoff mapping row."""
        if not self.current_category_id:
            return

        categories = self.working_categories.get("categories", {})
        category = categories.get(self.current_category_id, {})
        available_tags = category.get("tags", [])

        if not available_tags:
            QMessageBox.warning(
                self,
                "No Tags",
                "Please add tags to this category before creating writeoff mappings."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Add Writeoff Mapping")
        dialog_layout = QFormLayout(dialog)

        tag_combo = QComboBox()
        tag_combo.addItems(available_tags)
        dialog_layout.addRow("Tag:", tag_combo)

        sku_input = QLineEdit()
        sku_input.setPlaceholderText("e.g., PKG-BOX-SMALL")
        dialog_layout.addRow("SKU:", sku_input)

        quantity_spin = QDoubleSpinBox()
        quantity_spin.setMinimum(0.01)
        quantity_spin.setMaximum(999.99)
        quantity_spin.setDecimals(2)
        quantity_spin.setValue(1.0)
        dialog_layout.addRow("Quantity:", quantity_spin)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        dialog_layout.addRow(button_box)

        if dialog.exec() == QDialog.Accepted:
            tag = tag_combo.currentText()
            sku = sku_input.text().strip()
            quantity = quantity_spin.value()

            if not sku:
                QMessageBox.warning(self, "Invalid Input", "SKU cannot be empty.")
                return

            row_position = self.writeoff_mappings_table.rowCount()
            self.writeoff_mappings_table.insertRow(row_position)

            self.writeoff_mappings_table.setItem(row_position, 0, QTableWidgetItem(tag))
            self.writeoff_mappings_table.setItem(row_position, 1, QTableWidgetItem(sku))
            self.writeoff_mappings_table.setItem(row_position, 2, QTableWidgetItem(f"{quantity:.2f}"))

            self._on_editor_changed()

    def _on_remove_mapping(self):
        """Remove selected writeoff mapping."""
        selected_rows = set(index.row() for index in self.writeoff_mappings_table.selectedIndexes())

        if not selected_rows:
            return

        for row in sorted(selected_rows, reverse=True):
            self.writeoff_mappings_table.removeRow(row)

        self._on_editor_changed()

    def _on_new_category(self):
        """Handle new category button click."""
        category_id, ok = QInputDialog.getText(
            self,
            "New Category",
            "Enter category ID (lowercase, underscores only):",
            QLineEdit.Normal,
            ""
        )

        if not ok or not category_id:
            return

        category_id = category_id.strip().lower()

        if not category_id:
            QMessageBox.warning(self, "Invalid ID", "Category ID cannot be empty.")
            return

        if not category_id.replace("_", "").isalnum():
            QMessageBox.warning(
                self,
                "Invalid ID",
                "Category ID can only contain lowercase letters, numbers, and underscores."
            )
            return

        categories = self.working_categories.get("categories", {})
        if category_id in categories:
            QMessageBox.warning(self, "Duplicate ID", f"Category '{category_id}' already exists.")
            return

        new_category = {
            "label": category_id.replace("_", " ").title(),
            "color": "#9E9E9E",
            "order": len(categories) + 1,
            "tags": [],
            "sku_writeoff": {
                "enabled": False,
                "mappings": {}
            }
        }

        categories[category_id] = new_category
        self.modified = True

        self._load_categories()

        for i in range(self.categories_list.count()):
            item = self.categories_list.item(i)
            if item.data(Qt.UserRole) == category_id:
                self.categories_list.setCurrentItem(item)
                break

    def _on_delete_category(self):
        """Handle delete category button click."""
        if not self.current_category_id:
            return

        categories = self.working_categories.get("categories", {})
        category = categories.get(self.current_category_id, {})

        reply = QMessageBox.question(
            self,
            "Delete Category",
            f"Are you sure you want to delete category '{category.get('label', self.current_category_id)}'?\n\n"
            f"This category has {len(category.get('tags', []))} tags.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            del categories[self.current_category_id]
            self.modified = True

            self.current_category_id = None
            self._load_categories()
            self._set_editor_enabled(False)
            self.delete_category_btn.setEnabled(False)

    def validate_categories(self) -> tuple:
        """Validate current categories. Returns (is_valid, errors)."""
        if self.current_category_id:
            self._save_editor_to_working_copy()
        return validate_tag_categories_v2(self.working_categories)


class TagCategoriesDialog(QDialog):
    """Dialog wrapper around TagCategoriesPanel for standalone use."""

    categories_updated = Signal(dict)

    def __init__(self, tag_categories: Dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag Categories Management")
        self.setModal(True)
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)

        title_label = QLabel("Manage Tag Categories")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 10px;")
        layout.addWidget(title_label)

        self.panel = TagCategoriesPanel(tag_categories, parent=self)
        layout.addWidget(self.panel)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self._on_cancel)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        layout.addWidget(button_box)

        self.button_box = button_box

    def __getattr__(self, name):
        """Proxy attribute lookups to the embedded panel for backwards compatibility."""
        # Avoid infinite recursion during __init__ before self.panel exists
        panel = self.__dict__.get('panel')
        if panel is not None and hasattr(panel, name):
            return getattr(panel, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _validate(self) -> bool:
        is_valid, errors = self.panel.validate_categories()
        if not is_valid:
            error_msg = "Validation errors:\n\n" + "\n".join(f"- {err}" for err in errors)
            QMessageBox.critical(self, "Validation Failed", error_msg)
            return False
        return True

    def _on_apply(self):
        if not self._validate():
            return
        self.categories_updated.emit(self.panel.get_categories())
        self.panel.modified = False
        QMessageBox.information(self, "Saved", "Tag categories have been saved successfully.")

    def _on_save(self):
        if not self._validate():
            return
        self.categories_updated.emit(self.panel.get_categories())
        self.accept()

    def _on_cancel(self):
        if self.panel.modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Are you sure you want to cancel?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        self.reject()

    def get_categories(self) -> Dict:
        """Get the current categories configuration."""
        return self.panel.get_categories()
