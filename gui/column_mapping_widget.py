"""Column Mapping Widget for Shopify Fulfillment Tool.

This widget provides an intuitive UI for mapping CSV column names to internal field names.
Users can see the relationship between their CSV columns and the internal processing names.
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QScrollArea, QMessageBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from gui.theme_manager import get_theme_manager

logger = logging.getLogger("ShopifyToolLogger")


class ColumnMappingWidget(QWidget):
    """Widget for editing column mappings between CSV and internal names.

    Displays a grid where users can:
    - See required internal field names (fixed)
    - Edit CSV column names that map to each internal field
    - Visual indication of required vs optional fields

    Args:
        mapping_type (str): Type of mapping - "orders" or "stock"
        current_mappings (dict): Current mappings {csv_name: internal_name}
        required_fields (list): List of internal names that are required
        optional_fields (list): List of internal names that are optional
    """

    mappings_changed = Signal()

    def __init__(self, mapping_type, current_mappings=None, required_fields=None, optional_fields=None):
        super().__init__()
        self.mapping_type = mapping_type
        self.current_mappings = current_mappings or {}
        self.required_fields = required_fields or []
        self.optional_fields = optional_fields or []

        # Reverse mapping: internal_name -> csv_column_name
        self.internal_to_csv = {v: k for k, v in self.current_mappings.items()}

        # Store widgets for accessing values
        self.csv_column_inputs = {}  # {internal_name: QLineEdit}

        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Instructions
        instructions = QLabel(
            f"Map your CSV column names to internal fields for {self.mapping_type.upper()} file.\n"
            f"Fields marked with * are required."
        )
        instructions.setWordWrap(True)
        theme = get_theme_manager().get_current_theme()
        instructions.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; padding: 5px;")
        layout.addWidget(instructions)

        # Scroll area for mappings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Required fields section
        if self.required_fields:
            required_group = QGroupBox("Required Fields *")
            required_group.setStyleSheet("QGroupBox { font-weight: bold; }")
            required_layout = QVBoxLayout(required_group)

            for internal_name in self.required_fields:
                row_widget = self._create_mapping_row(internal_name, required=True)
                required_layout.addWidget(row_widget)

            scroll_layout.addWidget(required_group)

        # Optional fields section
        if self.optional_fields:
            optional_group = QGroupBox("Optional Fields")
            optional_layout = QVBoxLayout(optional_group)

            for internal_name in self.optional_fields:
                row_widget = self._create_mapping_row(internal_name, required=False)
                optional_layout.addWidget(row_widget)

            scroll_layout.addWidget(optional_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Help text at bottom
        help_text = QLabel(
            "Enter the exact column names as they appear in your CSV file.\n"
            "Example: 'Name' → 'Order_Number' means your CSV has a 'Name' column "
            "that will be used for order numbers."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("background-color: #e8f4f8; padding: 10px; border-radius: 5px; font-size: 9pt;")
        layout.addWidget(help_text)

    def _create_mapping_row(self, internal_name, required=False):
        """Create a single mapping row.

        Args:
            internal_name (str): The internal field name (e.g., "Order_Number")
            required (bool): Whether this field is required

        Returns:
            QWidget: Widget containing the mapping row
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(5, 3, 5, 3)

        # CSV Column input (left side)
        csv_label = QLabel("Your CSV Column:")
        csv_label.setFixedWidth(120)

        csv_input = QLineEdit()
        csv_input.setPlaceholderText(f"Enter column name...")
        csv_input.setMinimumWidth(200)

        # Set current value if exists
        current_csv_name = self.internal_to_csv.get(internal_name, "")
        if current_csv_name:
            csv_input.setText(current_csv_name)

        # Connect change signal
        csv_input.textChanged.connect(lambda: self.mappings_changed.emit())

        # Store for later access
        self.csv_column_inputs[internal_name] = csv_input

        # Arrow
        arrow_label = QLabel("→")
        arrow_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        arrow_label.setFixedWidth(30)
        arrow_label.setAlignment(Qt.AlignCenter)

        # Internal name label (right side)
        internal_label = QLabel(internal_name)
        internal_label.setStyleSheet("font-family: monospace; font-weight: bold;")
        internal_label.setFixedWidth(150)

        # Required indicator
        if required:
            required_indicator = QLabel("*")
            required_indicator.setStyleSheet("color: red; font-size: 16pt; font-weight: bold;")
            required_indicator.setFixedWidth(15)
            required_indicator.setToolTip("This field is required")
        else:
            required_indicator = QLabel("")
            required_indicator.setFixedWidth(15)

        # Add to layout
        row_layout.addWidget(csv_label)
        row_layout.addWidget(csv_input, 1)
        row_layout.addWidget(arrow_label)
        row_layout.addWidget(internal_label)
        row_layout.addWidget(required_indicator)
        row_layout.addStretch()

        return row_widget

    def get_mappings(self):
        """Get current mappings from UI.

        Returns:
            dict: Dictionary of {csv_column_name: internal_name}
        """
        mappings = {}

        # Combine required and optional fields
        all_fields = self.required_fields + self.optional_fields

        for internal_name in all_fields:
            input_widget = self.csv_column_inputs.get(internal_name)
            if input_widget:
                csv_column = input_widget.text().strip()
                if csv_column:  # Only add non-empty mappings
                    mappings[csv_column] = internal_name

        return mappings

    def validate_mappings(self):
        """Validate current mappings.

        Returns:
            tuple: (is_valid, error_message)
        """
        mappings = self.get_mappings()

        # Check that all required fields are mapped
        for internal_name in self.required_fields:
            csv_column = self.csv_column_inputs[internal_name].text().strip()
            if not csv_column:
                return False, f"Required field '{internal_name}' must be mapped to a CSV column"

        # Check for duplicate CSV column names
        csv_columns = list(mappings.keys())
        if len(csv_columns) != len(set(csv_columns)):
            duplicates = [col for col in csv_columns if csv_columns.count(col) > 1]
            return False, f"Duplicate CSV column names: {', '.join(set(duplicates))}"

        # Check that no two CSV columns map to the same internal name
        internal_names = list(mappings.values())
        if len(internal_names) != len(set(internal_names)):
            duplicates = [name for name in internal_names if internal_names.count(name) > 1]
            return False, f"Multiple CSV columns mapping to same internal field: {', '.join(set(duplicates))}"

        return True, ""

    def set_mappings(self, mappings):
        """Set mappings from dictionary.

        Args:
            mappings (dict): Dictionary of {csv_column_name: internal_name}
        """
        self.current_mappings = mappings
        self.internal_to_csv = {v: k for k, v in mappings.items()}

        # Update all input widgets
        for internal_name, input_widget in self.csv_column_inputs.items():
            csv_column = self.internal_to_csv.get(internal_name, "")
            input_widget.setText(csv_column)
