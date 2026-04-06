"""
Dialog for manually adding products to orders.

This dialog allows users to add products to existing orders with:
- Search/autocomplete for order numbers
- Search/autocomplete for SKUs
- Real-time validation
- Stock warnings
- Live stock display
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QSpinBox, QLabel, QPushButton,
    QGroupBox, QMessageBox, QCompleter, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import logging

logger = logging.getLogger(__name__)


class AddProductDialog(QDialog):
    """
    Dialog for manually adding product to order.

    User workflow:
    1. Type order number (with autocomplete)
    2. Type SKU (with autocomplete from stock)
    3. Enter quantity
    4. Click Add
    → Product added to analysis_df
    → Fulfillment recalculated for this order only
    → Saved to session
    → NO full re-analysis!
    """

    def __init__(self, parent, analysis_df, stock_df, live_stock):
        super().__init__(parent)

        self.analysis_df = analysis_df
        self.stock_df = stock_df
        self.live_stock = live_stock  # Current stock tracking dict
        self.result = None

        self.setup_ui()
        self.setup_autocompleters()

    def setup_ui(self):
        """Setup dialog UI components."""
        self.setWindowTitle("Add Product to Order")
        self.setModal(True)
        self.resize(500, 500)

        layout = QVBoxLayout(self)

        # Section 1: Order Number Input
        layout.addWidget(self._create_order_section())

        # Section 2: Product/SKU Input
        layout.addWidget(self._create_product_section())

        # Section 3: Quantity
        layout.addWidget(self._create_quantity_section())

        # Section 4: Info/Warning
        self.warning_box = self._create_warning_box()
        self.warning_box.setVisible(False)
        layout.addWidget(self.warning_box)

        self.info_box = self._create_info_box()
        layout.addWidget(self.info_box)

        # Section 5: Buttons
        layout.addWidget(self._create_buttons())

    def _create_order_section(self):
        """Create order number input section."""
        group = QGroupBox("ORDER NUMBER")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("Enter order number:"))

        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("Type order number... (e.g., 1001)")
        self.order_input.textChanged.connect(self._on_order_changed)
        layout.addWidget(self.order_input)

        # Status label (shows if order found)
        self.order_status_label = QLabel("")
        layout.addWidget(self.order_status_label)

        return group

    def _create_product_section(self):
        """Create SKU input section."""
        group = QGroupBox("PRODUCT SKU")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("Enter product SKU:"))

        self.sku_input = QLineEdit()
        self.sku_input.setPlaceholderText("Type SKU... (e.g., SKU-HAT)")
        self.sku_input.textChanged.connect(self._on_sku_changed)
        layout.addWidget(self.sku_input)

        # Product info label (shows name + stock)
        self.product_info_label = QLabel("")
        layout.addWidget(self.product_info_label)

        return group

    def _create_quantity_section(self):
        """Create quantity input section."""
        group = QGroupBox("QUANTITY")
        layout = QVBoxLayout(group)

        layout.addWidget(QLabel("Quantity to add:"))

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(9999)
        self.quantity_spin.setValue(1)
        layout.addWidget(self.quantity_spin)

        return group

    def _create_warning_box(self):
        """Create warning box for low/zero stock."""
        label = QLabel()
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                background-color: #FFEBEE;
                border: 2px solid #F44336;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        return label

    def _create_info_box(self):
        """Create info box."""
        text = (
            "INFO\n\n"
            "• Product will be added with Source: 'Manual'\n"
            "• Fulfillment will be recalculated for this order\n"
            "• Manual addition will be saved in session\n"
            "• NO full re-analysis needed"
        )

        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("""
            QLabel {
                background-color: #E3F2FD;
                border: 2px solid #2196F3;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        return label

    def _create_buttons(self):
        """Create Cancel/Add buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        self.add_btn = QPushButton("Add Product")
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        layout.addWidget(self.add_btn)

        return widget

    def setup_autocompleters(self):
        """Setup autocomplete for order and SKU inputs."""
        # Order number autocomplete - convert to strings and strip whitespace
        order_numbers = self.analysis_df["Order_Number"].astype(str).unique().tolist()
        order_numbers = [str(o).strip() for o in order_numbers]  # Convert to strings and strip
        order_numbers = sorted(set(order_numbers))  # Remove duplicates and sort

        order_completer = QCompleter(order_numbers, self)
        order_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.order_input.setCompleter(order_completer)

        # SKU autocomplete (from stock)
        skus = self.stock_df["SKU"].unique().tolist()
        skus = [str(s).strip() for s in skus]
        skus = sorted(set(skus))  # Remove duplicates and sort

        sku_completer = QCompleter(skus, self)
        sku_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.sku_input.setCompleter(sku_completer)

    def _on_order_changed(self, text):
        """Handle order number input change."""
        if not text:
            self.order_status_label.setText("")
            return

        # Check if order exists - convert both to string for comparison
        # Order_Number might be stored as int/float in DataFrame
        text_str = str(text).strip()
        order_numbers_str = self.analysis_df["Order_Number"].astype(str)
        order_exists = text_str in order_numbers_str.values

        if order_exists:
            # Get order info - compare as strings
            order_rows = self.analysis_df[
                self.analysis_df["Order_Number"].astype(str) == text_str
            ]
            item_count = len(order_rows)
            status = order_rows.iloc[0]["Order_Fulfillment_Status"]

            self.order_status_label.setText(
                f"✓ Order found: {item_count} items, Status: {status}"
            )
            self.order_status_label.setStyleSheet("color: green;")
        else:
            self.order_status_label.setText("✗ Order not found")
            self.order_status_label.setStyleSheet("color: red;")

    def _on_sku_changed(self, text):
        """Handle SKU input change."""
        if not text:
            self.product_info_label.setText("")
            self.warning_box.setVisible(False)
            return

        # Check if SKU exists in stock - compare as strings
        text_str = str(text).strip()
        stock_row = self.stock_df[self.stock_df["SKU"].astype(str).str.strip() == text_str]

        if stock_row.empty:
            self.product_info_label.setText("✗ SKU not found in stock")
            self.product_info_label.setStyleSheet("color: red;")
            return

        # Get product info
        product_name = stock_row.iloc[0].get("Product_Name", "")
        # Live stock keys might be strings, ensure we lookup with string
        current_stock = self.live_stock.get(text_str, self.live_stock.get(text, 0))

        self.product_info_label.setText(
            f"✓ {product_name} | Live stock: {current_stock}"
        )
        self.product_info_label.setStyleSheet("color: green;")

        # Show warning if low/zero stock
        if current_stock == 0:
            warning_text = (
                "WARNING\n\n"
                f"Product {text} has 0 stock available!\n"
                "Adding this product will affect order fulfillment."
            )
            self.warning_box.setText(warning_text)
            self.warning_box.setVisible(True)
            self.warning_box.setStyleSheet("""
                QLabel {
                    background-color: #FFEBEE;
                    border: 2px solid #F44336;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
        elif current_stock < 5:
            warning_text = (
                "WARNING\n\n"
                f"Product {text} has low stock ({current_stock} units)."
            )
            self.warning_box.setText(warning_text)
            self.warning_box.setVisible(True)
            self.warning_box.setStyleSheet("""
                QLabel {
                    background-color: #FFF8E1;
                    border: 2px solid #FFC107;
                    border-radius: 5px;
                    padding: 10px;
                }
            """)
        else:
            self.warning_box.setVisible(False)

    def _on_add_clicked(self):
        """Handle Add Product button click."""
        # Validate inputs
        if not self._validate():
            return

        # Get values
        order_number = self.order_input.text().strip()
        sku = self.sku_input.text().strip()
        quantity = self.quantity_spin.value()

        # Get product name from stock - compare as strings
        stock_row = self.stock_df[self.stock_df["SKU"].astype(str).str.strip() == sku]
        product_name = stock_row.iloc[0].get("Product_Name", sku) if not stock_row.empty else sku

        # Store result
        self.result = {
            "order_number": order_number,
            "sku": sku,
            "product_name": product_name,
            "quantity": quantity
        }

        logger.info(f"Adding product: {self.result}")

        # Close dialog with accepted
        self.accept()

    def _validate(self):
        """Validate user inputs."""
        order_number = self.order_input.text().strip()
        sku = self.sku_input.text().strip()

        # Check order number entered
        if not order_number:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter an order number."
            )
            self.order_input.setFocus()
            return False

        # Check order exists - convert to string for comparison
        order_numbers_str = self.analysis_df["Order_Number"].astype(str)
        if order_number not in order_numbers_str.values:
            QMessageBox.warning(
                self,
                "Validation Error",
                f"Order '{order_number}' not found in analysis."
            )
            self.order_input.setFocus()
            return False

        # Check SKU entered
        if not sku:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter a product SKU."
            )
            self.sku_input.setFocus()
            return False

        # Check SKU exists in stock - convert to string for comparison
        stock_skus_str = self.stock_df["SKU"].astype(str).str.strip()
        if sku not in stock_skus_str.values:
            reply = QMessageBox.question(
                self,
                "SKU Not Found",
                f"SKU '{sku}' not found in stock file.\n\n"
                "Do you want to add it anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.sku_input.setFocus()
                return False

        # Check quantity
        if self.quantity_spin.value() < 1:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Quantity must be at least 1."
            )
            self.quantity_spin.setFocus()
            return False

        return True

    def get_result(self):
        """Get dialog result after accept."""
        return self.result
