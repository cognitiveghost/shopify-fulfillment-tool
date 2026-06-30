"""Bulk operations toolbar for Analysis Results.

This module provides the BulkOperationsToolbar widget that contains buttons
for performing mass operations on selected rows in the Analysis Results table.
"""

from PySide6.QtWidgets import (
    QWidget, QLayout, QLabel, QPushButton,
    QToolButton, QMenu, QFrame
)
from PySide6.QtCore import Signal, Qt, QRect, QSize, QPoint

from gui.theme_manager import get_theme_manager


class FlowLayout(QLayout):
    """A layout that lays widgets out left-to-right and wraps to the next row
    when it runs out of horizontal space.

    Qt has no built-in flow layout; this is the canonical minimal
    implementation (adapted from the official Qt example). It is what keeps the
    bulk toolbar's ~10 buttons reachable on a narrow window instead of being
    clipped off the right edge.
    """

    def __init__(self, parent=None, margin=5, spacing=8):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_height = 0
        spacing = self.spacing()
        right = rect.right() - m.right()

        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            if x > rect.x() + m.left() and x + w > right:
                x = rect.x() + m.left()
                y = y + line_height + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = x + w + spacing
            line_height = max(line_height, h)

        return y + line_height + m.bottom() - rect.y()


class BulkOperationsToolbar(QWidget):
    """Toolbar for bulk operations on selected rows.

    This widget provides buttons for:
    - Selection controls (Select All, Clear)
    - Status changes (Set Fulfillable, Set Not Fulfillable)
    - Tag operations (Add Tag, Remove Tag)
    - Delete operations (Remove SKU, Remove Orders with SKU, Delete Orders)
    - Export operations (XLSX, CSV)

    Signals:
        select_all_clicked: Emitted when Select All button is clicked
        clear_selection_clicked: Emitted when Clear button is clicked
        change_status_clicked(bool): Emitted when status change is requested
            True = Fulfillable, False = Not Fulfillable
        add_tag_clicked: Emitted when Add Tag is clicked
        remove_tag_clicked: Emitted when Remove Tag is clicked
        remove_sku_from_orders_clicked: Emitted when Remove SKU from Orders is clicked
        remove_orders_with_sku_clicked: Emitted when Remove Orders with SKU is clicked
        delete_orders_clicked: Emitted when Delete Selected Orders is clicked
        export_selection_clicked(str): Emitted when export is requested
            Format: 'xlsx' or 'csv'
    """

    # Signals
    select_all_clicked = Signal()
    clear_selection_clicked = Signal()
    change_status_clicked = Signal(bool)  # True = Fulfillable, False = Not Fulfillable
    add_tag_clicked = Signal()
    remove_tag_clicked = Signal()
    remove_sku_from_orders_clicked = Signal()
    remove_orders_with_sku_clicked = Signal()
    delete_orders_clicked = Signal()
    export_selection_clicked = Signal(str)  # Format: 'xlsx' or 'csv'

    def __init__(self, parent=None):
        """Initialize the bulk operations toolbar.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self._setup_ui()
        self._apply_theme()
        get_theme_manager().theme_changed.connect(self._apply_theme)

    def _separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def _setup_ui(self):
        """Initialize UI components."""
        layout = FlowLayout(self, margin=5, spacing=8)

        # Section 1: Selection controls
        self.selection_label = QLabel("Selected: 0 orders (0 items)")
        layout.addWidget(self.selection_label)

        select_all_btn = QPushButton("Select All")
        select_all_btn.setToolTip("Select all visible rows (respects current filter)")
        select_all_btn.clicked.connect(self.select_all_clicked.emit)
        layout.addWidget(select_all_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setToolTip("Clear all selections")
        clear_btn.clicked.connect(self.clear_selection_clicked.emit)
        layout.addWidget(clear_btn)

        layout.addWidget(self._separator())

        # Section 2: Status operations
        layout.addWidget(QLabel("Status:"))

        self.fulfillable_btn = QPushButton("Set Fulfillable")
        self.fulfillable_btn.setToolTip("Mark selected orders as Fulfillable")
        self.fulfillable_btn.clicked.connect(lambda: self.change_status_clicked.emit(True))
        layout.addWidget(self.fulfillable_btn)

        self.not_fulfillable_btn = QPushButton("Set Not Fulfillable")
        self.not_fulfillable_btn.setToolTip("Mark selected orders as Not Fulfillable")
        self.not_fulfillable_btn.clicked.connect(lambda: self.change_status_clicked.emit(False))
        layout.addWidget(self.not_fulfillable_btn)

        layout.addWidget(self._separator())

        # Section 3: Tag operations
        layout.addWidget(QLabel("Tags:"))

        self.add_tag_btn = QPushButton("Add Tag")
        self.add_tag_btn.setToolTip("Add Internal Tag to selected orders")
        self.add_tag_btn.clicked.connect(self.add_tag_clicked.emit)
        layout.addWidget(self.add_tag_btn)

        self.remove_tag_btn = QPushButton("Remove Tag")
        self.remove_tag_btn.setToolTip("Remove Internal Tag from selected orders")
        self.remove_tag_btn.clicked.connect(self.remove_tag_clicked.emit)
        layout.addWidget(self.remove_tag_btn)

        layout.addWidget(self._separator())

        # Section 4: Delete operations (dropdown menu) - destructive, styled red
        self.delete_menu_btn = QToolButton()
        self.delete_menu_btn.setText("Delete Operations")
        self.delete_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.delete_menu_btn.setToolTip("Delete or remove items from selected orders")

        delete_menu = QMenu(self.delete_menu_btn)
        remove_sku_action = delete_menu.addAction("Remove SKU from Orders")
        remove_sku_action.setToolTip("Remove specific SKU from selected orders (keeps other items)")
        remove_sku_action.triggered.connect(self.remove_sku_from_orders_clicked.emit)

        remove_orders_action = delete_menu.addAction("Remove Orders with SKU")
        remove_orders_action.setToolTip("Remove entire orders that contain a specific SKU")
        remove_orders_action.triggered.connect(self.remove_orders_with_sku_clicked.emit)

        delete_menu.addSeparator()

        delete_orders_action = delete_menu.addAction("Delete Selected Orders")
        delete_orders_action.setToolTip("Permanently delete all selected orders")
        delete_orders_action.triggered.connect(self.delete_orders_clicked.emit)

        self.delete_menu_btn.setMenu(delete_menu)
        layout.addWidget(self.delete_menu_btn)

        layout.addWidget(self._separator())

        # Section 5: Export
        layout.addWidget(QLabel("Export:"))

        self.export_xlsx_btn = QPushButton("XLSX")
        self.export_xlsx_btn.setToolTip("Export selected orders to Excel file")
        self.export_xlsx_btn.clicked.connect(lambda: self.export_selection_clicked.emit('xlsx'))
        layout.addWidget(self.export_xlsx_btn)

        self.export_csv_btn = QPushButton("CSV")
        self.export_csv_btn.setToolTip("Export selected orders to CSV file")
        self.export_csv_btn.clicked.connect(lambda: self.export_selection_clicked.emit('csv'))
        layout.addWidget(self.export_csv_btn)

        # Store references to operation buttons for enabling/disabling
        self._operation_buttons = [
            self.fulfillable_btn,
            self.not_fulfillable_btn,
            self.add_tag_btn,
            self.remove_tag_btn,
            self.delete_menu_btn,
            self.export_xlsx_btn,
            self.export_csv_btn,
        ]

    def _apply_theme(self):
        """Apply current theme colors. Re-runs on theme change."""
        theme = get_theme_manager().get_current_theme()
        self.selection_label.setStyleSheet(
            f"font-weight: bold; color: {theme.accent_blue};"
        )
        # Destructive operations get a red accent so they're not mistaken for
        # the safe export/status buttons sitting next to them.
        self.delete_menu_btn.setStyleSheet(
            f"QToolButton {{ color: {theme.accent_red}; font-weight: bold; }}"
        )

    def update_selection_count(self, orders_count: int, items_count: int):
        """Update selection counter label.

        Args:
            orders_count: Number of unique orders selected
            items_count: Total number of items (rows) selected
        """
        self.selection_label.setText(f"Selected: {orders_count} orders ({items_count} items)")

    def set_enabled(self, enabled: bool):
        """Enable/disable all operation buttons.

        Select All and Clear buttons remain always enabled.
        Other buttons are enabled only when selection exists.

        Args:
            enabled: True to enable operation buttons, False to disable
        """
        for button in self._operation_buttons:
            button.setEnabled(enabled)

    def set_toolbar_visible(self, visible: bool):
        """Show or hide the toolbar.

        Args:
            visible: True to show, False to hide
        """
        self.setVisible(visible)
