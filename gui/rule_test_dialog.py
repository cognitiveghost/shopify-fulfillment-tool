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
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)
from gui.theme_manager import font_css, get_theme_manager


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

        # Set by _align_frames(): df_before/df_after made comparable.
        self.before_aligned = None
        self.after_existing = None
        self.added_rows = None

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

        # Close button. Same accept()-not-reject() preservation as
        # groups_management_dialog: this dialog has always closed via accept().
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

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
        self.match_summary_label.setStyleSheet(f"{font_css('label')} margin-top: 10px;")
        layout.addWidget(self.match_summary_label)

        return group

    def _create_preview_section(self):
        """Create section showing first 5 matched rows (max 100 total)."""
        group = QGroupBox("Matched Rows Preview (Before Actions)")
        layout = QVBoxLayout(group)

        # Info label
        info_label = QLabel("Showing first 5 matched rows (limited to 100 for performance)")
        theme = get_theme_manager().get_current_theme()
        info_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; {font_css('caption')}")
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
        self.actions_label.setStyleSheet(font_css("body"))
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
        legend = QLabel(
            "Yellow highlight = Modified by rule actions   |   "
            "Green highlight = Row added by rule"
        )
        theme = get_theme_manager().get_current_theme()
        legend.setStyleSheet(f"color: {theme.text_secondary}; {font_css('caption')} margin-top: 5px;")
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

            # RuleEngine.apply() may add columns and append rows, so make the
            # two frames comparable before anything diffs them.
            self._align_frames()

            # Detect matched rows by comparing before/after (works for all rule types)
            self.matches = self._detect_changed_rows()
            self.matched_count = int(self.matches.sum()) + len(self.added_rows)
            logger.info(f"[RULE TEST] Rule affected {self.matched_count} rows")

            # Populate UI sections
            self._populate_conditions_table()
            self._populate_preview_table()
            self._populate_actions_list()
            self._populate_after_actions_table()

        except Exception as e:
            logger.exception("[RULE TEST] Error testing rule")
            QMessageBox.critical(
                self,
                "Test Error",
                f"Failed to test rule:\n\n{e!s}\n\nCheck logs for details."
            )

    def _align_frames(self):
        """Make df_before and df_after comparable.

        apply() changes the frame two ways: CALCULATE/COPY_FIELD create their
        target column mid-apply, and ADD_PRODUCT rows are concatenated with
        ignore_index=True. Either one breaks a naive before/after diff.

        apply() only ever appends -- it has no drop, sort, or reindex -- so
        the first len(df_before) positional rows of df_after are the original
        rows in order. Slice positionally rather than by label: it is correct
        whether or not ignore_index fired, and label alignment is precisely
        what breaks. tests/test_rule_test_dialog.py asserts that assumption.
        """
        n = len(self.df_before)

        self.after_existing = self.df_after.iloc[:n].copy()
        self.after_existing.index = self.df_before.index
        self.added_rows = self.df_after.iloc[n:]

        # A column the rule created is absent from df_before -- reindex adds
        # it as NaN so every populate method can read a uniform column set.
        # _detect_changed_rows treats new columns specially; see there.
        self.before_aligned = self.df_before.reindex(columns=self.df_after.columns)

        if len(self.added_rows):
            logger.info(f"[RULE TEST] Rule appended {len(self.added_rows)} new rows")

    def _detect_changed_rows(self):
        """Detect which existing rows were modified, comparing aligned frames.

        Rows the rule *added* are not changes -- they have no before state --
        and are tracked separately in self.added_rows.

        A column the rule creates (CALCULATE/COPY_FIELD's target) is a
        special case: rules.py seeds it for *every* row (e.g. CALCULATE's
        `df[target] = 0.0`) before writing real results only into matched
        rows, so an unmatched row's cell also differs from the reindexed
        NaN even though the rule never touched that row. Pre-existing
        columns don't have this seeding step, so a plain before/after
        string diff is exact for them; a brand-new column instead needs the
        "does it hold a real value" check.
        """
        original_cols = set(self.df_before.columns)
        changed = pd.Series(False, index=self.before_aligned.index)

        for col in self.df_after.columns:
            after_vals = self.after_existing[col]
            if col in original_cols:
                before_vals = self.before_aligned[col].fillna("").astype(str)
                changed = changed | (before_vals != after_vals.fillna("").astype(str))
            else:
                has_value = after_vals.notna() & (after_vals != 0) & (after_vals != "") & (after_vals != 0.0)
                changed = changed | has_value

        return changed

    def _populate_conditions_table(self):
        """Populate conditions table with evaluation results (supports steps)."""
        theme = get_theme_manager().get_current_theme()
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
        summary += f"<span style='color: {theme.accent_green}; {font_css('heading')}'>{self.matched_count}</span> rows affected "
        summary += f"({percentage:.1f}% of {total_rows} total rows)"
        if len(self.added_rows):
            summary += f" — {len(self.added_rows)} added by rule"

        self.match_summary_label.setText(summary)

    def _populate_preview_table(self):
        """Populate preview table with first 5 matched rows."""
        theme = get_theme_manager().get_current_theme()
        if self.matches is None or self.matched_count == 0:
            self.preview_table.setRowCount(1)
            self.preview_table.setColumnCount(1)
            no_match_item = QTableWidgetItem("No rows matched the conditions")
            no_match_item.setForeground(QColor(theme.text_secondary))
            self.preview_table.setItem(0, 0, no_match_item)
            return

        # Get matched rows (first 5)
        matched_df = self.before_aligned[self.matches].head(5)

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
                actions_text += " → Appends to Status_Note column"
            elif action_type == "SET_STATUS":
                actions_text += " → Sets Order_Fulfillment_Status"
            elif action_type == "ADD_INTERNAL_TAG":
                actions_text += " → Appends to Internal_Tags (JSON list)"
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
        theme = get_theme_manager().get_current_theme()
        if self.matches is None or self.matched_count == 0:
            self.after_table.setRowCount(1)
            self.after_table.setColumnCount(1)
            no_match_item = QTableWidgetItem("No rows to show")
            no_match_item.setForeground(QColor(theme.text_secondary))
            self.after_table.setItem(0, 0, no_match_item)
            return

        # Aligned frames: same columns, same index, same length.
        matched_before = self.before_aligned[self.matches].head(5)
        matched_after = self.after_existing[self.matches].head(5)
        added = self.added_rows.head(5)

        display_cols = self._get_display_columns(self.after_existing)

        self.after_table.setRowCount(len(matched_after) + len(added))
        self.after_table.setColumnCount(len(display_cols))
        self.after_table.setHorizontalHeaderLabels(display_cols)

        for row_idx, (idx_after, row_after) in enumerate(matched_after.iterrows()):
            row_before = matched_before.loc[idx_after]

            for col_idx, col_name in enumerate(display_cols):
                value_before = row_before[col_name]
                value_after = row_after[col_name]

                item = QTableWidgetItem(str(value_after))

                # Highlight changed cells
                # ponytail: literal diff-highlight yellow/green, not worth two
                # new ThemeTokens fields for this one call site.
                if value_before != value_after and not (pd.isna(value_before) and pd.isna(value_after)):
                    item.setBackground(QColor("#FFEB3B"))  # Yellow
                    item.setToolTip(f"Changed from: {value_before}")

                self.after_table.setItem(row_idx, col_idx, item)

        # Rows the rule created have no before state, so they are tinted whole
        # rather than diffed cell by cell.
        for offset, (_, row_added) in enumerate(added.iterrows()):
            row_idx = len(matched_after) + offset
            for col_idx, col_name in enumerate(display_cols):
                item = QTableWidgetItem(str(row_added[col_name]))
                item.setBackground(QColor("#C8E6C9"))  # Green
                item.setToolTip("Added by rule")
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
