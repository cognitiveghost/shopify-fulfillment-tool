"""
Dialog for testing rules against current analysis data.

Allows users to:
- Preview condition evaluation results
- See matched rows before actions
- Preview actions to be applied
- See DataFrame after actions with change highlighting
"""

import logging
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem,
    QLabel, QMessageBox, QScrollArea, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)
from gui.theme_manager import get_theme_manager


class RuleTestDialog(QDialog):
    """
    Dialog for testing a rule against current analysis DataFrame.

    Shows:
    - Condition evaluation results (matched rows per condition)
    - Final match count (ALL vs ANY logic)
    - Preview of matched rows (first 5, max 100 for performance)
    - Actions to be applied
    - Preview after actions (highlighting changed cells)
    """

    def __init__(self, rule_config, analysis_df, parent=None):
        """
        Initialize test dialog.

        Args:
            rule_config (dict): Rule configuration to test
            analysis_df (pd.DataFrame): Analysis data to test against
            parent: Parent widget
        """
        super().__init__(parent)

        self.rule_config = rule_config
        self.analysis_df = analysis_df

        # Test results (populated by _run_test)
        self.test_df = None
        self.df_before = None
        self.df_after = None
        self.matches = None
        self.matched_count = 0

        self.setWindowTitle(f"Test Rule: {rule_config.get('name', 'Unnamed')}")
        self.setMinimumSize(1000, 800)
        self.setModal(True)

        self._init_ui()
        self._run_test()

    def _init_ui(self):
        """Create UI sections."""
        layout = QVBoxLayout(self)

        # Section 1: Conditions Results
        self.conditions_section = self._create_conditions_section()
        layout.addWidget(self.conditions_section)

        # Section 2: Matched Rows Preview (BEFORE actions)
        self.preview_section = self._create_preview_section()
        layout.addWidget(self.preview_section)

        # Section 3: Actions to be applied
        self.actions_section = self._create_actions_section()
        layout.addWidget(self.actions_section)

        # Section 4: After Actions Preview (AFTER actions)
        self.after_section = self._create_after_actions_section()
        layout.addWidget(self.after_section)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

    def _create_conditions_section(self):
        """Create section showing condition evaluation results."""
        group = QGroupBox("Condition Evaluation")
        layout = QVBoxLayout(group)

        # Table: Field | Operator | Value | Matched Rows
        self.conditions_table = QTableWidget()
        self.conditions_table.setColumnCount(4)
        self.conditions_table.setHorizontalHeaderLabels([
            "Field", "Operator", "Value", "Matched Rows"
        ])
        self.conditions_table.setMaximumHeight(200)
        self.conditions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.conditions_table.setSelectionMode(QTableWidget.NoSelection)

        layout.addWidget(self.conditions_table)

        # Summary label
        self.match_summary_label = QLabel()
        self.match_summary_label.setStyleSheet("font-weight: bold; font-size: 11pt; margin-top: 10px;")
        layout.addWidget(self.match_summary_label)

        return group

    def _create_preview_section(self):
        """Create section showing first 5 matched rows (max 100 total)."""
        group = QGroupBox("Matched Rows Preview (Before Actions)")
        layout = QVBoxLayout(group)

        # Info label
        info_label = QLabel("Showing first 5 matched rows (limited to 100 for performance)")
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; font-size: 9pt;")
        layout.addWidget(info_label)

        # Preview table
        self.preview_table = QTableWidget()
        self.preview_table.setMaximumHeight(250)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)

        layout.addWidget(self.preview_table)
        return group

    def _create_actions_section(self):
        """Create section showing actions to be applied."""
        group = QGroupBox("Actions to be Applied")
        layout = QVBoxLayout(group)

        # Actions list label
        self.actions_label = QLabel()
        self.actions_label.setWordWrap(True)
        self.actions_label.setStyleSheet("font-size: 10pt;")
        layout.addWidget(self.actions_label)

        return group

    def _create_after_actions_section(self):
        """Create section showing rows after actions applied."""
        group = QGroupBox("Preview After Actions")
        layout = QVBoxLayout(group)

        # Preview table
        self.after_table = QTableWidget()
        self.after_table.setMaximumHeight(250)
        self.after_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.after_table.setAlternatingRowColors(True)

        layout.addWidget(self.after_table)

        # Legend for highlights
        legend = QLabel("Yellow highlight = Modified by rule actions")
        theme = get_theme_manager().get_current_theme()
        legend.setStyleSheet(f"color: {theme.text_secondary}; font-size: 9pt; margin-top: 5px;")
        layout.addWidget(legend)

        return group

    def _run_test(self):
        """Execute rule test using RuleEngine.apply() on a copy of DataFrame."""
        from shopify_tool.rules import RuleEngine

        try:
            # Performance warning for large datasets
            if len(self.analysis_df) > 1000:
                logger.warning(f"[RULE TEST] Large dataset ({len(self.analysis_df)} rows), limiting to 100 for performance")

            # Limit to 100 rows for performance
            self.test_df = self.analysis_df.head(100).copy()
            logger.info(f"[RULE TEST] Testing rule '{self.rule_config.get('name')}' with {len(self.test_df)} rows")

            # Create single-rule engine
            engine = RuleEngine([self.rule_config])

            # Save before state
            self.df_before = self.test_df.copy()

            # Apply rule (modifies test_df in-place)
            self.df_after = engine.apply(self.test_df)

            # Detect matched rows by comparing before/after (works for all rule types)
            self.matches = self._detect_changed_rows()
            self.matched_count = self.matches.sum()
            logger.info(f"[RULE TEST] Rule affected {self.matched_count} rows")

            # Populate UI sections
            self._populate_conditions_table()
            self._populate_preview_table()
            self._populate_actions_list()
            self._populate_after_actions_table()

        except Exception as e:
            logger.error(f"[RULE TEST] Error testing rule: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Test Error",
                f"Failed to test rule:\n\n{str(e)}\n\nCheck logs for details."
            )

    def _detect_changed_rows(self):
        """Detect which rows were modified by comparing before/after DataFrames."""
        # Find common columns
        common_cols = [c for c in self.df_before.columns if c in self.df_after.columns]
        # Also check new columns added by CALCULATE
        new_cols = [c for c in self.df_after.columns if c not in self.df_before.columns]

        # Compare common columns
        changed = pd.Series(False, index=self.df_before.index)
        for col in common_cols:
            before_vals = self.df_before[col].fillna("").astype(str)
            # df_after may have extra rows from ADD_PRODUCT, limit to original index
            after_vals = self.df_after.loc[self.df_before.index, col].fillna("").astype(str)
            changed = changed | (before_vals != after_vals)

        # New columns with non-default values indicate changes
        for col in new_cols:
            if col in self.df_after.columns:
                after_vals = self.df_after.loc[self.df_before.index, col]
                has_value = after_vals.notna() & (after_vals != 0) & (after_vals != "") & (after_vals != 0.0)
                changed = changed | has_value

        return changed

    def _populate_conditions_table(self):
        """Populate conditions table with evaluation results (supports steps)."""
        steps = self.rule_config.get("steps", [])

        # Collect all conditions across all steps
        all_conditions = []
        for step_idx, step in enumerate(steps):
            for condition in step.get("conditions", []):
                all_conditions.append((step_idx + 1, step.get("match", "ALL"), condition))

        self.conditions_table.setColumnCount(5)
        self.conditions_table.setHorizontalHeaderLabels([
            "Step", "Field", "Operator", "Value", "Match Logic"
        ])
        self.conditions_table.setRowCount(len(all_conditions))

        for row_idx, (step_num, match_type, condition) in enumerate(all_conditions):
            self.conditions_table.setItem(row_idx, 0, QTableWidgetItem(f"Step {step_num}"))
            self.conditions_table.setItem(row_idx, 1, QTableWidgetItem(condition.get("field", "")))
            self.conditions_table.setItem(row_idx, 2, QTableWidgetItem(condition.get("operator", "")))
            self.conditions_table.setItem(row_idx, 3, QTableWidgetItem(str(condition.get("value", ""))))
            self.conditions_table.setItem(row_idx, 4, QTableWidgetItem(match_type))

        self.conditions_table.resizeColumnsToContents()

        # Update summary label
        total_rows = len(self.test_df)
        percentage = (self.matched_count / total_rows * 100) if total_rows > 0 else 0
        step_info = f"{len(steps)} step(s)" if len(steps) > 1 else "1 step"

        summary = f"Final Result ({step_info}, narrowing): "
        summary += f"<span style='color: #4CAF50; font-size: 14pt;'>{self.matched_count}</span> rows affected "
        summary += f"({percentage:.1f}% of {total_rows} total rows)"

        self.match_summary_label.setText(summary)

    def _populate_preview_table(self):
        """Populate preview table with first 5 matched rows."""
        if self.matches is None or self.matched_count == 0:
            self.preview_table.setRowCount(1)
            self.preview_table.setColumnCount(1)
            no_match_item = QTableWidgetItem("No rows matched the conditions")
            no_match_item.setForeground(QColor("#999"))
            self.preview_table.setItem(0, 0, no_match_item)
            return

        # Get matched rows (first 5)
        matched_df = self.df_before[self.matches].head(5)

        # Select relevant columns to display
        display_cols = self._get_display_columns(matched_df)
        display_df = matched_df[display_cols]

        self.preview_table.setRowCount(len(display_df))
        self.preview_table.setColumnCount(len(display_cols))
        self.preview_table.setHorizontalHeaderLabels(display_cols)

        for row_idx, (_, row) in enumerate(display_df.iterrows()):
            for col_idx, col_name in enumerate(display_cols):
                value = row[col_name]
                item = QTableWidgetItem(str(value))
                self.preview_table.setItem(row_idx, col_idx, item)

        self.preview_table.resizeColumnsToContents()

        # Show "and X more" if there are more matches
        if self.matched_count > 5:
            remaining = self.matched_count - 5
            logger.info(f"[RULE TEST] Showing 5 of {self.matched_count} matched rows ({remaining} more)")

    def _populate_actions_list(self):
        """Populate actions list with actions from all steps."""
        steps = self.rule_config.get("steps", [])

        all_actions = []
        for step_idx, step in enumerate(steps):
            for action in step.get("actions", []):
                all_actions.append((step_idx + 1, action))

        if not all_actions:
            self.actions_label.setText("No actions configured for this rule")
            return

        actions_text = f"<b>{len(all_actions)} action(s) across {len(steps)} step(s):</b><br><br>"

        for idx, (step_num, action) in enumerate(all_actions, 1):
            action_type = action.get("type", "")
            action_value = action.get("value", "")

            step_prefix = f"[Step {step_num}] " if len(steps) > 1 else ""
            actions_text += f"{idx}. {step_prefix}<b>{action_type}</b>"

            if action_value:
                actions_text += f": <code>{action_value}</code>"

            if action_type == "ADD_TAG":
                actions_text += f" → Appends to Status_Note column"
            elif action_type == "SET_STATUS":
                actions_text += f" → Sets Order_Fulfillment_Status"
            elif action_type == "ADD_INTERNAL_TAG":
                actions_text += f" → Appends to Internal_Tags (JSON list)"
            elif action_type == "COPY_FIELD":
                source = action.get("source", "")
                target = action.get("target", "")
                actions_text += f" → Copies '{source}' to '{target}'"
            elif action_type == "CALCULATE":
                operation = action.get("operation", "")
                field1 = action.get("field1", "")
                field2 = action.get("field2", "")
                target = action.get("target", "")
                actions_text += f" → {operation.upper()} {field1} and {field2}, store in {target}"

            actions_text += "<br>"

        self.actions_label.setText(actions_text)

    def _populate_after_actions_table(self):
        """Populate after-actions table with changed cells highlighted."""
        if self.matches is None or self.matched_count == 0:
            self.after_table.setRowCount(1)
            self.after_table.setColumnCount(1)
            no_match_item = QTableWidgetItem("No rows to show")
            no_match_item.setForeground(QColor("#999"))
            self.after_table.setItem(0, 0, no_match_item)
            return

        # Get matched rows before and after (first 5)
        matched_before = self.df_before[self.matches].head(5)
        matched_after = self.df_after[self.matches].head(5)

        # Select relevant columns to display
        display_cols = self._get_display_columns(matched_after)

        self.after_table.setRowCount(len(matched_after))
        self.after_table.setColumnCount(len(display_cols))
        self.after_table.setHorizontalHeaderLabels(display_cols)

        for row_idx, (idx_after, row_after) in enumerate(matched_after.iterrows()):
            row_before = matched_before.loc[idx_after]

            for col_idx, col_name in enumerate(display_cols):
                value_before = row_before[col_name]
                value_after = row_after[col_name]

                item = QTableWidgetItem(str(value_after))

                # Highlight changed cells
                if value_before != value_after and not (pd.isna(value_before) and pd.isna(value_after)):
                    item.setBackground(QColor("#FFEB3B"))  # Yellow
                    item.setToolTip(f"Changed from: {value_before}")

                self.after_table.setItem(row_idx, col_idx, item)

        self.after_table.resizeColumnsToContents()

    def _get_display_columns(self, df):
        """
        Get relevant columns to display in preview tables.

        Prioritizes important columns and limits total number.

        Args:
            df: DataFrame to select columns from

        Returns:
            List of column names to display
        """
        priority_cols = [
            "Order_Number",
            "SKU",
            "Order_Fulfillment_Status",
            "Status_Note",
            "Total_Price",
            "Quantity",
            "Shipping_Provider",
            "Internal_Tags"
        ]

        # Select priority columns that exist in DataFrame
        display_cols = [col for col in priority_cols if col in df.columns]

        # Add other columns if we have space (max 10 total)
        remaining_cols = [col for col in df.columns if col not in display_cols]
        if len(display_cols) < 10:
            display_cols.extend(remaining_cols[:10 - len(display_cols)])

        return display_cols
