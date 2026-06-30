"""Tag Management Panel for managing Internal_Tags on selected orders."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QListWidget
)
from PySide6.QtCore import Signal

from shopify_tool.tag_manager import parse_tags

from gui.theme_manager import get_theme_manager

class TagManagementPanel(QWidget):
    """
    Sidebar panel for managing Internal_Tags on selected orders.

    Features:
    - Shows current tags on selected order(s)
    - Add tag (predefined or custom)
    - Remove tag
    - Predefined tags from config
    - Bulk operations
    """

    tag_added = Signal(str, str)  # order_number, tag
    tag_removed = Signal(str, str)  # order_number, tag

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_order = None
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel("<b>Internal Tags Manager</b>")
        layout.addWidget(header)

        # Selected order display
        self.order_label = QLabel("No order selected")
        theme = get_theme_manager().get_current_theme()
        self.order_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        layout.addWidget(self.order_label)

        layout.addSpacing(10)

        # Current tags display
        tags_group = QGroupBox("Current Tags")
        tags_layout = QVBoxLayout()

        self.tags_list_widget = QListWidget()
        self.tags_list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.tags_list_widget.setMaximumHeight(150)
        tags_layout.addWidget(self.tags_list_widget)

        remove_btn = QPushButton("Remove Selected Tag")
        remove_btn.clicked.connect(self.remove_selected_tag)
        tags_layout.addWidget(remove_btn)

        tags_group.setLayout(tags_layout)
        layout.addWidget(tags_group)

        # Add tag section
        add_group = QGroupBox("Add Tag")
        add_layout = QVBoxLayout()

        # Predefined tags combo
        self.predefined_combo = QComboBox()
        self.predefined_combo.addItem("-- Select Predefined Tag --")
        add_layout.addWidget(QLabel("Predefined Tags:"))
        add_layout.addWidget(self.predefined_combo)

        add_predefined_btn = QPushButton("Add Predefined")
        add_predefined_btn.clicked.connect(self.add_predefined_tag)
        add_layout.addWidget(add_predefined_btn)

        # Custom tag input
        add_layout.addSpacing(10)
        add_layout.addWidget(QLabel("Or Custom Tag:"))
        self.custom_tag_input = QLineEdit()
        self.custom_tag_input.setPlaceholderText("Enter custom tag...")
        self.custom_tag_input.returnPressed.connect(self.add_custom_tag)
        add_layout.addWidget(self.custom_tag_input)

        add_custom_btn = QPushButton("Add Custom")
        add_custom_btn.clicked.connect(self.add_custom_tag)
        add_layout.addWidget(add_custom_btn)

        add_group.setLayout(add_layout)
        layout.addWidget(add_group)

        layout.addStretch()

    def set_selected_order(self, order_number, current_tags_json):
        """Update panel for selected order.

        Args:
            order_number: Order number (or None if no selection)
            current_tags_json: Current Internal_Tags value (JSON string)
        """
        self.selected_order = order_number

        if order_number:
            self.order_label.setText(f"Order: {order_number}")
            self.order_label.setStyleSheet("color: #000; font-weight: bold;")
        else:
            self.order_label.setText("No order selected")
            theme = get_theme_manager().get_current_theme()
            self.order_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")

        # Parse and display current tags
        tags = parse_tags(current_tags_json)
        self.tags_list_widget.clear()
        for tag in tags:
            self.tags_list_widget.addItem(tag)

    def load_predefined_tags(self, tag_categories):
        """Load predefined tags from config.

        Args:
            tag_categories: Dict of tag category configs (v1 or v2 format)
        """
        from shopify_tool.tag_manager import _normalize_tag_categories

        self.predefined_combo.clear()
        self.predefined_combo.addItem("-- Select Predefined Tag --")

        # Normalize to handle both v1 and v2 formats
        categories = _normalize_tag_categories(tag_categories)

        for category, config in categories.items():
            label = config.get("label", category)
            for tag in config.get("tags", []):
                # Display as "Category: Tag", store just tag as data
                self.predefined_combo.addItem(f"{label}: {tag}", tag)

    def add_predefined_tag(self):
        """Add selected predefined tag to order."""
        if self.predefined_combo.currentIndex() == 0:
            # No tag selected (placeholder)
            return

        tag = self.predefined_combo.currentData()
        if tag and self.selected_order:
            self.tag_added.emit(self.selected_order, tag)
            # Reset combo to placeholder
            self.predefined_combo.setCurrentIndex(0)

    def add_custom_tag(self):
        """Add custom tag from input field to order."""
        tag = self.custom_tag_input.text().strip()
        if tag and self.selected_order:
            self.tag_added.emit(self.selected_order, tag)
            self.custom_tag_input.clear()

    def remove_selected_tag(self):
        """Remove selected tag from list."""
        current_item = self.tags_list_widget.currentItem()
        if current_item and self.selected_order:
            tag = current_item.text()
            self.tag_removed.emit(self.selected_order, tag)
