"""
Tools Widget - Main container for utility tools.

Contains sub-tabs:
- Reference Labels: PDF processing for reference numbers
- Barcode Generator: Generate warehouse barcode labels
- SKU Labels: Barcode-scan-to-print labeling workflow
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel
)
from PySide6.QtCore import Qt

from gui.reference_labels_widget import ReferenceLabelsWidget
from gui.barcode_generator_widget import BarcodeGeneratorWidget
from gui.sku_label_widget import SKULabelWidget


class ToolsWidget(QWidget):
    """Main Tools tab widget with sub-tabs for various utilities."""

    def __init__(self, main_window, parent=None):
        """
        Initialize Tools widget.

        Args:
            main_window: MainWindow instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.mw = main_window
        self._init_ui()

    def _init_ui(self):
        """Initialize UI with sub-tabs."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(0)

        # Create sub-tab widget
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setTabPosition(QTabWidget.North)

        # Sub-tab 1: Reference Labels
        self.reference_labels_widget = ReferenceLabelsWidget(self.mw)
        self.sub_tabs.addTab(
            self.reference_labels_widget,
            "📄 Reference Labels"
        )

        # Sub-tab 2: Barcode Generator
        self.barcode_generator_widget = BarcodeGeneratorWidget(self.mw)
        self.sub_tabs.addTab(
            self.barcode_generator_widget,
            "🏷️ Barcode Generator"
        )

        # Sub-tab 3: SKU Labels
        self.sku_label_widget = SKULabelWidget(self.mw)
        self.sub_tabs.addTab(
            self.sku_label_widget,
            "🖨️ SKU Labels"
        )

        layout.addWidget(self.sub_tabs)
