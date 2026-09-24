"""General settings: CSV delimiters and analysis thresholds."""

from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox, QVBoxLayout

from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage

_DELIMITERS = [
    ("Auto — detect per file", "auto"),
    ("Comma  ,", ","),
    ("Semicolon  ;", ";"),
    ("Tab", "\t"),
    ("Pipe  |", "|"),
]
_DELIMITER_TOOLTIP = (
    "Auto reads each file's own delimiter.\n"
    "Pick a character only for a client whose files Auto reads wrong."
)


def _delimiter_combo(value: str) -> QComboBox:
    combo = QComboBox()
    for label, data in _DELIMITERS:
        combo.addItem(label, data)
    index = combo.findData(value)
    if index < 0:  # hand-edited value: keep it rather than rewrite it on save
        combo.addItem(repr(value), value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)
    return combo


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

        self.stock_delimiter_combo = _delimiter_combo(
            settings.get("stock_csv_delimiter", "auto")
        )
        section.add_row(
            "Stock CSV Delimiter:",
            self.stock_delimiter_combo,
            tooltip=_DELIMITER_TOOLTIP,
        )

        self.orders_delimiter_combo = _delimiter_combo(
            settings.get("orders_csv_delimiter", "auto")
        )
        section.add_row(
            "Orders CSV Delimiter:",
            self.orders_delimiter_combo,
            tooltip=_DELIMITER_TOOLTIP,
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
        self.repeat_days_input.setMaximumWidth(100)
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
        self._settings.update(
            {
                "stock_csv_delimiter": self.stock_delimiter_combo.currentData(),
                "orders_csv_delimiter": self.orders_delimiter_combo.currentData(),
                "low_stock_threshold": int(self.low_stock_edit.text()),
                "repeat_detection_days": self.repeat_days_input.value(),
            }
        )
        return {"settings": self._settings}
