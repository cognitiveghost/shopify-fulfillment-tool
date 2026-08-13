"""General settings: CSV delimiters and analysis thresholds."""

from PySide6.QtWidgets import QLineEdit, QSpinBox, QVBoxLayout

from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage


class GeneralPage(SettingsPage):
    """Delimiters and thresholds, stored under config_data["settings"]."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        # Held by reference so collect() can update it in place. The shell
        # assigns collect()'s value straight over config_data[key], so a
        # fresh dict here would drop any key this page does not render.
        self._settings = settings
        main_layout = QVBoxLayout(self)

        section = FormSection("General Settings")

        self.stock_delimiter_edit = QLineEdit(settings.get("stock_csv_delimiter", ";"))
        self.stock_delimiter_edit.setMaximumWidth(100)
        section.add_row(
            "Stock CSV Delimiter:",
            self.stock_delimiter_edit,
            tooltip=(
                "Character used to separate columns in stock CSV file.\n\n"
                "Common values:\n"
                "  • Semicolon (;) - for exports from local warehouse\n"
                "  • Comma (,) - for Shopify exports\n\n"
                "Make sure this matches your stock CSV file format."
            ),
        )

        self.orders_delimiter_edit = QLineEdit(settings.get("orders_csv_delimiter", ","))
        self.orders_delimiter_edit.setMaximumWidth(100)
        self.orders_delimiter_edit.setPlaceholderText(",")
        section.add_row(
            "Orders CSV Delimiter:",
            self.orders_delimiter_edit,
            tooltip=(
                "Character used to separate columns in orders CSV file.\n\n"
                "Common values:\n"
                "  • Comma (,) - standard Shopify exports\n"
                "  • Semicolon (;) - European Excel exports\n"
                "  • Tab (\\t) - tab-separated files\n\n"
                "The tool will auto-detect delimiter when you select a file,\n"
                "but you can override it here if needed."
            ),
        )

        self.low_stock_edit = QLineEdit(str(settings.get("low_stock_threshold", 5)))
        self.low_stock_edit.setMaximumWidth(100)
        section.add_row(
            "Low Stock Threshold:",
            self.low_stock_edit,
            tooltip=(
                "Trigger stock alerts when quantity falls below this number.\n\n"
                "Items with stock below this threshold will be marked in analysis."
            ),
        )

        self.repeat_days_input = QSpinBox()
        self.repeat_days_input.setMinimum(1)
        self.repeat_days_input.setMaximum(365)
        self.repeat_days_input.setValue(settings.get("repeat_detection_days", 1))
        section.add_row(
            "Repeat Detection Window (days):",
            self.repeat_days_input,
            tooltip=(
                "Orders fulfilled within this many days are marked as 'Repeat'.\n"
                "Default: 1 day (only yesterday's fulfillments)\n"
                "Increase for longer detection window (e.g., 7 days, 30 days)"
            ),
        )

        main_layout.addWidget(section)
        main_layout.addStretch()

    def collect(self) -> dict:
        self._settings.update({
            "stock_csv_delimiter": self.stock_delimiter_edit.text(),
            "orders_csv_delimiter": self.orders_delimiter_edit.text(),
            "low_stock_threshold": int(self.low_stock_edit.text()),
            "repeat_detection_days": self.repeat_days_input.value(),
        })
        return {"settings": self._settings}
