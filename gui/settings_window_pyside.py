import sys
import os
import json
import pandas as pd
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QCheckBox,
)
from PySide6.QtCore import Qt, QTimer, QDate

from shopify_tool.core import get_unique_column_values
from gui.column_mapping_widget import ColumnMappingWidget
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from shopify_tool.set_decoder import import_sets_from_csv, export_sets_to_csv


class SettingsWindow(QDialog):
    """A dialog window for viewing and editing all application settings.

    This window provides a tabbed interface for modifying different sections
    of the application's configuration, including:
    - General settings and paths.
    - The rule engine's rule definitions.
    - Pre-configured packing list reports.
    - Pre-configured stock export reports.

    The UI is built dynamically based on the current configuration data that
    is passed in during initialization. It allows for adding, editing, and
    deleting rules, reports, and their constituent parts.

    Attributes:
        config_data (dict): A deep copy of the application's configuration.
        analysis_df (pd.DataFrame): The main analysis DataFrame, used to
            populate dynamic dropdowns for filter values.
        rule_widgets (list): A list of dictionaries, each holding references
            to the UI widgets for a single rule.
        packing_list_widgets (list): References to packing list UI widgets.
        stock_export_widgets (list): References to stock export UI widgets.
    """

    # Constants for builders
    FILTERABLE_COLUMNS = [
        "Order_Number",
        "Order_Type",
        "SKU",
        "Product_Name",
        "Stock_Alert",
        "Order_Fulfillment_Status",
        "Shipping_Provider",
        "Destination_Country",
        "Tags",
        "System_note",
        "Status_Note",
        "Total Price",
    ]
    FILTER_OPERATORS = ["==", "!=", "in", "not in", "contains"]
    # Group order-level fields first for better UX
    ORDER_LEVEL_FIELDS = [
        "--- ORDER-LEVEL FIELDS ---",
        "item_count",
        "total_quantity",
        "has_sku",
        "Has_SKU",
        "--- ARTICLE-LEVEL FIELDS ---",
    ]
    CONDITION_FIELDS = ORDER_LEVEL_FIELDS + FILTERABLE_COLUMNS
    CONDITION_OPERATORS = [
        "equals",
        "does not equal",
        "contains",
        "does not contain",
        "is greater than",
        "is less than",
        "is greater than or equal",
        "is less than or equal",
        "starts with",
        "ends with",
        "is empty",
        "is not empty",
        "in list",
        "not in list",
        "between",
        "not between",
        "date before",
        "date after",
        "date equals",
        "matches regex",
        "does not match regex",
    ]
    ACTION_TYPES = [
        "ADD_TAG",
        "ADD_ORDER_TAG",
        "ADD_INTERNAL_TAG",
        "SET_STATUS",
        "COPY_FIELD",
        "CALCULATE",
        "SET_MULTI_TAGS",
        "ALERT_NOTIFICATION",
        "ADD_PRODUCT",
    ]

    def __init__(self, client_id, client_config, profile_manager, analysis_df=None, parent=None):
        """Initializes the SettingsWindow.

        Args:
            client_id (str): The client ID for which settings are being edited.
            client_config (dict): The client's configuration dictionary. A deep
                copy is made to avoid modifying the original until saved.
            profile_manager: The ProfileManager instance for saving settings.
            analysis_df (pd.DataFrame, optional): The current analysis
                DataFrame, used for populating filter value dropdowns.
                Defaults to None.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.client_id = client_id
        self.config_data = json.loads(json.dumps(client_config))
        self.profile_manager = profile_manager
        self.analysis_df = analysis_df if analysis_df is not None else pd.DataFrame()

        # Ensure config structure exists
        if not isinstance(self.config_data.get("column_mappings"), dict):
            self.config_data["column_mappings"] = {
                "orders_required": [],
                "stock_required": []
            }

        if "courier_mappings" not in self.config_data:
            self.config_data["courier_mappings"] = {}

        if "settings" not in self.config_data:
            self.config_data["settings"] = {
                "low_stock_threshold": 5,
                "stock_csv_delimiter": ";"
            }

        if "rules" not in self.config_data:
            self.config_data["rules"] = []

        if "packing_list_configs" not in self.config_data:
            self.config_data["packing_list_configs"] = []

        if "stock_export_configs" not in self.config_data:
            self.config_data["stock_export_configs"] = []

        if "sku_label_config" not in self.config_data:
            self.config_data["sku_label_config"] = {
                "sku_to_label": {},
                "default_printer": ""
            }

        # Widget lists
        self.rule_widgets = []
        self.packing_list_widgets = []
        self.stock_export_widgets = []
        self.courier_mapping_widgets = []

        self.setWindowTitle(f"Settings - CLIENT_{self.client_id}")
        self.setMinimumSize(1100, 600)
        self.setModal(True)

        screen_geo = QApplication.primaryScreen().availableGeometry()
        self.resize(
            min(1250, screen_geo.width() - 40),
            min(920, screen_geo.height() - 60),
        )

        main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create all tabs
        self.create_general_tab()
        self.create_rules_tab()
        self.create_packing_lists_tab()
        self.create_stock_exports_tab()
        self.create_mappings_tab()
        self.create_sets_tab()  # Sets/Bundles tab
        self.create_weight_tab()  # Volumetric Weight tab
        self.create_tag_categories_tab()  # Tag Categories tab
        self.create_column_config_tab()  # Column Configuration tab
        self.create_sku_labels_tab()     # SKU Label Printing tab

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    # Generic helper to delete a widget and its reference from a list
    def _delete_widget_from_list(self, widget_refs, ref_list):
        """Generic helper to delete a group box widget and its reference from a list."""
        widget_refs["group_box"].deleteLater()
        ref_list.remove(widget_refs)
        self._update_rules_count_label()

    # Generic helper to delete a row widget and its reference from a list
    def _delete_row_from_list(self, row_widget, ref_list, ref_dict):
        """Generic helper to delete a row widget and its reference from a list."""
        row_widget.deleteLater()
        ref_list.remove(ref_dict)

    def _move_rule_up(self, widget_refs):
        """Moves a rule up in the list (higher priority)."""
        idx = self.rule_widgets.index(widget_refs)
        if idx == 0:
            return  # Already at top

        # Swap in list
        self.rule_widgets[idx], self.rule_widgets[idx - 1] = \
            self.rule_widgets[idx - 1], self.rule_widgets[idx]

        # Swap in UI layout
        layout = self.rules_layout
        widget = widget_refs["group_box"]
        prev_widget = self.rule_widgets[idx]["group_box"]

        layout.removeWidget(widget)
        layout.removeWidget(prev_widget)
        layout.insertWidget(idx - 1, widget)
        layout.insertWidget(idx, prev_widget)

        # Update priority labels
        self._update_priority_labels()

    def _move_rule_down(self, widget_refs):
        """Moves a rule down in the list (lower priority)."""
        idx = self.rule_widgets.index(widget_refs)
        if idx >= len(self.rule_widgets) - 1:
            return  # Already at bottom

        # Swap in list
        self.rule_widgets[idx], self.rule_widgets[idx + 1] = \
            self.rule_widgets[idx + 1], self.rule_widgets[idx]

        # Swap in UI layout
        layout = self.rules_layout
        widget = widget_refs["group_box"]
        next_widget = self.rule_widgets[idx]["group_box"]

        layout.removeWidget(widget)
        layout.removeWidget(next_widget)
        layout.insertWidget(idx, next_widget)
        layout.insertWidget(idx + 1, widget)

        # Update priority labels
        self._update_priority_labels()

    def _update_priority_labels(self):
        """Updates priority labels and button states for all rules.

        Groups rules by level (article/order) and shows per-level priority.
        """
        # Group by level
        article_count = 1
        order_count = 1

        for idx, rule_w in enumerate(self.rule_widgets):
            level = rule_w["level_combo"].currentText()

            # Update label with level-specific numbering
            if level == "article":
                rule_w["priority_label"].setText(f"Article #{article_count}")
                article_count += 1
            else:  # order
                rule_w["priority_label"].setText(f"Order #{order_count}")
                order_count += 1

            # Disable up button for first rule
            rule_w["up_btn"].setEnabled(idx > 0)

            # Disable down button for last rule
            rule_w["down_btn"].setEnabled(idx < len(self.rule_widgets) - 1)

    def get_available_rule_fields(self):
        """Get all available fields for rules from DataFrame + common fields.

        Returns a list of field names including:
        - Order-level fields (shown first)
        - Common article-level fields
        - All other DataFrame columns (dynamically discovered)
        - Separators (disabled items starting with "---")
        """
        import logging
        logger = logging.getLogger(__name__)

        # Start with order-level fields (these are ALWAYS available)
        order_level_fields = [
            "--- ORDER-LEVEL FIELDS ---",
            "item_count",
            "total_quantity",
            "unique_sku_count",
            "max_quantity",
            "has_sku",
            "has_product",
            "order_volumetric_weight",
            "all_no_packaging",
            "order_min_box",
        ]

        # Common article-level fields
        common_fields = [
            "--- COMMON ARTICLE FIELDS ---",
            "Order_Number",
            "Order_Type",
            "SKU",
            "Product_Name",
            "Quantity",
            "Stock",
            "Final_Stock",
            "Shipping_Provider",
            "Shipping_Method",
            "Destination_Country",
        ]

        # Get ALL columns from DataFrame
        if self.analysis_df is not None and not self.analysis_df.empty:
            all_columns = sorted(self.analysis_df.columns.tolist())
            logger.info(f"[RULE ENGINE] DataFrame has {len(all_columns)} columns")
            logger.info(f"[RULE ENGINE] ALL COLUMNS: {all_columns}")

            # Check if specific columns exist
            logger.info(f"[RULE ENGINE] 'Stock' in columns: {'Stock' in all_columns}")
            logger.info(f"[RULE ENGINE] 'Total_Price' in columns: {'Total_Price' in all_columns}")

            # Filter out internal columns (starting with _) and already listed common fields
            # But keep separators for checking
            common_field_names = [f for f in common_fields if not f.startswith("---")]

            custom_columns = [
                col for col in all_columns
                if not col.startswith('_')
                and col not in common_field_names  # Avoid duplicates
            ]

            logger.info(f"[RULE ENGINE] Found {len(custom_columns)} custom columns: {custom_columns}")

            # Combine: order-level fields first, then common fields, then separator, then custom
            if custom_columns:
                return order_level_fields + common_fields + [
                    "--- OTHER AVAILABLE FIELDS ---"
                ] + custom_columns
            else:
                return order_level_fields + common_fields
        else:
            logger.warning(f"[RULE ENGINE] No analysis_df available (is None: {self.analysis_df is None})")

        return order_level_fields + common_fields  # Fallback to order-level + common only

    def create_general_tab(self):
        """Creates the 'General Settings' tab."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)

        # Settings GroupBox
        settings_box = QGroupBox("General Settings")
        settings_layout = QFormLayout(settings_box)

        # Stock CSV delimiter with improved tooltip
        delimiter_label = QLabel("Stock CSV Delimiter:")
        self.stock_delimiter_edit = QLineEdit(
            self.config_data.get("settings", {}).get("stock_csv_delimiter", ";")
        )
        self.stock_delimiter_edit.setMaximumWidth(100)

        # Add informative tooltip
        self.stock_delimiter_edit.setToolTip(
            "Character used to separate columns in stock CSV file.\n\n"
            "Common values:\n"
            "  • Semicolon (;) - for exports from local warehouse\n"
            "  • Comma (,) - for Shopify exports\n\n"
            "Make sure this matches your stock CSV file format."
        )

        settings_layout.addRow(delimiter_label, self.stock_delimiter_edit)

        # Orders CSV Delimiter
        orders_delimiter_label = QLabel("Orders CSV Delimiter:")
        self.orders_delimiter_edit = QLineEdit(
            self.config_data.get("settings", {}).get("orders_csv_delimiter", ",")
        )
        self.orders_delimiter_edit.setMaximumWidth(100)
        self.orders_delimiter_edit.setPlaceholderText(",")

        # Add informative tooltip
        self.orders_delimiter_edit.setToolTip(
            "Character used to separate columns in orders CSV file.\n\n"
            "Common values:\n"
            "  • Comma (,) - standard Shopify exports\n"
            "  • Semicolon (;) - European Excel exports\n"
            "  • Tab (\\t) - tab-separated files\n\n"
            "The tool will auto-detect delimiter when you select a file,\n"
            "but you can override it here if needed."
        )

        settings_layout.addRow(orders_delimiter_label, self.orders_delimiter_edit)

        # Low stock threshold with improved tooltip
        threshold_label = QLabel("Low Stock Threshold:")
        self.low_stock_edit = QLineEdit(
            str(self.config_data.get("settings", {}).get("low_stock_threshold", 5))
        )
        self.low_stock_edit.setMaximumWidth(100)

        # Add informative tooltip
        self.low_stock_edit.setToolTip(
            "Trigger stock alerts when quantity falls below this number.\n\n"
            "Items with stock below this threshold will be marked in analysis."
        )

        settings_layout.addRow(threshold_label, self.low_stock_edit)

        # Repeat Detection Window
        repeat_days_label = QLabel("Repeat Detection Window (days):")
        self.repeat_days_input = QSpinBox()
        self.repeat_days_input.setMinimum(1)
        self.repeat_days_input.setMaximum(365)
        self.repeat_days_input.setValue(
            self.config_data.get("settings", {}).get("repeat_detection_days", 1)
        )
        self.repeat_days_input.setToolTip(
            "Orders fulfilled within this many days are marked as 'Repeat'.\n"
            "Default: 1 day (only yesterday's fulfillments)\n"
            "Increase for longer detection window (e.g., 7 days, 30 days)"
        )

        settings_layout.addRow(repeat_days_label, self.repeat_days_input)

        main_layout.addWidget(settings_box)

        # Info about removed fields
        info_box = QGroupBox("Note")
        info_layout = QVBoxLayout(info_box)
        info_label = QLabel(
            "Templates and custom output directories are no longer used.\n"
            "All reports are now generated in session-specific folders automatically."
        )
        info_label.setWordWrap(True)
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic;")
        info_layout.addWidget(info_label)
        main_layout.addWidget(info_box)

        main_layout.addStretch()

        self.tab_widget.addTab(tab, "General")

    def create_rules_tab(self):
        """Creates the 'Rules' tab for dynamically managing automation rules."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)

        # Header row with Add button and rule count label
        header_row = QHBoxLayout()
        add_rule_btn = QPushButton("Add New Rule")
        add_rule_btn.clicked.connect(lambda: [self.add_rule_widget(), self._update_priority_labels(), self._update_rules_count_label()])
        header_row.addWidget(add_rule_btn)
        header_row.addStretch()
        self.rules_count_label = QLabel("")
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        self.rules_count_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt;")
        header_row.addWidget(self.rules_count_label)
        main_layout.addLayout(header_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.rules_layout = QVBoxLayout(scroll_content)
        self.rules_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        self.tab_widget.addTab(tab, "Rules")
        for rule_config in self.config_data.get("rules", []):
            self.add_rule_widget(rule_config)
        self._update_priority_labels()
        self._update_rules_count_label()

    def _update_rules_count_label(self):
        """Update the rules summary label in the Rules tab header."""
        if not hasattr(self, 'rules_count_label'):
            return
        rules = self.config_data.get("rules", [])
        article_count = sum(1 for r in rules if r.get("level", "article") == "article")
        order_count = sum(1 for r in rules if r.get("level") == "order")
        # Count from live widgets instead if available
        if hasattr(self, 'rule_widgets'):
            article_count = 0
            order_count = 0
            for rw in self.rule_widgets:
                level = rw.get("level_combo")
                if level:
                    if level.currentText() == "order":
                        order_count += 1
                    else:
                        article_count += 1
        parts = []
        if article_count:
            parts.append(f"{article_count} article rule{'s' if article_count != 1 else ''}")
        if order_count:
            parts.append(f"{order_count} order rule{'s' if order_count != 1 else ''}")
        self.rules_count_label.setText(", ".join(parts) if parts else "No rules defined")

    def add_rule_widget(self, config=None):
        """Adds a new group of widgets for creating/editing a single rule.

        Args:
            config (dict, optional): The configuration for a pre-existing
                rule to load into the widgets. If None, creates a new,
                blank rule.
        """
        if not isinstance(config, dict):
            config = {"name": "New Rule", "level": "article", "match": "ALL", "conditions": [], "actions": []}
        rule_box = QGroupBox()
        rule_layout = QVBoxLayout(rule_box)
        header_layout = QHBoxLayout()

        # Priority label (e.g., "Article #1", "Order #2")
        priority_label = QLabel("")
        priority_label.setMinimumWidth(70)
        priority_label.setStyleSheet("font-weight: bold; color: #2196F3; font-size: 11pt;")
        header_layout.addWidget(priority_label)

        # Up button
        up_btn = QPushButton("↑")
        up_btn.setMaximumWidth(30)
        up_btn.setToolTip("Move rule up (higher priority)")
        header_layout.addWidget(up_btn)

        # Down button
        down_btn = QPushButton("↓")
        down_btn.setMaximumWidth(30)
        down_btn.setToolTip("Move rule down (lower priority)")
        header_layout.addWidget(down_btn)

        # Test button
        test_btn = QPushButton("🧪 Test")
        test_btn.setMaximumWidth(70)
        test_btn.setToolTip("Test this rule against current analysis data")
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_green};
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #45a049;
            }}
            QPushButton:disabled {{
                background-color: {theme.border_subtle};
                color: {theme.text_secondary};
            }}
        """)
        header_layout.addWidget(test_btn)

        header_layout.addWidget(QLabel("Rule Name:"))
        name_edit = QLineEdit(config.get("name", ""))
        header_layout.addWidget(name_edit)
        delete_rule_btn = QPushButton("Delete Rule")
        delete_rule_btn.setStyleSheet("background-color: #f44336; color: white;")
        header_layout.addWidget(delete_rule_btn)
        rule_layout.addLayout(header_layout)

        # Add level selector
        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("Rule Level:"))

        level_combo = WheelIgnoreComboBox()
        level_combo.addItems(["article", "order"])
        level_combo.setCurrentText(config.get("level", "article"))
        level_combo.setToolTip(
            "article: Apply to each item (row) individually\n"
            "  → Use article-level fields (SKU, Product_Name, etc.)\n"
            "  → All actions apply to matching rows\n\n"
            "order: Evaluate entire order based on aggregate data\n"
            "  → Use order-level fields:\n"
            "     • item_count - number of rows in order\n"
            "     • total_quantity - sum of all quantities\n"
            "     • unique_sku_count - count of unique SKUs\n"
            "     • max_quantity - max quantity of single item\n"
            "     • has_sku - check if order contains specific SKU\n"
            "     • has_product - check by Product_Name\n"
            "  → Actions behavior:\n"
            "     • ADD_TAG - applies to ALL rows (for filtering)\n"
            "     • ADD_ORDER_TAG - applies to first row only (for counting)\n"
            "     • ADD_INTERNAL_TAG - applies to ALL rows (structured tags)"
        )
        level_layout.addWidget(level_combo)
        level_layout.addStretch()

        rule_layout.addLayout(level_layout)

        # Steps container
        steps_container = QVBoxLayout()
        rule_layout.addLayout(steps_container)

        # "Add Step" button
        add_step_btn = QPushButton("+ Add Step")
        add_step_btn.setToolTip("Add a new step to this rule (narrowing: each step filters rows from previous step)")
        add_step_btn.setStyleSheet("color: #2196F3; font-weight: bold;")
        rule_layout.addWidget(add_step_btn, 0, Qt.AlignLeft)

        self.rules_layout.addWidget(rule_box)
        widget_refs = {
            "group_box": rule_box,
            "priority_label": priority_label,
            "up_btn": up_btn,
            "down_btn": down_btn,
            "test_btn": test_btn,
            "name_edit": name_edit,
            "level_combo": level_combo,
            "steps_container": steps_container,
            "steps": [],
        }
        self.rule_widgets.append(widget_refs)
        delete_rule_btn.clicked.connect(lambda: self._delete_widget_from_list(widget_refs, self.rule_widgets))
        up_btn.clicked.connect(lambda: self._move_rule_up(widget_refs))
        down_btn.clicked.connect(lambda: self._move_rule_down(widget_refs))
        test_btn.clicked.connect(lambda: self._test_rule(widget_refs))
        add_step_btn.clicked.connect(lambda: self._add_step_widget(widget_refs))

        # Update test button state based on data availability
        self._update_test_button_state(widget_refs)

        # Load steps (backward compat: old format has root-level conditions/actions)
        steps_config = config.get("steps")
        if steps_config:
            for step_config in steps_config:
                self._add_step_widget(widget_refs, step_config)
        else:
            # Old format: single step from root-level conditions/actions
            single_step = {
                "conditions": config.get("conditions", []),
                "match": config.get("match", "ALL"),
                "actions": config.get("actions", []),
            }
            self._add_step_widget(widget_refs, single_step)

    def _add_step_widget(self, rule_widget_refs, step_config=None):
        """Adds a step (IF conditions + THEN actions) to a rule.

        Each step is a narrowing filter: step N only processes rows
        that matched step N-1.

        Args:
            rule_widget_refs (dict): Rule widget references containing steps list
            step_config (dict, optional): Step configuration with conditions/match/actions
        """
        if not isinstance(step_config, dict):
            step_config = {"conditions": [], "match": "ALL", "actions": []}

        steps = rule_widget_refs["steps"]
        step_number = len(steps) + 1
        steps_container = rule_widget_refs["steps_container"]

        # Add separator between steps (not before first step)
        separator_label = None
        if step_number > 1:
            separator_label = QLabel("   ↓ THEN CHECK ↓")
            separator_label.setAlignment(Qt.AlignCenter)
            separator_label.setStyleSheet(
                "color: #FF9800; font-weight: bold; font-size: 11pt; "
                "padding: 4px; margin: 2px 0;"
            )
            steps_container.addWidget(separator_label)

        # Step wrapper
        step_box = QGroupBox(f"Step {step_number}")
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        step_box.setStyleSheet(
            f"QGroupBox {{ font-weight: bold; border: 1px solid {theme.border}; "
            f"border-radius: 4px; margin-top: 6px; padding-top: 10px; }}"
        )
        step_layout = QVBoxLayout(step_box)

        # Conditions box ("IF")
        conditions_box = QGroupBox("IF")
        conditions_layout = QVBoxLayout(conditions_box)
        match_layout = QHBoxLayout()
        match_layout.addWidget(QLabel("Execute actions if"))
        match_combo = WheelIgnoreComboBox()
        match_combo.addItems(["ALL", "ANY"])
        match_combo.setCurrentText(step_config.get("match", "ALL"))
        match_layout.addWidget(match_combo)
        match_layout.addWidget(QLabel("of the following conditions are met:"))
        match_layout.addStretch()
        conditions_layout.addLayout(match_layout)
        conditions_rows_layout = QVBoxLayout()
        conditions_layout.addLayout(conditions_rows_layout)
        add_condition_btn = QPushButton("Add Condition")
        conditions_layout.addWidget(add_condition_btn, 0, Qt.AlignLeft)
        step_layout.addWidget(conditions_box)

        # Actions box ("THEN")
        actions_box = QGroupBox("THEN perform these actions:")
        actions_layout = QVBoxLayout(actions_box)
        actions_rows_layout = QVBoxLayout()
        actions_layout.addLayout(actions_rows_layout)
        add_action_btn = QPushButton("Add Action")
        actions_layout.addWidget(add_action_btn, 0, Qt.AlignLeft)
        step_layout.addWidget(actions_box)

        # Delete step button (not for step 1)
        delete_step_btn = None
        if step_number > 1:
            delete_step_btn = QPushButton("Delete Step")
            delete_step_btn.setStyleSheet("color: #f44336;")
            step_layout.addWidget(delete_step_btn, 0, Qt.AlignRight)

        steps_container.addWidget(step_box)

        # Step references (same keys as old rule_widget_refs for compatibility)
        step_refs = {
            "step_box": step_box,
            "separator_label": separator_label,
            "match_combo": match_combo,
            "conditions_layout": conditions_rows_layout,
            "actions_layout": actions_rows_layout,
            "conditions": [],
            "actions": [],
        }
        steps.append(step_refs)

        # Connect buttons
        add_condition_btn.clicked.connect(lambda: self.add_condition_row(step_refs))
        add_action_btn.clicked.connect(lambda: self.add_action_row(step_refs))
        if delete_step_btn:
            delete_step_btn.clicked.connect(lambda: self._delete_step(rule_widget_refs, step_refs))

        # Load conditions and actions
        for cond_config in step_config.get("conditions", []):
            self.add_condition_row(step_refs, cond_config)
        for act_config in step_config.get("actions", []):
            self.add_action_row(step_refs, act_config)

    def _delete_step(self, rule_widget_refs, step_refs):
        """Delete a step from a rule (never deletes step 1)."""
        steps = rule_widget_refs["steps"]
        if step_refs not in steps or len(steps) <= 1:
            return

        idx = steps.index(step_refs)
        steps.remove(step_refs)

        # Remove widgets
        if step_refs.get("separator_label"):
            step_refs["separator_label"].setParent(None)
            step_refs["separator_label"].deleteLater()
        step_refs["step_box"].setParent(None)
        step_refs["step_box"].deleteLater()

        # Re-number remaining steps
        for i, s in enumerate(steps):
            s["step_box"].setTitle(f"Step {i + 1}")
            # Remove separator from new step 1
            if i == 0 and s.get("separator_label"):
                s["separator_label"].setParent(None)
                s["separator_label"].deleteLater()
                s["separator_label"] = None

    def add_condition_row(self, rule_widget_refs, config=None):
        """Adds a new row of widgets for a single condition within a rule.

        This method now supports dynamic value widgets, allowing for either a
        `QLineEdit` or a `QComboBox` based on the selected field and operator.

        Args:
            rule_widget_refs (dict): A dictionary of widget references for the
                parent rule (or step).
            config (dict, optional): The configuration for a pre-existing
                condition. If None, creates a new, blank condition.
        """
        if not isinstance(config, dict):
            config = {}
        row_layout = QHBoxLayout()
        field_combo = WheelIgnoreComboBox()

        # Get dynamic fields from analysis DataFrame
        available_fields = self.get_available_rule_fields()

        # Add fields with separators disabled
        for field in available_fields:
            if field.startswith("---"):
                # Add separator as disabled item
                field_combo.addItem(field)
                # Disable the separator item
                model = field_combo.model()
                item = model.item(field_combo.count() - 1)
                item.setEnabled(False)
            else:
                field_combo.addItem(field)

        op_combo = WheelIgnoreComboBox()
        op_combo.addItems(self.CONDITION_OPERATORS)
        delete_btn = QPushButton("X")

        row_layout.addWidget(field_combo)
        row_layout.addWidget(op_combo)
        # The value widget will be inserted at index 2 by the handler

        # Set current text, skipping separators
        initial_field = config.get("field", "")
        if initial_field and not initial_field.startswith("---"):
            # Find the index of the field in the combo box
            index = field_combo.findText(initial_field)
            if index >= 0:
                field_combo.setCurrentIndex(index)
            else:
                # Field not found in combo box - add it to preserve saved value
                field_combo.addItem(initial_field)
                field_combo.setCurrentText(initial_field)
        elif not initial_field:
            # Set to first non-separator field
            for i, field in enumerate(available_fields):
                if not field.startswith("---"):
                    field_combo.setCurrentIndex(i)
                    break
        op_combo.setCurrentText(config.get("operator", self.CONDITION_OPERATORS[0]))
        initial_value = config.get("value", "")

        row_widget = QWidget()
        row_widget.setLayout(row_layout)

        condition_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "value_layout": row_layout,
        }

        row_layout.addWidget(delete_btn)

        # Connect signals to the new handler
        field_combo.currentTextChanged.connect(lambda: self._on_rule_condition_changed(condition_refs))
        op_combo.currentTextChanged.connect(lambda: self._on_rule_condition_changed(condition_refs))

        # Create the initial value widget
        self._on_rule_condition_changed(condition_refs, initial_value=initial_value)

        rule_widget_refs["conditions_layout"].addWidget(row_widget)
        rule_widget_refs["conditions"].append(condition_refs)
        delete_btn.clicked.connect(
            lambda: self._delete_row_from_list(row_widget, rule_widget_refs["conditions"], condition_refs)
        )

    def _on_rule_condition_changed(self, condition_refs, initial_value=None):
        """Dynamically changes the rule's value widget based on other selections.

        This method is connected to the 'field' and 'operator' combo boxes
        for a rule condition. It creates a `QComboBox` for value selection if
        the field is in the DataFrame and the operator is suitable (e.g., 'equals').
        For operators like 'is_empty', it hides the value widget. Otherwise,
        it provides a standard `QLineEdit`.

        Args:
            condition_refs (dict): A dictionary of widget references for the
                condition row.
            initial_value (any, optional): The value to set in the newly
                created widget. Defaults to None.
        """
        field = condition_refs["field"].currentText()
        op = condition_refs["op"].currentText()

        # Clean up validation feedback before removing widget
        if "feedback_label" in condition_refs:
            condition_refs["feedback_label"].deleteLater()
            del condition_refs["feedback_label"]

        # Cancel pending validation timer
        if "validation_timer" in condition_refs:
            condition_refs["validation_timer"].stop()
            del condition_refs["validation_timer"]

        # Remove the old value widget, if it exists
        if condition_refs["value_widget"]:
            condition_refs["value_widget"].deleteLater()
            condition_refs["value_widget"] = None

        # Operators that don't need a value input
        if op in ["is_empty", "is_not_empty"]:
            return  # No widget will be created or added

        # Determine if a ComboBox should be used
        use_combobox = (
            op in ["equals", "does not equal"]
            and not self.analysis_df.empty
            and field in self.analysis_df.columns
        )

        if use_combobox:
            unique_values = get_unique_column_values(self.analysis_df, field)
            new_widget = WheelIgnoreComboBox()
            new_widget.addItems([""] + unique_values)  # Add a blank option
            if initial_value and str(initial_value) in unique_values:
                new_widget.setCurrentText(str(initial_value))

        # DATE OPERATORS - Use QDateEdit with calendar popup
        elif op in ["date before", "date after", "date equals"]:
            from PySide6.QtWidgets import QDateEdit
            from PySide6.QtCore import QDate

            new_widget = QDateEdit()
            new_widget.setCalendarPopup(True)  # Enable calendar dropdown
            new_widget.setDisplayFormat("yyyy-MM-dd")  # ISO format

            # Parse initial value if provided
            if initial_value:
                parsed_date = self._parse_date_for_widget(initial_value)
                if parsed_date:
                    new_widget.setDate(parsed_date)
                else:
                    new_widget.setDate(QDate.currentDate())
            else:
                new_widget.setDate(QDate.currentDate())

            new_widget.setToolTip(
                "Select date from calendar or type manually.\n"
                "Formats: YYYY-MM-DD, DD/MM/YYYY, timestamp"
            )

        else:
            # Default to QLineEdit with smart placeholders
            new_widget = QLineEdit()

            # Set operator-specific placeholders
            placeholder = "Value"  # Default

            if op in ["in list", "not in list"]:
                placeholder = "Value1, Value2, Value3"
            elif op in ["between", "not between"]:
                placeholder = "10-100"
            elif op in ["matches regex", "does not match regex"]:
                placeholder = "^SKU-\\d{4}$"

            new_widget.setPlaceholderText(placeholder)

            if initial_value is not None:
                new_widget.setText(str(initial_value))

        # Insert the new widget into the layout at the correct position
        condition_refs["value_layout"].insertWidget(2, new_widget, 1)
        condition_refs["value_widget"] = new_widget

        # Connect validation for QLineEdit widgets (QLineEdit is already imported globally)
        if isinstance(new_widget, QLineEdit):
            new_widget.textChanged.connect(lambda: self._validate_condition_value(condition_refs))

    def _validate_condition_value(self, condition_refs):
        """
        Validate condition value based on operator type.

        Validates in real-time with debouncing for regex patterns (500ms).
        Other operators validate immediately.

        Args:
            condition_refs (dict): Condition widget references
        """
        from PySide6.QtCore import QTimer

        op = condition_refs["op"].currentText()

        # Cancel existing timer for this condition
        if "validation_timer" in condition_refs:
            condition_refs["validation_timer"].stop()

        # For regex: debounce 500ms
        if op in ["matches regex", "does not match regex"]:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._perform_validation(condition_refs))
            timer.start(500)  # 500ms debounce
            condition_refs["validation_timer"] = timer
        else:
            # For other operators: validate immediately
            self._perform_validation(condition_refs)

    def _perform_validation(self, condition_refs):
        """
        Execute validation based on operator type and show feedback.

        Args:
            condition_refs (dict): Condition widget references
        """
        from gui.rule_validator import (
            validate_regex,
            validate_date,
            validate_range,
            validate_list,
            validate_numeric
        )

        op = condition_refs["op"].currentText()
        value_widget = condition_refs.get("value_widget")

        if not value_widget:
            return

        # Get value based on widget type
        from PySide6.QtWidgets import QComboBox, QLineEdit, QDateEdit
        if isinstance(value_widget, QComboBox):
            value = value_widget.currentText()
        elif isinstance(value_widget, QDateEdit):
            value = value_widget.date().toString("yyyy-MM-dd")
        elif isinstance(value_widget, QLineEdit):
            value = value_widget.text()
        else:
            return

        # Validate based on operator
        if op in ["matches regex", "does not match regex"]:
            is_valid, error_msg = validate_regex(value)
            if is_valid:
                self._show_validation_feedback(condition_refs, "clear", "")
            else:
                self._show_validation_feedback(condition_refs, "error", error_msg)

        elif op in ["date before", "date after", "date equals"]:
            # QDateEdit always provides valid dates, skip validation
            self._show_validation_feedback(condition_refs, "clear", "")

        elif op in ["between", "not between"]:
            is_valid, error_msg, warning_msg = validate_range(value)
            if not is_valid:
                self._show_validation_feedback(condition_refs, "error", error_msg)
            elif warning_msg:
                self._show_validation_feedback(condition_refs, "warning", warning_msg)
            else:
                self._show_validation_feedback(condition_refs, "clear", "")

        elif op in ["in list", "not in list"]:
            is_valid, item_count, error_msg = validate_list(value)
            if not is_valid:
                self._show_validation_feedback(condition_refs, "error", error_msg)
            else:
                self._show_validation_feedback(condition_refs, "success", f"{item_count} items")

        elif op in ["is greater than", "is less than", "is greater than or equal", "is less than or equal"]:
            is_valid, error_msg = validate_numeric(value)
            if not is_valid:
                self._show_validation_feedback(condition_refs, "error", error_msg)
            else:
                self._show_validation_feedback(condition_refs, "clear", "")

        else:
            # No validation needed for other operators
            self._show_validation_feedback(condition_refs, "clear", "")

    def _show_validation_feedback(self, condition_refs, status, message):
        """
        Show validation feedback with visual indicators.

        Args:
            condition_refs (dict): Condition widget references
            status (str): "error", "warning", "success", or "clear"
            message (str): Message to display
        """
        from PySide6.QtWidgets import QLabel

        value_widget = condition_refs.get("value_widget")
        if not value_widget:
            return

        # Create feedback label if doesn't exist
        if "feedback_label" not in condition_refs:
            feedback_label = QLabel()
            feedback_label.setWordWrap(True)
            feedback_label.setStyleSheet("font-size: 9pt; margin-top: 2px;")
            condition_refs["value_layout"].addWidget(feedback_label)
            condition_refs["feedback_label"] = feedback_label

        feedback_label = condition_refs["feedback_label"]

        if status == "error":
            value_widget.setStyleSheet("border: 1px solid #f44336; background-color: #ffebee;")
            feedback_label.setStyleSheet("color: #f44336; font-size: 9pt;")
            feedback_label.setText(f"⚠ {message}")
            feedback_label.show()

        elif status == "warning":
            value_widget.setStyleSheet("border: 1px solid #ff9800; background-color: #fff3e0;")
            feedback_label.setStyleSheet("color: #ff9800; font-size: 9pt;")
            feedback_label.setText(f"⚠ {message}")
            feedback_label.show()

        elif status == "success":
            value_widget.setStyleSheet("border: 1px solid #4CAF50;")
            feedback_label.setStyleSheet("color: #4CAF50; font-size: 9pt;")
            feedback_label.setText(f"✓ {message}")
            feedback_label.show()

        elif status == "clear":
            value_widget.setStyleSheet("")
            feedback_label.hide()

    def _parse_date_for_widget(self, date_str):
        """
        Parse date string to QDate for widget initialization.

        Supports multiple formats:
        - ISO format: "2024-01-30"
        - European: "30/01/2024", "30.01.2024"
        - Timestamp: "2026-01-14 18:56:50 +0200"

        Args:
            date_str: Date string to parse

        Returns:
            QDate object or None if parsing fails
        """
        from PySide6.QtCore import QDate
        from shopify_tool.rules import _parse_date_safe

        pd_timestamp = _parse_date_safe(date_str)
        if pd_timestamp:
            return QDate(pd_timestamp.year, pd_timestamp.month, pd_timestamp.day)
        return None

    def _test_rule(self, rule_widget_refs):
        """
        Test a rule against current analysis data.

        Opens a test dialog showing:
        - Condition evaluation results
        - Matched rows preview
        - Actions to be applied
        - Preview after actions

        Args:
            rule_widget_refs (dict): Rule widget references
        """
        from PySide6.QtWidgets import QMessageBox
        from gui.rule_test_dialog import RuleTestDialog

        if self.analysis_df is None or self.analysis_df.empty:
            QMessageBox.warning(
                self,
                "No Data",
                "No analysis data available to test rule.\n\n"
                "Please run analysis first in the main window."
            )
            return

        # Build rule config from current UI state
        rule_config = self._build_rule_config_from_widgets(rule_widget_refs)

        # Validate rule has conditions in at least one step
        has_conditions = any(
            step.get("conditions") for step in rule_config.get("steps", [])
        )
        if not has_conditions:
            QMessageBox.warning(
                self,
                "No Conditions",
                "This rule has no conditions defined in any step.\n\n"
                "Add at least one condition before testing."
            )
            return

        # Open test dialog
        dialog = RuleTestDialog(rule_config, self.analysis_df, parent=self)
        dialog.exec()

    def _build_rule_config_from_widgets(self, rule_widget_refs):
        """
        Extract current rule configuration from widget state.

        Builds a config dict compatible with RuleEngine from the current
        UI state of all condition and action widgets. Supports multi-step rules.

        Args:
            rule_widget_refs (dict): Rule widget references

        Returns:
            dict: Rule configuration compatible with RuleEngine
        """
        from PySide6.QtWidgets import QComboBox, QLineEdit, QDateEdit

        steps = []
        for step_refs in rule_widget_refs.get("steps", []):
            # Extract conditions
            conditions = []
            for condition_refs in step_refs["conditions"]:
                value_widget = condition_refs.get("value_widget")
                val = ""

                if value_widget:
                    if isinstance(value_widget, QComboBox):
                        val = value_widget.currentText()
                    elif isinstance(value_widget, QDateEdit):
                        val = value_widget.date().toString("yyyy-MM-dd")
                    elif isinstance(value_widget, QLineEdit):
                        val = value_widget.text()

                conditions.append({
                    "field": condition_refs["field"].currentText(),
                    "operator": condition_refs["op"].currentText(),
                    "value": val,
                })

            # Extract actions
            actions = []
            for action_refs in step_refs["actions"]:
                action_type = action_refs["type"].currentText()
                action_dict = {"type": action_type}

                param_widgets = action_refs.get("param_widgets", {})
                for param_name, widget in param_widgets.items():
                    if isinstance(widget, QComboBox):
                        action_dict[param_name] = widget.currentText()
                    elif isinstance(widget, QLineEdit):
                        action_dict[param_name] = widget.text()

                actions.append(action_dict)

            steps.append({
                "conditions": conditions,
                "match": step_refs["match_combo"].currentText(),
                "actions": actions,
            })

        return {
            "name": rule_widget_refs["name_edit"].text(),
            "level": rule_widget_refs["level_combo"].currentText(),
            "steps": steps,
        }

    def _update_test_button_state(self, rule_widget_refs):
        """
        Enable/disable test button based on data availability.

        Args:
            rule_widget_refs (dict): Rule widget references
        """
        has_data = self.analysis_df is not None and not self.analysis_df.empty
        rule_widget_refs["test_btn"].setEnabled(has_data)

        if not has_data:
            rule_widget_refs["test_btn"].setToolTip(
                "Test disabled: No analysis data available.\n"
                "Run analysis in main window first."
            )
        else:
            rule_widget_refs["test_btn"].setToolTip("Test this rule against current analysis data")


    def add_action_row(self, rule_widget_refs, config=None):
        """Adds action row with dynamic parameter widgets based on type.

        Args:
            rule_widget_refs (dict): A dictionary of widget references for the
                parent rule.
            config (dict, optional): The configuration for a pre-existing
                action. If None, creates a new, blank action.
        """
        if not isinstance(config, dict):
            config = {}

        row_layout = QHBoxLayout()

        # Type dropdown
        type_combo = WheelIgnoreComboBox()
        type_combo.addItems(self.ACTION_TYPES)
        type_combo.setCurrentText(config.get("type", self.ACTION_TYPES[0]))

        # Delete button
        delete_btn = QPushButton("X")

        row_layout.addWidget(type_combo)
        # Параметри будуть вставлені динамічно

        row_widget = QWidget()
        row_widget.setLayout(row_layout)

        # Зберегти посилання
        action_refs = {
            "widget": row_widget,
            "type": type_combo,
            "param_widgets": {},
            "param_layout": row_layout,
        }

        # Connect type change
        type_combo.currentTextChanged.connect(
            lambda: self._on_action_type_changed(action_refs)
        )

        # Створити початкові widgets
        self._on_action_type_changed(action_refs, initial_config=config)

        row_layout.addWidget(delete_btn)

        rule_widget_refs["actions_layout"].addWidget(row_widget)
        rule_widget_refs["actions"].append(action_refs)

        delete_btn.clicked.connect(
            lambda: self._delete_row_from_list(row_widget, rule_widget_refs["actions"], action_refs)
        )

    def _on_action_type_changed(self, action_refs, initial_config=None):
        """Dynamically updates parameter widgets based on action type."""
        action_type = action_refs["type"].currentText()

        # Очистити існуючі параметри
        for widget in action_refs["param_widgets"].values():
            widget.deleteLater()
        action_refs["param_widgets"].clear()

        layout = action_refs["param_layout"]
        insert_pos = 1  # Після type combo

        # Створити widgets залежно від типу
        if action_type in ["ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG", "SET_STATUS"]:
            # Простий value field
            value_edit = QLineEdit()
            value_edit.setPlaceholderText("Value")
            if initial_config:
                value_edit.setText(initial_config.get("value", ""))
            layout.insertWidget(insert_pos, value_edit, 1)
            action_refs["param_widgets"]["value"] = value_edit

        elif action_type == "COPY_FIELD":
            # Source dropdown
            source_combo = WheelIgnoreComboBox()
            fields = self.get_available_rule_fields()
            source_combo.addItems([f for f in fields if not f.startswith("---")])
            if initial_config:
                source_combo.setCurrentText(initial_config.get("source", ""))

            # Target input
            target_edit = QLineEdit()
            target_edit.setPlaceholderText("Target column")
            if initial_config:
                target_edit.setText(initial_config.get("target", ""))

            layout.insertWidget(insert_pos, source_combo, 1)
            layout.insertWidget(insert_pos + 1, QLabel("→"), 0)
            layout.insertWidget(insert_pos + 2, target_edit, 1)

            action_refs["param_widgets"]["source"] = source_combo
            action_refs["param_widgets"]["target"] = target_edit

        elif action_type == "CALCULATE":
            # Operation dropdown
            op_combo = WheelIgnoreComboBox()
            op_combo.addItems(["add", "subtract", "multiply", "divide"])
            if initial_config:
                op_combo.setCurrentText(initial_config.get("operation", "add"))

            # Field1 & Field2 dropdowns
            fields = [f for f in self.get_available_rule_fields() if not f.startswith("---")]

            field1_combo = WheelIgnoreComboBox()
            field1_combo.addItems(fields)
            if initial_config:
                field1_combo.setCurrentText(initial_config.get("field1", ""))

            field2_combo = WheelIgnoreComboBox()
            field2_combo.addItems(fields)
            if initial_config:
                field2_combo.setCurrentText(initial_config.get("field2", ""))

            # Target input
            target_edit = QLineEdit()
            target_edit.setPlaceholderText("Result column")
            if initial_config:
                target_edit.setText(initial_config.get("target", ""))

            layout.insertWidget(insert_pos, op_combo, 0)
            layout.insertWidget(insert_pos + 1, field1_combo, 1)
            layout.insertWidget(insert_pos + 2, field2_combo, 1)
            layout.insertWidget(insert_pos + 3, QLabel("→"), 0)
            layout.insertWidget(insert_pos + 4, target_edit, 1)

            action_refs["param_widgets"]["operation"] = op_combo
            action_refs["param_widgets"]["field1"] = field1_combo
            action_refs["param_widgets"]["field2"] = field2_combo
            action_refs["param_widgets"]["target"] = target_edit

        elif action_type == "SET_MULTI_TAGS":
            # Comma-separated tags
            tags_edit = QLineEdit()
            tags_edit.setPlaceholderText("TAG1, TAG2, TAG3")
            if initial_config:
                tags_value = initial_config.get("tags") or initial_config.get("value", "")
                if isinstance(tags_value, list):
                    tags_edit.setText(", ".join(tags_value))
                else:
                    tags_edit.setText(tags_value)

            layout.insertWidget(insert_pos, tags_edit, 1)
            action_refs["param_widgets"]["value"] = tags_edit

        elif action_type == "ALERT_NOTIFICATION":
            # Message input
            message_edit = QLineEdit()
            message_edit.setPlaceholderText("Alert message")
            if initial_config:
                message_edit.setText(initial_config.get("message", ""))

            # Severity dropdown
            severity_combo = WheelIgnoreComboBox()
            severity_combo.addItems(["info", "warning", "error"])
            if initial_config:
                severity_combo.setCurrentText(initial_config.get("severity", "info"))

            layout.insertWidget(insert_pos, message_edit, 1)
            layout.insertWidget(insert_pos + 1, severity_combo, 0)

            action_refs["param_widgets"]["message"] = message_edit
            action_refs["param_widgets"]["severity"] = severity_combo

        elif action_type == "ADD_PRODUCT":
            # SKU input
            sku_edit = QLineEdit()
            sku_edit.setPlaceholderText("Product SKU")
            if initial_config:
                sku_edit.setText(initial_config.get("sku", ""))

            # Quantity spinbox
            qty_spin = QSpinBox()
            qty_spin.setMinimum(1)
            qty_spin.setMaximum(9999)
            qty_spin.setValue(initial_config.get("quantity", 1) if initial_config else 1)

            layout.insertWidget(insert_pos, sku_edit, 1)
            layout.insertWidget(insert_pos + 1, QLabel("Qty:"), 0)
            layout.insertWidget(insert_pos + 2, qty_spin, 0)

            action_refs["param_widgets"]["sku"] = sku_edit
            action_refs["param_widgets"]["quantity"] = qty_spin

    def create_packing_lists_tab(self):
        """Creates the 'Packing Lists' tab for managing report configurations."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        add_btn = QPushButton("Add New Packing List")
        add_btn.clicked.connect(self.add_packing_list_widget)
        main_layout.addWidget(add_btn, 0, Qt.AlignLeft)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.packing_lists_layout = QVBoxLayout(scroll_content)
        self.packing_lists_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        self.tab_widget.addTab(tab, "Packing Lists")
        for pl_config in self.config_data.get("packing_list_configs", []):
            self.add_packing_list_widget(pl_config)

    def add_packing_list_widget(self, config=None):
        """Adds a new group of widgets for a single packing list configuration.

        Args:
            config (dict, optional): The configuration for a pre-existing
                packing list. If None, creates a new, blank one.
        """
        if not isinstance(config, dict):
            config = {"name": "", "output_filename": "", "filters": [], "exclude_skus": []}
        pl_box = QGroupBox()
        pl_layout = QVBoxLayout(pl_box)
        form_layout = QFormLayout()
        name_edit = QLineEdit(config.get("name", ""))
        filename_edit = QLineEdit(config.get("output_filename", ""))
        exclude_skus_edit = QLineEdit(",".join(config.get("exclude_skus", [])))
        form_layout.addRow("Name:", name_edit)
        form_layout.addRow("Output Filename:", filename_edit)
        form_layout.addRow("Exclude SKUs (comma-separated):", exclude_skus_edit)
        pl_layout.addLayout(form_layout)
        filters_box = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_box)
        filters_rows_layout = QVBoxLayout()
        filters_layout.addLayout(filters_rows_layout)
        add_filter_btn = QPushButton("Add Filter")
        filters_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        pl_layout.addWidget(filters_box)
        delete_btn = QPushButton("Delete Packing List")
        pl_layout.addWidget(delete_btn, 0, Qt.AlignRight)
        self.packing_lists_layout.addWidget(pl_box)
        widget_refs = {
            "group_box": pl_box,
            "name": name_edit,
            "filename": filename_edit,
            "exclude_skus": exclude_skus_edit,
            "filters_layout": filters_rows_layout,
            "filters": [],
        }
        self.packing_list_widgets.append(widget_refs)
        add_filter_btn.clicked.connect(
            lambda: self.add_filter_row(widget_refs, self.FILTERABLE_COLUMNS, self.FILTER_OPERATORS)
        )
        delete_btn.clicked.connect(lambda: self._delete_widget_from_list(widget_refs, self.packing_list_widgets))
        for f_config in config.get("filters", []):
            self.add_filter_row(widget_refs, self.FILTERABLE_COLUMNS, self.FILTER_OPERATORS, f_config)

    def add_filter_row(self, parent_widget_refs, fields, operators, config=None):
        """Adds a new row of widgets for a single filter criterion.

        This is a generic helper used by both packing list and stock export tabs.

        Args:
            parent_widget_refs (dict): Widget references for the parent report.
            fields (list[str]): The list of columns to show in the field dropdown.
            operators (list[str]): The list of operators to show.
            config (dict, optional): The configuration for a pre-existing
                filter. If None, creates a new, blank filter.
        """
        if not isinstance(config, dict):
            config = {}
        row_layout = QHBoxLayout()
        field_combo = WheelIgnoreComboBox()
        field_combo.addItems(fields)
        op_combo = WheelIgnoreComboBox()
        op_combo.addItems(operators)
        value_edit = QLineEdit()
        delete_btn = QPushButton("X")

        row_layout.addWidget(field_combo)
        row_layout.addWidget(op_combo)
        row_layout.addWidget(value_edit, 1)

        field_combo.setCurrentText(config.get("field", fields[0]))
        op_combo.setCurrentText(config.get("operator", operators[0]))
        val = config.get("value", "")

        row_widget = QWidget()
        row_widget.setLayout(row_layout)

        filter_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "value_layout": row_layout,
        }

        # Connect signals before setting initial value to trigger the handler
        field_combo.currentTextChanged.connect(lambda: self._on_filter_criteria_changed(filter_refs))
        op_combo.currentTextChanged.connect(lambda: self._on_filter_criteria_changed(filter_refs))

        self._on_filter_criteria_changed(filter_refs, initial_value=val)  # Set initial widget and value

        row_layout.addWidget(delete_btn)
        parent_widget_refs["filters_layout"].addWidget(row_widget)
        parent_widget_refs["filters"].append(filter_refs)
        delete_btn.clicked.connect(
            lambda: self._delete_row_from_list(row_widget, parent_widget_refs["filters"], filter_refs)
        )

    def _on_filter_criteria_changed(self, filter_refs, initial_value=None):
        """Dynamically changes the filter's value widget based on other selections.

        For example, if the operator is '==' and the field is 'Order_Type',
        this method will create a QComboBox with unique values from the
        DataFrame ('Single', 'Multi') instead of a plain QLineEdit.

        Args:
            filter_refs (dict): A dictionary of widget references for the filter row.
            initial_value (any, optional): The value to set in the newly
                created widget. Defaults to None.
        """
        field = filter_refs["field"].currentText()
        op = filter_refs["op"].currentText()

        if filter_refs["value_widget"]:
            filter_refs["value_widget"].deleteLater()

        use_combobox = op in ["==", "!="] and not self.analysis_df.empty and field in self.analysis_df.columns

        if use_combobox:
            try:
                unique_values = self.analysis_df[field].dropna().unique().tolist()
                unique_values = sorted([str(v) for v in unique_values])
                new_widget = WheelIgnoreComboBox()
                new_widget.addItems(unique_values)
                if initial_value and str(initial_value) in unique_values:
                    new_widget.setCurrentText(str(initial_value))
            except Exception:
                new_widget = QLineEdit()
                new_widget.setText(str(initial_value) if initial_value else "")
        else:
            new_widget = QLineEdit()
            placeholder = "Value"
            if op in ["in", "not in"]:
                placeholder = "Values, comma-separated"
            new_widget.setPlaceholderText(placeholder)
            text_value = ",".join(initial_value) if isinstance(initial_value, list) else (initial_value or "")
            new_widget.setText(str(text_value))

        filter_refs["value_layout"].insertWidget(2, new_widget, 1)
        filter_refs["value_widget"] = new_widget

    def create_stock_exports_tab(self):
        """Creates the 'Stock Exports' tab for managing report configurations."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        add_btn = QPushButton("Add New Stock Export")
        add_btn.clicked.connect(self.add_stock_export_widget)
        main_layout.addWidget(add_btn, 0, Qt.AlignLeft)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.stock_exports_layout = QVBoxLayout(scroll_content)
        self.stock_exports_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        self.tab_widget.addTab(tab, "Stock Exports")
        for se_config in self.config_data.get("stock_export_configs", []):
            self.add_stock_export_widget(se_config)

    def add_stock_export_widget(self, config=None):
        """Adds a new group of widgets for a single stock export configuration.

        Args:
            config (dict, optional): The configuration for a pre-existing
                stock export. If None, creates a new, blank one.
        """
        if not isinstance(config, dict):
            config = {"name": "", "output_filename": "", "filters": []}
        se_box = QGroupBox()
        se_layout = QVBoxLayout(se_box)
        form_layout = QFormLayout()
        name_edit = QLineEdit(config.get("name", ""))
        filename_edit = QLineEdit(config.get("output_filename", ""))
        form_layout.addRow("Name:", name_edit)
        form_layout.addRow("Output Filename:", filename_edit)
        se_layout.addLayout(form_layout)
        filters_box = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_box)
        filters_rows_layout = QVBoxLayout()
        filters_layout.addLayout(filters_rows_layout)
        add_filter_btn = QPushButton("Add Filter")
        filters_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        se_layout.addWidget(filters_box)
        delete_btn = QPushButton("Delete Stock Export")
        se_layout.addWidget(delete_btn, 0, Qt.AlignRight)
        self.stock_exports_layout.addWidget(se_box)
        widget_refs = {
            "group_box": se_box,
            "name": name_edit,
            "filename": filename_edit,
            "filters_layout": filters_rows_layout,
            "filters": [],
        }
        self.stock_export_widgets.append(widget_refs)
        add_filter_btn.clicked.connect(
            lambda: self.add_filter_row(widget_refs, self.FILTERABLE_COLUMNS, self.FILTER_OPERATORS)
        )
        delete_btn.clicked.connect(lambda: self._delete_widget_from_list(widget_refs, self.stock_export_widgets))
        for f_config in config.get("filters", []):
            self.add_filter_row(widget_refs, self.FILTERABLE_COLUMNS, self.FILTER_OPERATORS, f_config)

    def create_mappings_tab(self):
        """Creates the 'Mappings' tab for column mappings and courier mappings."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)

        # Add scroll area for the entire tab
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # ========================================
        # COLUMN MAPPINGS - Orders
        # ========================================
        orders_box = QGroupBox("📋 Orders CSV Column Mapping")
        orders_layout = QVBoxLayout(orders_box)

        # Define required and optional fields for orders
        orders_required = ["Order_Number", "SKU", "Quantity", "Shipping_Method"]
        orders_optional = ["Product_Name", "Shipping_Country", "Tags", "Notes", "Total_Price", "Subtotal"]

        # Get current mappings (v2 format)
        column_mappings = self.config_data.get("column_mappings", {})
        orders_mappings = column_mappings.get("orders", {})

        # Create widget
        self.orders_mapping_widget = ColumnMappingWidget(
            mapping_type="orders",
            current_mappings=orders_mappings,
            required_fields=orders_required,
            optional_fields=orders_optional
        )

        orders_layout.addWidget(self.orders_mapping_widget)
        scroll_layout.addWidget(orders_box)

        # ========================================
        # COLUMN MAPPINGS - Stock
        # ========================================
        stock_box = QGroupBox("📦 Stock CSV Column Mapping")
        stock_layout = QVBoxLayout(stock_box)

        # Define required and optional fields for stock
        stock_required = ["SKU", "Stock"]
        stock_optional = ["Product_Name"]

        # Get current mappings (v2 format)
        stock_mappings = column_mappings.get("stock", {})

        # Create widget
        self.stock_mapping_widget = ColumnMappingWidget(
            mapping_type="stock",
            current_mappings=stock_mappings,
            required_fields=stock_required,
            optional_fields=stock_optional
        )

        stock_layout.addWidget(self.stock_mapping_widget)
        scroll_layout.addWidget(stock_box)

        # ========================================
        # COURIER MAPPINGS
        # ========================================
        courier_mappings_box = QGroupBox("Courier Mappings")
        courier_main_layout = QVBoxLayout(courier_mappings_box)

        instructions2 = QLabel(
            "Map different shipping provider names to standardized courier codes.\n"
            "You can specify multiple patterns (comma-separated) for each courier."
        )
        instructions2.setWordWrap(True)
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        instructions2.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; font-size: 10pt;")
        courier_main_layout.addWidget(instructions2)

        # Container for courier mapping rows
        self.courier_mappings_container = QWidget()
        self.courier_mappings_layout = QVBoxLayout(self.courier_mappings_container)
        self.courier_mappings_layout.setContentsMargins(0, 0, 0, 0)

        courier_main_layout.addWidget(self.courier_mappings_container)

        add_courier_btn = QPushButton("+ Add Courier Mapping")
        add_courier_btn.clicked.connect(lambda: self.add_courier_mapping_row())
        courier_main_layout.addWidget(add_courier_btn, 0, Qt.AlignLeft)

        scroll_layout.addWidget(courier_mappings_box)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        self.tab_widget.addTab(tab, "Mappings")

        # Populate existing courier mappings
        courier_mappings = self.config_data.get("courier_mappings", {})
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
        delete_btn.setFixedWidth(30)
        delete_btn.setStyleSheet("color: red; font-weight: bold;")
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

        delete_btn.clicked.connect(
            lambda: self._delete_row_from_list(row_widget, self.courier_mapping_widgets, row_refs)
        )

    # ========================================
    # SETS/BUNDLES TAB
    # ========================================
    def create_sets_tab(self):
        """Create the Sets/Bundles management tab."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header_label = QLabel("🎁 Set/Bundle Definitions")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        main_layout.addWidget(header_label)

        # Help text
        help_text = QLabel(
            "Define sets/bundles that will be automatically expanded into their component SKUs during analysis.\n"
            "Example: SET-WINTER-KIT → HAT(1x), GLOVES(1x), SCARF(1x)"
        )
        help_text.setWordWrap(True)
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        help_text.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; margin-bottom: 10px;")
        main_layout.addWidget(help_text)

        # Search box
        self.sets_search = QLineEdit()
        self.sets_search.setPlaceholderText("Search by SKU or components...")
        self.sets_search.setClearButtonEnabled(True)
        self.sets_search.textChanged.connect(self._filter_sets_table)
        main_layout.addWidget(self.sets_search)

        # Sets table
        self.sets_table = QTableWidget()
        self.sets_table.setColumnCount(3)
        self.sets_table.setHorizontalHeaderLabels(["Set SKU", "Components", "Actions"])

        # Configure columns
        header = self.sets_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Set SKU
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Components
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Actions
        self.sets_table.setColumnWidth(2, 150)

        self.sets_table.setAlternatingRowColors(True)
        self.sets_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        main_layout.addWidget(self.sets_table)

        # Buttons row
        buttons_layout = QHBoxLayout()

        add_btn = QPushButton("➕ Add Set")
        add_btn.clicked.connect(self._add_set_dialog)
        buttons_layout.addWidget(add_btn)

        import_btn = QPushButton("📁 Import from CSV")
        import_btn.clicked.connect(self._import_sets_from_csv)
        buttons_layout.addWidget(import_btn)

        export_btn = QPushButton("💾 Export to CSV")
        export_btn.clicked.connect(self._export_sets_to_csv)
        buttons_layout.addWidget(export_btn)

        buttons_layout.addStretch()

        main_layout.addLayout(buttons_layout)

        # Tips
        tips_label = QLabel(
            "💡 Tips:\n"
            "• CSV format: Set_SKU, Component_SKU, Component_Quantity\n"
            "• Sets are expanded before fulfillment simulation\n"
            "• Components must exist in your stock file"
        )
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        tips_label.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; margin-top: 10px;")
        tips_label.setWordWrap(True)
        main_layout.addWidget(tips_label)

        self.tab_widget.addTab(tab, "Sets")

        # Populate table with existing sets
        self._populate_sets_table()

    def _populate_sets_table(self):
        """Populate the sets table with current set definitions."""
        set_decoders = self.config_data.get("set_decoders", {})

        self.sets_table.setRowCount(len(set_decoders))

        for row_idx, (set_sku, components) in enumerate(set_decoders.items()):
            # Set SKU column
            sku_item = QTableWidgetItem(set_sku)
            sku_item.setFlags(sku_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            self.sets_table.setItem(row_idx, 0, sku_item)

            # Components summary column
            if components:
                # Show first 5 components, then "..."
                comp_summary = ", ".join([
                    f"{comp['sku']}({comp['quantity']}x)"
                    for comp in components[:5]
                ])
                if len(components) > 5:
                    comp_summary += f" ... (+{len(components) - 5} more)"
            else:
                comp_summary = "(no components)"

            comp_item = QTableWidgetItem(comp_summary)
            comp_item.setFlags(comp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            self.sets_table.setItem(row_idx, 1, comp_item)

            # Actions column - Edit and Delete buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 2, 5, 2)
            actions_layout.setSpacing(5)

            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setMaximumWidth(70)
            edit_btn.clicked.connect(lambda checked, sku=set_sku: self._edit_set_dialog(sku))
            actions_layout.addWidget(edit_btn)

            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.setMaximumWidth(70)
            delete_btn.clicked.connect(lambda checked, sku=set_sku: self._delete_set(sku))
            actions_layout.addWidget(delete_btn)

            actions_layout.addStretch()
            self.sets_table.setCellWidget(row_idx, 2, actions_widget)

        # Re-apply search filter after repopulate
        if hasattr(self, 'sets_search'):
            self._filter_sets_table(self.sets_search.text())

    def _filter_sets_table(self, text: str):
        """Filter sets table rows by SKU or components text."""
        text = text.lower().strip()
        for row in range(self.sets_table.rowCount()):
            sku_item = self.sets_table.item(row, 0)
            comp_item = self.sets_table.item(row, 1)
            sku_text = sku_item.text().lower() if sku_item else ""
            comp_text = comp_item.text().lower() if comp_item else ""
            visible = not text or text in sku_text or text in comp_text
            self.sets_table.setRowHidden(row, not visible)

    def _add_set_dialog(self):
        """Show dialog to add a new set."""
        dialog = SetEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_sku, components = dialog.get_set_definition()

            # Debug: print what we got
            print(f"[DEBUG] Adding set '{set_sku}' with {len(components)} components:")
            for i, comp in enumerate(components):
                print(f"  {i+1}. {comp['sku']} x {comp['quantity']}")

            # Add to config
            if "set_decoders" not in self.config_data:
                self.config_data["set_decoders"] = {}

            self.config_data["set_decoders"][set_sku] = components

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(
                self,
                "Success",
                f"Set '{set_sku}' added with {len(components)} components!"
            )

    def _edit_set_dialog(self, set_sku):
        """Show dialog to edit an existing set."""
        current_components = self.config_data.get("set_decoders", {}).get(set_sku, [])

        dialog = SetEditorDialog(set_sku=set_sku, components=current_components, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_set_sku, new_components = dialog.get_set_definition()

            # Remove old SKU if changed
            if new_set_sku != set_sku:
                del self.config_data["set_decoders"][set_sku]

            # Update with new definition
            self.config_data["set_decoders"][new_set_sku] = new_components

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(self, "Success", f"Set '{new_set_sku}' updated successfully!")

    def _delete_set(self, set_sku):
        """Delete a set after confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete set '{set_sku}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            del self.config_data["set_decoders"][set_sku]
            self._populate_sets_table()
            QMessageBox.information(self, "Success", f"Set '{set_sku}' deleted successfully!")

    def _import_sets_from_csv(self):
        """Import sets from CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sets from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Import using set_decoder module
            imported_sets = import_sets_from_csv(file_path)

            if not imported_sets:
                QMessageBox.warning(self, "Warning", "No sets found in CSV file.")
                return

            # Ask user: Replace all or Merge
            reply = QMessageBox.question(
                self,
                "Import Mode",
                f"Found {len(imported_sets)} sets in CSV.\n\n"
                "Yes = Replace all existing sets\n"
                "No = Merge (update existing, add new)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Cancel:
                return

            if reply == QMessageBox.StandardButton.Yes:
                # Replace all
                self.config_data["set_decoders"] = imported_sets
            else:
                # Merge
                if "set_decoders" not in self.config_data:
                    self.config_data["set_decoders"] = {}
                self.config_data["set_decoders"].update(imported_sets)

            # Refresh table
            self._populate_sets_table()

            QMessageBox.information(
                self,
                "Success",
                f"Successfully imported {len(imported_sets)} sets from CSV!"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import sets from CSV:\n\n{str(e)}"
            )

    def _export_sets_to_csv(self):
        """Export sets to CSV file."""
        set_decoders = self.config_data.get("set_decoders", {})

        if not set_decoders:
            QMessageBox.warning(self, "Warning", "No sets to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sets to CSV",
            "sets_export.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        try:
            # Export using set_decoder module
            export_sets_to_csv(set_decoders, file_path)

            QMessageBox.information(
                self,
                "Success",
                f"Successfully exported {len(set_decoders)} sets to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export sets to CSV:\n\n{str(e)}"
            )

    # ========================================
    def create_weight_tab(self):
        """Create the Volumetric Weight management tab with sub-tabs for Products and Boxes."""
        from PySide6.QtWidgets import QTabWidget as _QTabWidget

        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()

        weight_cfg = self.config_data.get("weight_config", {
            "volumetric_divisor": 6000,
            "products": {},
            "boxes": []
        })

        # ---- Global Settings (compact row) ----
        global_row = QHBoxLayout()
        global_row.setContentsMargins(0, 0, 0, 0)
        div_label = QLabel("Volumetric Divisor (cm³ → kg):")
        self.weight_divisor_spin = QDoubleSpinBox()
        self.weight_divisor_spin.setRange(1, 100000)
        self.weight_divisor_spin.setDecimals(0)
        self.weight_divisor_spin.setValue(float(weight_cfg.get("volumetric_divisor", 6000)))
        self.weight_divisor_spin.setFixedWidth(100)
        self.weight_divisor_spin.setToolTip(
            "Volumetric weight formula: L × W × H / divisor\n"
            "6000 = DPD/Speedy standard (cm³ → kg)\n"
            "5000 = DHL/FedEx standard"
        )
        hint = QLabel("(6000 = DPD/Speedy · 5000 = DHL/FedEx)")
        hint.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt;")
        global_row.addWidget(div_label)
        global_row.addWidget(self.weight_divisor_spin)
        global_row.addWidget(hint)
        global_row.addStretch()
        main_layout.addLayout(global_row)

        # ---- Sub-tabs: Products | Boxes ----
        weight_sub_tabs = _QTabWidget()
        weight_sub_tabs.setDocumentMode(True)

        # --- Products sub-tab ---
        products_tab = QWidget()
        products_layout = QVBoxLayout(products_tab)
        products_layout.setContentsMargins(4, 6, 4, 4)
        products_layout.setSpacing(4)

        prod_toolbar = QHBoxLayout()
        import_sku_btn = QPushButton("Import from Stock CSV")
        import_sku_btn.setToolTip("Load SKUs from the current stock CSV file")
        import_sku_btn.clicked.connect(self._weight_import_skus_from_stock_csv)
        prod_toolbar.addWidget(import_sku_btn)
        import_dims_btn = QPushButton("Import Dimensions CSV")
        import_dims_btn.setToolTip("Import SKU dimensions from a CSV (columns: SKU, Name, L, W, H, No Packaging)")
        import_dims_btn.clicked.connect(self._weight_import_products_from_csv)
        prod_toolbar.addWidget(import_dims_btn)
        add_prod_btn = QPushButton("Add Row")
        add_prod_btn.clicked.connect(self._weight_add_product_row)
        prod_toolbar.addWidget(add_prod_btn)
        export_prod_btn = QPushButton("Export CSV")
        export_prod_btn.setToolTip("Export all products with dimensions to a CSV file")
        export_prod_btn.clicked.connect(self._weight_export_products_to_csv)
        prod_toolbar.addWidget(export_prod_btn)
        del_prod_btn = QPushButton("Delete Selected")
        del_prod_btn.clicked.connect(lambda: self._weight_delete_selected(self.weight_products_table))
        prod_toolbar.addWidget(del_prod_btn)
        prod_toolbar.addStretch()
        products_layout.addLayout(prod_toolbar)

        self.products_search = QLineEdit()
        self.products_search.setPlaceholderText("Search by SKU or name...")
        self.products_search.setClearButtonEnabled(True)
        self.products_search.textChanged.connect(self._filter_products_table)
        products_layout.addWidget(self.products_search)

        self.weight_products_table = QTableWidget(0, 7)
        self.weight_products_table.setHorizontalHeaderLabels([
            "SKU", "Name", "L (cm)", "W (cm)", "H (cm)", "Vol. Weight (kg)", "No Packaging"
        ])
        self.weight_products_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.weight_products_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.weight_products_table.setColumnWidth(2, 70)
        self.weight_products_table.setColumnWidth(3, 70)
        self.weight_products_table.setColumnWidth(4, 70)
        self.weight_products_table.setColumnWidth(5, 110)
        self.weight_products_table.setColumnWidth(6, 100)
        self.weight_products_table.setAlternatingRowColors(True)
        self.weight_products_table.cellChanged.connect(
            lambda row, col: self._weight_recalc_vol_weight(self.weight_products_table, row, col, [2, 3, 4])
        )
        products_layout.addWidget(self.weight_products_table)

        weight_sub_tabs.addTab(products_tab, "Products (SKU Dimensions)")

        # --- Boxes sub-tab ---
        boxes_tab = QWidget()
        boxes_layout = QVBoxLayout(boxes_tab)
        boxes_layout.setContentsMargins(4, 6, 4, 4)
        boxes_layout.setSpacing(4)

        box_toolbar = QHBoxLayout()
        import_box_btn = QPushButton("Import CSV")
        import_box_btn.setToolTip("Import boxes from a CSV (columns: Name, L, W, H)")
        import_box_btn.clicked.connect(self._weight_import_boxes_from_csv)
        box_toolbar.addWidget(import_box_btn)
        add_box_btn = QPushButton("Add Box")
        add_box_btn.clicked.connect(self._weight_add_box_row)
        box_toolbar.addWidget(add_box_btn)
        export_box_btn = QPushButton("Export CSV")
        export_box_btn.setToolTip("Export all boxes to a CSV file")
        export_box_btn.clicked.connect(self._weight_export_boxes_to_csv)
        box_toolbar.addWidget(export_box_btn)
        del_box_btn = QPushButton("Delete Selected")
        del_box_btn.clicked.connect(lambda: self._weight_delete_selected(self.weight_boxes_table))
        box_toolbar.addWidget(del_box_btn)
        box_toolbar.addStretch()
        boxes_layout.addLayout(box_toolbar)

        self.boxes_search = QLineEdit()
        self.boxes_search.setPlaceholderText("Search by box name...")
        self.boxes_search.setClearButtonEnabled(True)
        self.boxes_search.textChanged.connect(self._filter_boxes_table)
        boxes_layout.addWidget(self.boxes_search)

        self.weight_boxes_table = QTableWidget(0, 5)
        self.weight_boxes_table.setHorizontalHeaderLabels([
            "Box Name", "L (cm)", "W (cm)", "H (cm)", "Vol. Weight (kg)"
        ])
        self.weight_boxes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.weight_boxes_table.setColumnWidth(1, 70)
        self.weight_boxes_table.setColumnWidth(2, 70)
        self.weight_boxes_table.setColumnWidth(3, 70)
        self.weight_boxes_table.setColumnWidth(4, 110)
        self.weight_boxes_table.setAlternatingRowColors(True)
        self.weight_boxes_table.cellChanged.connect(
            lambda row, col: self._weight_recalc_vol_weight(self.weight_boxes_table, row, col, [1, 2, 3])
        )
        boxes_layout.addWidget(self.weight_boxes_table)

        tips_box = QLabel(
            "Volumetric weight = L × W × H / Divisor · "
            "No Packaging skips box selection · "
            "Values: box name / NO_BOX_NEEDED / NO_BOX_FITS / UNKNOWN_DIMS"
        )
        tips_box.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt;")
        tips_box.setWordWrap(True)
        boxes_layout.addWidget(tips_box)

        weight_sub_tabs.addTab(boxes_tab, "Boxes (Packaging Reference)")

        main_layout.addWidget(weight_sub_tabs, 1)
        self.tab_widget.addTab(tab, "Weight")

        # Populate with existing data
        self._weight_populate_products(weight_cfg.get("products", {}))
        self._weight_populate_boxes(weight_cfg.get("boxes", []))

    def _weight_recalc_vol_weight(self, table, row, col, dim_cols):
        """Recalculate volumetric weight cell when L/W/H changes."""
        if col not in dim_cols:
            return
        vol_col = max(dim_cols) + 1
        try:
            l = float(table.item(row, dim_cols[0]).text() or 0) if table.item(row, dim_cols[0]) else 0
            w = float(table.item(row, dim_cols[1]).text() or 0) if table.item(row, dim_cols[1]) else 0
            h = float(table.item(row, dim_cols[2]).text() or 0) if table.item(row, dim_cols[2]) else 0
            divisor = float(self.weight_divisor_spin.value() or 6000)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0
            item = QTableWidgetItem(str(vol_w))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.blockSignals(True)
            table.setItem(row, vol_col, item)
            table.blockSignals(False)
        except (ValueError, AttributeError):
            pass

    def _weight_populate_products(self, products: dict):
        """Fill products table from config dict."""
        self.weight_products_table.blockSignals(True)
        self.weight_products_table.setRowCount(0)
        divisor = float(self.weight_divisor_spin.value() or 6000)
        for sku, data in products.items():
            row = self.weight_products_table.rowCount()
            self.weight_products_table.insertRow(row)
            l = float(data.get("length_cm") or 0)
            w = float(data.get("width_cm") or 0)
            h = float(data.get("height_cm") or 0)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0
            no_pkg = data.get("no_packaging", False)

            self.weight_products_table.setItem(row, 0, QTableWidgetItem(sku))
            self.weight_products_table.setItem(row, 1, QTableWidgetItem(data.get("name", "")))
            self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l else ""))
            self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w else ""))
            self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h else ""))
            vol_item = QTableWidgetItem(str(vol_w))
            vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.weight_products_table.setItem(row, 5, vol_item)

            # Checkbox for no_packaging
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(8, 2, 8, 2)
            chk = QCheckBox()
            chk.setChecked(bool(no_pkg))
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.weight_products_table.setCellWidget(row, 6, chk_widget)
        self.weight_products_table.blockSignals(False)
        if hasattr(self, 'products_search'):
            self._filter_products_table(self.products_search.text())

    def _weight_populate_boxes(self, boxes: list):
        """Fill boxes table from config list."""
        self.weight_boxes_table.blockSignals(True)
        self.weight_boxes_table.setRowCount(0)
        divisor = float(self.weight_divisor_spin.value() or 6000)
        for box in boxes:
            row = self.weight_boxes_table.rowCount()
            self.weight_boxes_table.insertRow(row)
            l = float(box.get("length_cm") or 0)
            w = float(box.get("width_cm") or 0)
            h = float(box.get("height_cm") or 0)
            vol_w = round((l * w * h) / divisor, 4) if divisor > 0 else 0.0

            self.weight_boxes_table.setItem(row, 0, QTableWidgetItem(box.get("name", "")))
            self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l else ""))
            self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w else ""))
            self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h else ""))
            vol_item = QTableWidgetItem(str(vol_w))
            vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.weight_boxes_table.setItem(row, 4, vol_item)
        self.weight_boxes_table.blockSignals(False)
        if hasattr(self, 'boxes_search'):
            self._filter_boxes_table(self.boxes_search.text())

    def _filter_products_table(self, text: str):
        """Filter products table rows by SKU or name."""
        text = text.lower().strip()
        for row in range(self.weight_products_table.rowCount()):
            sku_item = self.weight_products_table.item(row, 0)
            name_item = self.weight_products_table.item(row, 1)
            sku_text = sku_item.text().lower() if sku_item else ""
            name_text = name_item.text().lower() if name_item else ""
            visible = not text or text in sku_text or text in name_text
            self.weight_products_table.setRowHidden(row, not visible)

    def _filter_boxes_table(self, text: str):
        """Filter boxes table rows by box name."""
        text = text.lower().strip()
        for row in range(self.weight_boxes_table.rowCount()):
            name_item = self.weight_boxes_table.item(row, 0)
            name_text = name_item.text().lower() if name_item else ""
            visible = not text or text in name_text
            self.weight_boxes_table.setRowHidden(row, not visible)

    def _weight_add_product_row(self):
        """Add a blank product row to the products table."""
        row = self.weight_products_table.rowCount()
        self.weight_products_table.insertRow(row)
        for col in range(6):
            self.weight_products_table.setItem(row, col, QTableWidgetItem(""))
        vol_item = QTableWidgetItem("0.0")
        vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.weight_products_table.setItem(row, 5, vol_item)
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(8, 2, 8, 2)
        chk = QCheckBox()
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weight_products_table.setCellWidget(row, 6, chk_widget)

    def _weight_add_box_row(self):
        """Add a blank box row to the boxes table."""
        row = self.weight_boxes_table.rowCount()
        self.weight_boxes_table.insertRow(row)
        for col in range(4):
            self.weight_boxes_table.setItem(row, col, QTableWidgetItem(""))
        vol_item = QTableWidgetItem("0.0")
        vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.weight_boxes_table.setItem(row, 4, vol_item)

    def _weight_delete_selected(self, table):
        """Delete selected rows from the given table."""
        selected = sorted(set(idx.row() for idx in table.selectedIndexes()), reverse=True)
        for row in selected:
            table.removeRow(row)

    def _weight_import_skus_from_stock_csv(self):
        """Import SKUs from a stock CSV file into the products table."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SKUs from Stock CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            delimiter = self.config_data.get("settings", {}).get("stock_csv_delimiter", ";")
            df = pd.read_csv(file_path, sep=delimiter, dtype=str)

            # Find SKU and Name columns via column_mappings
            mappings = self.config_data.get("column_mappings", {})
            stock_mappings = mappings.get("stock", {}) if isinstance(mappings.get("stock"), dict) else {}
            sku_col = next((csv_col for csv_col, internal in stock_mappings.items() if internal == "SKU"), None)
            name_col = next((csv_col for csv_col, internal in stock_mappings.items() if internal == "Product_Name"), None)

            if not sku_col or sku_col not in df.columns:
                # Fallback: try common names
                for candidate in ["SKU", "Артикул", "sku", "Article"]:
                    if candidate in df.columns:
                        sku_col = candidate
                        break

            if not sku_col:
                QMessageBox.warning(self, "Warning", "Could not find SKU column in CSV.\nCheck column mappings in Settings → Mappings tab.")
                return

            skus_in_csv = df[sku_col].dropna().astype(str).str.strip().unique().tolist()
            skus_in_csv = [s for s in skus_in_csv if s and s != "nan"]

            # Get existing SKUs in table
            existing_skus = set()
            for r in range(self.weight_products_table.rowCount()):
                item = self.weight_products_table.item(r, 0)
                if item:
                    existing_skus.add(item.text().strip())

            # Determine names if available
            sku_to_name = {}
            if name_col and name_col in df.columns:
                for _, row in df[[sku_col, name_col]].dropna(subset=[sku_col]).iterrows():
                    sku = str(row[sku_col]).strip()
                    name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
                    if sku not in sku_to_name:
                        sku_to_name[sku] = name

            added = 0
            self.weight_products_table.blockSignals(True)
            for sku in skus_in_csv:
                if sku in existing_skus:
                    continue
                row = self.weight_products_table.rowCount()
                self.weight_products_table.insertRow(row)
                self.weight_products_table.setItem(row, 0, QTableWidgetItem(sku))
                self.weight_products_table.setItem(row, 1, QTableWidgetItem(sku_to_name.get(sku, "")))
                for col in range(2, 6):
                    self.weight_products_table.setItem(row, col, QTableWidgetItem(""))
                vol_item = QTableWidgetItem("0.0")
                vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.weight_products_table.setItem(row, 5, vol_item)
                chk_widget = QWidget()
                chk_layout = QHBoxLayout(chk_widget)
                chk_layout.setContentsMargins(8, 2, 8, 2)
                chk = QCheckBox()
                chk_layout.addWidget(chk)
                chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.weight_products_table.setCellWidget(row, 6, chk_widget)
                added += 1
            self.weight_products_table.blockSignals(False)

            QMessageBox.information(
                self, "Import Complete",
                f"Added {added} new SKUs. Skipped {len(skus_in_csv) - added} already existing."
            )

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import SKUs:\n\n{str(e)}")

    def _weight_import_products_from_csv(self):
        """Import SKU dimensions from an arbitrary CSV into the products table."""
        from shopify_tool.csv_utils import detect_csv_delimiter

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Product Dimensions from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            delimiter, _ = detect_csv_delimiter(file_path)
            df = pd.read_csv(file_path, sep=delimiter, dtype=str)

            cols_lower = {c.lower().strip(): c for c in df.columns}

            def find_col(candidates):
                for c in candidates:
                    if c in cols_lower:
                        return cols_lower[c]
                return None

            sku_col = find_col(["sku", "артикул", "article", "код", "article_no"])
            name_col = find_col(["name", "назва", "product_name", "наименование", "title"])
            l_col = find_col(["l (cm)", "l(cm)", "length_cm", "length", "l", "довжина", "длина"])
            w_col = find_col(["w (cm)", "w(cm)", "width_cm", "width", "w", "ширина"])
            h_col = find_col(["h (cm)", "h(cm)", "height_cm", "height", "h", "висота", "высота"])
            np_col = find_col(["no_packaging", "no packaging", "без упаковки", "nopackaging"])

            if not sku_col:
                cols_str = ", ".join(df.columns.tolist())
                QMessageBox.warning(
                    self, "Column Not Found",
                    f"Could not find SKU column in CSV.\n\nAvailable columns: {cols_str}\n\n"
                    "Expected one of: SKU, Артикул, Article, Код"
                )
                return

            # Ask about duplicates
            existing_skus = {}
            for r in range(self.weight_products_table.rowCount()):
                item = self.weight_products_table.item(r, 0)
                if item:
                    existing_skus[item.text().strip()] = r

            rows_in_csv = df[sku_col].dropna().astype(str).str.strip().tolist()
            new_skus = [s for s in rows_in_csv if s and s != "nan" and s not in existing_skus]
            dup_skus = [s for s in rows_in_csv if s and s != "nan" and s in existing_skus]

            update_existing = False
            if dup_skus:
                msg = QMessageBox(self)
                msg.setWindowTitle("Duplicates Found")
                msg.setText(f"Found {len(dup_skus)} SKU(s) already in the table.\nWhat would you like to do?")
                skip_btn = msg.addButton("Skip Duplicates", QMessageBox.ButtonRole.AcceptRole)
                update_btn = msg.addButton("Update Existing", QMessageBox.ButtonRole.ActionRole)
                msg.setDefaultButton(skip_btn)
                msg.exec()
                update_existing = msg.clickedButton() == update_btn

            divisor = float(self.weight_divisor_spin.value() or 6000)
            added = 0
            updated = 0
            skipped = 0

            self.weight_products_table.blockSignals(True)
            for _, csv_row in df.iterrows():
                sku = str(csv_row[sku_col]).strip() if pd.notna(csv_row[sku_col]) else ""
                if not sku or sku == "nan":
                    continue

                name = str(csv_row[name_col]).strip() if name_col and pd.notna(csv_row.get(name_col)) else ""

                def _val(col):
                    if col and pd.notna(csv_row.get(col)):
                        try:
                            return float(str(csv_row[col]).replace(",", ".").strip())
                        except ValueError:
                            pass
                    return None

                l = _val(l_col)
                w = _val(w_col)
                h = _val(h_col)
                vol_w = round((l * w * h) / divisor, 4) if (l and w and h and divisor > 0) else 0.0

                no_pkg = False
                if np_col and pd.notna(csv_row.get(np_col)):
                    val = str(csv_row[np_col]).strip().lower()
                    no_pkg = val in ("true", "1", "yes", "так", "да")

                if sku in existing_skus:
                    if not update_existing:
                        skipped += 1
                        continue
                    row = existing_skus[sku]
                    if name_col:
                        self.weight_products_table.setItem(row, 1, QTableWidgetItem(name))
                    if l_col:
                        self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l is not None else ""))
                    if w_col:
                        self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w is not None else ""))
                    if h_col:
                        self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_products_table.setItem(row, 5, vol_item)
                    chk_widget = self.weight_products_table.cellWidget(row, 6)
                    if chk_widget:
                        chk = chk_widget.findChild(QCheckBox)
                        if chk:
                            chk.setChecked(no_pkg)
                    updated += 1
                else:
                    row = self.weight_products_table.rowCount()
                    self.weight_products_table.insertRow(row)
                    self.weight_products_table.setItem(row, 0, QTableWidgetItem(sku))
                    self.weight_products_table.setItem(row, 1, QTableWidgetItem(name))
                    self.weight_products_table.setItem(row, 2, QTableWidgetItem(str(l) if l is not None else ""))
                    self.weight_products_table.setItem(row, 3, QTableWidgetItem(str(w) if w is not None else ""))
                    self.weight_products_table.setItem(row, 4, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_products_table.setItem(row, 5, vol_item)
                    chk_widget = QWidget()
                    chk_layout = QHBoxLayout(chk_widget)
                    chk_layout.setContentsMargins(8, 2, 8, 2)
                    chk = QCheckBox()
                    chk.setChecked(no_pkg)
                    chk_layout.addWidget(chk)
                    chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.weight_products_table.setCellWidget(row, 6, chk_widget)
                    added += 1
            self.weight_products_table.blockSignals(False)

            parts = [f"Added {added} new product(s)."]
            if updated:
                parts.append(f"Updated {updated} existing.")
            if skipped:
                parts.append(f"Skipped {skipped} duplicate(s).")
            QMessageBox.information(self, "Import Complete", " ".join(parts))

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import dimensions:\n\n{str(e)}")

    def _weight_import_boxes_from_csv(self):
        """Import boxes from an arbitrary CSV into the boxes table."""
        from shopify_tool.csv_utils import detect_csv_delimiter

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Boxes from CSV",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            delimiter, _ = detect_csv_delimiter(file_path)
            df = pd.read_csv(file_path, sep=delimiter, dtype=str)

            cols_lower = {c.lower().strip(): c for c in df.columns}

            def find_col(candidates):
                for c in candidates:
                    if c in cols_lower:
                        return cols_lower[c]
                return None

            name_col = find_col(["box name", "box_name", "name", "назва", "size", "box", "коробка"])
            l_col = find_col(["l (cm)", "l(cm)", "length_cm", "length", "l", "довжина", "длина"])
            w_col = find_col(["w (cm)", "w(cm)", "width_cm", "width", "w", "ширина"])
            h_col = find_col(["h (cm)", "h(cm)", "height_cm", "height", "h", "висота", "высота"])

            if not name_col:
                cols_str = ", ".join(df.columns.tolist())
                QMessageBox.warning(
                    self, "Column Not Found",
                    f"Could not find box name column in CSV.\n\nAvailable columns: {cols_str}\n\n"
                    "Expected one of: Name, Box Name, Size, Box"
                )
                return

            existing_boxes = {}
            for r in range(self.weight_boxes_table.rowCount()):
                item = self.weight_boxes_table.item(r, 0)
                if item:
                    existing_boxes[item.text().strip()] = r

            dup_boxes = [
                str(r[name_col]).strip() for _, r in df.iterrows()
                if pd.notna(r.get(name_col)) and str(r[name_col]).strip() in existing_boxes
            ]

            update_existing = False
            if dup_boxes:
                msg = QMessageBox(self)
                msg.setWindowTitle("Duplicates Found")
                msg.setText(f"Found {len(dup_boxes)} box name(s) already in the table.\nWhat would you like to do?")
                skip_btn = msg.addButton("Skip Duplicates", QMessageBox.ButtonRole.AcceptRole)
                update_btn = msg.addButton("Update Existing", QMessageBox.ButtonRole.ActionRole)
                msg.setDefaultButton(skip_btn)
                msg.exec()
                update_existing = msg.clickedButton() == update_btn

            divisor = float(self.weight_divisor_spin.value() or 6000)
            added = 0
            updated = 0
            skipped = 0

            self.weight_boxes_table.blockSignals(True)
            for _, csv_row in df.iterrows():
                name = str(csv_row[name_col]).strip() if pd.notna(csv_row[name_col]) else ""
                if not name or name == "nan":
                    continue

                def _val(col):
                    if col and pd.notna(csv_row.get(col)):
                        try:
                            return float(str(csv_row[col]).replace(",", ".").strip())
                        except ValueError:
                            pass
                    return None

                l = _val(l_col)
                w = _val(w_col)
                h = _val(h_col)
                vol_w = round((l * w * h) / divisor, 4) if (l and w and h and divisor > 0) else 0.0

                if name in existing_boxes:
                    if not update_existing:
                        skipped += 1
                        continue
                    row = existing_boxes[name]
                    if l_col:
                        self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l is not None else ""))
                    if w_col:
                        self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w is not None else ""))
                    if h_col:
                        self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_boxes_table.setItem(row, 4, vol_item)
                    updated += 1
                else:
                    row = self.weight_boxes_table.rowCount()
                    self.weight_boxes_table.insertRow(row)
                    self.weight_boxes_table.setItem(row, 0, QTableWidgetItem(name))
                    self.weight_boxes_table.setItem(row, 1, QTableWidgetItem(str(l) if l is not None else ""))
                    self.weight_boxes_table.setItem(row, 2, QTableWidgetItem(str(w) if w is not None else ""))
                    self.weight_boxes_table.setItem(row, 3, QTableWidgetItem(str(h) if h is not None else ""))
                    vol_item = QTableWidgetItem(str(vol_w))
                    vol_item.setFlags(vol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.weight_boxes_table.setItem(row, 4, vol_item)
                    added += 1
            self.weight_boxes_table.blockSignals(False)

            parts = [f"Added {added} new box(es)."]
            if updated:
                parts.append(f"Updated {updated} existing.")
            if skipped:
                parts.append(f"Skipped {skipped} duplicate(s).")
            QMessageBox.information(self, "Import Complete", " ".join(parts))

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import boxes:\n\n{str(e)}")

    def _weight_export_products_to_csv(self):
        """Export products table to a CSV file."""
        if self.weight_products_table.rowCount() == 0:
            QMessageBox.information(self, "Export", "No products to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Product Dimensions to CSV",
            "weight_products.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            rows = []
            for r in range(self.weight_products_table.rowCount()):
                sku = self.weight_products_table.item(r, 0)
                name = self.weight_products_table.item(r, 1)
                l = self.weight_products_table.item(r, 2)
                w = self.weight_products_table.item(r, 3)
                h = self.weight_products_table.item(r, 4)
                chk_widget = self.weight_products_table.cellWidget(r, 6)
                no_pkg = False
                if chk_widget:
                    chk = chk_widget.findChild(QCheckBox)
                    if chk:
                        no_pkg = chk.isChecked()
                rows.append({
                    "SKU": sku.text().strip() if sku else "",
                    "Name": name.text().strip() if name else "",
                    "L (cm)": l.text().strip() if l else "",
                    "W (cm)": w.text().strip() if w else "",
                    "H (cm)": h.text().strip() if h else "",
                    "No Packaging": str(no_pkg),
                })
            df = pd.DataFrame(rows)
            df.to_csv(file_path, sep=";", index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} product(s) to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export products:\n\n{str(e)}")

    def _weight_export_boxes_to_csv(self):
        """Export boxes table to a CSV file."""
        if self.weight_boxes_table.rowCount() == 0:
            QMessageBox.information(self, "Export", "No boxes to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Boxes to CSV",
            "weight_boxes.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            rows = []
            for r in range(self.weight_boxes_table.rowCount()):
                name = self.weight_boxes_table.item(r, 0)
                l = self.weight_boxes_table.item(r, 1)
                w = self.weight_boxes_table.item(r, 2)
                h = self.weight_boxes_table.item(r, 3)
                rows.append({
                    "Name": name.text().strip() if name else "",
                    "L (cm)": l.text().strip() if l else "",
                    "W (cm)": w.text().strip() if w else "",
                    "H (cm)": h.text().strip() if h else "",
                })
            df = pd.DataFrame(rows)
            df.to_csv(file_path, sep=";", index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} box(es) to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export boxes:\n\n{str(e)}")

    def _weight_collect_config(self) -> dict:
        """Collect weight configuration from UI tables."""
        divisor = int(self.weight_divisor_spin.value())

        products = {}
        for row in range(self.weight_products_table.rowCount()):
            sku_item = self.weight_products_table.item(row, 0)
            if not sku_item or not sku_item.text().strip():
                continue
            sku = sku_item.text().strip()
            name = (self.weight_products_table.item(row, 1) or QTableWidgetItem("")).text().strip()

            def _safe_float(table, r, c):
                item = table.item(r, c)
                if item and item.text().strip():
                    try:
                        return float(item.text().strip())
                    except ValueError:
                        pass
                return 0.0

            l = _safe_float(self.weight_products_table, row, 2)
            w = _safe_float(self.weight_products_table, row, 3)
            h = _safe_float(self.weight_products_table, row, 4)

            # Read checkbox
            no_pkg = False
            chk_widget = self.weight_products_table.cellWidget(row, 6)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    no_pkg = chk.isChecked()

            products[sku] = {
                "name": name,
                "length_cm": l,
                "width_cm": w,
                "height_cm": h,
                "no_packaging": no_pkg,
            }

        boxes = []
        for row in range(self.weight_boxes_table.rowCount()):
            name_item = self.weight_boxes_table.item(row, 0)
            if not name_item or not name_item.text().strip():
                continue
            name = name_item.text().strip()

            def _safe_float_b(r, c):
                item = self.weight_boxes_table.item(r, c)
                if item and item.text().strip():
                    try:
                        return float(item.text().strip())
                    except ValueError:
                        pass
                return 0.0

            boxes.append({
                "name": name,
                "length_cm": _safe_float_b(row, 1),
                "width_cm": _safe_float_b(row, 2),
                "height_cm": _safe_float_b(row, 3),
            })

        return {
            "volumetric_divisor": divisor,
            "products": products,
            "boxes": boxes,
        }

    def save_settings(self):
        """Saves all settings from the UI back into the config dictionary."""
        try:
            # ========================================
            # General Tab - Settings ONLY
            # ========================================
            self.config_data["settings"]["stock_csv_delimiter"] = self.stock_delimiter_edit.text()
            self.config_data["settings"]["orders_csv_delimiter"] = self.orders_delimiter_edit.text()
            self.config_data["settings"]["low_stock_threshold"] = int(self.low_stock_edit.text())
            self.config_data["settings"]["repeat_detection_days"] = self.repeat_days_input.value()

            # ========================================
            # Rules Tab - Line Item Rules
            # ========================================
            new_rules = []
            for idx, rule_w in enumerate(self.rule_widgets):
                steps = []
                for step_refs in rule_w.get("steps", []):
                    conditions = []
                    for c in step_refs["conditions"]:
                        value_widget = c.get("value_widget")
                        val = ""
                        if value_widget:
                            if isinstance(value_widget, QComboBox):
                                val = value_widget.currentText()
                            else:
                                val = value_widget.text()

                        conditions.append({
                            "field": c["field"].currentText(),
                            "operator": c["op"].currentText(),
                            "value": val,
                        })

                    actions = []
                    for act_refs in step_refs["actions"]:
                        action_type = act_refs["type"].currentText()
                        act = {"type": action_type}

                        # Serialize parameters based on type
                        if action_type in ["ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG", "SET_STATUS"]:
                            act["value"] = act_refs["param_widgets"]["value"].text()

                        elif action_type == "COPY_FIELD":
                            act["source"] = act_refs["param_widgets"]["source"].currentText()
                            act["target"] = act_refs["param_widgets"]["target"].text()

                        elif action_type == "CALCULATE":
                            act["operation"] = act_refs["param_widgets"]["operation"].currentText()
                            act["field1"] = act_refs["param_widgets"]["field1"].currentText()
                            act["field2"] = act_refs["param_widgets"]["field2"].currentText()
                            act["target"] = act_refs["param_widgets"]["target"].text()

                        elif action_type == "SET_MULTI_TAGS":
                            act["value"] = act_refs["param_widgets"]["value"].text()

                        elif action_type == "ALERT_NOTIFICATION":
                            act["message"] = act_refs["param_widgets"]["message"].text()
                            act["severity"] = act_refs["param_widgets"]["severity"].currentText()

                        elif action_type == "ADD_PRODUCT":
                            act["sku"] = act_refs["param_widgets"]["sku"].text()
                            act["quantity"] = act_refs["param_widgets"]["quantity"].value()

                        actions.append(act)

                    steps.append({
                        "conditions": conditions,
                        "match": step_refs["match_combo"].currentText(),
                        "actions": actions,
                    })

                new_rules.append({
                    "name": rule_w["name_edit"].text(),
                    "priority": idx + 1,
                    "level": rule_w["level_combo"].currentText(),
                    "steps": steps,
                })

            self.config_data["rules"] = new_rules

            # ========================================
            # Packing Lists Tab
            # ========================================
            new_packing_lists = []
            for pl_w in self.packing_list_widgets:
                filters = []
                for f in pl_w["filters"]:
                    value_widget = f.get("value_widget")
                    val = ""
                    if value_widget:
                        if isinstance(value_widget, QComboBox):
                            val = value_widget.currentText()
                        else:
                            val = value_widget.text()

                    filters.append({
                        "field": f["field"].currentText(),
                        "operator": f["op"].currentText(),
                        "value": val,
                    })

                # Parse exclude_skus from comma-separated string
                exclude_skus_text = pl_w["exclude_skus"].text().strip()
                exclude_skus = []
                if exclude_skus_text:
                    exclude_skus = [s.strip() for s in exclude_skus_text.split(',') if s.strip()]

                new_packing_lists.append({
                    "name": pl_w["name"].text(),
                    "output_filename": pl_w["filename"].text(),
                    "filters": filters,
                    "exclude_skus": exclude_skus,
                })

            self.config_data["packing_list_configs"] = new_packing_lists

            # ========================================
            # Stock Exports Tab
            # ========================================
            new_stock_exports = []
            for se_w in self.stock_export_widgets:
                filters = []
                for f in se_w["filters"]:
                    value_widget = f.get("value_widget")
                    val = ""
                    if value_widget:
                        if isinstance(value_widget, QComboBox):
                            val = value_widget.currentText()
                        else:
                            val = value_widget.text()

                    filters.append({
                        "field": f["field"].currentText(),
                        "operator": f["op"].currentText(),
                        "value": val,
                    })

                new_stock_exports.append({
                    "name": se_w["name"].text(),
                    "output_filename": se_w["filename"].text(),
                    "filters": filters,
                })

            self.config_data["stock_export_configs"] = new_stock_exports

            # ========================================
            # Mappings Tab - Column Mappings (v2 format)
            # ========================================
            # Validate mappings before saving
            orders_valid, orders_error = self.orders_mapping_widget.validate_mappings()
            if not orders_valid:
                QMessageBox.warning(
                    self,
                    "Invalid Orders Mapping",
                    f"Orders column mapping is invalid:\n{orders_error}"
                )
                return

            stock_valid, stock_error = self.stock_mapping_widget.validate_mappings()
            if not stock_valid:
                QMessageBox.warning(
                    self,
                    "Invalid Stock Mapping",
                    f"Stock column mapping is invalid:\n{stock_error}"
                )
                return

            # Get mappings from widgets
            orders_mappings = self.orders_mapping_widget.get_mappings()
            stock_mappings = self.stock_mapping_widget.get_mappings()

            # Save in v2 format
            self.config_data["column_mappings"] = {
                "version": 2,
                "orders": orders_mappings,
                "stock": stock_mappings
            }

            # ========================================
            # Mappings Tab - Courier Mappings
            # ========================================
            self.config_data["courier_mappings"] = {}

            for row_refs in self.courier_mapping_widgets:
                courier_code = row_refs["courier_code"].text().strip()
                patterns_str = row_refs["patterns"].text().strip()

                if courier_code and patterns_str:
                    # Parse comma-separated patterns
                    patterns = [
                        p.strip()
                        for p in patterns_str.split(',')
                        if p.strip()
                    ]

                    self.config_data["courier_mappings"][courier_code] = {
                        "patterns": patterns,
                        "case_sensitive": False
                    }

            # ========================================
            # Weight Tab
            # ========================================
            self.config_data["weight_config"] = self._weight_collect_config()

            # ========================================
            # Tag Categories Tab
            # ========================================
            if hasattr(self, 'tag_categories_panel'):
                is_valid, errors = self.tag_categories_panel.validate_categories()
                if not is_valid:
                    error_msg = "Tag Categories validation errors:\n\n" + "\n".join(f"- {err}" for err in errors)
                    QMessageBox.warning(self, "Tag Categories Invalid", error_msg)
                    return
                self.config_data["tag_categories"] = self.tag_categories_panel.get_categories()

            # ========================================
            # SKU Labels Tab
            # ========================================
            if hasattr(self, "sku_table"):
                sku_to_label = {}
                for row in range(self.sku_table.rowCount()):
                    sku_item = self.sku_table.item(row, 0)
                    bc_item = self.sku_table.item(row, 1)
                    path_widget = self.sku_table.cellWidget(row, 2)

                    sku = sku_item.text().strip() if sku_item else ""
                    if not sku:
                        continue

                    barcodes_raw = bc_item.text().strip() if bc_item else ""
                    barcodes = [b.strip() for b in barcodes_raw.split(",") if b.strip()]

                    path_edit = path_widget.findChild(QLineEdit) if path_widget else None
                    pdf_path = path_edit.text().strip() if path_edit else ""

                    # Preserve existing extra fields (backwards compat)
                    existing = self.config_data["sku_label_config"]["sku_to_label"].get(sku, {})
                    sku_to_label[sku] = {
                        **{k: v for k, v in existing.items() if k not in ("barcodes", "pdf_path")},
                        "barcodes": barcodes,
                        "pdf_path": pdf_path,
                    }

                self.config_data["sku_label_config"] = {
                    "sku_to_label": sku_to_label,
                    "default_printer": self.sku_default_printer_combo.currentText(),
                }

            # ========================================
            # Save to server via ProfileManager
            # ========================================
            success = self.profile_manager.save_shopify_config(
                self.client_id,
                self.config_data
            )

            if success:
                QMessageBox.information(
                    self,
                    "Success",
                    "Settings saved successfully!"
                )
                self.accept()  # Close dialog
            else:
                # Calculate config size for diagnostic info
                import json
                config_size = len(json.dumps(self.config_data, ensure_ascii=False))
                num_sets = len(self.config_data.get("set_decoders", {}))

                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save settings to server.\n\n"
                    f"Configuration size: {config_size:,} bytes\n"
                    f"Number of sets: {num_sets}\n\n"
                    f"Possible causes:\n"
                    f"• File is locked by another user\n"
                    f"• Network connection issue\n"
                    f"• Insufficient permissions\n\n"
                    f"Please wait a few seconds and try again."
                )

        except ValueError as e:
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Invalid value entered:\n\n{str(e)}\n\nPlease check your inputs."
            )
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings:\n\n{str(e)}\n\n{traceback.format_exc()}"
            )
    # ========================================
    # TAG CATEGORIES TAB
    # ========================================
    def create_tag_categories_tab(self):
        """Create the Tag Categories management tab."""
        from gui.tag_categories_dialog import TagCategoriesPanel

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        tag_categories = self.config_data.get("tag_categories", {"version": 2, "categories": {}})
        self.tag_categories_panel = TagCategoriesPanel(tag_categories, parent=tab)
        layout.addWidget(self.tag_categories_panel)

        self.tab_widget.addTab(tab, "Tag Categories")

    # ========================================
    # COLUMN CONFIGURATION TAB
    # ========================================
    def create_column_config_tab(self):
        """Create the Column Configuration tab (embedded ColumnConfigPanel)."""
        from gui.column_config_dialog import ColumnConfigPanel

        main_window = self.parent()
        if main_window is None or not hasattr(main_window, 'table_config_manager'):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.addWidget(QLabel("Column configuration is not available in this context."))
            self.tab_widget.addTab(tab, "Column Config")
            return

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        header_label = QLabel("📋 Column Configuration")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        help_text = QLabel(
            "Configure which columns are visible in the analysis table, their order, and saved views."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; margin-bottom: 6px;")
        layout.addWidget(help_text)

        self.column_config_panel = ColumnConfigPanel(
            main_window.table_config_manager,
            main_window=main_window,
            parent=tab
        )
        layout.addWidget(self.column_config_panel)

        self.tab_widget.addTab(tab, "Column Config")

    # ========================================
    # SKU LABELS TAB
    # ========================================
    def create_sku_labels_tab(self):
        """Create the SKU Label Printing settings tab."""
        from PySide6.QtPrintSupport import QPrinterInfo
        from gui.theme_manager import get_theme_manager

        theme = get_theme_manager().get_current_theme()

        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        header_label = QLabel("🖨️ SKU Label Printing")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        main_layout.addWidget(header_label)

        help_text = QLabel(
            "Map barcodes → SKU → PDF label file. "
            "Each SKU can have multiple barcodes (comma-separated). "
            "PDF files may be on the file server (UNC paths supported)."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            f"color: {theme.text_secondary}; font-style: italic; margin-bottom: 4px;"
        )
        main_layout.addWidget(help_text)

        # Default printer row
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Default Printer:"))
        self.sku_default_printer_combo = QComboBox()
        self.sku_default_printer_combo.addItem("")
        for pi in QPrinterInfo.availablePrinters():
            self.sku_default_printer_combo.addItem(pi.printerName())
        saved_printer = self.config_data["sku_label_config"].get("default_printer", "")
        if saved_printer:
            idx = self.sku_default_printer_combo.findText(saved_printer)
            if idx >= 0:
                self.sku_default_printer_combo.setCurrentIndex(idx)
        printer_row.addWidget(self.sku_default_printer_combo, 1)
        main_layout.addLayout(printer_row)

        # Mapping table group
        mapping_group = QGroupBox("SKU → Barcodes → PDF Label Mappings")
        mapping_layout = QVBoxLayout(mapping_group)

        add_btn = QPushButton("+ Add Row")
        add_btn.setMaximumWidth(140)
        add_btn.clicked.connect(self._sku_add_mapping_row)
        mapping_layout.addWidget(add_btn)

        self.sku_table = QTableWidget()
        self.sku_table.setColumnCount(4)
        self.sku_table.setHorizontalHeaderLabels(["SKU", "Barcodes (comma-separated)", "PDF File", ""])
        hdr = self.sku_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.sku_table.setColumnWidth(3, 80)
        self.sku_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sku_table.verticalHeader().setVisible(False)
        mapping_layout.addWidget(self.sku_table)

        main_layout.addWidget(mapping_group, 1)

        self.tab_widget.addTab(tab, "SKU Labels")

        # Populate from config
        self._sku_populate_table()

    def _sku_populate_table(self):
        """Populate the SKU mapping table from current config."""
        sku_to_label = self.config_data.get("sku_label_config", {}).get("sku_to_label", {})
        for sku, entry in sku_to_label.items():
            barcodes_str = ", ".join(entry.get("barcodes", []))
            pdf_path = entry.get("pdf_path", "")
            self._sku_add_mapping_row(sku=sku, barcodes_str=barcodes_str, pdf_path=pdf_path)

    def _sku_add_mapping_row(self, sku: str = "", barcodes_str: str = "", pdf_path: str = ""):
        """Add one row to the SKU mapping table."""
        row = self.sku_table.rowCount()
        self.sku_table.insertRow(row)

        self.sku_table.setItem(row, 0, QTableWidgetItem(sku))
        self.sku_table.setItem(row, 1, QTableWidgetItem(barcodes_str))

        # PDF path cell: QLineEdit + Browse button
        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(2, 1, 2, 1)
        path_layout.setSpacing(4)
        path_edit = QLineEdit(pdf_path)
        path_edit.setPlaceholderText("\\\\SERVER\\Share\\Labels\\sku.pdf")
        browse_btn = QPushButton("Browse")
        browse_btn.setMaximumWidth(60)
        browse_btn.clicked.connect(lambda _, e=path_edit: self._sku_browse_pdf(e))
        path_layout.addWidget(path_edit, 1)
        path_layout.addWidget(browse_btn)
        self.sku_table.setCellWidget(row, 2, path_widget)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setMaximumWidth(60)
        del_btn.setToolTip("Delete row")
        del_btn.clicked.connect(
            lambda _, btn=del_btn: self.sku_table.removeRow(
                self.sku_table.indexAt(btn.parent().pos()).row()
            )
        )
        del_widget = QWidget()
        del_layout = QHBoxLayout(del_widget)
        del_layout.setContentsMargins(2, 1, 2, 1)
        del_layout.addWidget(del_btn)
        self.sku_table.setCellWidget(row, 3, del_widget)

        self.sku_table.setRowHeight(row, 38)

    def _sku_browse_pdf(self, path_edit: QLineEdit):
        """Open file dialog to select a PDF label file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Label PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            path_edit.setText(path)


# ========================================
# SetEditorDialog - Dialog for adding/editing set definitions
# ========================================
class SetEditorDialog(QDialog):
    """Dialog for adding or editing a set/bundle definition."""

    def __init__(self, set_sku=None, components=None, parent=None):
        """
        Initialize the Set Editor Dialog.

        Args:
            set_sku: Set SKU (None for new set, or existing SKU for edit)
            components: List of components (for edit mode)
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Add Set" if set_sku is None else f"Edit Set: {set_sku}")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Set SKU input
        sku_layout = QFormLayout()
        self.set_sku_edit = QLineEdit(set_sku or "")
        self.set_sku_edit.setPlaceholderText("e.g., SET-WINTER-KIT")
        sku_layout.addRow("Set SKU:", self.set_sku_edit)
        layout.addLayout(sku_layout)

        # Components table
        components_label = QLabel("Components:")
        components_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(components_label)

        self.components_table = QTableWidget()
        self.components_table.setColumnCount(3)
        self.components_table.setHorizontalHeaderLabels(["Component SKU", "Quantity", "Remove"])

        # Configure columns
        header = self.components_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Component SKU
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # Quantity
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Remove
        self.components_table.setColumnWidth(1, 100)
        self.components_table.setColumnWidth(2, 80)

        layout.addWidget(self.components_table)

        # Add component button
        add_comp_btn = QPushButton("+ Add Component")
        # Use lambda to avoid passing 'checked' bool as first argument
        add_comp_btn.clicked.connect(lambda: self._add_component_row())
        layout.addWidget(add_comp_btn)

        # Populate with existing components if provided
        if components:
            for comp in components:
                self._add_component_row(comp.get("sku", ""), comp.get("quantity", 1))
        else:
            # Add one empty row for new sets
            self._add_component_row()

        # Tips
        tips_label = QLabel(
            "💡 Tip: Components are SKUs that exist in your stock file.\n"
            "Quantity indicates how many of each component are in one set."
        )
        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        tips_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; font-size: 9pt; margin-top: 10px;")
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._validate_and_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _add_component_row(self, sku="", quantity=1):
        """Add a new row to the components table."""
        # Protection: if sku is bool (from button clicked signal), convert to empty string
        if isinstance(sku, bool):
            sku = ""

        row_idx = self.components_table.rowCount()
        self.components_table.insertRow(row_idx)

        # Component SKU
        sku_edit = QLineEdit(str(sku))  # Ensure it's a string
        sku_edit.setPlaceholderText("e.g., HAT-001")
        self.components_table.setCellWidget(row_idx, 0, sku_edit)

        # Quantity
        qty_spinbox = QSpinBox()
        qty_spinbox.setMinimum(1)
        qty_spinbox.setMaximum(9999)
        qty_spinbox.setValue(quantity)
        self.components_table.setCellWidget(row_idx, 1, qty_spinbox)

        # Remove button - використовуємо sender() щоб знайти правильний row
        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(60)
        remove_btn.clicked.connect(self._remove_component_row)
        self.components_table.setCellWidget(row_idx, 2, remove_btn)

    def _remove_component_row(self):
        """Remove a component row from the table."""
        # Знаходимо який button викликав цю функцію
        button = self.sender()
        if button:
            # Знаходимо row index цієї кнопки в таблиці
            for row in range(self.components_table.rowCount()):
                if self.components_table.cellWidget(row, 2) == button:
                    self.components_table.removeRow(row)
                    break

    def _validate_and_save(self):
        """Validate inputs and accept dialog if valid."""
        # Validate Set SKU
        set_sku = self.set_sku_edit.text().strip()
        if not set_sku:
            QMessageBox.warning(self, "Validation Error", "Set SKU cannot be empty!")
            return

        # Validate components
        components = []
        for row in range(self.components_table.rowCount()):
            sku_widget = self.components_table.cellWidget(row, 0)
            qty_widget = self.components_table.cellWidget(row, 1)

            if sku_widget and qty_widget:
                comp_sku = sku_widget.text().strip()
                comp_qty = qty_widget.value()

                if comp_sku:  # Only add non-empty SKUs
                    components.append({
                        "sku": comp_sku,
                        "quantity": comp_qty
                    })

        if not components:
            QMessageBox.warning(self, "Validation Error", "Set must have at least one component!")
            return

        # All valid, accept dialog
        self.accept()

    def get_set_definition(self):
        """
        Get the set definition from the dialog.

        Returns:
            Tuple of (set_sku, components_list)
        """
        set_sku = self.set_sku_edit.text().strip()
        components = []

        print(f"[DEBUG] get_set_definition: Reading {self.components_table.rowCount()} rows from table")

        for row in range(self.components_table.rowCount()):
            sku_widget = self.components_table.cellWidget(row, 0)
            qty_widget = self.components_table.cellWidget(row, 1)

            if sku_widget and qty_widget:
                comp_sku = sku_widget.text().strip()
                comp_qty = qty_widget.value()

                print(f"[DEBUG]   Row {row}: SKU='{comp_sku}', Qty={comp_qty}, Empty={not bool(comp_sku)}")

                if comp_sku:
                    components.append({
                        "sku": comp_sku,
                        "quantity": comp_qty
                    })
            else:
                print(f"[DEBUG]   Row {row}: widgets are None (sku_widget={sku_widget}, qty_widget={qty_widget})")

        print(f"[DEBUG] get_set_definition: Collected {len(components)} non-empty components")
        return set_sku, components


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dummy_config = {
        "settings": {"stock_csv_delimiter": ";", "low_stock_threshold": 5},
        "paths": {"templates": "data/templates", "output_dir_stock": "data/output"},
        "rules": [
            {
                "name": "Test Rule",
                "match": "ANY",
                "conditions": [{"field": "SKU", "operator": "contains", "value": "TEST"}],
                "actions": [{"type": "ADD_TAG", "value": "auto_tagged"}],
            }
        ],
        "packing_lists": [
            {
                "name": "Test PL",
                "output_filename": "test.xlsx",
                "filters": [{"field": "Order_Type", "operator": "==", "value": "Single"}],
                "exclude_skus": ["SKU1"],
            }
        ],
        "stock_exports": [
            {
                "name": "Test SE",
                "template": "template.xls",
                "filters": [{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}],
            }
        ],
    }
    dialog = SettingsWindow(None, dummy_config)
    if dialog.exec():
        print("Settings saved:", json.dumps(dialog.config_data, indent=2))
    else:
        print("Cancelled.")
    sys.exit(0)
