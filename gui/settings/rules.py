"""The rule engine's rule definitions: conditions, actions, and multi-step rules."""

import logging

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.settings.fields import ACTION_TYPES, CONDITION_OPERATORS, LEGACY_ACTION_TYPES
from gui.theme_manager import font_css, get_theme_manager, set_button_role
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from shopify_tool.core import get_unique_column_values
from shopify_tool.rules import RuleEngine

logger = logging.getLogger(__name__)


class RulesPage(SettingsPage):
    """The rule engine's rules, stored under config_data["rules"].

    Attributes:
        rule_widgets (list): A list of dictionaries, each holding references
            to the UI widgets for a single rule.
    """

    def __init__(self, rules: list, analysis_df, tag_categories: dict | None = None, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self.rule_widgets = []
        self._rules_config = rules
        # ponytail: a snapshot taken when the dialog opens. The Tag Categories
        # page can add a tag while this page is open and this list will not
        # see it; the combo is editable, so the tag is still typeable. Wire up
        # a signal between the two pages if that stops being good enough.
        self._tag_categories = tag_categories or {}

        main_layout = QVBoxLayout(self)

        # Header row with Add button and rule count label
        header_row = QHBoxLayout()
        add_rule_btn = QPushButton("Add New Rule")
        set_button_role(add_rule_btn, "secondary")
        add_rule_btn.clicked.connect(lambda: [self.add_rule_widget(), self._update_priority_labels(), self._update_rules_count_label()])
        header_row.addWidget(add_rule_btn)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter rules by name…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._filter_rules)
        header_row.addWidget(self.filter_edit)

        header_row.addStretch()
        self.rules_count_label = QLabel("")
        theme = get_theme_manager().get_current_theme()
        self.rules_count_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
        header_row.addWidget(self.rules_count_label)
        main_layout.addLayout(header_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        scroll_content = QWidget()
        self.rules_layout = QVBoxLayout(scroll_content)
        self.rules_layout.setAlignment(Qt.AlignTop)
        scroll_area.setWidget(scroll_content)
        for rule_config in rules:
            self.add_rule_widget(rule_config)
        self._update_priority_labels()
        self._update_rules_count_label()

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

    def _neighbour_of_same_level(self, idx, direction):
        """Index of the nearest rule sharing this one's level, or None."""
        level = self.rule_widgets[idx]["level_combo"].currentText()
        candidate = idx + direction
        while 0 <= candidate < len(self.rule_widgets):
            if self.rule_widgets[candidate]["level_combo"].currentText() == level:
                return candidate
            candidate += direction
        return None

    def _swap_rules(self, idx_a, idx_b):
        """Swaps two rules in both the refs list and the layout."""
        widgets = self.rule_widgets
        widgets[idx_a], widgets[idx_b] = widgets[idx_b], widgets[idx_a]

        layout = self.rules_layout
        for position in sorted((idx_a, idx_b)):
            box = widgets[position]["group_box"]
            layout.removeWidget(box)
            layout.insertWidget(position, box)

        self._update_priority_labels()

    def _move_rule_up(self, widget_refs):
        """Moves a rule above the nearest rule of the same level."""
        idx = self.rule_widgets.index(widget_refs)
        target = self._neighbour_of_same_level(idx, -1)
        if target is not None:
            self._swap_rules(idx, target)

    def _move_rule_down(self, widget_refs):
        """Moves a rule below the nearest rule of the same level."""
        idx = self.rule_widgets.index(widget_refs)
        target = self._neighbour_of_same_level(idx, +1)
        if target is not None:
            self._swap_rules(idx, target)

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

            rule_w["up_btn"].setEnabled(
                self._neighbour_of_same_level(idx, -1) is not None
            )
            rule_w["down_btn"].setEnabled(
                self._neighbour_of_same_level(idx, +1) is not None
            )

    def _filter_rules(self, text):
        """Hides rule cards whose name does not contain `text`."""
        needle = (text or "").strip().lower()
        for rule_w in self.rule_widgets:
            name = rule_w["name_edit"].text().lower()
            rule_w["group_box"].setVisible(not needle or needle in name)

    def _repopulate_field_combos(self, rule_widget_refs):
        """Rebuilds condition field combos after the rule's level changed.

        A field the new level does not offer is kept as an extra item so a
        saved condition is never silently reset; Task 6's validation marks it.
        """
        level = rule_widget_refs["level_combo"].currentText()
        available_fields = self.get_available_rule_fields(level=level)

        for step_refs in rule_widget_refs.get("steps", []):
            for cond_refs in step_refs["conditions"]:
                combo = cond_refs["field"]
                previous = combo.currentText()

                combo.blockSignals(True)
                combo.clear()
                for field in available_fields:
                    combo.addItem(field)
                    if field.startswith("---"):
                        combo.model().item(combo.count() - 1).setEnabled(False)

                index = combo.findText(previous)
                if index < 0:
                    combo.addItem(previous)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
                # Re-run the value validation first so a field that just became
                # resolvable again does not keep the old "never match" message,
                # then re-apply the resolvability mark on top of it.
                self._perform_validation(cond_refs)
                self._check_field_resolvable(cond_refs)

    def _update_rule_summary(self, widget_refs):
        """Rewrites a rule's header summary from its current widget state."""
        level = widget_refs["level_combo"].currentText()
        steps = widget_refs.get("steps", [])
        conditions = sum(len(s["conditions"]) for s in steps)
        actions = sum(len(s["actions"]) for s in steps)

        def plural(n, word):
            return f"{n} {word}" if n == 1 else f"{n} {word}s"

        widget_refs["summary_label"].setText(
            f"{level} · {plural(len(steps), 'step')} · "
            f"{plural(conditions, 'condition')} · {plural(actions, 'action')}"
        )

    def _update_rule_summary_for_step(self, step_refs):
        """Finds the rule a step belongs to and refreshes its summary."""
        for rule_w in self.rule_widgets:
            if step_refs in rule_w.get("steps", []):
                self._update_rule_summary(rule_w)
                return

    def get_available_rule_fields(self, level="article"):
        """Fields offered for a condition on a rule of the given level.

        Order-level field names come from RuleEngine.ORDER_LEVEL_FIELDS so the
        editor cannot drift from what the engine dispatches on, and they are
        offered only on order-level rules -- on an article rule they are never
        DataFrame columns, so selecting one produces a condition the engine
        treats as no-match.
        """
        fields = []
        if level == "order":
            fields += ["--- ORDER-LEVEL FIELDS ---"]
            fields += list(RuleEngine.ORDER_LEVEL_FIELDS.keys())

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

        fields += common_fields

        # Get ALL columns from DataFrame
        if self.analysis_df is not None and not self.analysis_df.empty:
            all_columns = sorted(self.analysis_df.columns.tolist())

            # Filter out internal columns (starting with _) and already listed common fields
            # But keep separators for checking
            common_field_names = [f for f in common_fields if not f.startswith("---")]

            custom_columns = [
                col for col in all_columns
                if not col.startswith('_')
                and col not in common_field_names  # Avoid duplicates
            ]

            if custom_columns:
                fields += ["--- OTHER AVAILABLE FIELDS ---"] + custom_columns
        else:
            logger.warning(f"[RULE ENGINE] No analysis_df available (is None: {self.analysis_df is None})")

        return fields

    def get_configured_tags(self) -> list[str]:
        """Every tag named by the configured tag categories, sorted and deduped.

        SYSTEM_TAGS (core.py) are deliberately excluded: the analyser owns
        them, and offering them here invites rules that fight it. The combo
        that consumes this is editable, so they remain typeable.
        """
        from shopify_tool.tag_manager import _normalize_tag_categories

        tags = set()
        for category in _normalize_tag_categories(self._tag_categories).values():
            tags.update(category.get("tags", []))
        return sorted(tags)

    def _update_rules_count_label(self):
        """Update the rules summary label in the Rules tab header."""
        if not hasattr(self, 'rules_count_label'):
            return
        rules = self._rules_config
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
        theme = get_theme_manager().get_current_theme()
        config_was_none = not isinstance(config, dict)
        if not isinstance(config, dict):
            config = {"name": "New Rule", "level": "article", "match": "ALL", "conditions": [], "actions": []}
        rule_box = QGroupBox()
        rule_layout = QVBoxLayout(rule_box)
        header_layout = QHBoxLayout()

        # Disclosure toggle
        toggle_btn = QPushButton("▶")
        set_button_role(toggle_btn, "secondary")
        toggle_btn.setMaximumWidth(30)
        toggle_btn.setToolTip("Show or hide this rule's conditions and actions")
        header_layout.addWidget(toggle_btn)

        # Priority label (e.g., "Article #1", "Order #2")
        priority_label = QLabel("")
        priority_label.setMinimumWidth(70)
        priority_label.setStyleSheet(f"{font_css('label')} color: {theme.accent_blue};")
        header_layout.addWidget(priority_label)

        # Up button
        up_btn = QPushButton("↑")
        set_button_role(up_btn, "secondary")
        up_btn.setMaximumWidth(30)
        up_btn.setToolTip("Move rule up (higher priority)")
        header_layout.addWidget(up_btn)

        # Down button
        down_btn = QPushButton("↓")
        set_button_role(down_btn, "secondary")
        down_btn.setMaximumWidth(30)
        down_btn.setToolTip("Move rule down (lower priority)")
        header_layout.addWidget(down_btn)

        # Test button
        test_btn = QPushButton("Test")
        set_button_role(test_btn, "secondary")
        test_btn.setMaximumWidth(70)
        test_btn.setToolTip("Test this rule against current analysis data")
        # As with Delete Rule below: the per-widget green background is
        # deliberate and overrides the secondary role's background.
        test_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.accent_green};
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.accent_green};
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

        summary_label = QLabel("")
        summary_label.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')}")
        header_layout.addWidget(summary_label)

        delete_rule_btn = QPushButton("Delete Rule")
        set_button_role(delete_rule_btn, "secondary")
        # The per-widget background wins over the role on purpose: destructive
        # red stays. The role is here so the Hub's inventory guard sees it
        # marked, and so it picks up the secondary border/disabled treatment.
        delete_rule_btn.setStyleSheet(f"background-color: {theme.accent_red}; color: white;")
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

        # Steps container
        steps_container = QVBoxLayout()

        # "Add Step" button
        add_step_btn = QPushButton("+ Add Step")
        set_button_role(add_step_btn, "secondary")
        add_step_btn.setToolTip(
            "Add a step to this rule.\n"
            "article rules: each step narrows the rows matched by the step before it.\n"
            "order rules: each step is a gate on the whole order - if it does not\n"
            "match, the rule stops and later steps do not run."
        )
        add_step_btn.setStyleSheet(f"color: {theme.accent_blue}; font-weight: bold;")

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(level_layout)
        body_layout.addLayout(steps_container)
        body_layout.addWidget(add_step_btn, 0, Qt.AlignLeft)
        rule_layout.addWidget(body)

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
            "body": body,
            "summary_label": summary_label,
        }
        self.rule_widgets.append(widget_refs)
        delete_rule_btn.clicked.connect(lambda: self._delete_widget_from_list(widget_refs, self.rule_widgets))
        up_btn.clicked.connect(lambda: self._move_rule_up(widget_refs))
        down_btn.clicked.connect(lambda: self._move_rule_down(widget_refs))
        test_btn.clicked.connect(lambda: self._test_rule(widget_refs))
        add_step_btn.clicked.connect(lambda: self._add_step_widget(widget_refs))
        level_combo.currentTextChanged.connect(
            lambda: [self._repopulate_field_combos(widget_refs),
                     self._update_priority_labels(),
                     self._update_rule_summary(widget_refs)]
        )

        def _toggle():
            visible = body.isHidden()
            body.setVisible(visible)
            toggle_btn.setText("▼" if visible else "▶")

        toggle_btn.clicked.connect(_toggle)

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

        # A rule loaded from config starts collapsed; a rule the user just
        # added starts expanded, since they are about to edit it.
        expanded = config_was_none
        body.setVisible(expanded)
        toggle_btn.setText("▼" if expanded else "▶")
        self._update_rule_summary(widget_refs)

    def _add_step_widget(self, rule_widget_refs, step_config=None):
        """Adds a step (IF conditions + THEN actions) to a rule.

        Each step is a narrowing filter: step N only processes rows
        that matched step N-1.

        Args:
            rule_widget_refs (dict): Rule widget references containing steps list
            step_config (dict, optional): Step configuration with conditions/match/actions
        """
        theme = get_theme_manager().get_current_theme()
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
                f"color: {theme.accent_orange}; {font_css('label')} "
                "padding: 4px; margin: 2px 0;"
            )
            steps_container.addWidget(separator_label)

        # Step wrapper
        step_box = QGroupBox(f"Step {step_number}")
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
        set_button_role(add_condition_btn, "secondary")
        conditions_layout.addWidget(add_condition_btn, 0, Qt.AlignLeft)
        step_layout.addWidget(conditions_box)

        # Actions box ("THEN")
        actions_box = QGroupBox("THEN perform these actions:")
        actions_layout = QVBoxLayout(actions_box)
        actions_rows_layout = QVBoxLayout()
        actions_layout.addLayout(actions_rows_layout)
        add_action_btn = QPushButton("Add Action")
        set_button_role(add_action_btn, "secondary")
        actions_layout.addWidget(add_action_btn, 0, Qt.AlignLeft)
        step_layout.addWidget(actions_box)

        # Delete step button (not for step 1)
        delete_step_btn = None
        if step_number > 1:
            delete_step_btn = QPushButton("Delete Step")
            set_button_role(delete_step_btn, "secondary")
            delete_step_btn.setStyleSheet(f"color: {theme.accent_red};")
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
            "level_combo": rule_widget_refs["level_combo"],
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

        self._update_rule_summary(rule_widget_refs)

    def _delete_step(self, rule_widget_refs, step_refs):
        """Delete a step from a rule (never deletes step 1)."""
        steps = rule_widget_refs["steps"]
        if step_refs not in steps or len(steps) <= 1:
            return

        steps.index(step_refs)
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

        self._update_rule_summary(rule_widget_refs)

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
        level_combo = rule_widget_refs.get("level_combo")
        level = level_combo.currentText() if level_combo else "article"
        available_fields = self.get_available_rule_fields(level=level)

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
        op_combo.addItems(CONDITION_OPERATORS)
        delete_btn = QPushButton("X")
        set_button_role(delete_btn, "secondary")

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
        op_combo.setCurrentText(config.get("operator", CONDITION_OPERATORS[0]))
        initial_value = config.get("value", "")

        # The row goes inside a vertical wrapper so its validation message can
        # have a full-width line of its own underneath, instead of being
        # appended as one more horizontal cell past the delete button. The
        # wrapper takes over the row's padding -- a nested layout gets none of
        # its own -- so the row's geometry is unchanged.
        row_widget = QWidget()
        outer_layout = QVBoxLayout(row_widget)
        outer_layout.setSpacing(2)
        row_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addLayout(row_layout)

        # One feedback label per condition row, alive for the row's whole
        # lifetime. A hidden label is skipped by the layout, so a row with
        # nothing to say keeps exactly its old height.
        feedback_label = QLabel()
        feedback_label.setWordWrap(True)
        feedback_label.hide()
        outer_layout.addWidget(feedback_label)

        condition_refs = {
            "widget": row_widget,
            "field": field_combo,
            "op": op_combo,
            "value_widget": None,
            "row_layout": row_layout,
            "feedback_label": feedback_label,
            "level_combo": rule_widget_refs.get("level_combo"),
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
            lambda: [self._delete_row_from_list(row_widget, rule_widget_refs["conditions"], condition_refs),
                     self._update_rule_summary_for_step(rule_widget_refs)]
        )

        self._update_rule_summary_for_step(rule_widget_refs)

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

        # Drop any message the previous operator left behind. The label belongs
        # to the row, so it is reused rather than rebuilt.
        condition_refs["feedback_label"].clear()
        condition_refs["feedback_label"].hide()

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
            self._check_field_resolvable(condition_refs)
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
        condition_refs["row_layout"].insertWidget(2, new_widget, 1)
        condition_refs["value_widget"] = new_widget

        # Connect validation for QLineEdit widgets (QLineEdit is already imported globally)
        if isinstance(new_widget, QLineEdit):
            new_widget.textChanged.connect(lambda: self._validate_condition_value(condition_refs))

        # Mark an unresolvable field as soon as the row is built. This is the
        # only path that runs on load -- the value validation that also calls it
        # is driven by textChanged, which a programmatic setText above does not
        # reach (it is connected after the text is set).
        self._check_field_resolvable(condition_refs)

    def _validate_condition_value(self, condition_refs):
        """
        Validate condition value based on operator type.

        Validates in real-time with debouncing for regex patterns (500ms).
        Other operators validate immediately.

        Args:
            condition_refs (dict): Condition widget references
        """

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
            validate_list,
            validate_numeric,
            validate_range,
            validate_regex,
        )

        op = condition_refs["op"].currentText()
        value_widget = condition_refs.get("value_widget")

        if not value_widget:
            return

        # Get value based on widget type
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

        self._check_field_resolvable(condition_refs)

    def _show_validation_feedback(self, condition_refs, status, message):
        """
        Show validation feedback with visual indicators.

        Args:
            condition_refs (dict): Condition widget references
            status (str): "error", "warning", "success", or "clear"
            message (str): Message to display
        """
        theme = get_theme_manager().get_current_theme()

        # ponytail: literal validation-tint background colors, not worth new
        # ThemeTokens fields for ~2 call sites; revisit if more validation
        # states are added.
        border_css = {
            "error": f"border: 1px solid {theme.accent_red}; background-color: #ffebee; color: #1A1A1A;",
            "warning": f"border: 1px solid {theme.accent_orange}; background-color: #fff3e0; color: #1A1A1A;",
            "success": f"border: 1px solid {theme.accent_green};",
        }
        text_color = {
            "error": theme.accent_red,
            "warning": theme.accent_orange,
            "success": theme.accent_green,
        }
        if status not in text_color:
            status = "clear"

        # The message describes the condition; only the tinted border needs a
        # value widget. An operator that takes no value still has something to
        # say -- most of all that its field will never match.
        value_widget = condition_refs.get("value_widget")
        if value_widget is not None:
            value_widget.setStyleSheet(border_css.get(status, ""))

        feedback_label = condition_refs["feedback_label"]
        if status == "clear":
            feedback_label.clear()
            feedback_label.hide()
            return

        feedback_label.setStyleSheet(f"color: {text_color[status]}; {font_css('caption')}")
        feedback_label.setText(message)
        feedback_label.show()

    def _check_field_resolvable(self, condition_refs):
        """Marks a field the engine will treat as no-match.

        The engine fails a condition closed when its field is not a column (or,
        on an order rule, a known order-level field). Showing that here means the
        user sees it while editing rather than finding a rule that quietly
        stopped firing.

        Returns:
            bool: True when the field is one the engine can evaluate.
        """
        theme = get_theme_manager().get_current_theme()
        combo = condition_refs.get("field")
        if combo is None:
            return True

        field = combo.currentText()
        level_combo = condition_refs.get("level_combo")
        level = level_combo.currentText() if level_combo else "article"

        if not field or field.startswith("---"):
            resolvable = False
        elif field in set(self.get_available_rule_fields(level=level)):
            resolvable = True
        elif self.analysis_df is None or self.analysis_df.empty:
            # No analysis loaded, so the offered list is only a hardcoded guess
            # at the columns and any real client column would flag falsely. The
            # one thing still provable is an order-level field on an article
            # rule -- that never resolves whatever the data looks like.
            resolvable = field not in RuleEngine.ORDER_LEVEL_FIELDS
        else:
            resolvable = False

        if resolvable:
            combo.setStyleSheet("")
        else:
            combo.setStyleSheet(f"border: 1px solid {theme.accent_red};")
            self._show_validation_feedback(
                condition_refs,
                "error",
                f"'{field}' is not available on an {level} rule - this condition "
                f"will never match.",
            )
        return resolvable

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
        type_combo.addItems(ACTION_TYPES)
        # A retired action type is added to this row's combo only, so the rule
        # round-trips instead of being silently retyped: setCurrentText on a
        # non-editable QComboBox is a no-op for an absent string, which would
        # leave the row showing ACTION_TYPES[0] and save that over the user's
        # rule. New rows still offer only the current types.
        configured_type = config.get("type", ACTION_TYPES[0])
        if configured_type and configured_type not in ACTION_TYPES:
            type_combo.addItem(configured_type)
        type_combo.setCurrentText(configured_type)

        # Delete button
        delete_btn = QPushButton("X")
        set_button_role(delete_btn, "secondary")

        row_layout.addWidget(type_combo)
        # Параметри будуть вставлені динамічно

        # The row goes inside a vertical wrapper so the retired-action notice
        # gets a full-width line of its own underneath, instead of being
        # squeezed in past the delete button. The wrapper takes over the row's
        # padding, so the row's geometry is unchanged.
        row_widget = QWidget()
        outer_layout = QVBoxLayout(row_widget)
        outer_layout.setSpacing(2)
        row_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addLayout(row_layout)

        # One label per action row, alive for the row's whole lifetime. Hidden
        # labels are skipped by the layout, so an unflagged row keeps its
        # current height.
        legacy_label = QLabel()
        legacy_label.setWordWrap(True)
        legacy_label.hide()
        outer_layout.addWidget(legacy_label)

        # Зберегти посилання
        action_refs = {
            "widget": row_widget,
            "type": type_combo,
            "param_widgets": {},
            "param_layout": row_layout,
            "legacy_label": legacy_label,
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
            lambda: [self._delete_row_from_list(row_widget, rule_widget_refs["actions"], action_refs),
                     self._update_rule_summary_for_step(rule_widget_refs)]
        )

        self._update_rule_summary_for_step(rule_widget_refs)

    def _refresh_legacy_action_flag(self, action_refs):
        """Explain a retired action type on the row that still uses it.

        These three still run -- the engine is deliberately unchanged -- so
        this is advice, not an error. It leads with what the action really
        does, because the name says the opposite.
        """
        label = action_refs["legacy_label"]
        action_type = action_refs["type"].currentText()

        if action_type not in LEGACY_ACTION_TYPES:
            label.clear()
            label.hide()
            return

        replacement = (
            "one ADD_INTERNAL_TAG per tag"
            if action_type == "SET_MULTI_TAGS"
            else "ADD_INTERNAL_TAG"
        )
        theme = get_theme_manager().get_current_theme()
        label.setStyleSheet(f"color: {theme.accent_orange}; {font_css('caption')}")
        label.setText(
            f"Writes the Status_Note text column, not tags. "
            f"Replace with {replacement} to add a real tag."
        )
        label.show()

    def _on_action_type_changed(self, action_refs, initial_config=None):
        """Dynamically updates parameter widgets based on action type."""
        action_type = action_refs["type"].currentText()

        self._refresh_legacy_action_flag(action_refs)

        # Очистити існуючі параметри
        for widget in action_refs["param_widgets"].values():
            widget.deleteLater()
        action_refs["param_widgets"].clear()

        layout = action_refs["param_layout"]
        insert_pos = 1  # Після type combo

        # Створити widgets залежно від типу
        if action_type in ["ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"]:
            # Editable: an unlisted tag must stay typeable, and an unknown
            # value loaded from config must round-trip rather than snap to
            # item 0 the way a fixed combo would.
            value_combo = WheelIgnoreComboBox()
            value_combo.setEditable(True)
            value_combo.addItems(self.get_configured_tags())
            # On an editable combo the placeholder lives on the line edit --
            # QComboBox.setPlaceholderText only shows at currentIndex == -1.
            value_combo.lineEdit().setPlaceholderText("Tag")
            if initial_config:
                value_combo.setCurrentText(initial_config.get("value", ""))
            layout.insertWidget(insert_pos, value_combo, 1)
            action_refs["param_widgets"]["value"] = value_combo

        elif action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_STATUS"]:
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

    def collect(self) -> dict:
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
                    if action_type in ["ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"]:
                        act["value"] = act_refs["param_widgets"]["value"].currentText()

                    elif action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_STATUS"]:
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

        return {"rules": new_rules}
