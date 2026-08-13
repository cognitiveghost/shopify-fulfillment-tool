"""Column mappings (orders/stock) and courier-name mappings."""

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


class MappingsPage(SettingsPage):
    """Column and courier mappings, stored under config_data["column_mappings"]
    and config_data["courier_mappings"]."""

    def __init__(self, column_mappings: dict, courier_mappings: dict, parent=None):
        super().__init__(parent)
        # Held by reference (not copied) so collect() can mutate them in place --
        # see the comment on collect() for why that matters.
        self.column_mappings = column_mappings
        self.courier_mappings = courier_mappings
        self.courier_mapping_widgets = []

        main_layout = QVBoxLayout(self)

        # Add scroll area for the entire tab
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # ========================================
        # COLUMN MAPPINGS - Orders
        # ========================================
        orders_box = FormSection("Orders CSV Column Mapping")

        # Define required and optional fields for orders
        orders_required = ["Order_Number", "SKU", "Quantity", "Shipping_Method"]
        orders_optional = ["Product_Name", "Shipping_Country", "Tags", "Notes", "Total_Price", "Subtotal"]

        orders_mappings = column_mappings.get("orders", {})

        self.orders_mapping_widget = ColumnMappingWidget(
            mapping_type="orders",
            current_mappings=orders_mappings,
            required_fields=orders_required,
            optional_fields=orders_optional
        )

        orders_box.add_widget(self.orders_mapping_widget)
        scroll_layout.addWidget(orders_box)

        # ========================================
        # COLUMN MAPPINGS - Stock
        # ========================================
        stock_box = FormSection("Stock CSV Column Mapping")

        # Define required and optional fields for stock.
        # Expiry_Date and Batch are the exact internal names _build_fifo_lots()
        # looks for (shopify_tool/analysis.py:96-97) -- renaming them here
        # silently turns FIFO lot allocation off.
        stock_required = ["SKU", "Stock"]
        stock_optional = ["Product_Name", "Expiry_Date", "Batch"]

        stock_mappings = column_mappings.get("stock", {})

        self.stock_mapping_widget = ColumnMappingWidget(
            mapping_type="stock",
            current_mappings=stock_mappings,
            required_fields=stock_required,
            optional_fields=stock_optional
        )

        stock_box.add_widget(self.stock_mapping_widget)
        scroll_layout.addWidget(stock_box)

        # ========================================
        # COURIER MAPPINGS
        # ========================================
        courier_mappings_box = FormSection(
            "Courier Mappings",
            "Map different shipping provider names to standardized courier codes. "
            "You can specify multiple patterns (comma-separated) for each courier.",
        )

        # Container for courier mapping rows
        self.courier_mappings_container = QWidget()
        self.courier_mappings_layout = QVBoxLayout(self.courier_mappings_container)
        self.courier_mappings_layout.setContentsMargins(0, 0, 0, 0)

        courier_mappings_box.add_widget(self.courier_mappings_container)

        add_courier_btn = QPushButton("+ Add Courier Mapping")
        set_button_role(add_courier_btn, "secondary")
        add_courier_btn.clicked.connect(lambda: self.add_courier_mapping_row())
        add_courier_btn.setMaximumWidth(200)
        courier_mappings_box.add_widget(add_courier_btn)

        scroll_layout.addWidget(courier_mappings_box)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # Populate existing courier mappings
        if isinstance(courier_mappings, dict):
            for courier_code, mapping_data in courier_mappings.items():
                if isinstance(mapping_data, dict):
                    patterns = mapping_data.get("patterns", [])
                    patterns_str = ", ".join(patterns) if patterns else ""
                    self.add_courier_mapping_row(courier_code, patterns_str)

        # Add at least one empty row if no mappings exist
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

    def validate(self) -> tuple[bool, list[str]]:
        orders_valid, orders_error = self.orders_mapping_widget.validate_mappings()
        if not orders_valid:
            return False, [f"Orders column mapping is invalid:\n{orders_error}"]

        stock_valid, stock_error = self.stock_mapping_widget.validate_mappings()
        if not stock_valid:
            return False, [f"Stock column mapping is invalid:\n{stock_error}"]

        return True, []

    def collect(self) -> dict:
        orders_mappings = self.orders_mapping_widget.get_mappings()
        stock_mappings = self.stock_mapping_widget.get_mappings()

        new_couriers = {}
        for row_refs in self.courier_mapping_widgets:
            courier_code = row_refs["courier_code"].text().strip()
            patterns_str = row_refs["patterns"].text().strip()

            if courier_code and patterns_str:
                patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
                new_couriers[courier_code] = {"patterns": patterns, "case_sensitive": False}

        # SettingsPage's contract: the returned value replaces
        # config_data[key], so these must be the live dicts handed to
        # __init__ -- clear-and-refill in place, never a fresh dict.
        self.column_mappings.clear()
        self.column_mappings.update({"version": 2, "orders": orders_mappings, "stock": stock_mappings})
        self.courier_mappings.clear()
        self.courier_mappings.update(new_couriers)

        return {
            "column_mappings": self.column_mappings,
            "courier_mappings": self.courier_mappings,
        }
