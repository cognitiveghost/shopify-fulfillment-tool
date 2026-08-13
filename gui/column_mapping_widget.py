"""Column Mapping Widget for Shopify Fulfillment Tool.

This widget provides an intuitive UI for mapping CSV column names to internal field names.
Users can see the relationship between their CSV columns and the internal processing names.
"""

import logging
from typing import ClassVar

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget

from gui.components.form_section import FormSection

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

    # Only fields whose effect is not obvious from the name. A warehouse
    # operator setting up lot tracking has no other way to learn what these do.
    FIELD_TOOLTIPS: ClassVar[dict[str, str]] = {
        "Expiry_Date": (
            "Optional. When mapped, stock is allocated oldest-expiry-first (FIFO) "
            "and each packing list row shows the lot it came from.\n"
            "Understood formats: YYMMDD, YYYYMMDD, DDMMYY, MMYY."
        ),
        "Batch": (
            "Optional. Lot or batch number. Shown per lot on packing lists, and "
            "used to keep separate deliveries of the same SKU apart."
        ),
    }

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
        """Setup the UI layout.

        No QScrollArea here: the settings page already scrolls, and nesting a
        second one clips this widget to a few rows. One FormSection per group;
        the internal field name is the row label, so the per-row
        "Your CSV Column:" label and the -> arrow both go.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.required_fields:
            required_section = FormSection("Required")
            for internal_name in self.required_fields:
                self._add_mapping_row(required_section, internal_name, required=True)
            layout.addWidget(required_section)

        if self.optional_fields:
            optional_section = FormSection("Optional")
            for internal_name in self.optional_fields:
                self._add_mapping_row(optional_section, internal_name, required=False)
            layout.addWidget(optional_section)

    def _add_mapping_row(self, section, internal_name, required=False):
        """Add one internal-field row to `section`.

        Args:
            section (FormSection): The section to append the row to.
            internal_name (str): The internal field name (e.g. "Order_Number").
            required (bool): Whether this field is required.
        """
        csv_input = QComboBox()
        csv_input.setEditable(True)
        csv_input.setInsertPolicy(QComboBox.NoInsert)
        csv_input.lineEdit().setPlaceholderText("Enter column name...")
        csv_input.setCurrentText(self.internal_to_csv.get(internal_name, ""))
        csv_input.currentTextChanged.connect(lambda: self.mappings_changed.emit())

        self.csv_column_inputs[internal_name] = csv_input
        section.add_row(
            f"{internal_name} *" if required else internal_name,
            csv_input,
            tooltip=self.FIELD_TOOLTIPS.get(
                internal_name,
                "Required — the save is blocked until this is mapped."
                if required
                else "",
            ),
        )

    def get_mappings(self):
        """Get current mappings from UI.

        Entries for internal names this widget has no row for are carried
        through untouched. Without that, a field missing from
        required_fields/optional_fields is silently deleted from the client's
        config on every save -- which is exactly what happened to the
        Expiry_Date and Batch mappings that drive FIFO lot allocation.

        A *managed* field left blank is still removed: its old entry was
        never carried over, so clearing a box does delete the mapping.

        Returns:
            dict: Dictionary of {csv_column_name: internal_name}
        """
        managed = set(self.required_fields) | set(self.optional_fields)
        mappings = {
            csv_column: internal_name
            for csv_column, internal_name in self.current_mappings.items()
            if internal_name not in managed
        }

        for internal_name in self.required_fields + self.optional_fields:
            input_widget = self.csv_column_inputs.get(internal_name)
            if input_widget:
                csv_column = input_widget.currentText().strip()
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
            csv_column = self.csv_column_inputs[internal_name].currentText().strip()
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
            input_widget.setCurrentText(csv_column)

    def set_available_headers(self, headers):
        """Offer `headers` as dropdown options on every row.

        The text already in each box is preserved -- a configured mapping
        whose column is absent from the file the user just picked must not be
        wiped by looking at that file. A header already used by another row is
        still offered; validate_mappings() catches the duplicate on Save,
        which is where that error belongs.

        Args:
            headers (list): Column names read from a CSV.
        """
        for input_widget in self.csv_column_inputs.values():
            current = input_widget.currentText()
            input_widget.clear()
            input_widget.addItems(headers)
            input_widget.setCurrentText(current)
