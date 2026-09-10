"""One tool's print settings, folded behind a row that states them.

Reference labels and Barcode labels each carried the same 80-line print block,
with every control always visible and four of five greyed out by mode. This is
that block once: the controls a mode does not use are hidden rather than
disabled, and the closed fold shows the current values, so nobody opens it to
check which printer is selected.

See docs/superpowers/specs/2026-09-10-phase9-bundle8-tools-inner-tabs-design.md §4.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.components.form_section import FormSection, row_widget
from gui.pdf_printing import load_print_settings, save_print_settings
from shared.theme import on_theme_changed

# Shared with both Tools cards so their fields and these start at one inset.
LABEL_WIDTH = 120


def print_summary(settings: dict) -> str:
    """The folded row's text: the current settings as one sentence."""
    if settings.get("print_mode") == "raw_zpl":
        target = (settings.get("raw_zpl_target") or "").strip()
        if not target:
            return "Raw ZPL needs a printer target. Open to set one."
        width = settings.get("raw_zpl_label_width_mm") or 0.0
        height = settings.get("raw_zpl_label_height_mm") or 0.0
        size = (
            f"{width:g} × {height:g} mm" if width and height else "the PDF's page size"
        )
        text = f"Prints raw ZPL to {target} at {size}"
        if settings.get("raw_zpl_rotate"):
            text += ", rotated 90°"
        return text
    printer = settings.get("driver_printer_name") or "the Windows default printer"
    return f"Prints through the print dialog to {printer}"


class PrintOptions(QWidget):
    """A fold button stating the settings, over the rows that change them."""

    changed = Signal()

    def __init__(self, scope: str, *, label_size_tooltip: str, parent=None) -> None:
        super().__init__(parent)
        self._scope = scope
        settings = load_print_settings(scope)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.fold_button = QToolButton(self)
        self.fold_button.setCheckable(True)
        self.fold_button.setAutoRaise(True)
        self.fold_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.fold_button.setAccessibleName("Print options")
        # Ignored: a long printer target must clip, never widen the card.
        # The tooltip carries the full text.
        self.fold_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.fold_button.toggled.connect(self.set_open)
        layout.addWidget(self.fold_button)

        self.body = FormSection("", label_width=LABEL_WIDTH)
        layout.addWidget(self.body)

        self.print_mode_combo = QComboBox()
        self.print_mode_combo.addItem("OS driver (print dialog)", "driver")
        self.print_mode_combo.addItem("Raw ZPL (direct)", "raw_zpl")
        index = self.print_mode_combo.findData(settings["print_mode"])
        if index >= 0:
            self.print_mode_combo.setCurrentIndex(index)
        self.body.add_row("Print mode", self.print_mode_combo)

        self.driver_printer_combo = QComboBox()
        # Otherwise its minimum width is its longest printer name, and a print
        # server's names are long enough to push the card past its slot.
        self.driver_printer_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.driver_printer_combo.setMinimumContentsLength(20)
        self.driver_printer_combo.addItem("(Windows default)", "")
        for info in QPrinterInfo.availablePrinters():
            self.driver_printer_combo.addItem(info.printerName(), info.printerName())
        index = self.driver_printer_combo.findData(settings["driver_printer_name"])
        if index >= 0:
            self.driver_printer_combo.setCurrentIndex(index)
        self.body.add_row("Printer", self.driver_printer_combo)

        self.raw_zpl_target_edit = QLineEdit(settings["raw_zpl_target"])
        self.raw_zpl_target_edit.setPlaceholderText(
            "e.g. ZPL-RAW-Printer (Windows) or /dev/usb/lp0 (Linux)"
        )
        self.body.add_row("Raw ZPL target", self.raw_zpl_target_edit)

        self.raw_zpl_label_width_spin = self._mm_spin(
            settings["raw_zpl_label_width_mm"], label_size_tooltip
        )
        self.raw_zpl_label_height_spin = self._mm_spin(
            settings["raw_zpl_label_height_mm"], label_size_tooltip
        )
        self._label_size_row = row_widget(
            self.raw_zpl_label_width_spin, QLabel("×"), self.raw_zpl_label_height_spin
        )
        self.body.add_row("Label size (mm)", self._label_size_row)

        self.raw_zpl_rotate_check = QCheckBox("Rotate 90°")
        self.raw_zpl_rotate_check.setChecked(settings["raw_zpl_rotate"])
        self.body.add_row("", self.raw_zpl_rotate_check)

        # Connected after the values are loaded, so construction saves nothing.
        self.print_mode_combo.currentIndexChanged.connect(
            self._update_zpl_controls_visible
        )
        self.print_mode_combo.currentIndexChanged.connect(self._on_edited)
        self.raw_zpl_target_edit.editingFinished.connect(self._on_edited)
        self.raw_zpl_rotate_check.toggled.connect(self._on_edited)
        self.raw_zpl_label_width_spin.editingFinished.connect(self._on_edited)
        self.raw_zpl_label_height_spin.editingFinished.connect(self._on_edited)
        self.driver_printer_combo.currentIndexChanged.connect(self._on_edited)

        self._update_zpl_controls_visible()
        self._refresh_summary()
        self.set_open(False)
        on_theme_changed(self.fold_button, self._style_fold_button)

    @staticmethod
    def _mm_spin(value: float, tooltip: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 500.0)
        spin.setDecimals(1)
        spin.setSpecialValueText("(use PDF page size)")
        spin.setValue(value)
        spin.setToolTip(tooltip)
        return spin

    def current_settings(self) -> dict:
        """The dict save_print_settings takes, read from the controls."""
        return {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
            "raw_zpl_label_width_mm": self.raw_zpl_label_width_spin.value(),
            "raw_zpl_label_height_mm": self.raw_zpl_label_height_spin.value(),
            "driver_printer_name": self.driver_printer_combo.currentData(),
        }

    def is_open(self) -> bool:
        return self.fold_button.isChecked()

    def set_open(self, open_: bool) -> None:
        """Show or hide the rows. No animation: QSS has no transitions."""
        self.fold_button.setChecked(open_)  # no-op, and no signal, when unchanged
        self.fold_button.setArrowType(Qt.DownArrow if open_ else Qt.RightArrow)
        self.body.setVisible(open_)

    def _update_zpl_controls_visible(self, *_args) -> None:
        """Hide the rows the chosen mode does not use -- hidden, not greyed out."""
        is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
        form = self.body.form
        form.setRowVisible(self.driver_printer_combo, not is_zpl)
        form.setRowVisible(self.raw_zpl_target_edit, is_zpl)
        form.setRowVisible(self._label_size_row, is_zpl)
        form.setRowVisible(self.raw_zpl_rotate_check, is_zpl)

    def _on_edited(self, *_args) -> None:
        save_print_settings(self._scope, self.current_settings())
        self._refresh_summary()
        self.changed.emit()

    def _refresh_summary(self) -> None:
        text = print_summary(self.current_settings())
        self.fold_button.setText(text)
        self.fold_button.setToolTip(text)

    def _style_fold_button(self, tokens) -> None:
        # build_stylesheet has no QToolButton rule, and shared/ is not edited
        # here. The transparent background is load-bearing: without it the
        # global `QWidget { background-color: surface }` rule paints a surface
        # patch on the card's surface_raised plane.
        self.fold_button.setStyleSheet(
            f"""
            QToolButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: {tokens.radius}px;
                padding: 4px 6px;
                color: {tokens.text_secondary};
            }}
            QToolButton:hover {{ background-color: {tokens.hover}; color: {tokens.text}; }}
            QToolButton:focus {{ border-color: {tokens.focus_ring}; }}
            """
        )
