"""Column mappings, split one page per CSV: orders (plus courier name
mappings, which resolve an orders column) and stock."""

from typing import ClassVar

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.column_mapping_widget import ColumnMappingWidget
from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage
from gui.theme_manager import get_theme_manager, set_button_role


class _MappingPageBase(SettingsPage):
    """Shared scaffolding: one scroll area, one column-mapping widget.

    Both pages hold the SAME live config_data["column_mappings"] dict and
    write only their own sub-key into it, in place. Never clear() it and
    never rebuild it -- whichever page collect()s second would wipe the
    other's sub-key, and _pages order would silently decide which.
    """

    MAPPING_TYPE = ""
    TITLE = ""
    DESCRIPTION = ""
    # ClassVar, not a bare annotation: ruff's RUF012 rejects a mutable class
    # attribute without it, and window.py already uses this for the same reason.
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    OPTIONAL_FIELDS: ClassVar[list[str]] = []

    def __init__(self, column_mappings: dict, parent=None):
        super().__init__(parent)
        self.column_mappings = column_mappings

        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)

        box = FormSection(self.TITLE, self.DESCRIPTION)
        self.mapping_widget = ColumnMappingWidget(
            mapping_type=self.MAPPING_TYPE,
            current_mappings=column_mappings.get(self.MAPPING_TYPE, {}),
            required_fields=self.REQUIRED_FIELDS,
            optional_fields=self.OPTIONAL_FIELDS,
        )
        box.add_widget(self.mapping_widget)
        self.scroll_layout.addWidget(box)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

    def validate(self) -> tuple[bool, list[str]]:
        ok, error = self.mapping_widget.validate_mappings()
        if not ok:
            return False, [f"{self.TITLE} is invalid:\n{error}"]
        return True, []

    def _collect_column_mappings(self) -> dict:
        """Write this page's sub-key into the live dict and return it."""
        self.column_mappings["version"] = 2
        self.column_mappings[self.MAPPING_TYPE] = self.mapping_widget.get_mappings()
        return self.column_mappings


class OrdersMappingPage(_MappingPageBase):
    """Orders CSV columns, plus the courier name mappings that resolve the
    Shipping_Method values those columns carry."""

    MAPPING_TYPE = "orders"
    TITLE = "Orders CSV Column Mapping"
    DESCRIPTION = "Map your CSV column names to internal fields for the ORDERS file."
    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "Order_Number", "SKU", "Quantity", "Shipping_Method",
    ]
    OPTIONAL_FIELDS: ClassVar[list[str]] = [
        "Product_Name", "Shipping_Country", "Tags", "Notes", "Total_Price", "Subtotal",
    ]

    def __init__(self, column_mappings: dict, courier_mappings: dict, parent=None):
        super().__init__(column_mappings, parent)
        self.courier_mappings = courier_mappings
        self.courier_mapping_widgets = []
        self.orders_mapping_widget = self.mapping_widget  # name used by tests/callers

        courier_box = FormSection(
            "Courier Mappings",
            "Map different shipping provider names to standardized courier codes. "
            "You can specify multiple patterns (comma-separated) for each courier.",
        )
        self.courier_mappings_container = QWidget()
        self.courier_mappings_layout = QVBoxLayout(self.courier_mappings_container)
        self.courier_mappings_layout.setContentsMargins(0, 0, 0, 0)
        courier_box.add_widget(self.courier_mappings_container)

        add_courier_btn = QPushButton("+ Add Courier Mapping")
        set_button_role(add_courier_btn, "secondary")
        add_courier_btn.clicked.connect(lambda: self.add_courier_mapping_row())
        add_courier_btn.setMaximumWidth(200)
        courier_box.add_widget(add_courier_btn)

        self.scroll_layout.addWidget(courier_box)
        self.scroll_layout.addStretch()

        if isinstance(courier_mappings, dict):
            for courier_code, mapping_data in courier_mappings.items():
                if isinstance(mapping_data, dict):
                    patterns = mapping_data.get("patterns", [])
                    self.add_courier_mapping_row(courier_code, ", ".join(patterns) if patterns else "")

        if not courier_mappings:
            self.add_courier_mapping_row()

    def add_courier_mapping_row(self, courier_code="", patterns_str=""):
        """Adds a new row for a single courier mapping.

        Args:
            courier_code: Standardized courier code (e.g., "DHL", "DPD", "Speedy")
            patterns_str: Comma-separated patterns (e.g., "dhl, dhl express, dhl_express")
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 5, 0, 5)

        # Courier Code
        code_label = QLabel("Code:")
        code_label.setFixedWidth(50)
        courier_edit = QLineEdit(courier_code)
        courier_edit.setPlaceholderText("DHL, DPD, Speedy...")
        courier_edit.setMinimumWidth(100)
        courier_edit.setMaximumWidth(150)

        # Patterns
        patterns_label = QLabel("Patterns:")
        patterns_label.setFixedWidth(70)
        patterns_edit = QLineEdit(patterns_str)
        patterns_edit.setPlaceholderText("dhl, dhl express, dhl_express")
        patterns_edit.setMinimumWidth(300)

        # Delete button
        delete_btn = QPushButton("✕")
        set_button_role(delete_btn, "secondary")
        delete_btn.setFixedWidth(30)
        theme = get_theme_manager().get_current_theme()
        # Sets only `color`, so the secondary role's background still applies.
        delete_btn.setStyleSheet(f"color: {theme.accent_red}; font-weight: bold;")
        delete_btn.setToolTip("Remove this courier mapping")

        row_layout.addWidget(code_label)
        row_layout.addWidget(courier_edit, 1)
        row_layout.addWidget(patterns_label)
        row_layout.addWidget(patterns_edit, 3)
        row_layout.addWidget(delete_btn)
        row_layout.addStretch()

        self.courier_mappings_layout.addWidget(row_widget)

        row_refs = {
            "widget": row_widget,
            "courier_code": courier_edit,
            "patterns": patterns_edit,
        }
        self.courier_mapping_widgets.append(row_refs)

        delete_btn.clicked.connect(lambda: self._delete_courier_row(row_refs))

    def _delete_courier_row(self, row_refs):
        row_refs["widget"].deleteLater()
        self.courier_mapping_widgets.remove(row_refs)

    def collect(self) -> dict:
        new_couriers = {}
        for row_refs in self.courier_mapping_widgets:
            courier_code = row_refs["courier_code"].text().strip()
            patterns_str = row_refs["patterns"].text().strip()
            if courier_code and patterns_str:
                patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
                new_couriers[courier_code] = {"patterns": patterns, "case_sensitive": False}

        # Same live-dict contract as column_mappings: clear-and-refill in
        # place so a deleted courier code does not survive the shell's merge.
        self.courier_mappings.clear()
        self.courier_mappings.update(new_couriers)

        return {
            "column_mappings": self._collect_column_mappings(),
            "courier_mappings": self.courier_mappings,
        }


class StockMappingPage(_MappingPageBase):
    """Stock CSV columns, including the two that drive FIFO lot allocation."""

    MAPPING_TYPE = "stock"
    TITLE = "Stock CSV Column Mapping"
    DESCRIPTION = "Map your CSV column names to internal fields for the STOCK file."
    REQUIRED_FIELDS: ClassVar[list[str]] = ["SKU", "Stock"]
    # Expiry_Date and Batch are the exact internal names _build_fifo_lots()
    # looks for (shopify_tool/analysis.py:96-97) -- renaming them here
    # silently turns FIFO lot allocation off.
    OPTIONAL_FIELDS: ClassVar[list[str]] = ["Product_Name", "Expiry_Date", "Batch"]

    def __init__(self, column_mappings: dict, parent=None):
        super().__init__(column_mappings, parent)
        self.stock_mapping_widget = self.mapping_widget  # name used by tests/callers
        self.scroll_layout.addStretch()

    def collect(self) -> dict:
        return {"column_mappings": self._collect_column_mappings()}
